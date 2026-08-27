"""Explicit reproducibility settings shared by the two Z3 oracles."""

from typing import Final

from z3 import Solver, get_version_string


Z3_RANDOM_SEED: Final = 0
Z3_THREADS: Final = 1


def configured_solver(solver=None) -> Solver:
    """Configure a supplied solver, or create one, with stable parameters."""
    if solver is None:
        solver = Solver()
    solver.set(random_seed=Z3_RANDOM_SEED, threads=Z3_THREADS)
    return solver


def z3_configuration() -> dict[str, object]:
    """Return the exact environment fields used by encoding summaries."""
    return {
        "version": get_version_string(),
        "parameters": {
            "random_seed": Z3_RANDOM_SEED,
            "threads": Z3_THREADS,
        },
    }
