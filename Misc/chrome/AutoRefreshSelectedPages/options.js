const DEFAULT_URLS = [
  "https://redchanit.xyz/servers.html",
  "https://alphablaster.neocities.org/"
];

function normalizeLinesToUrlList(multilineText) {
  const lines = (multilineText || "")
    .split(/\r?\n/g)
    .map((line) => line.trim())
    .filter((line) => line.length > 0);

  const normalized = [];
  for (const line of lines) {
    const valueWithScheme = /^[a-zA-Z][a-zA-Z0-9+.-]*:\/\//.test(line)
      ? line
      : `https://${line}`;

    try {
      const parsed = new URL(valueWithScheme);
      normalized.push(parsed.toString());
    } catch {
      // Skip invalid lines silently
    }
  }

  // Deduplicate while preserving order
  const unique = [];
  const seen = new Set();
  for (const url of normalized) {
    if (!seen.has(url)) {
      unique.push(url);
      seen.add(url);
    }
  }
  return unique;
}

function setStatus(text) {
  const statusEl = document.getElementById("status");
  statusEl.textContent = text;
  if (text) {
    setTimeout(() => {
      statusEl.textContent = "";
    }, 2000);
  }
}

async function loadOptions() {
  const data = await chrome.storage.sync.get({ urlList: DEFAULT_URLS });
  const urlList = Array.isArray(data.urlList) ? data.urlList : DEFAULT_URLS;
  document.getElementById("urlList").value = urlList.join("\n");
}

async function saveOptions() {
  const rawText = document.getElementById("urlList").value;
  const urlList = normalizeLinesToUrlList(rawText);
  await chrome.storage.sync.set({ urlList });
  setStatus("Saved.");
}

async function resetOptions() {
  await chrome.storage.sync.set({ urlList: DEFAULT_URLS });
  await loadOptions();
  setStatus("Reset.");
}

document.addEventListener("DOMContentLoaded", () => {
  loadOptions();

  document.getElementById("saveBtn").addEventListener("click", () => {
    saveOptions();
  });

  document.getElementById("resetBtn").addEventListener("click", () => {
    resetOptions();
  });
});
