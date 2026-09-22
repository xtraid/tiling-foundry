# Tiling Foundry renderer

The renderer turns Tiling Foundry artifacts into figures that explain the
Yang–Zhang construction, the solver search, and the final tiling. It reads
versioned JSON snapshots and traces, then produces static PNGs and animations
used by the project documentation and run dossiers.

The focus is making each stage inspectable: which formula was parsed, how its
region was built, what the native solver did, and how a verified witness maps
to square, generalized, and hex views.

**Read:** [Project overview](../README.md) ·
[Static snapshots](../docs/wang_explainability_snapshots.md) ·
[Reduction explanation](../docs/wang_reduction_explanation.md) ·
[Solver traces](../docs/wang_solver_trace.md) ·
[Run dossiers](../docs/run_dossiers.md)

## How the pipeline works

The root project owns parsing, construction, solving, and witness verification.
This directory consumes the exported data in a separate Python environment;
it does not load `libwang.so` or import Z3.

```text
.cm13 --> parser --> Formula --> Yang–Zhang builder --> Region + TILESET
                       |                  |
                       +------ snapshots + construction provenance
                                          |
                    native solvers -------+--> observed event traces
                    Z3 checks ------------+--> encoding summaries
                    witness verification -+--> verified solution
                                          |
                                          v
                              versioned JSON artifacts
                                          |
                              schema / hash / identity checks
                                          |
                              static views / offline replay
                                          |
                              PNG frames + contact sheet + GIF
                                          |
                              documentation / run dossier / PDF
```

1. **Capture the construction.** The exporter copies the parsed formula, the
   fixed 23-tile set, and the unassigned region into snapshots. Optional native
   provenance records signals, their permutation, and gadget spans so the
   renderer can explain the reduction without rebuilding it.
2. **Record the search.** The reference and optimized native solvers can export
   observed events, including propagation, decisions, conflicts, and
   backtracks. Z3 exports separate summaries of the encoding order and returned
   model; these do not describe its internal search.
3. **Validate the inputs.** Manifests bind artifacts to their schemas and
   SHA-256 hashes. Consumers check the expected fields and consistency between
   artifacts before rendering. The trace consumer also replays and validates
   the recorded state changes.
4. **Compose the views.** Static renderers show the formula, tileset, region,
   reduction, or verified solution. Trace rendering selects semantic milestones
   from one validated replay, then draws those states as frames.
5. **Publish the same evidence.** The animation encoder writes PNG frames, a
   contact sheet, and a GIF. The root dossier tools reuse these assets for the
   run report and optional PDF. UNSAT runs show an explicit not-applicable view
   where a SAT witness would appear.

## Quick start

