from dataclasses import dataclass

@dataclass
class Formula:
    variable_count: int
    clauses: tuple[tuple[int, int, int], ...]
