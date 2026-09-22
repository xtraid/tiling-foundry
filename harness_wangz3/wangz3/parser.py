from .formula import Formula

def parse_formula(path):
    with open(path, 'r') as file:
        clauses = []
        for line in file:
            if line.startswith("c"):
                continue
            if line.startswith("p"):
                parts = line.split()
                variable_count = int(parts[2])
                nclause = int(parts[3])
                continue
            parts = line.split()
            clause = []
            for part in parts:
                if part == "0":
                    break
                else:
                    clause.append(int(part))
            clauses.append(clause)
        clauseset = tuple(tuple(clause) for clause in clauses)
        if len(clauseset) != nclause:
            raise ValueError("wrojng number of clauses")
        return Formula(variable_count=variable_count, clauses = clauseset)
