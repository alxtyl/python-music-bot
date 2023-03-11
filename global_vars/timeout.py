"""
Constants for timeout for leaving the chat, deleting messages, etc
"""
from typing import Final

AFK_TIMEOUT: Final[int] = 1200   # Amount of seconds before the bot disconnects due to nothing being played
QUEUE_TIMEOUT: Final[int] = 180  # Time before users aren't able to interact with the queue pages