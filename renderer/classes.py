import numpy as np
import json
from PIL import Image


class PaletteError(Exception):
    pass


class Palette:
    def __init__(self, path):
        self.__path = path
        self.data = self._load_json()

    # Reads and validates a palette JSON file.
    # Input: self.__path — path to a JSON file containing a list of 16 [R, G, B] colors.
    # Output: np.ndarray of shape (16, 3) dtype uint8 with the palette colors.
    def _load_json(self):
        try:
            with open(self.__path) as f:
                raw = json.load(f)
        except FileNotFoundError as e:
            raise FileNotFoundError(f"palette file not found: {self.__path!r}") from e
        except json.JSONDecodeError as e:
            raise PaletteError(f"file JSON not valid: {e}") from e
        if len(raw) != 16:
            raise PaletteError(f"palette must contain 16 colors, trovati {len(raw)}")
        for i, color in enumerate(raw):
            if len(color) != 3:
                raise PaletteError(
                    f"color {i}: must contain 3 component for RGB, found {len(color)}"
                )
            for component in color:
                if not isinstance(component, int) or isinstance(component, bool):
                    raise PaletteError(
                        f"color {i}: component must be int, got {type(component).__name__}"
                    )
                if not 0 <= component <= 255:
                    raise PaletteError(
                        f"color {i}: value {component} out of bounds [0, 255]"
                    )
        return np.array(raw, np.uint8)

    # Returns an unambiguous string representation of the palette.
    # Input: none.
    # Output: str.
    def __repr__(self):
        return f"Palette(path={self.__path!r})"

    # Prints the full palette to stdout.
    # Input: none.
    # Output: none.
    def print_palette(self):
        print(self.data)

    # Returns the RGB color at the given palette index.
    # Input: idx — integer in [0, 15].
    # Output: np.ndarray of shape (3,) dtype uint8 with [R, G, B] values.
    def __getitem__(self, idx):
        if not isinstance(idx, int):
            raise PaletteError(f"index must be int, got {type(idx).__name__}")
        if not 0 <= idx <= 15:
            raise PaletteError(f"index {idx} out of range [0, 15]")
        return self.data[idx]


class VRAMError(Exception):
    pass


class VirtualVRAM:
    def __init__(self, path_t, path_s):
        self.__path_tiles = path_t
        self.__path_sprites = path_s
        self.__tiles, self.__sprites = self._load_bin()
        self._tiles_mx = self._decode(self.__tiles)
        self._sprites_mx = self._decode(self.__sprites)

    # Reads the tile sheet and sprite sheet binary files.
    # Input: self.__path_tiles, self.__path_sprites — paths to nibble-packed binary files.
    # Output: tuple of two bytes objects (tiles_raw, sprites_raw).
    def _load_bin(self):
        try:
            with open(self.__path_tiles, "rb") as ftile:
                tiles = ftile.read()
        except FileNotFoundError as e:
            raise FileNotFoundError(
                f"tiles file not found: {self.__path_tiles!r}"
            ) from e
        except OSError as e:
            raise VRAMError(f"cannot open {self.__path_tiles!r}: {e}") from e
        try:
            with open(self.__path_sprites, "rb") as fsprite:
                sprites = fsprite.read()
        except FileNotFoundError as e:
            raise FileNotFoundError(
                f"sprites file not found: {self.__path_sprites!r}"
            ) from e
        except OSError as e:
            raise VRAMError(f"cannot open {self.__path_sprites!r}: {e}") from e
        return tiles, sprites

    # Decodes a nibble-packed binary buffer into a 256x256 matrix of palette indexes.
    # Input: raw — bytes of exactly 32768 bytes (2 pixels per byte, high nibble first).
    # Output: np.ndarray of shape (256, 256) dtype uint8 with palette indexes 0-15.
    def _decode(self, raw):
        if len(raw) != 32768:
            raise VRAMError(f"invalid file size: expected 32768 bytes, got {len(raw)}")
        data = np.frombuffer(raw, dtype=np.uint8)
        return np.stack([data >> 4, data & 0x0F], axis=1).ravel().reshape(256, 256)

    # Returns the tile at the given index as a palette-index matrix.
    # Input: idx — integer in [0, 63].
    # Output: np.ndarray of shape (32, 32) dtype uint8 with palette indexes 0-15.
    def get_tile(self, idx):
        if not isinstance(idx, int):
            raise VRAMError(f"index must be int, got {type(idx).__name__}")
        if not 0 <= idx <= 63:
            raise VRAMError(f"index must be in [0, 63], got {idx}")
        row = idx // 8
        col = idx % 8
        return self._tiles_mx[row * 32 : row * 32 + 32, col * 32 : col * 32 + 32]

    # Returns the sprite at the given index as a palette-index matrix.
    # Input: idx — integer in [0, 15].
    # Output: np.ndarray of shape (64, 64) dtype uint8 with palette indexes 0-15.
    def get_sprite(self, idx):
        if not isinstance(idx, int):
            raise VRAMError(f"index must be int, got {type(idx).__name__}")
        if not 0 <= idx <= 15:
            raise VRAMError(f"index must be in [0, 15], got {idx}")
        row = idx // 4
        col = idx % 4
        return self._sprites_mx[row * 64 : row * 64 + 64, col * 64 : col * 64 + 64]

    def __repr__(self):
        return (
            f"VirtualVRAM(path_t={self.__path_tiles!r}, path_s={self.__path_sprites!r})"
        )


