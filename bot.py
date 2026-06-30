import os
import discord
import asyncio
import re
from discord.ext import commands
from dotenv import load_dotenv
from emoji import is_emoji

load_dotenv()

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix='!', intents=intents)

@bot.event
async def on_ready():
    print(f'We have logged in as {bot.user}')

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
        print("Error: WELCOME_CHANNEL_ID is missing from your .env file!")
        return
    
    channel_id = int(channel_id_str)

    channel = bot.get_channel(channel_id) or await bot.fetch_channel(channel_id)

    if isinstance(channel, discord.TextChannel):
        await channel.send(f"Welcome to the server, {member.mention}! I'm so glad you're here! I'd really appreciate it if you could help me.")

# run through this function to prevent users from voting on multiple options at once
@bot.event
async def on_raw_reaction_add(payload):
    # ignore bot's own reaction when it sets up the poll
    if bot.user is None or payload.user_id == bot.user.id:
        return
    
    # fetch channel and message where reaction happened
    channel = bot.get_channel(payload.channel_id) or await bot.fetch_channel(payload.channel_id)

    if isinstance(channel, discord.TextChannel):
        message = await channel.fetch_message(payload.message_id)

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
                            await message.remove_reaction(payload.emoji, user)
                            return

# poll command
@bot.command()
async def poll(ctx, *args):
    if len(args) < 2:
        await ctx.send("Usage: !poll \"Question\" \"Option 1\" \"Option 2\"")
        return

    await ctx.message.delete()

    question_text = args[0].strip()
    poll_options = args[1:]

    default_numbers = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]

    final_body_lines = []
    reactions_to_add = []

    for index, option in enumerate(poll_options):
        cleaned_option = option.strip()
        first_char = cleaned_option[0]

        if is_emoji(first_char):
            final_body_lines.append(cleaned_option)
            reactions_to_add.append(first_char)
        else:
            number_emoji = default_numbers[index % len(default_numbers)]
            final_body_lines.append(f"{number_emoji} {cleaned_option}")
            reactions_to_add.append(number_emoji)

    poll_body = f"📊 **{question_text}**\n" + "\n".join(final_body_lines)
    message = await ctx.send(poll_body)

    for emoji in reactions_to_add:
        await message.add_reaction(emoji)

# clear command
@bot.command()
@commands.has_permissions(manage_messages=True)
async def clear(ctx, amount: int):
    # deletes clear message first
    await ctx.message.delete()

    # deletes specified number of past messages
    deleted = await ctx.channel.purge(limit=amount)

    # inform of message deletion
    await ctx.send(f"Successfully cleared {len(deleted)} messages.")

@bot.command()
async def remind(ctx, time_str: str, *, reminder_text: str):
    await ctx.message.delete()
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
        val_int = int(value)
        total_seconds += val_int * unit_multipliers.get(unit.lower(), 0)

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
    bot.dispatch("member_join", fake_new_member)

    await ctx.send("Simulating a new member joining...")

TOKEN = os.getenv('DISCORD_TOKEN')

if TOKEN is None:
    raise ValueError("Error: DISCORD_TOKEN not found in environment variables. Check your .env file.")

bot.run(TOKEN)