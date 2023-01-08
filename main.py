import discord
from discord.ext import commands
from datetime import datetime, timedelta
import asyncio

# Set prefix and start bot
bot = commands.Bot(command_prefix='/', intents=discord.Intents.all())

# Identifying clients
client = discord.Client(intents=discord.Intents.all())

# Required role ID to execute commands
required_role_id = 000000000000000000

# Category ID where channels will be created
category_id = 000000000000000000

# Category ID where channels will be sent to archive
file_category_id = 000000000000000000

# Dictionary that stores information about ongoing tasks
# The key is the name of the channel and the value is a tuple with the channel ID, the creation time, and the role name
tasks = {}

# New task command
@bot.command(name='new_task')
async def create_task(ctx, name: str, url: str, description: str, reward: float, time: float):
    # Is admin? Verify this to avoid impersonations
    if required_role_id not in [role.id for role in ctx.author.roles]:
        await ctx.send("Oops! ✋ You can't use me!🛑 You are not an admin")
        return

    # Get the category where channels will be created
    category = bot.get_channel(category_id)

    # Create the channel and give it a name
    channel = await category.create_text_channel(name=name)

    # Create a role with the same name as the channel and assign it permissions to send and view the channel
    role = await ctx.guild.create_role(name=name)
    await channel.set_permissions(role, send_messages=True, read_messages=True)

    # Calculate the expiration time for the task
    expiration_time = datetime.utcnow() + timedelta(hours=time)

    # Save the info in a dictionary
    tasks[name] = (channel.id, expiration_time, role.name)

    # Send a message to the channel with the task information
    await channel.send(
        f'Hey, @everyone! New task created! {name}\nURL: {url}\nDescription: {description}\nReward: {reward}$\nExpiration time: {expiration_time}')

    # Get the message above
    last_message = await channel.history(limit=1).flatten()

    # Pin this message
    await last_message[0].pin()

    # Start the countdown
    await countdown(channel, expiration_time)

async def countdown(channel, expiration_time):
    while True:
        # Calculate the time remaining
        time_remaining = expiration_time - datetime.utcnow()

        # Break the loop if the task has expired
        if time_remaining.total_seconds() <= 0:
            break

        # Format the time remaining and send it to the channel
        formatted_time = str(time_remaining).split('.')[0]
        await channel.send(f'Time remaining: {formatted_time}')

        # Wait 10 minutes before checking again
        await asyncio.sleep(600)

# Process user message
@bot.event
async def on_message(message):
    # Only process messages that are not from the bot itself and that contain an image attachment
    if message.author != bot.user and len(message.attachments) > 0 and message.attachments[0].height is not None:
        # Check if the channel where the message was sent is a task channel
        channel_id = message.channel.id
        for task in tasks.values():
            if channel_id == task[0]:
                # Assign the role to the user
                role = discord.utils.get(message.guild.roles, name=task[2])
                await message.author.add_roles(role)
                await message.channel.send(f'Capture uploaded, @{message.author.name}! Role {role.name} granted.')
                break
    await bot.process_commands(message)

# Close task function
@bot.command(name='close_task')
async def close_task(ctx, name: str):
    # Is admin? Verify this to avoid impersonations
    if required_role_id not in [role.id for role in ctx.author.roles]:
        await ctx.send("Oops! ✋ You can't use me!🛑 You are not an admin")
        return

    # Check if the task exists
    if name not in tasks:
        await ctx.send(f"Oops! ✋ Task '{name}' does not exist")
        return

    # Get the task info
    channel_id, _, role_name = tasks[name]

    # Get the channel and role objects
    channel = bot.get_channel(channel_id)
    role = discord.utils.get(ctx.guild.roles, name=role_name)

    # Remove the role from all users
    for member in ctx.guild.members:
        if role in member.roles:
            await member.remove_roles(role)

    # Delete the channel
    await channel.delete()

    # Delete the role
    await role.delete()

    # Remove the task from the tasks dictionary
    del tasks[name]

    await ctx.send(f'Task {name} closed and deleted successfully.')


bot.run("YOUR_DISCORD_BOT_TOKEN_HERE")
