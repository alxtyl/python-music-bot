import os
import re
import discord
import asyncio
import logging
import wavelink
import subprocess
from discord.ext import commands

TIMEOUT = 1200  # Amount of seconds before the bot disconnects due to nothing being played
logging.getLogger().setLevel(logging.INFO)

class VoiceConnectionError(commands.CommandError):
    """Custom Exception class for connection errors."""

class InvalidVoiceChannel(VoiceConnectionError):
    """Exception for cases of invalid Voice Channels."""

class MusicBot(commands.Cog):
    timer = None
    current_track = None
    music_channel = None
    vc : wavelink.Player = None
    
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

    async def timeout(self):
        await asyncio.sleep(TIMEOUT)
        embed = discord.Embed(title="", description=f"Disconnecting due to inactivity", color=discord.Color.red())
        await self.music_channel.send(embed=embed)
        await self.vc.disconnect()
    
    @commands.Cog.listener()
    async def on_wavelink_node_ready(self, node: wavelink.Node):
        logging.info(f"{node} is ready")

    @commands.Cog.listener()
    async def on_wavelink_track_end(self, player: wavelink.Player, track: wavelink.Track, reason):
        # On the end of each track, reset the AFK timer
        # If the queue is not empty, play next song
        if self.timer is not None:
            self.timer.cancel()
            self.timer = None
            logging.info("AFK timer reset")
        if not player.queue.is_empty:
            next_song = player.queue.get()
            embed = discord.Embed(title="", description=f"Now playing [{self.current_track.title}]({self.current_track.info['uri']}) [{self.current_track.author}]", color=discord.Color.green())
            await self.music_channel.send(embed=embed)
            await player.play(next_song)
        if player.is_playing() or not player.is_connected():
            return
        self.timer = asyncio.create_task(self.timeout())
            
    @commands.command(name='join', aliases=['connect', 'j'], description="Joins the bot into the voice channel")
    async def join(self, ctx):
        await ctx.typing()

        voice = ctx.message.author.voice
        if not voice or ctx.author.voice.channel is None or ctx.author.voice is None:
            embed = discord.Embed(title="", description="You're not connected to a voice channel", color=discord.Color.red())
            return await ctx.send(embed=embed)

        channel = voice.channel    
        voice_channel = ctx.author.voice.channel
        self.music_channel = ctx.message.channel

        if ctx.voice_client is None:   
            self.vc = await channel.connect(cls=wavelink.Player, self_deaf=True)
            embed = discord.Embed(title="", description=f"Joined {channel.name}", color=discord.Color.blurple())
            return await ctx.send(embed=embed)
        elif ctx.guild.voice_client.channel == voice_channel:
            embed = discord.Embed(title="", description=f"I am already in {channel.name}", color=discord.Color.blurple())
            return await ctx.send(embed=embed)
            
        await ctx.voice_client.move_to(voice_channel)
        embed = discord.Embed(title="", description=f"Moved to {channel.name}", color=discord.Color.blurple())
        return await ctx.send(embed=embed)

    @commands.command(name='leave', aliases=["dc", "disconnect", "bye"], description="Leaves the channel")
    async def leave(self, ctx):
        # Make sure user is conn to voice channel
        voice = ctx.message.author.voice
        if not voice:
            embed = discord.Embed(title="", description="You're not connected to a voice channel", color=discord.Color.red())
            return await ctx.send(embed=embed)
        if not self.vc or not self.vc.is_connected():
            embed = discord.Embed(title="", description="I'm not connected to a voice channel", color=discord.Color.red())
            return await ctx.send(embed=embed)
        if ctx.guild.voice_client.channel != ctx.message.author.voice.channel:
            embed = discord.Embed(title="", description="You're not connected to the same voice channel as me", color=discord.Color.red())
            return await ctx.send(embed=embed)
        if not self.vc.queue.is_empty:
            self.vc.queue.clear()

        await ctx.message.add_reaction('👋')
        server = ctx.message.guild.voice_client
        await server.disconnect()
            
    @commands.command(name='play', aliases=['sing','p'], description="Plays a track from YouTube")
    async def play(self, ctx, *title : str):
        try:
            # Join channel if not connected
            if not self.vc or not self.vc.is_connected():
                await ctx.invoke(self.bot.get_command('join'))

            if ctx.guild.voice_client.channel != ctx.message.author.voice.channel:
                embed = discord.Embed(title="", description="You're not connected to the same voice channel as me", color=discord.Color.red())
                return await ctx.send(embed=embed)

            user_input = " ".join(title)

            # TODO: Add in playlist logic
            if "/playlist" in user_input:
                logging.info("Playlist identified")
                self.playlist = await wavelink.YouTubePlaylist.search(query=user_input)
                print(self.playlist.tracks)
                return

            # Add track to the queue, regardless of the bot playing
            chosen_track = await wavelink.YouTubeTrack.search(query=user_input, return_first=True)
            #print(f"Info for the track \n{chosen_track.info}\n")
            #print(f"Id for the track {chosen_track.id}\n")
            if chosen_track:
                self.current_track = chosen_track
                if self.vc.is_playing() or not self.vc.queue.is_empty:
                    embed = discord.Embed(title="", description=f"Queued [{self.current_track.title}]({self.current_track.info['uri']}) [{ctx.author.mention}]", color=discord.Color.green())
                    await ctx.send(embed=embed)
                self.vc.queue.put(self.current_track)

            # If bot isn't playing a song, play current song
            if not self.vc.is_playing():
                self.current_track = self.vc.queue.get()
                embed = discord.Embed(title="", description=f"Now playing [{self.current_track.title}]({self.current_track.info['uri']}) [{self.current_track.author}]", color=discord.Color.green())
                await ctx.send(embed=embed)
                await self.vc.play(self.current_track)
        except Exception as e:
            logging.error(f"Exception: {e}")
            embed = discord.Embed(title=f"Error playing \n{user_input}", description="Something went wrong with the track you sent, please try again.", color=discord.Color.red())
            embed.set_footer(text=f"If this persists ping Alex")
            return await ctx.send(embed=embed)
            

    @commands.command(name='queue', aliases=['q', 'playlist', 'que'], description="Shows the queue")
    async def queue(self, ctx):
        await ctx.typing()

        voice = ctx.message.author.voice
        if not voice:
            embed = discord.Embed(title="", description="You're not connected to a voice channel", color=discord.Color.red())
            return await ctx.send(embed=embed)
        if not self.vc or not self.vc.is_connected():
            embed = discord.Embed(title="", description="I'm not connected to a voice channel", color=discord.Color.red())
            return await ctx.send(embed=embed)
        if ctx.guild.voice_client.channel != ctx.message.author.voice.channel:
            embed = discord.Embed(title="", description="You're not connected to the same voice channel as me", color=discord.Color.red())
            return await ctx.send(embed=embed)
        if self.vc.queue.is_empty:
            embed = discord.Embed(title="", description="The queue is empty", color=discord.Color.red())
            return await ctx.send(embed=embed)

        song_lst = list()
        temp_queue = self.vc.queue.copy()
        
        for _ in range(temp_queue.count):
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
            # song_formated = str(song.title) + ' - ' + duration
            song_formated = f"[{str(song.title)}]({song.info['uri']}) - {duration}"
            song_lst.append(song_formated)
        
        embed = discord.Embed(title="Items In Queue", color=discord.Color.blurple())
        song_lst = '\n'.join(song_lst)  # Joining the list with newline as the delimiter
        embed.add_field(name="Songs:", value=song_lst)
        return await ctx.send(embed=embed)

    @commands.command(name="now_playing", aliases=["np"], description="Shows what's currently playing")
    async def now_playing(self, ctx):
        await ctx.typing()

        voice = ctx.message.author.voice
        if not voice:
            embed = discord.Embed(title="", description="You're not connected to a voice channel", color=discord.Color.red())
            return await ctx.send(embed=embed)
        if not self.vc or not self.vc.is_connected():
            embed = discord.Embed(title="", description="I'm not connected to a voice channel", color=discord.Color.red())
            return await ctx.send(embed=embed)
        if not self.vc.is_playing():
            embed = discord.Embed(title="", description="I'm not playing anything", color=discord.Color.red())
            return await ctx.send(embed=embed)

        seconds = int(self.vc.track.length) % (24 * 3600) 
        hour = seconds // 3600
        seconds %= 3600
        minutes = seconds // 60
        seconds %= 60
        if hour > 0:
            duration = "%dh %02dm %02ds" % (hour, minutes, seconds)
        else:
            duration = "%02dm %02ds" % (minutes, seconds)
        
        embed = discord.Embed(title="Now playing", color=discord.Color.blurple())
        # [{self.current_track.title}]({self.current_track.info['uri']}
        embed.add_field(name="Current track:", value=f"[{str(self.vc.track.title)}]({self.vc.track.info['uri']}) - {duration}")
        return await ctx.send(embed=embed)

    @commands.command(name='skip', aliases=['s', 'next'], description="Skips the current song")
    async def skip(self, ctx):
        voice = ctx.message.author.voice
        if not voice:
            embed = discord.Embed(title="", description="You're not connected to a voice channel", color=discord.Color.red())
            return await ctx.send(embed=embed)
        if not self.vc or not self.vc.is_connected():
            embed = discord.Embed(title="", description="I'm not connected to a voice channel", color=discord.Color.red())
            return await ctx.send(embed=embed)
        if ctx.guild.voice_client.channel != ctx.message.author.voice.channel:
            embed = discord.Embed(title="", description="You're not connected to the same voice channel as me", color=discord.Color.red())
            return await ctx.send(embed=embed)

        if self.vc.queue.is_empty:
            # If the queue is empty, we can stop the bot
            await ctx.message.add_reaction('👍')
            return await self.vc.stop()

        self.current_track = self.vc.queue.get()
        await self.vc.play(self.current_track)

        await ctx.message.add_reaction('👍')

    @commands.command(description="Resumes current paused song")
    async def resume(self, ctx):
        voice = ctx.message.author.voice
        if not voice:
            embed = discord.Embed(title="", description="You're not connected to a voice channel", color=discord.Color.red())
            return await ctx.send(embed=embed)
        if not self.vc or not self.vc.is_connected():
            embed = discord.Embed(title="", description="I'm not connected to a voice channel", color=discord.Color.red())
            return await ctx.send(embed=embed)
        if ctx.guild.voice_client.channel != ctx.message.author.voice.channel:
            embed = discord.Embed(title="", description="You're not connected to the same voice channel as me", color=discord.Color.red())
            return await ctx.send(embed=embed)
            
        await self.vc.resume()
        return await ctx.send(f"Resuming current track")
    
    @commands.command(description="Pause playing song")
    async def pause(self, ctx):
        voice = ctx.message.author.voice
        if not voice:
            embed = discord.Embed(title="", description="You're not connected to a voice channel", color=discord.Color.red())
            return await ctx.send(embed=embed)
        if not self.vc or not self.vc.is_connected():
            embed = discord.Embed(title="", description="I'm not connected to a voice channel", color=discord.Color.red())
            return await ctx.send(embed=embed)
        if ctx.guild.voice_client.channel != ctx.message.author.voice.channel:
            embed = discord.Embed(title="", description="You're not connected to the same voice channel as me", color=discord.Color.red())
            return await ctx.send(embed=embed)
            
        await self.vc.pause()
        return await ctx.send(f"Paused current track")

    @commands.command(name='clear', aliases=['clr', 'cl', 'cr'], description="Clears entire queue")
    async def clear(self, ctx):
        await ctx.typing()

        voice = ctx.message.author.voice
        if not voice:
            embed = discord.Embed(title="", description="You're not connected to a voice channel", color=discord.Color.red())
            return await ctx.send(embed=embed)
        if not self.vc or not self.vc.is_connected():
            embed = discord.Embed(title="", description="I'm not connected to a voice channel", color=discord.Color.red())
            return await ctx.send(embed=embed)
        if ctx.guild.voice_client.channel != ctx.message.author.voice.channel:
            embed = discord.Embed(title="", description="You're not connected to the same voice channel as me", color=discord.Color.red())
            return await ctx.send(embed=embed)

        self.vc.queue.clear()
        embed = discord.Embed(title="", description="Queue is cleared", color=discord.Color.green())
        return await ctx.send(embed=embed)
        
    @commands.command(description="Stops the bot and resets the queue")
    async def stop(self, ctx):
        voice = ctx.message.author.voice.channel
        if not voice:
            embed = discord.Embed(title="", description="You're not connected to a voice channel", color=discord.Color.red())
            return await ctx.send(embed=embed)
        if not self.vc or not self.vc.is_connected():
            embed = discord.Embed(title="", description="I'm not connected to a voice channel", color=discord.Color.red())
            return await ctx.send(embed=embed)
        if ctx.guild.voice_client.channel != ctx.message.author.voice.channel:
            embed = discord.Embed(title="", description="You're not connected to the same voice channel as me", color=discord.Color.red())
            return await ctx.send(embed=embed)
        if not self.vc.is_playing():
            embed = discord.Embed(title="", description="I'm not playing anything", color=discord.Color.red())
            return await ctx.send(embed=embed)

        if not self.vc.queue.is_empty:
            self.vc.queue.clear()
        await self.vc.stop()
        await ctx.message.add_reaction('🛑')
        
    @commands.command(description="Sets the output volume")
    async def volume(self, ctx, new_volume : int = 100):
        voice = ctx.message.author.voice
        if not voice:
            embed = discord.Embed(title="", description="You're not connected to a voice channel", color=discord.Color.red())
            return await ctx.send(embed=embed)
        await self.vc.set_volume(new_volume)

    @commands.command(description="Displays system info", aliases=["spec"])
    async def info(self, ctx):
        py_ver = subprocess.check_output('python3 --version', shell=True).decode('utf-8').strip()
        sys_info = subprocess.check_output('lsb_release -d', shell=True).decode('utf-8').split('\t')[1].strip()

        embed = discord.Embed(title="Currently running:", color=discord.Color.blurple())
        info_lst = '\n'.join([py_ver, sys_info])  # Joining the list with newline as the delimiter
        embed.add_field(name="System info", value=info_lst)
        return await ctx.send(embed=embed)

async def setup(bot):
    music_bot = MusicBot(bot)
    await bot.add_cog(music_bot)
    await music_bot.setup()