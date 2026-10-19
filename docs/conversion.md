# Conversion Rules

The converter maps FreeCol Classic terrain to the original Colonization plane-0
terrain byte. It emits warnings for approximations and lost state.

## Geometry

FreeCol's map is not a square grid. It draws diamonds in staggered rows: north
is two rows up, north-east one row up (FreeCol's `Direction.java`). Seen from
above, each diamond is a square turned by 45 degrees and each row is half a
tile tall. Copying FreeCol tile (x, y) to square (x, y), as version 0.1 did,
makes a map twice as tall as it should be and breaks every river that runs
north into dots.

So the converter resamples the map onto squares (`src/fsm_to_mp/resample.py`):

- A FreeCol map of w x h tiles becomes round(w x 1.414) x round(h / 1.414)
  squares, about the same number of squares as it had tiles. FreeCol's "small"
  maps (40 x 100) become 57 x 71, the size of the original's America (58 x 72).
- A map over 228 squares a side (OpenCol's limit) is scaled down to fit, with
  the warning `scaled-to-fit`.
- **Terrain:** each square takes the diamond under its centre.
- **Placed things** are put forward instead: the square that holds a diamond's
  centre gets that diamond's village, river, resource or rumour, and takes its
  terrain. Sampling would miss about one diamond in six; forward placement
  misses none, and rivers stay connected. Where two placed diamonds fall on one
  square, the stronger wins: village, then river (major over minor), then
  resource, then rumour.
- **The frame:** a new game on a loaded map makes columns 0, 1, w-2 and w-1 sea
  lane and the top and bottom rows arctic. The FreeCol map is drawn inside that
  frame, and the frame is written as the game will make it.

`--copy-tiles` keeps 0.1's square-for-square copy.

## Exact Terrain

| FreeCol type | `.MP` ID / bits | Result |
| --- | --- | --- |
| `model.tile.tundra` | `0` | tundra |
| `model.tile.desert` | `1` | desert |
| `model.tile.plains` | `2` | plains |
| `model.tile.prairie` | `3` | prairie |
| `model.tile.grassland` | `4` | grassland |
| `model.tile.savannah` | `5` | savannah |
| `model.tile.marsh` | `6` | marsh |
| `model.tile.swamp` | `7` | swamp |
| `model.tile.borealForest` | `8` | boreal forest |
| `model.tile.scrubForest` | `9` | scrub forest |
| `model.tile.mixedForest` | `10` | mixed forest |
| `model.tile.broadleafForest` | `11` | broadleaf forest |
| `model.tile.coniferForest` | `12` | conifer forest |
| `model.tile.tropicalForest` | `13` | tropical forest |
| `model.tile.wetlandForest` | `14` | wetland forest |
| `model.tile.rainForest` | `15` | rain forest |
| `model.tile.arctic` | `24` | arctic |
| `model.tile.ocean` | `25` | ocean |
| `model.tile.highSeas` | `26` | sea lane/high seas |
| `model.tile.hills` | `0x20 \| 2` | hills over plains base |
| `model.tile.mountains` | `0x20 \| 0x80 \| 2` | mountains over plains base |

Original Colonization stores hills and mountains as overlay bits over a normal
low-five-bit terrain. FreeCol elevation tiles are standalone, so this converter
uses plains as their neutral underlying base.

## Rivers

`tileImprovement type="model.improvement.river"` is converted from magnitude:

| FreeCol river magnitude | `.MP` bits | Result |
| ---: | --- | --- |
| `1` | `0x40` | minor river |
| `2` or greater | `0x40 \| 0x80` | major river |

River connection `style` is lost. Colonization renders river/coast details from
adjacent terrain; the `.MP` terrain byte does not preserve FreeCol's explicit
connection string.

## Approximated

| FreeCol type | Conversion | Warning |
| --- | --- | --- |
| `model.tile.lake` | ocean (`25`) | `lake-as-ocean` |
| `model.tile.greatRiver` | savannah plus major river | `great-river-as-major-river` |

The original `.MP` table has ocean and sea lane/high seas but no distinct lake
or great-river water terrain. Great rivers in FreeCol are water tiles navigable
by ships, whereas original Colonization major rivers are land-tile overlays.

## Placed things in the `.MPX`

`--mpx` (and the web page's second download) also writes OpenCol's `.MPX`,
which carries what the `.MP` cannot, by the original's rules:

| FreeCol | `.MPX` | Dropped, with a warning |
| --- | --- | --- |
| resources | `RSRC`: the square has its terrain's bonus | a kind that is not the terrain's bonus (`resource-mismatch`; mostly lumber on mixed forest, where the original has beaver) |
| Lost City Rumours | `RUMR` | one on water or arctic (`rumour-on-water`) |
| native settlements, tribe and capital | `VILL` version 2, placed exactly | none: one on hills, mountains or arctic, where the original places no village, moves to the nearest square within 2 that can hold it (`village-moved`) |

What a village teaches, what it wants and its braves are not kept: the game
gives every village its own, as on any map.

## Lost

The `.MP` is a map terrain file, not a savegame. These FreeCol features are
not written to `.MP` (the `.MPX` keeps resources, rumours and settlements, above):

- regions and region names
- native settlements
- tile ownership
- resources and fish bonuses
- lost-city rumours
- roads and plows
- tile `style`, `connected`, and `contiguity`
- players, markets, units, Europe/high-seas objects, and all other game state

When a source tile has owner or settlement attributes, the converter emits
`ownership-lost`. When it has resource children or non-river improvements, it
emits `resource-lost` or `improvement-lost`.
