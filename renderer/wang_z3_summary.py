"""Z3-free consumer and encoding-order animation for Z3 summary v1."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw

from wang_animation import AnimationOutputs, write_animation_assets
from wang_explain import (
    EXPLAIN_ACTIVE_RGB,
    EXPLAIN_MUTED_RGB,
    EXPLAIN_OUTLINE_RGB,
    EXPLAIN_PANEL_RGB,
    EXPLAIN_TEXT_RGB,
    draw_explain_heading,
    explain_font,
)
from wang_hex_port import WangSquareRenderError
from wang_snapshot import (
    _array,
    _fields,
    _integer,
    _load_json_bytes,
    _object,
    _read_bytes,
    _sha256,
    _string,
)


SCHEMA_NAME = "z3-encoding-summary-v1"
BOOLEAN_ENGINE = "boolean-z3"
WANG_ENGINE = "wang-z3"
_WANG_TILE_COUNT = 23
_BOOLEAN_ORDER = (
    "variables:ascending-id",
    "clauses:source-order",
    "clause-positions:left-to-right",
)
_WANG_ORDER = (
    "cells:row-major",
    "directions:N,E,S,W",
    "tile-tuples:first-positional-id",
    "cell-relation-before-boundary",
    "boundary-directions:N,E,S,W",
)


@dataclass(frozen=True, slots=True)
class Z3EncodingSummary:
    engine: str
    source_formula_sha256: str
    region_sha256: str | None
    version: str
    random_seed: int
    threads: int
    status: str
    order: tuple[str, ...]
    variable_count: int
    width: int
    height: int
    active_cell_count: int
    edge_term_count: int
    shared_internal_edge_count: int
    unique_tile_tuple_count: int
    assertion_count: int
    assignment: tuple[bool, ...] | None
    cells: tuple[int | None, ...] | None
    statistics: tuple[tuple[str, int], ...]


def _fail(path: str, message: str) -> None:
    raise WangSquareRenderError(f"Z3 encoding summary {path}: {message}")


def load_z3_encoding_summary(path: str | Path) -> Z3EncodingSummary:
    """Strictly load a closed summary without importing Z3."""
    source = Path(path)
    document = _load_json_bytes(_read_bytes(source, "Z3 summary"), str(source))
    _fields(
        document,
        frozenset(
            {
                "schema",
                "semantics",
                "engine",
                "source_formula_sha256",
                "region_sha256",
                "z3",
                "status",
                "encoding",
                "model",
                "statistics",
            }
        ),
        "$",
    )
    if document["schema"] != SCHEMA_NAME or document["semantics"] != "encoding-order":
        _fail("$", "must use the closed encoding-order v1 contract")
    engine = _string(document["engine"], "$.engine")
    if engine not in (BOOLEAN_ENGINE, WANG_ENGINE):
        _fail("$.engine", "is not supported")
    source_digest = _sha256(
        document["source_formula_sha256"], "$.source_formula_sha256"
    )
    region_digest = document["region_sha256"]
    if region_digest is not None:
        region_digest = _sha256(region_digest, "$.region_sha256")
    if (engine == WANG_ENGINE) != (region_digest is not None):
        _fail("$.region_sha256", "must be present exactly for Wang Z3")

    z3 = _object(document["z3"], "$.z3")
    _fields(z3, frozenset({"version", "parameters"}), "$.z3")
    version = _string(z3["version"], "$.z3.version")
    if not version:
        _fail("$.z3.version", "must not be empty")
    parameters = _object(z3["parameters"], "$.z3.parameters")
    _fields(parameters, frozenset({"random_seed", "threads"}), "$.z3.parameters")
    random_seed = _integer(
        parameters["random_seed"], "$.z3.parameters.random_seed", nonnegative=True
    )
    threads = _integer(
        parameters["threads"], "$.z3.parameters.threads", nonnegative=True
    )
    if (random_seed, threads) != (0, 1):
        _fail("$.z3.parameters", "must equal random_seed=0 and threads=1")
    status = _string(document["status"], "$.status")
    if status not in ("sat", "unsat", "unknown"):
        _fail("$.status", "is not supported")

    encoding = _object(document["encoding"], "$.encoding")
    count_names = (
        "variable_count",
        "width",
        "height",
        "active_cell_count",
        "edge_term_count",
        "shared_internal_edge_count",
        "unique_tile_tuple_count",
        "assertion_count",
    )
    _fields(encoding, frozenset({"order", *count_names}), "$.encoding")
    order = tuple(
        _string(item, f"$.encoding.order[{index}]")
        for index, item in enumerate(_array(encoding["order"], "$.encoding.order"))
    )
    expected_order = _BOOLEAN_ORDER if engine == BOOLEAN_ENGINE else _WANG_ORDER
    if order != expected_order:
        _fail("$.encoding.order", "does not match the engine contract")
    counts = {
        name: _integer(encoding[name], f"$.encoding.{name}", nonnegative=True)
        for name in count_names
    }
    if counts["variable_count"] == 0 or counts["assertion_count"] == 0:
        _fail("$.encoding", "variable and assertion counts must be positive")
    if engine == BOOLEAN_ENGINE and any(
        counts[name] != 0 for name in count_names[1:-1]
    ):
        _fail("$.encoding", "Boolean summary must not contain Wang counts")
    if engine == WANG_ENGINE and (
        any(
            counts[name] == 0
            for name in (
                "width",
                "height",
                "active_cell_count",
                "edge_term_count",
            )
        )
        or counts["unique_tile_tuple_count"] != _WANG_TILE_COUNT
    ):
        _fail(
            "$.encoding",
            "Wang summary requires region counts and the canonical tile table",
        )
    if engine == WANG_ENGINE and (
        counts["active_cell_count"] > counts["width"] * counts["height"]
        or counts["edge_term_count"]
        != 4 * counts["active_cell_count"]
        - counts["shared_internal_edge_count"]
    ):
        _fail("$.encoding", "Wang edge accounting is inconsistent")

    model = _object(document["model"], "$.model")
    _fields(model, frozenset({"assignment", "cells"}), "$.model")
    assignment: tuple[bool, ...] | None = None
    cells: tuple[int | None, ...] | None = None
    if model["assignment"] is not None:
        raw_assignment = _array(model["assignment"], "$.model.assignment")
        if any(type(value) is not bool for value in raw_assignment):
            _fail("$.model.assignment", "must contain only booleans")
        assignment = tuple(raw_assignment)
    if model["cells"] is not None:
        cells = tuple(
            None
            if value is None
            else _integer(value, f"$.model.cells[{index}]", nonnegative=True)
            for index, value in enumerate(_array(model["cells"], "$.model.cells"))
        )
    if status == "sat" and engine == BOOLEAN_ENGINE:
        if assignment is None or len(assignment) != counts["variable_count"] or cells is not None:
            _fail("$.model", "does not match a SAT Boolean result")
    elif status == "sat":
        if assignment is not None or cells is None or len(cells) != counts["width"] * counts["height"]:
            _fail("$.model", "does not match a SAT Wang result")
        if any(
            tile_id is not None
            and tile_id >= counts["unique_tile_tuple_count"]
            for tile_id in cells
        ):
            _fail("$.model.cells", "contains an ID outside the canonical tile table")
        if sum(tile_id is not None for tile_id in cells) != counts["active_cell_count"]:
            _fail("$.model.cells", "non-null entries must equal active cells")
    elif assignment is not None or cells is not None:
        _fail("$.model", "must be empty for a non-SAT result")

    statistics: list[tuple[str, int]] = []
    for index, raw in enumerate(_array(document["statistics"], "$.statistics")):
        item = _object(raw, f"$.statistics[{index}]")
        _fields(item, frozenset({"name", "value"}), f"$.statistics[{index}]")
        statistics.append(
            (
                _string(item["name"], f"$.statistics[{index}].name"),
                _integer(
                    item["value"],
                    f"$.statistics[{index}].value",
                    nonnegative=True,
                ),
            )
        )
    model_entry_count = (
        len(assignment)
        if assignment is not None
        else len(cells)
        if cells is not None
        else 0
    )
    expected_statistics = (
        [
            ("variables", counts["variable_count"]),
            ("assertions", counts["assertion_count"]),
            ("model-entries", model_entry_count),
        ]
        if engine == BOOLEAN_ENGINE
        else [
            ("active-cells", counts["active_cell_count"]),
            ("edge-terms", counts["edge_term_count"]),
            ("shared-internal-edges", counts["shared_internal_edge_count"]),
            ("assertions", counts["assertion_count"]),
            ("model-entries", model_entry_count),
        ]
    )
    if statistics != expected_statistics:
        _fail("$.statistics", "must match the ordered project-owned counters")
    return Z3EncodingSummary(
        engine=engine,
        source_formula_sha256=source_digest,
        region_sha256=region_digest,
        version=version,
        random_seed=random_seed,
        threads=threads,
        status=status,
        order=order,
        assignment=assignment,
        cells=cells,
        statistics=tuple(statistics),
        **counts,
    )


def _compose_wang_frame(summary: Z3EncodingSummary, stage: int) -> Image.Image:
    width, height = 940, 430
    image = Image.new("RGB", (width, height), EXPLAIN_PANEL_RGB)
    draw = ImageDraw.Draw(image)
    labels = (
        "configuration",
        "edge terms",
        "shared internal edges",
        "cell relations and boundaries",
        "result, model, and encoding statistics",
    )
    draw_explain_heading(
        draw,
        (18, 16),
        title="Wang Z3 encoding order",
        subtitle=(
            f"encoding-order stage {stage + 1}/5 | {labels[stage]} | "
            "not a Z3 internal execution trace"
        ),
    )
    draw.text(
        (18, 78),
        f"Z3 {summary.version} | random_seed={summary.random_seed} | "
        f"threads={summary.threads}",
        font=explain_font(12),
        fill=EXPLAIN_TEXT_RGB,
    )
    steps = (
        "1. create edge terms in row-major cell order",
        "2. share north/south and east/west internal terms",
        "3. add one positional tile-tuple relation per active cell",
        "4. add exposed boundary equalities in N,E,S,W order",
        "5. check once; copy model and encoding statistics",
    )
    for index, label in enumerate(steps):
        y = 112 + index * 38
        active = index <= stage
        draw.rounded_rectangle(
            (18, y, 455, y + 28),
            radius=5,
            fill=(213, 235, 246) if active else (239, 241, 245),
            outline=(54, 127, 169) if index == stage else (184, 190, 201),
            width=2 if index == stage else 1,
        )
        draw.text(
            (29, y + 7),
            label,
            font=explain_font(10),
            fill=EXPLAIN_TEXT_RGB if active else EXPLAIN_MUTED_RGB,
        )

    panel = (485, 106, 922, 402)
    draw.rounded_rectangle(panel, radius=6, fill=EXPLAIN_ACTIVE_RGB, outline=(180, 187, 198))
    if stage == 0:
        lines = (
            f"formula variables: {summary.variable_count}",
            f"region: {summary.width} x {summary.height}",
            f"active cells: {summary.active_cell_count}",
            "project order is public; Z3 search order is not",
        )
    elif stage == 1:
        lines = (
            f"distinct edge terms: {summary.edge_term_count}",
            "N and W reuse already-created neighbor terms",
            "E and S create the forward row-major frontier",
        )
    elif stage == 2:
        lines = (
            f"shared internal edges: {summary.shared_internal_edge_count}",
            "one arithmetic term represents both sides of an adjacency",
            "no support implications or copied native propagation",
        )
    elif stage == 3:
        lines = (
            f"unique tile tuples: {summary.unique_tile_tuple_count}",
            f"assertions: {summary.assertion_count}",
            "cell relation precedes boundary equalities",
        )
    else:
        lines = (
            f"result: {summary.status.upper()}",
            f"model cells: {0 if summary.cells is None else len(summary.cells)}",
            f"encoding statistics: {len(summary.statistics)}",
            "internal Z3 counters and debug order are not claimed",
        )
    y = 124
    for line in lines:
        draw.text((502, y), line, font=explain_font(11), fill=EXPLAIN_TEXT_RGB)
        y += 27

    if stage == 4 and summary.cells is not None:
        cell = 8
        origin_x, origin_y = 502, 246
        for index, tile_id in enumerate(summary.cells):
            x = origin_x + (index % summary.width) * cell
            y = origin_y + (index // summary.width) * cell
            fill = (205, 210, 218) if tile_id is None else (88, 170, 122)
            draw.rectangle((x, y, x + cell - 1, y + cell - 1), fill=fill)
        draw.text(
            (502, 346),
            "model projection (inactive positions in gray)",
            font=explain_font(9),
            fill=EXPLAIN_MUTED_RGB,
        )
    draw.text(
        (18, 408),
        "Rendering explains the declared encoding order; it makes no claim about Z3's internal decisions.",
        font=explain_font(9),
        fill=EXPLAIN_MUTED_RGB,
    )
    return image


def _compose_boolean_frame(summary: Z3EncodingSummary, stage: int) -> Image.Image:
    width, height = 940, 430
    image = Image.new("RGB", (width, height), EXPLAIN_PANEL_RGB)
    draw = ImageDraw.Draw(image)
    labels = (
        "configuration",
        "Boolean variables",
        "source-order clauses",
        "result, assignment, and encoding statistics",
    )
    draw_explain_heading(
        draw,
        (18, 16),
        title="Boolean Z3 encoding order",
        subtitle=(
            f"encoding-order stage {stage + 1}/4 | {labels[stage]} | "
            "not a Z3 internal execution trace"
        ),
    )
    draw.text(
        (18, 78),
        f"Z3 {summary.version} | random_seed={summary.random_seed} | "
        f"threads={summary.threads}",
        font=explain_font(12),
        fill=EXPLAIN_TEXT_RGB,
    )
    steps = (
        "1. create one Boolean term per variable in ascending ID order",
        "2. visit clauses in source order",
        "3. visit each clause left-to-right and assert exactly one true",
        "4. check once; copy assignment and project-owned statistics",
    )
    for index, label in enumerate(steps):
        y = 112 + index * 48
        active = index <= stage
        draw.rounded_rectangle(
            (18, y, 520, y + 34),
            radius=5,
            fill=(213, 235, 246) if active else (239, 241, 245),
            outline=(54, 127, 169) if index == stage else (184, 190, 201),
            width=2 if index == stage else 1,
        )
        draw.text(
            (29, y + 9),
            label,
            font=explain_font(10),
            fill=EXPLAIN_TEXT_RGB if active else EXPLAIN_MUTED_RGB,
        )

    draw.rounded_rectangle(
        (548, 106, 922, 378),
        radius=6,
        fill=EXPLAIN_ACTIVE_RGB,
        outline=(180, 187, 198),
    )
    if stage == 0:
        lines = (
            f"formula variables: {summary.variable_count}",
            "fixed seed and one solver thread",
            "project order is public; Z3 search order is not",
        )
    elif stage == 1:
        lines = (
            f"Boolean terms: {summary.variable_count}",
            "term IDs follow the formula variable IDs",
            "no native-solver state is imported",
        )
    elif stage == 2:
        lines = (
            f"assertions: {summary.assertion_count}",
            "clause order follows the parsed source",
            "literal positions remain left-to-right",
        )
    else:
        assignment = summary.assignment or ()
        assignment_text = ", ".join(
            f"x{index + 1}={'1' if value else '0'}"
            for index, value in enumerate(assignment)
        )
        lines = (
            f"result: {summary.status.upper()}",
            f"assignment: {assignment_text or 'not applicable'}",
            f"encoding statistics: {len(summary.statistics)}",
            "independent assignment checking is downstream",
        )
    y = 128
    for line in lines:
        draw.text((566, y), line, font=explain_font(11), fill=EXPLAIN_TEXT_RGB)
        y += 31
    draw.text(
        (18, 408),
        "Rendering explains declared construction order; it does not expose Z3 decisions.",
        font=explain_font(9),
        fill=EXPLAIN_MUTED_RGB,
    )
    return image


def render_boolean_z3_assets(
    summary_path: str | Path,
    output_directory: str | Path,
    *,
    duration_ms: int = 800,
) -> AnimationOutputs:
    summary = load_z3_encoding_summary(summary_path)
    if summary.engine != BOOLEAN_ENGINE:
        raise WangSquareRenderError("encoding animation requires a Boolean Z3 summary")
    frames = tuple(_compose_boolean_frame(summary, stage) for stage in range(4))
    return write_animation_assets(
        frames,
        tuple(f"frame-{stage:02d}.png" for stage in range(4)),
        output_directory,
        fallback_index=2,
        duration_ms=duration_ms,
    )


def render_wang_z3_assets(
    summary_path: str | Path,
    output_directory: str | Path,
    *,
    duration_ms: int = 800,
) -> AnimationOutputs:
    summary = load_z3_encoding_summary(summary_path)
    if summary.engine != WANG_ENGINE:
        raise WangSquareRenderError("encoding animation requires a Wang Z3 summary")
    frames = tuple(_compose_wang_frame(summary, stage) for stage in range(5))
    return write_animation_assets(
        frames,
        tuple(f"frame-{stage:02d}.png" for stage in range(5)),
        output_directory,
        fallback_index=3,
        duration_ms=duration_ms,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="render a declared Boolean or Wang Z3 encoding order without Z3"
    )
    parser.add_argument("summary", type=Path)
    parser.add_argument("output_directory", type=Path)
    parser.add_argument("--duration-ms", type=int, default=800)
    return parser


def main(arguments: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(arguments)
    try:
        summary = load_z3_encoding_summary(args.summary)
        renderer = (
            render_boolean_z3_assets
            if summary.engine == BOOLEAN_ENGINE
            else render_wang_z3_assets
        )
        outputs = renderer(
            args.summary, args.output_directory, duration_ms=args.duration_ms
        )
    except (FileNotFoundError, WangSquareRenderError) as error:
        parser.error(str(error))
    print(f"animation={outputs.animation}")
    print(f"fallback={outputs.fallback}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
