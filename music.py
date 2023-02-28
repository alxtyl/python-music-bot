import os
import re
import discord
import asyncio
import logging
import wavelink
import subprocess
from random import randint
from wavelink.ext import spotify
from discord.ext import commands

logging.getLogger().setLevel(logging.INFO)

AFK_TIMEOUT = 1200   # Amount of seconds before the bot disconnects due to nothing being played
QUEUE_TIMEOUT = 180  # Time before users aren't able to interact with the queue pages

URL_REG = re.compile("^(https?|ftp):\/\/[^\s\/$.?#].[^\s]*$")                                            # Regex for checking if a string is a url
SPOT_REG = re.compile("^(?:https?:\/\/)?(?:www\.)?(?:open|play)\.spotify\.com\/.*$")                     # Regex for checking if a string is a url from Spotify
YT_PLAYLIST_REG = re.compile("(?:https?:\/\/)?(?:www\.)?youtube\.com\/playlist\?list=([a-zA-Z0-9_-]+)")  # Regex for matching a youtube playlist


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
            password=os.environ['SERVER_PASS'],
            spotify_client=spotify.SpotifyClient(client_id=os.environ['SPOTIFY_ID'], 
                                                    client_secret=os.environ['SPOTIFY_SECRET'])
        )

    async def timeout(self):
        await asyncio.sleep(AFK_TIMEOUT)
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
        if not player.queue.is_empty and not player.is_playing():
            self.current_track = player.queue.get()
            embed = discord.Embed(title="", description=f"Now playing [{self.current_track.title}]({self.current_track.info['uri']})", color=discord.Color.green())
            await self.music_channel.send(embed=embed, delete_after=self.current_track.length)
            await player.play(self.current_track)
        if player.is_playing() or not player.is_connected():
            return
        self.timer = asyncio.create_task(self.timeout())
            
    @commands.command(name='join', aliases=['connect', 'j'], description="Joins the bot into the voice channel")
    async def join(self, ctx):
        await ctx.typing()

        voice = ctx.message.author.voice
        if not voice or ctx.author.voice.channel is None or ctx.author.voice is None:
            embed = discord.Embed(title="", description="You're not connected to a voice channel", color=discord.Color.red())
            await ctx.send(embed=embed)
            return False

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
                resp = await ctx.invoke(self.bot.get_command('join'))
                if resp == False:
                    return

            if ctx.guild.voice_client.channel != ctx.message.author.voice.channel:
                embed = discord.Embed(title="", description="You're not connected to the same voice channel as me", color=discord.Color.red())
                return await ctx.send(embed=embed)

            user_input = " ".join(title)

            if URL_REG.match(user_input):
                if YT_PLAYLIST_REG.match(user_input):
                    self.playlist = await wavelink.YouTubePlaylist.search(query=user_input)
                    for track in self.playlist.tracks:
                        self.vc.queue.put(track)
                    embed = discord.Embed(title="", description=f"Added {len(self.playlist.tracks)} tracks to the queue [{ctx.author.mention}]", color=discord.Color.green())
                    await ctx.send(embed=embed)
                elif SPOT_REG.match(user_input):
                    decoded = spotify.decode_url(user_input)
                    if decoded and decoded['type'] is spotify.SpotifySearchType.track:
                        track = await spotify.SpotifyTrack.search(query=decoded["id"], type=decoded["type"], return_first=True)
                        self.vc.queue.put(track)
                    elif decoded and decoded['type'] is spotify.SpotifySearchType.album:
                        embed = discord.Embed(title="", description="Searching, this may take a bit", color=discord.Color.blurple())
                        await ctx.send(embed=embed, delete_after=60)
                        counter = 0
                        async for track in spotify.SpotifyTrack.iterator(query=user_input, type=decoded['type']):
                            self.vc.queue.put(track)
                            counter += 1
                        embed = discord.Embed(title="", description=f"Added {counter} tracks to the queue [{ctx.author.mention}]", color=discord.Color.green())
                        await ctx.send(embed=embed)
                    elif decoded and decoded['type'] is spotify.SpotifySearchType.playlist:
                        embed = discord.Embed(title="", description="Searching, this may take a bit", color=discord.Color.blurple())
                        await ctx.send(embed=embed, delete_after=60)
                        counter = 0
                        async for track in spotify.SpotifyTrack.iterator(query=user_input, type=decoded['type']):
                            self.vc.queue.put(track)
                            counter += 1
                        embed = discord.Embed(title="", description=f"Added {counter} tracks to the queue [{ctx.author.mention}]", color=discord.Color.green())
                        await ctx.send(embed=embed)
                else:
                    chosen_track = await wavelink.YouTubeTrack.search(query=user_input, return_first=True)
                    if chosen_track:
                        self.current_track = chosen_track
                        if self.vc.is_playing() or not self.vc.queue.is_empty:
                            embed = discord.Embed(title="", description=f"Queued [{self.current_track.title}]({self.current_track.info['uri']}) [{ctx.author.mention}]", color=discord.Color.green())
                            await ctx.send(embed=embed)
                        self.vc.queue.put(self.current_track)

            if not self.vc.is_playing():
                self.current_track = self.vc.queue.get()
                embed = discord.Embed(title="", description=f"Now playing [{self.current_track.title}]({self.current_track.info['uri']})", color=discord.Color.green())
                await ctx.send(embed=embed, delete_after=self.current_track.length)
                await self.vc.play(self.current_track)

        except Exception as e:
            logging.error(f"Exception: {e}")
            embed = discord.Embed(title=f"Error", description="Something went wrong with the track you sent, please try again.", color=discord.Color.red())
            embed.set_footer(text="If this persists ping Alex")
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
            embed = discord.Embed(title="", description="The queue is empty", color=discord.Color.blue())
            return await ctx.send(embed=embed)

        pages = list()
        song_lst = list()
        song_count = 0
        temp_queue = self.vc.queue.copy()
        queue_cnt = self.vc.queue.count
        num_pages = int((queue_cnt // 10) + 1)
        
        # Build the queue w/ times & indext
        for i in range(queue_cnt):
            song_count += 1
            song_num = i + 1

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
            song_formated = f"{song_num}. {song.title} - {duration}"
            song_lst.append(song_formated)

            if song_count % 10 == 0 or song_num == queue_cnt:
                embed = discord.Embed(title=f"Items In Queue: {queue_cnt}", color=discord.Color.blurple())
                embed.add_field(name=f"Tracks:", value='\n'.join(song_lst))
                pages.append(embed)
                
                song_count = 0
                song_lst.clear()

        cur_page = 1

        if num_pages == 1:
            message = await ctx.send(
            content="",
            embed=pages[cur_page - 1]
            )
            return

        # Create the page(s) for users to scroll through
        message = await ctx.send(
            content=f"Page {cur_page}/{num_pages}\n",
            embed=pages[cur_page - 1]
        )

        await message.add_reaction("◀️")
        await message.add_reaction("▶️")

        while True:
            try:
                reaction, user = await self.bot.wait_for("reaction_add", timeout=QUEUE_TIMEOUT)

                if str(reaction.emoji) == "▶️" and cur_page != num_pages:
                    cur_page += 1
                    await message.edit(
                        content=f"Page {cur_page}/{num_pages}",
                        embed=pages[cur_page - 1]
                    )
                    await message.remove_reaction(reaction, user)
                elif str(reaction.emoji) == "◀️" and cur_page > 1:
                    cur_page -= 1
                    await message.edit(
                        content=f"Page {cur_page}/{num_pages}",
                        embed=pages[cur_page - 1])
                    await message.remove_reaction(reaction, user)
                else:
                    await message.remove_reaction(reaction, user)
            except asyncio.TimeoutError:
                await message.delete()
                break

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
        embed.add_field(name="Current track:", value=f"[{str(self.vc.track.title)}]({self.vc.track.info['uri']}) - {duration}")
        return await ctx.send(embed=embed, delete_after=self.vc.track.length)

    @commands.command(name="shuffle", aliases=["shuf"], description="Shuffles the queue")
    async def shuffle(self, ctx):
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

        arr = list()
        num_items = self.vc.queue.count

        # TODO: Optimize
        # Populate list
        for _ in range(num_items):
            arr.append(self.vc.queue.pop())
            
        # Perform Fisher-Yates shuffle
        for i in range(num_items-1,0,-1):
            j = randint(0,i+1)

            arr[i],arr[j] = arr[j],arr[i]

        # Put shuffled list back into the queue
        for track in arr:
            self.vc.queue.put(track)

        await ctx.message.add_reaction('👍')

    @commands.command(name='remove', aliases=['rm'], description="Removes a song from the queue")
    async def remove(self, ctx, *input : str):
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
        
        input = " ".join(input)
        rm_track_num = int(input)

        if not input.isdigit() or rm_track_num > self.vc.queue.count or rm_track_num == 0:
            embed = discord.Embed(title="", description="Please send a valid track to remove", color=discord.Color.red())
            return await ctx.send(embed=embed)

        embed = discord.Embed(title="", description="This command is currently under construction *drill noises* 🚧", color=discord.Color.yellow())
        return await ctx.send(embed=embed, delete_after=120)

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
        embed = discord.Embed(title="", description=f"Now playing [{self.current_track.title}]({self.current_track.info['uri']})", color=discord.Color.green())
        await self.music_channel.send(embed=embed)
        return await self.vc.play(self.current_track)

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