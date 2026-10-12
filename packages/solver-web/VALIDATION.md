# Runtime-sized WebAssembly domains

The former browser limit came from one `uint32_t` per cell, fixed compatibility
arrays in `src/solver/solver_serial.c`, the browser C bridge, JavaScript shifts
by tile ID, and Studio's active-tile validation. The canonical Yang–Zhang tiles
and native solvers still use their existing representations.

## Scope and contract

The web build continues to share `core/tile.c`, `core/region.c`,
`solver/solver_serial.c`, `solver/byte_support_table.c`, both trace modules and
`verify/verify_tiling.c` with native builds. None of those files, native headers,
the builder or native Makefile changed. Only the web build links the new
`packages/solver-web/dynamic.c`. Inputs within the native limits (32 tiles, 16 colors, 4096 cells) take the
existing native-core path. Larger inputs use a private graph solver for both browser selections;
`optimized` above 32 does not imply native byte-support/MRV-index optimizations.

Domains have `ceil(tile_count/32)` words per cell. Every shift is modulo 32 and
tail bits are validated. Array multiplication and trail growth are checked;
allocation failure returns an error, never UNSAT. The engine performs root
restriction, allowed duplicate-tuple elimination, fixed-point arc consistency,
MRV, iterative DFS and rollback of changed words. Every complete assignment is
checked against original domains, boundaries and reciprocal adjacency before
publication. Decisions live on the heap, avoiding recursion limits.

The public JS API remains version 1 (edge arrays in, numeric indices out).
Private Wasm ABI 3 transfers multiword domains and optional 32-bit colors; the updated Worker decodes them
without converting IDs to `uint8_t` or truncating them to JavaScript bitmasks.
Square instances above 32 tiles use dense graph adjacency. Buffer ownership,
Asyncify pause/resume and Worker Stop/deadline behavior are unchanged. See the
package README for the precise ABI and resource budgets.

## Initial multiword validation on 2026-10-12

- `make -j4 check`: passed C checks, shared/serial/OpenMP builds, benchmark smoke,
  solver comparisons and all 252 Python tests. Native source hashes also match
  the source hashes of Studio's previous installed package.
- `node tests/test_solver_web.mjs PACKAGE`: passed 500 existing randomized
  differential instances and 100 new 65-tile instances against an independent
  exhaustive polygon oracle, for both solver selections.
- Cardinalities 23, 31, 32, 33, 64, 65, 96, 97, 257 and 1025: passed SAT/UNSAT,
  enumeration, highest-ID pins and asynchronous pause in all five geometries.
- The actual canonical 23-tile fixture (emitted from `TILESET`) passed SAT and
  UNSAT comparisons. Counts are independently compared, not just SAT flags.
- Actual Wasm odd cycles that are arc-consistent but UNSAT, and branches that
  fail before a later SAT witness, passed across word boundaries. A failed
  allocation above the Wasm memory ceiling returned null; a subsequent small allocation succeeded.
- `tests/test_web_dynamic.c` compiled with AddressSanitizer and UBSan passed,
  including leak checking, every reached allocation failure, malformed tail
  bits, odd/even cycles and repeated trail reallocations on a 1024-cell ring.
- Studio's Chromium tests passed actual Add/edit controls, JSON download/import,
  23/32/33/64/65 tiles, both solver selections, SAT/UNSAT, highest-ID rendering
  and canvas export in all five geometries. Catalogs of 65 generalized atoms
  also survived serialization and solved through Wasm. Runtime ABI 2 is asserted
  in the UI session; console errors and native API calls fail the harness.
- Studio's six Node editor/geometry/generalized suites and 14 Python tests passed.

The browser-only memory test is wired into the package CI. Reproduce it with:

```sh
cc -Iinclude -std=c17 -Wall -Wextra -Werror -O1 -g \
  -fsanitize=address,undefined tests/test_web_dynamic.c -o build/test_web_dynamic
build/test_web_dynamic
```

## Remaining resource limits

There is no tileset-cardinality cap in the web API or engine. Available address
space/memory, a 2 GiB Wasm ceiling, 65536 used colors/palette entries, 65536 active
cells and configurable session deadlines still apply. Color support uses dynamic
stamp arrays; the wide boundary sentinel is UINT32_MAX, so 255 remains a color. Large-domain search
is not promised to match the specialized small-domain optimized engine.
Studio retains its 5 MB import budget and its separate 32-cell limit per single
generalized piece; multiple pieces can contribute more than 32 active atoms.
Native runtime-tileset APIs and Studio's optional native connector retain 32.
Validation is local Chromium/static hosting; no public-site deployment was made.

## Small-tileset benchmark

`node tests/benchmark_solver_web.mjs OLD_PACKAGE NEW_PACKAGE`, Node 26.8.2,
Emscripten 4.0.23, 2x2 regions, 200 warmups, nine alternating samples of 1000
complete enumerations per engine. Baseline is Studio's previously pinned
`0.1.0-dev.e74e7f2776b9`. The final web build enables link-time optimization
(`-flto`) only in `build_solver_web.py`; it removed a 9–14% slowdown observed in
intermediate non-LTO builds. Native compiler flags remain unchanged.

| Case | Old median ms / 1000 | New median ms / 1000 | New / old |
| --- | ---: | ---: | ---: |
| Yang–Zhang 23 Reference | 152.35 | 145.77 | 0.957 |
| Yang–Zhang 23 Optimized | 162.25 | 160.70 | 0.990 |
| 32 Reference | 880.74 | 846.74 | 0.961 |
| 32 Optimized | 887.11 | 866.06 | 0.976 |

Counts matched exactly: 608 and 4096 configurations per enumeration. No
regression was observed in these measured cases; this is a local microbenchmark,
not a guarantee for all workloads or browser engines.

## Color and release consolidation

The current regression suite additionally covers 17, 33, 256, 257 and 1025
colors in all five geometries, adjacent SAT/UNSAT, high palette indices and
sparse square regions. Native sanitizer tests cover wide colors through 65535,
boundary sentinel separation and allocation failures. Release archives normalize
tar/gzip metadata and require the pinned Emscripten 4.0.23 toolchain.
