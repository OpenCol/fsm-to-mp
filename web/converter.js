const SAVEGAME_XML = "savegame.xml";
const RIVER_TYPE = "model.improvement.river";

const FOREST_BASE = {
  borealForest: "tundra",
  scrubForest: "desert",
  mixedForest: "plains",
  broadleafForest: "prairie",
  coniferForest: "grassland",
  tropicalForest: "savannah",
  wetlandForest: "marsh",
  rainForest: "swamp",
};

const WATER_TYPES = {
  ocean: "ocean",
  highSeas: "high_seas",
  lake: "lake",
  greatRiver: "great_river",
};

const BASE_TERRAIN = {
  tundra: 0,
  desert: 1,
  plains: 2,
  prairie: 3,
  grassland: 4,
  savannah: 5,
  marsh: 6,
  swamp: 7,
  arctic: 24,
};

const FOREST_TERRAIN = {
  tundra: 8,
  desert: 9,
  plains: 10,
  prairie: 11,
  grassland: 12,
  savannah: 13,
  marsh: 14,
  swamp: 15,
};

// FreeCol's native nations as the original's tribe numbers (its nation index less 4)
const TRIBES = {
  "model.nation.inca": 0,
  "model.nation.aztec": 1,
  "model.nation.arawak": 2,
  "model.nation.iroquois": 3,
  "model.nation.cherokee": 4,
  "model.nation.apache": 5,
  "model.nation.sioux": 6,
  "model.nation.tupi": 7,
};

export class FsmFormatError extends Error {
  constructor(message) {
    super(message);
    this.name = "FsmFormatError";
  }
}

export function readFsmXml(xmlText) {
  const document = new DOMParser().parseFromString(xmlText, "application/xml");
  const parseError = document.querySelector("parsererror");
  if (parseError) {
    throw new FsmFormatError("savegame.xml is not valid XML");
  }

  const mapElement = document.querySelector("map");
  if (!mapElement) {
    throw new FsmFormatError("savegame.xml contains no <map> element");
  }

  const width = requiredInt(mapElement, "width");
  const height = requiredInt(mapElement, "height");
  const byPosition = new Map();
  const byId = new Map();

  for (const tileElement of childElements(mapElement, "tile")) {
    const tile = readTile(tileElement);
    byPosition.set(`${tile.x},${tile.y}`, tile);
    if (tileElement.getAttribute("id")) {
      byId.set(tileElement.getAttribute("id"), { x: tile.x, y: tile.y });
    }
  }

  const tiles = [];
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      const tile = byPosition.get(`${x},${y}`);
      if (!tile) {
        throw new FsmFormatError(`missing tile at (${x}, ${y})`);
      }
      tiles.push(tile);
    }
  }

  return {
    width,
    height,
    tiles,
    layer: mapElement.getAttribute("layer"),
    metadata: {
      minimumLatitude: mapElement.getAttribute("minimumLatitude") ?? "",
      maximumLatitude: mapElement.getAttribute("maximumLatitude") ?? "",
    },
    features: readFeatures(document, mapElement, byId),
  };
}

// the resources, rumours and native settlements the map places, by FreeCol tile
function readFeatures(document, mapElement, byId) {
  const resources = new Map();
  const rumours = new Set();
  for (const element of mapElement.getElementsByTagName("resource")) {
    const at = byId.get(element.getAttribute("tile"));
    const type = element.getAttribute("type");
    if (at && type) {
      resources.set(key(at.x, at.y), type.split(".").at(-1));
    }
  }
  for (const element of mapElement.getElementsByTagName("lostCityRumour")) {
    const at = byId.get(element.getAttribute("tile"));
    if (at) {
      rumours.add(key(at.x, at.y));
    }
  }
  const nations = new Map();
  for (const element of document.getElementsByTagName("player")) {
    nations.set(element.getAttribute("id"), element.getAttribute("nationId"));
  }
  const villages = [];
  for (const element of document.getElementsByTagName("indianSettlement")) {
    const at = byId.get(element.getAttribute("tile"));
    const tribe = TRIBES[nations.get(element.getAttribute("owner")) ?? ""];
    if (!at || tribe === undefined) {
      continue;
    }
    const capital = (element.getAttribute("settlementType") ?? "").endsWith(".capital");
    villages.push({ x: at.x, y: at.y, tribe, capital, name: element.getAttribute("name") ?? "" });
  }
  return { resources, rumours, villages };
}

