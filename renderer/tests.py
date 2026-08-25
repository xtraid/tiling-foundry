# %%
import sys
import pytest
import json
import numpy as np
from pathlib import Path
from PIL import Image as PILImage
from classes import Palette, PaletteError, VirtualVRAM, VRAMError, SceneParser, SceneError, Blitter, BlitterException, RenderingPipeline, RenderingException, FRAME_W, FRAME_H
from main import main

VALID = "test_data/palette_ok.json"


@pytest.fixture
def test_dir(tmp_path):
    # File generati dai test finiscono nella tmp dir per-test di pytest,
    # non nella cartella del repo.
    return tmp_path


def make_tmp(base_dir, data):
    f = base_dir / "palette.json"
    f.write_text(json.dumps(data))
    return str(f)


# -- happy path ---------------------------------------------------------------

def test_load_ok():
    p = Palette(VALID)
    assert p.data.shape == (16, 3)
    assert p.data.dtype == np.uint8

def test_getitem_first():
    p = Palette(VALID)
    assert list(p[0]) == [0, 0, 0]

def test_getitem_last():
    p = Palette(VALID)
    assert list(p[15]) == [255, 128, 0]

def test_boundary_values(test_dir):
    data = [([0, 0, 0] if i % 2 == 0 else [255, 255, 255]) for i in range(16)]
    p = Palette(make_tmp(test_dir, data))
    assert list(p[0]) == [0, 0, 0]
    assert list(p[1]) == [255, 255, 255]


# -- file errors --------------------------------------------------------------

def test_file_not_found():
    with pytest.raises(FileNotFoundError):
        Palette("non_esiste.json")

def test_invalid_json(test_dir):
    f = test_dir / "palette.json"
    f.write_text("questo non e json {{{")
    with pytest.raises(PaletteError):
        Palette(str(f))


# -- wrong color count --------------------------------------------------------

def test_too_few_colors(test_dir):
    data = [[0, 0, 0]] * 3
    with pytest.raises(PaletteError):
        Palette(make_tmp(test_dir, data))

def test_too_many_colors(test_dir):
    data = [[0, 0, 0]] * 17
    with pytest.raises(PaletteError):
        Palette(make_tmp(test_dir, data))

def test_empty_palette(test_dir):
    with pytest.raises(PaletteError):
        Palette(make_tmp(test_dir, []))


# -- wrong color format -------------------------------------------------------

def test_color_too_few_components(test_dir):
    data = [[0, 0]] + [[0, 0, 0]] * 15
    with pytest.raises(PaletteError):
        Palette(make_tmp(test_dir, data))

def test_color_too_many_components(test_dir):
    data = [[0, 0, 0, 0]] + [[0, 0, 0]] * 15
    with pytest.raises(PaletteError):
        Palette(make_tmp(test_dir, data))


# -- out of range values ------------------------------------------------------

def test_value_above_255(test_dir):
    data = [[300, 0, 0]] + [[0, 0, 0]] * 15
    with pytest.raises(PaletteError):
        Palette(make_tmp(test_dir, data))

def test_value_negative(test_dir):
    data = [[-1, 0, 0]] + [[0, 0, 0]] * 15
    with pytest.raises(PaletteError):
        Palette(make_tmp(test_dir, data))

# C4 regression: a color component must be an integer (the PDF says integers).
def test_value_float_component(test_dir):
    data = [[255.5, 0, 0]] + [[0, 0, 0]] * 15
    with pytest.raises(PaletteError):
        Palette(make_tmp(test_dir, data))

def test_value_bool_component(test_dir):
    data = [[True, 0, 0]] + [[0, 0, 0]] * 15
    with pytest.raises(PaletteError):
        Palette(make_tmp(test_dir, data))

def test_value_exact_255(test_dir):
    data = [[255, 255, 255]] * 16
    p = Palette(make_tmp(test_dir, data))
    assert list(p[0]) == [255, 255, 255]


# -- __getitem__ bounds -------------------------------------------------------

def test_getitem_out_of_range_high():
    p = Palette(VALID)
    with pytest.raises(PaletteError):
        p[16]

def test_getitem_out_of_range_low():
    p = Palette(VALID)
    with pytest.raises(PaletteError):
        p[-1]


# -- VirtualVRAM helpers ------------------------------------------------------

def make_tmp_bin(base_dir, data, name="sheet.bin"):
    f = base_dir / name
    f.write_bytes(data)
    return str(f)


# -- VirtualVRAM happy path ---------------------------------------------------

def test_vram_load_ok(test_dir):
    t = make_tmp_bin(test_dir, bytes(32768), "tiles.bin")
    s = make_tmp_bin(test_dir, bytes(32768), "sprites.bin")
    vram = VirtualVRAM(t, s)
    assert vram._tiles_mx.shape == (256, 256)
    assert vram._sprites_mx.shape == (256, 256)
    assert vram._tiles_mx.dtype == np.uint8
    assert vram._sprites_mx.dtype == np.uint8

def test_vram_decode_all_zeros(test_dir):
    t = make_tmp_bin(test_dir, bytes(32768), "tiles.bin")
    s = make_tmp_bin(test_dir, bytes(32768), "sprites.bin")
    vram = VirtualVRAM(t, s)
    assert vram._tiles_mx.max() == 0

def test_vram_decode_all_ff(test_dir):
    t = make_tmp_bin(test_dir, bytes([0xFF] * 32768), "tiles.bin")
    s = make_tmp_bin(test_dir, bytes(32768), "sprites.bin")
    vram = VirtualVRAM(t, s)
    assert vram._tiles_mx.max() == 15
    assert vram._tiles_mx.min() == 15

def test_vram_decode_nibbles(test_dir):
    # 0xAB → high nibble = 10 (primo pixel), low nibble = 11 (secondo pixel)
    data = bytes([0xAB]) + bytes(32767)
    t = make_tmp_bin(test_dir, data, "tiles.bin")
    s = make_tmp_bin(test_dir, bytes(32768), "sprites.bin")
    vram = VirtualVRAM(t, s)
    assert vram._tiles_mx[0, 0] == 10
    assert vram._tiles_mx[0, 1] == 11


