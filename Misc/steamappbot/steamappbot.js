// steamappbot.js
// Author: ChatGPT
// discord.js v14 message-prefix bot for Steam player counts + review summaries

require("dotenv").config();
const { Client, GatewayIntentBits } = require("discord.js");

const DISCORD_TOKEN = process.env.DISCORD_TOKEN;
const STEAM_WEB_API_KEY = process.env.STEAM_WEB_API_KEY;
const PREFIX = (process.env.PREFIX || "!").trim();

if (!DISCORD_TOKEN) {
  console.error("Missing DISCORD_TOKEN in .env");
  process.exit(1);
}
if (!STEAM_WEB_API_KEY) {
  console.error("Missing STEAM_WEB_API_KEY in .env");
  process.exit(1);
}

const client = new Client({
  intents: [GatewayIntentBits.Guilds, GatewayIntentBits.GuildMessages, GatewayIntentBits.MessageContent],
});

/**
 * Built-in alias map. Add more as you like.
 * Keys are normalized (lowercase, stripped).
 */
const builtInAliases = new Map([
  ["tf2", "440"],
  ["teamfortress2", "440"],

  ["tf2c", "3545060"],
  ["tf2classic", "3545060"],
  ["tf2classified", "3545060"],

  ["tf2gr", "3826520"],
  ["tfgr", "3826520"],
  ["tfgoldrush", "3826520"],
  ["tf2goldrush", "3826520"],

  // Add these:
  ["dmc", "40"],   // Deathmatch Classic
  ["tfc", "20"],   // Team Fortress Classic
  ["deathmatchclassic", "40"],
  ["teamfortressclassic", "20"],
]);


// Command aliases
const playersCommands = new Set(["players", "nowplaying", "playercount"]);
const reviewsCommands = new Set(["reviews", "rating", "score"]);

// Simple in-memory cache to reduce calls
const cache = {
  // key -> { value, expiresAt }
  map: new Map(),
  get(key) {
    const cached = this.map.get(key);
    if (!cached) return null;
    if (Date.now() > cached.expiresAt) {
      this.map.delete(key);
      return null;
    }
    return cached.value;
  },
  set(key, value, ttlMs) {
    this.map.set(key, { value, expiresAt: Date.now() + ttlMs });
  },
};

