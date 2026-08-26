"""Strict consumer and raster views for static explainability snapshots."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Final

import numpy as np
from PIL import Image, ImageDraw

from wang_explain import (
    EXPLAIN_ACTIVE_RGB,
    EXPLAIN_MUTED_RGB,
    EXPLAIN_OUTLINE_RGB,
    EXPLAIN_PANEL_RGB,
    EXPLAIN_TEXT_RGB,
    draw_boundary_side,
    draw_explain_heading,
    draw_inactive_key,
    draw_lines,
    draw_palette_legend,
    explain_font,
    hex_explain_tile,
    square_explain_tile,
    square_inactive_tile,
    square_region_tile,
    wrap_text,
)
from wang_hex_port import (
    WangHexPort,
    WangPresentation,
    WangSquareRenderError,
    check_square_to_hex,
    reduce_square_to_hex,
)
from wang_square import (
    DEFAULT_MARGIN,
    DEFAULT_PIXELS_PER_CELL,
    MAX_MARGIN,
    MAX_PIXELS_PER_CELL,
    MIN_PIXELS_PER_CELL,
    _build_palette_from_edges,
    _check_canvas_limits,
    _hex_mask,
    _hex_vertices,
    _render_integer,
    _save_png_atomic,
)


FORMULA_SCHEMA: Final = "cm13-formula-snapshot-v1"
TILESET_SCHEMA: Final = "wang-tileset-snapshot-v1"
REGION_SCHEMA: Final = "wang-region-snapshot-v1"
MANIFEST_SCHEMA: Final = "wang-explain-manifest-v1"
DIRECTIONS: Final = ("N", "E", "S", "W")
HEX_DIRECTIONS: Final = ("E", "SE", "SW", "W", "NW", "NE")
_SHA256_PATTERN: Final = re.compile(r"[0-9a-f]{64}")
_FORMULA_PANEL_WIDTH: Final = 360
_LEGEND_WIDTH: Final = 190
_PANEL_GAP: Final = 20
_HEADER_HEIGHT: Final = 58


@dataclass(frozen=True, slots=True)
class FormulaSnapshot:
    source_name: str
    source_sha256: str
    variable_count: int
    clauses: tuple[tuple[int, int, int], ...]


@dataclass(frozen=True, slots=True)
class TilesetSnapshot:
    colors: tuple[int, ...]
    tile_edges: tuple[tuple[int, int, int, int], ...]


@dataclass(frozen=True, slots=True)
class RegionSnapshot:
    min_x: int
    min_y: int
    max_x: int
    max_y: int
    source_formula_sha256: str
    active: tuple[bool, ...]
    boundary: tuple[
        tuple[int | None, int | None, int | None, int | None] | None,
        ...,
    ]

    @property
    def width(self) -> int:
        return self.max_x - self.min_x + 1

    @property
    def height(self) -> int:
        return self.max_y - self.min_y + 1


@dataclass(frozen=True, slots=True)
class ExplainabilityBundle:
    source_formula_sha256: str
    formula: FormulaSnapshot
    tileset: TilesetSnapshot
    region: RegionSnapshot


def _fail(path: str, message: str) -> None:
    raise WangSquareRenderError(f"explainability snapshot {path}: {message}")


def _object(value: object, path: str) -> dict[str, object]:
    if type(value) is not dict:
        _fail(path, "must be an object")
    return value


def _array(value: object, path: str) -> list[object]:
    if type(value) is not list:
        _fail(path, "must be an array")
    return value


def _string(value: object, path: str) -> str:
    if type(value) is not str:
        _fail(path, "must be a string")
    return value


def _integer(value: object, path: str, *, nonnegative: bool) -> int:
    if type(value) is not int:
        _fail(path, "must be an integer")
    if nonnegative and value < 0:
        _fail(path, "must be nonnegative")
    return value


def _fields(
    value: dict[str, object],
    expected: frozenset[str],
    path: str,
) -> None:
    actual = frozenset(value)
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if missing:
        _fail(path, f"missing fields: {', '.join(missing)}")
    if extra:
        _fail(path, f"unknown fields: {', '.join(extra)}")


def _literal(value: object, expected: str, path: str) -> None:
    if _string(value, path) != expected:
        _fail(path, f"must equal {expected!r}")


def _sha256(value: object, path: str) -> str:
    digest = _string(value, path)
    if _SHA256_PATTERN.fullmatch(digest) is None:
        _fail(path, "must be a lowercase SHA-256 digest")
    return digest


def _basename(value: object, path: str) -> str:
    name = _string(value, path)
    if (
        not name
        or name in {".", ".."}
        or Path(name).name != name
        or "/" in name
        or "\\" in name
    ):
        _fail(path, "must be a nonempty artifact basename")
    return name


def _reject_duplicate_members(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise WangSquareRenderError(
                f"JSON object contains duplicate member {key!r}"
            )
        result[key] = value
    return result


def _reject_nonfinite_constant(value: str) -> None:
    raise WangSquareRenderError(
        f"JSON document contains non-finite number {value}"
    )


def _load_json_bytes(encoded: bytes, label: str) -> dict[str, object]:
    try:
        source = encoded.decode("utf-8")
    except UnicodeDecodeError as error:
        raise WangSquareRenderError(f"{label}: is not valid UTF-8") from error
    try:
        document = json.loads(
            source,
            object_pairs_hook=_reject_duplicate_members,
            parse_constant=_reject_nonfinite_constant,
        )
    except json.JSONDecodeError as error:
        raise WangSquareRenderError(
            f"{label}: invalid JSON at line {error.lineno}, "
            f"column {error.colno}: {error.msg}"
        ) from error
    except WangSquareRenderError:
        raise
    except (ValueError, RecursionError) as error:
        raise WangSquareRenderError(f"{label}: invalid JSON value: {error}") from error
    return _object(document, label)


def _read_bytes(path: Path, label: str) -> bytes:
    try:
        return path.read_bytes()
    except OSError as error:
        raise WangSquareRenderError(f"cannot read {label} {path!s}: {error}") from error


def _parse_formula(document: dict[str, object]) -> FormulaSnapshot:
    _fields(
        document,
        frozenset({"schema", "source", "variable_count", "clauses"}),
        "formula $",
    )
    _literal(document["schema"], FORMULA_SCHEMA, "formula $.schema")
    source = _object(document["source"], "formula $.source")
    _fields(source, frozenset({"name", "sha256"}), "formula $.source")
    source_name = _basename(source["name"], "formula $.source.name")
    source_digest = _sha256(source["sha256"], "formula $.source.sha256")
    variable_count = _integer(
        document["variable_count"],
        "formula $.variable_count",
        nonnegative=True,
    )
    if variable_count == 0:
        _fail("formula $.variable_count", "must be positive")
    clauses = _array(document["clauses"], "formula $.clauses")
    if len(clauses) != variable_count:
        _fail("formula $.clauses", "length must equal variable_count")
    occurrences = [0] * variable_count
    projected: list[tuple[int, int, int]] = []
    for clause_id, raw_clause in enumerate(clauses):
        path = f"formula $.clauses[{clause_id}]"
        clause = _object(raw_clause, path)
        _fields(clause, frozenset({"clause_id", "variables"}), path)
        actual_id = _integer(
            clause["clause_id"],
            f"{path}.clause_id",
            nonnegative=True,
        )
        if actual_id != clause_id:
            _fail(f"{path}.clause_id", "must equal canonical position")
        variables = _array(clause["variables"], f"{path}.variables")
        if len(variables) != 3:
            _fail(f"{path}.variables", "must contain exactly three positions")
        checked: list[int] = []
        for position, raw_variable in enumerate(variables):
            variable = _integer(
                raw_variable,
                f"{path}.variables[{position}]",
                nonnegative=True,
            )
            if variable >= variable_count:
                _fail(f"{path}.variables[{position}]", "is outside the domain")
            occurrences[variable] += 1
            checked.append(variable)
        projected.append(tuple(checked))
    if any(count != 3 for count in occurrences):
        _fail("formula $.clauses", "every variable must occur exactly three times")
    return FormulaSnapshot(
        source_name=source_name,
        source_sha256=source_digest,
        variable_count=variable_count,
        clauses=tuple(projected),
    )


def _edges(
    value: object,
    path: str,
    *,
    optional: bool,
) -> tuple[int | None, int | None, int | None, int | None]:
    edges = _object(value, path)
    _fields(edges, frozenset(DIRECTIONS), path)
    projected: list[int | None] = []
    for direction in DIRECTIONS:
        color = edges[direction]
        if optional and color is None:
            projected.append(None)
        else:
            projected.append(
                _integer(color, f"{path}.{direction}", nonnegative=True)
            )
    return tuple(projected)


def _parse_tileset(document: dict[str, object]) -> TilesetSnapshot:
    _fields(
        document,
        frozenset({"schema", "geometry", "directions", "colors", "tiles"}),
        "tileset $",
    )
    _literal(document["schema"], TILESET_SCHEMA, "tileset $.schema")
    _literal(document["geometry"], "square", "tileset $.geometry")
    if _array(document["directions"], "tileset $.directions") != list(DIRECTIONS):
        _fail("tileset $.directions", "must equal N/E/S/W")
    raw_colors = _array(document["colors"], "tileset $.colors")
    colors = tuple(
        _integer(color, f"tileset $.colors[{index}]", nonnegative=True)
        for index, color in enumerate(raw_colors)
    )
    if not colors or list(colors) != sorted(set(colors)):
        _fail("tileset $.colors", "must be nonempty, increasing, and unique")
    raw_tiles = _array(document["tiles"], "tileset $.tiles")
    if not raw_tiles:
        _fail("tileset $.tiles", "must not be empty")
    tiles: list[tuple[int, int, int, int]] = []
    for expected_id, raw_tile in enumerate(raw_tiles):
        path = f"tileset $.tiles[{expected_id}]"
        tile = _object(raw_tile, path)
        _fields(tile, frozenset({"tile_id", "edges"}), path)
        tile_id = _integer(tile["tile_id"], f"{path}.tile_id", nonnegative=True)
        if tile_id != expected_id:
            _fail(f"{path}.tile_id", "must equal canonical table position")
        projected = _edges(tile["edges"], f"{path}.edges", optional=False)
        assert all(color is not None for color in projected)
        tiles.append(tuple(projected))
    used = sorted({color for tile in tiles for color in tile})
    if list(colors) != used:
        _fail("tileset $.colors", "must equal exactly the colors used by tiles")
    return TilesetSnapshot(colors=colors, tile_edges=tuple(tiles))


def _parse_region(document: dict[str, object]) -> RegionSnapshot:
    _fields(
        document,
        frozenset(
            {
                "schema",
                "geometry",
                "source_formula_sha256",
                "bounds",
                "active",
                "boundary",
            }
        ),
        "region $",
    )
    _literal(document["schema"], REGION_SCHEMA, "region $.schema")
    _literal(document["geometry"], "square", "region $.geometry")
    source_digest = _sha256(
        document["source_formula_sha256"],
        "region $.source_formula_sha256",
    )
    bounds = _object(document["bounds"], "region $.bounds")
    fields = frozenset(
        {
            "min_x_inclusive",
            "min_y_inclusive",
            "max_x_inclusive",
            "max_y_inclusive",
        }
    )
    _fields(bounds, fields, "region $.bounds")
    min_x = _integer(
        bounds["min_x_inclusive"],
        "region $.bounds.min_x_inclusive",
        nonnegative=False,
    )
    min_y = _integer(
        bounds["min_y_inclusive"],
        "region $.bounds.min_y_inclusive",
        nonnegative=False,
    )
    max_x = _integer(
        bounds["max_x_inclusive"],
        "region $.bounds.max_x_inclusive",
        nonnegative=False,
    )
    max_y = _integer(
        bounds["max_y_inclusive"],
        "region $.bounds.max_y_inclusive",
        nonnegative=False,
    )
    if max_x < min_x or max_y < min_y:
        _fail("region $.bounds", "inclusive maxima must not precede minima")
    width = max_x - min_x + 1
    height = max_y - min_y + 1
    area = width * height
    raw_active = _array(document["active"], "region $.active")
    raw_boundary = _array(document["boundary"], "region $.boundary")
    if len(raw_active) != area or len(raw_boundary) != area:
        _fail("region $", f"active and boundary lengths must equal area {area}")
    if any(type(value) is not bool for value in raw_active):
        _fail("region $.active", "must contain only booleans")
    if not any(raw_active):
        _fail("region $.active", "must contain an active cell")
    active = tuple(raw_active)
    boundary: list[
        tuple[int | None, int | None, int | None, int | None] | None
    ] = []
    for index, raw_sides in enumerate(raw_boundary):
        if not active[index]:
            if raw_sides is not None:
                _fail(f"region $.boundary[{index}]", "must be null when inactive")
            boundary.append(None)
            continue
        if raw_sides is None:
            _fail(f"region $.boundary[{index}]", "must be present when active")
        boundary.append(
            _edges(raw_sides, f"region $.boundary[{index}]", optional=True)
        )
    for index, is_active in enumerate(active):
        if not is_active:
            continue
        sides = boundary[index]
        assert sides is not None
        x = index % width
        y = index // width
        for direction, (dx, dy) in enumerate(((0, -1), (1, 0), (0, 1), (-1, 0))):
            neighbor_x = x + dx
            neighbor_y = y + dy
            if (
                0 <= neighbor_x < width
                and 0 <= neighbor_y < height
                and active[neighbor_y * width + neighbor_x]
                and sides[direction] is not None
            ):
                _fail(
                    f"region $.boundary[{index}].{DIRECTIONS[direction]}",
                    "must be null on an internal edge",
                )
    return RegionSnapshot(
        min_x=min_x,
        min_y=min_y,
        max_x=max_x,
        max_y=max_y,
        source_formula_sha256=source_digest,
        active=active,
        boundary=tuple(boundary),
    )


def load_explainability_bundle(path: str | Path) -> ExplainabilityBundle:
    """Load one manifest, verify hashes, and project its three artifacts."""
    manifest_path = Path(path)
    manifest = _load_json_bytes(
        _read_bytes(manifest_path, "manifest"),
        str(manifest_path),
    )
    _fields(
        manifest,
        frozenset({"schema", "stage", "source_formula_sha256", "artifacts"}),
        "$",
    )
    _literal(manifest["schema"], MANIFEST_SCHEMA, "$.schema")
    _literal(manifest["stage"], "region", "$.stage")
    source_digest = _sha256(
        manifest["source_formula_sha256"],
        "$.source_formula_sha256",
    )
    artifacts = _object(manifest["artifacts"], "$.artifacts")
    _fields(artifacts, frozenset({"formula", "tileset", "region"}), "$.artifacts")
    expected_schemas = {
        "formula": FORMULA_SCHEMA,
        "tileset": TILESET_SCHEMA,
        "region": REGION_SCHEMA,
    }
    documents: dict[str, dict[str, object]] = {}
    for name, expected_schema in expected_schemas.items():
        reference_path = f"$.artifacts.{name}"
        reference = _object(artifacts[name], reference_path)
        _fields(reference, frozenset({"path", "sha256", "schema"}), reference_path)
        artifact_name = _basename(reference["path"], f"{reference_path}.path")
        expected_digest = _sha256(
            reference["sha256"],
            f"{reference_path}.sha256",
        )
        _literal(reference["schema"], expected_schema, f"{reference_path}.schema")
        artifact_path = manifest_path.parent / artifact_name
        encoded = _read_bytes(artifact_path, f"{name} artifact")
        if hashlib.sha256(encoded).hexdigest() != expected_digest:
            _fail(f"{reference_path}.sha256", f"does not match {artifact_name}")
        documents[name] = _load_json_bytes(encoded, str(artifact_path))

    formula = _parse_formula(documents["formula"])
    tileset = _parse_tileset(documents["tileset"])
    region = _parse_region(documents["region"])
    if formula.source_sha256 != source_digest:
        _fail("$.source_formula_sha256", "does not match formula snapshot")
    if region.source_formula_sha256 != source_digest:
        _fail("$.source_formula_sha256", "does not match region snapshot")
    colors = set(tileset.colors)
    for index, sides in enumerate(region.boundary):
        if sides is None:
            continue
        for direction, color in enumerate(sides):
            if color is not None and color not in colors:
                _fail(
                    f"region $.boundary[{index}].{DIRECTIONS[direction]}",
                    "is absent from the referenced tileset",
                )
    return ExplainabilityBundle(
        source_formula_sha256=source_digest,
        formula=formula,
        tileset=tileset,
        region=region,
    )


def _palette(bundle: ExplainabilityBundle) -> dict[int, tuple[int, int, int]]:
    boundary_colors = tuple(
        sorted(
            {
                color
                for sides in bundle.region.boundary
                if sides is not None
                for color in sides
                if color is not None
            }
        )
    )
    edges: tuple[tuple[int, ...], ...]
    if boundary_colors:
        edges = (*bundle.tileset.tile_edges, boundary_colors)
    else:
        edges = bundle.tileset.tile_edges
    return _build_palette_from_edges(edges)


def _formula_lines(formula: FormulaSnapshot) -> list[str]:
    lines = [
        f"Source: {formula.source_name}",
        "SHA-256:",
        formula.source_sha256[:32],
        formula.source_sha256[32:],
        "",
        "Cubic monotone 1-in-3 SAT",
        f"Variables: {formula.variable_count}",
        f"Clauses: {len(formula.clauses)}",
        "",
    ]
    for clause_id, clause in enumerate(formula.clauses):
        variables = ", ".join(f"x{variable}" for variable in clause)
        lines.append(f"c{clause_id}: exactly-one({variables})")
    return lines


def _compose_formula(bundle: ExplainabilityBundle, margin: int) -> np.ndarray:
    checked_margin = _render_integer(
        margin,
        "margin",
        minimum=0,
        maximum=MAX_MARGIN,
    )
    content_width = 780
    width = 2 * checked_margin + content_width
    font = explain_font(16)
    line_height = 25
    lines = _formula_lines(bundle.formula)
    height = 2 * checked_margin + _HEADER_HEIGHT + 20 + len(lines) * line_height
    _check_canvas_limits(width, height)
    canvas = Image.new("RGB", (width, height), EXPLAIN_PANEL_RGB)
    draw = ImageDraw.Draw(canvas)
    draw_explain_heading(
        draw,
        (checked_margin, checked_margin),
        title="Parsed formula snapshot",
        subtitle=(
            "positions and duplicates are preserved exactly; "
            "variable IDs are zero-based"
        ),
    )
    y = checked_margin + _HEADER_HEIGHT
    for line in lines:
        wrapped = wrap_text(draw, line, font, content_width)
        y = draw_lines(draw, wrapped, (checked_margin, y), font=font, spacing=7)
    return np.asarray(canvas, dtype=np.uint8)


def _hex_tile_edges(
    tileset: TilesetSnapshot,
) -> tuple[tuple[tuple[int, int, int, int, int, int], ...], int]:
    square = WangPresentation(
        min_x=0,
        min_y=0,
        max_x=0,
        max_y=0,
        tile_edges=tileset.tile_edges,
        cells=(0,),
        boundary=((None, None, None, None),),
    )
    port = reduce_square_to_hex(square)
    check_square_to_hex(square, port)
    return port.tile_edges, port.fresh_color


def _region_hex_port(bundle: ExplainabilityBundle) -> WangHexPort:
    region = bundle.region
    square = WangPresentation(
        min_x=region.min_x,
        min_y=region.min_y,
        max_x=region.max_x,
        max_y=region.max_y,
        tile_edges=bundle.tileset.tile_edges,
        # The static region has no assignment.  Empty presentation cells let
        # the existing port/checker validate only table, bounds, and boundary.
        cells=(None,) * len(region.active),
        boundary=region.boundary,
    )
    port = reduce_square_to_hex(square)
    check_square_to_hex(square, port)
    return port


def _compose_tileset(
    bundle: ExplainabilityBundle,
    pixels_per_cell: int,
    margin: int,
    *,
    hex_mode: bool,
) -> np.ndarray:
    checked = _render_integer(
        pixels_per_cell,
        "pixels_per_cell",
        minimum=MIN_PIXELS_PER_CELL,
        maximum=MAX_PIXELS_PER_CELL,
    )
    checked_margin = _render_integer(
        margin,
        "margin",
        minimum=0,
        maximum=MAX_MARGIN,
    )
    columns = 6
    rows = (len(bundle.tileset.tile_edges) + columns - 1) // columns
    gap = 14
    palette = _palette(bundle)
    fresh: int | None = None
    if hex_mode:
        tile_edges, fresh = _hex_tile_edges(bundle.tileset)
        palette = _build_palette_from_edges(tile_edges)
        radius = max(28, checked)
        shoulder = radius // 2
        tile_width = 2 * radius + 1
        tile_height = 2 * radius + 1
    else:
        tile_edges = bundle.tileset.tile_edges
        tile_width = tile_height = max(64, checked * 2)
        radius = 0
        shoulder = 0
    grid_width = columns * tile_width + (columns - 1) * gap
    grid_height = rows * tile_height + (rows - 1) * gap
    width = 2 * checked_margin + grid_width + _PANEL_GAP + _LEGEND_WIDTH
    height = max(2 * checked_margin + _HEADER_HEIGHT + grid_height, 410)
    _check_canvas_limits(width, height)
    canvas = Image.new("RGB", (width, height), EXPLAIN_PANEL_RGB)
    draw = ImageDraw.Draw(canvas)
    geometry = "hex" if hex_mode else "square"
    draw_explain_heading(
        draw,
        (checked_margin, checked_margin),
        title=f"Tile sheet ({len(tile_edges)} tiles) - {geometry}",
        subtitle="tile ID at center; numeric logical color on every side",
    )
    grid_y = checked_margin + _HEADER_HEIGHT
    vertices = _hex_vertices(radius, shoulder) if hex_mode else ()
    for tile_id, edges in enumerate(tile_edges):
        column = tile_id % columns
        row = tile_id // columns
        x = checked_margin + column * (tile_width + gap)
        y = grid_y + row * (tile_height + gap)
        if hex_mode:
            asset = hex_explain_tile(
                edges,
                palette,
                radius,
                vertices,
                tile_id=tile_id,
                edge_labels=True,
            )
            canvas.paste(asset, (x, y), _hex_mask(radius, vertices))
        else:
            asset = square_explain_tile(
                edges,
                palette,
                tile_width,
                tile_id=tile_id,
                edge_labels=True,
            )
            canvas.paste(asset, (x, y))
    legend_x = checked_margin + grid_width + _PANEL_GAP
    _, legend_height = draw_palette_legend(
        ImageDraw.Draw(canvas),
        palette,
        (legend_x, grid_y),
        columns=2,
    )
    if fresh is not None:
        ImageDraw.Draw(canvas).text(
            (legend_x, grid_y + legend_height + 10),
            f"kappa = {fresh} (fresh axis)",
            font=explain_font(13),
            fill=EXPLAIN_TEXT_RGB,
        )
    return np.asarray(canvas, dtype=np.uint8)


def _formula_panel(
    canvas: Image.Image,
    bundle: ExplainabilityBundle,
    origin: tuple[int, int],
    max_height: int,
) -> int:
    draw = ImageDraw.Draw(canvas)
    x, y = origin
    draw.text(
        (x, y),
        "Formula being simulated",
        font=explain_font(17),
        fill=EXPLAIN_TEXT_RGB,
    )
    y += 30
    font = explain_font(13)
    for line in _formula_lines(bundle.formula):
        wrapped = wrap_text(draw, line, font, _FORMULA_PANEL_WIDTH)
        for item in wrapped:
            if y + 20 > max_height:
                draw.text((x, y), "...", font=font, fill=EXPLAIN_MUTED_RGB)
                return y + 22
            draw.text((x, y), item, font=font, fill=EXPLAIN_TEXT_RGB)
            y += 20
    return y


def _compose_region_square(
    bundle: ExplainabilityBundle,
    pixels_per_cell: int,
    margin: int,
) -> np.ndarray:
    ppc = _render_integer(
        pixels_per_cell,
        "pixels_per_cell",
        minimum=MIN_PIXELS_PER_CELL,
        maximum=MAX_PIXELS_PER_CELL,
    )
    checked_margin = _render_integer(
        margin,
        "margin",
        minimum=0,
        maximum=MAX_MARGIN,
    )
    region = bundle.region
    grid_width = region.width * ppc
    grid_height = region.height * ppc
    side_width = max(_FORMULA_PANEL_WIDTH, _LEGEND_WIDTH)
    width = 2 * checked_margin + grid_width + _PANEL_GAP + side_width
    formula_height = 30 + len(_formula_lines(bundle.formula)) * 20
    legend_rows = (len(_palette(bundle)) + 1) // 2
    side_height = formula_height + 20 + 36 + legend_rows * 22 + 42
    height = max(
        2 * checked_margin + _HEADER_HEIGHT + grid_height,
        2 * checked_margin + _HEADER_HEIGHT + side_height,
    )
    _check_canvas_limits(width, height)
    canvas = Image.new("RGB", (width, height), EXPLAIN_PANEL_RGB)
    draw = ImageDraw.Draw(canvas)
    draw_explain_heading(
        draw,
        (checked_margin, checked_margin),
        title="Yang-Zhang region - before solving",
        subtitle=(
            "active mask and exposed boundary constraints; "
            "no tile is assigned"
        ),
    )
    grid_x = checked_margin
    grid_y = checked_margin + _HEADER_HEIGHT
    palette = _palette(bundle)
    inactive = square_inactive_tile(ppc)
    for index, active in enumerate(region.active):
        x = grid_x + (index % region.width) * ppc
        y = grid_y + (index // region.width) * ppc
        if not active:
            canvas.paste(inactive, (x, y))
            continue
        sides = region.boundary[index]
        assert sides is not None
        canvas.paste(square_region_tile(ppc, sides, palette), (x, y))
    side_x = grid_x + grid_width + _PANEL_GAP
    formula_end = _formula_panel(
        canvas,
        bundle,
        (side_x, grid_y),
        height - checked_margin,
    )
    legend_y = formula_end + 16
    _, legend_height = draw_palette_legend(
        ImageDraw.Draw(canvas),
        palette,
        (side_x, legend_y),
        columns=2,
    )
    draw_inactive_key(
        ImageDraw.Draw(canvas),
        (side_x, legend_y + legend_height + 8),
    )
    return np.asarray(canvas, dtype=np.uint8)


def _compose_region_hex(
    bundle: ExplainabilityBundle,
    pixels_per_cell: int,
    margin: int,
) -> np.ndarray:
    radius = _render_integer(
        pixels_per_cell,
        "pixels_per_cell",
        minimum=MIN_PIXELS_PER_CELL,
        maximum=MAX_PIXELS_PER_CELL,
    )
    checked_margin = _render_integer(
        margin,
        "margin",
        minimum=0,
        maximum=MAX_MARGIN,
    )
    region = bundle.region
    port = _region_hex_port(bundle)
    shoulder = radius // 2
    raw_width = (
        2 * radius * (region.width - 1)
        + radius * (region.height - 1)
        + 2 * radius
        + 1
    )
    raw_height = (
        (radius + shoulder) * (region.height - 1) + 2 * radius + 1
    )
    side_width = max(_FORMULA_PANEL_WIDTH, _LEGEND_WIDTH)
    width = 2 * checked_margin + raw_width + _PANEL_GAP + side_width
    formula_height = 30 + len(_formula_lines(bundle.formula)) * 20
    legend_rows = (len(_palette(bundle)) + 1) // 2
    side_height = formula_height + 20 + 36 + legend_rows * 22 + 42
    height = max(
        2 * checked_margin + _HEADER_HEIGHT + raw_height,
        2 * checked_margin + _HEADER_HEIGHT + side_height,
    )
    _check_canvas_limits(width, height)
    canvas = Image.new("RGB", (width, height), EXPLAIN_PANEL_RGB)
    draw = ImageDraw.Draw(canvas)
    draw_explain_heading(
        draw,
        (checked_margin, checked_margin),
        title="Yang-Zhang region - checked axial presentation",
        subtitle="square coordinates (x,y) become (q,r); no tile is assigned",
    )
    grid_x = checked_margin
    grid_y = checked_margin + _HEADER_HEIGHT
    vertices = _hex_vertices(radius, shoulder)
    mask = _hex_mask(radius, vertices)
    neutral = Image.new("RGB", (2 * radius + 1, 2 * radius + 1), EXPLAIN_PANEL_RGB)
    ImageDraw.Draw(neutral).polygon(
        vertices,
        fill=EXPLAIN_ACTIVE_RGB,
        outline=EXPLAIN_OUTLINE_RGB,
    )
    inactive = Image.new("RGB", neutral.size, EXPLAIN_PANEL_RGB)
    inactive_draw = ImageDraw.Draw(inactive)
    inactive_draw.polygon(
        vertices,
        fill=(215, 220, 228),
        outline=EXPLAIN_OUTLINE_RGB,
    )
    inactive_draw.line(
        (radius // 2, radius // 2, radius + radius // 2, radius + radius // 2),
        fill=EXPLAIN_OUTLINE_RGB,
        width=1,
    )
    inactive_draw.line(
        (radius + radius // 2, radius // 2, radius // 2, radius + radius // 2),
        fill=EXPLAIN_OUTLINE_RGB,
        width=1,
    )
    palette = _palette(bundle)
    min_anchor_x = 2 * radius * region.min_x + radius * region.min_y
    min_anchor_y = (radius + shoulder) * region.min_y
    overlays: list[
        tuple[tuple[int, int], tuple[int, int], tuple[int, int, int]]
    ] = []
    for index, active in enumerate(region.active):
        local_q = index % region.width
        local_r = index // region.width
        q = region.min_x + local_q
        r = region.min_y + local_r
        anchor_x = 2 * radius * q + radius * r
        anchor_y = (radius + shoulder) * r
        x = grid_x + anchor_x - min_anchor_x
        y = grid_y + anchor_y - min_anchor_y
        canvas.paste(neutral if active else inactive, (x, y), mask)
        if not active:
            continue
        sides = port.boundary[index]
        assert sides is not None
        for direction, color in enumerate(sides):
            if color is None:
                continue
            first = vertices[(direction + 1) % 6]
            second = vertices[(direction + 2) % 6]
            overlays.append(
                (
                    (x + first[0], y + first[1]),
                    (x + second[0], y + second[1]),
                    palette[color],
                )
            )
    draw = ImageDraw.Draw(canvas)
    for first, second, rgb in overlays:
        draw_boundary_side(draw, first, second, rgb, width=max(2, radius // 7))
    side_x = grid_x + raw_width + _PANEL_GAP
    formula_end = _formula_panel(
        canvas,
        bundle,
        (side_x, grid_y),
        height - checked_margin,
    )
    legend_y = formula_end + 16
    _, legend_height = draw_palette_legend(
        ImageDraw.Draw(canvas),
        palette,
        (side_x, legend_y),
        columns=2,
    )
    draw_inactive_key(
        ImageDraw.Draw(canvas),
        (side_x, legend_y + legend_height + 8),
    )
    return np.asarray(canvas, dtype=np.uint8)


def render_pipeline_snapshot(
    input_path: str | Path,
    output_path: str | Path,
    *,
    view: str,
    pixels_per_cell: int = DEFAULT_PIXELS_PER_CELL,
    margin: int = DEFAULT_MARGIN,
    hex_mode: bool = False,
) -> None:
    """Render one strict manifest view and atomically install its PNG."""
    bundle = load_explainability_bundle(input_path)
    if view == "formula":
        if hex_mode:
            raise WangSquareRenderError("--hex is not meaningful for formula view")
        canvas = _compose_formula(bundle, margin)
    elif view == "tileset":
        canvas = _compose_tileset(
            bundle,
            pixels_per_cell,
            margin,
            hex_mode=hex_mode,
        )
    elif view == "region":
        if hex_mode:
            canvas = _compose_region_hex(bundle, pixels_per_cell, margin)
        else:
            canvas = _compose_region_square(bundle, pixels_per_cell, margin)
    else:
        raise WangSquareRenderError(
            "snapshot view must be one of formula, tileset, or region"
        )
    _save_png_atomic(canvas, output_path)
