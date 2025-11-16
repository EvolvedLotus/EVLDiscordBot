from datetime import datetime
import discord
from discord import Embed
from core.data_manager import DataManager

class GuildInitializer:
    """Ensures all stored data has corresponding Discord elements"""

    def __init__(self, bot, data_manager: DataManager):
        self.bot = bot
        self.data_manager = data_manager

    async def initialize_guild(self, guild: discord.Guild):
        """Run full initialization check for a guild"""
        print(f"🔄 Initializing guild: {guild.name} (ID: {guild.id})")

        # Step 1: Ensure config exists
        await self._ensure_config(guild)

        # Step 2: Initialize task system
        await self._initialize_tasks(guild)

        # Step 3: Initialize currency/shop system
        await self._initialize_currency(guild)

        # Step 4: Initialize embed system
        await self._initialize_embeds(guild)

        # Step 5: Validate user data integrity
        await self._validate_user_data(guild)

        # Step 5: Clean up orphaned data
        await self._cleanup_orphaned_data(guild)

        print(f"✅ Guild {guild.name} initialization complete")

    async def _ensure_config(self, guild: discord.Guild):
        """Ensure guild config exists with valid settings"""
        config = self.data_manager.load_guild_data(guild.id, "config")

        # Check if config needs initialization
        needs_save = False

        if not config.get("server_name") or config["server_name"] != guild.name:
            config["server_name"] = guild.name
            needs_save = True

        if not config.get("member_count") or config["member_count"] != guild.member_count:
            config["member_count"] = guild.member_count
            needs_save = True

        if guild.icon:
            icon_url = guild.icon.url
            if config.get("icon_url") != icon_url:
                config["icon_url"] = icon_url
                needs_save = True

        if needs_save:
            self.data_manager.save_guild_data(guild.id, "config", config)
            print(f"  ✓ Updated config for {guild.name}")

    async def _initialize_tasks(self, guild: discord.Guild):
        """Ensure all tasks in data have Discord messages"""
        config = self.data_manager.load_guild_data(guild.id, "config")
        tasks_data = self.data_manager.load_guild_data(guild.id, "tasks")

        # Get or create task channel
        task_channel_id = config.get("task_channel_id")
        task_channel = None

        if task_channel_id:
            task_channel = guild.get_channel(int(task_channel_id))

        # If no channel or channel deleted, find/create one
        if not task_channel:
            # Look for existing channel named "tasks" or "task-board"
            task_channel = discord.utils.get(guild.text_channels, name="tasks")

            if not task_channel:
                task_channel = discord.utils.get(guild.text_channels, name="task-board")

            # Create if still not found
            if not task_channel:
                try:
                    task_channel = await guild.create_text_channel(
                        "tasks",
                        topic="📋 Complete tasks to earn rewards!",
                        reason="Auto-created by economy bot"
                    )
                    print(f"  ✓ Created #tasks channel in {guild.name}")
                except discord.Forbidden:
                    print(f"  ⚠️ No permission to create task channel in {guild.name}")
                    return

            # Save channel ID to config
            config["task_channel_id"] = task_channel.id
            self.data_manager.save_guild_data(guild.id, "config", config)

        # Now sync all tasks
        tasks = tasks_data.get("tasks", {})
        updated = False

        for task_id, task_data in tasks.items():
            message_id = task_data.get("message_id")

            # Check if message exists
            message_exists = False
            if message_id:
                try:
                    await task_channel.fetch_message(int(message_id))
                    message_exists = True
                except (discord.NotFound, discord.HTTPException):
                    message_exists = False

            # Create message if doesn't exist
            if not message_exists:
                embed = self._create_task_embed(task_data)
                try:
                    message = await task_channel.send(embed=embed)
                    task_data["message_id"] = str(message.id)
                    task_data["channel_id"] = str(task_channel.id)
                    updated = True
                    print(f"  ✓ Created Discord message for task: {task_data['name']}")
                except discord.Forbidden:
                    print(f"  ⚠️ No permission to send messages in {task_channel.name}")

        if updated:
            self.data_manager.save_guild_data(guild.id, "tasks", tasks_data)

    async def _initialize_currency(self, guild: discord.Guild):
        """Ensure all shop items in data have Discord messages"""
        config = self.data_manager.load_guild_data(guild.id, "config")
        currency_data = self.data_manager.load_guild_data(guild.id, "currency")

        # Get or create shop channel
        shop_channel_id = config.get("shop_channel_id")
        shop_channel = None

        if shop_channel_id:
            shop_channel = guild.get_channel(int(shop_channel_id))

        # If no channel or channel deleted, find/create one
        if not shop_channel:
            # Look for existing channel named "shop" or "store"
            shop_channel = discord.utils.get(guild.text_channels, name="shop")

            if not shop_channel:
                shop_channel = discord.utils.get(guild.text_channels, name="store")

            # Create if still not found
            if not shop_channel:
                try:
                    shop_channel = await guild.create_text_channel(
                        "shop",
                        topic="🛒 Purchase items with your earned coins!",
                        reason="Auto-created by economy bot"
                    )
                    print(f"  ✓ Created #shop channel in {guild.name}")
                except discord.Forbidden:
                    print(f"  ⚠️ No permission to create shop channel in {guild.name}")
                    return

            # Save channel ID to config
            config["shop_channel_id"] = shop_channel.id
            self.data_manager.save_guild_data(guild.id, "config", config)

        # Now sync all shop items
        shop_items = currency_data.get("shop_items", {})
        updated = False

        for item_id, item_data in shop_items.items():
            message_id = item_data.get("message_id")

            # Check if message exists
            message_exists = False
            if message_id:
                try:
                    await shop_channel.fetch_message(int(message_id))
                    message_exists = True
                except (discord.NotFound, discord.HTTPException):
                    message_exists = False

            # Create message if doesn't exist and item is active
            if not message_exists and item_data.get("is_active", True):
                embed = self._create_shop_item_embed(item_data, config)
                try:
                    message = await shop_channel.send(embed=embed)
                    item_data["message_id"] = str(message.id)
                    item_data["channel_id"] = str(shop_channel.id)
                    updated = True
                    print(f"  ✓ Created Discord message for shop item: {item_data['name']}")
                except discord.Forbidden:
                    print(f"  ⚠️ No permission to send messages in {shop_channel.name}")

        if updated:
            self.data_manager.save_guild_data(guild.id, "currency", currency_data)

    async def _initialize_embeds(self, guild: discord.Guild):
        """Initialize embed system for the guild"""
        # Load embeds data - this will create default structure if it doesn't exist
        embeds_data = self.data_manager.load_guild_data(guild.id, "embeds")

        # Ensure embeds.json exists with proper structure
        if not embeds_data.get("embeds"):
            embeds_data["embeds"] = {}
        if not embeds_data.get("templates"):
            embeds_data["templates"] = {
                'task_template': {
                    'color': '#3498db',
                    'footer_text': 'Task System',
                    'thumbnail_url': None
                },
                'announcement_template': {
                    'color': '#e74c3c',
                    'footer_text': 'Server Announcement'
                }
            }
        if not embeds_data.get("settings"):
            embeds_data["settings"] = {
                'default_color': '#7289da',
                'allow_user_embeds': False,
                'max_embeds_per_channel': 50
            }

        # Save to ensure file exists
        self.data_manager.save_guild_data(guild.id, "embeds", embeds_data)
        print(f"  ✓ Initialized embed system for {guild.name}")

    async def _validate_user_data(self, guild: discord.Guild):
        """Ensure all users in data still exist in guild"""
        currency_data = self.data_manager.load_guild_data(guild.id, "currency")
        users = currency_data.get("users", {})

        # Get current guild member IDs
        member_ids = {str(member.id) for member in guild.members}

        # Find users in data who left the guild
        orphaned_users = set(users.keys()) - member_ids

        if orphaned_users:
            print(f"  ℹ️ Found {len(orphaned_users)} users who left {guild.name}")
            # Don't delete - keep for if they rejoin
            # Just log for awareness

    async def _cleanup_orphaned_data(self, guild: discord.Guild):
        """Remove Discord messages for deleted data"""
        config = self.data_manager.load_guild_data(guild.id, "config")

        # Clean up task messages
        task_channel_id = config.get("task_channel_id")
        if task_channel_id:
            task_channel = guild.get_channel(int(task_channel_id))
            if task_channel:
                tasks_data = self.data_manager.load_guild_data(guild.id, "tasks")
                valid_message_ids = {
                    task.get("message_id")
                    for task in tasks_data.get("tasks", {}).values()
                    if task.get("message_id")
                }

                # Check messages in channel
                try:
                    async for message in task_channel.history(limit=100):
                        if message.author == self.bot.user:
                            if str(message.id) not in valid_message_ids:
                                await message.delete()
                                print(f"  🗑️ Deleted orphaned task message in {guild.name}")
                except discord.Forbidden:
                    pass  # No permission to read history

    def _create_task_embed(self, task_data: dict) -> Embed:
        """Create embed for task display"""
        embed = Embed(
            title=f"📋 {task_data['name']}",
            description=task_data.get('description', 'No description'),
            color=discord.Color.blue()
        )

        embed.add_field(name="Reward", value=f"💰 {task_data['reward']} coins", inline=True)

        duration = task_data.get('duration_hours', 24)
        embed.add_field(name="Time Limit", value=f"⏰ {duration} hours", inline=True)

        status = task_data.get('status', 'pending')
        status_emoji = {"pending": "🟡", "active": "🟢", "completed": "✅"}.get(status, "⚪")
        embed.add_field(name="Status", value=f"{status_emoji} {status.title()}", inline=True)

        embed.set_footer(text=f"Task ID: {task_data['id']} | Use /claim {task_data['id']} to start")

        return embed

    def _create_shop_item_embed(self, item_data: dict, config: dict) -> Embed:
        """Create embed for shop item display"""
        currency_symbol = config.get("currency_symbol", "🪙")

        embed = Embed(
            title=item_data['name'],
            description=item_data.get('description', 'No description'),
            color=discord.Color.green() if item_data.get('is_active', True) else discord.Color.grey()
        )

        embed.add_field(
            name="Price",
            value=f"{currency_symbol}{item_data['price']}",
            inline=True
        )

        stock = item_data.get('stock', -1)
        stock_text = "♾️ Unlimited" if stock == -1 else f"📦 {stock} available"
        embed.add_field(name="Stock", value=stock_text, inline=True)

        category = item_data.get('category', 'misc')
        embed.add_field(name="Category", value=f"🏷️ {category.title()}", inline=True)

        embed.set_footer(text="Use /buy <item_id> to purchase")

        return embed