export function convertMap(gameMap) {
  const warnings = [];
  const tiles = gameMap.tiles.map((tile) => {
    const converted = { ...tile };

    if (tile.water === "lake") {
      warnings.push(warn(tile, "lake-as-ocean", "FreeCol lake converted to Colonization ocean"));
      converted.water = "ocean";
    } else if (tile.water === "great_river") {
      warnings.push(warn(tile, "great-river-as-major-river", "FreeCol greatRiver converted to savannah with major river"));
      converted.water = "land";
      converted.terrain = "savannah";
      converted.river = "major";
    }

    if (tile.elevation !== "flat" && tile.river !== "none") {
      warnings.push(warn(tile, "elevation-river", "Colonization can encode hill/mountain plus river, but FreeCol normally disallows it"));
    }
    if (tile.raw.owner || tile.raw.owningSettlement) {
      warnings.push(warn(tile, "ownership-lost", "FreeCol tile ownership/native settlement data is not represented in .MP terrain output"));
    }
    if (tile.raw.resourceCount) {
      warnings.push(warn(tile, "resource-lost", "FreeCol tile resource data is not represented in .MP terrain output"));
    }
    if (tile.raw.unsupportedImprovementCount) {
      warnings.push(warn(tile, "improvement-lost", "FreeCol non-river tile improvement data is not represented in .MP terrain output"));
    }

    return converted;
  });

  return {
    map: { ...gameMap, tiles },
    warnings,
  };
}

export function encodePlane0(gameMap) {
  return Uint8Array.from(gameMap.tiles, encodeTile);
}

export function writeMp(gameMap, plane0) {
  const size = gameMap.width * gameMap.height;
  if (plane0.length !== size) {
    throw new Error(`plane0 has ${plane0.length} bytes, expected ${size}`);
  }
  if (gameMap.width < 0 || gameMap.width > 0xffff || gameMap.height < 0 || gameMap.height > 0xffff) {
    throw new Error("MP dimensions must fit 16-bit little-endian header fields");
  }

  const output = new Uint8Array(6 + 3 * size);
  output[0] = gameMap.width & 0xff;
  output[1] = (gameMap.width >> 8) & 0xff;
  output[2] = gameMap.height & 0xff;
  output[3] = (gameMap.height >> 8) & 0xff;
  output[4] = 4;
  output[5] = 0;
  output.set(plane0, 6);
  return output;
}

export function warningCounts(warnings) {
  return warnings.reduce((counts, warning) => {
    counts[warning.code] = (counts[warning.code] ?? 0) + 1;
    return counts;
  }, {});
}

export function outputName(inputName, extension = ".MP") {
  const clean = inputName.trim() || "converted.fsm";
  return clean.replace(/\.[^.]*$/, "") + extension;
}

export function xmlFromUnzippedEntries(entries, decode) {
  const entry = entries[SAVEGAME_XML];
  if (!entry) {
    throw new FsmFormatError(`.fsm archive does not contain ${SAVEGAME_XML}`);
  }
  return decode(entry);
}

