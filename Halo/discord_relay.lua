-- discord_relay.lua - SAPP Lua plugin to relay joins, leaves, and chat to Discord
-- api_version must match your SAPP build; 1.12.0.0 works on current releases.

api_version = "1.12.0.0"

-- =========================
-- ====== CONFIGURE ========
-- =========================
local CONFIG = {
    WEBHOOK_URL = "https://discord.com/api/webhooks/PASTE_YOURS_HERE",
    BOT_NAME    = "HaloCE Relay",
    USE_CURL    = true,     -- true = curl; false = PowerShell Invoke-RestMethod
    TIMEOUT_SEC = 5,
    SEND_IP     = true,     -- <— keep true to include IP:port
    INCLUDE_SERVER_INFO = true, -- prepend [ServerName:Map]
    MAX_CONTENT_LEN = 1800,
    RELAY_CHAT  = true,
    RELAY_JOIN  = true,
    RELAY_LEAVE = true
}

-- =========================
-- ====== UTILITIES ========
-- =========================

local function clamp_len(s, max)
    if #s <= max then return s end
    return s:sub(1, max) .. " …"
end

local function json_escape(s)
    s = s:gsub("\\", "\\\\")
    s = s:gsub("\"", "\\\"")
    s = s:gsub("\b", "\\b")
    s = s:gsub("\f", "\\f")
    s = s:gsub("\n", "\\n")
    s = s:gsub("\r", "\\r")
    s = s:gsub("\t", "\\t")
    return s
end

local function sanitize_mentions(s)
    return s:gsub("<@[%!&]?%d+>", "@user"):gsub("@everyone", "@ everyone"):gsub("@here", "@ here")
end

-- Return SAPP's raw $ip value (usually "A.B.C.D:port") with no masking
local function get_player_ip(pid)
    local raw = get_var(pid, "$ip") or ""
    if raw == "" or raw == "unknown" then return "unknown" end
    return raw
end

local function server_prefix()
    if not CONFIG.INCLUDE_SERVER_INFO then return "" end
    local srv_name = get_var(0, "$servername") or "Server"
    local map      = get_var(0, "$map") or "map"
    return "[" .. map .. "] "
end

local function build_payload(content)
    content = sanitize_mentions(content)
    content = clamp_len(content, CONFIG.MAX_CONTENT_LEN)
    local payload = string.format(
        '{"content":"%s","username":"%s","allowed_mentions":{"parse":[]}}',
        json_escape(content),
        json_escape(CONFIG.BOT_NAME)
    )
    return payload
end

local function write_temp_file(data)
    local tmp = os.tmpname()
    local f = io.open(tmp, "wb")
    if not f then return nil end
    f:write(data)
    f:close()
    return tmp
end

local function sh(cmd)
    os.execute(cmd)
end

local function send_via_curl(payload)
    local path = write_temp_file(payload)
    if not path then return end
    local cmd = string.format(
        'curl -m %d -s -H "Content-Type: application/json" -X POST --data-binary "@%s" "%s" >nul 2>&1',
        CONFIG.TIMEOUT_SEC, path, CONFIG.WEBHOOK_URL
    )
    sh(cmd)
    os.remove(path)
end

local function send_via_powershell(payload)
    local path = write_temp_file(payload)
    if not path then return end
    local ps = string.format(
        'powershell -NoProfile -ExecutionPolicy Bypass -Command "try { ' ..
        "$body = Get-Content -Raw -Encoding Byte '%s'; " ..
        "Invoke-RestMethod -Uri '%s' -Method Post -ContentType 'application/json' -Body $body | Out-Null } catch {}\"",
        path, CONFIG.WEBHOOK_URL
    )
    sh(ps)
    os.remove(path)
end

local function post_to_discord(content)
    if not CONFIG.WEBHOOK_URL or CONFIG.WEBHOOK_URL == "" or CONFIG.WEBHOOK_URL:find("PASTE_YOURS_HERE", 1, true) then
        return
    end
    local payload = build_payload(content)
    if CONFIG.USE_CURL then
        send_via_curl(payload)
    else
        send_via_powershell(payload)
    end
end

-- =========================
-- ====== CALLBACKS ========
-- =========================

function OnScriptLoad()
    if CONFIG.RELAY_JOIN  then register_callback(cb['EVENT_JOIN'],  "OnJoin")  end
    if CONFIG.RELAY_LEAVE then register_callback(cb['EVENT_LEAVE'], "OnLeave") end
    if CONFIG.RELAY_CHAT  then register_callback(cb['EVENT_CHAT'],  "OnChat")  end
end

function OnScriptUnload()
    -- nothing to clean up
end

function OnJoin(pid)
    if not CONFIG.RELAY_JOIN then return end
    local name = get_var(pid, "$name") or ("Player#" .. tostring(pid))
    local msg  = server_prefix() .. "[JOIN] " .. name
    if CONFIG.SEND_IP then
        local ip = get_player_ip(pid) -- now plain (e.g., "1.2.3.4:2302")
        msg = msg .. " (" .. ip .. ")"
    end
    post_to_discord(msg)
end

function OnLeave(pid)
    if not CONFIG.RELAY_LEAVE then return end
    local name = get_var(pid, "$name")
    if not name or name == "" then name = "Player#" .. tostring(pid) end
    local msg = server_prefix() .. "[LEAVE] " .. name
    post_to_discord(msg)
end

function OnChat(pid, message)
    if not CONFIG.RELAY_CHAT then return false end
    if not message or message == "" then return false end
    local name = get_var(pid, "$name") or ("Player#" .. tostring(pid))
    local formatted = server_prefix() .. "[CHAT] " .. name .. ": " .. message
    post_to_discord(formatted)
    return false
end
