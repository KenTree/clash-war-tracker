# bot.py
import discord
from discord.ext import commands, tasks
from datetime import datetime, timezone
import asyncio
from collections import defaultdict
from config import (
    DISCORD_TOKEN,
    DISCORD_GUILD_ID,
    DISCORD_CHANNEL_ID,
    COC_API_KEY,
    CLAN_TAG,
    COC_BASE_URL,
    CHECK_INTERVAL_MINUTES,
    PING_TIMER_HOURS
)
from coc.client import ClashOfClansClient
from coc.war_logic import parse_war_data, members_with_remaining_attacks
from coc.member_mapping import MemberMapper

# Bot setup with intents
intents = discord.Intents.default()
intents.message_content = True
intents.members = True  # Needed to mention members
bot = commands.Bot(command_prefix="!", intents=intents)

# Initialize CoC client and member mapper
coc_client = ClashOfClansClient(COC_API_KEY, COC_BASE_URL)
member_mapper = MemberMapper()

# Rate limiting: Track last command use per user
user_cooldowns = defaultdict(lambda: 0)
COMMAND_COOLDOWN_SECONDS = 3  # Cooldown between commands per user


def is_cwl_week() -> bool:
    """
    Check if we're in a CWL week (first week of the month).
    CWL typically runs during days 1-9 of each month.
    """
    now = datetime.now(timezone.utc)
    return 1 <= now.day <= 9

def parse_coc_time(time_str: str) -> datetime:
    """Parse CoC time format which can be either ISO or compact: 20260306T201037+00:00"""
    time_str = time_str.replace('Z', '+00:00').replace('.000', '')
    if 'T' in time_str and '-' not in time_str[:8]:
        time_str = f"{time_str[:4]}-{time_str[4:6]}-{time_str[6:8]}T{time_str[9:11]}:{time_str[11:13]}:{time_str[13:15]}{time_str[15:]}"
    return datetime.fromisoformat(time_str)

async def check_rate_limit(ctx) -> bool:
    """
    Check if user is rate limited. Returns True if allowed, False if rate limited.
    """
    user_id = ctx.author.id
    now = asyncio.get_event_loop().time()
    last_used = user_cooldowns[user_id]

    if now - last_used < COMMAND_COOLDOWN_SECONDS:
        remaining = COMMAND_COOLDOWN_SECONDS - (now - last_used)
        await ctx.send(f"Please wait {remaining:.1f}s before using another command.", delete_after=5)
        return False

    user_cooldowns[user_id] = now
    return True


def get_war(clan_tag: str) -> dict | None:
    """
    Fetch current war, falling back to CWL if no regular war is active.
    """
    raw_war = coc_client.get_current_war(clan_tag)

    if not raw_war or raw_war.get("state") == "notInWar":
        print("No regular war found, checking for active CWL war...")
        raw_war = coc_client.get_active_cwl_war(clan_tag)

    return raw_war


@bot.event
async def on_ready():
    """Called when the bot successfully connects to Discord"""
    print(f"Bot connected as {bot.user}")
    print(f"Guild ID: {DISCORD_GUILD_ID}")
    print(f"Channel ID: {DISCORD_CHANNEL_ID}")

    # Start the background task to check war status
    if not check_war_status.is_running():
        check_war_status.start()

    print("War monitoring started!")

@bot.command(name="remind")
async def remind_member(ctx, member: discord.Member, delay_minutes: int = 30):
    """"Command to remind a linked member to attack after a certain time"""
    if not await check_rate_limit(ctx):
        return

    is_admin = ctx.author.guild_permissions.administrator
    is_self = ctx.author.id == member.id

    # Non-admins can only remind themselves
    if not is_admin and not is_self:
        await ctx.send("You can only set a reminder for yourself. Admins can remind any member.")
        return

    # If reminding themselves, check they are linked
    if is_self and not is_admin:
        coc_tag = member_mapper.get_coc_tag(ctx.author.id)
        if not coc_tag:
            await ctx.send("You are not linked to a CoC account. Use `!linkme <tag>` first.")
            return

    # Check if target member is linked (for informational purposes)
    coc_tag = member_mapper.get_coc_tag(member.id)
    linked = coc_tag is not None

    if not linked and not is_admin:
        await ctx.send(f"{member.display_name} is not linked to a CoC account.")
        return

    # Confirm reminder was set
    linked_note = f"(CoC: `{coc_tag}`)" if linked else "*(not linked to CoC)*"
    await ctx.send(
        f"Reminder set for {member.mention} {linked_note} in {delay_minutes} minute{'s' if delay_minutes != 1 else ''}."
    )

    # Wait then ping
    await asyncio.sleep(delay_minutes * 60)

    raw_war = get_war(CLAN_TAG)
    if not raw_war:
        return

    war = parse_war_data(raw_war)
    if war is None:
        return

    # If linked, check if they actually still have attacks before pinging
    if linked:
        remaining = members_with_remaining_attacks(war)
        still_has_attack = any(m.tag == coc_tag for m in remaining)

        if not still_has_attack:
            await ctx.send(f"Reminder cancelled — {member.mention} has already used their attack.")
            return

    war_label = "CWL" if war.is_cwl else "war"
    await ctx.send(f"{member.mention} — reminder to use your {war_label} attack!")