For the full pipeline setup, follow the [root quick start](../README.md#quick-start).
To render the committed fixtures alone, run these commands from `renderer/`:

```sh
uv sync --locked

uv run --locked python wang_square.py \
  ../tests/fixtures/pipeline_sat_explain/manifest.json \
  output/formula.png --view formula

uv run --locked python wang_square.py \
  ../tests/fixtures/pipeline_sat_reduction_explain/manifest.json \
  output/reduction.png --view reduction

uv run --locked python wang_trace_render.py \
  ../tests/fixtures/pipeline_sat_solver_trace/manifest.json \
  output/solver-trace

uv run --locked python wang_square.py \
  ../tests/fixtures/wang_solution_v1_square_sat.json \
  output/solution-explain.png --explain
```

The renderer uses Python 3.14 and its own `uv.lock`. Rendering existing
artifacts does not require a native build or a new solver run.

## Exporting a new instance

From the repository root, build the native library and export the construction:

```sh
make shared
uv run --locked python tools/export_pipeline_snapshots.py \
  tests/instances/pipeline_sat.cm13 \
  build/explain/manifest.json --reduction-explanation
```

This parses and reduces the formula without solving it. Omit
`--reduction-explanation` for just the formula, tileset, and region snapshots.
To run a native solver and export its trace instead:

```sh
uv run --locked python tools/export_solver_trace.py \
  tests/instances/pipeline_sat.cm13 \
  build/trace/manifest.json --solver reference
```

Use `--solver optimized` for the experimental variant. Pass the resulting
manifest to `wang_trace_render.py` in the renderer environment.

For a complete run with all four solver results, figures, and a PDF, use the
root orchestrator after completing the full setup:

```sh
uv run --locked python tools/generate_run_dossier.py \
  examples/run-cases-v2/pipeline-sat.json \
  build/first-dossier --pdf
```

The output directory must be new for each dossier. See the
[dossier guide](../docs/run_dossiers.md) for inputs and generated artifacts.

## What the views explain

| View | What it shows |
| --- | --- |
| `--view formula` | Parsed clauses and their variable positions |
| `--view tileset` | Atomic tiles and their edge colors |
| `--view region` | Active cells and boundary constraints, without an assignment |
| `--view reduction` | Native construction signals, routing, and gadget spans |
| `--explain` | A solution with tile IDs, colored edges, boundary emphasis, and a legend |
| `--view generalized-sheet` | The 14 generalized Yang–Zhang tiles |
| `--view atomic-legend` | The 23 atomic tiles with their semantic labels |
| `--view generalized-overlay` | Exact generalized compositions recognized in a square witness |

Static views use a manifest; solution and generalized-overlay views use a
`wang-solution-v1` document. Manifest v1 contains the basic snapshots, v2 adds
reduction provenance, and v3 carries the solver trace bundle. Static views can
also read the static projection of a v3 bundle; trace semantics are checked by
the separate trace consumer.

Add `--hex` to solution, tileset, or region rendering for a checked
square-to-hex presentation. The renderer applies the pure reducer and checks
its result before drawing; it does not export a second hex JSON document.
Formula, reduction, and generalized views remain square-only.

## Animations and their meaning

Native trace animations show observed solver events. Frame selection keeps
semantic milestones such as phase changes, decisions, conflicts, backtracks,
and the terminal state, then fills remaining gaps. It is deterministic and
does not represent elapsed execution time.

The other animations have distinct sources:

| Command | Source and meaning |
| --- | --- |
| `wang_z3_summary.py` | Project-owned encoding order and returned model |
| `wang_algorithm_animation.py builder` | Canonical construction from reduction provenance |
| `wang_algorithm_animation.py hex` | Checked square-to-hex transformation |
| `wang_algorithm_animation.py optimized` | Didactic overview of the six optimization mechanisms |

`wang_narrative.py` composes the verification, witness, and overview sequences
used by the root shared-asset generator. PNG frames provide deterministic
comparison artifacts; GIFs are presentation outputs with static fallbacks.
Performance claims come from measured reports, not animation speed.

## Code map

| Module | Responsibility |
| --- | --- |
| `wang_square.py` | Main CLI for static views and solution rendering |
| `wang_snapshot.py` | Snapshot loading, validation, and static composition |
| `wang_explain.py` | Shared edge bands, labels, and legends |
| `wang_trace.py` | Trace bundle validation and offline replay |
| `wang_trace_render.py` | Milestone selection and trace frame composition |
| `wang_animation.py` | PNG, contact-sheet, and GIF encoding |
| `wang_hex_port.py` | Pure square-to-hex reduction and independent checker |
| `wang_generalized.py` / `wang_generalized_render.py` | Exact atomic grouping and generalized views |
| `wang_z3_summary.py` | Z3 encoding-summary views |
| `wang_algorithm_animation.py` / `wang_narrative.py` | Algorithm and pipeline compositions |

## Verification and scope

A rendered image is not a correctness certificate. Witness verification takes
place upstream; hashes bind the inputs, and replay checks trace consistency.
An observed trace is not a standalone UNSAT proof. Generalized recognition
checks the tile compositions, while the hex checker validates the presentation
transformation.

Run the isolated renderer suite from this directory:

```sh
uv run --locked pytest -q
```

The original PAP Render pixel-art implementation remains in `main.py` and
`classes.py`, with its example inputs and tests. It is separate from the Wang
pipeline; provenance and license details are in [UPSTREAM.md](UPSTREAM.md).
