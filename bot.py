import os
import discord
import asyncio
import re
import logging
from discord.ext import commands
from dotenv import load_dotenv
from emoji import is_emoji

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix='!', intents=intents)

async def is_moderator(ctx):
    mod_role_name = os.getenv("MODERATOR_ROLE_NAME")

    if mod_role_name is None:
        print("Error: MODERATOR_ROLE_NAME is missing from your .env file.")
        return False
    
    if ctx.guild and isinstance(ctx.author, discord.Member):
        return any(role.name.lower() == mod_role_name.lower() for role in ctx.author.roles)
    
    return False

@bot.event
async def on_ready():
    logger.info(f'We have logged in as {bot.user}')

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    await bot.process_commands(message)

@bot.command()
async def test(ctx, *, args):
    await ctx.send(args)

@bot.command()
async def hello(ctx):
    await ctx.send("Hello!")

# stats command
@bot.command()
async def stats(ctx):
    if ctx.guild is None:
        await ctx.send("This command can only be used inside a server.")
        return
    
    member_count = ctx.guild.member_count
    channel_count = len(ctx.guild.channels)
    created_date = ctx.guild.created_at.strftime("%m-%d-%Y")

    response = (
        f"**Members:** {member_count}\n"
        f"**Channels:** {channel_count}\n"
        f"**Created On:** {created_date}"
    )
    await ctx.send(response)

# welcome event
@bot.event
async def on_member_join(member):
    channel_id_str = os.getenv("WELCOME_CHANNEL_ID")

    if channel_id_str is None:
        logger.warning("WELCOME_CHANNEL_ID is missing from environment; skipping welcome message.")
        return

    try:
        channel_id = int(channel_id_str)
    except ValueError:
        logger.error("WELCOME_CHANNEL_ID is not a valid integer: %s", channel_id_str)
        return

    try:
        channel = bot.get_channel(channel_id) or await bot.fetch_channel(channel_id)
    except (discord.NotFound, discord.HTTPException) as e:
        logger.error("Could not fetch welcome channel %s: %s", channel_id, e)
        return

    if not isinstance(channel, discord.TextChannel):
        logger.warning("Configured WELCOME_CHANNEL_ID is not a text channel: %s", channel)
        return

    try:
        await channel.send(f"Welcome to the server, {member.mention}! I'm so glad you're here! I'd really appreciate it if you could help me.")
    except discord.Forbidden:
        logger.warning("Missing permission to send messages to welcome channel %s", channel_id)
    except discord.HTTPException as e:
        logger.error("Failed to send welcome message: %s", e)

# run through this function to prevent users from voting on multiple options at once
@bot.event
async def on_raw_reaction_add(payload):
    # ignore bot's own reaction when it sets up the poll
    if bot.user is None or payload.user_id == bot.user.id:
        return
    
    # fetch channel and message where reaction happened
    try:
        channel = bot.get_channel(payload.channel_id) or await bot.fetch_channel(payload.channel_id)
    except (discord.NotFound, discord.HTTPException) as e:
        logger.error("Could not fetch channel for reaction payload: %s", e)
        return

    if isinstance(channel, discord.TextChannel):
        try:
            message = await channel.fetch_message(payload.message_id)
        except (discord.NotFound, discord.HTTPException) as e:
            logger.error("Could not fetch message %s: %s", payload.message_id, e)
            return

        # only apply this to poll messages
        if message.author == bot.user and message.content.startswith("📊"):
            # loop through every reaction currently on the message
            for reaction in message.reactions:
                # if its NOT the emoji the user just clicked
                if str(reaction.emoji) != str(payload.emoji):
                    # check if user has already reacted to other emoji
                    async for user in reaction.users():
                        if user.id == payload.user_id:
                            # remove newly added reaction to block double vote
                            try:
                                await message.remove_reaction(payload.emoji, user)
                            except (discord.Forbidden, discord.HTTPException) as e:
                                logger.warning("Failed to remove reaction: %s", e)
                            return

