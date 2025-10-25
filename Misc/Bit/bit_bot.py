# bit_bot.py
# Requires: pip install -U "discord.py>=2.3.2"

import random
import asyncio
import logging
import os
import discord
from discord.ext import commands

# --- YOUR BOT TOKEN HERE ---
TOKEN = "PASTE_YOUR_DISCORD_BOT_TOKEN_HERE"

# --- timing config ---
DECIDE_DELAY = 1.5            # wait before starting presence (avoid spoilers)
PRESENCE_TOTAL = 5.0          # total time to keep the temporary status
PRESENCE_BEFORE_REPLY = 0.5   # show the temporary status briefly before sending the reply
STOP_TYPING_BEFORE_REPLY = 1.5  # end typing this long before sending

# --- basic logging ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("bit-bot")

# --- intents ---
intents = discord.Intents.default()
intents.message_content = True  # enable in Dev Portal

# --- bot setup ---
bot = commands.Bot(command_prefix="!", intents=intents)

# lock to avoid presence flapping if multiple triggers overlap
presence_lock = asyncio.Lock()

YES_TEXT = "Yes!"
NO_TEXT  = "No!"
YES_FILE = "bit_yes.mp4"
NO_FILE  = "bit_no.mp4"


async def _replied_to_bot(message: discord.Message) -> bool:
    if not (message.reference and message.reference.message_id):
        return False
    try:
        ref = await message.channel.fetch_message(message.reference.message_id)
        return ref.author.id == bot.user.id
    except Exception:
        return False


async def _reply_with_bit(message: discord.Message) -> None:
    decision_is_yes = bool(random.getrandbits(1))
    text = YES_TEXT if decision_is_yes else NO_TEXT
    filename = YES_FILE if decision_is_yes else NO_FILE
    target_status = discord.Status.idle if decision_is_yes else discord.Status.dnd

    # Prepare attachment if present
    file_kw = {}
    try:
        if os.path.isfile(filename):
            file_kw = {"file": discord.File(fp=filename, filename=os.path.basename(filename))}
        else:
            log.warning("Attachment %s not found; sending without attachment.", filename)
    except Exception as e:
        log.exception("Failed to open attachment %s: %s", filename, e)

    # Start typing immediately; we will exit typing BEFORE the actual send
    async with message.channel.typing():
        # Think a bit so presence doesn't spoil the outcome
        await asyncio.sleep(DECIDE_DELAY)

        # Flip presence (guarded so multiple triggers don't thrash)
        async with presence_lock:
            try:
                await bot.change_presence(status=target_status, activity=None)
            except Exception as e:
                log.warning("Unable to change presence: %s", e)

            # Briefly show the status before we post the message
            await asyncio.sleep(PRESENCE_BEFORE_REPLY)

        # Exit typing context now so clients can clear the indicator
    await asyncio.sleep(STOP_TYPING_BEFORE_REPLY)

    # Send the reply (threaded if possible)
    sent_ok = False
    try:
        await message.reply(content=text, mention_author=True, **file_kw)
        sent_ok = True
    except discord.Forbidden:
        try:
            await message.channel.send(content=f"{message.author.mention} {text}", **file_kw)
            sent_ok = True
        except Exception as e:
            log.exception("Failed channel send fallback: %s", e)
    except Exception as e:
        log.exception("Failed to send reply: %s", e)
        # Retry without file in case attachment was the issue
        try:
            await message.reply(content=text, mention_author=True)
            sent_ok = True
        except Exception as e2:
            log.exception("Retry without file also failed: %s", e2)

    # Keep the temporary presence for the remainder up to PRESENCE_TOTAL
    # Presence started DECIDE_DELAY seconds after trigger and was visible for PRESENCE_BEFORE_REPLY
    elapsed_since_presence_start = PRESENCE_BEFORE_REPLY + STOP_TYPING_BEFORE_REPLY
    remainder = max(0.0, PRESENCE_TOTAL - elapsed_since_presence_start)

    await asyncio.sleep(remainder)

    # Restore to online
    try:
        await bot.change_presence(status=discord.Status.online, activity=None)
    except Exception as e:
        log.warning("Unable to restore presence: %s", e)

    if not sent_ok:
        log.warning("No reply was successfully sent.")


@bot.event
async def on_ready():
    log.info("Logged in as %s (%s)", bot.user, bot.user.id)
    try:
        await bot.change_presence(status=discord.Status.online)
    except Exception:
        pass


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    # Trigger if bot is mentioned or if user is replying to a bot message
    trigger = False
    if bot.user in getattr(message, "mentions", []):
        trigger = True
    elif message.reference:
        trigger = await _replied_to_bot(message)

    if trigger:
        await _reply_with_bit(message)

    await bot.process_commands(message)


if __name__ == "__main__":
    if not TOKEN or TOKEN == "PASTE_YOUR_DISCORD_BOT_TOKEN_HERE":
        raise SystemExit("Edit this file and set TOKEN to your bot token.")
    bot.run(TOKEN)
