# Clash of Clans War Tracker Bot
To create your own clan tracker bot, you have to have your own discord bot setup with proper permissions. I recommend watching Tech With Tim's video on setting up your Discord Bot. Once this is complete you can continue with the environment setup.
Discord Bot Setup with Python: https://youtu.be/YD_N6Ffoojw?si=0Y2jVtTMvYLddmZk


## Requirements

- Python 3.10+
- A Discord bot token
- A Clash of Clans API key
- Your clan tag

Install dependencies:
```bash
pip install -r requirements.txt
```

To find your Discord IDs you must have **Developer Mode** active:
`User Settings` → `Advanced` → toggle on **Developer Mode**

## Environment Setup
1. Create your `.env` file
2. Setup `.env` file accordingly (**config.py will draw from this file, so DO NOT SKIP this step**):

```env
COC_API_KEY=*(INSERT YOUR CLASH OF CLANS API KEY)*
CLAN_TAG=#*(INSERT YOUR CLAN TAG, KEEP THE #)*

To be able to view all of these tokens you must have Developer Mode active
DISCORD_TOKEN=*(YOUR DISCORD BOT TOKEN)*
DISCORD_GUILD_ID=*(YOUR DISCORD SERVER ID)*
DISCORD_CHANNEL_ID=*(YOUR CHANNEL ID)*

Customizable Bot Configuration:
PING_TIMER_HOURS=*(INSERT ANY TIME)*
CHECK_INTERVAL_MINUTES=*(CHECKING INTERVALS)*
```


| Variable | How to get it |
|---|---|
| `DISCORD_TOKEN` | [Discord Developer Portal](https://discord.com/developers/applications) → Your App → Bot tab |
| `DISCORD_GUILD_ID` | Right-click your server icon → Copy Server ID |
| `DISCORD_CHANNEL_ID` | Right-click your channel → Copy Channel ID |
| `COC_API_KEY` | [Clash of Clans Developer Portal](https://developer.clashofclans.com) — must whitelist your server's IP |
| `CLAN_TAG` | Found in-game on your clan profile, keep the `#` |

> **Note:** Your CoC API key is IP-whitelisted. If you run the bot on a new machine, you must add its public IP to your API key in the developer portal. Run `curl ifconfig.me` to find your machine's public IP.

## Running the Bot

```bash
python3 bot.py
```


## Member Linking

For the bot to ping members in Discord, each player's CoC tag must be linked to their Discord account. Members can link themselves, or an admin can link them manually.

- Members without a linked account will still appear in `!war` output marked as *Not linked*, but will not receive pings.
- Linking is persistent and stored locally in a mappings file.

## Current Default Available Commands

### 👥 General Commands
| Command | Description |
|---|---|
| `!war` | Check current war status and see who has attacks remaining |
| `!linkme <#tag>` | Link your own CoC player tag to your Discord account (e.g. `!linkme #ABC123`) |
| `!remind @user <minutes>` | Set a delayed reminder ping for a member to attack (default: 30 min) |
| `!mappings` | Show all current CoC tag → Discord user mappings |
| `!unlinked` | Show all clan members in the current war not linked to a Discord account |
| `!ping` | Check if the bot is online and view latency |
| `!commands` | Display all available commands in Discord |

### 🔧 Admin Commands
*(Requires Administrator permission)*
| Command | Description |
|---|---|
| `!link <#tag> @user` | Link a CoC player tag to a Discord user (e.g. `!link #ABC123 @PlayerName`) |
| `!unlink <#tag>` | Remove a CoC tag to Discord mapping (e.g. `!unlink #ABC123`) |
| `!pingwar` | Manually ping all linked members who still have attacks remaining |


## Automatic Behavior

The bot runs a background task every `CHECK_INTERVAL_MINUTES` minutes. When a war is active and within `PING_TIMER_HOURS` hours of ending, it will automatically ping all linked members with remaining attacks in the configured Discord channel.

Both regular wars and CWL are supported:
- **Regular war** — members have 2 attacks each
- **CWL** — members have 1 attack each, bot detects this automatically

---

## Project Structure

```
clash-war-tracker/
├── bot.py                  # Main bot file, commands and background task
├── config.py               # Loads environment variables
├── .env                    # Your secrets (never commit this)
├── requirements.txt        # Python dependencies
└── coc/
    ├── client.py           # Clash of Clans API client
    ├── models.py           # War and Member data models
    ├── war_logic.py        # War parsing and attack logic
    └── member_mapping.py   # CoC tag to Discord ID mappings
```

---
