# Wang Studio: independent research editor

Wang Studio is an independent project for the research following Tiling Foundry,
with its own repository and website. It consumes Foundry's versioned solver
package for authoring tilesets, constructing finite regions and exploring search.

The browser package is maintained under `packages/solver-web/` in Foundry and
contains the C reference and optimized engines compiled to WebAssembly. Its
documentation is the current package contract. Python/Z3 is not distributed
to the editor. The local Python connector described below remains an optional
development comparison path. Foundry's Pages link to Studio; Studio is not
hosted in the Foundry source repository.

It is distinct from `renderer/`, which produces figures from verified
Foundry artifacts. Studio owns interaction and experiments; Foundry continues
to own native propagation, search, verification and scientific pipelines.

The first local connector consumes `libwang.so` through
`wang_solve_optimized_tileset`: the **same optimized core** accepts a runtime
square tileset of 1–32 tiles with colors 0–15. It supports initial domains and
metrics. Canonical trace formats are not accepted for custom tilesets.
The existing 23-tile APIs and the Yang–Zhang pipeline remain available.

The runtime verifier is `wang_verify_tiling_with_tileset`. Both interfaces
borrow their input arrays. The result lifecycle is unchanged:
`wang_solve_result_destroy` releases returned domains.

Studio runs solves in worker processes for cancellation/deadlines, checks
solutions independently, and treats timeout as distinct from UNSAT. It does
not copy the solver implementation or use Z3 as a runtime fallback.

Current local companion checkout: `~/Projects/wang-studio`. Its README
contains startup instructions and the connector's resource limits. Native
adjacency for hexagons and triangles is future work; Studio's support for
editing those geometries does not imply that this square-grid API solves them.

## Incremental enumeration

`wang_enumerate_optimized_tileset` shares the optimized search core. Each
verified solution is passed to a borrowed-domain visitor. Returning true
continues via trail rollback; false stops. A visitor may block, retaining the
DFS stack, to implement interactive next-solution requests. Return codes are
`0` for exhaustive completion, `1` for visitor-requested stop, and `-1` for error.

Enumeration deduplicates identical edge tuples within each initial cell domain.
It disables the single-solution shortcut that arbitrarily picks one tile for an
isolated cell. The canonical decision solver and its trace formats retain their
previous behavior. The caller owns the count, so no fixed-width counter can
silently overflow inside the core.

Studio's worker counts with Python integers, publishes throttled progress
atomically, and waits for next/count commands inside the native visitor. Stop
and deadlines retain only a lower bound; exhaustive completion publishes the
exact total. Displayed solutions do not replace the original fixed constraints.
