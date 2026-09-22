import argparse
import json
from pathlib import Path

from z3 import is_true, unsat, unknown

from wangz3.parser import parse_formula
from wangz3.builder import building_region
from wangz3.boolean_witness import witness_solver
from wangz3.solver import solve
from wangz3.tileset import COLORS, TILESET


def _serialize_boolean_witness(witness):
    if witness is None:
        return None

    return [
        value if isinstance(value, bool) else is_true(value)
        for value in witness
    ]


def _wang_status(result):
    if isinstance(result, list):
        return "SAT"

    if result == unsat:
        return "UNSAT"

    if result == unknown:
        return "UNKNOWN"

    return "UNKNOWN"


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Independent CM1-in-3 -> Yang-Zhang -> Wang-Z3 "
            "verification harness"
        )
    )

    parser.add_argument(
        "input",
        type=Path,
        help="CM1-in-3 input file",
    )

    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Write JSON result to this file instead of stdout",
    )

    args = parser.parse_args()

    
    # 1. Parse CM1-in-3 formula
 

    formula = parse_formula(args.input)


    # 2. Independent Boolean witness


    boolean_result = witness_solver(formula)

    if boolean_result is None:
        boolean_status = "UNSAT"
        boolean_data = None
    else:
        boolean_status = "SAT"
        boolean_data = _serialize_boolean_witness(boolean_result)


    # 3. Yang-Zhang region construction


    region = building_region(formula)


    # 4. Independent Wang-Z3 solve


    wang_result = solve(region)
    wang_status = _wang_status(wang_result)

    if wang_status == "SAT":
        tiling = wang_result
    else:
        tiling = None


    # 5. Cross-check


    if wang_status == "UNKNOWN":
        consistent = None
    else:
        consistent = boolean_status == wang_status


    # 6. Stable JSON artifact


    result = {
        "schema_version": 1,

        "input": {
            "path": str(args.input),
        },

        "formula": {
            "variable_count": formula.variable_count,
            "clause_count": len(formula.clauses),
            "clauses": formula.clauses,
        },

        "boolean_z3": {
            "status": boolean_status,
            "witness": boolean_data,
        },

        "region": {
            "width": region.width,
            "height": region.height,
            "active_cell_count": sum(region.active),
            "active": region.active,
            "boundary": region.boundary,
        },

        "wang_z3": {
            "status": wang_status,
            "tiling": tiling,
        },

        "tileset": {
            "colors": COLORS,
            "tiles": TILESET,
        },

        "cross_check": {
            "consistent": consistent,
        },
    }

    encoded = json.dumps(
        result,
        indent=2,
        ensure_ascii=False,
    )

    if args.output is None:
        print(encoded)
    else:
        args.output.write_text(
            encoded + "\n",
            encoding="utf-8",
        )

    #
    # Exit codes:
    #   0 = both engines agree
    #   1 = Boolean/Wang mismatch
    #   2 = Wang-Z3 returned UNKNOWN
    #

    if wang_status == "UNKNOWN":
        return 2

    if not consistent:
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
