"""OpenCol's .MPX map: one chunked container, as OpenCol's docs/proposals/svx-mpx.md specifies.

    header: magic "OCMP"  guard 0D 0A 1A 0A  major u16  minor u16
    chunk:  id (4)  length u32  version u16  flags u16  data  crc32 u32 (over id .. data)
    the last chunk is "END ", with no data and nothing after it

All integers are little-endian. The map's chunks:

    HEAD v1 REQUIRED  w, h (u16 each)
    TERR v1 REQUIRED  plane 0 of the .MP, w*h bytes
    RSRC v1 REQUIRED  one byte per square: 1 the square's terrain bonus, 0 none
    RUMR v1 REQUIRED  one byte per square: 1 a Lost City Rumour, 0 none
    VILL v2 REQUIRED  count u16, then per village: tribe u8 (0-7), flags u8 (1: capital), x u16, y u16
    INFO v1 KEEP      "key=value" lines, ASCII

A layer the map does not have is left out, and the game then makes its own, as for any .MP.
"""
from __future__ import annotations

from dataclasses import dataclass
import struct
import zlib

MAGIC = b"OCMP"
GUARD = b"\r\n\x1a\n"
MAJOR, MINOR = 1, 0
REQUIRED, KEEP = 1, 2
END = b"END "

# FreeCol's resource kinds as the original's bonus numbers
BONUS_OF_KIND = {
    "oasis": 1,
    "grain": 2,
    "cotton": 3,
    "tobacco": 4,
    "sugar": 5,
    "minerals": 6,
    "fish": 7,
    "furs": 8,
    "game": 9,
    "lumber": 10,
    "silver": 12,
    "ore": 13,
}

# the original's bonus for each terrain (g_terrain_bonus, terrain 0-28): -1 none; the game's
# resource_at reads tundra's 0 as 6, minerals
BONUS_OF_TERRAIN = (
    6, 1, 2, 3, 4, 5, 6, 6,      # tundra .. swamp
    9, 1, 8, 9, 10, 10, 6, 6,    # boreal .. rain forest
    9, 1, 8, 9, 10, 10, 6, 6,    # 16-23, unused by maps
    -1, 7, -1, 12, 13,           # arctic, ocean, sea lane, mountains, hills
)

TERRAIN_ARCTIC = 24


def terrain_type(byte: int) -> int:
    """the terrain a plane-0 byte stands for, as the game decodes it (terrain_type)"""
    if byte & 0x20:
        return 27 if byte & 0x80 else 28
    return byte & 0x1F


@dataclass(frozen=True)
class Chunk:
    id: bytes
    version: int
    flags: int
    data: bytes


def write_container(chunks: list[Chunk]) -> bytes:
    out = [MAGIC, GUARD, struct.pack("<HH", MAJOR, MINOR)]
    for c in list(chunks) + [Chunk(END, 0, 0, b"")]:
        if len(c.id) != 4:
            raise ValueError(f"chunk id {c.id!r} is not four bytes")
        head = c.id + struct.pack("<IHH", len(c.data), c.version, c.flags)
        out += [head, c.data, struct.pack("<I", zlib.crc32(head + c.data))]
    return b"".join(out)


def read_container(data: bytes) -> list[Chunk]:
    if data[:4] != MAGIC or data[4:8] != GUARD:
        raise ValueError("not an .MPX file")
    major, _minor = struct.unpack_from("<HH", data, 8)
    if major != MAJOR:
        raise ValueError(f"container version {major} is not {MAJOR}")
    pos, chunks = 12, []
    while True:
        if pos + 12 > len(data):
            raise ValueError("cut short")
        cid = data[pos : pos + 4]
        length, version, flags = struct.unpack_from("<IHH", data, pos + 4)
        end = pos + 12 + length
        if end + 4 > len(data):
            raise ValueError("cut short")
        (crc,) = struct.unpack_from("<I", data, end)
        if crc != zlib.crc32(data[pos:end]):
            raise ValueError(f"chunk {cid!r} is damaged")
        pos = end + 4
        if cid == END:
            if pos != len(data):
                raise ValueError("bytes after its end")
            return chunks
        chunks.append(Chunk(cid, version, flags, data[pos - 4 - length : pos - 4]))
