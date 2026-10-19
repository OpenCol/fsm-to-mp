from __future__ import annotations

import struct

from fsm_to_mp.convert import convert_map, encode_plane0
from fsm_to_mp.model import Elevation, Features, Map, River, Tile, Village, WaterKind
from fsm_to_mp.mpx.format import KEEP, REQUIRED, read_container
from fsm_to_mp.mpx.writer import build_mpx
from fsm_to_mp.resample import FRAME_X, FRAME_Y, resample, resampled_size


def freecol_map(width, height, river=(), hills=(), features=Features()):
    tiles = []
    for y in range(height):
        for x in range(width):
            if (x, y) in hills:
                tiles.append(Tile(x, y, "hills", elevation=Elevation.HILLS))
            else:
                tiles.append(Tile(x, y, "plains", river=River.MINOR if (x, y) in river else River.NONE))
    return Map(width, height, tuple(tiles), features=features)


def test_size_keeps_the_tile_count_and_fits_the_side():
    assert resampled_size(40, 100) == (58, 72, False)  # FreeCol's "small" map: 57 x 71, made classic
    assert resampled_size(30, 120) == (42, 85, False)
    assert resampled_size(180, 300) == (228, 190, True)


def test_the_frame_is_what_a_new_game_makes():
    squares, _ = resample(freecol_map(10, 20))
    plane0 = encode_plane0(convert_map(squares).map)
    w, h = squares.width, squares.height
    assert all(plane0[x] == 24 and plane0[(h - 1) * w + x] == 24 for x in range(w))
    for y in range(FRAME_Y, h - FRAME_Y):
        assert [plane0[y * w + x] for x in (0, 1, w - 2, w - 1)] == [26] * 4
        assert plane0[y * w + FRAME_X] == 2


def test_a_river_running_north_stays_connected():
    # north is two rows up in FreeCol; the river steps through the diagonal neighbours between
    path = [(5, y) for y in range(4, 36)]
    squares, _ = resample(freecol_map(12, 40, river=set(path)))
    rivers = {(t.x, t.y) for t in squares.tiles if t.river != River.NONE}
    start = min(rivers, key=lambda p: p[1])
    seen, todo = {start}, [start]
    while todo:
        x, y = todo.pop()
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                n = (x + dx, y + dy)
                if n in rivers and n not in seen:
                    seen.add(n)
                    todo.append(n)
    assert seen == rivers
    assert max(p[1] for p in rivers) - min(p[1] for p in rivers) >= 20


def test_placed_things_go_to_the_square_that_holds_their_diamond():
    features = Features({(3, 7): "grain", (4, 9): "lumber"}, frozenset({(6, 11)}), (Village(2, 13, 4, True, "Ani-kituhwa"),))
    squares, warnings = resample(freecol_map(10, 20, features=features))
    assert not warnings
    assert len(squares.features.resources) == 2 and len(squares.features.rumours) == 1
    (village,) = squares.features.villages
    assert (village.tribe, village.capital) == (4, True)
    assert FRAME_X <= village.x < squares.width - FRAME_X and FRAME_Y <= village.y < squares.height - FRAME_Y


def test_mpx_layers_follow_the_original_rules():
    features = Features(
        {(3, 3): "grain", (4, 3): "lumber"},  # plains: grain is its bonus, lumber is not
        frozenset({(5, 3), (0, 0)}),          # the second at sea
        (Village(6, 3, 0, True, "Cuzco"), Village(7, 3, 2, False, "Hills")),
    )
    tiles = []
    for y in range(6):
        for x in range(10):
            if x == 0 or y == 0:
                tiles.append(Tile(x, y, "ocean", water=WaterKind.OCEAN))
            elif (x, y) == (7, 3):
                tiles.append(Tile(x, y, "hills", elevation=Elevation.HILLS))
            else:
                tiles.append(Tile(x, y, "plains"))
    game_map = convert_map(Map(10, 6, tuple(tiles), features=features)).map
    data, warnings = build_mpx(game_map, encode_plane0(game_map), {"title": "Test", "author": "Gó:wah"})
    assert sorted(w.code for w in warnings) == ["resource-mismatch", "rumour-on-water", "village-moved"]

    chunks = {c.id: c for c in read_container(data)}
    assert list(chunks) == [b"HEAD", b"TERR", b"RSRC", b"RUMR", b"VILL", b"INFO"]
    assert all(c.flags == REQUIRED for k, c in chunks.items() if k != b"INFO") and chunks[b"INFO"].flags == KEEP
    assert struct.unpack("<HH", chunks[b"HEAD"].data) == (10, 6)
    assert [i for i, b in enumerate(chunks[b"RSRC"].data) if b] == [3 * 10 + 3]
    assert [i for i, b in enumerate(chunks[b"RUMR"].data) if b] == [3 * 10 + 5]
    vill = chunks[b"VILL"]
    assert vill.version == 2 and struct.unpack_from("<H", vill.data) == (2,)
    cuzco, moved = struct.unpack_from("<BBHH", vill.data, 2), struct.unpack_from("<BBHH", vill.data, 8)
    assert cuzco == (0, 1, 6, 3) and moved[:2] == (2, 0) and (moved[2], moved[3]) != (7, 3)
    assert chunks[b"INFO"].data == b"title=Test\nauthor=Go:wah\nfeatures=map:layers\n"


def test_mpx_without_features_lets_the_game_make_them():
    game_map = convert_map(freecol_map(4, 4)).map
    data, warnings = build_mpx(game_map, encode_plane0(game_map), {})
    assert not warnings
    assert [c.id for c in read_container(data)] == [b"HEAD", b"TERR", b"INFO"]
