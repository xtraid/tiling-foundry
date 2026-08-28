"""Closed case and run documents for opt-in, self-contained run dossiers."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path, PurePosixPath
import re
from typing import Final

from formats.pipeline_snapshot import (
    PipelineSnapshotError,
    _load_json_bytes,
    _require_array,
    _require_exact_fields,
    _require_integer,
    _require_literal,
    _require_object,
    _require_sha256,
    _require_string,
)
from model.region import Region
from model.solver_trace import DOMAIN_ALL, SolverTrace


CASE_SCHEMA: Final = "wang-run-case-v1"
RUN_SCHEMA: Final = "wang-run-dossier-v1"
CLASS_SAT: Final = "sat-end-to-end"
CLASS_ROOT_CONFLICT: Final = "unsat-root-conflict"
CLASS_PROPAGATION: Final = "unsat-propagation-contradiction"
CLASS_SEARCH: Final = "unsat-non-superficial-search"
CLASSIFICATIONS: Final = frozenset(
    {CLASS_SAT, CLASS_ROOT_CONFLICT, CLASS_PROPAGATION, CLASS_SEARCH}
)
SOLVERS: Final = frozenset({"reference", "optimized"})
STATUSES: Final = frozenset({"sat", "unsat"})
STAGES: Final = (
    "parse",
    "region_build",
    "encoding",
    "solve",
    "verify",
    "export",
    "render",
)
_CASE_ID = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
_GIT_COMMIT = re.compile(r"[0-9a-f]{40}\Z")
_MEDIA_TYPES = frozenset({"application/json", "image/png", "image/gif"})


@dataclass(frozen=True, slots=True)
class InitialDomainOverride:
    cell: int
    domain: int


@dataclass(frozen=True, slots=True)
class RunCase:
    identifier: str
    title: str
    classification: str
    description: str
    source: str
    solver: str
    expected_status: str
    event_capacity: int
    checkpoint_interval: int
    checkpoint_capacity: int
    initial_domain_overrides: tuple[InitialDomainOverride, ...]


def _nonempty_string(value: object, path: str) -> str:
    text = _require_string(value, path)
    if not text or text != text.strip():
        raise PipelineSnapshotError(f"{path}: must be nonempty without edge space")
    return text


def _boolean(value: object, path: str) -> bool:
    if type(value) is not bool:
        raise PipelineSnapshotError(f"{path}: must be a boolean")
    return value


def _nullable_integer(value: object, path: str) -> int | None:
    if value is None:
        return None
    return _require_integer(value, path, nonnegative=True)


def _relative_path(value: object, path: str, *, prefix: str | None = None) -> str:
    text = _nonempty_string(value, path)
    if "\\" in text or re.fullmatch(r"[A-Za-z0-9._/-]+", text) is None:
        raise PipelineSnapshotError(
            f"{path}: must use only portable POSIX path characters"
        )
    parsed = PurePosixPath(text)
    if parsed.is_absolute() or parsed.as_posix() != text or any(
        part in ("", ".", "..") for part in parsed.parts
    ):
        raise PipelineSnapshotError(f"{path}: must be a normalized relative path")
    if prefix is not None and (not parsed.parts or parsed.parts[0] != prefix):
        raise PipelineSnapshotError(f"{path}: must remain below {prefix}/")
    return text


def _validate_case_override_shape(
    classification: str,
    overrides: tuple[InitialDomainOverride, ...],
    path: str,
) -> None:
    if classification in (CLASS_SAT, CLASS_SEARCH) and overrides:
        raise PipelineSnapshotError(f"{path}: this case class forbids overrides")
    if classification == CLASS_ROOT_CONFLICT and not (
        len(overrides) == 1 and overrides[0].domain == 0
    ):
        raise PipelineSnapshotError(
            f"{path}: root conflict requires one empty active-cell domain"
        )
    if classification == CLASS_PROPAGATION and not (
        len(overrides) == 1
        and overrides[0].domain > 0
        and overrides[0].domain & (overrides[0].domain - 1) == 0
    ):
        raise PipelineSnapshotError(
            f"{path}: propagation contradiction requires one singleton domain"
        )


def load_run_case(path: str | Path, repository_root: str | Path) -> RunCase:
    """Load one strict, repository-relative dossier case."""
    case_path = Path(path)
    try:
        document = _load_json_bytes(case_path.read_bytes(), str(case_path))
    except OSError as error:
        raise PipelineSnapshotError(f"cannot read case {case_path!s}: {error}") from error
    _require_exact_fields(
        document,
        frozenset(
            {
                "schema",
                "id",
                "title",
                "classification",
                "description",
                "source",
                "solver",
                "expected_status",
                "trace",
                "initial_domain_overrides",
            }
        ),
        "$",
    )
    _require_literal(document["schema"], CASE_SCHEMA, "$.schema")
    identifier = _nonempty_string(document["id"], "$.id")
    if _CASE_ID.fullmatch(identifier) is None:
        raise PipelineSnapshotError("$.id: must be a lowercase hyphenated identifier")
    title = _nonempty_string(document["title"], "$.title")
    classification = _nonempty_string(document["classification"], "$.classification")
    if classification not in CLASSIFICATIONS:
        raise PipelineSnapshotError("$.classification: is not a dossier case class")
    description = _nonempty_string(document["description"], "$.description")
    source = _relative_path(document["source"], "$.source")
    if not source.endswith(".cm13"):
        raise PipelineSnapshotError("$.source: must name a .cm13 input")
    source_path = Path(repository_root) / source
    if not source_path.is_file():
        raise PipelineSnapshotError(f"$.source: repository input does not exist: {source}")
    solver = _nonempty_string(document["solver"], "$.solver")
    if solver not in SOLVERS:
        raise PipelineSnapshotError("$.solver: is not a native traced solver")
    expected_status = _nonempty_string(document["expected_status"], "$.expected_status")
    if expected_status not in STATUSES:
        raise PipelineSnapshotError("$.expected_status: must equal sat or unsat")
    if (classification == CLASS_SAT) != (expected_status == "sat"):
        raise PipelineSnapshotError("$.expected_status: disagrees with classification")

    trace = _require_object(document["trace"], "$.trace")
    _require_exact_fields(
        trace,
        frozenset({"event_capacity", "checkpoint_interval", "checkpoint_capacity"}),
        "$.trace",
    )
    event_capacity = _require_integer(
        trace["event_capacity"], "$.trace.event_capacity", nonnegative=True
    )
    checkpoint_interval = _require_integer(
        trace["checkpoint_interval"],
        "$.trace.checkpoint_interval",
        nonnegative=True,
    )
    checkpoint_capacity = _require_integer(
        trace["checkpoint_capacity"],
        "$.trace.checkpoint_capacity",
        nonnegative=True,
    )
    if not 2 <= event_capacity <= 100_000:
        raise PipelineSnapshotError("$.trace.event_capacity: must be in [2, 100000]")
    if (checkpoint_interval == 0) != (checkpoint_capacity == 0):
        raise PipelineSnapshotError(
            "$.trace: checkpoint interval and capacity must be jointly set"
        )

    overrides: list[InitialDomainOverride] = []
    cells: set[int] = set()
    for index, raw in enumerate(
        _require_array(document["initial_domain_overrides"], "$.initial_domain_overrides")
    ):
        item_path = f"$.initial_domain_overrides[{index}]"
        item = _require_object(raw, item_path)
        _require_exact_fields(item, frozenset({"cell", "domain"}), item_path)
        cell = _require_integer(item["cell"], f"{item_path}.cell", nonnegative=True)
        domain = _require_integer(
            item["domain"], f"{item_path}.domain", nonnegative=True
        )
        if domain > DOMAIN_ALL:
            raise PipelineSnapshotError(f"{item_path}.domain: is not a Wang domain")
        if cell in cells:
            raise PipelineSnapshotError(f"{item_path}.cell: duplicates an override")
        cells.add(cell)
        overrides.append(InitialDomainOverride(cell=cell, domain=domain))
    if tuple(item.cell for item in overrides) != tuple(sorted(cells)):
        raise PipelineSnapshotError("$.initial_domain_overrides: must be cell-sorted")
    parsed_overrides = tuple(overrides)
    _validate_case_override_shape(
        classification,
        parsed_overrides,
        "$.initial_domain_overrides",
    )

    return RunCase(
        identifier=identifier,
        title=title,
        classification=classification,
        description=description,
        source=source,
        solver=solver,
        expected_status=expected_status,
        event_capacity=event_capacity,
        checkpoint_interval=checkpoint_interval,
        checkpoint_capacity=checkpoint_capacity,
        initial_domain_overrides=parsed_overrides,
    )


def initial_domains_for_case(case: RunCase, region: Region) -> tuple[int, ...] | None:
    """Expand sparse case overrides to the public dense solver option."""
    if not isinstance(case, RunCase):
        raise TypeError("case must be a RunCase")
    if not isinstance(region, Region):
        raise TypeError("region must be a Region")
    if not case.initial_domain_overrides:
        return None
    domains = [DOMAIN_ALL if active else 0 for active in region.active]
    for override in case.initial_domain_overrides:
        if override.cell >= len(domains):
            raise PipelineSnapshotError("initial domain override lies outside region")
        if not region.active[override.cell]:
            raise PipelineSnapshotError("initial domain override targets an inactive cell")
        domains[override.cell] = override.domain
    return tuple(domains)


def validate_case_outcome(case: RunCase, trace: SolverTrace) -> None:
    """Prove that an observed trace has the case class claimed by its input."""
    if trace.solver != case.solver:
        raise PipelineSnapshotError("observed trace solver disagrees with case")
    if trace.status.value != case.expected_status:
        raise PipelineSnapshotError("observed trace status disagrees with case")
    if trace.truncated:
        raise PipelineSnapshotError("versioned dossier cases require a complete trace")
    events = trace.events
    counts = {kind: sum(event.kind == kind for event in events) for kind in (
        "decision", "domain_reduction", "propagation", "conflict", "backtrack"
    )}
    maximum_depth = max(event.depth for event in events)
    conflicts = tuple(event for event in events if event.kind == "conflict")
    if case.classification == CLASS_SAT:
        if trace.status.value != "sat":
            raise PipelineSnapshotError("SAT case did not produce SAT")
        return
    if not conflicts:
        raise PipelineSnapshotError("UNSAT case did not record a conflict")
    if case.classification == CLASS_ROOT_CONFLICT:
        if not (
            len(events) == 3
            and conflicts[0].phase == "initial"
            and counts["domain_reduction"] == 0
            and counts["decision"] == 0
            and counts["backtrack"] == 0
            and maximum_depth == 0
        ):
            raise PipelineSnapshotError("trace is not an immediate root conflict")
    elif case.classification == CLASS_PROPAGATION:
        if not (
            conflicts[-1].phase == "initial"
            and counts["domain_reduction"] > 0
            and counts["propagation"] > 0
            and counts["decision"] == 0
            and counts["backtrack"] == 0
            and maximum_depth == 0
        ):
            raise PipelineSnapshotError("trace is not an initial propagation contradiction")
    elif case.classification == CLASS_SEARCH and not (
        conflicts[-1].phase == "search"
        and counts["decision"] >= 4
        and counts["backtrack"] >= 4
        and maximum_depth >= 2
    ):
        raise PipelineSnapshotError("trace is not a non-superficial UNSAT search")


def validate_run_dossier(document: object) -> None:
    """Validate one closed run.json transport document."""
    root = _require_object(document, "$")
    _require_exact_fields(
        root,
        frozenset({"schema", "case", "source", "environment", "solver", "timings", "artifacts"}),
        "$",
    )
    _require_literal(root["schema"], RUN_SCHEMA, "$.schema")
    case = _require_object(root["case"], "$.case")
    _require_exact_fields(
        case,
        frozenset({"id", "title", "classification", "description"}),
        "$.case",
    )
    identifier = _nonempty_string(case["id"], "$.case.id")
    if _CASE_ID.fullmatch(identifier) is None:
        raise PipelineSnapshotError("$.case.id: is invalid")
    _nonempty_string(case["title"], "$.case.title")
    classification = _nonempty_string(case["classification"], "$.case.classification")
    if classification not in CLASSIFICATIONS:
        raise PipelineSnapshotError("$.case.classification: is invalid")
    _nonempty_string(case["description"], "$.case.description")

    source = _require_object(root["source"], "$.source")
    _require_exact_fields(source, frozenset({"path", "sha256"}), "$.source")
    source_path = _relative_path(source["path"], "$.source.path")
    if not source_path.endswith(".cm13"):
        raise PipelineSnapshotError("$.source.path: must name a .cm13 input")
    _require_sha256(source["sha256"], "$.source.sha256")

    environment = _require_object(root["environment"], "$.environment")
    _require_exact_fields(
        environment,
        frozenset({"captured_at_utc", "platform", "python", "git_commit"}),
        "$.environment",
    )
    captured = _nonempty_string(environment["captured_at_utc"], "$.environment.captured_at_utc")
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", captured) is None:
        raise PipelineSnapshotError("$.environment.captured_at_utc: must be UTC seconds")
    _nonempty_string(environment["platform"], "$.environment.platform")
    _nonempty_string(environment["python"], "$.environment.python")
    commit = _nonempty_string(environment["git_commit"], "$.environment.git_commit")
    if _GIT_COMMIT.fullmatch(commit) is None:
        raise PipelineSnapshotError("$.environment.git_commit: must be a full SHA-1")

    solver = _require_object(root["solver"], "$.solver")
    _require_exact_fields(
        solver,
        frozenset(
            {
                "engine",
                "semantics",
                "status",
                "expected_status",
                "initial_domain_overrides",
                "trace",
                "replay",
            }
        ),
        "$.solver",
    )
    engine = _nonempty_string(solver["engine"], "$.solver.engine")
    if engine not in SOLVERS:
        raise PipelineSnapshotError("$.solver.engine: is invalid")
    _require_literal(solver["semantics"], "observed", "$.solver.semantics")
    status = _nonempty_string(solver["status"], "$.solver.status")
    expected_status = _nonempty_string(solver["expected_status"], "$.solver.expected_status")
    if status not in STATUSES or status != expected_status:
        raise PipelineSnapshotError("$.solver.status: must match the expected status")
    if (classification == CLASS_SAT) != (status == "sat"):
        raise PipelineSnapshotError("$.solver.status: disagrees with case classification")
    overrides = _require_array(
        solver["initial_domain_overrides"], "$.solver.initial_domain_overrides"
    )
    parsed_overrides: list[InitialDomainOverride] = []
    previous_cell = -1
    for index, raw in enumerate(overrides):
        item_path = f"$.solver.initial_domain_overrides[{index}]"
        item = _require_object(raw, item_path)
        _require_exact_fields(item, frozenset({"cell", "domain"}), item_path)
        cell = _require_integer(item["cell"], f"{item_path}.cell", nonnegative=True)
        domain = _require_integer(item["domain"], f"{item_path}.domain", nonnegative=True)
        if cell <= previous_cell or domain > DOMAIN_ALL:
            raise PipelineSnapshotError(f"{item_path}: overrides must be sorted and canonical")
        parsed_overrides.append(InitialDomainOverride(cell=cell, domain=domain))
        previous_cell = cell
    _validate_case_override_shape(
        classification,
        tuple(parsed_overrides),
        "$.solver.initial_domain_overrides",
    )

    trace = _require_object(solver["trace"], "$.solver.trace")
    _require_exact_fields(
        trace,
        frozenset(
            {
                "event_capacity",
                "observed_event_count",
                "truncated",
                "checkpoint_interval",
                "checkpoint_capacity",
                "checkpoint_count",
                "event_counts",
                "max_depth",
            }
        ),
        "$.solver.trace",
    )
    event_capacity = _require_integer(
        trace["event_capacity"], "$.solver.trace.event_capacity", nonnegative=True
    )
    observed = _require_integer(
        trace["observed_event_count"],
        "$.solver.trace.observed_event_count",
        nonnegative=True,
    )
    truncated = _boolean(trace["truncated"], "$.solver.trace.truncated")
    if truncated:
        raise PipelineSnapshotError("$.solver.trace.truncated: dossier v1 requires a complete trace")
    if event_capacity < 2 or observed < 2 or observed > event_capacity:
        raise PipelineSnapshotError("$.solver.trace: event capacity is inconsistent")
    checkpoint_interval = _require_integer(
        trace["checkpoint_interval"],
        "$.solver.trace.checkpoint_interval",
        nonnegative=True,
    )
    checkpoint_capacity = _require_integer(
        trace["checkpoint_capacity"],
        "$.solver.trace.checkpoint_capacity",
        nonnegative=True,
    )
    checkpoint_count = _require_integer(
        trace["checkpoint_count"],
        "$.solver.trace.checkpoint_count",
        nonnegative=True,
    )
    if (checkpoint_interval == 0) != (checkpoint_capacity == 0) or checkpoint_count > checkpoint_capacity:
        raise PipelineSnapshotError("$.solver.trace: checkpoint metadata is inconsistent")
    event_counts = _require_object(trace["event_counts"], "$.solver.trace.event_counts")
    _require_exact_fields(
        event_counts,
        frozenset({"root", "propagation", "decision", "domain_reduction", "conflict", "backtrack", "result"}),
        "$.solver.trace.event_counts",
    )
    parsed_counts = {
        name: _require_integer(value, f"$.solver.trace.event_counts.{name}", nonnegative=True)
        for name, value in event_counts.items()
    }
    if parsed_counts["root"] != 1 or parsed_counts["result"] != 1:
        raise PipelineSnapshotError("$.solver.trace.event_counts: requires one root and result")
    if not truncated and sum(parsed_counts.values()) != observed:
        raise PipelineSnapshotError("$.solver.trace.event_counts: does not total observed events")
    maximum_depth = _require_integer(trace["max_depth"], "$.solver.trace.max_depth", nonnegative=True)

    replay = _require_object(solver["replay"], "$.solver.replay")
    _require_exact_fields(
        replay,
        frozenset({"trace_scope", "frame_scope", "unsat_certificate"}),
        "$.solver.replay",
    )
    _require_literal(replay["trace_scope"], "complete", "$.solver.replay.trace_scope")
    _require_literal(replay["frame_scope"], "selected", "$.solver.replay.frame_scope")
    if _boolean(replay["unsat_certificate"], "$.solver.replay.unsat_certificate"):
        raise PipelineSnapshotError("$.solver.replay.unsat_certificate: must remain false")
    if classification == CLASS_ROOT_CONFLICT and not (
        maximum_depth == 0
        and observed == 3
        and parsed_counts["conflict"] == 1
        and parsed_counts["propagation"] == 0
        and parsed_counts["domain_reduction"] == 0
        and parsed_counts["decision"] == 0
        and parsed_counts["backtrack"] == 0
    ):
        raise PipelineSnapshotError("$.solver.trace: does not describe a root conflict")
    if classification == CLASS_PROPAGATION and not (
        maximum_depth == 0
        and parsed_counts["conflict"] >= 1
        and parsed_counts["domain_reduction"] > 0
        and parsed_counts["propagation"] > 0
        and parsed_counts["decision"] == 0
        and parsed_counts["backtrack"] == 0
    ):
        raise PipelineSnapshotError("$.solver.trace: does not describe propagation UNSAT")
    if classification == CLASS_SEARCH and not (
        maximum_depth >= 2
        and parsed_counts["conflict"] >= 1
        and parsed_counts["decision"] >= 4
        and parsed_counts["backtrack"] >= 4
    ):
        raise PipelineSnapshotError("$.solver.trace: does not describe non-superficial search")

    timings = _require_object(root["timings"], "$.timings")
    _require_exact_fields(
        timings,
        frozenset({"clock", "identity", "stages"}),
        "$.timings",
    )
    _require_literal(timings["clock"], "monotonic-perf-counter-ns", "$.timings.clock")
    _require_literal(
        timings["identity"],
        "environment-specific-observation",
        "$.timings.identity",
    )
    stages = _require_array(timings["stages"], "$.timings.stages")
    names: list[str] = []
    for index, raw in enumerate(stages):
        item_path = f"$.timings.stages[{index}]"
        stage = _require_object(raw, item_path)
        _require_exact_fields(stage, frozenset({"name", "performed", "elapsed_ns"}), item_path)
        name = _nonempty_string(stage["name"], f"{item_path}.name")
        performed = _boolean(stage["performed"], f"{item_path}.performed")
        elapsed = _nullable_integer(stage["elapsed_ns"], f"{item_path}.elapsed_ns")
        if performed != (elapsed is not None):
            raise PipelineSnapshotError(f"{item_path}: performed must match elapsed_ns")
        names.append(name)
    if tuple(names) != STAGES:
        raise PipelineSnapshotError("$.timings.stages: order does not match the run contract")
    if stages[2]["performed"] is not False:
        raise PipelineSnapshotError("$.timings.stages[2]: native encoding must be not applicable")
    expected_verify = status == "sat"
    if stages[4]["performed"] is not expected_verify:
        expectation = "performed for SAT" if expected_verify else "not applicable for UNSAT"
        raise PipelineSnapshotError(f"$.timings.stages[4]: verify must be {expectation}")

    artifacts = _require_object(root["artifacts"], "$.artifacts")
    required = {"trace_manifest", "formula_view", "region_square", "region_hex", "reduction_view", "trace_contact_sheet", "trace_fallback", "trace_animation"}
    if not required.issubset(artifacts):
        missing = ", ".join(sorted(required - artifacts.keys()))
        raise PipelineSnapshotError(f"$.artifacts: missing required artifacts: {missing}")
    if status == "sat" and not {"solution_square", "solution_hex"}.issubset(artifacts):
        raise PipelineSnapshotError("$.artifacts: SAT dossier requires square and hex solutions")
    if status == "unsat" and ({"solution_square", "solution_hex"} & artifacts.keys()):
        raise PipelineSnapshotError("$.artifacts: UNSAT dossier forbids solution images")
    referenced_paths: set[str] = set()
    for name, raw in artifacts.items():
        if _CASE_ID.fullmatch(name.replace("_", "-")) is None:
            raise PipelineSnapshotError(f"$.artifacts.{name}: invalid artifact key")
        item_path = f"$.artifacts.{name}"
        item = _require_object(raw, item_path)
        _require_exact_fields(item, frozenset({"path", "sha256", "media_type", "role"}), item_path)
        artifact_path = _relative_path(item["path"], f"{item_path}.path", prefix="assets")
        if artifact_path in referenced_paths:
            raise PipelineSnapshotError(f"{item_path}.path: duplicates another artifact")
        referenced_paths.add(artifact_path)
        _require_sha256(item["sha256"], f"{item_path}.sha256")
        media_type = _nonempty_string(item["media_type"], f"{item_path}.media_type")
        if media_type not in _MEDIA_TYPES:
            raise PipelineSnapshotError(f"{item_path}.media_type: is unsupported")
        _nonempty_string(item["role"], f"{item_path}.role")


def load_run_dossier(path: str | Path) -> dict[str, object]:
    """Load run.json and verify every referenced asset without producer imports."""
    run_path = Path(path)
    try:
        document = _load_json_bytes(run_path.read_bytes(), str(run_path))
    except OSError as error:
        raise PipelineSnapshotError(f"cannot read run dossier {run_path!s}: {error}") from error
    validate_run_dossier(document)
    artifacts = _require_object(document["artifacts"], "$.artifacts")
    try:
        dossier_root = run_path.parent.resolve(strict=True)
    except OSError as error:
        raise PipelineSnapshotError(f"cannot resolve dossier root: {error}") from error
    for name, raw in artifacts.items():
        item = _require_object(raw, f"$.artifacts.{name}")
        relative = _relative_path(
            item["path"], f"$.artifacts.{name}.path", prefix="assets"
        )
        artifact_path = run_path.parent / relative
        try:
            resolved = artifact_path.resolve(strict=True)
            if not resolved.is_relative_to(dossier_root) or not resolved.is_file():
                raise PipelineSnapshotError(
                    f"$.artifacts.{name}.path: escapes the self-contained dossier"
                )
            encoded = resolved.read_bytes()
        except OSError as error:
            raise PipelineSnapshotError(
                f"$.artifacts.{name}.path: cannot read {relative}: {error}"
            ) from error
        if hashlib.sha256(encoded).hexdigest() != item["sha256"]:
            raise PipelineSnapshotError(
                f"$.artifacts.{name}.sha256: does not match {relative}"
            )
    return document


def build_run_dossier(
    case: RunCase,
    trace: SolverTrace,
    *,
    source_sha256: str,
    captured_at_utc: str,
    platform: str,
    python_version: str,
    git_commit: str,
    timings_ns: dict[str, int | None],
    artifacts: dict[str, dict[str, str]],
) -> dict[str, object]:
    """Build and validate the raw authoritative run.json document."""
    validate_case_outcome(case, trace)
    event_counts = {
        kind: sum(event.kind == kind for event in trace.events)
        for kind in ("root", "propagation", "decision", "domain_reduction", "conflict", "backtrack", "result")
    }
    document: dict[str, object] = {
        "schema": RUN_SCHEMA,
        "case": {
            "id": case.identifier,
            "title": case.title,
            "classification": case.classification,
            "description": case.description,
        },
        "source": {"path": case.source, "sha256": source_sha256},
        "environment": {
            "captured_at_utc": captured_at_utc,
            "platform": platform,
            "python": python_version,
            "git_commit": git_commit,
        },
        "solver": {
            "engine": trace.solver,
            "semantics": "observed",
            "status": trace.status.value,
            "expected_status": case.expected_status,
            "initial_domain_overrides": [
                {"cell": item.cell, "domain": item.domain}
                for item in case.initial_domain_overrides
            ],
            "trace": {
                "event_capacity": trace.event_capacity,
                "observed_event_count": trace.observed_event_count,
                "truncated": trace.truncated,
                "checkpoint_interval": trace.checkpoint_interval,
                "checkpoint_capacity": trace.checkpoint_capacity,
                "checkpoint_count": len(trace.checkpoints),
                "event_counts": event_counts,
                "max_depth": max(event.depth for event in trace.events),
            },
            "replay": {
                "trace_scope": "truncated-prefix" if trace.truncated else "complete",
                "frame_scope": "selected",
                "unsat_certificate": False,
            },
        },
        "timings": {
            "clock": "monotonic-perf-counter-ns",
            "identity": "environment-specific-observation",
            "stages": [
                {
                    "name": name,
                    "performed": timings_ns[name] is not None,
                    "elapsed_ns": timings_ns[name],
                }
                for name in STAGES
            ],
        },
        "artifacts": artifacts,
    }
    validate_run_dossier(document)
    return document
