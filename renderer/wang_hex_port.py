"""Pure square-to-hex presentation port for ``wang-solution-v1``.

The source document remains square-only.  This module changes neither the
solver domain nor the serialized contract: it maps the already selected tile
table, cells, coordinates, and boundary presentation into an in-memory
pointy-top axial view.  It deliberately has no NumPy, Pillow, solver, or native
library dependency.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final


SQUARE_DIRECTIONS: Final = ("N", "E", "S", "W")
HEX_DIRECTIONS: Final = ("E", "SE", "SW", "W", "NW", "NE")

_SQUARE_N: Final = 0
_SQUARE_E: Final = 1
_SQUARE_S: Final = 2
_SQUARE_W: Final = 3

_HEX_E: Final = 0
_HEX_SE: Final = 1
_HEX_SW: Final = 2
_HEX_W: Final = 3
_HEX_NW: Final = 4
_HEX_NE: Final = 5

SquareEdges = tuple[int, int, int, int]
HexEdges = tuple[int, int, int, int, int, int]
SquareBoundary = tuple[int | None, int | None, int | None, int | None]
HexBoundary = tuple[
    int | None,
    int | None,
    int | None,
    int | None,
    int | None,
    int | None,
]


class WangSquareRenderError(ValueError):
    """Raised when a Wang presentation cannot be rendered safely."""


@dataclass(frozen=True, slots=True)
class WangPresentation:
    """Immutable projection of the square fields relevant to presentation."""

    min_x: int
    min_y: int
    max_x: int
    max_y: int
    tile_edges: tuple[SquareEdges, ...]
    cells: tuple[int | None, ...]
    boundary: tuple[SquareBoundary | None, ...] = ()

    @property
    def width(self) -> int:
        return self.max_x - self.min_x + 1

    @property
    def height(self) -> int:
        return self.max_y - self.min_y + 1


@dataclass(frozen=True, slots=True)
class WangHexPort:
    """In-memory hex view derived one-to-one from a square presentation."""

    min_q: int
    min_r: int
    max_q: int
    max_r: int
    tile_edges: tuple[HexEdges, ...]
    cells: tuple[int | None, ...]
    boundary: tuple[HexBoundary | None, ...]
    fresh_color: int

    @property
    def width(self) -> int:
        return self.max_q - self.min_q + 1

    @property
    def height(self) -> int:
        return self.max_r - self.min_r + 1


def _port_fail(message: str) -> None:
    raise WangSquareRenderError(f"square-to-hex port: {message}")


def _check_square_storage(presentation: WangPresentation) -> None:
    for name, value in (
        ("min_x", presentation.min_x),
        ("min_y", presentation.min_y),
        ("max_x", presentation.max_x),
        ("max_y", presentation.max_y),
    ):
        if type(value) is not int:
            _port_fail(f"square {name} must be an integer")
    if presentation.max_x < presentation.min_x:
        _port_fail("square max_x must be at least min_x")
    if presentation.max_y < presentation.min_y:
        _port_fail("square max_y must be at least min_y")
    if type(presentation.tile_edges) is not tuple:
        _port_fail("square tile table must be an immutable tuple")
    if not presentation.tile_edges:
        _port_fail("square tile table must not be empty")
    for tile_id, edges in enumerate(presentation.tile_edges):
        if type(edges) is not tuple or len(edges) != len(SQUARE_DIRECTIONS):
            _port_fail(f"square tile {tile_id} must have four immutable edges")
        if any(type(color) is not int or color < 0 for color in edges):
            _port_fail(f"square tile {tile_id} has an invalid edge color")

    if type(presentation.cells) is not tuple:
        _port_fail("square cells must be an immutable tuple")
    if type(presentation.boundary) is not tuple:
        _port_fail("square boundary must be an immutable tuple")
    area = presentation.width * presentation.height
    if len(presentation.cells) != area:
        _port_fail("square cells must match the inclusive bounds area")
    if len(presentation.boundary) != area:
        _port_fail("square boundary must match the inclusive bounds area")
    for index, tile_id in enumerate(presentation.cells):
        if tile_id is not None and (
            type(tile_id) is not int
            or tile_id < 0
            or tile_id >= len(presentation.tile_edges)
        ):
            _port_fail(f"square cell {index} has an invalid tile ID")
    for index, sides in enumerate(presentation.boundary):
        if sides is None:
            continue
        if type(sides) is not tuple or len(sides) != len(SQUARE_DIRECTIONS):
            _port_fail(f"square boundary entry {index} must have four sides")
        if any(
            color is not None and (type(color) is not int or color < 0)
            for color in sides
        ):
            _port_fail(f"square boundary entry {index} has an invalid color")


def _check_hex_bounds(presentation: WangHexPort) -> None:
    for name, value in (
        ("min_q", presentation.min_q),
        ("min_r", presentation.min_r),
        ("max_q", presentation.max_q),
        ("max_r", presentation.max_r),
    ):
        if type(value) is not int:
            _port_fail(f"hex {name} must be an integer")
    if presentation.max_q < presentation.min_q:
        _port_fail("hex max_q must be at least min_q")
    if presentation.max_r < presentation.min_r:
        _port_fail("hex max_r must be at least min_r")


def _check_hex_storage(presentation: WangHexPort) -> None:
    if type(presentation.tile_edges) is not tuple:
        _port_fail("hex tile table must be an immutable tuple")
    if not presentation.tile_edges:
        _port_fail("hex tile table must not be empty")
    for tile_id, edges in enumerate(presentation.tile_edges):
        if type(edges) is not tuple or len(edges) != len(HEX_DIRECTIONS):
            _port_fail(f"hex tile {tile_id} must have six immutable edges")
        if any(type(color) is not int or color < 0 for color in edges):
            _port_fail(f"hex tile {tile_id} has an invalid edge color")

    if type(presentation.cells) is not tuple:
        _port_fail("hex cells must be an immutable tuple")
    if type(presentation.boundary) is not tuple:
        _port_fail("hex boundary must be an immutable tuple")
    area = presentation.width * presentation.height
    if len(presentation.cells) != area:
        _port_fail("hex cells must match the inclusive bounds area")
    if len(presentation.boundary) != area:
        _port_fail("hex boundary must match the inclusive bounds area")
    for index, tile_id in enumerate(presentation.cells):
        if tile_id is not None and (
            type(tile_id) is not int
            or tile_id < 0
            or tile_id >= len(presentation.tile_edges)
        ):
            _port_fail(f"hex cell {index} has an invalid tile ID")
    for index, sides in enumerate(presentation.boundary):
        if sides is None:
            continue
        if type(sides) is not tuple or len(sides) != len(HEX_DIRECTIONS):
            _port_fail(f"hex boundary entry {index} must have six sides")
        if any(
            color is not None and (type(color) is not int or color < 0)
            for color in sides
        ):
            _port_fail(f"hex boundary entry {index} has an invalid color")
    if (
        type(presentation.fresh_color) is not int
        or presentation.fresh_color < 0
    ):
        _port_fail("hex fresh color must be a nonnegative integer")


def _fresh_color(presentation: WangPresentation) -> int:
    return max(
        color
        for edges in presentation.tile_edges
        for color in edges
    ) + 1


def reduce_square_to_hex(presentation: WangPresentation) -> WangHexPort:
    """Map one square presentation to a pointy-top axial hex view.

    Axial coordinates are ``(q, r) = (x, y)``.  Hex edges are stored as
    ``(E, SE, SW, W, NW, NE)`` and each square ``(N, E, S, W)`` tile becomes
    ``(E, S, kappa, W, N, kappa)``.
    """
    if not isinstance(presentation, WangPresentation):
        raise TypeError("presentation must be a WangPresentation")
    _check_square_storage(presentation)
    kappa = _fresh_color(presentation)

    hex_tiles = tuple(
        (
            edges[_SQUARE_E],
            edges[_SQUARE_S],
            kappa,
            edges[_SQUARE_W],
            edges[_SQUARE_N],
            kappa,
        )
        for edges in presentation.tile_edges
    )
    hex_boundary: list[HexBoundary | None] = []
    for sides in presentation.boundary:
        if sides is None:
            hex_boundary.append(None)
            continue
        hex_boundary.append(
            (
                sides[_SQUARE_E],
                sides[_SQUARE_S],
                None,
                sides[_SQUARE_W],
                sides[_SQUARE_N],
                None,
            )
        )

    return WangHexPort(
        min_q=presentation.min_x,
        min_r=presentation.min_y,
        max_q=presentation.max_x,
        max_r=presentation.max_y,
        tile_edges=hex_tiles,
        cells=presentation.cells,
        boundary=tuple(hex_boundary),
        fresh_color=kappa,
    )


def _check_matching_equivalence(
    square: WangPresentation,
    candidate: WangHexPort,
) -> None:
    """Check that matching truth values survive the port without judging them."""
    width = square.width
    for index, tile_id in enumerate(square.cells):
        if tile_id is None:
            continue
        square_edges = square.tile_edges[tile_id]
        hex_edges = candidate.tile_edges[tile_id]
        local_x = index % width
        local_y = index // width

        if local_x + 1 < width:
            east_id = square.cells[index + 1]
            if east_id is not None:
                square_match = (
                    square_edges[_SQUARE_E]
                    == square.tile_edges[east_id][_SQUARE_W]
                )
                hex_match = (
                    hex_edges[_HEX_E]
                    == candidate.tile_edges[east_id][_HEX_W]
                )
                if square_match != hex_match:
                    _port_fail(f"east/west matching changed at cell {index}")

        if local_y + 1 < square.height:
            southeast_id = square.cells[index + width]
            if southeast_id is not None:
                square_match = (
                    square_edges[_SQUARE_S]
                    == square.tile_edges[southeast_id][_SQUARE_N]
                )
                hex_match = (
                    hex_edges[_HEX_SE]
                    == candidate.tile_edges[southeast_id][_HEX_NW]
                )
                if square_match != hex_match:
                    _port_fail(f"south/north matching changed at cell {index}")

        if local_x > 0 and local_y + 1 < square.height:
            southwest_id = square.cells[index + width - 1]
            if southwest_id is not None and (
                hex_edges[_HEX_SW]
                != candidate.tile_edges[southwest_id][_HEX_NE]
            ):
                _port_fail(f"fresh-axis matching failed at cell {index}")


def _check_boundary_equivalence(
    square: WangPresentation,
    candidate: WangHexPort,
) -> None:
    for index, (tile_id, square_sides, hex_sides) in enumerate(
        zip(square.cells, square.boundary, candidate.boundary, strict=True)
    ):
        if square_sides is None:
            if hex_sides is not None:
                _port_fail(f"boundary null changed at cell {index}")
            continue
        if (
            type(hex_sides) is not tuple
            or len(hex_sides) != len(HEX_DIRECTIONS)
        ):
            _port_fail(f"hex boundary entry {index} must have six sides")
        expected = (
            square_sides[_SQUARE_E],
            square_sides[_SQUARE_S],
            None,
            square_sides[_SQUARE_W],
            square_sides[_SQUARE_N],
            None,
        )
        if hex_sides != expected:
            _port_fail(f"boundary mapping changed at cell {index}")

        # Compare truth values instead of requiring a semantically valid input.
        # Rendering therefore checks the port but does not become a verifier.
        if tile_id is None:
            continue
        square_edges = square.tile_edges[tile_id]
        hex_edges = candidate.tile_edges[tile_id]
        for square_direction, hex_direction in (
            (_SQUARE_N, _HEX_NW),
            (_SQUARE_E, _HEX_E),
            (_SQUARE_S, _HEX_SE),
            (_SQUARE_W, _HEX_W),
        ):
            required = square_sides[square_direction]
            if required is None:
                continue
            if (
                square_edges[square_direction] == required
            ) != (hex_edges[hex_direction] == hex_sides[hex_direction]):
                _port_fail(f"boundary matching changed at cell {index}")


def check_square_to_hex(
    square: WangPresentation,
    candidate: WangHexPort,
) -> None:
    """Independently check a port without using any raster geometry.

    The checker establishes exact field preservation, the six-edge mapping,
    inverse projection, boundary mapping, and matching equivalence.  It does
    not require the source matching relations to be true and is therefore not
    a substitute for solution validation or the independent tiling verifier.
    """
    if not isinstance(square, WangPresentation):
        raise TypeError("square must be a WangPresentation")
    if not isinstance(candidate, WangHexPort):
        raise TypeError("candidate must be a WangHexPort")
    _check_square_storage(square)
    _check_hex_bounds(candidate)

    expected_bounds = (
        square.min_x,
        square.min_y,
        square.max_x,
        square.max_y,
    )
    actual_bounds = (
        candidate.min_q,
        candidate.min_r,
        candidate.max_q,
        candidate.max_r,
    )
    if actual_bounds != expected_bounds:
        _port_fail("axial coordinates do not preserve square coordinates")
    _check_hex_storage(candidate)
    if candidate.cells != square.cells:
        _port_fail("cell assignment or holes changed")
    if len(candidate.boundary) != len(square.boundary):
        _port_fail("boundary cardinality changed")
    if len(candidate.tile_edges) != len(square.tile_edges):
        _port_fail("tile-table cardinality changed")

    kappa = _fresh_color(square)
    if candidate.fresh_color != kappa:
        _port_fail("fresh color is not max(C) + 1")
    if any(kappa in edges for edges in square.tile_edges):
        _port_fail("fresh color occurs in the square color set")

    for tile_id, (square_edges, hex_edges) in enumerate(
        zip(square.tile_edges, candidate.tile_edges, strict=True)
    ):
        if (
            hex_edges[_HEX_E] != square_edges[_SQUARE_E]
            or hex_edges[_HEX_SE] != square_edges[_SQUARE_S]
            or hex_edges[_HEX_SW] != kappa
            or hex_edges[_HEX_W] != square_edges[_SQUARE_W]
            or hex_edges[_HEX_NW] != square_edges[_SQUARE_N]
            or hex_edges[_HEX_NE] != kappa
        ):
            _port_fail(f"hex tile {tile_id} does not implement H")
        projected = (
            hex_edges[_HEX_NW],
            hex_edges[_HEX_E],
            hex_edges[_HEX_SE],
            hex_edges[_HEX_W],
        )
        if projected != square_edges:
            _port_fail(f"inverse projection failed for tile {tile_id}")

    _check_boundary_equivalence(square, candidate)
    _check_matching_equivalence(square, candidate)
