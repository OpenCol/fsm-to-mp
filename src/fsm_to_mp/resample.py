"""FreeCol's diamond grid onto Colonization's square grid.

FreeCol draws its map as diamonds in staggered rows: north is two rows up, north-east one row up
and half a tile east on odd rows (FreeCol's Direction.java). Seen from above, a diamond is a square
turned by 45 degrees and a row is half a tile tall, so a FreeCol map of w x h tiles covers the
ground of a square map of about w*sqrt(2) x h/sqrt(2) squares. Copying tile (x, y) to square
(x, y) would stretch the map to twice its height and break every river that runs north.

On the ground, in units where a diamond is 128 wide and 128 tall, tile (x, y) has its centre at
(128x + 64(y & 1) + 32, 64y + 32) and is every point within 64 of it in the L1 metric. The map
covers 128w x 64h, and a square of the new map is that box cut into W x H cells.

- Terrain: a square takes the diamond under its centre. The two grids do not line up, so about
  one diamond in six is never sampled and as many are sampled twice; for terrain that is fine.
- Placed things are put forward instead: the square that holds a diamond's centre gets the
  village, river, resource or rumour, and takes that diamond's terrain, so nothing is lost to the
  sampling. Diamonds that share an edge have centres 64 apart on both axes, less than a square,
  so a river's squares stay connected. Where two placed diamonds share a square, the stronger
  wins: village, then river (major over minor), then resource, then rumour.
- The frame: a new game on a loaded map makes columns 0, 1, w-2 and w-1 sea lane and the top and
  bottom rows arctic (the original's build_map does this to every map). The FreeCol map is drawn
  inside that frame, and the frame is written as the game will make it, so nothing the author
  drew is overwritten and the .MP shows what is played.
"""
from __future__ import annotations

import math

from fsm_to_mp.model import ConversionWarning, Features, Map, River, Tile, Village, WaterKind

MAX_SIDE = 228  # OpenCol's longest side (the off-map markers start at 0xE4)
FRAME_X, FRAME_Y = 2, 1  # the sea-lane columns and the arctic rows on each side
CLASSIC = (58, 72)  # the original's America: a map that comes within 2 of it is made that size


def _round(value: float) -> int:
    """half up (the web converter's Math.floor(v + 0.5)), not Python's half to even"""
    return math.floor(value + 0.5)


def resampled_size(width: int, height: int, max_side: int = MAX_SIDE) -> tuple[int, int, bool]:
    """the square map's width and height, frame included, and whether it was scaled down to fit"""
    w = max(2 * FRAME_X + 1, _round(width * math.sqrt(2)))
    h = max(2 * FRAME_Y + 1, _round(height / math.sqrt(2)))
    if abs(w - CLASSIC[0]) <= 2 and abs(h - CLASSIC[1]) <= 2:
        # the original's own size: its minimap is drawn wrongly on a map narrower than 58
        return CLASSIC[0], CLASSIC[1], False
    if max(w, h) <= max_side:
        return w, h, False
    k = max_side / max(w, h)
    return max(1, min(max_side, _round(w * k))), max(1, min(max_side, _round(h * k))), True


def _centre(x: int, y: int) -> tuple[int, int]:
    return 128 * x + 64 * (y & 1) + 32, 64 * y + 32


def resample(game_map: Map, max_side: int = MAX_SIDE) -> tuple[Map, list[ConversionWarning]]:
    width, height = game_map.width, game_map.height
    w, h, scaled = resampled_size(width, height, max_side)
    cw, ch = w - 2 * FRAME_X, h - 2 * FRAME_Y  # the FreeCol map's squares, inside the frame
    sx, sy = 128 * width / cw, 64 * height / ch
    warnings: list[ConversionWarning] = []
    if scaled:
        warnings.append(ConversionWarning(0, 0, "scaled-to-fit", f"the map was scaled down to {w} x {h} to fit {max_side} squares a side"))

    def forward(x: int, y: int) -> tuple[int, int]:
        gx, gy = _centre(x, y)
        return FRAME_X + min(cw - 1, math.floor(gx / sx)), FRAME_Y + min(ch - 1, math.floor(gy / sy))

    def under(cx: int, cy: int) -> tuple[int, int]:
        gx, gy = (cx + 0.5) * sx, (cy + 0.5) * sy
        best = None
        y0 = _round((gy - 32) / 64)
        for y in (y0 - 1, y0, y0 + 1):
            if not 0 <= y < height:
                continue
            x0 = _round((gx - 32 - 64 * (y & 1)) / 128)
            for x in (x0 - 1, x0, x0 + 1):
                if not 0 <= x < width:
                    continue
                ex, ey = _centre(x, y)
                d = abs(gx - ex) + abs(gy - ey)
                if best is None or d < best[0]:
                    best = (d, x, y)
        return best[1], best[2]

    source = {(FRAME_X + cx, FRAME_Y + cy): under(cx, cy) for cy in range(ch) for cx in range(cw)}

    # placed diamonds, weakest first, so that a stronger one written later takes the square
    features = game_map.features
    placed: list[tuple[int, int]] = sorted(features.rumours)
    placed += sorted(features.resources)
    rivers = [(t.x, t.y) for t in game_map.tiles if t.river != River.NONE or t.water == WaterKind.GREAT_RIVER]
    rivers.sort(key=lambda p: (game_map.tile_at(*p).river == River.MAJOR or game_map.tile_at(*p).water == WaterKind.GREAT_RIVER, p))
    placed += rivers
    placed += [(v.x, v.y) for v in features.villages]
    for x, y in placed:
        source[forward(x, y)] = (x, y)

    tiles = []
    for cy in range(h):
        for cx in range(w):
            if cy < FRAME_Y or cy >= h - FRAME_Y:
                tiles.append(Tile(cx, cy, "arctic", source_type="frame"))
            elif cx < FRAME_X or cx >= w - FRAME_X:
                tiles.append(Tile(cx, cy, "highSeas", water=WaterKind.HIGH_SEAS, source_type="frame"))
            else:
                t = game_map.tile_at(*source[(cx, cy)])
                tiles.append(Tile(cx, cy, t.terrain, t.forest, t.elevation, t.river, t.water, t.source_type, t.raw))

    resources: dict[tuple[int, int], str] = {}
    for (x, y), kind in sorted(features.resources.items()):
        square = forward(x, y)
        if square in resources:
            if source[square] == (x, y):
                resources[square] = kind
            warnings.append(ConversionWarning(x, y, "resource-merged", "two FreeCol resources fall on one square; one is kept"))
        else:
            resources[square] = kind
    rumours: set[tuple[int, int]] = set()
    for x, y in sorted(features.rumours):
        square = forward(x, y)
        if square in rumours:
            warnings.append(ConversionWarning(x, y, "rumour-merged", "two FreeCol rumours fall on one square; one is kept"))
        rumours.add(square)
    villages = []
    taken: set[tuple[int, int]] = set()
    for v in features.villages:
        square = forward(v.x, v.y)
        if square in taken:
            warnings.append(ConversionWarning(v.x, v.y, "village-merged", "two FreeCol settlements fall on one square; one is kept"))
            continue
        taken.add(square)
        villages.append(Village(square[0], square[1], v.tribe, v.capital, v.name))

    return (
        Map(w, h, tuple(tiles), game_map.layer, game_map.metadata, Features(resources, frozenset(rumours), tuple(villages))),
        warnings,
    )