class SceneError(Exception):
    pass


class SceneParser:
    def __init__(self, path):
        self.__path = path
        raw = self._load_descriptor()
        self.transparent_index, self.tile_map, self.sprites = self._validate(raw)

    # Reads the scene JSON file.
    # Input: self.__path — path to a JSON file describing the scene.
    # Output: dict with the raw parsed JSON content.
    def _load_descriptor(self):
        try:
            with open(self.__path) as f:
                raw = json.load(f)
        except FileNotFoundError as e:
            raise FileNotFoundError(f"scene file not found: {self.__path!r}") from e
        except json.JSONDecodeError as e:
            raise SceneError(f"file JSON not valid: {e}") from e
        for sprite in raw.get("sprites", []):
            if "flip_h" in sprite:
                sprite["flip_x"] = sprite.pop("flip_h")
            if "flip_v" in sprite:
                sprite["flip_y"] = sprite.pop("flip_v")
        return raw

    # Validates the raw scene dict and returns typed, checked fields.
    # Input: raw — dict from _load_descriptor.
    # Output: tuple (transparent_index: int, tile_map: np.ndarray (15,20) uint8, sprites: list of dict).
    def _validate(self, raw):
        for key in ("transparent_index", "tile_map", "sprites"):
            if key not in raw:
                raise SceneError(f"missing key: {key!r}")
        transparent_idx = raw["transparent_index"]
        tile_map = raw["tile_map"]
        sprites = raw["sprites"]
        if not isinstance(transparent_idx, int) or isinstance(transparent_idx, bool):
            raise SceneError(
                f"transparent_index must be int, got {type(transparent_idx).__name__}"
            )
        if not 0 <= transparent_idx <= 15:
            raise SceneError(
                f"transparent_index must be in [0, 15], got {transparent_idx}"
            )
        if len(tile_map) != 15:
            raise SceneError(f"tile_map must have 15 rows, got {len(tile_map)}")
        for i, row in enumerate(tile_map):
            if len(row) != 20:
                raise SceneError(
                    f"tile_map row {i} must have 20 columns, got {len(row)}"
                )
            for j, v in enumerate(row):
                if not isinstance(v, int) or isinstance(v, bool):
                    raise SceneError(
                        f"tile_map[{i}][{j}] must be int, got {type(v).__name__}"
                    )
                if not 0 <= v <= 63:
                    raise SceneError(
                        f"tile_map[{i}][{j}] value {v} out of range [0, 63]"
                    )
        if not isinstance(sprites, list):
            raise SceneError(f"sprites must be a list, got {type(sprites).__name__}")
        for i, sprite in enumerate(sprites):
            for key in ("id", "x", "y", "flip_x", "flip_y", "rotation"):
                if key not in sprite:
                    raise SceneError(f"sprite {i}: missing key {key!r}")
            if not isinstance(sprite["id"], int) or isinstance(sprite["id"], bool):
                raise SceneError(
                    f"sprite {i}: id must be int, got {type(sprite['id']).__name__}"
                )
            if not 0 <= sprite["id"] <= 15:
                raise SceneError(
                    f"sprite {i}: id must be in [0, 15], got {sprite['id']}"
                )
            if not isinstance(sprite["x"], int) or isinstance(sprite["x"], bool):
                raise SceneError(
                    f"sprite {i}: x must be int, got {type(sprite['x']).__name__}"
                )
            if not isinstance(sprite["y"], int) or isinstance(sprite["y"], bool):
                raise SceneError(
                    f"sprite {i}: y must be int, got {type(sprite['y']).__name__}"
                )
            if not isinstance(sprite["flip_x"], bool):
                raise SceneError(
                    f"sprite {i}: flip_x must be bool, got {type(sprite['flip_x']).__name__}"
                )
            if not isinstance(sprite["flip_y"], bool):
                raise SceneError(
                    f"sprite {i}: flip_y must be bool, got {type(sprite['flip_y']).__name__}"
                )
            if not isinstance(sprite["rotation"], int) or isinstance(sprite["rotation"], bool):
                raise SceneError(
                    f"sprite {i}: rotation must be int, got {type(sprite['rotation']).__name__}"
                )
            if sprite["rotation"] not in {0, 90, 180, 270}:
                raise SceneError(
                    f"sprite {i}: rotation must be in {{0, 90, 180, 270}}, got {sprite['rotation']}"
                )
        return transparent_idx, np.array(tile_map, np.uint8), sprites

    # Returns an unambiguous string representation of the scene parser.
    # Input: none.
    # Output: str.
    def __repr__(self):
        return f"SceneParser(path={self.__path!r})"


