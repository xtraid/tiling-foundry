"""Boolean Z3 oracle for Cubic Monotone 1-in-3 SAT formulas.

The solver consumes an already constructed :class:`Formula`. Parsing,
filesystem access, ctypes, the Wang region, and Yang-Zhang reduction logic do
not belong here.
"""

from dataclasses import dataclass
from enum import Enum

from z3 import Bool, BoolRef, If, Solver, Sum, is_true, sat, unsat

from model.formula import Formula
from oracles.z3_config import configured_solver


class BooleanSolveStatus(Enum):
    SAT = "sat"
    UNSAT = "unsat"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class BooleanSolveResult:
    status: BooleanSolveStatus
    assignment: tuple[bool, ...] | None = None

    def __post_init__(self) -> None:
        has_assignment = self.assignment is not None
        if has_assignment != (self.status is BooleanSolveStatus.SAT):
            raise ValueError("only SAT results carry an assignment")


def _encode_boolean(formula: Formula) -> tuple[Solver, tuple[BoolRef, ...]]:
    """Build the canonical variable and clause order used by this oracle."""
    variables = [Bool(f"x_{index}") for index in range(formula.variable_count)]
    solver = configured_solver(Solver())
    for clause in formula.clauses:
        solver.add(Sum([If(variables[index], 1, 0) for index in clause]) == 1)
    return solver, tuple(variables)


def solve_boolean(formula: Formula) -> BooleanSolveResult:
    """Solve ``formula`` while counting all three positions of each clause."""
    solver, variables = _encode_boolean(formula)

    status = solver.check()

    if status == sat:
        model = solver.model()
        assignment = tuple(
            is_true(model.eval(variable, model_completion=True))
            for variable in variables
        )
        return BooleanSolveResult(BooleanSolveStatus.SAT, assignment)

    if status == unsat:
        return BooleanSolveResult(BooleanSolveStatus.UNSAT)

    return BooleanSolveResult(BooleanSolveStatus.UNKNOWN)
