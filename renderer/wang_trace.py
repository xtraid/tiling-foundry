"""Strict offline validation and replay for solver trace v1.

The consumer is presentation-only: it loads hash-bound JSON, independently
replays the recorded semantic deltas.  Raster composition and animation live
in separate downstream modules.  This imports neither native code nor solvers.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
from typing import Final

from wang_hex_port import WangPresentation, WangSquareRenderError
from wang_snapshot import (
    FORMULA_SCHEMA,
    REDUCTION_SCHEMA,
    REGION_SCHEMA,
    TILESET_SCHEMA,
    ExplainabilityBundle,
    _array,
    _basename,
    _fields,
    _integer,
    _load_json_bytes,
    _object,
    _parse_formula,
    _parse_reduction,
    _parse_region,
    _parse_tileset,
    _read_bytes,
    _sha256,
    _string,
)
from wang_square import SCHEMA_NAME as SOLUTION_SCHEMA
from wang_square import _project_wang_presentation


TRACE_SCHEMA: Final = "wang-solver-trace-v1"
MANIFEST_SCHEMA: Final = "wang-explain-manifest-v3"
_TRACE_STAGE: Final = "solver-trace"
_SEMANTICS: Final = "observed"
_DOMAIN_ALL: Final = (1 << 23) - 1
_KINDS: Final = frozenset(
    {
        "root",
        "propagation",
        "decision",
        "domain_reduction",
        "conflict",
        "backtrack",
        "result",
    }
)
_PHASES: Final = frozenset({"initial", "search"})
_REASONS: Final = frozenset({"decision", "propagation"})
_SOLVERS: Final = frozenset({"reference", "optimized"})
_STATUSES: Final = frozenset({"sat", "unsat"})
_EVENT_FIELDS: Final = frozenset(
    {
        "sequence",
        "kind",
        "phase",
        "reason",
        "depth",
        "cell",
        "change_mark",
        "old_domain",
        "new_domain",
        "status",
    }
)


@dataclass(frozen=True, slots=True)
class TraceEvent:
    sequence: int
    kind: str
    phase: str | None
    reason: str | None
    depth: int
    cell: int | None
    change_mark: int
    old_domain: int | None
    new_domain: int | None
    status: str | None


@dataclass(frozen=True, slots=True)
class TraceCheckpoint:
    event_sequence: int
    change_mark: int
    domains: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class TraceSnapshot:
    solver: str
    status: str
    source_formula_sha256: str
    region_sha256: str
    solution_sha256: str | None
    width: int
    height: int
    event_capacity: int
    observed_event_count: int
    truncated: bool
    checkpoint_interval: int
    checkpoint_capacity: int
    checkpoints_truncated: bool
    initial_domains: tuple[int, ...]
    events: tuple[TraceEvent, ...]
    checkpoints: tuple[TraceCheckpoint, ...]


@dataclass(frozen=True, slots=True)
class TraceBundle:
    explanation: ExplainabilityBundle
    trace: TraceSnapshot
    solution: WangPresentation | None


def _check_reduction_formula_identity(
    bundle: ExplainabilityBundle,
) -> None:
    reduction = bundle.reduction
    assert reduction is not None
    variable_count = bundle.formula.variable_count
    expected_source: list[tuple[str, int, int | None, int | None]] = []
    for variable in range(variable_count):
        expected_source.extend(
            ("variable", 3 * variable + occurrence, variable, occurrence)
            for occurrence in range(3)
        )
        if variable + 1 < variable_count:
            expected_source.append(
                ("redundant", 3 * variable_count + variable, None, None)
            )
    expected_target: list[tuple[str, int, int | None, int | None]] = []
    next_occurrence = [0] * variable_count
    for clause_id, clause in enumerate(bundle.formula.clauses):
        for variable in clause:
            occurrence = next_occurrence[variable]
            next_occurrence[variable] += 1
            expected_target.append(
                ("variable", 3 * variable + occurrence, variable, occurrence)
            )
        if clause_id + 1 < variable_count:
            expected_target.append(
                ("redundant", 3 * variable_count + clause_id, None, None)
            )
    if tuple(expected_source) != tuple(
        signal.identity for signal in reduction.source_signals
    ):
        _fail("reduction $.signals.source", "does not match formula")
    if tuple(expected_target) != tuple(
        signal.identity for signal in reduction.target_signals
    ):
        _fail("reduction $.signals.target", "does not match formula")


def _fail(path: str, message: str) -> None:
    raise WangSquareRenderError(f"solver trace {path}: {message}")


def _optional_string(value: object, path: str) -> str | None:
    if value is None:
        return None
    return _string(value, path)


def _optional_integer(value: object, path: str) -> int | None:
    if value is None:
        return None
    return _integer(value, path, nonnegative=True)


def _boolean(value: object, path: str) -> bool:
    if type(value) is not bool:
        _fail(path, "must be a boolean")
    return value


def _domain(value: object, path: str) -> int:
    domain = _integer(value, path, nonnegative=True)
    if domain > _DOMAIN_ALL:
        _fail(path, "exceeds the 23-tile Wang domain")
    return domain


def _reference(
    value: object,
    path: str,
    expected_schema: str,
) -> tuple[str, str]:
    reference = _object(value, path)
    _fields(reference, frozenset({"path", "sha256", "schema"}), path)
    name = _basename(reference["path"], f"{path}.path")
    digest = _sha256(reference["sha256"], f"{path}.sha256")
    if _string(reference["schema"], f"{path}.schema") != expected_schema:
        _fail(f"{path}.schema", f"must equal {expected_schema!r}")
    return name, digest


def _parse_event(value: object, path: str) -> TraceEvent:
    event = _object(value, path)
    _fields(event, _EVENT_FIELDS, path)
    kind = _string(event["kind"], f"{path}.kind")
    if kind not in _KINDS:
        _fail(f"{path}.kind", "is not a supported event kind")
    phase = _optional_string(event["phase"], f"{path}.phase")
    if phase is not None and phase not in _PHASES:
        _fail(f"{path}.phase", "is not a supported phase")
    reason = _optional_string(event["reason"], f"{path}.reason")
    if reason is not None and reason not in _REASONS:
        _fail(f"{path}.reason", "is not a supported reason")
    status = _optional_string(event["status"], f"{path}.status")
    if status is not None and status not in _STATUSES:
        _fail(f"{path}.status", "is not a terminal status")
    return TraceEvent(
        sequence=_integer(event["sequence"], f"{path}.sequence", nonnegative=True),
        kind=kind,
        phase=phase,
        reason=reason,
        depth=_integer(event["depth"], f"{path}.depth", nonnegative=True),
        cell=_optional_integer(event["cell"], f"{path}.cell"),
        change_mark=_integer(
            event["change_mark"], f"{path}.change_mark", nonnegative=True
        ),
        old_domain=(
            None
            if event["old_domain"] is None
            else _domain(event["old_domain"], f"{path}.old_domain")
        ),
        new_domain=(
            None
            if event["new_domain"] is None
            else _domain(event["new_domain"], f"{path}.new_domain")
        ),
        status=status,
    )


def _parse_trace(document: dict[str, object]) -> TraceSnapshot:
    _fields(
        document,
        frozenset(
            {
                "schema",
                "semantics",
                "solver",
                "status",
                "geometry",
                "source_formula_sha256",
                "region_sha256",
                "solution_sha256",
                "layout",
                "capacity",
                "initial_domains",
                "events",
                "checkpoints",
            }
        ),
        "trace $",
    )
    for field, expected in (
        ("schema", TRACE_SCHEMA),
        ("semantics", _SEMANTICS),
        ("geometry", "square"),
    ):
        if _string(document[field], f"trace $.{field}") != expected:
            _fail(f"trace $.{field}", f"must equal {expected!r}")
    solver = _string(document["solver"], "trace $.solver")
    status = _string(document["status"], "trace $.status")
    if solver not in _SOLVERS or status not in _STATUSES:
        _fail("trace $", "has an unsupported solver or status")
    source_digest = _sha256(
        document["source_formula_sha256"], "trace $.source_formula_sha256"
    )
    region_digest = _sha256(document["region_sha256"], "trace $.region_sha256")
    solution_digest = document["solution_sha256"]
    if solution_digest is not None:
        solution_digest = _sha256(solution_digest, "trace $.solution_sha256")
    if (status == "sat") != (solution_digest is not None):
        _fail("trace $.solution_sha256", "must be present exactly for SAT")

    layout = _object(document["layout"], "trace $.layout")
    _fields(
        layout,
        frozenset({"width", "height", "tile_count", "indexing"}),
        "trace $.layout",
    )
    width = _integer(layout["width"], "trace $.layout.width", nonnegative=True)
    height = _integer(
        layout["height"], "trace $.layout.height", nonnegative=True
    )
    if width == 0 or height == 0:
        _fail("trace $.layout", "dimensions must be positive")
    if layout["tile_count"] != 23 or type(layout["tile_count"]) is not int:
        _fail("trace $.layout.tile_count", "must equal 23")
    if layout["indexing"] != "row-major":
        _fail("trace $.layout.indexing", "must equal 'row-major'")

    capacity = _object(document["capacity"], "trace $.capacity")
    _fields(
        capacity,
        frozenset(
            {
                "event_capacity",
                "observed_event_count",
                "truncated",
                "checkpoint_interval",
                "checkpoint_capacity",
                "checkpoints_truncated",
            }
        ),
        "trace $.capacity",
    )
    initial = tuple(
        _domain(item, f"trace $.initial_domains[{index}]")
        for index, item in enumerate(
            _array(document["initial_domains"], "trace $.initial_domains")
        )
    )
    events = tuple(
        _parse_event(item, f"trace $.events[{index}]")
        for index, item in enumerate(_array(document["events"], "trace $.events"))
    )
    checkpoints: list[TraceCheckpoint] = []
    for index, raw in enumerate(
        _array(document["checkpoints"], "trace $.checkpoints")
    ):
        path = f"trace $.checkpoints[{index}]"
        checkpoint = _object(raw, path)
        _fields(
            checkpoint,
            frozenset({"event_sequence", "change_mark", "domains"}),
            path,
        )
        checkpoints.append(
            TraceCheckpoint(
                event_sequence=_integer(
                    checkpoint["event_sequence"],
                    f"{path}.event_sequence",
                    nonnegative=True,
                ),
                change_mark=_integer(
                    checkpoint["change_mark"],
                    f"{path}.change_mark",
                    nonnegative=True,
                ),
                domains=tuple(
                    _domain(item, f"{path}.domains[{domain_index}]")
                    for domain_index, item in enumerate(
                        _array(checkpoint["domains"], f"{path}.domains")
                    )
                ),
            )
        )
    trace = TraceSnapshot(
        solver=solver,
        status=status,
        source_formula_sha256=source_digest,
        region_sha256=region_digest,
        solution_sha256=solution_digest,
        width=width,
        height=height,
        event_capacity=_integer(
            capacity["event_capacity"],
            "trace $.capacity.event_capacity",
            nonnegative=True,
        ),
        observed_event_count=_integer(
            capacity["observed_event_count"],
            "trace $.capacity.observed_event_count",
            nonnegative=True,
        ),
        truncated=_boolean(capacity["truncated"], "trace $.capacity.truncated"),
        checkpoint_interval=_integer(
            capacity["checkpoint_interval"],
            "trace $.capacity.checkpoint_interval",
            nonnegative=True,
        ),
        checkpoint_capacity=_integer(
            capacity["checkpoint_capacity"],
            "trace $.capacity.checkpoint_capacity",
            nonnegative=True,
        ),
        checkpoints_truncated=_boolean(
            capacity["checkpoints_truncated"],
            "trace $.capacity.checkpoints_truncated",
        ),
        initial_domains=initial,
        events=events,
        checkpoints=tuple(checkpoints),
    )
    replay_trace(trace)
    return trace


def replay_trace(trace: TraceSnapshot) -> tuple[tuple[int, ...], ...]:
    area = trace.width * trace.height
    if len(trace.initial_domains) != area:
        _fail("trace $.initial_domains", "length must equal layout area")
    if trace.event_capacity < 2 or not 2 <= len(trace.events) <= trace.event_capacity:
        _fail("trace $.events", "must fit an event capacity of at least two")
    terminal = trace.events[-1]
    if trace.events[0].kind != "root" or terminal.kind != "result":
        _fail("trace $.events", "must start at root and end at result")
    if terminal.status != trace.status:
        _fail("trace $.events", "terminal status does not match trace")
    if terminal.sequence + 1 != trace.observed_event_count:
        _fail("trace $.capacity.observed_event_count", "does not follow result")
    if trace.truncated and terminal.sequence <= len(trace.events) - 1:
        _fail("trace $.events", "truncated trace must contain a sequence gap")
    if not trace.truncated and trace.observed_event_count != len(trace.events):
        _fail("trace $.events", "complete trace cannot contain a sequence gap")
    for index, event in enumerate(trace.events[:-1]):
        if event.sequence != index:
            _fail(f"trace $.events[{index}].sequence", "breaks prefix order")

    domains = list(trace.initial_domains)
    changes: list[tuple[int, int]] = []
    states: list[tuple[int, ...]] = []
    checkpoints = {item.event_sequence: item for item in trace.checkpoints}
    if len(checkpoints) != len(trace.checkpoints):
        _fail("trace $.checkpoints", "event sequences must be unique")
    expected_checkpoint_sequences = tuple(
        trace.checkpoint_interval * (index + 1) - 1
        for index in range(len(trace.checkpoints))
    )
    if tuple(checkpoints) != expected_checkpoint_sequences:
        _fail("trace $.checkpoints", "does not follow checkpoint_interval")
    if (trace.checkpoint_interval == 0) != (trace.checkpoint_capacity == 0):
        _fail("trace $.capacity", "checkpoint settings must be jointly enabled")
    if len(trace.checkpoints) > trace.checkpoint_capacity:
        _fail("trace $.checkpoints", "exceeds checkpoint_capacity")
    checkpoint_opportunities = (
        0
        if trace.checkpoint_interval == 0
        else (len(trace.events) - int(trace.truncated))
        // trace.checkpoint_interval
    )
    if len(trace.checkpoints) != min(
        checkpoint_opportunities,
        trace.checkpoint_capacity,
    ):
        _fail("trace $.checkpoints", "count does not match recorded events")
    if trace.checkpoints_truncated != (
        checkpoint_opportunities > trace.checkpoint_capacity
    ):
        _fail("trace $.capacity.checkpoints_truncated", "is inconsistent")

    for index, event in enumerate(trace.events):
        if event.kind != "result" and event.status is not None:
            _fail(f"trace $.events[{index}].status", "is reserved for result")
        if event.kind != "domain_reduction" and event.reason is not None:
            _fail(f"trace $.events[{index}].reason", "is reserved for reduction")
        if event.kind not in ("decision", "domain_reduction") and (
            event.old_domain is not None or event.new_domain is not None
        ):
            _fail(f"trace $.events[{index}]", "must not publish domains")
        if event.kind == "root":
            if index != 0 or event.phase != "initial" or event.cell is not None:
                _fail(f"trace $.events[{index}]", "root fields are inconsistent")
            if event.change_mark != 0 or event.depth != 0:
                _fail(f"trace $.events[{index}]", "root counters must equal zero")
        elif event.kind == "domain_reduction":
            if event.phase not in _PHASES or event.reason not in _REASONS:
                _fail(f"trace $.events[{index}]", "reduction needs phase and reason")
            if event.cell is None or event.cell >= area:
                _fail(f"trace $.events[{index}].cell", "lies outside layout")
            if event.old_domain is None or event.new_domain is None:
                _fail(f"trace $.events[{index}]", "reduction needs both domains")
            if domains[event.cell] != event.old_domain:
                _fail(f"trace $.events[{index}].old_domain", "does not match replay")
            if event.new_domain == event.old_domain or event.new_domain & ~event.old_domain:
                _fail(f"trace $.events[{index}].new_domain", "must narrow old_domain")
            changes.append((event.cell, event.old_domain))
            domains[event.cell] = event.new_domain
            if event.change_mark != len(changes):
                _fail(f"trace $.events[{index}].change_mark", "is inconsistent")
        elif event.kind == "backtrack":
            if event.phase != "search" or event.change_mark > len(changes):
                _fail(f"trace $.events[{index}]", "backtrack mark is inconsistent")
            while len(changes) > event.change_mark:
                cell, previous = changes.pop()
                domains[cell] = previous
        elif not (
            event.kind == "result" and trace.truncated and event.sequence != index
        ) and event.change_mark != len(changes):
            _fail(f"trace $.events[{index}].change_mark", "is inconsistent")

        if event.kind == "decision":
            if event.phase != "search" or event.cell is None or event.cell >= area:
                _fail(f"trace $.events[{index}]", "decision cell is inconsistent")
            if event.old_domain != domains[event.cell]:
                _fail(f"trace $.events[{index}].old_domain", "does not match replay")
            if event.new_domain is None or event.new_domain == 0 or (
                event.new_domain & (event.new_domain - 1)
            ):
                _fail(f"trace $.events[{index}].new_domain", "is not a singleton")
            if event.old_domain is None or event.new_domain & ~event.old_domain:
                _fail(f"trace $.events[{index}]", "decision lies outside old domain")
        elif event.kind == "propagation":
            if event.phase not in _PHASES:
                _fail(f"trace $.events[{index}].phase", "is required")
            if (event.phase == "initial") != (event.cell is None):
                _fail(f"trace $.events[{index}].cell", "does not match phase")
            if event.phase == "initial" and event.depth != 0:
                _fail(f"trace $.events[{index}].depth", "must equal zero")
        elif event.kind == "conflict":
            if event.phase not in _PHASES or event.cell is None or event.cell >= area:
                _fail(f"trace $.events[{index}]", "conflict fields are inconsistent")
            if domains[event.cell] != 0:
                _fail(f"trace $.events[{index}].cell", "must hold the empty domain")
        elif event.kind == "result":
            if index != len(trace.events) - 1 or event.phase is not None:
                _fail(f"trace $.events[{index}]", "result must be terminal")
            if (trace.status == "sat") != (event.cell is None):
                _fail(f"trace $.events[{index}].cell", "does not match status")

        state = tuple(domains)
        checkpoint = checkpoints.get(event.sequence)
        if checkpoint is not None and (
            checkpoint.change_mark != len(changes) or checkpoint.domains != state
        ):
            _fail("trace $.checkpoints", "does not match replay state")
        states.append(state)
    if any(sequence not in {event.sequence for event in trace.events} for sequence in checkpoints):
        _fail("trace $.checkpoints", "must reference recorded events")
    return tuple(states)


def _check_trace_region_state(
    trace: TraceSnapshot,
    active: tuple[bool, ...],
) -> None:
    if len(active) != len(trace.initial_domains):
        _fail("trace $.initial_domains", "does not match region active mask")
    for index, is_active in enumerate(active):
        if not is_active and trace.initial_domains[index] != 0:
            _fail(
                f"trace $.initial_domains[{index}]",
                "inactive cell must be zero",
            )
    for checkpoint_index, checkpoint in enumerate(trace.checkpoints):
        for cell, is_active in enumerate(active):
            if not is_active and checkpoint.domains[cell] != 0:
                _fail(
                    f"trace $.checkpoints[{checkpoint_index}].domains[{cell}]",
                    "inactive cell must be zero",
                )
    for event_index, event in enumerate(trace.events):
        if event.cell is not None:
            if event.cell >= len(active):
                _fail(
                    f"trace $.events[{event_index}].cell",
                    "lies outside region",
                )
            if not active[event.cell]:
                _fail(
                    f"trace $.events[{event_index}].cell",
                    "must identify an active cell",
                )


def load_trace_bundle(path: str | Path) -> TraceBundle:
    """Load a v3 bundle, verify identities, and replay the trace offline."""
    manifest_path = Path(path)
    manifest = _load_json_bytes(
        _read_bytes(manifest_path, "solver trace manifest"),
        str(manifest_path),
    )
    _fields(
        manifest,
        frozenset({"schema", "stage", "source_formula_sha256", "artifacts"}),
        "$",
    )
    if manifest["schema"] != MANIFEST_SCHEMA or manifest["stage"] != _TRACE_STAGE:
        _fail("$", "must be a solver-trace v3 manifest")
    source_digest = _sha256(
        manifest["source_formula_sha256"], "$.source_formula_sha256"
    )
    artifacts = _object(manifest["artifacts"], "$.artifacts")
    expected = {
        "formula": FORMULA_SCHEMA,
        "tileset": TILESET_SCHEMA,
        "region": REGION_SCHEMA,
        "reduction": REDUCTION_SCHEMA,
        "trace": TRACE_SCHEMA,
        "solution": SOLUTION_SCHEMA,
    }
    _fields(artifacts, frozenset(expected), "$.artifacts")
    documents: dict[str, dict[str, object]] = {}
    digests: dict[str, str] = {}
    for name, schema in expected.items():
        if artifacts[name] is None:
            if name != "solution":
                _fail(f"$.artifacts.{name}", "must not be null")
            continue
        artifact_name, digest = _reference(
            artifacts[name], f"$.artifacts.{name}", schema
        )
        encoded = _read_bytes(manifest_path.parent / artifact_name, f"{name} artifact")
        if hashlib.sha256(encoded).hexdigest() != digest:
            _fail(f"$.artifacts.{name}.sha256", f"does not match {artifact_name}")
        document = _load_json_bytes(encoded, artifact_name)
        if document.get("schema") != schema:
            _fail(f"$.artifacts.{name}.schema", "does not match artifact")
        documents[name] = document
        digests[name] = digest

    formula = _parse_formula(documents["formula"])
    tileset = _parse_tileset(documents["tileset"])
    region = _parse_region(documents["region"])
    reduction = _parse_reduction(documents["reduction"])
    if formula.source_sha256 != source_digest or region.source_formula_sha256 != source_digest:
        _fail("$.source_formula_sha256", "does not match formula and region")
    if reduction.source_formula_sha256 != source_digest:
        _fail("reduction $.source_formula_sha256", "does not match formula")
    if reduction.region_sha256 != digests["region"]:
        _fail("reduction $.region_sha256", "does not match region")
    if reduction.variable_count != formula.variable_count or (
        reduction.width,
        reduction.height,
    ) != (region.width, region.height):
        _fail("reduction $", "does not match formula and region dimensions")

    explanation = ExplainabilityBundle(
        source_formula_sha256=source_digest,
        formula=formula,
        tileset=tileset,
        region=region,
        reduction=reduction,
    )
    _check_reduction_formula_identity(explanation)

    trace = _parse_trace(documents["trace"])
    if trace.source_formula_sha256 != source_digest or trace.region_sha256 != digests["region"]:
        _fail("trace $", "does not match formula and region")
    if (trace.width, trace.height) != (region.width, region.height):
        _fail("trace $.layout", "does not match region")
    _check_trace_region_state(trace, region.active)
    solution: WangPresentation | None = None
    if "solution" in documents:
        solution = _project_wang_presentation(documents["solution"])
        if trace.solution_sha256 != digests["solution"]:
            _fail("trace $.solution_sha256", "does not match solution")
        if (solution.width, solution.height) != (trace.width, trace.height):
            _fail("solution $.bounds", "does not match trace layout")
        if not trace.truncated:
            final_domains = replay_trace(trace)[-1]
            expected_domains = tuple(
                0 if tile_id is None else 1 << tile_id
                for tile_id in solution.cells
            )
            if final_domains != expected_domains:
                _fail("trace $", "does not replay to the bound SAT solution")
    elif trace.status != "unsat" or trace.solution_sha256 is not None:
        _fail("$.artifacts.solution", "must be present exactly for SAT")

    return TraceBundle(
        explanation=explanation,
        trace=trace,
        solution=solution,
    )
