import discord
from discord.ext import commands
import yt_dlp
import asyncio
import os
import re

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
bot = commands.Bot(command_prefix='&', intents=intents)

queue = []
loop_mode = None  # None, 'song', 'queue'
current_url = None

YDL_OPTIONS = {
    'format': 'bestaudio/best',
    'quiet': True,
    'noplaylist': True,
    'default_search': 'ytsearch1:',
    'extract_flat': False,
    'skip_download': True,
}

FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn'
}

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')

@bot.event
async def on_voice_state_update(member, before, after):
    if member.guild.voice_client:
        vc = member.guild.voice_client
        if vc.channel and len([m for m in vc.channel.members if not m.bot]) == 0:
            await vc.disconnect()
            queue.clear()

async def connect_to_voice(ctx):
    if ctx.author.voice is None:
        await ctx.send("You're not in a voice channel.")
        return None
    channel = ctx.author.voice.channel
    vc = discord.utils.get(bot.voice_clients, guild=ctx.guild)
    if vc and vc.channel == channel:
        return vc
    if vc:
        await vc.move_to(channel)
    else:
        vc = await channel.connect()
    return vc

async def stream_audio(ctx, url):
    global current_url
    vc = await connect_to_voice(ctx)
    if not vc:
        return

    ytdl = yt_dlp.YoutubeDL(YDL_OPTIONS)
    loop = asyncio.get_event_loop()
    try:
        info = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=False))
    except Exception as e:
        await ctx.send(f"Error: {e}")
        return

    if 'entries' in info:
        info = info['entries'][0]

    stream_url = info['url']
    title = info.get('title', 'Unknown')
    webpage_url = info.get('webpage_url', url)
    current_url = url

    source = await discord.FFmpegOpusAudio.from_probe(stream_url, **FFMPEG_OPTIONS)
    vc.play(source, after=lambda e: asyncio.run_coroutine_threadsafe(play_next(ctx), bot.loop))
    await ctx.send(f"Now playing: **{title}**\n<{webpage_url}>")

async def play_next(ctx):
    global current_url
    vc = discord.utils.get(bot.voice_clients, guild=ctx.guild)
    if loop_mode == 'song' and current_url:
        await stream_audio(ctx, current_url)
    elif loop_mode == 'queue' and queue:
        next_url = queue.pop(0)
        queue.append(next_url)
        await stream_audio(ctx, next_url)
    elif queue:
        await stream_audio(ctx, queue.pop(0))

@bot.command(aliases=['p'])
async def play(ctx, *, query):
    if not re.match(r'^https?://', query) and not query.lower().endswith(('.mp3', '.wav', '.ogg', '.mp4')):
        query = f"ytsearch1:{query}"
    queue.append(query)
    vc = discord.utils.get(bot.voice_clients, guild=ctx.guild)
    if not vc or not vc.is_playing():
        await play_next(ctx)
    else:
        await ctx.send("Added to queue.")

@bot.command()
async def connect(ctx):
    if await connect_to_voice(ctx):
        await ctx.send("Connected to your voice channel.")

@bot.command()
async def skip(ctx):
    vc = discord.utils.get(bot.voice_clients, guild=ctx.guild)
    if vc and vc.is_playing():
        vc.stop()
        await ctx.send("Skipping to the next track...")
    else:
        await ctx.send("Nothing is currently playing.")

@bot.command()
async def pause(ctx):
    vc = discord.utils.get(bot.voice_clients, guild=ctx.guild)
    if vc and vc.is_playing():
        vc.pause()
        await ctx.send("Playback paused.")
    else:
        await ctx.send("Nothing is currently playing.")

@bot.command()
async def resume(ctx):
    vc = discord.utils.get(bot.voice_clients, guild=ctx.guild)
    if vc and vc.is_paused():
        vc.resume()
        await ctx.send("Playback resumed.")
    else:
        await ctx.send("Nothing is paused.")

@bot.command(aliases=['q', 'queue'])
async def queue_(ctx):
    if queue:
        ytdl = yt_dlp.YoutubeDL({'quiet': True})
        titles = []
        for i, url in enumerate(queue):
            try:
                info = ytdl.extract_info(url, download=False)
                if 'entries' in info:
                    info = info['entries'][0]
                title = info.get('title', url)
                link = info.get('webpage_url', url)
                titles.append(f"{i+1}. {title} <{link}>")
            except:
                titles.append(f"{i+1}. <{url}>")
        await ctx.send("**Queue:**\n" + "\n".join(titles))
    else:
        await ctx.send("Queue is empty.")

@bot.command()
async def clear(ctx):
    queue.clear()
    await ctx.send("Queue cleared.")

@bot.command()
async def stop(ctx):
    vc = discord.utils.get(bot.voice_clients, guild=ctx.guild)
    if vc and vc.is_connected():
        await vc.disconnect()
        queue.clear()
        await ctx.send("Disconnected.")
    else:
        await ctx.send("Not connected.")

@bot.command(aliases=['disconnect'])
async def stop_(ctx):
    await stop(ctx)

@bot.command()
async def loop(ctx, mode: str = None):
    global loop_mode
    if mode == 'song':
        loop_mode = 'song'
        await ctx.send("Looping current song.")
    elif mode == 'queue':
        loop_mode = 'queue'
        await ctx.send("Looping queue.")
    elif mode is None:
        if loop_mode == 'queue':
            loop_mode = None
            await ctx.send("Queue looping disabled.")
        else:
            loop_mode = 'queue'
            await ctx.send("Looping queue.")
    else:
        await ctx.send("Usage: &loop [song|queue] or &stoploop")

@bot.command()
async def stoploop(ctx):
    global loop_mode
    loop_mode = None
    await ctx.send("Looping disabled.")

# Replace with your actual bot token
bot.run('YOUR_TOKEN_HERE')
