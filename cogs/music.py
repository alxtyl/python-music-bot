import os
import copy
import discord
import asyncio
import logging
import wavelink
import urllib.request
from discord.ext import commands

from global_vars.regex import *
from global_vars.timeout import *
from utils.queue_util import update_queue_file
from utils.number_util import is_float

#logging.getLogger().setLevel(logging.INFO)

class VoiceConnectionError(commands.CommandError):
    """Custom Exception class for connection errors."""

class InvalidVoiceChannel(VoiceConnectionError):
    """Exception for cases of invalid Voice Channels."""

class MusicBot(commands.Cog):
    timer = None
    current_track = None
    music_channel = None
    node = None
    filter_status = True
    vc : wavelink.Player = None
    now_playing_lst = list()
    
    def __init__(self, bot):
        self.bot = bot
        
    async def setup(self):
        """
        Sets up a connection to lavalink
        """     
        node: wavelink.Node = wavelink.Node(uri=os.environ['LAVAINK_SERVER'], password=os.environ['LAVALINK_SERVER_PASSWORD'])
        await wavelink.Pool.connect(client=self.bot, nodes=[node], cache_capacity=100)


    def _is_connected(self, ctx):
        voice_client = discord.utils.get(ctx.bot.voice_clients, guild=ctx.guild)
        return voice_client and voice_client.connected


    def parse_time(self, time: float) -> str:
        seconds = int(time / 1000) % (24 * 3600)  # Convert from milliseconds -> seconds
        hour = seconds // 3600
        seconds %= 3600
        minutes = seconds // 60
        seconds %= 60

        if hour > 0:
           return "%dh %02dm %02ds" % (hour, minutes, seconds)
        else:
            return "%02dm %02ds" % (minutes, seconds)
        

    async def clear_messages(self) -> None:
        """
        Clears all associated 'now playing' messages associated with a track
        """
        last_msg = None

        try:
            for msg in self.now_playing_lst:
                if msg == self.now_playing_lst[-1] and self.vc.playing:
                    last_msg = msg
                    break
                await msg.delete()
        except discord.errors.NotFound:
            pass

        self.now_playing_lst = [last_msg] if last_msg else []


    async def timeout(self) -> None:
        await asyncio.sleep(AFK_TIMEOUT)
        if self.vc.connected and not self.vc.is_playing():
            embed = discord.Embed(title="", description=f"Disconnecting due to inactivity", color=discord.Color.blue())
            await self.music_channel.send(embed=embed)
            return await self.vc.disconnect()
        

    async def validate_command(self, ctx) -> bool:
        """
        Checks to make sure user is performing
        a valid action before executing command
        """
        voice = ctx.message.author.voice
        if not voice:
            embed = discord.Embed(title="", description="You're not connected to a voice channel", color=discord.Color.red())
            await ctx.send(embed=embed, delete_after=60)
            return False
        if not self.vc or not self.vc.connected:
            embed = discord.Embed(title="", description="I'm not connected to a voice channel", color=discord.Color.red())
            await ctx.send(embed=embed, delete_after=60)
            return False
        if ctx.guild.voice_client.channel != ctx.message.author.voice.channel:
            embed = discord.Embed(title="", description="You're not connected to the same voice channel as me", color=discord.Color.red())
            await ctx.send(embed=embed, delete_after=60)
            return False
        
        return True
    

    async def get_spotify_redirect(self, url: str) -> str:
        """
        Takes a Spotify url of the form http://spotify.link/0123456
        follows the redirect, and returns a Spotify url of the form
        https://open.spotify.com/MEDIA_TYPE/r
        """
        return urllib.request.urlopen(url).geturl().split('&')[0]
    

    async def filter_not_active_msg(self, ctx):
        embed = discord.Embed(title="", description="Filter commands are currently not enabled", color=discord.Color.dark_grey())
        return await ctx.send(embed=embed, delete_after=30)


    async def queue_msg(self, ctx):
        if (type(self.current_track) == wavelink.ext.spotify.SpotifyTrack) and (track_url := self.current_track.raw['external_urls']['spotify']):
            embed = discord.Embed(title="", description=f"Queued [{self.current_track.title}]({(track_url)}) [{ctx.author.mention}]", color=discord.Color.green())              
            return await ctx.send(embed=embed, delete_after=120)  # Delete after 2 minutes
        else:
            embed = discord.Embed(title="", description=f"Queued [{self.current_track.title}]({(self.current_track.uri)}) [{ctx.author.mention}]", color=discord.Color.green())              
            return await ctx.send(embed=embed, delete_after=120)  # Delete after 2 minute
        
    
    async def on_wavelink_node_ready(self, node: wavelink.Node):
        logging.info(f"{node} is ready")

    
    # embed.add_field(name="Time Elapsed", value=f"{self.parse_time(self.vc.position)}", inline=False)

    @commands.Cog.listener()
    async def on_wavelink_track_start(self, payload: wavelink.TrackStartEventPayload) -> None:
        player = payload.player

        if not player:
            return

        if self.now_playing_lst is not None and 0 < len(self.now_playing_lst):
            await self.clear_messages()
        
        original = payload.original
        track = payload.track

        embed = discord.Embed(title="Now Playing", description=f"[{track.title}]({track.uri}) - {self.parse_time(self.current_track.length)} ", color=discord.Color.green())

        if track.artwork:
            embed.set_image(url=track.artwork)

        if original and original.recommended:
            embed.description += f"\n\n`This track was recommended via {track.source}`"

        self.now_playing_lst.append(await self.music_channel.send(embed=embed, delete_after=(self.vc.current.length / 1000)))
            

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
            await self.vc.set_volume(100)  # Set volume to 100%
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
        if not await self.validate_command(ctx):
            return

        if not self.vc.queue:
            self.vc.queue.clear()

        await ctx.message.add_reaction('👋')
        server = ctx.message.guild.voice_client
        await server.disconnect()


    @commands.command(name='play', aliases=['sing','p'], description="Plays a given input if it's valid")
    async def play(self, ctx, *, user_input = None):
        try:
            if not user_input:
                embed = discord.Embed(title="", description="Please enter something to play", color=discord.Color.red())
                return await ctx.send(embed=embed)

            if not self._is_connected(ctx):
                if await ctx.invoke(self.bot.get_command('join')) == False:
                    return

            if ctx.guild.voice_client.channel != ctx.message.author.voice.channel:
                embed = discord.Embed(title="", description="You're not connected to the same voice channel as me", color=discord.Color.red())
                return await ctx.send(embed=embed)
            
            if SPOT_REG_V2.match(user_input):
                user_input = await self.get_spotify_redirect(user_input)

            tracks : wavelink.Search = await wavelink.Playable.search(user_input)  # tracks: wavelink.Search
        
            if not tracks:
                RuntimeError("Search did not return any results")

            if isinstance(tracks, wavelink.Playlist):
                tracks_added : int = await self.vc.queue.put_wait(tracks)
                embed = discord.Embed(title="", description=f"Added {tracks_added} tracks to the queue [{ctx.author.mention}]", color=discord.Color.green())
                await ctx.send(embed=embed, delete_after=120)
            else:
                track : wavelink.Playable = tracks[0]
                if self.vc.playing:
                    embed = discord.Embed(title="", description=f"Queued [{track.title}]({(track.uri)}) [{ctx.author.mention}]", color=discord.Color.green())              
                    await ctx.send(embed=embed, delete_after=120)  # Delete after 2 minutes
                await self.vc.queue.put_wait(track)

            if not self.vc.playing:
                self.current_track = self.vc.queue.get()
                await self.vc.play(self.current_track)

        except Exception as e:
            logging.error(e, exc_info=True)
            embed = discord.Embed(title=f"Error", description=f"""Something went wrong with the track you sent, please try again.\nStack trace: {e}""", color=discord.Color.red())
            return await ctx.send(embed=embed)


    @commands.command(name='queue', aliases=['q', 'playlist', 'que'], description="Shows the queue")
    async def queue(self, ctx):
        await ctx.typing()

        if not await self.validate_command(ctx):
            return
        
        if not self.vc.queue:
            embed = discord.Embed(title="", description="The queue is empty", color=discord.Color.blue())
            return await ctx.send(embed=embed)

        pages = list()
        song_lst = list()
        song_count = 0
        
        queue_cnt = len(self.vc.queue)
        temp_queue = copy.deepcopy(self.vc.queue)
        num_pages = int((queue_cnt // 10) + 1) if queue_cnt % 10 != 0 else int(queue_cnt // 10)
        
        # Build the queue w/ times & index
        for i in range(queue_cnt):
            song_count += 1
            song_num = i + 1

            song = temp_queue.get()
            duration = self.parse_time(song.length)

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
            embed=pages[cur_page - 1],
            delete_after=QUEUE_TIMEOUT
            )
            return

        # Create the page(s) for user(s) to scroll through
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

        if not await self.validate_command(ctx):
            return
        
        if not self.vc.playing:
            embed = discord.Embed(title="", description="I'm not playing anything", color=discord.Color.red())
            return await ctx.send(embed=embed)

        return await self.now_playing_dur_msg(ctx, self.parse_time(self.current_track.length))


    @commands.command(name="shuffle", aliases=["shuf"], description="Shuffles the queue")
    async def shuffle(self, ctx):
        if not await self.validate_command(ctx):
            return
        
        if not self.vc.queue:
            embed = discord.Embed(title="", description="The queue is empty", color=discord.Color.red())
            return await ctx.send(embed=embed)

        self.vc.queue.shuffle()

        await ctx.message.add_reaction('👍')


    @commands.command(name='remove', aliases=['rm'], description="Removes a song from the queue")
    async def remove(self, ctx, *user_input : str):
        if not await self.validate_command(ctx) or not user_input:
            return
        
        if not self.vc.queue:
            embed = discord.Embed(title="", description="The queue is empty", color=discord.Color.red())
            return await ctx.send(embed=embed)

        user_input = " ".join(user_input)
        rm_track_num = int(user_input) - 1  # Change input to align with zero-based index

        if not user_input.isdigit() or len(self.vc.queue) < rm_track_num or rm_track_num <= -1:
            embed = discord.Embed(title="", description="Please send a valid track to remove", color=discord.Color.red())
            return await ctx.send(embed=embed)
        
        del self.vc.queue[rm_track_num]
        return await ctx.message.add_reaction('👍')


    @commands.command(name='skip', aliases=['s', 'next'], description="Skips the current song")
    async def skip(self, ctx):
        if not await self.validate_command(ctx):
            return
        
        if not self.vc.playing:
            embed = discord.Embed(title="", description="I'm not playing anything", color=discord.Color.red())
            return await ctx.send(embed=embed)

        if not self.vc.queue:
            # If the queue is empty, we can stop the bot
            await self.vc.stop()
            return await ctx.message.add_reaction('👍')

        self.current_track = self.vc.queue.get()
        await self.vc.play(self.current_track)
        return await ctx.message.add_reaction('👍')


    @commands.command(description="Resume current paused song", aliases=['unpause'])
    async def resume(self, ctx):
        if not await self.validate_command(ctx):
            return

        if not self.vc.is_paused():
            embed = discord.Embed(title="", description="I'm not paused", color=discord.Color.red())
            return await ctx.send(embed=embed)
            
        await self.vc.resume()
        return await ctx.message.add_reaction('👍')
    
    # Todo: Needs to be updated
    @commands.command(description="Pause playing song")
    async def pause(self, ctx):
        if not await self.validate_command(ctx):
            return

        if not self.vc.is_playing():
            embed = discord.Embed(title="", description="I'm not playing anything", color=discord.Color.red())
            return await ctx.send(embed=embed)
            
        await self.vc.pause()
        return await ctx.message.add_reaction('👍')


    @commands.command(name='clear', aliases=['clr', 'cl', 'cr'], description="Clears entire queue")
    async def clear(self, ctx):
        await ctx.typing()

        if not await self.validate_command(ctx):
            return
        
        if not self.vc.queue:
            embed = discord.Embed(title="", description="Queue is empty", color=discord.Color.blue())
            return await ctx.send(embed=embed)

        self.vc.queue.clear()
        embed = discord.Embed(title="", description="Queue is cleared", color=discord.Color.green())
        return await ctx.send(embed=embed)
        

    @commands.command(description="Stops the bot and resets the queue")
    async def stop(self, ctx):
        if not await self.validate_command(ctx):
            return
        
        if not self.vc.playing:
            embed = discord.Embed(title="", description="I'm not playing anything", color=discord.Color.red())
            return await ctx.send(embed=embed)
        
        if self.vc.queue:
            self.vc.queue.clear()

        await self.vc.stop()
        await ctx.message.add_reaction('🛑')
        
        if self.now_playing_lst is not None and 0 < len(self.now_playing_lst):
            await self.clear_messages()


    @commands.command(description="Sets the output volume")
    async def volume(self, ctx, new_volume):
        if not await self.validate_command(ctx) or not self.vc.playing or not new_volume.isdigit():
            return
        
        await self.vc.set_volume(int(new_volume))

        await ctx.message.add_reaction('👍')


    @commands.is_owner()
    @commands.command(description='Enables or disables filters on the bot')
    async def toggle_filter(self, ctx):
        if self.filter_status:
            await self.vc.set_filter(wavelink.Filter(equalizer=wavelink.Equalizer.flat()), seek=True)
            self.filter_status = False
        else:
            self.filter_status = True

        embed = discord.Embed(title="", description="Filter status has been toggled", color=discord.Color.green())              
        return await ctx.send(embed=embed, delete_after=60)


    @commands.command(description="Resets filter on the bot", aliases=['rs_filter', 'rsf'])
    async def reset_filter(self, ctx):
        if not await self.validate_command(ctx) or not self.vc.playing:
            return
        
        if not self.filter_status:
            return await self.filter_not_active_msg(ctx)

        await self.vc.set_filter(wavelink.Filter(equalizer=wavelink.Equalizer.flat()), seek=True)

        await ctx.message.add_reaction('👍')


    @commands.command(description="Changes the timescale of the song")
    async def timescale(self, ctx, speed: str = commands.parameter(default='1', description="Multiplier for the track playback speed"), 
                        pitch: str = commands.parameter(default='1', description="Multiplier for the track pitch"), 
                        rate: str = commands.parameter(default='1', description="Multiplier for the track rate (pitch + speed)")):
        
        if not await self.validate_command(ctx) or not self.vc.playing:
            return

        if not self.filter_status:
            return await self.filter_not_active_msg(ctx)
        
        if not is_float(speed) or not is_float(pitch) or not is_float(rate):
            return
        
        timescale_filter = wavelink.Filter(timescale=wavelink.Timescale(speed=float(speed), pitch=float(pitch), rate=float(rate)))
            
        await self.vc.set_filter(timescale_filter, seek=True)

        await ctx.message.add_reaction('👍')


async def setup(bot):
    music_bot = MusicBot(bot)
    await bot.add_cog(music_bot)
    await music_bot.setup()