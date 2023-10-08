import os
import discord
import asyncio
import logging
import wavelink
from wavelink.ext import spotify
from discord.ext import commands

from global_vars.regex import *
from global_vars.timeout import *
from .queue_writer import update_queue_file

logging.getLogger().setLevel(logging.INFO)

class VoiceConnectionError(commands.CommandError):
    """Custom Exception class for connection errors."""

class InvalidVoiceChannel(VoiceConnectionError):
    """Exception for cases of invalid Voice Channels."""

class MusicBot(commands.Cog):
    timer = None
    current_track = None
    music_channel = None
    node = None
    vc : wavelink.Player = None
    
    def __init__(self, bot):
        self.bot = bot
        
    async def setup(self):
        """
        Sets up a connection to lavalink
        """
        sc = spotify.SpotifyClient(client_id=os.environ['SPOTIFY_ID'],
                                    client_secret=os.environ['SPOTIFY_SECRET'])
                                                    

        node: wavelink.Node = wavelink.Node(uri='http://localhost:2333', password=os.environ['SERVER_PASS'])
        await wavelink.NodePool.connect(client=self.bot, nodes=[node], spotify=sc)


    async def timeout(self) -> None:
        await asyncio.sleep(AFK_TIMEOUT)
        if self.vc.is_connected() and not self.vc.is_playing():
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
            await ctx.send(embed=embed)
            return False
        if not self.vc or not self.vc.is_connected():
            embed = discord.Embed(title="", description="I'm not connected to a voice channel", color=discord.Color.red())
            await ctx.send(embed=embed)
            return False
        if ctx.guild.voice_client.channel != ctx.message.author.voice.channel:
            embed = discord.Embed(title="", description="You're not connected to the same voice channel as me", color=discord.Color.red())
            await ctx.send(embed=embed)
            return False
        
        return True

    def _is_connected(self, ctx):
        voice_client = discord.utils.get(ctx.bot.voice_clients, guild=ctx.guild)
        return voice_client and voice_client.is_connected()
    
    async def queue_msg(self, ctx):
        if (type(self.current_track) == wavelink.ext.spotify.SpotifyTrack) and (track_url := self.current_track.raw['external_urls']['spotify']):
            embed = discord.Embed(title="", description=f"Queued [{self.current_track.title}]({(track_url)}) [{ctx.author.mention}]", color=discord.Color.green())              
            return await ctx.send(embed=embed)
        else:
            embed = discord.Embed(title="", description=f"Queued [{self.current_track.title}]({(self.current_track.uri)}) [{ctx.author.mention}]", color=discord.Color.green())              
            return await ctx.send(embed=embed)
        
    async def now_playing_msg(self):
        if (type(self.current_track) == wavelink.ext.spotify.SpotifyTrack) and (track_url := self.current_track.raw['external_urls']['spotify']):
            embed = discord.Embed(title="", description=f"Now playing [{self.current_track.title}]({track_url})", color=discord.Color.green())
            return await self.music_channel.send(embed=embed, delete_after=(self.current_track.length / 1000))
        else:
            embed = discord.Embed(title="", description=f"Now playing [{self.current_track.title}]({self.current_track.uri})", color=discord.Color.green())
            return await self.music_channel.send(embed=embed, delete_after=(self.current_track.length / 1000))
        
    async def now_playing_dur_msg(self, ctx, duration):
        if (type(self.current_track) == wavelink.ext.spotify.SpotifyTrack) and (track_url := self.current_track.raw['external_urls']['spotify']):
            embed = discord.Embed(title="Now playing", color=discord.Color.blurple())
            embed.add_field(name="Current track:", value=f"[{str(self.vc.current.title)}]({track_url}) - {duration}")
            return await ctx.send(embed=embed, delete_after=(self.current_track.length / 1000))
        else:
            embed = discord.Embed(title="", description=f"Now playing [{self.current_track.title}]({self.current_track.uri})", color=discord.Color.green())
            return await self.music_channel.send(embed=embed, delete_after=(self.current_track.length / 1000))
    
    @commands.Cog.listener()
    async def on_wavelink_node_ready(self, node: wavelink.Node):
        logging.info(f"{node} is ready")

    @commands.Cog.listener()
    async def on_wavelink_track_end(self, payload):
        # On the end of each track, reset the AFK timer
        # If the queue is not empty, play next song
        player = payload.player
        if self.timer is not None:
            self.timer.cancel()
            self.timer = None
            logging.info("AFK timer reset")
        if not player.queue.is_empty and not player.is_playing():
            self.current_track = player.queue.get()
            await self.now_playing_msg()
            await player.play(self.current_track)
        
        await update_queue_file(self.vc.queue)
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

        if not self.vc.queue.is_empty:
            self.vc.queue.clear()
            await update_queue_file(self.vc.queue)

        await ctx.message.add_reaction('👋')
        server = ctx.message.guild.voice_client
        await server.disconnect()
            
    @commands.command(name='play', aliases=['sing','p'], description="Plays a given input if it's valid")
    async def play(self, ctx, *, user_input = None):
        try:
            if not self._is_connected(ctx):
                if await ctx.invoke(self.bot.get_command('join')) == False:
                    return

            if ctx.guild.voice_client.channel != ctx.message.author.voice.channel:
                embed = discord.Embed(title="", description="You're not connected to the same voice channel as me", color=discord.Color.red())
                return await ctx.send(embed=embed)
            
            if ctx.message.attachments == []:
                if URL_REG.match(user_input):
                    if YT_NON_PLAYLIST_REG.match(user_input) or YT_SHORT_REG.match(user_input):
                        self.current_track = (await wavelink.NodePool.get_node().get_tracks(wavelink.YouTubeTrack, user_input))[0]
                        if self.vc.is_playing() or not self.vc.queue.is_empty:
                            await self.queue_msg(ctx)
                        self.vc.queue.put(self.current_track)

                    elif YT_PLAYLIST_REG.match(user_input):
                        self.playlist = await wavelink.YouTubePlaylist.search(user_input)
                        for track in self.playlist.tracks:
                            self.vc.queue.put(track)
                        embed = discord.Embed(title="", description=f"Added {len(self.playlist.tracks)} tracks to the queue [{ctx.author.mention}]", color=discord.Color.green())
                        await ctx.send(embed=embed)

                    elif SPOT_REG.match(user_input):
                        decoded = spotify.decode_url(user_input)
                        if decoded and decoded['type'] is spotify.SpotifySearchType.track:
                            self.current_track = (await spotify.SpotifyTrack.search(query=user_input))[0]
                            if self.vc.is_playing() or not self.vc.queue.is_empty:
                                await self.queue_msg(ctx)
                            self.vc.queue.put(self.current_track)

                        elif decoded and (decoded['type'] is spotify.SpotifySearchType.album or decoded['type'] is spotify.SpotifySearchType.playlist):
                            counter = 0
                            async for track in spotify.SpotifyTrack.iterator(query=user_input):
                                self.vc.queue.put(track)
                                counter += 1
                            embed = discord.Embed(title="", description=f"Added {counter} tracks to the queue [{ctx.author.mention}]", color=discord.Color.green())
                            await ctx.send(embed=embed)

                    elif SOUND_REG.match(user_input):
                        if '/sets/' in user_input:
                            embed = discord.Embed(title="", description=f"Sets/Playlists from Soundcloud are not supported", color=discord.Color.red())
                            return await ctx.send(embed=embed)
                        self.current_track = (await wavelink.NodePool.get_node().get_tracks(wavelink.SoundCloudTrack, user_input))[0]
                        if self.vc.is_playing() or not self.vc.queue.is_empty:
                            await self.queue_msg(ctx)
                        self.vc.queue.put(self.current_track)

                    elif SOUND_FILE_REG.match(user_input):
                        self.current_track = await self.vc.node.get_tracks(query=user_input, cls=wavelink.LocalTrack)[0]
                        if self.vc.is_playing() or not self.vc.queue.is_empty:
                            await self.queue_msg(ctx)
                        self.vc.queue.put(self.current_track[0])

                else:
                    chosen_track = (await wavelink.YouTubeTrack.search(user_input))[0]
                    if chosen_track:
                        self.current_track = chosen_track
                        if self.vc.is_playing() or not self.vc.queue.is_empty:
                            await self.queue_msg(ctx)
                        self.vc.queue.put(self.current_track)

            else:
                self.current_track = (await self.vc.node.get_tracks(query=ctx.message.attachments[0].url, cls=wavelink.LocalTrack))[0]
                if self.vc.is_playing() or not self.vc.queue.is_empty:
                    await self.queue_msg(ctx)
                self.vc.queue.put(self.current_track)

            await update_queue_file(self.vc.queue)

            if not self.vc.is_playing():
                self.current_track = self.vc.queue.get()
                await self.now_playing_msg()
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
        
        if self.vc.queue.is_empty:
            embed = discord.Embed(title="", description="The queue is empty", color=discord.Color.blue())
            return await ctx.send(embed=embed)

        pages = list()
        song_lst = list()
        song_count = 0
        
        queue_cnt = self.vc.queue.count
        temp_queue = self.vc.queue.copy()
        num_pages = int((queue_cnt // 10) + 1)
        
        # Build the queue w/ times & index
        for i in range(queue_cnt):
            song_count += 1
            song_num = i + 1

            song = temp_queue.get()
            seconds = int(song.length / 1000) % (24 * 3600)  # Convert from milliseconds -> seconds
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

        seconds = int(self.vc.current.length / 1000 ) % (24 * 3600)  # Convert from milliseconds -> seconds
        hour = seconds // 3600
        seconds %= 3600
        minutes = seconds // 60
        seconds %= 60
        if hour > 0:
            duration = "%dh %02dm %02ds" % (hour, minutes, seconds)
        else:
            duration = "%02dm %02ds" % (minutes, seconds)

        return await self.now_playing_dur_msg(ctx, duration)

    @commands.command(name="shuffle", aliases=["shuf"], description="Shuffles the queue")
    async def shuffle(self, ctx):
        if not await self.validate_command(ctx):
            return
        
        if self.vc.queue.is_empty:
            embed = discord.Embed(title="", description="The queue is empty", color=discord.Color.red())
            return await ctx.send(embed=embed)

        self.vc.queue.shuffle()
        
        await update_queue_file(self.vc.queue)

        await ctx.message.add_reaction('👍')

    @commands.command(name='remove', aliases=['rm'], description="Removes a song from the queue")
    async def remove(self, ctx, *user_input : str):
        if not await self.validate_command(ctx) or not user_input:
            return
        
        if self.vc.queue.is_empty:
            embed = discord.Embed(title="", description="The queue is empty", color=discord.Color.red())
            return await ctx.send(embed=embed)

        user_input = " ".join(user_input)
        rm_track_num = int(user_input) - 1  # Change input to align with zero-based index

        if not user_input.isdigit() or self.vc.queue.count < rm_track_num or rm_track_num <= -1:
            embed = discord.Embed(title="", description="Please send a valid track to remove", color=discord.Color.red())
            return await ctx.send(embed=embed)
        
        del self.vc.queue[rm_track_num]
        await ctx.message.add_reaction('👍')
        
        await update_queue_file(self.vc.queue)

    @commands.command(name='skip', aliases=['s', 'next'], description="Skips the current song")
    async def skip(self, ctx):
        if not await self.validate_command(ctx):
            return
        
        if not self.vc.is_playing():
            embed = discord.Embed(title="", description="I'm not playing anything", color=discord.Color.red())
            return await ctx.send(embed=embed)

        if self.vc.queue.is_empty:
            # If the queue is empty, we can stop the bot
            await ctx.message.add_reaction('👍')
            return await self.vc.stop()

        self.current_track = self.vc.queue.get()
        await self.now_playing_msg()
        await update_queue_file(self.vc.queue)
        return await self.vc.play(self.current_track)

    @commands.command(description="Resume current paused song")
    async def resume(self, ctx):
        if not await self.validate_command(ctx):
            return
            
        await self.vc.resume()
        return await ctx.send("Resuming current track")
    
    @commands.command(description="Pause playing song")
    async def pause(self, ctx):
        if not await self.validate_command(ctx):
            return
            
        await self.vc.pause()
        return await ctx.send("Paused current track")

    @commands.command(name='clear', aliases=['clr', 'cl', 'cr'], description="Clears entire queue")
    async def clear(self, ctx):
        await ctx.typing()

        if not await self.validate_command(ctx):
            return

        self.vc.queue.clear()
        await update_queue_file(self.vc.queue)
        embed = discord.Embed(title="", description="Queue is cleared", color=discord.Color.green())
        return await ctx.send(embed=embed)
        
    @commands.command(description="Stops the bot and resets the queue")
    async def stop(self, ctx):
        if not await self.validate_command(ctx):
            return
        
        if not self.vc.is_playing():
            embed = discord.Embed(title="", description="I'm not playing anything", color=discord.Color.red())
            return await ctx.send(embed=embed)

        if not self.vc.queue.is_empty:
            self.vc.queue.clear()
            await update_queue_file(self.vc.queue)

        await self.vc.stop()
        await ctx.message.add_reaction('🛑')
        
    @commands.command(description="Sets the output volume")
    async def volume(self, ctx, new_volume : int = 100):
        if not await self.validate_command(ctx):
            return
        
        await self.vc.set_volume(new_volume)

        await ctx.message.add_reaction('👍')

async def setup(bot):
    music_bot = MusicBot(bot)
    await bot.add_cog(music_bot)
    await music_bot.setup()