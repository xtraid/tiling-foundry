"""Solver-neutral result contract for dense Wang tilings."""

from dataclasses import dataclass
from enum import Enum


class TilingSolveStatus(Enum):
    SAT = "sat"
    UNSAT = "unsat"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class TilingSolveResult:
    """A SAT result owns one dense tiling; other statuses own none."""

    status: TilingSolveStatus
    tiling: tuple[int | None, ...] | None = None

    def __post_init__(self) -> None:
        if type(self.status) is not TilingSolveStatus:
            raise TypeError("status must be a TilingSolveStatus")
        if self.tiling is not None and type(self.tiling) is not tuple:
            raise TypeError("tiling storage must be an immutable tuple")
        has_tiling = self.tiling is not None
        if has_tiling != (self.status is TilingSolveStatus.SAT):
            raise ValueError("only SAT results carry a tiling")
