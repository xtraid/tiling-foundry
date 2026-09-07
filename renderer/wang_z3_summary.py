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
    square_explain_tile,
)
from wang_hex_port import WangSquareRenderError
from wang_snapshot import (
    ExplainabilityBundle,
    _array,
    _fields,
    _integer,
    _load_json_bytes,
    _object,
    _read_bytes,
    _sha256,
    _string,
    load_explainability_bundle,
)
from wang_square import _build_palette_from_edges


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


def _boolean_clause_lines(
    bundle: ExplainabilityBundle,
) -> tuple[tuple[str, str], ...]:
    return tuple(
        (
            f"c{clause_id} source positions: "
            + ", ".join(f"x{variable}" for variable in clause),
            " + ".join(f"If(x{variable})" for variable in clause) + " = 1",
        )
        for clause_id, clause in enumerate(bundle.formula.clauses)
    )


def _bind_oracle_inputs(
    summary: Z3EncodingSummary, bundle: ExplainabilityBundle
) -> None:
    if summary.source_formula_sha256 != bundle.source_formula_sha256:
        raise WangSquareRenderError(
            "Z3 summary source formula identity disagrees with explainability bundle"
        )
    if summary.variable_count != bundle.formula.variable_count:
        raise WangSquareRenderError(
            "Z3 summary variable count disagrees with explainability bundle"
        )
    if summary.engine != WANG_ENGINE:
        return
    reduction = bundle.reduction
    if reduction is None or summary.region_sha256 != reduction.region_sha256:
        raise WangSquareRenderError(
            "Z3 summary region identity disagrees with explainability bundle"
        )
    if (summary.width, summary.height) != (bundle.region.width, bundle.region.height):
        raise WangSquareRenderError(
            "Z3 summary region dimensions disagree with explainability bundle"
        )
    if summary.active_cell_count != sum(bundle.region.active):
        raise WangSquareRenderError(
            "Z3 summary active-cell count disagrees with explainability bundle"
        )
    if summary.unique_tile_tuple_count != len(bundle.tileset.tile_edges):
        raise WangSquareRenderError(
            "Z3 summary canonical tile table disagrees with explainability bundle"
        )
    if summary.cells is not None and any(
        (tile_id is None) == active
        for tile_id, active in zip(summary.cells, bundle.region.active, strict=True)
    ):
        raise WangSquareRenderError(
            "Z3 model projection active cells disagree with explainability bundle"
        )


def _wang_example_lines(
    summary: Z3EncodingSummary, bundle: ExplainabilityBundle
) -> tuple[str, str, str, str]:
    if summary.cells is None:
        raise WangSquareRenderError("Wang SAT example requires a returned model")
    region = bundle.region
    selected: tuple[int, int] | None = None
    for index, active in enumerate(region.active):
        if not active:
            continue
        column = index % region.width
        sides = region.boundary[index]
        if (
            column + 1 < region.width
            and region.active[index + 1]
            and sides is not None
            and sides[0] is not None
        ):
            selected = (index, 0)
            break
    if selected is None:
        raise WangSquareRenderError(
            "Wang explanation needs an active cell with an east neighbor and exposed north edge"
        )
    index, boundary_direction = selected
    right_index = index + 1
    tile_id = summary.cells[index]
    right_id = summary.cells[right_index]
    if tile_id is None or right_id is None:
        raise WangSquareRenderError("Wang explanation selected an inactive model cell")
    tile = bundle.tileset.tile_edges[tile_id]
    right_tile = bundle.tileset.tile_edges[right_id]
    if tile[1] != right_tile[3]:
        raise WangSquareRenderError("Wang example internal term has unequal model colors")
    boundary = region.boundary[index]
    assert boundary is not None and boundary[boundary_direction] is not None
    required = boundary[boundary_direction]
    if tile[boundary_direction] != required:
        raise WangSquareRenderError("Wang example does not satisfy its exposed boundary")
    x = region.min_x + index % region.width
    y = region.min_y + index // region.width
    return (
        f"active cell ({x},{y}) -> returned tile #{tile_id}",
        f"canonical tile #{tile_id} = (N={tile[0]}, E={tile[1]}, S={tile[2]}, W={tile[3]})",
        f"shared term edge({x},{y},E) = edge({x + 1},{y},W) = {tile[1]}",
        f"exposed edge({x},{y},N) = required boundary N={required}",
    )


