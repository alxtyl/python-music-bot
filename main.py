import os
import pynacl
import discord
from discord.ext import commands
import logging

logging.basicConfig(level=logging.DEBUG)

def run():
    intents = discord.Intents.all()

    bot = commands.Bot(command_prefix='!', intents=intents)

    @bot.event
    async def on_ready():
        await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name='for !'))
        await bot.load_extension("music")

    bot.run(os.environ['BOT_KEY'], root_logger=True)

if __name__ == "__main__":
    run()