# bot.py
import discord
from discord.ext import commands, tasks
from config import (
    DISCORD_TOKEN, 
    DISCORD_GUILD_ID, 
    DISCORD_CHANNEL_ID,
    COC_API_KEY,
    CLAN_TAG,
    COC_BASE_URL,
    CHECK_INTERVAL_MINUTES
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


@bot.command(name="war")
async def check_war(ctx):
    """Manual command to check current war status"""
    raw_war = coc_client.get_current_war(CLAN_TAG)
    
    if not raw_war:
        await ctx.send("❌ No active war found.")
        return
    
    war = parse_war_data(raw_war)
    remaining = members_with_remaining_attacks(war)
    
    if not remaining:
        await ctx.send("✅ All attacks have been used!")
        return
    
    # Build response message with Discord mentions
    member_list = []
    for m in remaining:
        discord_id = member_mapper.get_discord_id(m.tag)
        if discord_id:
            member_list.append(f"• <@{discord_id}> ({m.name}) - {m.attacks_remaining} attack{'s' if m.attacks_remaining > 1 else ''} remaining")
        else:
            member_list.append(f"• {m.name} - {m.attacks_remaining} attack{'s' if m.attacks_remaining > 1 else ''} remaining ⚠️ *Not linked*")
    
    embed = discord.Embed(
        title="⚔️ War Status",
        description=f"**State:** {war.state}\n\n**Members with remaining attacks:**\n" + "\n".join(member_list),
        color=discord.Color.orange()
    )
    
    await ctx.send(embed=embed)


@bot.command(name="link")
async def link_member(ctx, coc_tag: str, member: discord.Member):
    """
    Link a CoC player tag to a Discord user
    Usage: !link #ABC123 @DiscordUser
    """
    if not ctx.author.guild_permissions.administrator:
        await ctx.send("❌ Only administrators can link members.")
        return
    
    # Add the mapping
    member_mapper.add_mapping(coc_tag, member.id)
    
    await ctx.send(f"✅ Linked CoC tag `{coc_tag}` to {member.mention}")


@bot.command(name="unlink")
async def unlink_member(ctx, coc_tag: str):
    """
    Unlink a CoC player tag
    Usage: !unlink #ABC123
    """
    if not ctx.author.guild_permissions.administrator:
        await ctx.send("❌ Only administrators can unlink members.")
        return
    
    if member_mapper.remove_mapping(coc_tag):
        await ctx.send(f"✅ Unlinked CoC tag `{coc_tag}`")
    else:
        await ctx.send(f"❌ No mapping found for `{coc_tag}`")


@bot.command(name="mappings")
async def show_mappings(ctx):
    """Show all current CoC tag to Discord user mappings"""
    mappings = member_mapper.get_all_mappings()
    
    if not mappings:
        await ctx.send("No member mappings found. Use `!link` to add mappings.")
        return
    
    # Build list of mappings
    mapping_list = []
    for coc_tag, discord_id in mappings.items():
        user = await bot.fetch_user(discord_id)
        mapping_list.append(f"• `{coc_tag}` → {user.mention} ({user.name})")
    
    embed = discord.Embed(
        title="🔗 Member Mappings",
        description="\n".join(mapping_list),
        color=discord.Color.blue()
    )
    
    await ctx.send(embed=embed)


@bot.command(name="unlinked")
async def show_unlinked(ctx):
    """Show all clan members who are NOT linked to Discord accounts"""
    # Get current war to fetch clan members
    raw_war = coc_client.get_current_war(CLAN_TAG)
    
    if not raw_war:
        await ctx.send("❌ No active war found. Cannot fetch clan member list.")
        return
    
    war = parse_war_data(raw_war)
    
    # Check which members are not linked
    unlinked = []
    linked = []
    
    for member in war.members:
        if member_mapper.is_mapped(member.tag):
            linked.append(member)
        else:
            unlinked.append(member)
    
    if not unlinked:
        await ctx.send("✅ All clan members are linked to Discord accounts!")
        return
    
    # Build unlinked member list
    unlinked_list = "\n".join([f"• {m.name} - `{m.tag}`" for m in unlinked])
    
    embed = discord.Embed(
        title="⚠️ Unlinked Clan Members",
        description=f"**{len(unlinked)}/{len(war.members)} members are not linked**\n\n{unlinked_list}\n\n*Use `!link <tag> @user` or ask members to use `!linkme <tag>`*",
        color=discord.Color.red()
    )
    
    embed.add_field(
        name="📊 Summary",
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
    member_mapper.add_mapping(coc_tag, ctx.author.id)
    await ctx.send(f"✅ Linked your account to CoC tag `{coc_tag}`")


@bot.command(name="ping")
async def ping_command(ctx):
    """Test command to check if bot is responsive"""
    await ctx.send(f"🏓 Pong! Latency: {round(bot.latency * 1000)}ms")


@bot.command(name="pingwar")
async def ping_war_members(ctx):
    """Manually ping all members with remaining attacks"""
    if not ctx.author.guild_permissions.administrator:
        await ctx.send("❌ Only administrators can manually ping war members.")
        return
    
    raw_war = coc_client.get_current_war(CLAN_TAG)
    
    if not raw_war:
        await ctx.send("❌ No active war found.")
        return
    
    war = parse_war_data(raw_war)
    remaining = members_with_remaining_attacks(war)
    
    if not remaining:
        await ctx.send("✅ All attacks have been used!")
        return
    
    # Separate members into linked and unlinked
    linked_members = []
    unlinked_members = []
    
    for member in remaining:
        discord_id = member_mapper.get_discord_id(member.tag)
        if discord_id:
            linked_members.append((member, discord_id))
        else:
            unlinked_members.append(member)
    
    # Build ping message
    if linked_members:
        mentions = [f"<@{discord_id}>" for _, discord_id in linked_members]
        ping_message = f"⚔️ **WAR REMINDER** ⚔️\n\n{' '.join(mentions)}\n\nYou have attacks remaining! Don't forget to attack before the war ends!"
        await ctx.send(ping_message)
    
    # Notify about unlinked members
    if unlinked_members:
        unlinked_names = [m.name for m in unlinked_members]
        warning = f"⚠️ **Unlinked members with remaining attacks:**\n" + "\n".join([f"• {name}" for name in unlinked_names])
        await ctx.send(warning)


@tasks.loop(minutes=CHECK_INTERVAL_MINUTES)
async def check_war_status():
    """Background task that runs every X minutes to check war status and ping members"""
    channel = bot.get_channel(DISCORD_CHANNEL_ID)
    
    if not channel:
        print(f"Error: Could not find channel with ID {DISCORD_CHANNEL_ID}")
        return
    
    raw_war = coc_client.get_current_war(CLAN_TAG)
    
    if not raw_war:
        print("No active war detected.")
        return
    
    war = parse_war_data(raw_war)
    
    # Only send notifications during active war
    if war.state != "inWar":
        print(f"War state is '{war.state}', not sending notifications.")
        return
    
    remaining = members_with_remaining_attacks(war)
    
    if not remaining:
        print("All attacks have been used!")
        return
    
    print(f"Found {len(remaining)} members with remaining attacks.")
    
    # Separate members into linked and unlinked
    linked_members = []
    unlinked_members = []
    
    for member in remaining:
        discord_id = member_mapper.get_discord_id(member.tag)
        if discord_id:
            linked_members.append((member, discord_id))
        else:
            unlinked_members.append(member)
    
    # Send ping message for linked members
    if linked_members:
        mentions = [f"<@{discord_id}>" for _, discord_id in linked_members]
        ping_message = f"⚔️ **WAR REMINDER** ⚔️\n\n{' '.join(mentions)}\n\nYou have attacks remaining! Don't forget to attack before the war ends!"
        await channel.send(ping_message)
        print(f"Pinged {len(linked_members)} members")


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