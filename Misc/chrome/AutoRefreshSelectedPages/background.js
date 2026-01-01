const ALARM_NAME = "autoRefreshTick";
const DEFAULT_REFRESH_MINUTES = 5;

const DEFAULT_URLS = [
  "https://redchanit.xyz/servers.html",
  "https://alphablaster.neocities.org/"
];

function normalizeUrlEntry(rawValue) {
  const trimmedValue = (rawValue || "").trim();
  if (!trimmedValue) return null;

  // Allow entries without scheme by assuming https://
  const valueWithScheme = /^[a-zA-Z][a-zA-Z0-9+.-]*:\/\//.test(trimmedValue)
    ? trimmedValue
    : `https://${trimmedValue}`;

  try {
    // Validate URL format
    const parsed = new URL(valueWithScheme);
    // Normalize: remove trailing whitespace, keep as string
    return parsed.toString();
  } catch {
    return null;
  }
}

async function getConfiguredUrls() {
  const storageData = await chrome.storage.sync.get({ urlList: DEFAULT_URLS });
  const rawList = Array.isArray(storageData.urlList) ? storageData.urlList : DEFAULT_URLS;

  const normalizedList = rawList
    .map(normalizeUrlEntry)
    .filter((entry) => entry !== null);

  // If user somehow clears everything, keep it safe (no refresh)
  return normalizedList;
}

function urlMatchesAnyEntry(tabUrl, configuredUrls) {
  if (!tabUrl) return false;

  // Exact match OR "startsWith" match if the entry is a site root.
  // Example: if entry is https://example.com/ then it matches any page under it.
  for (const entry of configuredUrls) {
    if (tabUrl === entry) return true;

    // If entry ends with '/', treat it as a prefix rule
    if (entry.endsWith("/") && tabUrl.startsWith(entry)) return true;
  }
  return false;
}

async function refreshMatchingTabs() {
  const configuredUrls = await getConfiguredUrls();

  if (!configuredUrls.length) return;

  const tabs = await chrome.tabs.query({});

  for (const tab of tabs) {
    // Skip chrome://, edge://, extensions pages, etc.
    const tabUrl = tab.url || "";
    if (!tabUrl.startsWith("http://") && !tabUrl.startsWith("https://")) continue;

    if (urlMatchesAnyEntry(tabUrl, configuredUrls)) {
      try {
        await chrome.tabs.reload(tab.id, { bypassCache: false });
      } catch {
        // Ignore failures (tab closing, permission limits, etc.)
      }
    }
  }
}

async function ensureAlarm() {
  const existing = await chrome.alarms.get(ALARM_NAME);
  if (!existing) {
    chrome.alarms.create(ALARM_NAME, { periodInMinutes: DEFAULT_REFRESH_MINUTES });
  }
}

chrome.runtime.onInstalled.addListener(async () => {
  // Set defaults only if not already set
  const current = await chrome.storage.sync.get({ urlList: null });
  if (!Array.isArray(current.urlList)) {
    await chrome.storage.sync.set({ urlList: DEFAULT_URLS });
  }
  await ensureAlarm();
});

chrome.runtime.onStartup.addListener(async () => {
  await ensureAlarm();
});

chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm && alarm.name === ALARM_NAME) {
    refreshMatchingTabs();
  }
});
