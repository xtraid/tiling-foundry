"""Versioned static snapshots for explainable Wang pipeline stages.

The producer is standard-library-only.  It converts the immutable Python
formula, tileset, and region models into closed JSON documents and installs a
manifest only after all content-addressed artifacts have been written.  The
snapshots carry presentation-neutral semantics; raster layout remains the
isolated renderer's responsibility.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Final

from model.formula import Formula
from model.region import Region
from model.tileset import COLOR_NONE, TILESET, Tileset


FORMULA_SCHEMA: Final = "cm13-formula-snapshot-v1"
TILESET_SCHEMA: Final = "wang-tileset-snapshot-v1"
REGION_SCHEMA: Final = "wang-region-snapshot-v1"
MANIFEST_SCHEMA: Final = "wang-explain-manifest-v1"
GEOMETRY: Final = "square"
STAGE: Final = "region"
DIRECTIONS: Final = ("N", "E", "S", "W")
_OFFSETS: Final = ((0, -1), (1, 0), (0, 1), (-1, 0))
_SHA256_PATTERN: Final = re.compile(r"[0-9a-f]{64}")


class PipelineSnapshotError(ValueError):
    """Raised when a static snapshot is malformed or cannot be installed."""


def _fail(path: str, message: str) -> None:
    raise PipelineSnapshotError(f"{path}: {message}")


def _require_object(value: object, path: str) -> dict[str, object]:
    if type(value) is not dict:
        _fail(path, "must be an object")
    return value


def _require_array(value: object, path: str) -> list[object]:
    if type(value) is not list:
        _fail(path, "must be an array")
    return value


def _require_string(value: object, path: str) -> str:
    if type(value) is not str:
        _fail(path, "must be a string")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as error:
        raise PipelineSnapshotError(
            f"{path}: must contain valid UTF-8 text"
        ) from error
    return value


def _require_integer(
    value: object,
    path: str,
    *,
    nonnegative: bool,
) -> int:
    if type(value) is not int:
        _fail(path, "must be an integer")
    if nonnegative and value < 0:
        _fail(path, "must be nonnegative")
    return value


def _require_exact_fields(
    value: dict[str, object],
    expected: frozenset[str],
    path: str,
) -> None:
    if any(type(key) is not str for key in value):
        _fail(path, "object member names must be strings")
    actual = frozenset(value)
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if missing:
        _fail(path, f"missing fields: {', '.join(missing)}")
    if extra:
        _fail(path, f"unknown fields: {', '.join(extra)}")


def _require_literal(
    value: object,
    expected: str,
    path: str,
) -> None:
    if _require_string(value, path) != expected:
        _fail(path, f"must equal {expected!r}")


def _require_sha256(value: object, path: str) -> str:
    digest = _require_string(value, path)
    if _SHA256_PATTERN.fullmatch(digest) is None:
        _fail(path, "must be a lowercase SHA-256 digest")
    return digest


def _require_artifact_name(value: object, path: str) -> str:
    name = _require_string(value, path)
    if (
        not name
        or name in {".", ".."}
        or Path(name).name != name
        or "/" in name
        or "\\" in name
    ):
        _fail(path, "must be a nonempty artifact basename")
    return name


def _validate_edges(
    value: object,
    path: str,
    *,
    optional: bool,
) -> tuple[int | None, int | None, int | None, int | None]:
    edges = _require_object(value, path)
    _require_exact_fields(edges, frozenset(DIRECTIONS), path)
    checked: list[int | None] = []
    for direction in DIRECTIONS:
        color = edges[direction]
        if optional and color is None:
            checked.append(None)
        else:
            checked.append(
                _require_integer(
                    color,
                    f"{path}.{direction}",
                    nonnegative=True,
                )
            )
    return tuple(checked)


def validate_formula_snapshot(document: object) -> None:
    """Validate one closed parsed-formula snapshot."""
    root = _require_object(document, "$")
    _require_exact_fields(
        root,
        frozenset({"schema", "source", "variable_count", "clauses"}),
        "$",
    )
    _require_literal(root["schema"], FORMULA_SCHEMA, "$.schema")

    source = _require_object(root["source"], "$.source")
    _require_exact_fields(source, frozenset({"name", "sha256"}), "$.source")
    _require_artifact_name(source["name"], "$.source.name")
    _require_sha256(source["sha256"], "$.source.sha256")

    variable_count = _require_integer(
        root["variable_count"],
        "$.variable_count",
        nonnegative=True,
    )
    if variable_count == 0:
        _fail("$.variable_count", "must be positive")

    clauses = _require_array(root["clauses"], "$.clauses")
    if len(clauses) != variable_count:
        _fail(
            "$.clauses",
            "length must equal variable_count for a cubic CM1-in-3 formula",
        )
    occurrences = [0] * variable_count
    for clause_id, raw_clause in enumerate(clauses):
        path = f"$.clauses[{clause_id}]"
        clause = _require_object(raw_clause, path)
        _require_exact_fields(
            clause,
            frozenset({"clause_id", "variables"}),
            path,
        )
        actual_id = _require_integer(
            clause["clause_id"],
            f"{path}.clause_id",
            nonnegative=True,
        )
        if actual_id != clause_id:
            _fail(
                f"{path}.clause_id",
                f"must equal canonical position {clause_id}",
            )
        variables = _require_array(clause["variables"], f"{path}.variables")
        if len(variables) != 3:
            _fail(f"{path}.variables", "must preserve exactly three positions")
        for position, raw_variable in enumerate(variables):
            variable = _require_integer(
                raw_variable,
                f"{path}.variables[{position}]",
                nonnegative=True,
            )
            if variable >= variable_count:
                _fail(
                    f"{path}.variables[{position}]",
                    "is outside the canonical variable domain",
                )
            occurrences[variable] += 1
    if any(count != 3 for count in occurrences):
        _fail("$.clauses", "every variable must occur exactly three times")


def validate_tileset_snapshot(document: object) -> None:
    """Validate one canonical square-tileset snapshot."""
    root = _require_object(document, "$")
    _require_exact_fields(
        root,
        frozenset({"schema", "geometry", "directions", "colors", "tiles"}),
        "$",
    )
    _require_literal(root["schema"], TILESET_SCHEMA, "$.schema")
    _require_literal(root["geometry"], GEOMETRY, "$.geometry")

    directions = _require_array(root["directions"], "$.directions")
    if directions != list(DIRECTIONS):
        _fail("$.directions", f"must equal {list(DIRECTIONS)!r}")

    colors = _require_array(root["colors"], "$.colors")
    checked_colors = [
        _require_integer(color, f"$.colors[{index}]", nonnegative=True)
        for index, color in enumerate(colors)
    ]
    if not checked_colors:
        _fail("$.colors", "must not be empty")
    if checked_colors != sorted(set(checked_colors)):
        _fail("$.colors", "must be strictly increasing and unique")

    tiles = _require_array(root["tiles"], "$.tiles")
    if not tiles:
        _fail("$.tiles", "must not be empty")
    used_colors: set[int] = set()
    for expected_id, raw_tile in enumerate(tiles):
        path = f"$.tiles[{expected_id}]"
        tile = _require_object(raw_tile, path)
        _require_exact_fields(tile, frozenset({"tile_id", "edges"}), path)
        tile_id = _require_integer(
            tile["tile_id"],
            f"{path}.tile_id",
            nonnegative=True,
        )
        if tile_id != expected_id:
            _fail(
                f"{path}.tile_id",
                f"must equal canonical table position {expected_id}",
            )
        used_colors.update(
            _validate_edges(
                tile["edges"],
                f"{path}.edges",
                optional=False,
            )
        )
    if checked_colors != sorted(used_colors):
        _fail("$.colors", "must equal exactly the colors used by the tile table")


def validate_region_snapshot(document: object) -> None:
    """Validate square-region geometry and exposed boundary constraints."""
    root = _require_object(document, "$")
    _require_exact_fields(
        root,
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
        "$",
    )
    _require_literal(root["schema"], REGION_SCHEMA, "$.schema")
    _require_literal(root["geometry"], GEOMETRY, "$.geometry")
    _require_sha256(root["source_formula_sha256"], "$.source_formula_sha256")

    bounds = _require_object(root["bounds"], "$.bounds")
    bound_fields = frozenset(
        {
            "min_x_inclusive",
            "min_y_inclusive",
            "max_x_inclusive",
            "max_y_inclusive",
        }
    )
    _require_exact_fields(bounds, bound_fields, "$.bounds")
    min_x = _require_integer(
        bounds["min_x_inclusive"],
        "$.bounds.min_x_inclusive",
        nonnegative=False,
    )
    min_y = _require_integer(
        bounds["min_y_inclusive"],
        "$.bounds.min_y_inclusive",
        nonnegative=False,
    )
    max_x = _require_integer(
        bounds["max_x_inclusive"],
        "$.bounds.max_x_inclusive",
        nonnegative=False,
    )
    max_y = _require_integer(
        bounds["max_y_inclusive"],
        "$.bounds.max_y_inclusive",
        nonnegative=False,
    )
    if max_x < min_x or max_y < min_y:
        _fail("$.bounds", "inclusive maxima must not precede minima")
    width = max_x - min_x + 1
    height = max_y - min_y + 1
    area = width * height

    active = _require_array(root["active"], "$.active")
    boundary = _require_array(root["boundary"], "$.boundary")
    if len(active) != area:
        _fail("$.active", f"length must equal inclusive bounds area {area}")
    if len(boundary) != area:
        _fail("$.boundary", f"length must equal inclusive bounds area {area}")
    if any(type(value) is not bool for value in active):
        _fail("$.active", "must contain only booleans")
    if not any(active):
        _fail("$.active", "must contain at least one active cell")

    checked_boundary: list[
        tuple[int | None, int | None, int | None, int | None] | None
    ] = []
    for index, raw_sides in enumerate(boundary):
        if not active[index]:
            if raw_sides is not None:
                _fail(
                    f"$.boundary[{index}]",
                    "must be null for an inactive position",
                )
            checked_boundary.append(None)
            continue
        if raw_sides is None:
            _fail(
                f"$.boundary[{index}]",
                "must contain N/E/S/W entries for an active cell",
            )
        checked_boundary.append(
            _validate_edges(
                raw_sides,
                f"$.boundary[{index}]",
                optional=True,
            )
        )

    for index, is_active in enumerate(active):
        if not is_active:
            continue
        sides = checked_boundary[index]
        assert sides is not None
        x = index % width
        y = index // width
        for direction, (dx, dy) in enumerate(_OFFSETS):
            neighbor_x = x + dx
            neighbor_y = y + dy
            neighbor_active = False
            if 0 <= neighbor_x < width and 0 <= neighbor_y < height:
                neighbor_active = active[neighbor_y * width + neighbor_x]
            if neighbor_active and sides[direction] is not None:
                _fail(
                    f"$.boundary[{index}].{DIRECTIONS[direction]}",
                    "must be null on an edge shared by active cells",
                )


def _validate_reference(
    value: object,
    path: str,
    *,
    expected_schema: str,
) -> tuple[str, str]:
    reference = _require_object(value, path)
    _require_exact_fields(
        reference,
        frozenset({"path", "sha256", "schema"}),
        path,
    )
    name = _require_artifact_name(reference["path"], f"{path}.path")
    digest = _require_sha256(reference["sha256"], f"{path}.sha256")
    _require_literal(reference["schema"], expected_schema, f"{path}.schema")
    return name, digest


def validate_explain_manifest(document: object) -> None:
    """Validate the closed manifest structure without loading artifacts."""
    root = _require_object(document, "$")
    _require_exact_fields(
        root,
        frozenset({"schema", "stage", "source_formula_sha256", "artifacts"}),
        "$",
    )
    _require_literal(root["schema"], MANIFEST_SCHEMA, "$.schema")
    _require_literal(root["stage"], STAGE, "$.stage")
    _require_sha256(root["source_formula_sha256"], "$.source_formula_sha256")
    artifacts = _require_object(root["artifacts"], "$.artifacts")
    _require_exact_fields(
        artifacts,
        frozenset({"formula", "tileset", "region"}),
        "$.artifacts",
    )
    for name, schema in (
        ("formula", FORMULA_SCHEMA),
        ("tileset", TILESET_SCHEMA),
        ("region", REGION_SCHEMA),
    ):
        _validate_reference(
            artifacts[name],
            f"$.artifacts.{name}",
            expected_schema=schema,
        )


def _reject_duplicate_members(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise PipelineSnapshotError(
                f"JSON object contains duplicate member {key!r}"
            )
        result[key] = value
    return result


def _reject_nonfinite_constant(value: str) -> None:
    raise PipelineSnapshotError(
        f"JSON document contains non-finite number {value}"
    )


def _load_json_bytes(encoded: bytes, label: str) -> dict[str, object]:
    try:
        decoded = encoded.decode("utf-8")
    except UnicodeDecodeError as error:
        raise PipelineSnapshotError(f"{label}: is not valid UTF-8") from error
    try:
        document = json.loads(
            decoded,
            object_pairs_hook=_reject_duplicate_members,
            parse_constant=_reject_nonfinite_constant,
        )
    except json.JSONDecodeError as error:
        raise PipelineSnapshotError(
            f"{label}: invalid JSON at line {error.lineno}, "
            f"column {error.colno}: {error.msg}"
        ) from error
    except (ValueError, RecursionError) as error:
        if isinstance(error, PipelineSnapshotError):
            raise
        raise PipelineSnapshotError(f"{label}: invalid JSON value: {error}") from error
    return _require_object(document, label)


def load_pipeline_snapshot(path: str | Path) -> dict[str, object]:
    """Strictly load and validate any static snapshot document."""
    source = Path(path)
    try:
        encoded = source.read_bytes()
    except OSError as error:
        raise PipelineSnapshotError(
            f"cannot read snapshot {source!s}: {error}"
        ) from error
    document = _load_json_bytes(encoded, str(source))
    schema = document.get("schema")
    if type(schema) is not str:
        _fail("$.schema", "must be a string")
    validators = {
        FORMULA_SCHEMA: validate_formula_snapshot,
        TILESET_SCHEMA: validate_tileset_snapshot,
        REGION_SCHEMA: validate_region_snapshot,
        MANIFEST_SCHEMA: validate_explain_manifest,
    }
    validator = validators.get(schema)
    if validator is None:
        _fail("$.schema", "is not a supported static snapshot schema")
    validator(document)
    return document


def load_explainability_bundle(
    manifest_path: str | Path,
) -> tuple[
    dict[str, object],
    dict[str, object],
    dict[str, object],
    dict[str, object],
]:
    """Load a manifest and its three hash-bound artifacts."""
    path = Path(manifest_path)
    manifest = load_pipeline_snapshot(path)
    if manifest["schema"] != MANIFEST_SCHEMA:
        _fail("$.schema", f"must equal {MANIFEST_SCHEMA!r}")
    artifacts = _require_object(manifest["artifacts"], "$.artifacts")
    loaded: dict[str, dict[str, object]] = {}
    for name, schema in (
        ("formula", FORMULA_SCHEMA),
        ("tileset", TILESET_SCHEMA),
        ("region", REGION_SCHEMA),
    ):
        reference = _require_object(artifacts[name], f"$.artifacts.{name}")
        artifact_name, expected_digest = _validate_reference(
            reference,
            f"$.artifacts.{name}",
            expected_schema=schema,
        )
        artifact_path = path.parent / artifact_name
        try:
            encoded = artifact_path.read_bytes()
        except OSError as error:
            raise PipelineSnapshotError(
                f"cannot read {name} artifact {artifact_path!s}: {error}"
            ) from error
        actual_digest = hashlib.sha256(encoded).hexdigest()
        if actual_digest != expected_digest:
            _fail(
                f"$.artifacts.{name}.sha256",
                f"does not match {artifact_name}",
            )
        document = _load_json_bytes(encoded, str(artifact_path))
        if document.get("schema") != schema:
            _fail(f"$.artifacts.{name}.schema", "does not match artifact")
        {
            FORMULA_SCHEMA: validate_formula_snapshot,
            TILESET_SCHEMA: validate_tileset_snapshot,
            REGION_SCHEMA: validate_region_snapshot,
        }[schema](document)
        loaded[name] = document

    formula = loaded["formula"]
    region = loaded["region"]
    tileset = loaded["tileset"]
    formula_source = _require_object(formula["source"], "formula.source")
    source_digest = _require_sha256(
        manifest["source_formula_sha256"],
        "$.source_formula_sha256",
    )
    if formula_source["sha256"] != source_digest:
        _fail("$.source_formula_sha256", "does not match formula artifact")
    if region["source_formula_sha256"] != source_digest:
        _fail("$.source_formula_sha256", "does not match region artifact")

    colors = set(_require_array(tileset["colors"], "tileset.colors"))
    for index, raw_sides in enumerate(
        _require_array(region["boundary"], "region.boundary")
    ):
        if raw_sides is None:
            continue
        sides = _require_object(raw_sides, f"region.boundary[{index}]")
        for direction in DIRECTIONS:
            color = sides[direction]
            if color is not None and color not in colors:
                _fail(
                    f"region.boundary[{index}].{direction}",
                    "is absent from the referenced tileset color set",
                )
    return manifest, formula, tileset, region


def build_formula_snapshot(
    formula: Formula,
    *,
    source_name: str,
    source_sha256: str,
) -> dict[str, object]:
    """Build one parsed-formula snapshot from an immutable model."""
    if not isinstance(formula, Formula):
        raise TypeError("formula must be a Formula")
    _require_artifact_name(source_name, "source_name")
    _require_sha256(source_sha256, "source_sha256")
    document: dict[str, object] = {
        "schema": FORMULA_SCHEMA,
        "source": {"name": source_name, "sha256": source_sha256},
        "variable_count": formula.variable_count,
        "clauses": [
            {"clause_id": clause_id, "variables": list(clause)}
            for clause_id, clause in enumerate(formula.clauses)
        ],
    }
    validate_formula_snapshot(document)
    return document


def build_tileset_snapshot(
    tileset: Tileset = TILESET,
) -> dict[str, object]:
    """Build one positional square-tileset snapshot."""
    if type(tileset) is not tuple or not tileset:
        raise TypeError("tileset must be a nonempty tuple")
    if any(
        type(tile) is not tuple
        or len(tile) != len(DIRECTIONS)
        or any(type(color) is not int or color < 0 for color in tile)
        for tile in tileset
    ):
        raise TypeError(
            "every tile must be an immutable N/E/S/W tuple of "
            "nonnegative integer colors"
        )
    document: dict[str, object] = {
        "schema": TILESET_SCHEMA,
        "geometry": GEOMETRY,
        "directions": list(DIRECTIONS),
        "colors": sorted({color for tile in tileset for color in tile}),
        "tiles": [
            {
                "tile_id": tile_id,
                "edges": {
                    direction: tile[direction_index]
                    for direction_index, direction in enumerate(DIRECTIONS)
                },
            }
            for tile_id, tile in enumerate(tileset)
        ],
    }
    validate_tileset_snapshot(document)
    return document


def build_region_snapshot(
    region: Region,
    *,
    source_formula_sha256: str,
    origin: tuple[int, int] = (0, 0),
) -> dict[str, object]:
    """Build one unassigned square-region snapshot."""
    if not isinstance(region, Region):
        raise TypeError("region must be a Region")
    _require_sha256(source_formula_sha256, "source_formula_sha256")
    if (
        type(origin) is not tuple
        or len(origin) != 2
        or any(type(coordinate) is not int for coordinate in origin)
    ):
        raise PipelineSnapshotError(
            "origin must be an immutable pair of integer coordinates"
        )
    min_x, min_y = origin
    boundary = [
        None
        if not active
        else {
            direction: None if color == COLOR_NONE else color
            for direction, color in zip(DIRECTIONS, sides, strict=True)
        }
        for active, sides in zip(region.active, region.boundary, strict=True)
    ]
    document: dict[str, object] = {
        "schema": REGION_SCHEMA,
        "geometry": GEOMETRY,
        "source_formula_sha256": source_formula_sha256,
        "bounds": {
            "min_x_inclusive": min_x,
            "min_y_inclusive": min_y,
            "max_x_inclusive": min_x + region.width - 1,
            "max_y_inclusive": min_y + region.height - 1,
        },
        "active": list(region.active),
        "boundary": boundary,
    }
    validate_region_snapshot(document)
    return document


def _encode_document(document: dict[str, object]) -> bytes:
    serialized = json.dumps(
        document,
        ensure_ascii=False,
        allow_nan=False,
        indent=2,
    )
    return f"{serialized}\n".encode("utf-8")


def _write_atomic(path: Path, encoded: bytes) -> None:
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
            stream.write(encoded)
        os.replace(temporary, path)
        temporary = None
    except OSError as error:
        raise PipelineSnapshotError(
            f"cannot install snapshot {path!s}: {error}"
        ) from error
    finally:
        if temporary is not None:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass


def dump_pipeline_snapshots(
    manifest_path: str | Path,
    source_path: str | Path,
    formula: Formula,
    region: Region,
    *,
    origin: tuple[int, int] = (0, 0),
) -> Path:
    """Write content-addressed artifacts, then atomically install a manifest."""
    destination = Path(manifest_path)
    source = Path(source_path)
    try:
        source_bytes = source.read_bytes()
    except OSError as error:
        raise PipelineSnapshotError(
            f"cannot read formula source {source!s}: {error}"
        ) from error
    source_digest = hashlib.sha256(source_bytes).hexdigest()
    formula_document = build_formula_snapshot(
        formula,
        source_name=source.name,
        source_sha256=source_digest,
    )
    tileset_document = build_tileset_snapshot()
    region_document = build_region_snapshot(
        region,
        source_formula_sha256=source_digest,
        origin=origin,
    )
    documents = {
        "formula": (FORMULA_SCHEMA, formula_document),
        "tileset": (TILESET_SCHEMA, tileset_document),
        "region": (REGION_SCHEMA, region_document),
    }
    references: dict[str, object] = {}
    for name, (schema, document) in documents.items():
        encoded = _encode_document(document)
        digest = hashlib.sha256(encoded).hexdigest()
        artifact_name = f"{name}-{digest}.json"
        if artifact_name == destination.name:
            raise PipelineSnapshotError(
                "manifest filename must not collide with a generated "
                f"artifact: {artifact_name}"
            )
        artifact_path = destination.parent / artifact_name
        _write_atomic(artifact_path, encoded)
        references[name] = {
            "path": artifact_name,
            "sha256": digest,
            "schema": schema,
        }

    manifest: dict[str, object] = {
        "schema": MANIFEST_SCHEMA,
        "stage": STAGE,
        "source_formula_sha256": source_digest,
        "artifacts": references,
    }
    validate_explain_manifest(manifest)
    _write_atomic(destination, _encode_document(manifest))
    load_explainability_bundle(destination)
    return destination
