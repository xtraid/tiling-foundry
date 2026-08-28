# PAP Render

[![CI](https://github.com/xtraid/PAP_render/actions/workflows/ci.yml/badge.svg)](https://github.com/xtraid/PAP_render/actions/workflows/ci.yml)

A command-line pixel art renderer that composites a scene from a tile-based background and a list of sprites, exporting the result as a PNG image.

**Status**: feature-complete. The code works and is tested; any future changes will be refactoring, cleanup, or optimization.

Tiling Foundry also supplies a separate presentation-only Wang backend. Its
default square path and explicit checked `--hex` view consume the same
versioned square JSON without importing the solver or changing this legacy
pixel-art pipeline.

## Output

![example render](output/example.png)

## Overview

- 16-color indexed palette (4 bit per pixel)
- Tile sheet: 64 tiles of 32×32 pixels in a 256×256 image
- Sprite sheet: 16 sprites of 64×64 pixels in a 256×256 image
- Frame buffer: 640×480 pixels (tile map 15×20)
- Sprite transformations: flip on x/y axis, rotation by 90/180/270 degrees
- Transparency via a designated palette index

## Usage

```bash
python main.py <palette.json> <scene.json> <tiles.bin> <sprites.bin> <output.png>
```

| Argument | Description |
|---|---|
| `palette.json` | 16 RGB colors |
| `scene.json` | transparent index, tile map, sprite list |
| `tiles.bin` | packed binary tile sheet (32768 bytes) |
| `sprites.bin` | packed binary sprite sheet (32768 bytes) |
| `output.png` | rendered output |

### Wang diagnostic rendering

From this directory, render a `wang-solution-v1` square document with the
default square geometry:

```bash
uv run --locked python wang_square.py \
  ../tests/fixtures/wang_solution_v1_square_sat.json \
  output/wang-square.png
```

Use the same command and the same square document for the pointy-top axial
view, enabled only by the explicit flag:

```bash
uv run --locked python wang_square.py \
  ../tests/fixtures/wang_solution_v1_square_sat.json \
  output/wang-hex.png \
  --hex
```

Optional `--pixels-per-cell N` and `--margin N` arguments control the dynamic
canvas. `N` is the square side in default mode and the integer hex radius in
hex mode. Inclusive coordinate offsets, including negative origins, do not
alter dense row-major placement. Holes use a neutral checkerboard. Each logical
edge color receives a deterministic, distinct RGB value, so the backend does
not collapse the contract's unbounded color IDs into the legacy 16-color
palette.

The square backend renders every active cell from its named `N`, `E`, `S`, and
`W` edge colors. Hex mode first invokes the standard-library-only reducer and
checker in `wang_hex_port.py`. With `(q,r)=(x,y)` and edge order
`(E,SE,SW,W,NW,NE)`, it maps `(N,E,S,W)` to
`(E,S,kappa,W,N,kappa)`, where `kappa=max(C)+1`, and then rasterizes the checked
in-memory view. No hex JSON or second command is created.

Both modes write the PNG with an atomic same-directory replace. Neither uses
`metadata` to select pixels, validates source SAT correctness, or loads
`libwang.so`/Z3. Boundary is pixel-neutral: hex mode retains and checks its
direction-preserving translation, while default square output remains
byte-for-byte unchanged. A successful PNG is presentation, not a proof;
correctness remains the responsibility of the independent Tiling Foundry
verifier before export.

Add `--explain` to a verified solution to show a neutral tile center, its
positional tile ID, colored `N,E,S,W` (or six hex) edge bands, emphasized
exposed boundary constraints, and the numeric palette legend:

```bash
uv run --locked python wang_square.py \
  ../tests/fixtures/wang_solution_v1_square_sat.json \
  output/wang-square-explain.png \
  --explain
```

Static pre-solver views consume a `wang-explain-manifest-v1` instead of a
solution. They are inherently explanatory, so they do not use `--explain`:

```bash
uv run --locked python wang_square.py \
  ../tests/fixtures/pipeline_sat_explain/manifest.json \
  output/formula.png \
  --view formula

uv run --locked python wang_square.py \
  ../tests/fixtures/pipeline_sat_explain/manifest.json \
  output/tileset.png \
  --view tileset

uv run --locked python wang_square.py \
  ../tests/fixtures/pipeline_sat_explain/manifest.json \
  output/region.png \
  --view region
```

`--view tileset` and `--view region` also accept `--hex`. Both invoke the pure
square-to-hex reducer and checker before rasterization. Formula view rejects
`--hex`; region view intentionally contains no assignment or partial solver
state.

An opt-in `wang-explain-manifest-v2` adds the construction provenance produced
by the native Yang–Zhang builder. Render its exact source/target signals,
adjacent-swap gadget spans, formula, and unassigned region with:

```bash
uv run --locked python wang_square.py \
  ../tests/fixtures/pipeline_sat_reduction_explain/manifest.json \
  output/reduction.png \
  --view reduction
```

Reduction spans describe the square construction itself, so this view rejects
`--hex`. The consumer verifies artifact hashes, formula and region identity,
the signal permutation, and gadget bounds without importing native code or
reconstructing builder geometry.

### Offline trace and algorithm animations

The animation modules keep state interpretation separate from image encoding.
`wang_trace.py` loads a hash-bound `wang-explain-manifest-v3` and independently
replays its `observed` native events once. `wang_trace_render.py` selects and
composes frames from those replayed states. `wang_animation.py` receives only
completed RGB frames and writes deterministic atomic PNGs, a contact sheet,
and a presentation-only GIF:

```bash
uv run --locked python wang_trace_render.py \
  ../tests/fixtures/pipeline_sat_solver_trace/manifest.json \
  output/solver-trace
```

The static projection of the same v3 manifest can also drive the existing
formula, tileset, region, and reduction views. It verifies every reference by
schema and hash but deliberately does not replay trace or solution content;
the trace consumer remains their semantic validator. This lets the root opt-in
dossier generator reuse one trace bundle without synthesizing a second v1/v2
manifest. The renderer still imports neither native code nor Z3, and it does
not own LaTeX or report metadata.

Z3 uses a separate `encoding-order` summary. The renderer shows the explicit
project-owned row-major constraint construction and returned model, never an
internal Z3 search or debug trace:

```bash
uv run --locked python wang_z3_summary.py \
  ../tests/fixtures/pipeline_sat_z3/wang-z3.json \
  output/z3-encoding
```

Three additional commands make their source semantics explicit: builder and
hex are `canonical-example` views over versioned data and pure checked
transformation respectively; optimized is a `didactic` overview whose dated
reports, not the animation, establish performance.

```bash
uv run --locked python wang_algorithm_animation.py builder \
  ../tests/fixtures/pipeline_sat_reduction_explain/manifest.json \
  output/builder-routing
uv run --locked python wang_algorithm_animation.py optimized \
  output/optimized-mechanisms
uv run --locked python wang_algorithm_animation.py hex \
  ../tests/fixtures/wang_solution_v1_square_sat.json \
  output/square-to-hex
```

All loaders reject unknown fields and identity drift before rasterization. No
animation module imports native code; trace rendering and algorithm rendering
do not import Z3. PNG sources are the deterministic test oracles. GIFs exist
only for presentation, and every published animation has a static fallback.

## Input Format

### palette.json

Array of 16 RGB colors:

```json
[
  [0, 0, 0],
  [255, 0, 0],
  ...
]
```

### scene.json

```json
{
  "transparent_index": 0,
  "tile_map": [[1, 0, 2, ...], ...],
  "sprites": [
    { "id": 0, "x": 100, "y": 80, "flip_x": false, "flip_y": false, "rotation": 0 }
  ]
}
```

- `transparent_index`: palette index (0–15) treated as transparent for all sprites
- `tile_map`: 15×20 matrix of tile IDs (0–63)
- `sprites`: ordered list — draw order determines z-order

### .bin files

Packed binary, 256×256 pixels stored as 32768 bytes. Each byte contains 2 pixels:
- high nibble (bits 7–4): first pixel → palette index 0–15
- low nibble (bits 3–0): second pixel → palette index 0–15

## Architecture

| Class | Responsibility | Status |
|---|---|---|
| `Palette` | Reads and validates `palette.json`, maps index → RGB | Done |
| `VirtualVRAM` | Loads `.bin` files, decodes nibble-packed pixels into index matrices; exposes `get_tile(id)` and `get_sprite(id)` | Done |
| `SceneParser` | Reads and validates `scene.json`, returns `transparent_index`, `tile_map`, and `sprites` | Done |
| `Blitter` | Composites tiles and sprites onto a 640×480 frame buffer; applies flip/rotation and transparency | Done |
| `RenderingPipeline` | Orchestrates the full render and exports PNG | Done |

Custom exceptions (`PaletteError`, `VRAMError`, `SceneError`, `BlitterException`, `RenderingException`) are raised for all invalid input cases. `FileNotFoundError` propagates with a descriptive message from all file-loading classes.

## API Reference

### Palette

```python
Palette(path: str)
```

| Member | Type | Description |
|---|---|---|
| `data` | `np.ndarray (16, 3) uint8` | Full palette array |
| `__getitem__(idx: int)` | `np.ndarray (3,) uint8` | RGB color at palette index `idx` ∈ [0, 15] |
| `print_palette()` | `None` | Prints palette to stdout |

Raises `PaletteError` on invalid palette. Raises `FileNotFoundError` if file is missing.

---

### VirtualVRAM

```python
VirtualVRAM(path_t: str, path_s: str)
```

| Member | Type | Description |
|---|---|---|
| `get_tile(idx: int)` | `np.ndarray (32, 32) uint8` | Palette-index matrix for tile `idx` ∈ [0, 63] |
| `get_sprite(idx: int)` | `np.ndarray (64, 64) uint8` | Palette-index matrix for sprite `idx` ∈ [0, 15] |

Raises `VRAMError` on invalid file size. Raises `FileNotFoundError` if a file is missing.

---

### SceneParser

```python
SceneParser(path: str)
```

| Member | Type | Description |
|---|---|---|
| `transparent_index` | `int` | Palette index treated as transparent, ∈ [0, 15] |
| `tile_map` | `np.ndarray (15, 20) uint8` | Grid of tile IDs |
| `sprites` | `list[dict]` | Ordered sprite list; each dict has `id`, `x`, `y`, `flip_x`, `flip_y`, `rotation` |

Raises `SceneError` on invalid scene. Raises `FileNotFoundError` if file is missing.

---

### Blitter

```python
Blitter(vram: VirtualVRAM, asset_type: str, idx: int, transparent_index: int, buffer: np.ndarray)
```

| Member | Type | Description |
|---|---|---|
| `transparent_index` | `int` | Palette index treated as transparent |
| `_buffer` | `np.ndarray (480, 640) uint8` | Shared frame buffer written in place |
| `blit_tile(row: int, col: int)` | `None` | Copies tile onto buffer at tilemap cell (`row` ∈ [0,14], `col` ∈ [0,19]) |
| `blit_sprite(x, y, flip_x, flip_y, rotation)` | `None` | Transforms and blits sprite at top-left `(x, y)`; transparent pixels are skipped |
| `_transform(sprite_matrix, flip_x, flip_y, rotation)` | `np.ndarray (64, 64) uint8` | Applies flip then rotation to a sprite matrix |
| `_clip(x: int, y: int)` | `tuple[tuple[slice, slice], tuple[slice, slice]]` | Returns `(dst, src)` slice pairs for a 64×64 sprite at `(x, y)` |

Raises `BlitterException` on invalid arguments.

---

### RenderingPipeline

```python
RenderingPipeline(palette_path, scene_path, tiles_path, sprites_path, output_path)
```

| Member | Type | Description |
|---|---|---|
| `get_buf()` | `np.ndarray (480, 640) uint8` | classmethod — creates a blank frame buffer |
| `render()` | `None` | Runs full pipeline: compose tiles + sprites, export PNG |
| `_compose(buf: np.ndarray)` | `None` | Fills `buf` with tiles then sprites in scene order |
| `_export(buf: np.ndarray)` | `None` | Maps palette indexes → RGB, saves PNG via Pillow |

Raises `RenderingException` on pipeline errors.

## Requirements

- Python ≥ 3.14
- `Pillow` used only for PNG export
- `numpy` arrays with `np.uint8` dtype

## Project Structure

```
.
├── main.py               # CLI entry point
├── classes.py            # Palette, VirtualVRAM, SceneParser, Blitter, RenderingPipeline
├── tests.py              # Test suite (144 tests, all passing)
├── wang_square.py         # One Wang CLI: square default, explicit hex raster
├── wang_hex_port.py       # Pure square-to-hex reducer and independent checker
├── wang_snapshot.py       # Strict static-snapshot consumer and view compositor
├── wang_explain.py        # Shared colored-edge and legend drawing primitives
├── wang_trace.py          # Strict observed-trace loader and offline replay
├── wang_trace_render.py   # Trace frame selection and composition CLI
├── wang_z3_summary.py     # Encoding-order summary consumer and compositor
├── wang_animation.py      # Deterministic PNG/contact-sheet/GIF encoder
├── wang_algorithm_animation.py # Canonical and didactic algorithm views
├── test_wang_square.py    # Square loader, raster, isolation, CLI, and failures
├── test_wang_hex.py       # Port proof obligations, hex raster, golden, and CLI
├── test_wang_snapshot.py  # Snapshot contracts, views, isolation, and goldens
├── test_wang_trace.py     # Hash-bound replay, isolation, and byte stability
├── test_wang_z3_summary.py # Fixed encoding summaries and byte stability
├── test_wang_algorithm_animation.py # Source checks and animation goldens
├── input/                # Example input files (palette, scene, tiles, sprites)
├── output/               # Rendered PNG output goes here
├── test_data/
│   ├── wang_solution_v1_square_sat.png # Square golden for the Wang fixture
│   ├── wang_solution_v1_hex_sat.png    # Pointy-top hex golden for the same fixture
│   ├── pipeline_sat_reduction.png      # Native reduction-provenance golden
│   ├── palette_ok.json             # Valid 16-color palette
│   ├── palette_wrong_count.json    # Only 3 colors (invalid)
│   ├── palette_wrong_value.json    # Component > 255 (invalid)
│   ├── test_boundary_values/       # Per-test directories generated at runtime
│   ├── test_vram_load_ok/          # Each contains the files written by that test
│   └── ...                         # (one subdirectory per test that writes files)
└── pyproject.toml
```

## Tests

```bash
uv run --locked pytest -q
```

The complete isolated suite has 262 tests: the 144 preserved legacy tests
below, 45 Wang square tests, 24 square-to-hex/hex-raster tests, 29 static
snapshot/explainability tests, and 20 trace/Z3/algorithm-animation tests.
To run only the original upstream suite:

```bash
uv run --locked pytest tests.py -v
```

The 144 legacy tests cover all original classes:

**Palette (18 tests)**
- Happy path: load, `__getitem__` first/last, boundary values (0 and 255)
- File errors: file not found, invalid JSON
- Wrong color count: too few, too many, empty
- Wrong color format: fewer than 3 components, more than 3 components
- Out-of-range values: above 255, negative, exact 255
- `__getitem__` bounds: index 16 and index −1

**VirtualVRAM — decode (8 tests)**
- Happy path: load, shape and dtype, all-zeros decode, all-`0xFF` decode, nibble split (`0xAB` → 10, 11)
- File errors: tiles not found, sprites not found
- Wrong size: tiles file too short, sprites file too short

**VirtualVRAM — get_tile (7 tests)**
- Happy path: shape and dtype, first tile (id 0) all 15, last tile (id 63) all 15
- Isolation: tile 5 filled, tile 0 untouched
- Errors: non-int id, id 64, id −1

**VirtualVRAM — get_sprite (7 tests)**
- Happy path: shape and dtype, first sprite (id 0) all 15, last sprite (id 15) all 15
- Isolation: sprite 7 filled, sprite 0 untouched
- Errors: non-int id, id 16, id −1

**SceneParser (33 tests)**
- Happy path: load, transparent_index, tile_map shape and dtype, sprites list, boundary transparent_index 15, empty sprites, sprite fields
- File errors: file not found, invalid JSON
- Missing keys: transparent_index, tile_map, sprites
- transparent_index errors: not int, too high (16), negative
- tile_map errors: wrong rows, wrong cols, jagged rows, value 64, negative value, value not int
- sprites errors: not a list, missing field, id not int, id out of range, x/y not int, flip_x/flip_y not bool, rotation not int, rotation invalid (45)

**Blitter (49 tests)**
- init/_validate: valid tile/sprite, all error cases (asset_type, idx, transparent_index)
- blit_tile: correct write and position, all error cases (row/col type and bounds)
- _transform: identity, flip_x, flip_y, rotation 90/180/270, flip_x+y
- _clip: fully inside, centered, clipping on all 4 sides, sprite fully outside frame
- blit_sprite: all-opaque, all-transparent, mixed transparency, position, clipping on all 4 sides, fully outside frame on all 4 sides, transform+clip combined, z-order

**RenderingPipeline (18 tests)**
- get_buf: shape, dtype, all zeros, independence between calls
- __repr__: all 5 paths present
- _export: file created, image size 640×480, pixel color maps correctly from palette, bad output path raises RenderingException
- _compose: tiles written, full tile_map filled, sprite over tile, transparent sprite not drawn, sprite z-order, sprite transformation applied, sprite clipping at frame edge
- render(): output file created, output size 640×480

**main.py (4 tests)**
- `--help` exits with code 0
- missing arguments exits with non-zero code
- valid input runs and creates output file
- invalid file paths propagate `FileNotFoundError`
