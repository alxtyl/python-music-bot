import os
import discord
from discord.ext import commands
import wavelink
import logging

logging.basicConfig(level=logging.DEBUG)

class VoiceConnectionError(commands.CommandError):
    """Custom Exception class for connection errors."""

class InvalidVoiceChannel(VoiceConnectionError):
    """Exception for cases of invalid Voice Channels."""

class MusicBot(commands.Cog):
    vc : wavelink.Player = None
    current_track = None
    music_channel = None
    
    def __init__(self, bot):
        self.bot = bot
        
    async def setup(self):
        """
        Sets up a connection to lavalink
        """
        await wavelink.NodePool.create_node(
            bot=self.bot, 
            host="localhost",
            port=2333, 
            password=os.environ['SERVER_PASS']
        )
    
    @commands.Cog.listener()
    async def on_wavelink_node_ready(self, node: wavelink.Node):
        logging.info(f"{node} is ready")
    
    @commands.command(brief="Manually joins the bot into the voice channel")
    async def join(self, ctx):
        await ctx.typing()

        channel = ctx.message.author.voice.channel
        self.music_channel = ctx.message.channel
        if not channel:
            embed = discord.Embed(title="", description="You're not connected to a voice channel", color=discord.Color.red())
            return await ctx.send(embed=embed) 
        self.vc = await channel.connect(cls=wavelink.Player)
        embed = discord.Embed(title="", description=f"Joined {channel.name}", color=discord.Color.blurple())
        await ctx.send(embed=embed)

    @commands.command(name='leave', aliases=["dc", "disconnect", "bye"], brief="Leaves the channel")
    async def leave(self, ctx):
        if not self.vc or not self.vc.is_connected():
            embed = discord.Embed(title="", description="I'm not connected to a voice channel", color=discord.Color.red())
            return await ctx.send(embed=embed)

        server = ctx.message.guild.voice_client
        await server.disconnect()
            
    @commands.command(brief="Plays a track from Youtube")
    async def play(self, ctx, *title : str):
        await ctx.typing()

        chosen_track = await wavelink.YouTubeTrack.search(query=" ".join(title), return_first=True)
        if chosen_track:
            self.current_track = chosen_track
            if not self.vc.queue.is_empty:
                await ctx.send(f"Added {chosen_track.title} to the Queue")
            self.vc.queue.put(chosen_track)

        # If bot isn't playing a song, play current song
        if self.current_track and self.vc and not self.vc.is_playing():
            await ctx.send(f"Now playing: {self.current_track.title}")
            await self.vc.play(self.current_track)
        
        # If the queue isn't empty and the voice chat isn't playing
        # play next song in the queue
        elif not self.vc.queue.is_empty and not self.vc.is_playing():
            self.current_track = self.vc.queue.get()
            await ctx.send(f"Now playing: {self.current_track.title}")
            await self.vc.play(self.current_track)

    @commands.command(brief="Shows what's in the queue")
    async def queue(self, ctx):
        if not self.vc or not self.vc.is_connected():
            embed = discord.Embed(title="", description="I'm not connected to a voice channel", color=discord.Color.red())
            return await ctx.send(embed=embed)

        if self.vc.queue.is_empty:
            embed = discord.Embed(title="", description="The queue is empty", color=discord.Color.red())
            return await ctx.send(embed=embed)

        temp_queue = self.vc.queue.copy()
        queue_store = list()
        
        for i in range(temp_queue.count):
            queue_store.append(temp_queue.get())
        
        embed = discord.Embed(title="Items in queue", description=queue_store, color=discord.Color.green())
        await ctx.send(embed=embed)

    @commands.command(brief="Skips the current song")
    async def skip(self, ctx):
        if self.vc.queue.is_empty:
            await ctx.send("There are no more tracks!")
            return
        self.current_track = self.vc.queue.get()
        await self.vc.play(self.current_track)
    
    @commands.command(brief="Pause playing song")
    async def pause(self, ctx):
        await self.vc.pause()
        await ctx.send(f"Paused current Track")            
        
    @commands.command(brief="Resumes current paused song")
    async def resume(self, ctx):
        await self.vc.resume()
        await ctx.send(f"Resuming current track")
        
    @commands.command(brief="Stops current song")
    async def stop(self, ctx):
        await self.vc.stop()
        
    @commands.command(brief="Sets the output volume")
    async def volume(self, ctx, new_volume : int = 100):
        await self.vc.set_volume(new_volume)

async def setup(bot):
    music_bot = MusicBot(bot)
    await bot.add_cog(music_bot)
    await music_bot.setup()