@bot.command(name="war")
async def check_war(ctx):
    """Manual command to check current war status"""
    if not await check_rate_limit(ctx):
        return

    raw_war = get_war(CLAN_TAG)

    if not raw_war:
        await ctx.send("No active war found.")
        return

    war = parse_war_data(raw_war)

    if war is None:
        await ctx.send("Could not retrieve war data. Check API key IP whitelist.")
        return

    remaining = members_with_remaining_attacks(war)

    # Sort by map position (war weight order)
    remaining.sort(key=lambda m: m.map_position)

    # Calculate time remaining
    time_remaining_str = "Unknown"
    if war.state == "inWar":
        try:
            end_time = parse_coc_time(war.end_time)
            now = datetime.now(end_time.tzinfo)

            time_delta = end_time - now
            hours = int(time_delta.total_seconds() // 3600)
            minutes = int((time_delta.total_seconds() % 3600) // 60)

            if hours > 0:
                time_remaining_str = f"{hours}h {minutes}m"
            else:
                time_remaining_str = f"{minutes}m"
        except Exception as e:
            print(f"Error calculating time remaining: {e}")
            time_remaining_str = "Error calculating time"

    # Set title and footer based on war type
    war_title = "CWL War Status" if war.is_cwl else "War Status"
    attacks_note = "1 attack per member" if war.is_cwl else "2 attacks per member"

    if not remaining:
        embed = discord.Embed(
            title=war_title,
            description=f"**State:** {war.state}\n**Time Remaining:** {time_remaining_str}\n\nAll attacks have been used!",
            color=discord.Color.green()
        )
        embed.set_footer(text=attacks_note)
        await ctx.send(embed=embed)
        return

    # Build response message with Discord mentions
    member_list = []
    for m in remaining:
        discord_id = member_mapper.get_discord_id(m.tag)
        attacks_text = f"{m.attacks_remaining} attack{'s' if m.attacks_remaining > 1 else ''} remaining"

        if discord_id:
            member_list.append(f"**#{m.map_position}** <@{discord_id}> ({m.name}) - {attacks_text}")
        else:
            member_list.append(f"**#{m.map_position}** {m.name} - {attacks_text} *Not linked*")

    embed = discord.Embed(
        title=war_title,
        description=f"**State:** {war.state}\n**Time Remaining:** {time_remaining_str}\n\n**Members with remaining attacks:**\n" + "\n".join(member_list),
        color=discord.Color.orange()
    )

    embed.set_footer(text=f"{len(remaining)} member{'s' if len(remaining) != 1 else ''} with attacks remaining • {attacks_note}")

    await ctx.send(embed=embed)


@bot.command(name="link")
async def link_member(ctx, coc_tag: str, member: discord.Member):
    """
    Link a CoC player tag to a Discord user
    Usage: !link #ABC123 @DiscordUser
    """
    if not await check_rate_limit(ctx):
        return

    if not ctx.author.guild_permissions.administrator:
        await ctx.send("Only administrators can link members.")
        return

    member_mapper.add_mapping(coc_tag, member.id)
    await ctx.send(f"Linked CoC tag `{coc_tag}` to {member.mention}")


@bot.command(name="unlink")
async def unlink_member(ctx, coc_tag: str):
    """
    Unlink a CoC player tag
    Usage: !unlink #ABC123
    """
    if not await check_rate_limit(ctx):
        return

    if not ctx.author.guild_permissions.administrator:
        await ctx.send("Only administrators can unlink members.")
        return

    if member_mapper.remove_mapping(coc_tag):
        await ctx.send(f"Unlinked CoC tag `{coc_tag}`")
    else:
        await ctx.send(f"No mapping found for `{coc_tag}`")


@bot.command(name="mappings")
async def show_mappings(ctx):
    """Show all current CoC tag to Discord user mappings"""
    if not await check_rate_limit(ctx):
        return

    mappings = member_mapper.get_all_mappings()

    if not mappings:
        await ctx.send("No member mappings found. Use `!link` to add mappings.")
        return

    mapping_list = []
    for coc_tag, discord_id in mappings.items():
        user = await bot.fetch_user(discord_id)
        mapping_list.append(f"• `{coc_tag}` → {user.mention} ({user.name})")

    embed = discord.Embed(
        title="Member Mappings",
        description="\n".join(mapping_list),
        color=discord.Color.blue()
    )

    await ctx.send(embed=embed)


@bot.command(name="unlinked")
async def show_unlinked(ctx):
    """Show all clan members who are NOT linked to Discord accounts"""
    if not await check_rate_limit(ctx):
        return

    raw_war = get_war(CLAN_TAG)

    if not raw_war:
        await ctx.send("No active war found. Cannot fetch clan member list.")
        return

    war = parse_war_data(raw_war)

    if war is None:
        await ctx.send("Could not retrieve war data. Check API key IP whitelist.")
        return

    unlinked = []
    linked = []

    for member in war.members:
        if member_mapper.is_mapped(member.tag):
            linked.append(member)
        else:
            unlinked.append(member)

    if not unlinked:
        await ctx.send("All clan members are linked to Discord accounts!")
        return

    unlinked_list = "\n".join([f"• {m.name} - `{m.tag}`" for m in unlinked])

    embed = discord.Embed(
        title="Unlinked Clan Members",
        description=f"**{len(unlinked)}/{len(war.members)} members are not linked**\n\n{unlinked_list}\n\n*Use `!link <tag> @user` or ask members to use `!linkme <tag>`*",
        color=discord.Color.red()
    )

    embed.add_field(
        name="Summary",
        value=f"Linked: {len(linked)} | Unlinked: {len(unlinked)}",
        inline=False
    )

    await ctx.send(embed=embed)


@bot.command(name="linkme")
async def link_me(ctx, coc_tag: str):
    """
    Link your own CoC tag to your Discord account
    Usage: !linkme #ABC123
    """
    if not await check_rate_limit(ctx):
        return

    member_mapper.add_mapping(coc_tag, ctx.author.id)
    await ctx.send(f"Linked your account to CoC tag `{coc_tag}`")


@bot.command(name="ping")
async def ping_command(ctx):
    """Test command to check if bot is responsive"""
    if not await check_rate_limit(ctx):
        return

    await ctx.send(f"Pong! Latency: {round(bot.latency * 1000)}ms")


@bot.command(name="commands")
async def show_commands(ctx):
    """Display all available bot commands"""
    if not await check_rate_limit(ctx):
        return

    general_commands = [
        ("!war", "Check current war status and see who has attacks remaining (works for both regular war and CWL)"),
        ("!linkme <tag>", "Link your CoC player tag to your Discord account\n*Example: !linkme #ABC123*"),
        ("!mappings", "Show all current CoC tag → Discord user mappings"),
        ("!unlinked", "Show all clan members not linked to Discord accounts"),
        ("!ping", "Check if the bot is online and responsive"),
        ("!commands", "Show this command list")
    ]

    admin_commands = [
        ("!link <tag> @user", "Link a CoC player tag to a Discord user\n*Example: !link #ABC123 @PlayerName*"),
        ("!unlink <tag>", "Remove a CoC tag mapping\n*Example: !unlink #ABC123*"),
        ("!pingwar", "Manually ping all members with remaining attacks")
    ]

    general_text = "\n\n".join([f"**{cmd}**\n{desc}" for cmd, desc in general_commands])
    admin_text = "\n\n".join([f"**{cmd}**\n{desc}" for cmd, desc in admin_commands])

    embed = discord.Embed(
        title="Bot Commands",
        description="Here are all available commands for the Clash of Clans War Bot:",
        color=discord.Color.blue()
    )

    embed.add_field(name="General Commands", value=general_text, inline=False)
    embed.add_field(name="Admin Commands", value=admin_text, inline=False)
    embed.add_field(
        name="How It Works",
        value="The bot monitors your clan war and will automatically ping linked members when the war is ending soon. "
              f"Members are pinged when there are **{PING_TIMER_HOURS} hours or less** remaining in the war. "
              "Supports both regular wars and CWL.",
        inline=False
    )

    embed.set_footer(text=f"Bot checks war status every {CHECK_INTERVAL_MINUTES} minutes")
    await ctx.send(embed=embed)


@bot.command(name="pingwar")
async def ping_war_members(ctx):
    """Manually ping all members with remaining attacks"""
    if not await check_rate_limit(ctx):
        return

    if not ctx.author.guild_permissions.administrator:
        await ctx.send("Only administrators can manually ping war members.")
        return

    raw_war = get_war(CLAN_TAG)

    if not raw_war:
        await ctx.send("No active war found.")
        return

    war = parse_war_data(raw_war)

    if war is None:
        await ctx.send("Could not retrieve war data. Check API key IP whitelist.")
        return

    remaining = members_with_remaining_attacks(war)

    if not remaining:
        await ctx.send("All attacks have been used!")
        return

    linked_members = []
    unlinked_members = []

    for member in remaining:
        discord_id = member_mapper.get_discord_id(member.tag)
        if discord_id:
            linked_members.append((member, discord_id))
        else:
            unlinked_members.append(member)

    war_label = "CWL WAR" if war.is_cwl else "WAR"

    if linked_members:
        mentions = [f"<@{discord_id}>" for _, discord_id in linked_members]
        ping_message = f"**{war_label} REMINDER** \n\n{' '.join(mentions)}\n\nYou have attacks remaining! Don't forget to attack before the war ends!"
        await ctx.send(ping_message)

    if unlinked_members:
        unlinked_names = [m.name for m in unlinked_members]
        warning = f"**Unlinked members with remaining attacks:**\n" + "\n".join([f"• {name}" for name in unlinked_names])
        await ctx.send(warning)


# Track war state
current_war_state = {
    "end_time": None,
    "last_pinged": None,
    "members_with_attacks": []
}


@tasks.loop(minutes=CHECK_INTERVAL_MINUTES)
async def check_war_status():
    """Background task that monitors war status and pings members when war is ending"""
    global current_war_state

    channel = bot.get_channel(DISCORD_CHANNEL_ID)

    if not channel:
        print(f"Error: Could not find channel with ID {DISCORD_CHANNEL_ID}")
        return

    raw_war = get_war(CLAN_TAG)

    if not raw_war:
        print("No active war detected.")
        current_war_state = {"end_time": None, "last_pinged": None, "members_with_attacks": []}
        return

    war = parse_war_data(raw_war)

    if war is None:
        print("Could not parse war data. Skipping this check")
        return

    # Only monitor during active war
    if war.state != "inWar":
        print(f"War state is '{war.state}', not in war.")
        current_war_state = {"end_time": None, "last_pinged": None, "members_with_attacks": []}
        return

    war_label = "CWL" if war.is_cwl else "Regular war"
    current_war_state["end_time"] = war.end_time

    remaining = members_with_remaining_attacks(war)

    if not remaining:
        print("All attacks have been used!")
        current_war_state["members_with_attacks"] = []
        return

    current_war_state["members_with_attacks"] = [m.tag for m in remaining]
    print(f"{war_label} active. {len(remaining)} members with remaining attacks.")

    # Handle CoC compact format: 20260306T201037.000+00:00 or 20260306T201037+00:00
    end_time = parse_coc_time(war.end_time)
    now = datetime.now(end_time.tzinfo)

    time_remaining = (end_time - now).total_seconds() / 3600  # Hours remaining

    if time_remaining <= PING_TIMER_HOURS and current_war_state["last_pinged"] != war.end_time:
        print(f"{war_label} ending in {time_remaining:.1f} hours. Sending reminder...")

        linked_members = []
        for member in remaining:
            discord_id = member_mapper.get_discord_id(member.tag)
            if discord_id:
                linked_members.append((member, discord_id))

        if linked_members:
            mentions = [f"<@{discord_id}>" for _, discord_id in linked_members]
            hours_text = f"{time_remaining:.1f} hours" if time_remaining > 1 else f"{time_remaining * 60:.0f} minutes"
            war_label_upper = "CWL WAR" if war.is_cwl else "WAR"
            ping_message = f"**{war_label_upper} ENDING SOON** \n\n{' '.join(mentions)}\n\nWar ends in **{hours_text}**!\nYou still have attacks remaining. Don't forget to attack!"
            await channel.send(ping_message)
            print(f"Pinged {len(linked_members)} members")
            current_war_state["last_pinged"] = war.end_time
        else:
            print("No linked members to ping.")
    else:
        print(f"{war_label} has {time_remaining:.1f} hours remaining. Not pinging yet.")


@check_war_status.before_loop
async def before_check_war_status():
    """Wait until bot is ready before starting the loop"""
    await bot.wait_until_ready()


def run_bot():
    """Start the Discord bot"""
    if not DISCORD_TOKEN:
        print("Error: DISCORD_TOKEN not found in environment variables")
        return

    bot.run(DISCORD_TOKEN)


if __name__ == "__main__":
    run_bot()
