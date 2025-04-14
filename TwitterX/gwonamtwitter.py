import discord
from discord.ext import commands
import re
import os

# Define intents to allow the bot to listen to message content
intents = discord.Intents.default()
intents.message_content = True

# Instantiate the bot
bot = commands.Bot(command_prefix="!", intents=intents)

# List of allowed guild IDs
allowed_guilds = [0, 0, 0]

# Regular expression to match Twitter or X links
twitter_link_regex = re.compile(r"https?://(x\.com|twitter\.com|fxtwitter\.com|stupidpenisx\.com)/([\w]+)/status/(\d+).*?")

# Path for storing opt-out preferences
opt_out_file = "user_opt_out.txt"

# Load opt-out preferences
def load_opt_out():
    if os.path.exists(opt_out_file):
        with open(opt_out_file, "r") as file:
            return set(line.strip() for line in file.readlines())
    return set()

# Save opt-out preferences
def save_opt_out(opt_out_users):
    with open(opt_out_file, "w") as file:
        file.writelines(f"{user}\n" for user in opt_out_users)

opt_out_users = load_opt_out()

@bot.event
async def on_ready():
    print(f"Bot logged in as {bot.user}")

@bot.event
async def on_message(message):
    # Ignore messages sent by bots
    if message.author.bot:
        return

    # Check if the message is in an allowed guild
    if message.guild and message.guild.id not in allowed_guilds:
        return

    # Check if the author has opted out
    if str(message.author.id) in opt_out_users:
        return

    # Check if the message contains a Twitter/X link
    match = twitter_link_regex.search(message.content)
    if match:
        # Extract the relevant parts of the URL
        username, status_id = match.group(2), match.group(3)

        # Construct the fxtwitter link
        fxtwitter_link = f"https://o.fxtwitter.com/{username}/status/{status_id}"
        original_twitter_link = f"https://twitter.com/{username}/status/{status_id}"

        # Create buttons
        view_original_button = discord.ui.Button(label="View Original", url=original_twitter_link, emoji="🔗")
        opt_out_button = discord.ui.Button(label="Opt Out", style=discord.ButtonStyle.secondary, emoji="🚫")
        opt_in_button = discord.ui.Button(label="Opt In", style=discord.ButtonStyle.success, emoji="✅")
        delete_button = discord.ui.Button(label="Delete", style=discord.ButtonStyle.danger, emoji="❌")

        async def delete_callback(interaction: discord.Interaction):
            if interaction.user == message.author or interaction.user.guild_permissions.manage_messages:
                await interaction.message.delete()
                await interaction.response.send_message("Message deleted.", ephemeral=True)
            else:
                await interaction.response.send_message("You do not have permission to delete this message.", ephemeral=True)

        async def opt_out_callback(interaction: discord.Interaction):
            user_id = str(interaction.user.id)
            opt_out_users.add(user_id)
            save_opt_out(opt_out_users)
            await interaction.response.send_message("You have opted out of link adaptation.", ephemeral=True)

        async def opt_in_callback(interaction: discord.Interaction):
            user_id = str(interaction.user.id)
            if user_id in opt_out_users:
                opt_out_users.remove(user_id)
                save_opt_out(opt_out_users)
            await interaction.response.send_message("You have opted in to link adaptation.", ephemeral=True)

        opt_out_button.callback = opt_out_callback
        opt_in_button.callback = opt_in_callback
        delete_button.callback = delete_callback

        # Create a view and add the buttons
        view = discord.ui.View()
        view.add_item(view_original_button)
        view.add_item(opt_out_button)
        view.add_item(opt_in_button)
        view.add_item(delete_button)

        # Send the message with buttons and attribution
        await message.channel.send(f"Posted by @{message.author.name}: {fxtwitter_link}", view=view)

        # Delete the original message
        await message.delete()

# Replace "YOUR_BOT_TOKEN" with your bot's token
bot.run("YOUR_BOT_TOKEN")