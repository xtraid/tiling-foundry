#!/usr/bin/env python3
"""Run six narrated correctness checks using installed native and Z3 tools."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import demo


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise demo.DemoError(message)


def _expect_status(result, expected: str, engine: str) -> None:
    observed = result.status.value.upper()
    if observed == "UNKNOWN":
        raise demo.DemoError(f"{engine}: UNKNOWN, esito non conclusivo")
    _require(observed == expected, f"{engine}: atteso {expected}, osservato {observed}")


def _preflight() -> None:
    try:
        import z3
        from native._lib import library

        library()
        z3.get_version_string()
    except (ImportError, OSError) as error:
        raise demo.DemoError(
            f"dipendenza non disponibile: {error}; eseguire make demo-setup"
        ) from error


def _run_checks() -> None:
    from crosscheck.witness_pipeline import solve_native_and_extract
    from model.tileset import COLOR_NONE, TILESET
    from native.formula_adapter import FormulaLoadError, FormulaParseStatus, load_formula
    from oracles.boolean_solver import solve_boolean
    from oracles.tiling_check import is_valid_tiling
    from oracles.tiling_solver import solve_tiling
    from oracles.witness_check import is_valid_assignment

    sat_path = ROOT / "tests/instances/pipeline_sat.cm13"
    unsat_path = ROOT / "tests/instances/pipeline_unsat_search.cm13"
    invalid_path = ROOT / "tests/fuzz/corpus/cm13/malformed_domain.cm13"

    print("[1/6] Input valido: il parser C deve leggere variabili e clausole CM1-in-3.", flush=True)
    parsed = load_formula(sat_path)
    _require(
        parsed.variable_count == 3
        and parsed.clauses == ((0, 0, 1), (0, 1, 2), (1, 2, 2)),
        "contenuto inatteso nel caso SAT noto",
    )
    print("OK: lette 3 variabili e 3 clausole da pipeline_sat.cm13.", flush=True)

    print("[2/6] Input fuori dominio: una variabile non dichiarata deve essere rifiutata.", flush=True)
    try:
        load_formula(invalid_path)
    except FormulaLoadError as error:
        _require(
            error.status is FormulaParseStatus.DOMAIN_ERROR,
            f"parser: atteso DOMAIN_ERROR, osservato {error.status.name}: {error}",
        )
    else:
        raise demo.DemoError("il parser ha accettato il caso fuori dominio")
    print("OK: variabile 3 con solo 2 variabili dichiarate rifiutata (DOMAIN_ERROR).", flush=True)

    print("[3/6] SAT noto: il witness reference deve superare verifiche indipendenti.", flush=True)
    sat_formula, sat_region, sat_result, sat_assignment = solve_native_and_extract(sat_path, optimized=False)
    _require(sat_formula == parsed, "la formula del solve differisce da quella letta")
    _expect_status(sat_result, "SAT", "reference SAT")
    _require(
        sat_result.tiling is not None
        and is_valid_tiling(sat_region, TILESET, sat_result.tiling)
        and sat_assignment is not None
        and is_valid_assignment(sat_formula, sat_assignment),
        "reference SAT: witness assente o non valido",
    )
    print("OK: tiling verificato; assegnamento estratto x1=0, x2=1, x3=0 valido.", flush=True)

    print("[4/6] UNSAT noto: la clausola (x4,x4,x4) richiede 3*x4=1, impossibile per un booleano.", flush=True)
    unsat_formula, unsat_region, unsat_result, unsat_assignment = solve_native_and_extract(unsat_path, optimized=False)
    _require(
        unsat_formula.variable_count == 4 and (3, 3, 3) in unsat_formula.clauses,
        "la clausola impossibile manca dal caso UNSAT noto",
    )
    _expect_status(unsat_result, "UNSAT", "reference UNSAT")
    _require(unsat_result.tiling is None and unsat_assignment is None, "UNSAT non deve avere un witness")
    print("OK: reference restituisce UNSAT senza tiling o assegnamento.", flush=True)

    print("[5/6] Accordo: reference, optimized, Boolean Z3 e Wang Z3 devono confermare i due casi noti.", flush=True)
    for path, formula, region, expected in (
        (sat_path, sat_formula, sat_region, "SAT"),
        (unsat_path, unsat_formula, unsat_region, "UNSAT"),
    ):
        # Reference results come from checks 3/4; each other engine runs once.
        print(f"  {path.name}: optimized", flush=True)
        optimized_formula, optimized_region, optimized, assignment = solve_native_and_extract(path, optimized=True)
        _require(optimized_formula == formula and optimized_region == region, "optimized: input o regione differente")
        _expect_status(optimized, expected, "optimized")
        if expected == "SAT":
            _require(
                optimized.tiling is not None and is_valid_tiling(region, TILESET, optimized.tiling)
                and assignment is not None and is_valid_assignment(formula, assignment),
                "optimized: witness assente o non valido",
            )
        else:
            _require(optimized.tiling is None and assignment is None, "optimized UNSAT: witness inatteso")

        print(f"  {path.name}: Boolean Z3", flush=True)
        boolean = solve_boolean(formula)
        _expect_status(boolean, expected, "Boolean Z3")
        if expected == "SAT":
            _require(
                boolean.assignment is not None and is_valid_assignment(formula, boolean.assignment),
                "Boolean Z3: witness assente o non valido",
            )
        else:
            _require(boolean.assignment is None, "Boolean Z3 UNSAT: witness inatteso")

        print(f"  {path.name}: Wang Z3", flush=True)
        wang = solve_tiling(region, TILESET)
        _expect_status(wang, expected, "Wang Z3")
        if expected == "SAT":
            _require(
                wang.tiling is not None and is_valid_tiling(region, TILESET, wang.tiling),
                "Wang Z3: witness assente o non valido",
            )
        else:
            _require(wang.tiling is None, "Wang Z3 UNSAT: witness inatteso")
        print(f"  Quattro motori concordi: {expected}.", flush=True)
    print("OK: entrambi gli esiti noti confermati; ogni witness SAT verificato.", flush=True)

    print("[6/6] Witness alterato: una tessera incompatibile deve essere rifiutata dal checker indipendente.", flush=True)
    # Choose a valid tile ID which violates an imposed boundary color.
    # The independent checker remains the only judge of the altered witness.
    change = next(
        ((index, tile_id) for index, active in enumerate(sat_region.active) if active
         for tile_id, tile in enumerate(TILESET)
         if any(required != COLOR_NONE and tile[direction] != required
                for direction, required in enumerate(sat_region.boundary[index]))),
        None,
    )
    _require(change is not None, "nessuna tessera alterabile nel caso SAT")
    index, tile_id = change
    altered = list(sat_result.tiling)
    original_id = altered[index]
    altered[index] = tile_id
    _require(not is_valid_tiling(sat_region, TILESET, altered), "il checker ha accettato il witness alterato")
    _require(is_valid_tiling(sat_region, TILESET, sat_result.tiling), "il witness originale non è più valido")
    print(
        f"OK: cella ({index % sat_region.width},{index // sat_region.width}), "
        f"tessera {original_id} -> {tile_id}: copia rifiutata; originale ancora valido.",
        flush=True,
    )


def _worker(run_root: Path) -> int:
    try:
        sys.path.insert(0, str(ROOT / "python"))
        _preflight()
        _run_checks()
        with (run_root / "complete").open("x", encoding="ascii") as marker:
            marker.write("6/6\n")
        return 0
    except Exception as error:
        print(f"demo-check: {type(error).__name__}: {error}", file=sys.stderr, flush=True)
        return 1


def _new_run(output: Path | None) -> Path:
    if output is not None:
        run = output.absolute()
        try:
            run.mkdir(parents=True)
        except FileExistsError as error:
            raise demo.DemoError(f"output already exists: {run}") from error
        return run
    directory = ROOT / "build/demo-check"
    directory.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix="run-", dir=directory))


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="new diagnostic directory (default: build/demo-check/run-*)")
    parser.add_argument(
        "--timeout", type=demo._positive_timeout,
        default=os.environ.get("TILING_DEMO_TIMEOUT", "300"),
        help="global timeout in seconds (default: 300)",
    )
    args = parser.parse_args(arguments)
    if not sys.platform.startswith("linux"):
        parser.error("demo-check currently supports Linux")
    try:
        run_root = _new_run(args.output)
        demo._emit(f"diagnostics={run_root}\n")
        worker_python = ROOT / ".venv/bin/python"
        _require(worker_python.is_file(), "Python installato mancante; eseguire make demo-setup")
        environment = os.environ.copy()
        environment.update(UV_OFFLINE="1", UV_NO_SYNC="1", UV_PYTHON_DOWNLOADS="never")
        environment.pop("UV_PROJECT_ENVIRONMENT", None)
        command = [
            str(worker_python), "-u", str(Path(__file__).resolve()),
            "--_worker", str(run_root),
        ]
        started = time.monotonic()
        result = demo._supervise(
            command, cwd=ROOT, env=environment,
            log_path=run_root / "worker.log", timeout=args.timeout,
        )
        if result:
            demo._emit(f"demo-check: suite non completata; diagnostica in {run_root}\n", stream=sys.stderr)
            return result
        marker = run_root / "complete"
        _require(marker.is_file() and marker.read_bytes() == b"6/6\n", "suite incompleta: conferma dei sei controlli mancante")
        demo._emit(f"Superati 6/6 controlli in {time.monotonic() - started:.3f} s.\n")
        return 0
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        demo._emit(f"demo-check: {error}\n", stream=sys.stderr)
        return 1


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--_worker":
        raise SystemExit(_worker(Path(sys.argv[2])))
    raise SystemExit(main())
