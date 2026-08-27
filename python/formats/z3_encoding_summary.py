"""Closed summaries of the project-owned Z3 encoding order and one result."""

from __future__ import annotations

from typing import Final

from z3 import is_true, sat, unsat

from formats.pipeline_snapshot import (
    PipelineSnapshotError,
    _require_array,
    _require_exact_fields,
    _require_integer,
    _require_literal,
    _require_object,
    _require_sha256,
    _require_string,
)
from model.formula import Formula
from model.region import Region
from model.tileset import COLOR_NONE, TILESET
from oracles.boolean_solver import _encode_boolean
from oracles.tiling_solver import _encode_tiling
from oracles.z3_config import Z3_RANDOM_SEED, Z3_THREADS, z3_configuration


SCHEMA_NAME: Final = "z3-encoding-summary-v1"
SEMANTICS: Final = "encoding-order"
BOOLEAN_ENGINE: Final = "boolean-z3"
WANG_ENGINE: Final = "wang-z3"
ENGINES: Final = frozenset({BOOLEAN_ENGINE, WANG_ENGINE})
STATUSES: Final = frozenset({"sat", "unsat", "unknown"})
WANG_TILE_COUNT: Final = len(TILESET)
BOOLEAN_ORDER: Final = (
    "variables:ascending-id",
    "clauses:source-order",
    "clause-positions:left-to-right",
)
WANG_ORDER: Final = (
    "cells:row-major",
    "directions:N,E,S,W",
    "tile-tuples:first-positional-id",
    "cell-relation-before-boundary",
    "boundary-directions:N,E,S,W",
)
def _fail(path: str, message: str) -> None:
    raise PipelineSnapshotError(f"{path}: {message}")


def _require_nullable_sha256(value: object, path: str) -> str | None:
    if value is None:
        return None
    return _require_sha256(value, path)


def _status_name(status: object) -> str:
    if status == sat:
        return "sat"
    if status == unsat:
        return "unsat"
    return "unknown"


