import discord


def is_connected(ctx=None, interaction: discord.Interaction=None):
    voice_client = discord.utils.get(ctx.bot.voice_clients, guild=ctx.guild) if ctx is not None \
        else discord.utils.get(interaction.client.voice_clients, guild=interaction.guild)

    return voice_client and voice_client.connected


def get_voice_channel(interaction: discord.Interaction):
    """
    Get the current voice channel the bot is connected
    """
    voice_client = discord.utils.get(interaction.client.voice_clients, guild=interaction.guild)

    return voice_client.channel if voice_client is not None else None


def is_bot_last_vc_member(bot, channel: discord.VoiceChannel):
    return channel and bot.user in channel.members and len(get_vc_users(channel)) == 0


def get_vc_users(channel: discord.VoiceChannel):
    return [member for member in channel.members if not member.bot]
