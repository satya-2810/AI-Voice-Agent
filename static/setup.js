// Setup page: collects and saves API keys, then moves to the session page.

const saveKeysBtn = document.getElementById("saveKeysBtn");
const setupNote = document.getElementById("setupNote");

function saveApiKeys() {
  const geminiKey = document.getElementById("geminiKey").value.trim();
  const murfKey = document.getElementById("murfKey").value.trim();
  const assemblyKey = document.getElementById("assemblyKey").value.trim();
  const tavilyKey = document.getElementById("tavilyKey").value.trim();

  if (!geminiKey || !murfKey || !assemblyKey) {
    setupNote.textContent = "Gemini, Murf, and AssemblyAI keys are required.";
    setupNote.className = "form-note error";
    return;
  }

  const keys = { geminiKey, murfKey, assemblyKey, tavilyKey };
  localStorage.setItem("apiKeys", JSON.stringify(keys));

  setupNote.textContent = "Saving…";
  setupNote.className = "form-note";

  fetch("/config", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(keys),
  })
    .then((res) => {
      if (!res.ok) throw new Error("Server rejected keys");
      window.location.href = "/session";
    })
    .catch(() => {
      setupNote.textContent = "Could not save keys. Please try again.";
      setupNote.className = "form-note error";
    });
}

function loadApiKeys() {
  const saved = localStorage.getItem("apiKeys");
  if (!saved) return;
  try {
    const { murfKey, assemblyKey, geminiKey, tavilyKey } = JSON.parse(saved);
    document.getElementById("murfKey").value = murfKey || "";
    document.getElementById("assemblyKey").value = assemblyKey || "";
    document.getElementById("geminiKey").value = geminiKey || "";
    document.getElementById("tavilyKey").value = tavilyKey || "";
  } catch (e) {
    /* ignore malformed storage */
  }
}

saveKeysBtn.addEventListener("click", saveApiKeys);

window.addEventListener("DOMContentLoaded", loadApiKeys);