def validate_z3_encoding_summary(document: object) -> None:
    """Validate the closed transport and engine-specific cross fields."""
    root = _require_object(document, "$")
    _require_exact_fields(
        root,
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
    _require_literal(root["schema"], SCHEMA_NAME, "$.schema")
    _require_literal(root["semantics"], SEMANTICS, "$.semantics")
    engine = _require_string(root["engine"], "$.engine")
    if engine not in ENGINES:
        _fail("$.engine", "is not a supported encoding engine")
    _require_sha256(root["source_formula_sha256"], "$.source_formula_sha256")
    region_digest = _require_nullable_sha256(root["region_sha256"], "$.region_sha256")
    if (engine == WANG_ENGINE) != (region_digest is not None):
        _fail("$.region_sha256", "must be present exactly for Wang Z3")

    z3 = _require_object(root["z3"], "$.z3")
    _require_exact_fields(z3, frozenset({"version", "parameters"}), "$.z3")
    if not _require_string(z3["version"], "$.z3.version"):
        _fail("$.z3.version", "must not be empty")
    parameters = _require_object(z3["parameters"], "$.z3.parameters")
    _require_exact_fields(
        parameters,
        frozenset({"random_seed", "threads"}),
        "$.z3.parameters",
    )
    if _require_integer(
        parameters["random_seed"], "$.z3.parameters.random_seed", nonnegative=True
    ) != Z3_RANDOM_SEED:
        _fail("$.z3.parameters.random_seed", f"must equal {Z3_RANDOM_SEED}")
    if _require_integer(
        parameters["threads"], "$.z3.parameters.threads", nonnegative=True
    ) != Z3_THREADS:
        _fail("$.z3.parameters.threads", f"must equal {Z3_THREADS}")

    status = _require_string(root["status"], "$.status")
    if status not in STATUSES:
        _fail("$.status", "is not a supported Z3 result")
    encoding = _require_object(root["encoding"], "$.encoding")
    _require_exact_fields(
        encoding,
        frozenset(
            {
                "order",
                "variable_count",
                "width",
                "height",
                "active_cell_count",
                "edge_term_count",
                "shared_internal_edge_count",
                "unique_tile_tuple_count",
                "assertion_count",
            }
        ),
        "$.encoding",
    )
    order = tuple(
        _require_string(item, f"$.encoding.order[{index}]")
        for index, item in enumerate(
            _require_array(encoding["order"], "$.encoding.order")
        )
    )
    expected_order = BOOLEAN_ORDER if engine == BOOLEAN_ENGINE else WANG_ORDER
    if order != expected_order:
        _fail("$.encoding.order", "does not match the engine contract")
    counts = {
        name: _require_integer(
            encoding[name], f"$.encoding.{name}", nonnegative=True
        )
        for name in (
            "variable_count",
            "width",
            "height",
            "active_cell_count",
            "edge_term_count",
            "shared_internal_edge_count",
            "unique_tile_tuple_count",
            "assertion_count",
        )
    }
    if counts["variable_count"] == 0:
        _fail("$.encoding.variable_count", "must be positive")
    if engine == BOOLEAN_ENGINE and any(
        counts[name] != 0
        for name in (
            "active_cell_count",
            "width",
            "height",
            "edge_term_count",
            "shared_internal_edge_count",
            "unique_tile_tuple_count",
        )
    ):
        _fail("$.encoding", "Boolean Z3 must not publish Wang counts")
    if engine == WANG_ENGINE and (
        counts["width"] == 0
        or counts["height"] == 0
        or counts["active_cell_count"] == 0
        or counts["edge_term_count"] == 0
        or counts["unique_tile_tuple_count"] != WANG_TILE_COUNT
    ):
        _fail(
            "$.encoding",
            "Wang Z3 requires nonzero region counts and the canonical tile table",
        )
    if engine == WANG_ENGINE and (
        counts["active_cell_count"] > counts["width"] * counts["height"]
        or counts["edge_term_count"]
        != 4 * counts["active_cell_count"]
        - counts["shared_internal_edge_count"]
    ):
        _fail("$.encoding", "Wang Z3 edge accounting is inconsistent")

    model = _require_object(root["model"], "$.model")
    _require_exact_fields(model, frozenset({"assignment", "cells"}), "$.model")
    assignment = model["assignment"]
    cells = model["cells"]
    model_entry_count = 0
    if status == "sat" and engine == BOOLEAN_ENGINE:
        values = _require_array(assignment, "$.model.assignment")
        if len(values) != counts["variable_count"] or any(
            type(value) is not bool for value in values
        ):
            _fail("$.model.assignment", "must contain one boolean per variable")
        if cells is not None:
            _fail("$.model.cells", "must be null for Boolean Z3")
        model_entry_count = len(values)
    elif status == "sat":
        if assignment is not None:
            _fail("$.model.assignment", "must be null for Wang Z3")
        values = _require_array(cells, "$.model.cells")
        if len(values) != counts["width"] * counts["height"]:
            _fail("$.model.cells", "length must equal the Wang extent")
        active_model_cells = 0
        for index, tile_id in enumerate(values):
            if tile_id is not None:
                parsed_tile_id = _require_integer(
                    tile_id, f"$.model.cells[{index}]", nonnegative=True
                )
                if parsed_tile_id >= counts["unique_tile_tuple_count"]:
                    _fail(
                        f"$.model.cells[{index}]",
                        "is outside the canonical tile table",
                    )
                active_model_cells += 1
        if active_model_cells != counts["active_cell_count"]:
            _fail(
                "$.model.cells",
                "non-null entries must equal the active-cell count",
            )
        model_entry_count = len(values)
    elif assignment is not None or cells is not None:
        _fail("$.model", "non-SAT summaries must not publish a model")

    statistics = _require_array(root["statistics"], "$.statistics")
    parsed_statistics: list[tuple[str, int]] = []
    for index, raw in enumerate(statistics):
        path = f"$.statistics[{index}]"
        statistic = _require_object(raw, path)
        _require_exact_fields(statistic, frozenset({"name", "value"}), path)
        name = _require_string(statistic["name"], f"{path}.name")
        if not name:
            _fail(f"{path}.name", "must not be empty")
        value = _require_integer(
            statistic["value"], f"{path}.value", nonnegative=True
        )
        parsed_statistics.append((name, value))
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
    if parsed_statistics != expected_statistics:
        _fail("$.statistics", "must match the ordered project-owned counters")


def build_boolean_z3_summary(
    formula: Formula,
    *,
    source_formula_sha256: str,
) -> dict[str, object]:
    """Run the Boolean oracle once and summarize its explicit encoding."""
    _require_sha256(source_formula_sha256, "source_formula_sha256")
    solver, variables = _encode_boolean(formula)
    status = solver.check()
    assignment = None
    if status == sat:
        model = solver.model()
        assignment = [
            is_true(model.eval(variable, model_completion=True))
            for variable in variables
        ]
    document: dict[str, object] = {
        "schema": SCHEMA_NAME,
        "semantics": SEMANTICS,
        "engine": BOOLEAN_ENGINE,
        "source_formula_sha256": source_formula_sha256,
        "region_sha256": None,
        "z3": z3_configuration(),
        "status": _status_name(status),
        "encoding": {
            "order": list(BOOLEAN_ORDER),
            "variable_count": formula.variable_count,
            "width": 0,
            "height": 0,
            "active_cell_count": 0,
            "edge_term_count": 0,
            "shared_internal_edge_count": 0,
            "unique_tile_tuple_count": 0,
            "assertion_count": len(solver.assertions()),
        },
        "model": {"assignment": assignment, "cells": None},
        "statistics": [
            {"name": "variables", "value": formula.variable_count},
            {"name": "assertions", "value": len(solver.assertions())},
            {
                "name": "model-entries",
                "value": 0 if assignment is None else len(assignment),
            },
        ],
    }
    validate_z3_encoding_summary(document)
    return document


def build_wang_z3_summary(
    formula: Formula,
    region: Region,
    *,
    source_formula_sha256: str,
    region_sha256: str,
) -> dict[str, object]:
    """Run the edge-table oracle once and summarize its encoding and model."""
    _require_sha256(source_formula_sha256, "source_formula_sha256")
    _require_sha256(region_sha256, "region_sha256")
    solver, edges, tile_id_by_edges = _encode_tiling(region, TILESET)
    status = solver.check()
    cells = None
    if status == sat:
        model = solver.model()
        cells = [
            None
            if cell_edges is None
            else tile_id_by_edges[
                tuple(
                    model.eval(edge, model_completion=True).as_long()
                    for edge in cell_edges
                )
            ]
            for cell_edges in edges
        ]
    active_count = sum(region.active)
    shared_edges = 0
    boundary_constraints = 0
    for index, active in enumerate(region.active):
        if not active:
            continue
        x = index % region.width
        y = index // region.width
        if x + 1 < region.width and region.active[index + 1]:
            shared_edges += 1
        if y + 1 < region.height and region.active[index + region.width]:
            shared_edges += 1
        boundary_constraints += sum(
            color != COLOR_NONE for color in region.boundary[index]
        )
    edge_term_count = len(
        {
            edge.get_id()
            for cell_edges in edges
            if cell_edges is not None
            for edge in cell_edges
        }
    )
    document: dict[str, object] = {
        "schema": SCHEMA_NAME,
        "semantics": SEMANTICS,
        "engine": WANG_ENGINE,
        "source_formula_sha256": source_formula_sha256,
        "region_sha256": region_sha256,
        "z3": z3_configuration(),
        "status": _status_name(status),
        "encoding": {
            "order": list(WANG_ORDER),
            "variable_count": formula.variable_count,
            "width": region.width,
            "height": region.height,
            "active_cell_count": active_count,
            "edge_term_count": edge_term_count,
            "shared_internal_edge_count": shared_edges,
            "unique_tile_tuple_count": len(tile_id_by_edges),
            "assertion_count": active_count + boundary_constraints,
        },
        "model": {"assignment": None, "cells": cells},
        "statistics": [
            {"name": "active-cells", "value": active_count},
            {"name": "edge-terms", "value": edge_term_count},
            {"name": "shared-internal-edges", "value": shared_edges},
            {
                "name": "assertions",
                "value": active_count + boundary_constraints,
            },
            {
                "name": "model-entries",
                "value": 0 if cells is None else len(cells),
            },
        ],
    }
    if len(solver.assertions()) != active_count + boundary_constraints:
        raise PipelineSnapshotError("Wang Z3 assertion accounting diverged")
    validate_z3_encoding_summary(document)
    return document
