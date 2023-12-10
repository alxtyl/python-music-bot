"""
Script used to init the bot
Before running, start lavalink server.
"""

import os
import time
import discord
import logging
from discord.ext import commands

logging.basicConfig(level=logging.INFO)

def run():
    logging.info("Bot is started, waiting for Lavalink server to start")
    time.sleep(int(os.environ['WAIT_TIME']))  # Give time for Lavalink server to start up
    cogs = ["cogs.music", "cogs.misc"]
    bot = commands.Bot(commands.when_mentioned_or('!'), intents=discord.Intents.all(), case_insensitive=True)

    @bot.event
    async def on_ready():
        await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name='for !'), status=discord.Status.idle)
        for cog in cogs:
            await bot.load_extension(cog)

    bot.run(os.environ['BOT_KEY'], reconnect=True, root_logger=True)

if __name__ == "__main__":
    run()