class BlitterException(Exception):
    pass


FRAME_W = 640
FRAME_H = 480


class Blitter:
    def __init__(self, vram, asset_type, idx, transparent_index, buffer):
        self.__vram = vram
        self.__asset_type, self.__position, self.transparent_index = self._validate(
            asset_type, idx, transparent_index
        )
        self._buffer = buffer

    # Validates asset_type, idx and transparent_index.
    # Input: asset_type — "tile" or "sprite"; idx — int index into the respective sheet; transparent_index — palette index 0-15.
    # Output: tuple (asset_type: str, idx: int, transparent_index: int).
    def _validate(self, asset_type, idx, transparent_index):
        if asset_type not in {"tile", "sprite"}:
            raise BlitterException(
                f"asset_type must be 'tile' or 'sprite', got {asset_type!r}"
            )
        if not isinstance(idx, int):
            raise BlitterException(f"idx must be int, got {type(idx).__name__}")
        if asset_type == "tile" and not 0 <= idx <= 63:
            raise BlitterException(f"tile idx must be in [0, 63], got {idx}")
        if asset_type == "sprite" and not 0 <= idx <= 15:
            raise BlitterException(f"sprite idx must be in [0, 15], got {idx}")
        if not isinstance(transparent_index, int):
            raise BlitterException(
                f"transparent_index must be int, got {type(transparent_index).__name__}"
            )
        if not 0 <= transparent_index <= 15:
            raise BlitterException(
                f"transparent_index must be in [0, 15], got {transparent_index}"
            )
        return asset_type, idx, transparent_index

    # Blits the tile at self.__position onto the frame buffer at the given tilemap cell.
    # Input: row — int in [0, 14]; col — int in [0, 19].
    # Output: none (writes to self._buffer in place).
    def blit_tile(self, row, col):
        if not isinstance(row, int):
            raise BlitterException(f"row type must be int, got {type(row).__name__}")
        if not isinstance(col, int):
            raise BlitterException(f"col type must be int, got {type(col).__name__}")
        if not 0 <= row <= 14:
            raise BlitterException(
                f"inserted row not valid, must be in [0,14], got {row}"
            )
        if not 0 <= col <= 19:
            raise BlitterException(
                f"inserted col not valid, must be in [0,19], got {col}"
            )
        tile_buf = self.__vram.get_tile(self.__position).copy()
        self._buffer[row * 32 : row * 32 + 32, col * 32 : col * 32 + 32] = tile_buf

    # Applies flip and rotation transformations to a sprite matrix.
    # Input: sprite_matrix — np.ndarray (64, 64) uint8; flip_x, flip_y — bool; rotation — 0/90/180/270.
    # Output: np.ndarray (64, 64) uint8 transformed.
    def _transform(self, sprite_matrix, flip_x, flip_y, rotation):
        m = sprite_matrix
        if flip_x:
            m = np.fliplr(m)
        if flip_y:
            m = np.flipud(m)
        if rotation != 0:
            m = np.rot90(m, rotation // 90)
        return m

    # Computes valid src/dst slice pairs to copy a 64x64 sprite at (x, y) into the frame buffer.
    # Input: x, y — top-left position of the sprite in the frame buffer (can be negative).
    # Output: tuple (dst, src) where each is a tuple of two slice objects (rows, cols).
    # A sprite fully off-screen yields an empty destination; that case is returned as
    # empty slices, since otherwise the negative width would produce inconsistent src
    # slices (e.g. slice(0, -60) is not empty in numpy) and crash blit_sprite.
    def _clip(self, x, y):
        dst_r0 = max(0, y)
        dst_r1 = min(FRAME_H, y + 64)
        dst_c0 = max(0, x)
        dst_c1 = min(FRAME_W, x + 64)
        if dst_r1 <= dst_r0 or dst_c1 <= dst_c0:
            empty = (slice(0, 0), slice(0, 0))
            return empty, empty
        src_r0 = max(0, -y)
        src_r1 = src_r0 + (dst_r1 - dst_r0)
        src_c0 = max(0, -x)
        src_c1 = src_c0 + (dst_c1 - dst_c0)
        return (slice(dst_r0, dst_r1), slice(dst_c0, dst_c1)), (
            slice(src_r0, src_r1),
            slice(src_c0, src_c1),
        )

    # Blits the sprite at self.__position onto the frame buffer with transformations and transparency.
    # Input: x, y — top-left position in the frame buffer (can be negative); flip_x, flip_y — bool; rotation — 0/90/180/270.
    # Output: none (writes to self._buffer in place).
    def blit_sprite(self, x, y, flip_x, flip_y, rotation):
        sprite_buf = self.__vram.get_sprite(self.__position).copy()
        sprite_buf = self._transform(sprite_buf, flip_x, flip_y, rotation)
        mask = sprite_buf != self.transparent_index
        dst, src = self._clip(x, y)
        self._buffer[dst][mask[src]] = sprite_buf[src][mask[src]]

    def __repr__(self):
        return f"Blitter(asset_type={self.__asset_type!r}, position={self.__position})"


class RenderingException(Exception):
    pass


class RenderingPipeline:
    def __init__(self, palette_path, scene_path, tiles_path, sprites_path, output_path):
        self._palette_path = palette_path
        self._scene_path = scene_path
        self._tiles_path = tiles_path
        self._sprites_path = sprites_path
        self._output_path = output_path

    # Returns an unambiguous string representation of the rendering pipeline.
    # Input: none.
    # Output: str.
    def __repr__(self):
        return (
            f"RenderingPipeline(palette_path={self._palette_path!r}, "
            f"scene_path={self._scene_path!r}, tiles_path={self._tiles_path!r}, "
            f"sprites_path={self._sprites_path!r}, output_path={self._output_path!r})"
        )

    # Runs the full pipeline: compose tiles and sprites onto the buffer, then export.
    # Input: none.
    # Output: none.
    def render(self):
        buf = RenderingPipeline.get_buf()
        self._compose(buf)
        self._export(buf)

    # Fills buf with all tiles from tile_map, then all sprites in scene order.
    # Input: buf — np.ndarray (FRAME_H, FRAME_W) uint8, written in place.
    # Output: none.
    def _compose(self, buf):
        vr = VirtualVRAM(self._tiles_path, self._sprites_path)
        sp = SceneParser(self._scene_path)
        for r, row in enumerate(sp.tile_map):
            for c, tile_id in enumerate(row):
                Blitter(vr, "tile", int(tile_id), sp.transparent_index, buf).blit_tile(r, c)
        for sprite in sp.sprites:
            Blitter(vr, "sprite", sprite["id"], sp.transparent_index, buf).blit_sprite(
                sprite["x"], sprite["y"], sprite["flip_x"], sprite["flip_y"], sprite["rotation"]
            )

    # Maps palette indexes in buf to RGB and saves the result as PNG.
    # Input: buf — np.ndarray (FRAME_H, FRAME_W) uint8 with palette indexes.
    # Output: none (writes file to self._output_path).
    def _export(self, buf):
        palette = Palette(self._palette_path)
        img = Image.fromarray(palette.data[buf])
        try:
            img.save(self._output_path)
        except (OSError, ValueError) as e:
            raise RenderingException(
                f"cannot save output PNG to {self._output_path!r}: {e}"
            ) from e

    # Creates and returns a blank frame buffer.
    # Input: none.
    # Output: np.ndarray of shape (FRAME_H, FRAME_W) dtype uint8, all zeros.
    @classmethod
    def get_buf(cls):
        return np.zeros((FRAME_H, FRAME_W), dtype=np.uint8)
