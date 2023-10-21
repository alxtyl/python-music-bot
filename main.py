"""
Script used to init the bot
Before running, start lavalink server.
"""

import os
import discord
import logging
from discord.ext import commands

logging.basicConfig(level=logging.DEBUG)

def run():
    cogs = ["cogs.music", "cogs.misc"]
    intents = discord.Intents.all()
    bot = commands.Bot(command_prefix='!', intents=intents)

    @bot.event
    async def on_ready():
        await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name='for !'), status=discord.Status.idle)
        for cog in cogs:
            await bot.load_extension(cog)

    bot.run(os.environ['BOT_KEY'], reconnect=True, root_logger=True)

if __name__ == "__main__":
    run()