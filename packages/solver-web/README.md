# Tiling Foundry browser solver

This package is built and owned by Tiling Foundry. Independent applications
consume the versioned artifacts without copying the native solver source.
It runs the existing reference and optimized C search mechanisms in a dedicated Web Worker.
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
clean checkout and uses the version in `packages/solver-web/package.json`.

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
Square edges are `(N,E,S,W)`, with fixed orientations. Limits are 32 tiles,
16 used colors, 4096 active cells, 16384 bounding-box cells for squares, and 128 palette
entries. `fixed` optionally pins an exact edge tuple. `required` constrains each
side; `null` means unconstrained. Negative coordinates, holes and disconnected
inputs are supported, but applications may impose stricter research profiles.

`solver` selects `optimized` (default) or `reference`. Both execute the shared
Foundry C core with their respective mechanism flags; Python/Z3 is not part of
this package. The two native reference/oracle paths remain available in Foundry.

The package validates input and independently checks published assignments in
JavaScript. Native Foundry verifies every solution before invoking the visitor.
Counting retains a single snapshot and a counter, not a list of solutions.

## Pause, stop and deadlines

Asyncify suspends the existing C callback for interactive stepping, preserving
the DFS stack and trail. Counting yields to the Worker event loop at throttled
progress updates. This adds no alternate search implementation. Asyncify has a
runtime cost; native and browser performance must be benchmarked separately.

The controlling thread enforces a deadline per active segment, including when
the native search has found no solution. Progress never resets that deadline.
Pause switches to a ten-minute idle expiry; Next/Count starts a new segment.
Stop/timeout terminates the Worker and retains the last published lower bound.
Browser timer throttling can delay enforcement in background tabs. A closed
page ends its computations; there is no server-side persistence.

Triangles use IDs `i,j,half` (half 0 or 1) and three sides; hexagons use IDs
`i,j` and six sides. Edge order follows Studio's polygon vertex order. Triangle
neighbors share the same side index (including inverted cells); hexagonal
neighbors use `(side+3)%6`. Variants rotate the lattice, without implicit tile
rotations. The input adapter builds reciprocal cell/side arcs and calls
`wang_enumerate_graph`, sharing the existing C propagation, MRV, trail and DFS.
Graph regions use dense active cells, without the square bounding-box limit.
Generalized-piece constraints are not supported.

Consumers should retain `manifest.json` with experiment results, pin releases,
and update only between searches. Integrity hashes identify artifacts; a hash
does not establish trust in an otherwise untrusted download source.
