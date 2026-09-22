from dataclasses import dataclass

@dataclass
class Region:
    width: int
    height: int
    active: tuple[bool, ...]
    boundary: tuple[tuple[str | None, str | None, str |None, str | None], ...] # N, E, S, W
