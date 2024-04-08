import os
import copy
import random
import discord
import asyncio
import logging
import wavelink
import urllib.request
from typing import cast

from utils.connect import *
from utils.validate import *
from discord import app_commands
from discord.ext import commands
from global_vars.timeout import *
from global_vars.regex import SPOT_REG_V2
from utils.time_parse_util import time_format

logging.getLogger().setLevel(logging.INFO)

class VoiceConnectionError(commands.CommandError):
    """Custom Exception class for connection errors."""

class InvalidVoiceChannel(VoiceConnectionError):
    """Exception for cases of invalid Voice Channels."""

class MusicBot(commands.Cog):
    #group = app_commands.Group(name="music", description="Music commands")
    current_track = None
    music_channel = None
    node = None
    filter_status : bool = True
    queue_message_active : bool = False
    queue_message = None
    vc : wavelink.Player = None
    now_playing_lst = list()
    

    def __init__(self, bot):
        self.bot = bot


    async def setup(self):
        """
        Sets up a connection to lavalink
        """
        node: wavelink.Node = wavelink.Node(uri=os.environ['LAVAINK_SERVER'], password=os.environ['LAVALINK_SERVER_PASSWORD'])
        await wavelink.Pool.connect(client=self.bot, nodes=[node], cache_capacity=250)


    async def get_spotify_redirect(self, url: str) -> str:
        """
        Takes a Spotify url of the form http://spotify.link/0123456
        follows the redirect, and returns a Spotify url of the form
        https://open.spotify.com/MEDIA_TYPE/r
        """
        return urllib.request.urlopen(url).geturl().split('&')[0]


    async def clear_messages(self) -> None:
        """
        Clears all associated 'now playing' messages
        """
        if 0 < len(self.now_playing_lst):
            for msg in self.now_playing_lst:
                try:
                    await msg.delete()
                except discord.errors.NotFound:
                    pass

            self.now_playing_lst = []
        

    async def shutdown_sequence(self) -> None:
        """Cleans up messages before leaving the voice channel"""
        await self.clear_messages()

        if self.queue_message_active and self.queue_message:
            try:
                await self.queue_message.delete()
            except discord.errors.NotFound:
                pass


    async def filter_not_active_msg(self, ctx):
        embed = discord.Embed(title="", description="Filter commands are currently not enabled", color=discord.Color.dark_grey())
        return await ctx.send(embed=embed, delete_after=30)


    @commands.Cog.listener()
    async def on_wavelink_node_ready(self, payload: wavelink.NodeReadyEventPayload) -> None:
        logging.info(f"Wavelink Node connected: {payload.node!r} | Resumed: {payload.resumed}")


    @commands.Cog.listener()
    async def on_wavelink_track_start(self, payload: wavelink.TrackStartEventPayload) -> None:
        player = payload.player

        if not player:
            return
        
        original = payload.original
        track = payload.track

        embed = discord.Embed(title="Now Playing", description=f"[{track.title}]({track.uri}) - {time_format(track.length)} ", color=discord.Color.green())

        if track.artwork:
            embed.set_thumbnail(url=track.artwork)

        if original and original.recommended:
            embed.description += f"\n\n`This track was recommended via {track.source}`"

        self.now_playing_lst.append(await self.music_channel.send(embed=embed, delete_after=(track.length / 1000)))


    @commands.Cog.listener()
    async def on_voice_state_update(self, before: discord.VoiceState):
        if is_bot_last_vc_member(self.bot, before.channel):
            player: wavelink.Player = before.channel.guild.voice_client
            if player is not None:
                await self.shutdown_sequence()
                await player.disconnect()

    
    @commands.Cog.listener()
    async def on_wavelink_inactive_player(self, player: wavelink.Player):
        if player is not None:
            await player.disconnect()
 

    @commands.is_owner()
    @commands.command(name='sync', description="Syncs commands")
    async def sync(self, ctx: commands.Context) -> None:
        """Sync commands"""
        synced = await ctx.bot.tree.sync()
        await ctx.send(f"Synced {len(synced)} commands globally")


    @app_commands.command(name="ping", description="Get the bot's latency")   
    async def ping(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(f"Pong! {round(self.bot.latency * 1000)}ms")


    @app_commands.command(name="join", description="Joins the bot into the voice channel")
    @app_commands.check(validate_join_command)
    async def join(self, interaction: discord.Interaction):
        user_channel = interaction.user.voice.channel
        bot_channel = get_voice_channel(interaction=interaction)
        self.music_channel = interaction.channel

        if user_channel is not None and bot_channel is None:
            self.vc = await user_channel.connect(cls=wavelink.Player, self_deaf=True)
            await self.vc.set_volume(100)  # Set volume to 100%
            self.vc.inactive_timeout = AFK_TIMEOUT
            embed = discord.Embed(title="", description=f"Joined {user_channel.name}", color=discord.Color.blurple())
            return await interaction.response.send_message(embed=embed, delete_after=120)
        elif user_channel == bot_channel:
            return await interaction.response.send_message(content=f"I am already in {user_channel.name}", ephemeral=True)
            
        await interaction.guild.voice_client.move_to(user_channel)
        embed = discord.Embed(title="", description=f"Moved to {user_channel.name}", color=discord.Color.blurple())
        return await interaction.response.send_message(embed=embed, delete_after=120)


    @app_commands.command(name='leave', description="Leaves the channel")
    @app_commands.check(validate_command_voice)
    async def leave(self, interaction: discord.Interaction):
        if not self.vc.queue:
            self.vc.queue.reset()

        await interaction.response.send_message(content="Left the channel", ephemeral=True)
        await self.shutdown_sequence()
        await self.vc.disconnect()


    @commands.command(name='play', aliases=['sing','p'], description="Plays a given input if it's valid")
    async def play(self, ctx, *, user_input=None, play_now=False):
        try:
            if not user_input:
                embed = discord.Embed(title="", description="Please enter something to play", color=discord.Color.red())
                return await ctx.send(embed=embed)

            if not is_connected(ctx):
                if await ctx.invoke(self.bot.get_command('join')) == False:
                    return

            if ctx.guild.voice_client.channel != ctx.message.author.voice.channel:
                embed = discord.Embed(title="", description="You're not connected to the same voice channel as me", color=discord.Color.red())
                return await ctx.send(embed=embed)
            
            if SPOT_REG_V2.match(user_input):
                user_input = await self.get_spotify_redirect(user_input)

            self.vc.autoplay = wavelink.AutoPlayMode.enabled
            tracks: wavelink.Search = await wavelink.Playable.search(user_input)
        
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

                await self.vc.queue.put_wait(track) if not play_now else self.vc.queue.put_at(0, track)

            if not self.vc.playing:
                self.current_track = self.vc.queue.get()
                await self.vc.play(self.current_track)

        except Exception as e:
            logging.error(e, exc_info=True)
            embed = discord.Embed(title=f"Error", description=f"""Something went wrong with the track you sent, please try again.\nStack trace: {e}""", color=discord.Color.red())
            return await ctx.send(embed=embed)
        

    @commands.command(name='play_now', aliases=['pn'], description="Inserts a track at the front of the queue")
    async def play_now(self, ctx, *, user_input = None):
        if not self.vc or not self.vc.queue or self.vc.queue.count < 2:
            return await ctx.invoke(self.bot.get_command('play'), user_input=user_input)
        else:
            return await ctx.invoke(self.bot.get_command('play'), user_input=user_input, play_now=True)


    @commands.command(name='queue', aliases=['q', 'playlist', 'que'], description="Shows the queue")
    async def queue(self, ctx):
        await ctx.typing()

        if not await self.validate_command(ctx):
            return
        
        if self.queue_message_active:
            try:
                await self.queue_message.delete()
            except discord.errors.NotFound:
                pass
        
        if not self.vc.queue:
            embed = discord.Embed(title="", description="The queue is empty", color=discord.Color.blue())
            return await ctx.send(embed=embed)

        pages = list()
        song_lst = list()
        song_count = 0
        total_time = 0
        
        queue_cnt = len(self.vc.queue)
        temp_queue = copy.deepcopy(self.vc.queue)
        num_pages = int((queue_cnt // 10) + 1) if queue_cnt % 10 != 0 else int(queue_cnt // 10)
        
        # Build the queue w/ times & index
        for i in range(queue_cnt):
            song_count += 1
            song_num = i + 1

            song = temp_queue.get()
            total_time += song.length
            duration = time_format(song.length)

            song_formated = f"{song_num}. {song.title} - {duration}"
            song_lst.append(song_formated)

            if song_count % 10 == 0 or song_num == queue_cnt:
                embed = discord.Embed(title=f"Items In Queue: {queue_cnt}", color=discord.Color.blurple())
                embed.add_field(name=f"Tracks:", value='\n'.join(song_lst))
                pages.append(embed)
                
                song_count = 0
                song_lst.clear()

        queue_time = time_format(total_time)
        for embed in pages:
            embed.description = f"Total time for queue: {queue_time}"

        cur_page = 1
        self.queue_message_active = True

        if num_pages == 1:
            message = await ctx.send(
            content="",
            embed=pages[cur_page - 1],
            delete_after=QUEUE_TIMEOUT)

            self.queue_message = message
            return

        # Create the page(s) for user(s) to scroll through
        message = await ctx.send(
            content=f"Page {cur_page}/{num_pages}\n",
            embed=pages[cur_page - 1],
        )

        self.queue_message = message

        await message.add_reaction("◀️")
        await message.add_reaction("▶️")

        while True:
            try:
                reaction, user = await self.bot.wait_for("reaction_add", timeout=QUEUE_TIMEOUT)

                if str(reaction.emoji) == "▶️":
                    if cur_page != num_pages:
                        cur_page += 1
                        await message.edit(
                            content=f"Page {cur_page}/{num_pages}",
                            embed=pages[cur_page - 1]
                        )
                        await message.remove_reaction(reaction, user)
                    else:
                        cur_page = 1
                        await message.edit(
                            content=f"Page {cur_page}/{num_pages}",
                            embed=pages[cur_page - 1]
                        )
                        await message.remove_reaction(reaction, user)
                elif str(reaction.emoji) == "◀️":
                    if 1 < cur_page:
                        cur_page -= 1
                        await message.edit(
                            content=f"Page {cur_page}/{num_pages}",
                            embed=pages[cur_page - 1])
                        await message.remove_reaction(reaction, user)
                    else:
                        cur_page = num_pages
                        await message.edit(
                            content=f"Page {cur_page}/{num_pages}",
                            embed=pages[cur_page - 1])
                        await message.remove_reaction(reaction, user)
            except asyncio.TimeoutError:
                await message.delete()
                self.queue_message_active = False
                self.queue_message = None
                break
            except discord.errors.NotFound:
                pass


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
        
        #self.vc.queue.delete(rm_track_num)

        del self.vc.queue[rm_track_num]

        return await ctx.message.add_reaction('👍')


    @commands.command(name='skip', aliases=['s', 'next'], description="Skips the current song")
    async def skip(self, ctx):
        if not await self.validate_command(ctx):
            return
        
        if not self.vc.playing:
            embed = discord.Embed(title="", description="I'm not playing anything", color=discord.Color.red())
            return await ctx.send(embed=embed)

        if self.now_playing_lst and 0 < len(self.now_playing_lst):
            await self.clear_messages()

        if not self.vc.queue:
            await self.vc.stop()  # If the queue is empty, we can stop the bot
            return await ctx.message.add_reaction('👍')

        self.current_track = self.vc.queue.get()
        await self.vc.play(self.current_track)
        return await ctx.message.add_reaction('👍')


    @commands.command(name="now_playing", aliases=["np"], description="Shows what's currently playing")
    async def now_playing(self, ctx):
        await ctx.typing()

        if not await self.validate_command(ctx):
            return
        
        if not self.vc.playing:
            embed = discord.Embed(title="", description="I'm not playing anything", color=discord.Color.red())
            return await ctx.send(embed=embed)
        
        track = self.vc.current

        embed = discord.Embed(title="Now Playing", description=f"[{track.title}]({track.uri}) - {time_format(track.length)} ", color=discord.Color.green())
        embed.add_field(name="Time Elapsed", value=f"{time_format(self.vc.position)}", inline=False)

        if track.artwork:
            embed.set_thumbnail(url=track.artwork)

        if track.recommended:
            embed.description += f"\n\n`This track was recommended via {track.source}`"

        self.now_playing_lst.append(await self.music_channel.send(embed=embed, delete_after=(((track.length) - (self.vc.position)) / 1000)))


    @commands.command(name="toggle", aliases=["pause", "resume"])
    async def pause_resume(self, ctx: commands.Context) -> None:
        """Pause or Resume the Player depending on its current state."""
        player: wavelink.Player = cast(wavelink.Player, ctx.voice_client)
        if not player:
            return

        await player.pause(not player.paused)
        await ctx.message.add_reaction('👍')


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
            self.vc.queue.reset()
        
        self.vc.autoplay = wavelink.AutoPlayMode.disabled

        await self.vc.stop()
        await ctx.message.add_reaction('🛑')

        if self.now_playing_lst is not None and 0 < len(self.now_playing_lst):
            await self.clear_messages()


    @commands.command(description="Sets the output volume", aliase=['vol'])
    async def volume(self, ctx, new_volume):
        if not await self.validate_command(ctx) or not self.vc.playing or not new_volume.isdigit():
            return
        
        await self.vc.set_volume(int(new_volume))

        await ctx.message.add_reaction('👍')

    # TODO: Needs to be upgraded and further enhacments
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
    

    @commands.command(description="Shows current filters on bot")
    async def get_filters(self, ctx):
        if not await self.validate_command(ctx) or not self.vc.playing:
            return
        
        embed = discord.Embed(title="", description=f"Current filters on the bot: {self.vc.filters!s}", color=discord.Color.green())              
        return await ctx.send(embed=embed, delete_after=60)


    @commands.command(description="Resets filter on the bot", aliases=['rs_filter', 'rsf'])
    async def reset_filter(self, ctx):
        if not await self.validate_command(ctx) or not self.vc.playing:
            return
        
        if not self.filter_status:
            return await self.filter_not_active_msg(ctx)

        # Reset all filters
        filters: wavelink.Filters = self.vc.filters
        filters.reset()

        await self.vc.set_filters(filters, seek=True)

        await ctx.message.add_reaction('👍')


    @commands.command(description="Changes the timescale of the song", aliases=['ts'])
    async def timescale(self, ctx, speed: float = commands.parameter(default=None, description="Multiplier for the track playback speed"), 
                        pitch: float = commands.parameter(default=None, description="Multiplier for the track pitch"), 
                        rate: float = commands.parameter(default=None, description="Multiplier for the track rate (pitch + speed)")):
        if not await self.validate_command(ctx) or not self.vc.playing:
            return

        if not self.filter_status:
            return await self.filter_not_active_msg(ctx)
        
        filters: wavelink.Filters = self.vc.filters
        filters.timescale.set(pitch=pitch if pitch is not None else round(random.uniform(.01, 2.0), 5), 
                              speed=speed if speed is not None else round(random.uniform(.01, 2.0), 5), 
                              rate=rate if rate is not None else round(random.uniform(.01, 2.0), 5))
            
        await self.vc.set_filters(filters, seek=True)
        await ctx.message.add_reaction('👍')


    @commands.command(description="Rotates the channels of the audio", aliases=['rot'])
    async def rotation(self, ctx, rotation_hz: float = commands.parameter(default=None, description="Multiplier for the track playback speed")):
        if not await self.validate_command(ctx) or not self.vc.playing:
            return

        if not self.filter_status:
            return await self.filter_not_active_msg(ctx)
        
        if rotation_hz is not None and 100.0 < rotation_hz:
            rotation_hz = 100.0
        
        filters: wavelink.Filters = self.vc.filters
        filters.rotation.set(rotation_hz=rotation_hz if rotation_hz is not None else round(random.uniform(0.00001, 5), 5))
            
        await self.vc.set_filters(filters, seek=True)
        await ctx.message.add_reaction('👍')


    @commands.command(description="Distorts the audio", aliases=['dist'])
    async def distortion(self, ctx, sin_offset: float, sin_scale: float, cos_offset: float, 
                         cos_scale: float, tan_offset: float, tan_scale: float, offset: float, scale: float):
        if not await self.validate_command(ctx) or not self.vc.playing:
            return

        if not self.filter_status:
            return await self.filter_not_active_msg(ctx)
        
        filters: wavelink.Filters = self.vc.filters
        filters.distortion.set(
            sin_offset=sin_offset if sin_offset is not None else round(random.uniform(.3, 1), 5),
            sin_scale=sin_scale if sin_scale is not None else round(random.uniform(.3, 1), 5),
            cos_offset=cos_offset if cos_offset is not None else round(random.uniform(.3, 1), 5),
            cos_scale=cos_scale if cos_scale is not None else round(random.uniform(.3, 1), 5),
            tan_offset=tan_offset if tan_offset is not None else round(random.uniform(.3, 1), 5),
            tan_scale=tan_scale if tan_scale is not None else round(random.uniform(.3, 1), 5),
            offset=offset if offset is not None else round(random.uniform(.3, 1), 5),
            scale=scale
        )

        await self.vc.set_filters(filters, seek=True)
        await ctx.message.add_reaction('👍')


async def setup(bot):
    music_bot = MusicBot(bot)
    await bot.add_cog(music_bot)
    await music_bot.setup()