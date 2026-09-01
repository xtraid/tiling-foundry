"""Pure semantic model for the fixed Yang--Zhang generalized tiles.

The solver and the square solution contract expose only the 23 positional
atomic tile IDs.  This module is a presentation-only interpretation of those
IDs: it guards the exact canonical edge table and recognizes the 14 fixed
generalized shapes from ID, orientation, part adjacency, and complete
composition.
It deliberately imports no raster, solver, native, or root-project module.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final


class GeneralizedTileError(ValueError):
    """Raised when an atomic table or generalized composition is not exact."""


@dataclass(frozen=True, slots=True)
class AtomicPart:
    tile_id: int
    dx: int
    dy: int
    label: str


@dataclass(frozen=True, slots=True)
class GeneralizedTile:
    name: str
    parts: tuple[AtomicPart, ...]

    @property
    def width(self) -> int:
        return max(part.dx for part in self.parts) + 1

    @property
    def height(self) -> int:
        return max(part.dy for part in self.parts) + 1


@dataclass(frozen=True, slots=True)
class GeneralizedInstance:
    kind: str
    origin_x: int
    origin_y: int


PAPER_COLOR_NAMES: Final[tuple[str, ...]] = (
    "b",
    "v",
    "0",
    "1",
    "0-prime",
    "l",
    "r",
)
INTERNAL_COLOR_NAMES: Final[tuple[str, ...]] = (
    "V0:a",
    "V0:b",
    "C1",
    "R0",
    "R1",
    "X00",
    "X01",
    "X10",
    "X11",
)
COLOR_NAMES: Final[tuple[str, ...]] = PAPER_COLOR_NAMES + INTERNAL_COLOR_NAMES

# Tuple position is the immutable atomic tile ID; edges are N, E, S, W.
CANONICAL_ATOMIC_TILE_EDGES: Final[
    tuple[tuple[int, int, int, int], ...]
] = (
    (0, 2, 7, 1),
    (7, 2, 8, 1),
    (8, 2, 0, 1),
    (0, 3, 0, 1),
    (0, 4, 0, 2),
    (0, 4, 9, 3),
    (9, 3, 0, 2),
    (0, 2, 0, 2),
    (0, 3, 0, 3),
    (5, 2, 5, 2),
    (5, 3, 5, 3),
    (0, 10, 6, 2),
    (6, 2, 0, 10),
    (0, 11, 6, 3),
    (6, 3, 0, 11),
    (6, 2, 12, 2),
    (12, 2, 5, 2),
    (6, 2, 13, 3),
    (13, 3, 5, 2),
    (6, 3, 14, 2),
    (14, 2, 5, 3),
    (6, 3, 15, 3),
    (15, 3, 5, 3),
)

GENERALIZED_TILES: Final[tuple[GeneralizedTile, ...]] = (
    GeneralizedTile(
        "V0",
        (
            AtomicPart(0, 0, 0, "top"),
            AtomicPart(1, 0, 1, "middle"),
            AtomicPart(2, 0, 2, "bottom"),
        ),
    ),
    GeneralizedTile("V1", (AtomicPart(3, 0, 0, "copy"),)),
    GeneralizedTile("C0", (AtomicPart(4, 0, 0, "single"),)),
    GeneralizedTile(
        "C1",
        (AtomicPart(5, 0, 0, "top"), AtomicPart(6, 0, 1, "bottom")),
    ),
    GeneralizedTile("F0", (AtomicPart(7, 0, 0, "single"),)),
    GeneralizedTile("F1", (AtomicPart(8, 0, 0, "single"),)),
    GeneralizedTile("L0", (AtomicPart(9, 0, 0, "single"),)),
    GeneralizedTile("L1", (AtomicPart(10, 0, 0, "single"),)),
    GeneralizedTile(
        "R0",
        (AtomicPart(11, 0, 0, "left"), AtomicPart(12, 1, 0, "right")),
    ),
    GeneralizedTile(
        "R1",
        (AtomicPart(13, 0, 0, "left"), AtomicPart(14, 1, 0, "right")),
    ),
    GeneralizedTile(
        "X00",
        (AtomicPart(15, 0, 0, "top"), AtomicPart(16, 0, 1, "bottom")),
    ),
    GeneralizedTile(
        "X01",
        (AtomicPart(17, 0, 0, "top"), AtomicPart(18, 0, 1, "bottom")),
    ),
    GeneralizedTile(
        "X10",
        (AtomicPart(19, 0, 0, "top"), AtomicPart(20, 0, 1, "bottom")),
    ),
    GeneralizedTile(
        "X11",
        (AtomicPart(21, 0, 0, "top"), AtomicPart(22, 0, 1, "bottom")),
    ),
)

_GENERALIZED_BY_NAME: Final = {tile.name: tile for tile in GENERALIZED_TILES}
_GENERALIZED_ORDER: Final = {
    tile.name: index for index, tile in enumerate(GENERALIZED_TILES)
}
_PART_BY_TILE_ID: Final = {
    part.tile_id: (tile, part)
    for tile in GENERALIZED_TILES
    for part in tile.parts
}


def _validate_fixed_specification() -> None:
    if len(GENERALIZED_TILES) != 14:
        raise RuntimeError("generalized table must contain exactly 14 tiles")
    if len(CANONICAL_ATOMIC_TILE_EDGES) != 23:
        raise RuntimeError("atomic table must contain exactly 23 tiles")
    if len(COLOR_NAMES) != 16:
        raise RuntimeError("color vocabulary must contain exactly 16 colors")
    if len(_GENERALIZED_BY_NAME) != len(GENERALIZED_TILES):
        raise RuntimeError("generalized names must be unique")
    if set(_PART_BY_TILE_ID) != set(range(23)):
        raise RuntimeError("generalized parts must partition atomic IDs 0..22")
    for tile in GENERALIZED_TILES:
        coordinates = {(part.dx, part.dy) for part in tile.parts}
        if len(coordinates) != len(tile.parts):
            raise RuntimeError(f"{tile.name} contains duplicate part coordinates")


_validate_fixed_specification()


def color_label(color_id: int) -> str:
    """Return the symbolic paper/glue name with the numeric ID secondary."""
    if type(color_id) is not int or not 0 <= color_id < len(COLOR_NAMES):
        raise GeneralizedTileError(f"invalid canonical color ID {color_id!r}")
    return f"{COLOR_NAMES[color_id]} [{color_id}]"


def atomic_semantic_label(tile_id: int) -> str:
    """Return the generalized name and part role for one positional ID."""
    if type(tile_id) is not int or tile_id not in _PART_BY_TILE_ID:
        raise GeneralizedTileError(f"invalid canonical atomic tile ID {tile_id!r}")
    tile, part = _PART_BY_TILE_ID[tile_id]
    if len(tile.parts) == 1:
        return tile.name
    return f"{tile.name} {part.label}"


def check_canonical_atomic_tileset(
    tile_edges: Sequence[Sequence[int]],
) -> None:
    """Require the exact positional 23-tile table, including orientation."""
    if isinstance(tile_edges, (str, bytes)):
        raise GeneralizedTileError("atomic tile table must be a sequence")
    if len(tile_edges) != len(CANONICAL_ATOMIC_TILE_EDGES):
        raise GeneralizedTileError(
            "atomic tile table must contain exactly 23 positional entries"
        )
    for tile_id, (actual, expected) in enumerate(
        zip(tile_edges, CANONICAL_ATOMIC_TILE_EDGES, strict=True)
    ):
        if isinstance(actual, (str, bytes)) or len(actual) != 4:
            raise GeneralizedTileError(
                f"atomic tile {tile_id} must contain four N/E/S/W edges"
            )
        checked = tuple(actual)
        if any(type(color) is not int for color in checked):
            raise GeneralizedTileError(
                f"atomic tile {tile_id} edges must be integer color IDs"
            )
        if checked != expected:
            raise GeneralizedTileError(
                f"atomic tile {tile_id} does not match the canonical "
                f"N/E/S/W orientation: expected {expected}, got {checked}"
            )


def _check_grid(
    cells: Sequence[int | None],
    min_x: int,
    min_y: int,
    max_x: int,
    max_y: int,
) -> int:
    for name, value in (
        ("min_x", min_x),
        ("min_y", min_y),
        ("max_x", max_x),
        ("max_y", max_y),
    ):
        if type(value) is not int:
            raise GeneralizedTileError(f"{name} must be an integer")
    if max_x < min_x or max_y < min_y:
        raise GeneralizedTileError("generalized grid bounds must be nonempty")
    width = max_x - min_x + 1
    area = width * (max_y - min_y + 1)
    if isinstance(cells, (str, bytes)) or len(cells) != area:
        raise GeneralizedTileError(
            f"generalized grid must contain exactly {area} dense cells"
        )
    for index, tile_id in enumerate(cells):
        if tile_id is None:
            continue
        if type(tile_id) is not int or tile_id not in _PART_BY_TILE_ID:
            raise GeneralizedTileError(
                f"generalized grid cell {index} has invalid tile ID {tile_id!r}"
            )
    return width


def _cell_at(
    cells: Sequence[int | None],
    width: int,
    min_x: int,
    min_y: int,
    max_x: int,
    max_y: int,
    x: int,
    y: int,
) -> int | None:
    if x < min_x or x > max_x or y < min_y or y > max_y:
        return None
    return cells[(y - min_y) * width + (x - min_x)]


def check_generalized_instances(
    tile_edges: Sequence[Sequence[int]],
    cells: Sequence[int | None],
    *,
    min_x: int,
    min_y: int,
    max_x: int,
    max_y: int,
    instances: Sequence[GeneralizedInstance],
) -> None:
    """Check exact composition, non-overlap, and complete active coverage."""
    check_canonical_atomic_tileset(tile_edges)
    width = _check_grid(cells, min_x, min_y, max_x, max_y)
    if isinstance(instances, (str, bytes)):
        raise GeneralizedTileError("generalized instances must be a sequence")

    covered: dict[tuple[int, int], int] = {}
    for instance_index, instance in enumerate(instances):
        if not isinstance(instance, GeneralizedInstance):
            raise GeneralizedTileError(
                f"generalized instance {instance_index} has an invalid type"
            )
        tile = _GENERALIZED_BY_NAME.get(instance.kind)
        if tile is None:
            raise GeneralizedTileError(
                f"generalized instance {instance_index} has unknown kind "
                f"{instance.kind!r}"
            )
        if type(instance.origin_x) is not int or type(instance.origin_y) is not int:
            raise GeneralizedTileError(
                f"generalized instance {instance_index} origin must be integral"
            )
        for part in tile.parts:
            x = instance.origin_x + part.dx
            y = instance.origin_y + part.dy
            actual = _cell_at(
                cells, width, min_x, min_y, max_x, max_y, x, y
            )
            if actual != part.tile_id:
                raise GeneralizedTileError(
                    f"incomplete or misoriented {tile.name} at "
                    f"({instance.origin_x},{instance.origin_y}): expected "
                    f"atomic tile {part.tile_id} at ({x},{y}), got {actual!r}"
                )
            coordinate = (x, y)
            previous = covered.get(coordinate)
            if previous is not None:
                raise GeneralizedTileError(
                    f"generalized instances {previous} and {instance_index} "
                    f"overlap at ({x},{y})"
                )
            covered[coordinate] = instance_index

    active = {
        (min_x + index % width, min_y + index // width)
        for index, tile_id in enumerate(cells)
        if tile_id is not None
    }
    missing = sorted(active - set(covered), key=lambda item: (item[1], item[0]))
    if missing:
        x, y = missing[0]
        raise GeneralizedTileError(
            f"generalized recognition leaves active cell ({x},{y}) uncovered"
        )
    extra = set(covered) - active
    if extra:
        x, y = min(extra, key=lambda item: (item[1], item[0]))
        raise GeneralizedTileError(
            f"generalized recognition covers inactive cell ({x},{y})"
        )


def recognize_generalized_tiles(
    tile_edges: Sequence[Sequence[int]],
    cells: Sequence[int | None],
    *,
    min_x: int,
    min_y: int,
    max_x: int,
    max_y: int,
) -> tuple[GeneralizedInstance, ...]:
    """Recognize the unique complete generalized partition of a square witness."""
    check_canonical_atomic_tileset(tile_edges)
    width = _check_grid(cells, min_x, min_y, max_x, max_y)
    candidates: set[tuple[str, int, int]] = set()
    for index, tile_id in enumerate(cells):
        if tile_id is None:
            continue
        tile, part = _PART_BY_TILE_ID[tile_id]
        x = min_x + index % width
        y = min_y + index // width
        candidates.add((tile.name, x - part.dx, y - part.dy))

    instances = tuple(
        GeneralizedInstance(kind, origin_x, origin_y)
        for kind, origin_x, origin_y in sorted(
            candidates,
            key=lambda item: (
                item[2],
                item[1],
                _GENERALIZED_ORDER[item[0]],
            ),
        )
    )
    check_generalized_instances(
        tile_edges,
        cells,
        min_x=min_x,
        min_y=min_y,
        max_x=max_x,
        max_y=max_y,
        instances=instances,
    )
    return instances


def generalized_tile(kind: str) -> GeneralizedTile:
    """Return one immutable canonical generalized specification by name."""
    tile = _GENERALIZED_BY_NAME.get(kind)
    if tile is None:
        raise GeneralizedTileError(f"unknown generalized tile {kind!r}")
    return tile
