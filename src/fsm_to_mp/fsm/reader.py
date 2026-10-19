from __future__ import annotations

from pathlib import Path
import zipfile
import xml.etree.ElementTree as ET

from fsm_to_mp.model import Elevation, Features, Map, River, Tile, Village, WaterKind


SAVEGAME_XML = "savegame.xml"
RIVER_TYPE = "model.improvement.river"

FOREST_BASE = {
    "borealForest": "tundra",
    "scrubForest": "desert",
    "mixedForest": "plains",
    "broadleafForest": "prairie",
    "coniferForest": "grassland",
    "tropicalForest": "savannah",
    "wetlandForest": "marsh",
    "rainForest": "swamp",
}

WATER_TYPES = {
    "ocean": WaterKind.OCEAN,
    "highSeas": WaterKind.HIGH_SEAS,
    "lake": WaterKind.LAKE,
    "greatRiver": WaterKind.GREAT_RIVER,
}


# FreeCol's native nations as the original's tribe numbers (its nation index less 4)
TRIBES = {
    "model.nation.inca": 0,
    "model.nation.aztec": 1,
    "model.nation.arawak": 2,
    "model.nation.iroquois": 3,
    "model.nation.cherokee": 4,
    "model.nation.apache": 5,
    "model.nation.sioux": 6,
    "model.nation.tupi": 7,
}


class FsmFormatError(ValueError):
    """Raised when an .fsm archive does not contain a readable FreeCol map."""


def read_fsm(path: str | Path) -> Map:
    path = Path(path)
    try:
        with zipfile.ZipFile(path) as archive:
            try:
                data = archive.read(SAVEGAME_XML)
            except KeyError as exc:
                raise FsmFormatError(f"{path} does not contain {SAVEGAME_XML}") from exc
    except zipfile.BadZipFile as exc:
        raise FsmFormatError(f"{path} is not a valid FreeCol .fsm ZIP archive") from exc

    root = ET.fromstring(data)
    map_el = root.find(".//map")
    if map_el is None:
        raise FsmFormatError(f"{path} contains no <map> element")

    width = _required_int(map_el, "width")
    height = _required_int(map_el, "height")
    by_pos: dict[tuple[int, int], Tile] = {}
    by_id: dict[str, tuple[int, int]] = {}
    for tile_el in map_el.findall("tile"):
        tile = _read_tile(tile_el)
        by_pos[(tile.x, tile.y)] = tile
        if tile_el.get("id"):
            by_id[tile_el.get("id")] = (tile.x, tile.y)

    tiles: list[Tile] = []
    for y in range(height):
        for x in range(width):
            try:
                tiles.append(by_pos[(x, y)])
            except KeyError as exc:
                raise FsmFormatError(f"missing tile at ({x}, {y})") from exc

    return Map(
        width=width,
        height=height,
        tiles=tuple(tiles),
        layer=map_el.get("layer"),
        metadata={
            "minimumLatitude": map_el.get("minimumLatitude", ""),
            "maximumLatitude": map_el.get("maximumLatitude", ""),
        },
        features=_read_features(root, map_el, by_id),
    )


def _read_features(root: ET.Element, map_el: ET.Element, by_id: dict[str, tuple[int, int]]) -> Features:
    """the resources, rumours and native settlements the map places, by FreeCol tile"""
    resources: dict[tuple[int, int], str] = {}
    rumours: set[tuple[int, int]] = set()
    for el in map_el.iter("resource"):
        if el.get("tile") in by_id and el.get("type"):
            resources[by_id[el.get("tile")]] = el.get("type").rsplit(".", 1)[-1]
    for el in map_el.iter("lostCityRumour"):
        if el.get("tile") in by_id:
            rumours.add(by_id[el.get("tile")])
    nations = {el.get("id"): el.get("nationId") for el in root.iter("player")}
    villages: list[Village] = []
    for el in root.iter("indianSettlement"):
        tribe = TRIBES.get(nations.get(el.get("owner"), ""))
        if el.get("tile") not in by_id or tribe is None:
            continue
        x, y = by_id[el.get("tile")]
        capital = (el.get("settlementType") or "").endswith(".capital")
        villages.append(Village(x, y, tribe, capital, el.get("name", "")))
    return Features(resources, frozenset(rumours), tuple(villages))


def summarize_fsm(path: str | Path) -> dict[str, object]:
    game_map = read_fsm(path)
    types: dict[str, int] = {}
    rivers: dict[str, int] = {}
    for tile in game_map.tiles:
        types[tile.source_type or tile.terrain] = types.get(tile.source_type or tile.terrain, 0) + 1
        if tile.river != River.NONE:
            rivers[tile.river.value] = rivers.get(tile.river.value, 0) + 1
    return {
        "width": game_map.width,
        "height": game_map.height,
        "layer": game_map.layer,
        "tile_types": dict(sorted(types.items())),
        "rivers": rivers,
    }


def _read_tile(tile_el: ET.Element) -> Tile:
    x = _required_int(tile_el, "x")
    y = _required_int(tile_el, "y")
    type_id = tile_el.get("type")
    if not type_id:
        raise FsmFormatError(f"tile ({x}, {y}) has no type")

    short_type = type_id.rsplit(".", 1)[-1]
    water = WATER_TYPES.get(short_type, WaterKind.LAND)
    elevation = Elevation.FLAT
    forest = False
    terrain = short_type

    if short_type in FOREST_BASE:
        forest = True
        terrain = FOREST_BASE[short_type]
    elif short_type == "hills":
        elevation = Elevation.HILLS
    elif short_type == "mountains":
        elevation = Elevation.MOUNTAINS

    river = River.NONE
    raw = {k: v for k, v in tile_el.attrib.items()}
    resources = 0
    unsupported_improvements = 0
    for improvement in tile_el.findall("./tileItemContainer/tileImprovement"):
        if improvement.get("type") == RIVER_TYPE:
            magnitude = int(improvement.get("magnitude", "1"))
            river = River.MAJOR if magnitude >= 2 else River.MINOR
        else:
            unsupported_improvements += 1
    resources = len(tile_el.findall("./tileItemContainer/resource"))
    if resources:
        raw["resourceCount"] = str(resources)
    if unsupported_improvements:
        raw["unsupportedImprovementCount"] = str(unsupported_improvements)

    return Tile(
        x=x,
        y=y,
        terrain=terrain,
        forest=forest,
        elevation=elevation,
        river=river,
        water=water,
        source_type=short_type,
        raw=raw,
    )


def _required_int(el: ET.Element, attr: str) -> int:
    value = el.get(attr)
    if value is None:
        raise FsmFormatError(f"<{el.tag}> missing {attr!r}")
    return int(value)
