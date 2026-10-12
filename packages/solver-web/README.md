# Tiling Foundry browser solver

This package is built and owned by Tiling Foundry. Independent applications
consume the versioned artifacts without copying the native solver source.
It runs C search in a dedicated Web Worker; native targets remain unchanged.
No Python service, npm runtime dependencies, shared memory, cross-origin
isolation headers, or paid compute service is required.

## Build

Activate Emscripten **4.0.23**, then run from the Foundry root:

```sh
python tools/build_solver_web.py
```

The archive and its SHA-256 are written to `build/solver-web/`. Development
versions include a digest of the actual source inputs; the manifest also records
the Git revision and whether the checkout was dirty. `--release` requires a
clean checkout and Emscripten 4.0.23, and uses the version in
`packages/solver-web/package.json`. Archive timestamps, ownership and permissions
are normalized; rebuilding the same revision with that SDK yields identical bytes.

## Consume

Serve the entire extracted package directory over HTTP(S). Keep its relative
paths intact, including the Worker, JavaScript loader, Wasm and manifest.

```js
import {Solver, capabilities} from './vendor/foundry/client.mjs';
const solver = new Solver();
const engine = await capabilities();
const {id} = await solver.start({
  geometry: 'square', solver: 'optimized', palette: ['#ffffff'], tiles: [[0, 0, 0, 0]],
  cells: [{id: '0,0', required: [null, null, null, null]}],
  enumeration_mode: 'step', timeout_seconds: 30,
});
// Poll solver.get(id). When paused: solver.resume(id, 'next' | 'count').
// solver.cancel(id) terminates the Worker; solver.close() closes all jobs.
```

One live search per Solver instance. Statuses: `running`, `paused`, `complete`,
`cancelled`, `timeout`, `expired`, `error`. Only exhaustive `complete` yields
`exact: true`. Counts are arbitrary-precision decimal strings; metrics are
decimal strings too. Duplicate edge tuples are counted once, subject to initial
domains. Palette indices are symbolic identities, even when RGB values repeat.

Supported geometries: `square`, `tri-up`, `tri-side`, `hex-flat`, `hex-point`.
Square edges are `(N,E,S,W)`, with fixed orientations. Tile cardinality is runtime-sized (`max_tiles: null`). Resource limits remain
65536 used colors, 65536 active cells and 65536 palette entries. Sparse square
regions use active-cell graphs when their bounding box exceeds the native adapter
budget, so no bounding-box size limit applies. `fixed` optionally pins an exact edge tuple. `required` constrains each
side; `null` means unconstrained. Negative coordinates, holes and disconnected
inputs are supported, but applications may impose stricter research profiles.

`solver` selects `optimized` (default) or `reference`. Within the native limits
(up to 32 tiles, 16 used colors and 4096 cells), both execute the shared
Foundry C core with their respective mechanism flags. Inputs exceeding those
limits use the same browser-only dynamic engine for either selection; they do
not claim the native optimized mechanisms. Python/Z3 is not part of
this package. The two native reference/oracle paths remain available in Foundry.

The package validates input and independently checks published assignments in
JavaScript. Native Foundry verifies every solution before invoking the visitor.
Counting retains a single snapshot and a counter, not a list of solutions.

## Pause, stop and deadlines

Asyncify suspends the existing C callback for interactive stepping, preserving
the DFS stack and trail. Counting yields to the Worker event loop at throttled
progress updates. Asyncify has a
runtime cost; native and browser performance must be benchmarked separately.

The controlling thread enforces a deadline per active segment, including when
the native search has found no solution. Progress never resets that deadline.
The default active deadline is 600 seconds. `timeout_seconds: 0` disables it.
Pause uses `idle_timeout_seconds` (default 0, no expiry); Next/Count starts a new
active segment. Both timers accept up to 2147483 seconds.
Stop/timeout terminates the Worker and retains the last published lower bound.
Browser timer throttling can delay enforcement in background tabs. A closed
page ends its computations; there is no server-side persistence.

Triangles use IDs `i,j,half` (half 0 or 1) and three sides; hexagons use IDs
`i,j` and six sides. Edge order follows Studio's polygon vertex order. Triangle
neighbors share the same side index (including inverted cells); hexagonal
neighbors use `(side+3)%6`. Variants rotate the lattice, without implicit tile
rotations. The input adapter builds reciprocal cell/side arcs and calls
the private browser bridge. Small domains share the existing C core; larger
domains use the private dynamic propagation, MRV, trail and iterative DFS.
Graph regions use dense active cells, without the square bounding-box limit.
Generalized pieces compiled into atomic edge tuples are supported; piece metadata
is not interpreted by the solver.

Consumers should retain `manifest.json` with experiment results, pin releases,
and update only between searches. Integrity hashes identify artifacts; a hash
does not establish trust in an otherwise untrusted download source.

## Domain and color ABI (version 3)

The public JavaScript API stays at version 1: input edge tuples and output numeric
array indices do not change. The matched Worker/Wasm pair uses private ABI 3,
recorded as `wasm_abi_version` in the manifest. Do not mix package artifacts.
`foundry_enumerate_graph` takes cell-major `uint32_t` domains with
`ceil(tile_count / 32)` words per cell. Tile `t` is bit `t % 32` in word
`floor(t / 32)`; unused tail bits must be zero. Callback domains have the same
layout and are borrowed until the callback returns. Counts remain cell counts,
not word counts. The Worker copies snapshots before resuming and refreshes heap
views after allocations/growth. It frees input buffers in `finally`.
The historical rectangular entry point retains its single-word contract; the
adapter routes squares larger than 32 tiles through the general graph entry.
The graph entry adds a `wide_colors` argument. When true, edge and boundary
arrays contain `uint32_t` color IDs, with `UINT32_MAX` as the unconstrained
boundary sentinel. Otherwise byte arrays retain their previous representation.
Color support uses runtime-sized stamp arrays, not a fixed-width color mask.
No tile ID is narrowed to the native `uint8_t TileId` in the dynamic engine.

`dynamic.c` is linked only by `build_solver_web.py`. Native sources, headers,
canonical tiles, builder and Makefile are unchanged. Root restrictions and
duplicate-tuple elimination precede arc consistency. Search records changed
words on an undo trail, selects MRV cells, and stores decisions on a heap stack.
Every witness is checked in C and published snapshots are checked independently
in JavaScript. Allocation/size failures return `-1`, never exhaustive UNSAT;
Wasm malloc returns null on exhaustion. The Worker reports an error and releases
its inputs. Current Wasm linear-memory ceiling is 2 GiB (allocation can fail earlier); Stop/deadline terminates the
Worker even while search has no witness. Large-cardinality performance is not
promised to match the specialized native optimized solver.