function readTile(tileElement) {
  const x = requiredInt(tileElement, "x");
  const y = requiredInt(tileElement, "y");
  const typeId = tileElement.getAttribute("type");
  if (!typeId) {
    throw new FsmFormatError(`tile (${x}, ${y}) has no type`);
  }

  const shortType = typeId.split(".").at(-1);
  let water = WATER_TYPES[shortType] ?? "land";
  let elevation = "flat";
  let forest = false;
  let terrain = shortType;

  if (FOREST_BASE[shortType]) {
    forest = true;
    terrain = FOREST_BASE[shortType];
  } else if (shortType === "hills") {
    elevation = "hills";
  } else if (shortType === "mountains") {
    elevation = "mountains";
  }

  let river = "none";
  const raw = Object.fromEntries([...tileElement.attributes].map((attr) => [attr.name, attr.value]));
  let unsupportedImprovements = 0;

  for (const improvement of tileElement.getElementsByTagName("tileImprovement")) {
    if (improvement.getAttribute("type") === RIVER_TYPE) {
      const magnitude = Number.parseInt(improvement.getAttribute("magnitude") ?? "1", 10);
      river = magnitude >= 2 ? "major" : "minor";
    } else {
      unsupportedImprovements += 1;
    }
  }

  const resourceCount = tileElement.getElementsByTagName("resource").length;
  if (resourceCount) {
    raw.resourceCount = String(resourceCount);
  }
  if (unsupportedImprovements) {
    raw.unsupportedImprovementCount = String(unsupportedImprovements);
  }

  return {
    x,
    y,
    terrain,
    forest,
    elevation,
    river,
    water,
    sourceType: shortType,
    raw,
  };
}

function encodeTile(tile) {
  let base;
  if (tile.water === "high_seas") {
    base = 26;
  } else if (tile.water === "ocean") {
    base = 25;
  } else if (tile.elevation === "mountains" || tile.elevation === "hills") {
    base = BASE_TERRAIN.plains;
  } else if (tile.forest) {
    base = valueFor(FOREST_TERRAIN, tile.terrain);
  } else {
    base = valueFor(BASE_TERRAIN, tile.terrain);
  }

  let value;
  if (tile.elevation === "mountains") {
    value = 0x20 | 0x80 | (base & 0x1f);
  } else if (tile.elevation === "hills") {
    value = 0x20 | (base & 0x1f);
  } else {
    value = base & 0x1f;
  }

  if (tile.river === "minor") {
    value |= 0x40;
  } else if (tile.river === "major") {
    value |= 0x40 | 0x80;
  }
  return value;
}

function valueFor(table, terrain) {
  const value = table[terrain];
  if (value === undefined) {
    throw new FsmFormatError(`unsupported FreeCol terrain ${terrain}`);
  }
  return value;
}

function requiredInt(element, attribute) {
  const value = element.getAttribute(attribute);
  if (value === null) {
    throw new FsmFormatError(`<${element.tagName}> missing '${attribute}'`);
  }
  const parsed = Number.parseInt(value, 10);
  if (!Number.isFinite(parsed)) {
    throw new FsmFormatError(`<${element.tagName}> has invalid '${attribute}'`);
  }
  return parsed;
}

function childElements(element, tagName) {
  return [...element.children].filter((child) => child.tagName === tagName);
}

function warn(tile, code, message) {
  return { x: tile.x, y: tile.y, code, message };
}

// ---- FreeCol's diamond grid onto the square grid (src/fsm_to_mp/resample.py, which explains it) ----

export const MAX_SIDE = 228;
const FRAME_X = 2;
const FRAME_Y = 1;

function key(x, y) {
  return `${x},${y}`;
}

function unkey(text) {
  const [x, y] = text.split(",").map(Number);
  return { x, y };
}

function positionOrder(a, b) {
  return a.x - b.x || a.y - b.y;
}

function roundHalfUp(value) {
  return Math.floor(value + 0.5);
}

export function resampledSize(width, height, maxSide = MAX_SIDE) {
  const w = Math.max(2 * FRAME_X + 1, roundHalfUp(width * Math.SQRT2));
  const h = Math.max(2 * FRAME_Y + 1, roundHalfUp(height / Math.SQRT2));
  if (Math.max(w, h) <= maxSide) {
    return { width: w, height: h, scaled: false };
  }
  const k = maxSide / Math.max(w, h);
  return {
    width: Math.max(1, Math.min(maxSide, roundHalfUp(w * k))),
    height: Math.max(1, Math.min(maxSide, roundHalfUp(h * k))),
    scaled: true,
  };
}

function centre(x, y) {
  return [128 * x + 64 * (y & 1) + 32, 64 * y + 32];
}

