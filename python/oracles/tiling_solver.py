"""Independent Wang-tiling Z3 oracle over the pure Python Region model."""

from z3 import And, ArithRef, Int, Or, Solver, sat, unsat

from model.region import Region
from model.tiling import TilingSolveResult, TilingSolveStatus
from model.tileset import (
    COLOR_COUNT,
    COLOR_NONE,
    DIR_COUNT,
    E,
    S,
    Tile,
    Tileset,
)


def _validate_tileset(tileset: Tileset) -> None:
    if type(tileset) is not tuple:
        raise TypeError("tileset must be a tuple")
    if not tileset:
        raise ValueError("tileset must contain at least one tile")

    for tile in tileset:
        if type(tile) is not tuple or len(tile) != DIR_COUNT:
            raise ValueError("each tile must contain four immutable edges")
        if any(
            type(color) is not int or not 0 <= color < COLOR_COUNT
            for color in tile
        ):
            raise ValueError("tile contains an invalid color")


def _edge_terms(
    region: Region,
) -> tuple[tuple[ArithRef, ArithRef, ArithRef, ArithRef] | None, ...]:
    """Create one color term per exposed edge and share every internal edge."""
    terms: list[
        tuple[ArithRef, ArithRef, ArithRef, ArithRef] | None
    ] = [None] * len(region.active)

    for y in range(region.height):
        for x in range(region.width):
            index = y * region.width + x
            if not region.active[index]:
                continue

            above = terms[index - region.width] if y > 0 else None
            left = terms[index - 1] if x > 0 else None
            north = above[S] if above is not None else Int(f"edge_{index}_n")
            west = left[E] if left is not None else Int(f"edge_{index}_w")
            terms[index] = (
                north,
                Int(f"edge_{index}_e"),
                Int(f"edge_{index}_s"),
                west,
            )

    return tuple(terms)


def solve_tiling(region: Region, tileset: Tileset) -> TilingSolveResult:
    """Solve an existing region without parsing or rebuilding its reduction.

    Each cell is constrained to one tileset edge tuple and adjacent cells
    share their internal edge-color term. SAT returns one dense row-major tile
    ID per active cell and ``None`` for inactive cells; UNSAT and UNKNOWN
    return no tiling. Duplicate edge tuples remain valid, constraint-equivalent
    tile IDs.
    """
    _validate_tileset(tileset)

    solver = Solver()
    edges = _edge_terms(region)
    tile_id_by_edges: dict[Tile, int] = {}
    for tile_id, tile in enumerate(tileset):
        tile_id_by_edges.setdefault(tile, tile_id)

    for index, cell_edges in enumerate(edges):
        if cell_edges is None:
            continue

        solver.add(
            Or(
                *(
                    And(
                        *(
                            cell_edges[direction] == color
                            for direction, color in enumerate(tile)
                        ),
                    )
                    for tile in tile_id_by_edges
                )
            )
        )
        for direction, required_color in enumerate(region.boundary[index]):
            if required_color != COLOR_NONE:
                solver.add(cell_edges[direction] == required_color)

    status = solver.check()
    if status == sat:
        model = solver.model()
        tiling = tuple(
            None
            if cell_edges is None
            else tile_id_by_edges[
                tuple(
                    model.eval(edge, model_completion=True).as_long()
                    for edge in cell_edges
                )
            ]
            for cell_edges in edges
        )
        return TilingSolveResult(TilingSolveStatus.SAT, tiling)

    if status == unsat:
        return TilingSolveResult(TilingSolveStatus.UNSAT)

    return TilingSolveResult(TilingSolveStatus.UNKNOWN)
