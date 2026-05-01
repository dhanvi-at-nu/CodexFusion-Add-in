const folderInput = document.getElementById("projectFolder");
const loadButton = document.getElementById("loadProject");
const statusBox = document.getElementById("status");
const generateAll = document.getElementById("generateAll");
const partSelect = document.getElementById("partSelect");
const applyAssembly = document.getElementById("applyAssembly");
const runButton = document.getElementById("runPreview");
const exportButton = document.getElementById("exportStl");
const output = document.getElementById("output");

function setStatus(text, isError = false) {
  statusBox.textContent = text;
  statusBox.classList.toggle("error", isError);
}

function setParts(parts) {
  partSelect.innerHTML = "";
  if (!parts || parts.length === 0) {
    const option = document.createElement("option");
    option.textContent = "(none)";
    option.value = "";
    partSelect.appendChild(option);
    return;
  }
  for (const part of parts) {
    const option = document.createElement("option");
    option.textContent = part;
    option.value = part;
    partSelect.appendChild(option);
  }
}

async function fusion(action, data = {}) {
  const raw = await adsk.fusionSendData(action, JSON.stringify(data));
  try {
    return JSON.parse(raw);
  } catch (error) {
    return { ok: false, error: raw || String(error) };
  }
}

async function loadState() {
  const result = await fusion("getState");
  if (!result.ok) {
    setStatus(result.error || "Failed to initialize.", true);
    return;
  }
  folderInput.value = result.projectFolder || "";
  setStatus(result.status || "Ready.");
  setParts(result.parts || []);
}

async function loadProject() {
  setStatus("Loading project...");
  const result = await fusion("loadProject", { projectFolder: folderInput.value });
  if (!result.ok) {
    setStatus(result.error || "Load failed.", true);
    return;
  }
  setStatus(result.status || "Project loaded.");
  setParts(result.parts || []);
}

async function runPreview() {
  output.textContent = "Running preview...";
  runButton.disabled = true;
  exportButton.disabled = true;
  const result = await fusion("runPreview", {
    projectFolder: folderInput.value,
    generateAll: generateAll.checked,
    selectedPart: partSelect.value,
    applyAssembly: applyAssembly.checked,
  });
  runButton.disabled = false;
  exportButton.disabled = false;
  if (!result.ok) {
    output.textContent = result.error || "Preview failed.";
    return;
  }
  output.textContent = result.output || "Preview complete.";
}

async function exportStl() {
  output.textContent = "Exporting STL...";
  exportButton.disabled = true;
  const result = await fusion("exportSTL", {
    projectFolder: folderInput.value,
    selectedPart: generateAll.checked ? "" : partSelect.value,
  });
  exportButton.disabled = false;
  if (!result.ok) {
    output.textContent = result.error || "STL export failed.";
    return;
  }
  output.textContent = result.output || "STL export complete.";
}

generateAll.addEventListener("change", () => {
  partSelect.disabled = generateAll.checked;
});
loadButton.addEventListener("click", loadProject);
runButton.addEventListener("click", runPreview);
exportButton.addEventListener("click", exportStl);
window.addEventListener("DOMContentLoaded", loadState);