export function resample(gameMap, maxSide = MAX_SIDE) {
  const { width, height } = gameMap;
  const { width: w, height: h, scaled } = resampledSize(width, height, maxSide);
  const cw = w - 2 * FRAME_X;
  const ch = h - 2 * FRAME_Y;
  const sx = (128 * width) / cw;
  const sy = (64 * height) / ch;
  const warnings = [];
  if (scaled) {
    warnings.push({ x: 0, y: 0, code: "scaled-to-fit", message: `the map was scaled down to ${w} x ${h} to fit ${maxSide} squares a side` });
  }
  const tileAt = (x, y) => gameMap.tiles[y * width + x];

  const forward = (x, y) => {
    const [gx, gy] = centre(x, y);
    return { x: FRAME_X + Math.min(cw - 1, Math.floor(gx / sx)), y: FRAME_Y + Math.min(ch - 1, Math.floor(gy / sy)) };
  };

  const under = (cx, cy) => {
    const gx = (cx + 0.5) * sx;
    const gy = (cy + 0.5) * sy;
    let best = null;
    const y0 = roundHalfUp((gy - 32) / 64);
    for (const y of [y0 - 1, y0, y0 + 1]) {
      if (y < 0 || y >= height) {
        continue;
      }
      const x0 = roundHalfUp((gx - 32 - 64 * (y & 1)) / 128);
      for (const x of [x0 - 1, x0, x0 + 1]) {
        if (x < 0 || x >= width) {
          continue;
        }
        const [ex, ey] = centre(x, y);
        const d = Math.abs(gx - ex) + Math.abs(gy - ey);
        if (best === null || d < best.d) {
          best = { d, x, y };
        }
      }
    }
    return { x: best.x, y: best.y };
  };

  const source = new Map();
  for (let cy = 0; cy < ch; cy += 1) {
    for (let cx = 0; cx < cw; cx += 1) {
      source.set(key(FRAME_X + cx, FRAME_Y + cy), under(cx, cy));
    }
  }

  // placed diamonds, weakest first, so that a stronger one written later takes the square
  const features = gameMap.features;
  const isMajor = (p) => tileAt(p.x, p.y).river === "major" || tileAt(p.x, p.y).water === "great_river";
  const placed = [...features.rumours].map(unkey).sort(positionOrder);
  placed.push(...[...features.resources.keys()].map(unkey).sort(positionOrder));
  const rivers = gameMap.tiles
    .filter((t) => t.river !== "none" || t.water === "great_river")
    .map((t) => ({ x: t.x, y: t.y }))
    .sort((a, b) => isMajor(a) - isMajor(b) || positionOrder(a, b));
  placed.push(...rivers);
  placed.push(...features.villages.map((v) => ({ x: v.x, y: v.y })));
  for (const p of placed) {
    const square = forward(p.x, p.y);
    source.set(key(square.x, square.y), p);
  }

  const tiles = [];
  for (let cy = 0; cy < h; cy += 1) {
    for (let cx = 0; cx < w; cx += 1) {
      if (cy < FRAME_Y || cy >= h - FRAME_Y) {
        tiles.push({ x: cx, y: cy, terrain: "arctic", forest: false, elevation: "flat", river: "none", water: "land", sourceType: "frame", raw: {} });
      } else if (cx < FRAME_X || cx >= w - FRAME_X) {
        tiles.push({ x: cx, y: cy, terrain: "highSeas", forest: false, elevation: "flat", river: "none", water: "high_seas", sourceType: "frame", raw: {} });
      } else {
        const from = source.get(key(cx, cy));
        tiles.push({ ...tileAt(from.x, from.y), x: cx, y: cy });
      }
    }
  }

  const resources = new Map();
  for (const p of [...features.resources.keys()].map(unkey).sort(positionOrder)) {
    const kind = features.resources.get(key(p.x, p.y));
    const square = forward(p.x, p.y);
    const at = key(square.x, square.y);
    if (resources.has(at)) {
      const from = source.get(at);
      if (from.x === p.x && from.y === p.y) {
        resources.set(at, kind);
      }
      warnings.push({ x: p.x, y: p.y, code: "resource-merged", message: "two FreeCol resources fall on one square; one is kept" });
    } else {
      resources.set(at, kind);
    }
  }
  const rumours = new Set();
  for (const p of [...features.rumours].map(unkey).sort(positionOrder)) {
    const square = forward(p.x, p.y);
    const at = key(square.x, square.y);
    if (rumours.has(at)) {
      warnings.push({ x: p.x, y: p.y, code: "rumour-merged", message: "two FreeCol rumours fall on one square; one is kept" });
    }
    rumours.add(at);
  }
  const villages = [];
  const taken = new Set();
  for (const v of features.villages) {
    const square = forward(v.x, v.y);
    const at = key(square.x, square.y);
    if (taken.has(at)) {
      warnings.push({ x: v.x, y: v.y, code: "village-merged", message: "two FreeCol settlements fall on one square; one is kept" });
      continue;
    }
    taken.add(at);
    villages.push({ ...v, x: square.x, y: square.y });
  }

  return {
    map: { ...gameMap, width: w, height: h, tiles, features: { resources, rumours, villages } },
    warnings,
  };
}