def _compose_wang_frame(
    summary: Z3EncodingSummary, bundle: ExplainabilityBundle, stage: int
) -> Image.Image:
    width, height = 1880, 1040
    image = Image.new("RGB", (width, height), EXPLAIN_PANEL_RGB)
    draw = ImageDraw.Draw(image)
    labels = ("terms", "shared", "tile tuple", "boundary", "model")
    draw_explain_heading(
        draw,
        (36, 20),
        title="Wang Z3 encoding order",
        subtitle=(
            f"encoding-order {stage + 1}/5 | row-major cells, then N/E/S/W | "
            "project construction, not Z3 search"
        ),
        scale=2,
    )
    for index, label in enumerate(labels):
        x = 36 + index * 362
        active = index <= stage
        draw.rounded_rectangle(
            (x, 118, x + 332, 184),
            radius=10,
            fill=(213, 235, 246) if active else (239, 241, 245),
            outline=(54, 127, 169) if index == stage else (184, 190, 201),
            width=4 if index == stage else 2,
        )
        draw.text(
            (x + 20, 136),
            f"{index + 1}  {label}",
            font=explain_font(28),
            fill=EXPLAIN_TEXT_RGB if active else EXPLAIN_MUTED_RGB,
        )
    facts = _wang_example_lines(summary, bundle) if summary.status == "sat" else (
        "No returned model for this result",
        f"canonical tile tuples: {summary.unique_tile_tuple_count}",
        f"shared internal terms: {summary.shared_internal_edge_count}",
        "boundary equalities remain project-owned assertions",
    )
    draw.rounded_rectangle((36, 216, 930, 968), radius=18, fill=EXPLAIN_ACTIVE_RGB, outline=(180, 187, 198), width=2)
    draw.text((72, 244), "One real cell relation", font=explain_font(48), fill=EXPLAIN_TEXT_RGB)
    if summary.status == "sat" and summary.cells is not None:
        region = bundle.region
        selected = next(i for i, active in enumerate(region.active) if active and i % region.width + 1 < region.width and region.active[i + 1] and region.boundary[i] is not None and region.boundary[i][0] is not None)
        tile_id = summary.cells[selected]
        right_id = summary.cells[selected + 1]
        assert tile_id is not None and right_id is not None
        palette = _build_palette_from_edges(bundle.tileset.tile_edges)
        left_edges = bundle.tileset.tile_edges[tile_id]
        right_edges = bundle.tileset.tile_edges[right_id]
        image.paste(square_explain_tile(left_edges, palette, 280, tile_id=tile_id, edge_labels=True), (94, 382))
        image.paste(square_explain_tile(right_edges, palette, 280, tile_id=right_id, edge_labels=True), (500, 382))
        draw.line((374, 522, 500, 522), fill=(54, 127, 169), width=12)
        draw.text((382, 456), f"E = W", font=explain_font(48), fill=EXPLAIN_TEXT_RGB)
        draw.text((404, 530), f"{left_edges[1]}", font=explain_font(56), fill=(32, 103, 148))
        draw.text((160, 314), facts[0], font=explain_font(48), fill=EXPLAIN_TEXT_RGB)
        draw.text((78, 704), f"tile #{tile_id}: N{left_edges[0]}  E{left_edges[1]}  S{left_edges[2]}  W{left_edges[3]}", font=explain_font(48), fill=EXPLAIN_TEXT_RGB)
        draw.text((78, 782), f"shared term: E{left_edges[1]} = W{right_edges[3]}", font=explain_font(52), fill=EXPLAIN_TEXT_RGB)
        required = region.boundary[selected][0]
        draw.text((78, 864), f"boundary: N{left_edges[0]} = required N{required}", font=explain_font(48), fill=EXPLAIN_TEXT_RGB)

    draw.rounded_rectangle((960, 216, 1844, 968), radius=18, fill=EXPLAIN_ACTIVE_RGB, outline=(180, 187, 198), width=2)
    draw.text((996, 244), "Returned model projection", font=explain_font(48), fill=EXPLAIN_TEXT_RGB)
    draw.text((996, 316), f"{summary.width} x {summary.height} | {summary.active_cell_count} active", font=explain_font(42), fill=EXPLAIN_MUTED_RGB)
    if summary.cells is not None:
        cell = max(2, min(18, 800 // summary.width, 300 // summary.height))
        origin_x, origin_y = 996, 420
        for index, tile_id in enumerate(summary.cells):
            x = origin_x + (index % summary.width) * cell
            y = origin_y + (index // summary.width) * cell
            fill = (205, 210, 218) if tile_id is None else (88, 170, 122)
            draw.rectangle((x, y, x + cell - 1, y + cell - 1), fill=fill)
        draw.text(
            (996, 420 + summary.height * cell + 34),
            "green = tile ID   gray = inactive",
            font=explain_font(42),
            fill=EXPLAIN_MUTED_RGB,
        )
        draw.text((996, 754), f"copied {summary.status.upper()} model", font=explain_font(52), fill=EXPLAIN_TEXT_RGB)
        draw.text((996, 830), f"{len(summary.cells)} dense entries", font=explain_font(44), fill=EXPLAIN_TEXT_RGB)
    draw.text(
        (36, 996),
        "Project construction order and returned projection only; Z3 internal search decisions are not exposed.",
        font=explain_font(32),
        fill=EXPLAIN_MUTED_RGB,
    )
    return image


def _compose_boolean_frame(
    summary: Z3EncodingSummary, bundle: ExplainabilityBundle, stage: int
) -> Image.Image:
    width, height = 1880, 1040
    image = Image.new("RGB", (width, height), EXPLAIN_PANEL_RGB)
    draw = ImageDraw.Draw(image)
    labels = ("variables", "source order", "ExactlyOne", "model")
    draw_explain_heading(
        draw,
        (36, 20),
        title="Boolean Z3 encoding order",
        subtitle=(
            f"encoding-order {stage + 1}/4 | repeated positions stay distinct | "
            "project construction, not Z3 search"
        ),
        scale=2,
    )
    for index, label in enumerate(labels):
        x = 36 + index * 452
        active = index <= stage
        draw.rounded_rectangle(
            (x, 118, x + 420, 184),
            radius=10,
            fill=(213, 235, 246) if active else (239, 241, 245),
            outline=(54, 127, 169) if index == stage else (184, 190, 201),
            width=4 if index == stage else 2,
        )
        draw.text(
            (x + 20, 136),
            f"{index + 1}  {label}",
            font=explain_font(28),
            fill=EXPLAIN_TEXT_RGB if active else EXPLAIN_MUTED_RGB,
        )

    draw.rounded_rectangle((36, 216, 1844, 968), radius=18, fill=EXPLAIN_ACTIVE_RGB, outline=(180, 187, 198), width=2)
    clause_lines = _boolean_clause_lines(bundle)
    if len(clause_lines) <= 3:
        selected = tuple(enumerate(clause_lines))
        omission = None
    else:
        selected = ((0, clause_lines[0]), (1, clause_lines[1]), (len(clause_lines) - 1, clause_lines[-1]))
        omission = f"{len(clause_lines) - 3} source clauses omitted between c1 and c{len(clause_lines) - 1}"
    draw.text((72, 244), "Source positions", font=explain_font(40), fill=EXPLAIN_TEXT_RGB)
    draw.text((1040, 244), "Actual sum asserted equal to one", font=explain_font(40), fill=EXPLAIN_TEXT_RGB)
    if omission is not None:
        draw.text((620, 250), omission, font=explain_font(28), fill=EXPLAIN_MUTED_RGB)
    for row, (clause_id, (_, equation)) in enumerate(selected):
        y = 330 + row * 176
        visible = stage >= 2
        draw.rounded_rectangle(
            (72, y, 800, y + 128),
            radius=8,
            fill=(213, 235, 246) if visible else (242, 244, 247),
            outline=(54, 127, 169) if visible else (190, 196, 205),
            width=2,
        )
        variables = bundle.formula.clauses[clause_id]
        draw.text((96, y + 38), f"c{clause_id}", font=explain_font(52), fill=EXPLAIN_TEXT_RGB if visible else EXPLAIN_MUTED_RGB)
        for position, variable in enumerate(variables):
            x = 230 + position * 170
            draw.rounded_rectangle((x, y + 24, x + 132, y + 104), radius=12, fill=EXPLAIN_PANEL_RGB, outline=(54, 127, 169), width=3)
            draw.text((x + 36, y + 40), f"x{variable}", font=explain_font(48), fill=EXPLAIN_TEXT_RGB if visible else EXPLAIN_MUTED_RGB)
        draw.line((820, y + 64, 994, y + 64), fill=(54, 127, 169), width=8)
        draw.polygon(((994, y + 64), (964, y + 46), (964, y + 82)), fill=(54, 127, 169))
        draw.rounded_rectangle((1020, y, 1808, y + 128), radius=8, fill=(213, 235, 246) if visible else (242, 244, 247), outline=(54, 127, 169) if visible else (190, 196, 205), width=2)
        draw.text((1050, y + 38), equation.replace(" + ", "+"), font=explain_font(48), fill=EXPLAIN_TEXT_RGB if visible else EXPLAIN_MUTED_RGB)
    assignment = summary.assignment or ()
    assignment_items = tuple(
        f"x{index}={'true' if value else 'false'}"
        for index, value in enumerate(assignment)
    )
    if len(assignment_items) <= 6:
        assignment_text = ", ".join(assignment_items)
        assignment_font = 48
    else:
        assignment_text = (
            ", ".join(assignment_items[:3])
            + f"  ... {len(assignment_items) - 5} omitted ...  "
            + ", ".join(assignment_items[-2:])
        )
        assignment_font = 40
    draw.rounded_rectangle((320, 874, 1560, 950), radius=12, fill=(213, 237, 224) if stage == 3 else (242, 244, 247), outline=(53, 144, 93), width=3)
    draw.text(
        (352, 890),
        f"copied {summary.status.upper()} model: {assignment_text or 'not applicable'}",
        font=explain_font(assignment_font),
        fill=EXPLAIN_TEXT_RGB if stage == 3 else EXPLAIN_MUTED_RGB,
    )
    draw.text(
        (36, 996),
        "Each repeated clause position remains a separate If term; Z3 internal search decisions are not exposed.",
        font=explain_font(32),
        fill=EXPLAIN_MUTED_RGB,
    )
    return image


def render_boolean_z3_assets(
    summary_path: str | Path,
    manifest_path: str | Path,
    output_directory: str | Path,
    *,
    duration_ms: int = 800,
) -> AnimationOutputs:
    summary = load_z3_encoding_summary(summary_path)
    if summary.engine != BOOLEAN_ENGINE:
        raise WangSquareRenderError("encoding animation requires a Boolean Z3 summary")
    bundle = load_explainability_bundle(manifest_path)
    _bind_oracle_inputs(summary, bundle)
    frames = tuple(_compose_boolean_frame(summary, bundle, stage) for stage in range(4))
    return write_animation_assets(
        frames,
        tuple(f"frame-{stage:02d}.png" for stage in range(4)),
        output_directory,
        fallback_index=3,
        duration_ms=duration_ms,
    )


def render_wang_z3_assets(
    summary_path: str | Path,
    manifest_path: str | Path,
    output_directory: str | Path,
    *,
    duration_ms: int = 800,
) -> AnimationOutputs:
    summary = load_z3_encoding_summary(summary_path)
    if summary.engine != WANG_ENGINE:
        raise WangSquareRenderError("encoding animation requires a Wang Z3 summary")
    bundle = load_explainability_bundle(manifest_path)
    _bind_oracle_inputs(summary, bundle)
    frames = tuple(_compose_wang_frame(summary, bundle, stage) for stage in range(5))
    return write_animation_assets(
        frames,
        tuple(f"frame-{stage:02d}.png" for stage in range(5)),
        output_directory,
        fallback_index=4,
        duration_ms=duration_ms,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="render a declared Boolean or Wang Z3 encoding order without Z3"
    )
    parser.add_argument("summary", type=Path)
    parser.add_argument("manifest", type=Path)
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
            args.summary,
            args.manifest,
            args.output_directory,
            duration_ms=args.duration_ms,
        )
    except (FileNotFoundError, WangSquareRenderError) as error:
        parser.error(str(error))
    print(f"animation={outputs.animation}")
    print(f"fallback={outputs.fallback}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
