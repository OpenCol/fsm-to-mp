import { strFromU8, unzipSync } from "https://cdn.jsdelivr.net/npm/fflate@0.8.2/esm/browser.js";
import {
  buildMpx,
  convertMap,
  encodePlane0,
  outputName,
  readFsmXml,
  resample,
  warningCounts,
  writeMp,
  xmlFromUnzippedEntries,
} from "./converter.js";

const fileInput = document.querySelector("[data-file]");
const status = document.querySelector("[data-status]");
const details = document.querySelector("[data-details]");
const download = document.querySelector("[data-download]");
const downloadMpx = document.querySelector("[data-download-mpx]");
const version = document.querySelector('meta[name="version"]').content;
const warningList = document.querySelector("[data-warnings]");

fileInput.addEventListener("change", convertSelectedFile);

async function convertSelectedFile() {
  resetResult();

  const file = fileInput.files?.[0];
  if (!file) {
    setStatus("Waiting for a map.", "line");
    return;
  }

  try {
    setStatus("Reading map...", "line");
    const archiveBytes = new Uint8Array(await file.arrayBuffer());
    const entries = unzipSync(archiveBytes);
    const xml = xmlFromUnzippedEntries(entries, strFromU8);
    const sourceMap = readFsmXml(xml);
    // as the command-line tool: the warnings are the FreeCol tiles', then the resampling's and the .MPX's
    const warnings = convertMap(sourceMap).warnings;
    const squares = resample(sourceMap);
    const converted = convertMap(squares.map).map;
    const plane0 = encodePlane0(converted);
    const title = file.name.replace(/\.[^.]*$/, "");
    const mpx = buildMpx(converted, plane0, { title, converter: `fsm-to-mp ${version}` });
    warnings.push(...squares.warnings, ...mpx.warnings);

    offer(download, writeMp(converted, plane0), outputName(file.name));
    offer(downloadMpx, mpx.bytes, outputName(file.name, ".MPX"));

    renderDetails(sourceMap, converted, warnings.filter((w) => w.code !== "resource-lost"));
    setStatus("Converted.", "ok");
  } catch (error) {
    setStatus(error instanceof Error ? error.message : String(error), "danger");
  }
}

function offer(link, bytes, filename) {
  link.href = URL.createObjectURL(new Blob([bytes], { type: "application/octet-stream" }));
  link.download = filename;
  link.hidden = false;
  link.textContent = `Download ${filename}`;
}

function resetResult() {
  for (const link of [download, downloadMpx]) {
    if (link.href) {
      URL.revokeObjectURL(link.href);
    }
    link.hidden = true;
    link.removeAttribute("href");
    link.removeAttribute("download");
    link.textContent = "Download";
  }
  details.textContent = "";
  warningList.replaceChildren();
}

function renderDetails(gameMap, converted, warnings) {
  details.innerHTML = `
    <div class="col-prop">
      <dt class="col-prop-label">FreeCol size</dt>
      <dd class="col-prop-desc">${gameMap.width} x ${gameMap.height}</dd>
    </div>
    <div class="col-prop">
      <dt class="col-prop-label">Map size</dt>
      <dd class="col-prop-desc">${converted.width} x ${converted.height}</dd>
    </div>
    <div class="col-prop">
      <dt class="col-prop-label">Placed</dt>
      <dd class="col-prop-desc">${gameMap.features.resources.size} resources, ${gameMap.features.rumours.size} rumours, ${gameMap.features.villages.length} villages</dd>
    </div>
    <div class="col-prop">
      <dt class="col-prop-label">Warnings</dt>
      <dd class="col-prop-desc">${warnings.length}</dd>
    </div>
  `;

  const counts = warningCounts(warnings);
  for (const [code, count] of Object.entries(counts).sort()) {
    const item = document.createElement("li");
    item.className = "col-list-item col-list-item--sub";
    item.innerHTML = `<span class="col-list-i"></span><span><strong>${code}</strong><br><span class="col-dim">${count}</span></span>`;
    warningList.append(item);
  }
}

function setStatus(message, tone) {
  status.textContent = message;
  status.className = `col-note col-note--${tone}`;
}