// ---- OpenCol's .MPX (src/fsm_to_mp/mpx/format.py describes the container and its chunks) ----

const REQUIRED = 1;
const KEEP = 2;
const TERRAIN_ARCTIC = 24;
const BONUS_OF_KIND = { oasis: 1, grain: 2, cotton: 3, tobacco: 4, sugar: 5, minerals: 6, fish: 7, furs: 8, game: 9, lumber: 10, silver: 12, ore: 13 };
const BONUS_OF_TERRAIN = [6, 1, 2, 3, 4, 5, 6, 6, 9, 1, 8, 9, 10, 10, 6, 6, 9, 1, 8, 9, 10, 10, 6, 6, -1, 7, -1, 12, 13];

const CRC_TABLE = (() => {
  const table = new Uint32Array(256);
  for (let n = 0; n < 256; n += 1) {
    let c = n;
    for (let k = 0; k < 8; k += 1) {
      c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    }
    table[n] = c >>> 0;
  }
  return table;
})();

function crc32(bytes) {
  let c = 0xffffffff;
  for (const b of bytes) {
    c = CRC_TABLE[(c ^ b) & 0xff] ^ (c >>> 8);
  }
  return (c ^ 0xffffffff) >>> 0;
}

function u16(...values) {
  const out = new Uint8Array(2 * values.length);
  values.forEach((v, i) => {
    out[2 * i] = v & 0xff;
    out[2 * i + 1] = (v >> 8) & 0xff;
  });
  return out;
}

function u32(value) {
  return Uint8Array.of(value & 0xff, (value >>> 8) & 0xff, (value >>> 16) & 0xff, (value >>> 24) & 0xff);
}

function concat(parts) {
  const out = new Uint8Array(parts.reduce((n, p) => n + p.length, 0));
  let at = 0;
  for (const p of parts) {
    out.set(p, at);
    at += p.length;
  }
  return out;
}

function writeContainer(chunks) {
  const parts = [new TextEncoder().encode("OCMP"), Uint8Array.of(0x0d, 0x0a, 0x1a, 0x0a), u16(1, 0)];
  for (const c of [...chunks, { id: "END ", version: 0, flags: 0, data: new Uint8Array(0) }]) {
    const head = concat([new TextEncoder().encode(c.id), u32(c.data.length), u16(c.version, c.flags)]);
    parts.push(head, c.data, u32(crc32(concat([head, c.data]))));
  }
  return concat(parts);
}

function terrainType(byte) {
  if (byte & 0x20) {
    return byte & 0x80 ? 27 : 28;
  }
  return byte & 0x1f;
}

function bonusOf(byte) {
  const t = terrainType(byte);
  return t < BONUS_OF_TERRAIN.length ? BONUS_OF_TERRAIN[t] : -1;
}

function isLand(byte) {
  const t = terrainType(byte);
  return t < TERRAIN_ARCTIC || t === 27 || t === 28;
}

// INFO is ASCII: accents dropped, anything else left out, one line
export function asciiText(value) {
  return value
    .normalize("NFKD")
    .replace(/[^\x00-\x7f]/g, "")
    .replace(/[\x00-\x20\x7f]+/g, " ")
    .replace(/^ +| +$/g, "");
}

