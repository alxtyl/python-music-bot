"""
Contains regex for matching various cases
"""
import re
from typing import Final

URL_REG: Final = re.compile("^(https?|ftp):\/\/[^\s\/$.?#].[^\s]*$")  # Regex for checking if a string is a url
SPOT_REG: Final = re.compile("^(?:https?:\/\/)?(?:www\.)?(?:open|play)\.spotify\.com\/.*$")  # Regex for checking if a string is a url from Spotify
SOUND_REG: Final = re.compile("^(?:https?:\/\/)?(?:www\.)?(?:m\.)?soundcloud\.com\/.*$")  # Regex for checking if a string is a url from Soundcloud
SOUND_FILE_REG: Final = re.compile("(?:https?:\/\/)?\S+(?:.mp3|.flac|.wav)")
YT_NON_PLAYLIST_REG: Final = re.compile("^(?:https?:\/\/)?(?:www\.)?(?:m\.)?youtu\.?be(?:\.com)?\/(?!playlist\?)(?:watch\?.*v=)?([a-zA-Z0-9_-]{11}).*$")  # Regex for checking if a string is a YouTube link (but not a playlist)
YT_PLAYLIST_REG: Final = re.compile("(?:https?:\/\/)?(?:www\.)?youtube\.com\/playlist\?list=([a-zA-Z0-9_-]+)")  # Regex for matching a YouTube playlist