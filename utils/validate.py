import discord
from utils.connect import is_connected, get_voice_channel


async def validate_command_voice(interaction: discord.Interaction) -> bool:
    """
    Checks to make sure user is performing
    a valid action before executing command while the bot is connected to a voice channel.
    """
    if interaction.user.voice is None:
        await interaction.response.send_message(content="You're not connected to a voice channel", ephemeral=True)
        return False
    elif interaction.client.voice_clients is None or len(interaction.client.voice_clients) < 1 or not is_connected(ctx=None, interaction=interaction):
        await interaction.response.send_message(content="I'm not connected to a voice channel", ephemeral=True)
        return False
    elif interaction.user.voice.channel != get_voice_channel(interaction=interaction):
        await interaction.response.send_message(content="You're not connected to the same voice channel as me", ephemeral=True)
        return False

    return True


async def validate_join_command(interaction: discord.Interaction) -> bool:
    """
    Verifies user is able to have bot join a voice channel
    """
    if interaction.user.voice is None:
        await interaction.response.send_message(content="Please join a voice channel first", ephemeral=True)
        return False
    
    return True