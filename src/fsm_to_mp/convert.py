from __future__ import annotations

from fsm_to_mp.model import ConversionResult, ConversionWarning, Elevation, Map, River, Tile, WaterKind
from fsm_to_mp.mp.format import BASE_TERRAIN, FOREST_TERRAIN, MpTerrain


def convert_map(game_map: Map) -> ConversionResult:
    warnings: list[ConversionWarning] = []
    converted_tiles: list[Tile] = []

    for tile in game_map.tiles:
        converted, tile_warnings = normalize_tile(tile)
        converted_tiles.append(converted)
        warnings.extend(tile_warnings)

    return ConversionResult(
        Map(game_map.width, game_map.height, tuple(converted_tiles), game_map.layer, game_map.metadata, game_map.features),
        tuple(warnings),
    )


def encode_plane0(game_map: Map) -> bytes:
    return bytes(_encode_tile(tile) for tile in game_map.tiles)


def normalize_tile(tile: Tile) -> tuple[Tile, list[ConversionWarning]]:
    warnings: list[ConversionWarning] = []
    water = tile.water
    terrain = tile.terrain
    river = tile.river

    if water == WaterKind.LAKE:
        warnings.append(_warn(tile, "lake-as-ocean", "FreeCol lake converted to Colonization ocean"))
        water = WaterKind.OCEAN
    elif water == WaterKind.GREAT_RIVER:
        warnings.append(_warn(tile, "great-river-as-major-river", "FreeCol greatRiver converted to savannah with major river"))
        water = WaterKind.LAND
        terrain = "savannah"
        river = River.MAJOR

    if tile.elevation != Elevation.FLAT and tile.river != River.NONE:
        warnings.append(_warn(tile, "elevation-river", "Colonization can encode hill/mountain plus river, but FreeCol normally disallows it"))

    if tile.raw.get("owner") or tile.raw.get("owningSettlement"):
        warnings.append(_warn(tile, "ownership-lost", "FreeCol tile ownership/native settlement data is not represented in .MP terrain output"))
    if tile.raw.get("resourceCount"):
        warnings.append(_warn(tile, "resource-lost", "FreeCol tile resource data is not represented in .MP terrain output"))
    if tile.raw.get("unsupportedImprovementCount"):
        warnings.append(_warn(tile, "improvement-lost", "FreeCol non-river tile improvement data is not represented in .MP terrain output"))

    return (
        Tile(
            x=tile.x,
            y=tile.y,
            terrain=terrain,
            forest=tile.forest,
            elevation=tile.elevation,
            river=river,
            water=water,
            source_type=tile.source_type,
            raw=tile.raw,
        ),
        warnings,
    )


def _encode_tile(tile: Tile) -> int:
    if tile.water == WaterKind.HIGH_SEAS:
        base = int(MpTerrain.HIGH_SEAS)
    elif tile.water == WaterKind.OCEAN:
        base = int(MpTerrain.OCEAN)
    elif tile.elevation in (Elevation.MOUNTAINS, Elevation.HILLS):
        # Original Colonization stores hills/mountains as overlay bits on top of
        # a normal low-five-bit terrain. FreeCol elevation tiles have no
        # underlying base terrain, so use plains as a neutral land base.
        base = int(MpTerrain.PLAINS)
    elif tile.forest:
        base = int(FOREST_TERRAIN[tile.terrain])
    else:
        base = int(BASE_TERRAIN[tile.terrain])

    if tile.elevation == Elevation.MOUNTAINS:
        value = 0x20 | 0x80 | (base & 0x1F)
    elif tile.elevation == Elevation.HILLS:
        value = 0x20 | (base & 0x1F)
    else:
        value = base & 0x1F

    if tile.river == River.MINOR:
        value |= 0x40
    elif tile.river == River.MAJOR:
        value |= 0x40 | 0x80
    return value


def _warn(tile: Tile, code: str, message: str) -> ConversionWarning:
    return ConversionWarning(tile.x, tile.y, code, message)
