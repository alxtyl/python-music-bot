# pynacl needs to be installed as well

import discord
import asyncio
from discord.ext import commands
import music
import os

cogs = [music]
client = commands.Bot(command_prefix='!', intents=discord.Intents.all())

@client.event
async def on_ready():
    print(f'Logged in as {client.user} (ID: {client.user.id})')
    print('------')
    await client.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name='for !'))
    for item in cogs:
        await item.setup(client)

on_ready()

client.run(os.environ['BOT_KEY'])
