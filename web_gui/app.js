const workspaces = {
  editor: document.querySelector("#editor-workspace"),
  ocr: document.querySelector("#ocr-workspace"),
};

const statusMessage = document.querySelector("#status-message");
const toast = document.querySelector("#toast");
const selectionTitle = document.querySelector("#selection-title");
const rotationField = document.querySelector("#rotation-field");
const documentPage = document.querySelector("#document-page");
const commandSearch = document.querySelector(".app-search input");

let selectedObject = document.querySelector(".editable-object.selected");
let activeTool = "select";
let dragState = null;
let rotation = 0;

function showToast(message) {
  toast.textContent = message;
  toast.classList.add("show");
  statusMessage.textContent = message;
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => toast.classList.remove("show"), 1700);
}

function selectWorkspace(name) {
  document.querySelectorAll(".workspace-tab").forEach((tab) => {
    tab.classList.toggle("active", tab.dataset.workspace === name);
  });
  Object.entries(workspaces).forEach(([key, element]) => {
    element.classList.toggle("active", key === name);
  });
  showToast(`${document.querySelector(`[data-workspace="${name}"]`).textContent} opened`);
}

document.querySelectorAll(".workspace-tab").forEach((tab) => {
  tab.addEventListener("click", () => selectWorkspace(tab.dataset.workspace));
});

document.querySelectorAll(".tool").forEach((tool) => {
  tool.addEventListener("click", () => {
    if (tool.dataset.tool) {
      activeTool = tool.dataset.tool;
      document.querySelectorAll(".tool[data-tool]").forEach((button) => {
        button.classList.toggle("active", button === tool);
      });
      showToast(`${tool.textContent} tool selected`);
    }
  });
});

function selectObject(object) {
  selectedObject?.classList.remove("selected");
  selectedObject = object;
  selectedObject.classList.add("selected");
  selectionTitle.textContent = object.dataset.kind || "Object";
  showToast(`${selectionTitle.textContent} selected`);
}

document.querySelectorAll(".editable-object").forEach((object) => {
  object.addEventListener("pointerdown", (event) => {
    if (activeTool !== "select") return;
    selectObject(object);
    object.setPointerCapture(event.pointerId);
    const rect = object.getBoundingClientRect();
    const pageRect = documentPage.getBoundingClientRect();
    dragState = {
      object,
      startX: event.clientX,
      startY: event.clientY,
      left: rect.left - pageRect.left,
      top: rect.top - pageRect.top,
    };
  });
});

document.addEventListener("pointermove", (event) => {
  if (!dragState) return;
  const nextLeft = dragState.left + event.clientX - dragState.startX;
  const nextTop = dragState.top + event.clientY - dragState.startY;
  dragState.object.style.left = `${Math.max(10, nextLeft)}px`;
  dragState.object.style.top = `${Math.max(10, nextTop)}px`;
});

document.addEventListener("pointerup", () => {
  if (dragState) showToast("Object moved");
  dragState = null;
});

document.querySelectorAll("[data-transform]").forEach((button) => {
  button.addEventListener("click", () => {
    if (!selectedObject) return showToast("Select an object first");
    const action = button.dataset.transform;
    if (action === "delete") {
      selectedObject.remove();
      selectedObject = null;
      selectionTitle.textContent = "No selection";
      return showToast("Object deleted");
    }
    rotation += action === "rotate-right" ? 15 : -15;
    selectedObject.style.transform = `rotate(${rotation}deg)`;
    rotationField.value = `${rotation} deg`;
    showToast("Object rotated");
  });
});

document.querySelectorAll(".page-thumb").forEach((thumb) => {
  thumb.addEventListener("click", () => {
    thumb.parentElement.querySelectorAll(".page-thumb").forEach((item) => {
      item.classList.toggle("active", item === thumb);
    });
    showToast("Page selected");
  });
});

document.querySelectorAll("[data-action]").forEach((button) => {
  button.addEventListener("click", () => {
    const labels = {
      open: "Open PDF dialog would appear here",
      save: "Document saved",
      export: "Export PDF ready",
      support: "Voluntary support page would open here",
      "add-page": "Blank page added",
      "add-image": "Image picker would appear here",
    };
    showToast(labels[button.dataset.action] || "Action ready");
  });
});

document.querySelector("#run-ocr")?.addEventListener("click", () => {
  const fill = document.querySelector("#progress-fill");
  const label = document.querySelector("#ocr-percent");
  let progress = 0;
  showToast("OCR started");
  const timer = window.setInterval(() => {
    progress += 8;
    fill.style.width = `${Math.min(progress, 100)}%`;
    label.textContent = `${Math.min(progress, 100)}%`;
    if (progress >= 100) {
      window.clearInterval(timer);
      showToast("Searchable PDF ready");
    }
  }, 140);
});

document.querySelector("#drop-zone")?.addEventListener("dragover", (event) => {
  event.preventDefault();
  event.currentTarget.classList.add("dragging");
});

document.querySelector("#drop-zone")?.addEventListener("dragleave", (event) => {
  event.currentTarget.classList.remove("dragging");
});

document.querySelector("#drop-zone")?.addEventListener("drop", (event) => {
  event.preventDefault();
  event.currentTarget.classList.remove("dragging");
  showToast(`${event.dataTransfer.files.length} file(s) queued for OCR`);
});

window.addEventListener("keydown", (event) => {
  if (event.ctrlKey && event.key.toLowerCase() === "z") {
    event.preventDefault();
    showToast("Undo");
  }
  if (event.ctrlKey && event.key.toLowerCase() === "k") {
    event.preventDefault();
    commandSearch?.focus();
    commandSearch?.select();
    showToast("Command search focused");
  }
});

commandSearch?.addEventListener("input", () => {
  const value = commandSearch.value.trim();
  statusMessage.textContent = value
    ? `Searching commands for "${value}"`
    : "Ready - local files stay on this device";
});