function normalizeLookupText(rawText) {
  return String(rawText || "")
    .toLowerCase()
    .replace(/['"]/g, "")
    .replace(/[^a-z0-9]+/g, " ")
    .trim()
    .replace(/\s+/g, "");
}

function isAllDigits(textValue) {
  return /^[0-9]+$/.test(textValue);
}

function formatNumber(value) {
  // Insert commas
  const num = Number(value);
  if (!Number.isFinite(num)) return String(value);
  return num.toLocaleString("en-US");
}

async function fetchJson(url) {
  const response = await fetch(url, {
    headers: {
      "User-Agent": "discord-bot/steam-lookup (contact: you)",
      "Accept": "application/json",
    },
  });
  if (!response.ok) {
    const bodyText = await response.text().catch(() => "");
    throw new Error(`HTTP ${response.status} for ${url}\n${bodyText.slice(0, 250)}`);
  }
  return await response.json();
}

/**
 * Resolve user input -> appid + app name.
 * Input may be: appid digits, built-in alias, exact/keyword name.
 */
async function resolveApp(inputText) {
  const trimmed = String(inputText || "").trim();
  if (!trimmed) {
    return { appid: null, name: null, error: "No app specified." };
  }

  // 1) Direct numeric appid
  if (isAllDigits(trimmed)) {
    const appid = trimmed;
    const name = await getAppName(appid);
    return { appid, name, error: name ? null : "Could not fetch app name." };
  }

  // 2) Built-in alias
  const normalized = normalizeLookupText(trimmed);
  const aliasAppid = builtInAliases.get(normalized);
  if (aliasAppid) {
    const name = await getAppName(aliasAppid);
    return { appid: aliasAppid, name, error: name ? null : "Could not fetch app name." };
  }

  // 3) Store search (keyword / exact)
  const searchResult = await storeSearchFirst(trimmed);
  if (!searchResult) {
    return { appid: null, name: null, error: `No results found for "${trimmed}".` };
  }
  return { appid: String(searchResult.appid), name: searchResult.name, error: null };
}

/**
 * Get app name via store appdetails endpoint.
 * Cached for 24h.
 */
async function getAppName(appid) {
  const cacheKey = `appname:${appid}`;
  const cachedName = cache.get(cacheKey);
  if (cachedName) return cachedName;

  // Steam Store: appdetails
  const url = `https://store.steampowered.com/api/appdetails?appids=${encodeURIComponent(appid)}&cc=us&l=en`;
  const json = await fetchJson(url);

  const entry = json?.[appid];
  const success = entry?.success;
  const name = entry?.data?.name;

  if (!success || !name) return null;

  cache.set(cacheKey, name, 24 * 60 * 60 * 1000);
  return name;
}

/**
 * Steam Store search API - returns first relevant match.
 * Cached for 10 minutes per query.
 */
async function storeSearchFirst(queryText) {
  const normalized = queryText.trim().toLowerCase();
  const cacheKey = `storesearch:${normalized}`;
  const cached = cache.get(cacheKey);
  if (cached) return cached;

  // Store search endpoint:
  // /api/storesearch?term=<term>&l=en&cc=us
  // It returns an object with "items": [{appid, name, ...}, ...]
  const url =
    `https://store.steampowered.com/api/storesearch?term=${encodeURIComponent(queryText)}&l=en&cc=us`;
  const json = await fetchJson(url);

  const firstItem = Array.isArray(json?.items) ? json.items[0] : null;
  if (!firstItem?.appid || !firstItem?.name) {
    cache.set(cacheKey, null, 10 * 60 * 1000);
    return null;
  }

  const result = { appid: firstItem.appid, name: firstItem.name };
  cache.set(cacheKey, result, 10 * 60 * 1000);
  return result;
}

/**
 * Current players via Steam Web API.
 * Cached for 30 seconds per app.
 */
async function getCurrentPlayers(appid) {
  const cacheKey = `players:${appid}`;
  const cached = cache.get(cacheKey);
  if (cached !== null && cached !== undefined) return cached;

  const url =
    `https://api.steampowered.com/ISteamUserStats/GetNumberOfCurrentPlayers/v1/` +
    `?key=${encodeURIComponent(STEAM_WEB_API_KEY)}` +
    `&appid=${encodeURIComponent(appid)}`;

  const json = await fetchJson(url);
  const playerCount = json?.response?.player_count;

  if (!Number.isFinite(playerCount)) {
    throw new Error("Steam API did not return a valid player_count.");
  }

  cache.set(cacheKey, playerCount, 30 * 1000);
  return playerCount;
}

/**
 * Review summary via Steam Store appreviews endpoint.
 * Cached for 5 minutes per app.
 *
 * We compute percent positive ourselves:
 * percent = (total_positive / (total_positive + total_negative)) * 100
 */
async function getReviewSummary(appid) {
  const cacheKey = `reviews:${appid}`;
  const cached = cache.get(cacheKey);
  if (cached) return cached;

  const url =
  `https://store.steampowered.com/appreviews/${encodeURIComponent(appid)}` +
  `?json=1&filter=summary&language=all&purchase_type=all&review_type=all` +
  `&num_per_page=0&cursor=*`;


  const json = await fetchJson(url);
	console.log("REVIEWS DEBUG", appid, {
	success: json?.success,
	review_score_desc: json?.review_score_desc,
	query_summary: json?.query_summary,
	error: json?.error,
	});


  // If an app has no public reviews / no store reviews available, these may be missing.
  const summary = json?.query_summary;
  const reviewScoreDesc = summary?.review_score_desc; // e.g., "Mixed", "Very Positive"
  const totalPositive = summary?.total_positive;
  const totalNegative = summary?.total_negative;

  // Return null instead of throwing.
  if (
    !reviewScoreDesc ||
    !Number.isFinite(totalPositive) ||
    !Number.isFinite(totalNegative)
  ) {
    cache.set(cacheKey, null, 5 * 60 * 1000);
    return null;
  }

  const total = totalPositive + totalNegative;
  const percentPositive = total > 0 ? (totalPositive / total) * 100 : 0;

  const result = {
    label: String(reviewScoreDesc),
    percentPositive,
    totalPositive,
    totalNegative,
    totalReviews: total,
  };

  cache.set(cacheKey, result, 5 * 60 * 1000);
  return result;
}

function parseCommand(messageContent) {
  if (!messageContent.startsWith(PREFIX)) return null;

  const withoutPrefix = messageContent.slice(PREFIX.length).trim();
  if (!withoutPrefix) return null;

  const spaceIndex = withoutPrefix.indexOf(" ");
  const commandName = (spaceIndex === -1 ? withoutPrefix : withoutPrefix.slice(0, spaceIndex)).toLowerCase();
  const argsText = (spaceIndex === -1 ? "" : withoutPrefix.slice(spaceIndex + 1)).trim();

  return { commandName, argsText };
}

client.on("messageCreate", async (message) => {
  if (message.author.bot) return;

  const parsed = parseCommand(message.content);
  if (!parsed) return;

  const { commandName, argsText } = parsed;

  const isPlayers = playersCommands.has(commandName);
  const isReviews = reviewsCommands.has(commandName);

  if (!isPlayers && !isReviews) return;

  if (!argsText) {
    const usage = isPlayers
      ? `Usage: ${PREFIX}${commandName} <appid | name | alias>`
      : `Usage: ${PREFIX}${commandName} <appid | name | alias>`;
    await message.reply(usage);
    return;
  }

  try {
    const resolved = await resolveApp(argsText);
    if (resolved.error || !resolved.appid) {
      await message.reply(resolved.error || "Could not resolve that app.");
      return;
    }

    const appid = resolved.appid;
    const appName = resolved.name || `(appid ${appid})`;

    if (isPlayers) {
      const count = await getCurrentPlayers(appid);
      await message.reply(`There are **${formatNumber(count)}** players online on **${appName}**.`);
      return;
    }

	if (isReviews) {
	const summary = await getReviewSummary(appid);
	
	if (!summary) {
		await message.reply(`No public Steam review summary is available for **${appName}**.`);
		return;
	}
	
	const pct = summary.percentPositive.toFixed(2);
	await message.reply(`Reviews are **${summary.label}** (${pct}%) for **${appName}**.`);
	return;
	}	
  } catch (err) {
    console.error(err);
    await message.reply("Something went wrong fetching Steam data. Try again in a moment.");
  }
});

client.once("ready", () => {
  console.log(`Logged in as ${client.user.tag}`);
  console.log(`Prefix: ${PREFIX}`);
  console.log("Players commands:", [...playersCommands].join(", "));
  console.log("Reviews commands:", [...reviewsCommands].join(", "));
});

client.login(DISCORD_TOKEN);
