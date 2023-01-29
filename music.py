import os
import discord
from discord.ext import commands
import wavelink
import logging
import subprocess

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
    
    @commands.command(brief="Joins the bot into the voice channel")
    async def join(self, ctx):
        await ctx.typing()

        voice = ctx.message.author.voice
        if not voice:
            embed = discord.Embed(title="", description="You're not connected to a voice channel", color=discord.Color.red())
            return await ctx.send(embed=embed) 
        else:
            channel = voice.channel
            self.music_channel = ctx.message.channel
        self.vc = await channel.connect(cls=wavelink.Player)
        embed = discord.Embed(title="", description=f"Joined {channel.name}", color=discord.Color.og_blurple())
        await ctx.send(embed=embed)

    @commands.command(name='leave', aliases=["dc", "disconnect", "bye"], brief="Leaves the channel")
    async def leave(self, ctx):
        # Make sure user is conn to voice channel
        voice = ctx.message.author.voice
        if not voice:
            embed = discord.Embed(title="", description="You're not connected to a voice channel", color=discord.Color.red())
            return await ctx.send(embed=embed)

        if not self.vc or not self.vc.is_connected():
            embed = discord.Embed(title="", description="I'm not connected to a voice channel", color=discord.Color.red())
            return await ctx.send(embed=embed)

        server = ctx.message.guild.voice_client
        await server.disconnect()
            
    @commands.command(brief="Plays a track from YouTube")
    async def play(self, ctx, *title : str):
        await ctx.typing()

        # Join channel if not connected
        if not self.vc or not self.vc.is_connected():
            await ctx.invoke(self.bot.get_command('join'))

        # Get track to play from youtube
        chosen_track = await wavelink.YouTubeTrack.search(query=" ".join(title), return_first=True)
        if chosen_track:
            self.current_track = chosen_track
            if not self.vc.queue.is_empty:
                embed = discord.Embed(title="", description=f"Added {chosen_track.title} to the Queue", color=discord.Color.green())
                await ctx.send(embed=embed)
            self.vc.queue.put(chosen_track)

        # If bot isn't playing a song, play current song
        if self.current_track and self.vc and not self.vc.is_playing():
            embed = discord.Embed(title="", description=f"Now playing: {self.current_track.title}", color=discord.Color.green())
            await ctx.send(embed=embed)
            await self.vc.play(self.current_track)
        
        # If the queue isn't empty and the voice chat isn't playing, play next song
        if not self.vc.queue.is_empty and not self.vc.is_playing():
            self.current_track = self.vc.queue.get()
            embed = discord.Embed(title="", description=f"Now playing: {self.current_track.title}", color=discord.Color.green())
            await ctx.send(embed=embed)
            await self.vc.play(self.current_track)

    @commands.command(brief="Shows what's in the queue")
    async def queue(self, ctx):
        await ctx.typing()

        voice = ctx.message.author.voice
        if not voice:
            embed = discord.Embed(title="", description="You're not connected to a voice channel", color=discord.Color.red())
            return await ctx.send(embed=embed)

        if not self.vc or not self.vc.is_connected():
            embed = discord.Embed(title="", description="I'm not connected to a voice channel", color=discord.Color.red())
            return await ctx.send(embed=embed)

        if self.vc.queue.is_empty:
            embed = discord.Embed(title="", description="The queue is empty", color=discord.Color.red())
            return await ctx.send(embed=embed)

        song_lst = list()
        temp_queue = self.vc.queue.copy()
        
        for i in range(temp_queue.count):
            song = temp_queue.get()
            seconds = int(song.length) % (24 * 3600) 
            hour = seconds // 3600
            seconds %= 3600
            minutes = seconds // 60
            seconds %= 60
            if hour > 0:
                duration = "%dh %02dm %02ds" % (hour, minutes, seconds)
            else:
                duration = "%02dm %02ds" % (minutes, seconds)
            song_formated = str(song.title) + ' - ' + duration
            song_lst.append(song_formated)
        
        embed = discord.Embed(title="Items In Queue", color=discord.Color.dark_blue())
        song_lst = '\n'.join(song_lst)  # Joining the list with newline as the delimiter
        embed.add_field(name="Songs:", value=song_lst)
        return await ctx.send(embed=embed)

    @commands.command(brief="Skips the current song")
    async def skip(self, ctx):
        voice = ctx.message.author.voice
        if not voice:
            embed = discord.Embed(title="", description="You're not connected to a voice channel", color=discord.Color.red())
            return await ctx.send(embed=embed)

        if self.vc.queue.is_empty:
            embed = discord.Embed(title="", description="There are no more tracks in the queue", color=discord.Color.red())
            return await ctx.send(embed=embed)
        self.current_track = self.vc.queue.get()
        await self.vc.play(self.current_track)
    
    @commands.command(brief="Pause playing song")
    async def pause(self, ctx):
        voice = ctx.message.author.voice
        if not voice:
            embed = discord.Embed(title="", description="You're not connected to a voice channel", color=discord.Color.red())
            return await ctx.send(embed=embed)
        await self.vc.pause()
        await ctx.send(f"Paused current track")            
        
    @commands.command(brief="Resumes current paused song")
    async def resume(self, ctx):
        channel = ctx.message.author.voice.channel
        if not channel:
            embed = discord.Embed(title="", description="You're not connected to a voice channel", color=discord.Color.red())
            return await ctx.send(embed=embed)
        await self.vc.resume()
        await ctx.send(f"Resuming current track")

    @commands.command(brief="Clears queue")
    async def clear(self, ctx):
        await ctx.typing()

        voice = ctx.message.author.voice
        if not voice:
            embed = discord.Embed(title="", description="You're not connected to a voice channel", color=discord.Color.red())
            return await ctx.send(embed=embed)
        elif self.vc.queue.is_empty:
            embed = discord.Embed(title="", description="The queue is empty", color=discord.Color.red())
            return await ctx.send(embed=embed)
        else:
            self.vc.queue.clear()
            embed = discord.Embed(title="", description="Queue is cleared", color=discord.Color.green())
            return await ctx.send(embed=embed)
        
    @commands.command(brief="Stops the bot and resets queue")
    async def stop(self, ctx):
        voice = ctx.message.author.voice.channel
        if not voice:
            embed = discord.Embed(title="", description="You're not connected to a voice channel", color=discord.Color.red())
            return await ctx.send(embed=embed)
        elif not self.vc.queue.is_empty:
            self.vc.queue.clear()
        await self.vc.stop()
        
    @commands.command(brief="Sets the output volume")
    async def volume(self, ctx, new_volume : int = 100):
        voice = ctx.message.author.voice
        if not voice:
            embed = discord.Embed(title="", description="You're not connected to a voice channel", color=discord.Color.red())
            return await ctx.send(embed=embed)
        await self.vc.set_volume(new_volume)

    @commands.command(brief="Displays system info", aliases=["spec"])
    async def info(self, ctx):
        py_ver = subprocess.check_output('python3 --version', shell=True).decode('utf-8').strip()
        sys_info = subprocess.check_output('lsb_release -d', shell=True).decode('utf-8').split('\t')[1].strip()

        embed = discord.Embed(title="Currently running:", color=discord.Color.og_blurple())
        info_lst = '\n'.join([py_ver, sys_info])  # Joining the list with newline as the delimiter
        embed.add_field(name="System info", value=info_lst)
        return await ctx.send(embed=embed)

async def setup(bot):
    music_bot = MusicBot(bot)
    await bot.add_cog(music_bot)
    await music_bot.setup()