# poll command
@bot.command()
async def poll(ctx, *args):
    if len(args) < 2:
        await ctx.send("Usage: !poll \"Question\" \"Option 1\" \"Option 2\"")
        return

    try:
        await ctx.message.delete()
    except (discord.Forbidden, discord.HTTPException):
        logger.info("Could not delete invoking poll message; continuing")

    question_text = args[0].strip()
    poll_options = args[1:]

    # basic validation
    if not question_text:
        await ctx.send("Poll question cannot be empty.")
        return

    max_options = 20
    if len(poll_options) == 0 or len(poll_options) > max_options:
        await ctx.send(f"Poll must have between 1 and {max_options} options.")
        return

    default_numbers = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]

    final_body_lines = []
    reactions_to_add = []

    for index, option in enumerate(poll_options):
        cleaned_option = option.strip()
        if not cleaned_option:
            await ctx.send("Poll options cannot be empty.")
            return

        first_char = cleaned_option[0]

        if is_emoji(first_char):
            final_body_lines.append(cleaned_option)
            reactions_to_add.append(first_char)
        else:
            number_emoji = default_numbers[index % len(default_numbers)]
            final_body_lines.append(f"{number_emoji} {cleaned_option}")
            reactions_to_add.append(number_emoji)

    poll_body = f"📊 **{question_text}**\n" + "\n".join(final_body_lines)
    try:
        message = await ctx.send(poll_body)
    except (discord.Forbidden, discord.HTTPException) as e:
        logger.error("Failed to send poll message: %s", e)
        return

    for emoji in reactions_to_add:
        try:
            await message.add_reaction(emoji)
        except (discord.HTTPException, discord.Forbidden) as e:
            logger.warning("Could not add reaction %s: %s", emoji, e)

# clear command
@bot.command()
@commands.check(is_moderator)
async def clear(ctx, amount: int):
    # deletes clear message first
    try:
        await ctx.message.delete()
    except (discord.Forbidden, discord.HTTPException):
        logger.info("Could not delete clear command message; continuing")

    if amount <= 0:
        await ctx.send("Amount must be a positive integer.")
        return

    if amount > 100:
        await ctx.send("Please limit clear to at most 100 messages at a time.")
        return

    try:
        deleted = await ctx.channel.purge(limit=amount)
    except (discord.Forbidden, discord.HTTPException) as e:
        logger.error("Failed to purge messages: %s", e)
        await ctx.send("Failed to clear messages; check permissions.")
        return

    try:
        await ctx.send(f"Successfully cleared {len(deleted)} messages.")
    except (discord.Forbidden, discord.HTTPException):
        logger.info("Could not send confirmation message after clearing messages")

@bot.command()
async def remind(ctx, time_str: str, *, reminder_text: str):
    try:
        await ctx.message.delete()
    except (discord.Forbidden, discord.HTTPException):
        logger.info("Could not delete remind command message; continuing")

    time_string = time_str.lower().strip()

    pattern = r"(\d+)([a-zA-Z])"
    matches = re.findall(pattern, time_string)

    unit_multipliers = {
        'h': 3600,
        'm': 60,
        's': 1
    }

    total_seconds = 0
    for value, unit in matches:
        try:
            val_int = int(value)
        except ValueError:
            continue
        total_seconds += val_int * unit_multipliers.get(unit.lower(), 0)

    if total_seconds <= 0:
        await ctx.send("Couldn't parse the time string. Use formats like '10m', '2h', '30s'.")
        return

    max_seconds = 7 * 24 * 3600  # 7 days
    if total_seconds > max_seconds:
        await ctx.send("Reminders are limited to 7 days maximum.")
        return

    try:
        await ctx.author.send(f"I set a reminder for {time_str} to {reminder_text}.")
    except discord.Forbidden:
        await ctx.send(f"{ctx.author.mention}, I tried to DM you about your reminder but your privacy settings blocked me... {reminder_text}")

    await asyncio.sleep(total_seconds)

    try:
        await ctx.author.send(f"**Reminder:** {reminder_text}")
    except discord.Forbidden:
        await ctx.send(f"{ctx.author.mention}, I tried to DM your reminder but your privacy settings blocked me... {reminder_text}")

@bot.command()
async def testjoin(ctx):
    fake_new_member = ctx.author
    # dispatch the member join event; if author is not a Member this may not fully mimic a real join
    bot.dispatch("member_join", fake_new_member)

    try:
        await ctx.send("Simulating a new member joining...")
    except (discord.Forbidden, discord.HTTPException):
        logger.info("Could not send testjoin confirmation message")

TOKEN = os.getenv('DISCORD_TOKEN')

if TOKEN is None:
    logger.error("DISCORD_TOKEN not found in environment variables. Check your .env file.")
    raise ValueError("DISCORD_TOKEN not found in environment variables. Check your .env file.")

try:
    bot.run(TOKEN)
except Exception as e:
    logger.exception("Bot failed to start: %s", e)