# -- VirtualVRAM file errors --------------------------------------------------

def test_vram_tiles_not_found(test_dir):
    s = make_tmp_bin(test_dir, bytes(32768), "sprites.bin")
    with pytest.raises(FileNotFoundError):
        VirtualVRAM("non_esiste.bin", s)

def test_vram_sprites_not_found(test_dir):
    t = make_tmp_bin(test_dir, bytes(32768), "tiles.bin")
    with pytest.raises(FileNotFoundError):
        VirtualVRAM(t, "non_esiste.bin")


# -- VirtualVRAM wrong size ---------------------------------------------------

def test_vram_tiles_wrong_size(test_dir):
    t = make_tmp_bin(test_dir, bytes(100), "tiles.bin")
    s = make_tmp_bin(test_dir, bytes(32768), "sprites.bin")
    with pytest.raises(VRAMError):
        VirtualVRAM(t, s)

def test_vram_sprites_wrong_size(test_dir):
    t = make_tmp_bin(test_dir, bytes(32768), "tiles.bin")
    s = make_tmp_bin(test_dir, bytes(100), "sprites.bin")
    with pytest.raises(VRAMError):
        VirtualVRAM(t, s)


# -- get_tile / get_sprite sheet builders -------------------------------------

def make_tile_sheet(tile_id, fill_byte=0xFF):
    data = bytearray(32768)
    row_start = (tile_id // 8) * 32
    col_start = (tile_id % 8) * 32
    for r in range(32):
        offset = (row_start + r) * 128 + col_start // 2
        for b in range(16):
            data[offset + b] = fill_byte
    return bytes(data)

def make_sprite_sheet(sprite_id, fill_byte=0xFF):
    data = bytearray(32768)
    row_start = (sprite_id // 4) * 64
    col_start = (sprite_id % 4) * 64
    for r in range(64):
        offset = (row_start + r) * 128 + col_start // 2
        for b in range(32):
            data[offset + b] = fill_byte
    return bytes(data)


# -- get_tile happy path ------------------------------------------------------

def test_get_tile_shape(test_dir):
    t = make_tmp_bin(test_dir, bytes(32768), "tiles.bin")
    s = make_tmp_bin(test_dir, bytes(32768), "sprites.bin")
    vram = VirtualVRAM(t, s)
    assert vram.get_tile(0).shape == (32, 32)
    assert vram.get_tile(0).dtype == np.uint8

def test_get_tile_first(test_dir):
    t = make_tmp_bin(test_dir, make_tile_sheet(0), "tiles.bin")
    s = make_tmp_bin(test_dir, bytes(32768), "sprites.bin")
    vram = VirtualVRAM(t, s)
    assert vram.get_tile(0).min() == 15
    assert vram.get_tile(0).max() == 15

def test_get_tile_last(test_dir):
    t = make_tmp_bin(test_dir, make_tile_sheet(63), "tiles.bin")
    s = make_tmp_bin(test_dir, bytes(32768), "sprites.bin")
    vram = VirtualVRAM(t, s)
    assert vram.get_tile(63).min() == 15
    assert vram.get_tile(63).max() == 15

def test_get_tile_isolation(test_dir):
    t = make_tmp_bin(test_dir, make_tile_sheet(5), "tiles.bin")
    s = make_tmp_bin(test_dir, bytes(32768), "sprites.bin")
    vram = VirtualVRAM(t, s)
    assert vram.get_tile(5).min() == 15
    assert vram.get_tile(0).max() == 0


# -- get_tile error path ------------------------------------------------------

def test_get_tile_not_int(test_dir):
    t = make_tmp_bin(test_dir, bytes(32768), "tiles.bin")
    s = make_tmp_bin(test_dir, bytes(32768), "sprites.bin")
    vram = VirtualVRAM(t, s)
    with pytest.raises(VRAMError):
        vram.get_tile("0")

def test_get_tile_out_of_range_high(test_dir):
    t = make_tmp_bin(test_dir, bytes(32768), "tiles.bin")
    s = make_tmp_bin(test_dir, bytes(32768), "sprites.bin")
    vram = VirtualVRAM(t, s)
    with pytest.raises(VRAMError):
        vram.get_tile(64)

def test_get_tile_out_of_range_low(test_dir):
    t = make_tmp_bin(test_dir, bytes(32768), "tiles.bin")
    s = make_tmp_bin(test_dir, bytes(32768), "sprites.bin")
    vram = VirtualVRAM(t, s)
    with pytest.raises(VRAMError):
        vram.get_tile(-1)


# -- get_sprite happy path ----------------------------------------------------

def test_get_sprite_shape(test_dir):
    t = make_tmp_bin(test_dir, bytes(32768), "tiles.bin")
    s = make_tmp_bin(test_dir, bytes(32768), "sprites.bin")
    vram = VirtualVRAM(t, s)
    assert vram.get_sprite(0).shape == (64, 64)
    assert vram.get_sprite(0).dtype == np.uint8

def test_get_sprite_first(test_dir):
    t = make_tmp_bin(test_dir, bytes(32768), "tiles.bin")
    s = make_tmp_bin(test_dir, make_sprite_sheet(0), "sprites.bin")
    vram = VirtualVRAM(t, s)
    assert vram.get_sprite(0).min() == 15
    assert vram.get_sprite(0).max() == 15

def test_get_sprite_last(test_dir):
    t = make_tmp_bin(test_dir, bytes(32768), "tiles.bin")
    s = make_tmp_bin(test_dir, make_sprite_sheet(15), "sprites.bin")
    vram = VirtualVRAM(t, s)
    assert vram.get_sprite(15).min() == 15
    assert vram.get_sprite(15).max() == 15

def test_get_sprite_isolation(test_dir):
    t = make_tmp_bin(test_dir, bytes(32768), "tiles.bin")
    s = make_tmp_bin(test_dir, make_sprite_sheet(7), "sprites.bin")
    vram = VirtualVRAM(t, s)
    assert vram.get_sprite(7).min() == 15
    assert vram.get_sprite(0).max() == 0


# -- get_sprite error path ----------------------------------------------------

def test_get_sprite_not_int(test_dir):
    t = make_tmp_bin(test_dir, bytes(32768), "tiles.bin")
    s = make_tmp_bin(test_dir, bytes(32768), "sprites.bin")
    vram = VirtualVRAM(t, s)
    with pytest.raises(VRAMError):
        vram.get_sprite("0")

def test_get_sprite_out_of_range_high(test_dir):
    t = make_tmp_bin(test_dir, bytes(32768), "tiles.bin")
    s = make_tmp_bin(test_dir, bytes(32768), "sprites.bin")
    vram = VirtualVRAM(t, s)
    with pytest.raises(VRAMError):
        vram.get_sprite(16)

def test_get_sprite_out_of_range_low(test_dir):
    t = make_tmp_bin(test_dir, bytes(32768), "tiles.bin")
    s = make_tmp_bin(test_dir, bytes(32768), "sprites.bin")
    vram = VirtualVRAM(t, s)
    with pytest.raises(VRAMError):
        vram.get_sprite(-1)


# -- SceneParser helpers ------------------------------------------------------

VALID_TILE_MAP = [[0] * 20 for _ in range(15)]
VALID_SPRITE = {"id": 0, "x": 0, "y": 0, "flip_x": False, "flip_y": False, "rotation": 0}

def make_scene(base_dir, data, name="scene.json"):
    f = base_dir / name
    f.write_text(json.dumps(data))
    return str(f)

def valid_scene():
    return {
        "transparent_index": 0,
        "tile_map": VALID_TILE_MAP,
        "sprites": [VALID_SPRITE],
    }


# -- SceneParser happy path ---------------------------------------------------

def test_scene_load_ok(test_dir):
    p = SceneParser(make_scene(test_dir, valid_scene()))
    assert p.transparent_index == 0
    assert p.tile_map.shape == (15, 20)
    assert p.tile_map.dtype == np.uint8
    assert isinstance(p.sprites, list)

def test_scene_transparent_index_boundary(test_dir):
    data = valid_scene()
    data["transparent_index"] = 15
    p = SceneParser(make_scene(test_dir, data))
    assert p.transparent_index == 15

def test_scene_empty_sprites(test_dir):
    data = valid_scene()
    data["sprites"] = []
    p = SceneParser(make_scene(test_dir, data))
    assert p.sprites == []

def test_scene_sprite_fields(test_dir):
    p = SceneParser(make_scene(test_dir, valid_scene()))
    s = p.sprites[0]
    assert s["id"] == 0
    assert s["x"] == 0
    assert s["y"] == 0
    assert s["flip_x"] is False
    assert s["flip_y"] is False
    assert s["rotation"] == 0


# -- SceneParser file errors --------------------------------------------------

def test_scene_file_not_found():
    with pytest.raises(FileNotFoundError):
        SceneParser("non_esiste.json")

def test_scene_invalid_json(test_dir):
    f = test_dir / "scene.json"
    f.write_text("questo non e json {{{")
    with pytest.raises(SceneError):
        SceneParser(str(f))


# -- SceneParser missing keys -------------------------------------------------

def test_scene_missing_transparent_index(test_dir):
    data = valid_scene()
    del data["transparent_index"]
    with pytest.raises(SceneError):
        SceneParser(make_scene(test_dir, data))

def test_scene_missing_tile_map(test_dir):
    data = valid_scene()
    del data["tile_map"]
    with pytest.raises(SceneError):
        SceneParser(make_scene(test_dir, data))

def test_scene_missing_sprites(test_dir):
    data = valid_scene()
    del data["sprites"]
    with pytest.raises(SceneError):
        SceneParser(make_scene(test_dir, data))


# -- SceneParser transparent_index errors -------------------------------------

def test_scene_transparent_index_not_int(test_dir):
    data = valid_scene()
    data["transparent_index"] = "0"
    with pytest.raises(SceneError):
        SceneParser(make_scene(test_dir, data))

def test_scene_transparent_index_too_high(test_dir):
    data = valid_scene()
    data["transparent_index"] = 16
    with pytest.raises(SceneError):
        SceneParser(make_scene(test_dir, data))

def test_scene_transparent_index_negative(test_dir):
    data = valid_scene()
    data["transparent_index"] = -1
    with pytest.raises(SceneError):
        SceneParser(make_scene(test_dir, data))


# -- C2 regression: bool rejected where int is required -----------------------
# In Python bool is a subclass of int, so a JSON `true` would pass isinstance int.

def test_scene_transparent_index_bool(test_dir):
    data = valid_scene()
    data["transparent_index"] = True
    with pytest.raises(SceneError):
        SceneParser(make_scene(test_dir, data))

def test_scene_tile_map_bool(test_dir):
    data = valid_scene()
    data["tile_map"] = [[0] * 20 for _ in range(15)]
    data["tile_map"][0][0] = True
    with pytest.raises(SceneError):
        SceneParser(make_scene(test_dir, data))

def test_scene_sprite_x_bool(test_dir):
    data = valid_scene()
    data["sprites"] = [{"id": 0, "x": True, "y": 0,
                        "flip_x": False, "flip_y": False, "rotation": 0}]
    with pytest.raises(SceneError):
        SceneParser(make_scene(test_dir, data))

def test_scene_sprite_rotation_bool(test_dir):
    data = valid_scene()
    data["sprites"] = [{"id": 0, "x": 0, "y": 0,
                        "flip_x": False, "flip_y": False, "rotation": True}]
    with pytest.raises(SceneError):
        SceneParser(make_scene(test_dir, data))


# -- SceneParser tile_map errors ----------------------------------------------

def test_scene_tile_map_wrong_rows(test_dir):
    data = valid_scene()
    data["tile_map"] = [[0] * 20 for _ in range(10)]
    with pytest.raises(SceneError):
        SceneParser(make_scene(test_dir, data))

def test_scene_tile_map_wrong_cols(test_dir):
    data = valid_scene()
    data["tile_map"] = [[0] * 15 for _ in range(15)]
    with pytest.raises(SceneError):
        SceneParser(make_scene(test_dir, data))

def test_scene_tile_map_value_too_high(test_dir):
    data = valid_scene()
    data["tile_map"][0][0] = 64
    with pytest.raises(SceneError):
        SceneParser(make_scene(test_dir, data))

def test_scene_tile_map_value_negative(test_dir):
    data = valid_scene()
    data["tile_map"][0][0] = -1
    with pytest.raises(SceneError):
        SceneParser(make_scene(test_dir, data))

def test_scene_tile_map_value_not_int(test_dir):
    data = valid_scene()
    data["tile_map"][0][0] = 1.5
    with pytest.raises(SceneError):
        SceneParser(make_scene(test_dir, data))


# -- SceneParser sprite errors ------------------------------------------------

def test_scene_sprites_not_list(test_dir):
    data = valid_scene()
    data["sprites"] = "not a list"
    with pytest.raises(SceneError):
        SceneParser(make_scene(test_dir, data))

def test_scene_sprite_missing_field(test_dir):
    data = valid_scene()
    del data["sprites"][0]["rotation"]
    with pytest.raises(SceneError):
        SceneParser(make_scene(test_dir, data))

def test_scene_sprite_id_not_int(test_dir):
    data = valid_scene()
    data["sprites"][0]["id"] = "0"
    with pytest.raises(SceneError):
        SceneParser(make_scene(test_dir, data))

def test_scene_sprite_id_too_high(test_dir):
    data = valid_scene()
    data["sprites"][0]["id"] = 16
    with pytest.raises(SceneError):
        SceneParser(make_scene(test_dir, data))

def test_scene_sprite_id_negative(test_dir):
    data = valid_scene()
    data["sprites"][0]["id"] = -1
    with pytest.raises(SceneError):
        SceneParser(make_scene(test_dir, data))

def test_scene_sprite_x_not_int(test_dir):
    data = valid_scene()
    data["sprites"][0]["x"] = 1.5
    with pytest.raises(SceneError):
        SceneParser(make_scene(test_dir, data))

def test_scene_sprite_y_not_int(test_dir):
    data = valid_scene()
    data["sprites"][0]["y"] = "0"
    with pytest.raises(SceneError):
        SceneParser(make_scene(test_dir, data))

def test_scene_sprite_flip_x_not_bool(test_dir):
    data = valid_scene()
    data["sprites"][0]["flip_x"] = 0
    with pytest.raises(SceneError):
        SceneParser(make_scene(test_dir, data))

def test_scene_sprite_flip_y_not_bool(test_dir):
    data = valid_scene()
    data["sprites"][0]["flip_y"] = 1
    with pytest.raises(SceneError):
        SceneParser(make_scene(test_dir, data))

def test_scene_sprite_rotation_not_int(test_dir):
    data = valid_scene()
    data["sprites"][0]["rotation"] = "90"
    with pytest.raises(SceneError):
        SceneParser(make_scene(test_dir, data))

def test_scene_sprite_rotation_invalid(test_dir):
    data = valid_scene()
    data["sprites"][0]["rotation"] = 45
    with pytest.raises(SceneError):
        SceneParser(make_scene(test_dir, data))

def test_scene_tile_map_jagged(test_dir):
    data = valid_scene()
    data["tile_map"][5] = [0] * 15
    with pytest.raises(SceneError):
        SceneParser(make_scene(test_dir, data))


# -- Blitter helpers ----------------------------------------------------------

def make_vram(base_dir, tile_data=None, sprite_data=None):
    t = make_tmp_bin(base_dir, tile_data or bytes(32768), "tiles.bin")
    s = make_tmp_bin(base_dir, sprite_data or bytes(32768), "sprites.bin")
    return VirtualVRAM(t, s)


# -- Blitter init / _validate -------------------------------------------------

def test_blitter_init_tile_ok(test_dir):
    vram = make_vram(test_dir)
    b = Blitter(vram, "tile", 0, 0, RenderingPipeline.get_buf())
    assert b.transparent_index == 0
    assert b._buffer.shape == (FRAME_H, FRAME_W)
    assert b._buffer.dtype == np.uint8

def test_blitter_init_sprite_ok(test_dir):
    vram = make_vram(test_dir)
    b = Blitter(vram, "sprite", 15, 7, RenderingPipeline.get_buf())
    assert b.transparent_index == 7

def test_blitter_invalid_asset_type(test_dir):
    vram = make_vram(test_dir)
    with pytest.raises(BlitterException):
        Blitter(vram, "block", 0, 0, RenderingPipeline.get_buf())

def test_blitter_idx_not_int(test_dir):
    vram = make_vram(test_dir)
    with pytest.raises(BlitterException):
        Blitter(vram, "tile", "0", 0, RenderingPipeline.get_buf())

def test_blitter_tile_idx_out_of_range_high(test_dir):
    vram = make_vram(test_dir)
    with pytest.raises(BlitterException):
        Blitter(vram, "tile", 64, 0, RenderingPipeline.get_buf())

def test_blitter_tile_idx_out_of_range_low(test_dir):
    vram = make_vram(test_dir)
    with pytest.raises(BlitterException):
        Blitter(vram, "tile", -1, 0, RenderingPipeline.get_buf())

def test_blitter_sprite_idx_out_of_range_high(test_dir):
    vram = make_vram(test_dir)
    with pytest.raises(BlitterException):
        Blitter(vram, "sprite", 16, 0, RenderingPipeline.get_buf())

def test_blitter_sprite_idx_out_of_range_low(test_dir):
    vram = make_vram(test_dir)
    with pytest.raises(BlitterException):
        Blitter(vram, "sprite", -1, 0, RenderingPipeline.get_buf())

def test_blitter_transparent_index_not_int(test_dir):
    vram = make_vram(test_dir)
    with pytest.raises(BlitterException):
        Blitter(vram, "tile", 0, "0", RenderingPipeline.get_buf())

def test_blitter_transparent_index_too_high(test_dir):
    vram = make_vram(test_dir)
    with pytest.raises(BlitterException):
        Blitter(vram, "tile", 0, 16, RenderingPipeline.get_buf())

def test_blitter_transparent_index_negative(test_dir):
    vram = make_vram(test_dir)
    with pytest.raises(BlitterException):
        Blitter(vram, "tile", 0, -1, RenderingPipeline.get_buf())


# -- blit_tile ----------------------------------------------------------------

def test_blit_tile_writes_to_buffer(test_dir):
    vram = make_vram(test_dir, tile_data=make_tile_sheet(0, 0xFF))
    b = Blitter(vram, "tile", 0, 0, RenderingPipeline.get_buf())
    b.blit_tile(0, 0)
    assert b._buffer[0:32, 0:32].min() == 15
    assert b._buffer[0:32, 0:32].max() == 15

def test_blit_tile_correct_position(test_dir):
    vram = make_vram(test_dir, tile_data=make_tile_sheet(0, 0xFF))
    b = Blitter(vram, "tile", 0, 0, RenderingPipeline.get_buf())
    b.blit_tile(1, 2)
    assert b._buffer[32:64, 64:96].min() == 15
    assert b._buffer[0:32, 0:32].max() == 0

def test_blit_tile_row_not_int(test_dir):
    vram = make_vram(test_dir)
    b = Blitter(vram, "tile", 0, 0, RenderingPipeline.get_buf())
    with pytest.raises(BlitterException):
        b.blit_tile("0", 0)

def test_blit_tile_col_not_int(test_dir):
    vram = make_vram(test_dir)
    b = Blitter(vram, "tile", 0, 0, RenderingPipeline.get_buf())
    with pytest.raises(BlitterException):
        b.blit_tile(0, "0")

def test_blit_tile_row_out_of_range_high(test_dir):
    vram = make_vram(test_dir)
    b = Blitter(vram, "tile", 0, 0, RenderingPipeline.get_buf())
    with pytest.raises(BlitterException):
        b.blit_tile(15, 0)

def test_blit_tile_row_out_of_range_low(test_dir):
    vram = make_vram(test_dir)
    b = Blitter(vram, "tile", 0, 0, RenderingPipeline.get_buf())
    with pytest.raises(BlitterException):
        b.blit_tile(-1, 0)

def test_blit_tile_col_out_of_range_high(test_dir):
    vram = make_vram(test_dir)
    b = Blitter(vram, "tile", 0, 0, RenderingPipeline.get_buf())
    with pytest.raises(BlitterException):
        b.blit_tile(0, 20)

def test_blit_tile_col_out_of_range_low(test_dir):
    vram = make_vram(test_dir)
    b = Blitter(vram, "tile", 0, 0, RenderingPipeline.get_buf())
    with pytest.raises(BlitterException):
        b.blit_tile(0, -1)


# -- _transform ---------------------------------------------------------------

def test_transform_identity(test_dir):
    vram = make_vram(test_dir)
    b = Blitter(vram, "sprite", 0, 0, RenderingPipeline.get_buf())
    m = np.arange(64 * 64, dtype=np.uint8).reshape(64, 64) % 16
    assert np.array_equal(b._transform(m, False, False, 0), m)

def test_transform_flip_x(test_dir):
    vram = make_vram(test_dir)
    b = Blitter(vram, "sprite", 0, 0, RenderingPipeline.get_buf())
    m = np.arange(64 * 64, dtype=np.uint8).reshape(64, 64) % 16
    assert np.array_equal(b._transform(m, True, False, 0), np.fliplr(m))

def test_transform_flip_y(test_dir):
    vram = make_vram(test_dir)
    b = Blitter(vram, "sprite", 0, 0, RenderingPipeline.get_buf())
    m = np.arange(64 * 64, dtype=np.uint8).reshape(64, 64) % 16
    assert np.array_equal(b._transform(m, False, True, 0), np.flipud(m))

def test_transform_rotation_90(test_dir):
    vram = make_vram(test_dir)
    b = Blitter(vram, "sprite", 0, 0, RenderingPipeline.get_buf())
    m = np.arange(64 * 64, dtype=np.uint8).reshape(64, 64) % 16
    assert np.array_equal(b._transform(m, False, False, 90), np.rot90(m, 1))

def test_transform_rotation_180(test_dir):
    vram = make_vram(test_dir)
    b = Blitter(vram, "sprite", 0, 0, RenderingPipeline.get_buf())
    m = np.arange(64 * 64, dtype=np.uint8).reshape(64, 64) % 16
    assert np.array_equal(b._transform(m, False, False, 180), np.rot90(m, 2))

def test_transform_rotation_270(test_dir):
    vram = make_vram(test_dir)
    b = Blitter(vram, "sprite", 0, 0, RenderingPipeline.get_buf())
    m = np.arange(64 * 64, dtype=np.uint8).reshape(64, 64) % 16
    assert np.array_equal(b._transform(m, False, False, 270), np.rot90(m, 3))

def test_transform_flip_x_and_y(test_dir):
    vram = make_vram(test_dir)
    b = Blitter(vram, "sprite", 0, 0, RenderingPipeline.get_buf())
    m = np.arange(64 * 64, dtype=np.uint8).reshape(64, 64) % 16
    assert np.array_equal(b._transform(m, True, True, 0), np.flipud(np.fliplr(m)))


# -- _clip --------------------------------------------------------------------

def test_clip_fully_inside(test_dir):
    vram = make_vram(test_dir)
    b = Blitter(vram, "sprite", 0, 0, RenderingPipeline.get_buf())
    dst, src = b._clip(0, 0)
    assert dst == (slice(0, 64), slice(0, 64))
    assert src == (slice(0, 64), slice(0, 64))

def test_clip_centered(test_dir):
    vram = make_vram(test_dir)
    b = Blitter(vram, "sprite", 0, 0, RenderingPipeline.get_buf())
    dst, src = b._clip(100, 50)
    assert dst == (slice(50, 114), slice(100, 164))
    assert src == (slice(0, 64), slice(0, 64))

def test_clip_top(test_dir):
    vram = make_vram(test_dir)
    b = Blitter(vram, "sprite", 0, 0, RenderingPipeline.get_buf())
    dst, src = b._clip(0, -10)
    assert dst == (slice(0, 54), slice(0, 64))
    assert src == (slice(10, 64), slice(0, 64))

def test_clip_left(test_dir):
    vram = make_vram(test_dir)
    b = Blitter(vram, "sprite", 0, 0, RenderingPipeline.get_buf())
    dst, src = b._clip(-10, 0)
    assert dst == (slice(0, 64), slice(0, 54))
    assert src == (slice(0, 64), slice(10, 64))

def test_clip_bottom(test_dir):
    vram = make_vram(test_dir)
    b = Blitter(vram, "sprite", 0, 0, RenderingPipeline.get_buf())
    dst, src = b._clip(0, FRAME_H - 32)
    assert dst == (slice(FRAME_H - 32, FRAME_H), slice(0, 64))
    assert src == (slice(0, 32), slice(0, 64))

def test_clip_right(test_dir):
    vram = make_vram(test_dir)
    b = Blitter(vram, "sprite", 0, 0, RenderingPipeline.get_buf())
    dst, src = b._clip(FRAME_W - 32, 0)
    assert dst == (slice(0, 64), slice(FRAME_W - 32, FRAME_W))
    assert src == (slice(0, 64), slice(0, 32))


# -- blit_sprite --------------------------------------------------------------

def test_blit_sprite_all_opaque(test_dir):
    vram = make_vram(test_dir, sprite_data=make_sprite_sheet(0, 0xFF))
    b = Blitter(vram, "sprite", 0, 0, RenderingPipeline.get_buf())
    b.blit_sprite(0, 0, False, False, 0)
    assert b._buffer[0:64, 0:64].min() == 15
    assert b._buffer[0:64, 0:64].max() == 15

def test_blit_sprite_all_transparent(test_dir):
    vram = make_vram(test_dir, sprite_data=make_sprite_sheet(0, 0x00))
    b = Blitter(vram, "sprite", 0, 0, RenderingPipeline.get_buf())
    b.blit_sprite(0, 0, False, False, 0)
    assert b._buffer[0:64, 0:64].max() == 0

def test_blit_sprite_correct_position(test_dir):
    vram = make_vram(test_dir, sprite_data=make_sprite_sheet(0, 0xFF))
    b = Blitter(vram, "sprite", 0, 0, RenderingPipeline.get_buf())
    b.blit_sprite(100, 50, False, False, 0)
    assert b._buffer[50:114, 100:164].min() == 15
    assert b._buffer[0:50, 0:100].max() == 0

def test_blit_sprite_clipping_left(test_dir):
    vram = make_vram(test_dir, sprite_data=make_sprite_sheet(0, 0xFF))
    b = Blitter(vram, "sprite", 0, 0, RenderingPipeline.get_buf())
    b.blit_sprite(-32, 0, False, False, 0)
    assert b._buffer[0:64, 0:32].min() == 15
    assert b._buffer[0:64, 32:64].max() == 0

def test_blit_sprite_mixed_transparency(test_dir):
    # 0xF0 → pixels alternano 15 (opaco) e 0 (trasparente)
    vram = make_vram(test_dir, sprite_data=make_sprite_sheet(0, 0xF0))
    b = Blitter(vram, "sprite", 0, 0, RenderingPipeline.get_buf())
    b.blit_sprite(0, 0, False, False, 0)
    assert b._buffer[0, 0] == 15
    assert b._buffer[0, 1] == 0

def test_blit_sprite_clipping_top(test_dir):
    vram = make_vram(test_dir, sprite_data=make_sprite_sheet(0, 0xFF))
    b = Blitter(vram, "sprite", 0, 0, RenderingPipeline.get_buf())
    b.blit_sprite(0, -32, False, False, 0)
    assert b._buffer[0:32, 0:64].min() == 15
    assert b._buffer[32:64, 0:64].max() == 0

def test_blit_sprite_clipping_right(test_dir):
    vram = make_vram(test_dir, sprite_data=make_sprite_sheet(0, 0xFF))
    b = Blitter(vram, "sprite", 0, 0, RenderingPipeline.get_buf())
    b.blit_sprite(FRAME_W - 32, 0, False, False, 0)
    assert b._buffer[0:64, FRAME_W - 32:FRAME_W].min() == 15
    assert b._buffer[0:64, FRAME_W - 96:FRAME_W - 32].max() == 0

def test_blit_sprite_clipping_bottom(test_dir):
    vram = make_vram(test_dir, sprite_data=make_sprite_sheet(0, 0xFF))
    b = Blitter(vram, "sprite", 0, 0, RenderingPipeline.get_buf())
    b.blit_sprite(0, FRAME_H - 32, False, False, 0)
    assert b._buffer[FRAME_H - 32:FRAME_H, 0:64].min() == 15
    assert b._buffer[FRAME_H - 96:FRAME_H - 32, 0:64].max() == 0

def test_blit_sprite_fully_outside_right(test_dir):
    vram = make_vram(test_dir, sprite_data=make_sprite_sheet(0, 0xFF))
    b = Blitter(vram, "sprite", 0, 0, RenderingPipeline.get_buf())
    b.blit_sprite(FRAME_W, 0, False, False, 0)
    assert b._buffer.max() == 0

def test_blit_sprite_fully_outside_bottom(test_dir):
    vram = make_vram(test_dir, sprite_data=make_sprite_sheet(0, 0xFF))
    b = Blitter(vram, "sprite", 0, 0, RenderingPipeline.get_buf())
    b.blit_sprite(0, FRAME_H, False, False, 0)
    assert b._buffer.max() == 0

def test_blit_sprite_fully_outside_left(test_dir):
    vram = make_vram(test_dir, sprite_data=make_sprite_sheet(0, 0xFF))
    b = Blitter(vram, "sprite", 0, 0, RenderingPipeline.get_buf())
    b.blit_sprite(-64, 0, False, False, 0)
    assert b._buffer.max() == 0

def test_blit_sprite_fully_outside_top(test_dir):
    vram = make_vram(test_dir, sprite_data=make_sprite_sheet(0, 0xFF))
    b = Blitter(vram, "sprite", 0, 0, RenderingPipeline.get_buf())
    b.blit_sprite(0, -64, False, False, 0)
    assert b._buffer.max() == 0

# C1 regression: sprite beyond the positive edge (x > FRAME_W, y > FRAME_H).
# Before the _clip fix the negative dst width produced inconsistent src slices
# -> IndexError. The exact-edge tests (FRAME_W/-64) did not catch it.
def test_blit_sprite_beyond_right_no_crash(test_dir):
    vram = make_vram(test_dir, sprite_data=make_sprite_sheet(0, 0xFF))
    b = Blitter(vram, "sprite", 0, 0, RenderingPipeline.get_buf())
    b.blit_sprite(FRAME_W + 60, 32, False, False, 0)
    assert b._buffer.max() == 0

def test_blit_sprite_beyond_bottom_no_crash(test_dir):
    vram = make_vram(test_dir, sprite_data=make_sprite_sheet(0, 0xFF))
    b = Blitter(vram, "sprite", 0, 0, RenderingPipeline.get_buf())
    b.blit_sprite(32, FRAME_H + 20, False, False, 0)
    assert b._buffer.max() == 0

def test_blit_sprite_far_left_no_crash(test_dir):
    vram = make_vram(test_dir, sprite_data=make_sprite_sheet(0, 0xFF))
    b = Blitter(vram, "sprite", 0, 0, RenderingPipeline.get_buf())
    b.blit_sprite(-100, 32, False, False, 0)
    assert b._buffer.max() == 0

def test_blit_sprite_transform_and_clip(test_dir):
    vram = make_vram(test_dir, sprite_data=make_sprite_sheet(0, 0xFF))
    b = Blitter(vram, "sprite", 0, 0, RenderingPipeline.get_buf())
    b.blit_sprite(-32, 0, True, False, 90)
    assert b._buffer[0:64, 0:32].min() == 15

def test_blit_sprite_z_order(test_dir):
    vram = make_vram(test_dir, sprite_data=make_sprite_sheet(0, 0xFF))
    b = Blitter(vram, "sprite", 0, 0, RenderingPipeline.get_buf())
    b.blit_sprite(0, 0, False, False, 0)
    # second blit with all-transparent sprite should not overwrite
    vram2 = make_vram(test_dir, sprite_data=make_sprite_sheet(0, 0x00))
    b2 = Blitter(vram2, "sprite", 0, 0, b._buffer)
    b2.blit_sprite(0, 0, False, False, 0)
    assert b2._buffer[0:64, 0:64].min() == 15


# -- RenderingPipeline helpers ------------------------------------------------

PIPELINE_PALETTE = [[i * 17, i * 17, i * 17] for i in range(16)]


def pack_matrix(matrix):
    flat = matrix.ravel().astype(np.uint8)
    return ((flat[0::2] << 4) | flat[1::2]).tobytes()


def make_pipeline_palette(base_dir):
    f = base_dir / "palette.json"
    f.write_text(json.dumps(PIPELINE_PALETTE))
    return str(f)


def make_pipeline_tiles(base_dir, tile0_index=1):
    matrix = np.zeros((256, 256), dtype=np.uint8)
    matrix[0:32, 0:32] = tile0_index
    f = base_dir / "tiles.bin"
    f.write_bytes(pack_matrix(matrix))
    return str(f)


def make_pipeline_sprites(base_dir, sprite0_index=2):
    matrix = np.zeros((256, 256), dtype=np.uint8)
    matrix[0:64, 0:64] = sprite0_index
    f = base_dir / "sprites.bin"
    f.write_bytes(pack_matrix(matrix))
    return str(f)


def make_pipeline_scene(base_dir, transparent_index=0, sprites=None):
    data = {
        "transparent_index": transparent_index,
        "tile_map": [[0] * 20 for _ in range(15)],
        "sprites": sprites or [],
    }
    f = base_dir / "scene.json"
    f.write_text(json.dumps(data))
    return str(f)


def make_pipeline(base_dir, tile0_index=1, sprite0_index=2, transparent_index=0, sprites=None):
    palette = make_pipeline_palette(base_dir)
    tiles = make_pipeline_tiles(base_dir, tile0_index)
    sprites_bin = make_pipeline_sprites(base_dir, sprite0_index)
    scene = make_pipeline_scene(base_dir, transparent_index, sprites)
    output = str(base_dir / "output.png")
    return RenderingPipeline(palette, scene, tiles, sprites_bin, output)


# -- get_buf ------------------------------------------------------------------

def test_pipeline_get_buf_shape():
    assert RenderingPipeline.get_buf().shape == (FRAME_H, FRAME_W)

def test_pipeline_get_buf_dtype():
    assert RenderingPipeline.get_buf().dtype == np.uint8

def test_pipeline_get_buf_zeros():
    assert np.all(RenderingPipeline.get_buf() == 0)

def test_pipeline_get_buf_independent():
    buf1 = RenderingPipeline.get_buf()
    buf2 = RenderingPipeline.get_buf()
    buf1[0, 0] = 5
    assert buf2[0, 0] == 0


# -- __repr__ -----------------------------------------------------------------

def test_pipeline_repr(test_dir):
    rp = make_pipeline(test_dir)
    r = repr(rp)
    assert "palette" in r
    assert "scene" in r
    assert "tiles" in r
    assert "sprites" in r
    assert "output" in r


# -- _export ------------------------------------------------------------------

def test_pipeline_export_creates_file(test_dir):
    rp = make_pipeline(test_dir)
    rp._export(RenderingPipeline.get_buf())
    assert Path(rp._output_path).exists()

def test_pipeline_export_image_size(test_dir):
    rp = make_pipeline(test_dir)
    rp._export(RenderingPipeline.get_buf())
    img = PILImage.open(rp._output_path)
    assert img.size == (FRAME_W, FRAME_H)

def test_pipeline_export_pixel_color(test_dir):
    rp = make_pipeline(test_dir)
    buf = RenderingPipeline.get_buf()
    buf[0, 0] = 1  # palette index 1 → [17, 17, 17]
    rp._export(buf)
    assert PILImage.open(rp._output_path).getpixel((0, 0)) == (17, 17, 17)

def test_pipeline_export_bad_path(test_dir):
    rp = make_pipeline(test_dir)
    rp._output_path = str(test_dir / "non_esiste" / "output.png")  # directory mancante
    with pytest.raises(RenderingException):
        rp._export(RenderingPipeline.get_buf())


# -- _compose -----------------------------------------------------------------

def test_pipeline_compose_tiles_written(test_dir):
    rp = make_pipeline(test_dir, tile0_index=1)
    buf = RenderingPipeline.get_buf()
    rp._compose(buf)
    assert buf[0, 0] == 1

def test_pipeline_compose_full_tilemap(test_dir):
    rp = make_pipeline(test_dir, tile0_index=1)
    buf = RenderingPipeline.get_buf()
    rp._compose(buf)
    assert buf[479, 639] == 1

def test_pipeline_compose_sprite_over_tile(test_dir):
    sprite = {"id": 0, "x": 0, "y": 0, "flip_x": False, "flip_y": False, "rotation": 0}
    rp = make_pipeline(test_dir, tile0_index=1, sprite0_index=2, transparent_index=0, sprites=[sprite])
    buf = RenderingPipeline.get_buf()
    rp._compose(buf)
    assert buf[0, 0] == 2

def test_pipeline_compose_transparent_sprite_not_drawn(test_dir):
    sprite = {"id": 0, "x": 0, "y": 0, "flip_x": False, "flip_y": False, "rotation": 0}
    rp = make_pipeline(test_dir, tile0_index=1, sprite0_index=0, transparent_index=0, sprites=[sprite])
    buf = RenderingPipeline.get_buf()
    rp._compose(buf)
    assert buf[0, 0] == 1


# -- render() -----------------------------------------------------------------

def test_pipeline_render_creates_output(test_dir):
    rp = make_pipeline(test_dir)
    rp.render()
    assert Path(rp._output_path).exists()

def test_pipeline_render_output_size(test_dir):
    rp = make_pipeline(test_dir)
    rp.render()
    assert PILImage.open(rp._output_path).size == (FRAME_W, FRAME_H)

def test_pipeline_compose_sprite_z_order(test_dir):
    # sprite 0 (index 2) drawn first, sprite 1 (index 3) drawn second at same position — sprite 1 wins
    matrix = np.zeros((256, 256), dtype=np.uint8)
    matrix[0:64, 0:64] = 2    # sprite 0
    matrix[0:64, 64:128] = 3  # sprite 1
    (test_dir / "sprites.bin").write_bytes(pack_matrix(matrix))
    scene_data = {
        "transparent_index": 0,
        "tile_map": [[0] * 20 for _ in range(15)],
        "sprites": [
            {"id": 0, "x": 0, "y": 0, "flip_x": False, "flip_y": False, "rotation": 0},
            {"id": 1, "x": 0, "y": 0, "flip_x": False, "flip_y": False, "rotation": 0},
        ],
    }
    (test_dir / "scene.json").write_text(json.dumps(scene_data))
    rp = RenderingPipeline(
        make_pipeline_palette(test_dir),
        str(test_dir / "scene.json"),
        make_pipeline_tiles(test_dir),
        str(test_dir / "sprites.bin"),
        str(test_dir / "output.png"),
    )
    buf = RenderingPipeline.get_buf()
    rp._compose(buf)
    assert buf[0, 0] == 3

def test_pipeline_compose_sprite_transformation(test_dir):
    # sprite 0: left half (cols 0-31) opaque index 2, right half transparent index 0
    # with flip_x the halves swap: buf[0,0] stays tile=1, buf[0,32] becomes 2
    matrix = np.zeros((256, 256), dtype=np.uint8)
    matrix[0:64, 0:32] = 2
    (test_dir / "sprites.bin").write_bytes(pack_matrix(matrix))
    scene_data = {
        "transparent_index": 0,
        "tile_map": [[0] * 20 for _ in range(15)],
        "sprites": [{"id": 0, "x": 0, "y": 0, "flip_x": True, "flip_y": False, "rotation": 0}],
    }
    (test_dir / "scene.json").write_text(json.dumps(scene_data))
    rp = RenderingPipeline(
        make_pipeline_palette(test_dir),
        str(test_dir / "scene.json"),
        make_pipeline_tiles(test_dir, tile0_index=1),
        str(test_dir / "sprites.bin"),
        str(test_dir / "output.png"),
    )
    buf = RenderingPipeline.get_buf()
    rp._compose(buf)
    assert buf[0, 0] == 1   # flip moved opaque pixels away from col 0
    assert buf[0, 32] == 2  # flip moved opaque pixels to col 32

def test_pipeline_compose_sprite_clipping(test_dir):
    # sprite at x=-32: only cols 32-63 of the sprite are visible (frame cols 0-31)
    sprite = {"id": 0, "x": -32, "y": 0, "flip_x": False, "flip_y": False, "rotation": 0}
    rp = make_pipeline(test_dir, tile0_index=1, sprite0_index=2, transparent_index=0, sprites=[sprite])
    buf = RenderingPipeline.get_buf()
    rp._compose(buf)
    assert buf[0, 0] == 2   # visible part of sprite drawn
    assert buf[0, 32] == 1  # tile only — sprite does not reach here


# -- main ---------------------------------------------------------------------

def test_main_help(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["main.py", "--help"])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 0

def test_main_missing_args(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["main.py"])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code != 0

def test_main_runs_ok(monkeypatch, test_dir):
    rp = make_pipeline(test_dir)
    monkeypatch.setattr(sys, "argv", [
        "main.py", rp._palette_path, rp._scene_path,
        rp._tiles_path, rp._sprites_path, rp._output_path,
    ])
    main()
    assert Path(rp._output_path).exists()

def test_main_file_not_found(monkeypatch, test_dir):
    output = str(test_dir / "output.png")
    monkeypatch.setattr(sys, "argv", [
        "main.py", "no.json", "no.json", "no.bin", "no.bin", output,
    ])
    with pytest.raises(FileNotFoundError):
        main()
