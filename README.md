# Task bot for Discord (Beta) 🤖

This bot made in Python is ideal for those who manage communities on Discord and use a reward system.

The main objective of this bot is to create a channel and a specific role with instructions to carry out 
a certain task of any scope.

# How to use this bot

First we need to create a bot on the [Discord developer site](https://discord.com/developers/applications). 
We need administrator permissions for this bot given the nature of the tasks it performs. 

All the detailed steps to create your bot can be followed in the [documentation for discord.py](https://discordpy.readthedocs.io/en/stable/discord.html).

When you have your bot created and invited it as well to your Discord server, you need to take notes of the [following developer IDs](https://www.remote.tools/remote-work/how-to-find-discord-id)
in order to give your bot the proper instructions:

`required_role_id`: Administrative role ID for this bot.

`catogory_id`: Category ID where new channels will be created by the bot

`file_category_id` : Category ID where finished tasks (channels) will be sent. Think on this like a "File" or "Folder".

`YOUR_BOT_TOKEN`: With the token you got From Discord developer site. It will look similar to this one `MTHer23sAat2.GEa2Kc.nq8hbnz53Lvk7rLQlpM1NX9XN7i09_WH4OKPfo`

# Commands

## Creating a task
`/new_task` `parameters`
Through a command issued by users with certain role [required_role_id], users who have access to channels 
created in a certain category [category_id]. This command will create a new channel where users with access to 
that specific [category_id] will be able to upload a screen capture confirming their participation in the activity
receiving automatically the role created by the bot with the channel name.

### Usage example
`/new_task` `"Twitter"` `"https://twitter.com/dexkit"` `"Follow DexKit on Twitter"` `0.05` `8`

### Morphology
`/new_task`: command

`"Twitter"`: Name of the task. String parameter. Remember the "" if you are including spaces.

`"https://twitter.com/dexkit"`: URL with the task. String parameter. Use "" as well.

`"Follow DexKit on Twitter"`: This will be the task description. String value.

`0.05`: amount in dollars. Float parameter.

`8`: How long this task will remain open in hours. Float parameter with asyncio and datetime libraries to keep the 
chronometer functionality working.

## Closing a task
`/close_task` `parameters`
This command will close the named task sending it to [file_category_id] away from everyone. Only users with
authorization will be able to see that channel. This command will also delete the role created for that specific
task.

### Usage example
`/close_task` `"Twitter"`

### Morphology
`/close_task`: command

`"Twitter`: "Twitter": Name of the task. String parameter. Remember the "" if you are including spaces.

# Better practices & some features
– You can use the commands in a private channel

– Chronometer works as intended. It will be sending messages each 10 minutes on each task remembering users to do the task.

# Known bugs or missing features
– Must be always online while tasks are open because it won't recognize the channels if the bot is turned off.

– The creation for a persistent database is pending. This for keeping external registry about community tasks.

– Discord native commands aren't enabled in this version, so all the the commands should be sent in a complete sentence.


Please feel free to contribute with this open source idea.


