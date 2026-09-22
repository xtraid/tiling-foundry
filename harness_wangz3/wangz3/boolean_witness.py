from z3 import Bool, Solver, Sum, If, sat
from .formula import Formula

def witness_solver (phi: Formula):
    psi = Solver()
    var = [f"x{x+1}" for x in range(phi.variable_count)]
    for clause in phi.clauses:
        psi.add(Sum(If(Bool(var[clause[0]-1]), 1, 0), If(Bool(var[clause[1]-1]), 1, 0), If(Bool(var[clause[2]-1]), 1, 0)) == 1)
    if psi.check() == sat:
        model = psi.model()
        ordered = sorted(model.decls(), key=lambda d: int(d.name()[1:]))
        return [model[d] for d in ordered]
    return None
