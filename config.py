# config.py
import os
from dotenv import load_dotenv

load_dotenv()

# Clash of Clans API
COC_API_KEY = os.getenv("COC_API_KEY")
CLAN_TAG = os.getenv("CLAN_TAG")
COC_BASE_URL = "https://api.clashofclans.com/v1"

# Discord Bot
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
DISCORD_GUILD_ID = int(os.getenv("DISCORD_GUILD_ID")) if os.getenv("DISCORD_GUILD_ID") else None
DISCORD_CHANNEL_ID = int(os.getenv("DISCORD_CHANNEL_ID")) if os.getenv("DISCORD_CHANNEL_ID") else None

# Bot Settings
PING_TIMER_HOURS = int(os.getenv("PING_TIMER_HOURS", "12"))
CHECK_INTERVAL_MINUTES = int(os.getenv("CHECK_INTERVAL_MINUTES", "30"))