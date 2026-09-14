# Reproducing the Presentazione solver excerpt

The five published branch PNGs come from the existing reference search-UNSAT
capture for `tests/instances/pipeline_unsat_search.cm13`. The complete v3
manifest and its five content-addressed JSON snapshots are preserved under
`docs/assets/presentazione/search-unsat/`; no solution is asserted for UNSAT.
The canonical SAT capture and narrative assets are unchanged.

Render the committed capture using the renderer's existing locked environment:

```sh
cd renderer
uv run --frozen python wang_trace_render.py \
  ../docs/assets/presentazione/search-unsat/reference-manifest.json \
  ../build/presentazione-reexport --max-frames 20
```

Publish only frames 003995, 004118, 004120, 004121 and 004122. The existing
selector already includes them at this frame budget; its implementation and
defaults require no change. `renderer/test_wang_trace.py` checks byte equality
of these five PNGs and the complete replayed domain state before/after rollback.
The Pages checker fixes the v3 manifest and PNG hashes, loads and validates all
snapshot identities and replay, and requires the exact selected-file inventory.

For a fresh capture from repository root after `make shared`:

```sh
uv run --frozen python tools/export_solver_trace.py \
  tests/instances/pipeline_unsat_search.cm13 \
  build/presentazione-recapture/reference-manifest.json --solver reference \
  --event-capacity 8192 --checkpoint-interval 128 --checkpoint-capacity 64
```

Before publishing any replacement, compare every source artifact and frame.
Sequence numbers are zero-based; image headings count events from one. The
excerpt starts inside a depth-two frame: decision 3994 records change marker 3990,
3995 applies tile 0 at cell 492, 4118 empties cell 614, 4120 records conflict,
4121 restores all domains to state 3993, 4122 chooses tile 3, and 4123 applies
it. These recorded markers include the initial-propagation prefix and are not
physical C trail offsets. The preceding depth-one choice remains applied. The full capture has
4,370 events and concludes UNSAT; this selected branch is diagnostic evidence,
not an UNSAT certificate.
