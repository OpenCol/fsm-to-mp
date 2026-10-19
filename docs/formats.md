# FreeCol `.fsm` and Colonization `.MP` Formats

Research date: 2026-09-21.

FreeCol upstream inspected at commit
`db87a4da4a18af61a622a3781455090670436247`.

## FreeCol `.fsm`

`.fsm` files are FreeCol map-editor saves. They use the same data-file
container machinery as FreeCol savegames: `FreeColDataFile` treats the file as a
ZIP/JAR archive or directory and `FreeColSavegameFile` reads `savegame.xml`
inside it.

Authoritative sources:

- `src/net/sf/freecol/common/io/FreeColDataFile.java`: ZIP/directory container,
  `findJarDirectory`, and `getInputStream`.
- `src/net/sf/freecol/common/io/FreeColSavegameFile.java`: `SAVEGAME_FILE =
  "savegame.xml"`.
- `src/net/sf/freecol/server/generator/FreeColMapLoader.java`: imports a
  FreeCol map with `FreeColServer.readMap(file, null)`.
- `src/net/sf/freecol/common/model/Game.java`: writes `specification`, players,
  then `map`.
- `src/net/sf/freecol/common/model/Map.java`: map attributes are `width`,
  `height`, `layer`, `minimumLatitude`, `maximumLatitude`; child tiles are
  written row-major, y outer loop and x inner loop.
- `src/net/sf/freecol/common/model/Tile.java`: tile attributes include `x`, `y`,
  `type`, `style`, optional `owner`, `owningSettlement`, `region`,
  `moveToEurope`, `connected`, `contiguity`.
- `src/net/sf/freecol/common/model/TileImprovement.java`: natural improvements
  serialize as `tileImprovement` with `tile`, `type`, `turns`, `magnitude`, and
  optional `style`.

Observed built-in `.fsm` archive entries:

- `savegame.xml`
- `savegame.properties`
- `thumbnail.png`

The map grid is reconstructed from `<map><tile ...>` elements. Tile order in
FreeCol is row-major, but this converter also checks coordinates so it is not
dependent on element order.

Classic terrain definitions come from
`data/rules/classic/specification.xml`. The terrain IDs relevant to this
converter are:

`plains`, `grassland`, `prairie`, `savannah`, `marsh`, `swamp`, `desert`,
`tundra`, `mixedForest`, `coniferForest`, `broadleafForest`,
`tropicalForest`, `wetlandForest`, `rainForest`, `scrubForest`,
`borealForest`, `hills`, `mountains`, `arctic`, `ocean`, `lake`,
`highSeas`, and `greatRiver`.

Forests are represented as distinct tile types with `is-forest="true"`, not as
a separate tile improvement. Hills and mountains are also distinct tile types
with `is-elevation="true"`.

Minor/major rivers are `tileImprovement` children of the tile's
`tileItemContainer`, with `type="model.improvement.river"`. Magnitude `1` is a
minor river; magnitude `2` is a major river in the official maps inspected.
River `style` stores connection shape and cannot be represented by Colonization
`.MP`.

FreeCol data that this converter intentionally drops because `.MP` has no
terrain-plane representation for it includes regions, native settlements,
tile ownership, resources, rumours, roads/plows, tile styles, contiguity,
European entry metadata, players, markets, and all non-map game state.

## Colonization `.MP`

The original format is documented on the OpenCol documentation site:
[`.MP` map files](https://opencol.github.io/docs/formats/shared/mp-map/).

Binary layout:

```text
WORD width                 little-endian
WORD height                little-endian
WORD unknown               observed as 4 in AMER2.MP
BYTE plane0[width*height]  terrain and natural overlays
BYTE plane1[width*height]  game-state bitfield in saves; zeroed by this tool
BYTE plane2[width*height]  ownership/region-like nibbles in saves; zeroed by this tool
```

Total size is `6 + 3 * width * height`.

Plane 0 encoding:

- Low five bits are the terrain ID when bit `0x20` is clear.
- IDs 0..7 are non-forest land terrains.
- IDs 8..15 are forest terrain variants.
- ID 24 is arctic.
- ID 25 is ocean.
- ID 26 is sea lane/high seas.
- Bit `0x20` means elevation overlay; with `0x80` clear it decodes as hills,
  with `0x80` set it decodes as mountains.
- Bit `0x40` means river.
- With river set, `0x80` distinguishes major river from minor river.

Terrain table:

| ID | Meaning |
| ---: | --- |
| 0 | tundra |
| 1 | desert |
| 2 | plains |
| 3 | prairie |
| 4 | grassland |
| 5 | savannah |
| 6 | marsh |
| 7 | swamp |
| 8 | boreal forest |
| 9 | scrub forest |
| 10 | mixed forest |
| 11 | broadleaf forest |
| 12 | conifer forest |
| 13 | tropical forest |
| 14 | wetland forest |
| 15 | rain forest |
| 24 | arctic |
| 25 | ocean |
| 26 | sea lane |
| 27 | mountains, decoded from overlay |
| 28 | hills, decoded from overlay |

FreeCol also ships `ColonizationMapLoader.java` and
`tools/ColonizationMapReader.java`. They are useful corroboration for the
header and plane-0 terrain encoding, but their comments say planes 1 and 2 are
unknown/zero. The local binary RE found live meanings for those planes in saves,
so this converter zeroes them for map-only output and documents them as not
fully representable from `.fsm` terrain alone.

## OpenCol `.MPX`

OpenCol's map file: a chunked container that holds the `.MP`'s terrain plane
and what a map places on it. `src/fsm_to_mp/mpx/format.py` gives the byte
layout; OpenCol's `docs/proposals/svx-mpx.md` is the specification.

```text
header: "OCMP"  0D 0A 1A 0A  major u16 (1)  minor u16 (0)
chunk:  id (4)  length u32  version u16  flags u16  data  crc32 u32 (over id .. data)
last:   "END " with no data
```

| Chunk | Version | Flags | Holds |
| --- | ---: | --- | --- |
| `HEAD` | 1 | REQUIRED | width, height (u16 each) |
| `TERR` | 1 | REQUIRED | plane 0 of the `.MP`, width x height bytes |
| `RSRC` | 1 | REQUIRED | one byte per square: 1 the square's terrain bonus, 0 none |
| `RUMR` | 1 | REQUIRED | one byte per square: 1 a Lost City Rumour, 0 none |
| `VILL` | 2 | REQUIRED | count u16, then per village tribe u8 (0-7), flags u8 (1 the capital), x u16, y u16 |
| `INFO` | 1 | KEEP | `key=value` lines in ASCII: `title`, `author`, `source`, `license`, `converter`, `features` |

REQUIRED is 1 and KEEP is 2. A layer the source map does not have is left out,
and the game then makes its own resources, rumours or villages, as for any
`.MP`. With `VILL`, only the villages listed are placed, each exactly on its
square. Tribe numbers are the original's order: Inca 0, Aztec 1, Arawak 2,
Iroquois 3, Cherokee 4, Apache 5, Sioux 6, Tupi 7.
