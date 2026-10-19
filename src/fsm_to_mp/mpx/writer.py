from __future__ import annotations

from pathlib import Path
import re
import struct
import unicodedata

from fsm_to_mp.model import ConversionWarning, Map
from fsm_to_mp.mpx.format import (
    BONUS_OF_KIND,
    BONUS_OF_TERRAIN,
    KEEP,
    REQUIRED,
    TERRAIN_ARCTIC,
    Chunk,
    terrain_type,
    write_container,
)


def _bonus(byte: int) -> int:
    t = terrain_type(byte)
    return BONUS_OF_TERRAIN[t] if t < len(BONUS_OF_TERRAIN) else -1


def _is_land(byte: int) -> bool:
    """below the arctic, or hills and mountains: where a rumour can be found"""
    t = terrain_type(byte)
    return t < TERRAIN_ARCTIC or t in (27, 28)


def ascii_text(value: str) -> str:
    """INFO is ASCII: accents dropped, anything else left out, one line"""
    text = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[\x00-\x20\x7f]+", " ", text).strip(" ")


def build_mpx(game_map: Map, plane0: bytes, info: dict[str, str]) -> tuple[bytes, list[ConversionWarning]]:
    """the map as an .MPX: its terrain, the layers its features give, and INFO's lines"""
    w, h = game_map.width, game_map.height
    if len(plane0) != w * h:
        raise ValueError(f"plane0 has {len(plane0)} bytes, expected {w * h}")
    if not (0 < w <= 0xFFFF and 0 < h <= 0xFFFF):
        raise ValueError("MPX dimensions must fit 16-bit fields")
    warnings: list[ConversionWarning] = []
    features = game_map.features
    chunks = [Chunk(b"HEAD", 1, REQUIRED, struct.pack("<HH", w, h)), Chunk(b"TERR", 1, REQUIRED, bytes(plane0))]
    layers = False

    if features.resources:
        plane = bytearray(w * h)
        for (x, y), kind in sorted(features.resources.items()):
            i = y * w + x
            if BONUS_OF_KIND.get(kind) == _bonus(plane0[i]):
                plane[i] = 1
            else:
                warnings.append(ConversionWarning(x, y, "resource-mismatch", f"a {kind} resource is not this terrain's bonus; dropped"))
        chunks.append(Chunk(b"RSRC", 1, REQUIRED, bytes(plane)))
        layers = True

    if features.rumours:
        plane = bytearray(w * h)
        for x, y in sorted(features.rumours):
            i = y * w + x
            if _is_land(plane0[i]):
                plane[i] = 1
            else:
                warnings.append(ConversionWarning(x, y, "rumour-on-water", "a rumour on water or arctic; dropped"))
        chunks.append(Chunk(b"RUMR", 1, REQUIRED, bytes(plane)))
        layers = True

    if features.villages:
        rows = []
        taken = {(v.x, v.y) for v in features.villages}

        def can_stand(x: int, y: int) -> bool:
            # as the game places a map's village: land below the arctic, so not hills or mountains
            return 0 <= x < w and 0 <= y < h and terrain_type(plane0[y * w + x]) < TERRAIN_ARCTIC

        for v in features.villages:
            x, y = v.x, v.y
            if not can_stand(x, y):
                # the nearest square within 2 that can hold it, as the .MPP's villages move up to 2
                near = sorted(
                    (max(abs(dx), abs(dy)), abs(dx) + abs(dy), v.x + dx, v.y + dy)
                    for dy in range(-2, 3) for dx in range(-2, 3)
                    if can_stand(v.x + dx, v.y + dy) and (v.x + dx, v.y + dy) not in taken
                )
                name = ascii_text(v.name)
                if not near:
                    warnings.append(ConversionWarning(v.x, v.y, "village-unplaceable", f"settlement {name!r} has no square within 2 where a village can stand; dropped"))
                    continue
                x, y = near[0][2], near[0][3]
                taken.add((x, y))
                warnings.append(ConversionWarning(v.x, v.y, "village-moved", f"settlement {name!r} moved to {x},{y}: no village can stand on hills, mountains or arctic"))
            rows.append(struct.pack("<BBHH", v.tribe, 1 if v.capital else 0, x, y))
        chunks.append(Chunk(b"VILL", 2, REQUIRED, struct.pack("<H", len(rows)) + b"".join(rows)))
        layers = True

    lines = []
    fields = dict(info)
    fields.setdefault("features", "map:layers" if layers else "")
    for key, value in fields.items():
        if not key or "=" in key or not key.isascii() or any(c.isspace() for c in key):
            raise ValueError(f"INFO key {key!r} is not a plain ASCII word")
        lines.append(f"{key}={ascii_text(value)}\n")
    chunks.append(Chunk(b"INFO", 1, KEEP, "".join(lines).encode("ascii")))
    return write_container(chunks), warnings


def write_mpx(path: str | Path, game_map: Map, plane0: bytes, info: dict[str, str]) -> list[ConversionWarning]:
    data, warnings = build_mpx(game_map, plane0, info)
    Path(path).write_bytes(data)
    return warnings
