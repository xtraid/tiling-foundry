from .region import Region
from .tileset import TILESET, N, E, S, W, COLORS
from z3 import Solver, Int, And, Or, sat

def _edge_terms(region):
    supporto = [None for x in region.active]
    n = len(region.active)
    for i in range(n):
        if not region.active[i]:
            continue
        x = i % region.width
        y = i // region.width
        above = supporto[i -region.width] if y > 0 else None
        left = supporto[i -1] if x > 0 else None
        north = above[S] if above is not None else Int(f"edge_{i}_n")
        west = left[E] if left is not None else Int(f"edge_{i}_w")
        east = Int(f"edge_{i}_e")
        south = Int(f"edge_{i}_s")
        supporto[i] = (north,east,south,west)
    return supporto


def _extract_tiling(model, edges):
    tiled = []
    for i, tile in enumerate(edges):
        if tile is None:
            tiled.append(None) # after 2 year of coding in python still mistaking appeand for append 
            continue
        cell = edges[i]
        values = (
            model.eval(cell[N]).as_long(),
            model.eval(cell[E]).as_long(),
            model.eval(cell[S]).as_long(),
            model.eval(cell[W]).as_long(),
        )
        tile_colors = tuple(COLORS[x] for x in values)
        tile_id = TILESET.index(tile_colors)
        tiled.append(tile_id)
    return tiled




def solve(region):
    edges = _edge_terms(region)
    color_id = {color: i for i, color in enumerate(COLORS)}
    phi = Solver()
    for i in range(len(edges)):
        if edges[i] is None:
            continue
        possibilita = []
        for tile in TILESET:
            possibilita.append(And(
                edges[i][N]== color_id[tile[N]],
                edges[i][E]== color_id[tile[E]],
                edges[i][S]== color_id[tile[S]],
                edges[i][W]== color_id[tile[W]],
                )
            )
        phi.add(Or(possibilita))

        for d in range(4):
            if region.boundary[i][d] is not None:
                phi.add(edges[i][d]== color_id[region.boundary[i][d]])

    sol = phi.check() #magia nera
    if sol != sat:
        return sol
    return _extract_tiling(phi.model(), edges)