export function buildMpx(gameMap, plane0, info) {
  const { width: w, height: h, features } = gameMap;
  if (plane0.length !== w * h) {
    throw new Error(`plane0 has ${plane0.length} bytes, expected ${w * h}`);
  }
  const warnings = [];
  const chunks = [
    { id: "HEAD", version: 1, flags: REQUIRED, data: u16(w, h) },
    { id: "TERR", version: 1, flags: REQUIRED, data: Uint8Array.from(plane0) },
  ];
  let layers = false;

  if (features.resources.size) {
    const plane = new Uint8Array(w * h);
    for (const p of [...features.resources.keys()].map(unkey).sort(positionOrder)) {
      const kind = features.resources.get(key(p.x, p.y));
      const i = p.y * w + p.x;
      if (BONUS_OF_KIND[kind] === bonusOf(plane0[i])) {
        plane[i] = 1;
      } else {
        warnings.push({ x: p.x, y: p.y, code: "resource-mismatch", message: `a ${kind} resource is not this terrain's bonus; dropped` });
      }
    }
    chunks.push({ id: "RSRC", version: 1, flags: REQUIRED, data: plane });
    layers = true;
  }

  if (features.rumours.size) {
    const plane = new Uint8Array(w * h);
    for (const p of [...features.rumours].map(unkey).sort(positionOrder)) {
      const i = p.y * w + p.x;
      if (isLand(plane0[i])) {
        plane[i] = 1;
      } else {
        warnings.push({ x: p.x, y: p.y, code: "rumour-on-water", message: "a rumour on water or arctic; dropped" });
      }
    }
    chunks.push({ id: "RUMR", version: 1, flags: REQUIRED, data: plane });
    layers = true;
  }

  if (features.villages.length) {
    const rows = [];
    const taken = new Set(features.villages.map((v) => key(v.x, v.y)));
    // as the game places a map's village: land below the arctic, so not hills or mountains
    const canStand = (x, y) => x >= 0 && x < w && y >= 0 && y < h && terrainType(plane0[y * w + x]) < TERRAIN_ARCTIC;
    for (const v of features.villages) {
      let { x, y } = v;
      if (!canStand(x, y)) {
        // the nearest square within 2 that can hold it, as the .MPP's villages move up to 2
        const near = [];
        for (let dy = -2; dy <= 2; dy += 1) {
          for (let dx = -2; dx <= 2; dx += 1) {
            if (canStand(v.x + dx, v.y + dy) && !taken.has(key(v.x + dx, v.y + dy))) {
              near.push([Math.max(Math.abs(dx), Math.abs(dy)), Math.abs(dx) + Math.abs(dy), v.x + dx, v.y + dy]);
            }
          }
        }
        near.sort((a, b) => a[0] - b[0] || a[1] - b[1] || a[2] - b[2] || a[3] - b[3]);
        const name = asciiText(v.name);
        if (!near.length) {
          warnings.push({ x: v.x, y: v.y, code: "village-unplaceable", message: `settlement '${name}' has no square within 2 where a village can stand; dropped` });
          continue;
        }
        [, , x, y] = near[0];
        taken.add(key(x, y));
        warnings.push({ x: v.x, y: v.y, code: "village-moved", message: `settlement '${name}' moved to ${x},${y}: no village can stand on hills, mountains or arctic` });
      }
      rows.push(Uint8Array.of(v.tribe, v.capital ? 1 : 0), u16(x, y));
    }
    chunks.push({ id: "VILL", version: 2, flags: REQUIRED, data: concat([u16(rows.length / 2), ...rows]) });
    layers = true;
  }

  const fields = { ...info };
  if (!("features" in fields)) {
    fields.features = layers ? "map:layers" : "";
  }
  const lines = Object.entries(fields).map(([k, v]) => `${k}=${asciiText(v)}\n`).join("");
  chunks.push({ id: "INFO", version: 1, flags: KEEP, data: new TextEncoder().encode(lines) });
  return { bytes: writeContainer(chunks), warnings };
}
