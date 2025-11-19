"""
Currency cog with per-guild data isolation
"""

import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timedelta, timezone
import logging
from typing import List
from core import data_manager
from core.permissions import feature_enabled, is_moderator
from core.utils import format_currency, create_embed, add_embed_footer
from core.transaction_manager import TransactionManager
from core.shop_manager import ShopManager

class Currency(commands.Cog):
    """Currency system with server-specific economies"""

    def __init__(self, bot):
        self.bot = bot
        # Store managers with fallback to ensure they're available
        self.data_manager = getattr(bot, 'data_manager', None)
        self.transaction_manager = getattr(bot, 'transaction_manager', None)
        self.shop_manager = getattr(bot, 'shop_manager', None)

        # Log initialization status
        import logging
        logger = logging.getLogger(__name__)
        if self.data_manager:
            logger.info("Currency cog initialized with data_manager")
        else:
            logger.warning("Currency cog initialized without data_manager - will use fallback")

    def _get_currency_symbol(self, guild_id: int) -> str:
        """Get currency symbol for this guild"""
        config = self.data_manager.load_guild_data(guild_id, "config")
        return config.get("currency_symbol", "$")

    def _initialize_user(self, data: dict, user_id_str: str):
        """Initialize a new user in the currency data"""
        if user_id_str not in data["users"]:
            data["users"][user_id_str] = {
                "balance": 0,
                "total_earned": 0,
                "total_spent": 0,
                "last_daily": None,
                "created_at": datetime.now().isoformat()
            }

    def _get_balance(self, guild_id: int, user_id: int) -> int:
        """Get user balance in specific guild"""
        data = self.data_manager.load_guild_data(guild_id, "currency")
        user_id_str = str(user_id)

        if user_id_str not in data["users"]:
            # Initialize new user
            self._initialize_user(data, user_id_str)
            self.data_manager.save_guild_data(guild_id, "currency", data)
            return 0

        return data["users"][user_id_str]["balance"]

    def _add_balance(self, guild_id: int, user_id: int, amount: int, description: str, transaction_type: str = 'earn', metadata: dict = None):
        """
        UPDATED: Two-phase commit implementation for balance updates and transaction logging.
        Transaction Log is considered the source of truth for history.
        If transaction logging fails, the entire operation (balance change) must fail and rollback.

        Phase 1 (Prepare): Validate and prepare transaction data
        Phase 2 (Commit): Log transaction first, then update balance
        Phase 3 (Rollback): If transaction logging fails, rollback any partial changes
        """
        import os
        import tempfile
        import json

        logger = logging.getLogger(__name__)

        try:
            # PHASE 1: Prepare - Load data and validate
            data = self.data_manager.load_guild_data(guild_id, "currency")
            if not data:
                return False

            user_id_str = str(user_id)

            # Initialize user if needed
            if user_id_str not in data["users"]:
                self._initialize_user(data, user_id_str)

            user = data["users"][user_id_str]
            balance_before = user["balance"]
            balance_after = balance_before + amount

            # Prevent negative balances
            if balance_after < 0:
                return False

            # Create transaction data for logging (Phase 1 prepare)
            transaction_data = {
                'guild_id': guild_id,
                'user_id': user_id,
                'amount': amount,
                'balance_before': balance_before,
                'balance_after': balance_after,
                'transaction_type': transaction_type,
                'description': description,
                'metadata': metadata or {}
            }

            # PHASE 2: Commit - Log transaction FIRST (source of truth)
            try:
                transaction_id = self.transaction_manager.log_transaction(**transaction_data)
                if not transaction_id:
                    logger.error(f"Transaction logging returned invalid ID for user {user_id} in guild {guild_id}")
                    return False
            except Exception as e:
                logger.critical(f"CRITICAL: Transaction logging failed for user {user_id} in guild {guild_id}: {e}")
                # Transaction log is source of truth - if it fails, entire operation fails
                return False

            # PHASE 3: Apply balance changes only after successful transaction logging
            try:
                # Update balance and totals
                user["balance"] = balance_after
                if amount > 0:
                    user["total_earned"] = user.get("total_earned", 0) + amount
                else:
                    user["total_spent"] = user.get("total_spent", 0) + abs(amount)

                # Recalculate total currency
                data["metadata"]["total_currency"] = sum(u["balance"] for u in data["users"].values())

                # Save currency data
                if not self.data_manager.save_guild_data(guild_id, "currency", data):
                    logger.critical(f"CRITICAL: Failed to save currency data after successful transaction log for user {user_id} in guild {guild_id}")
                    # This is a critical inconsistency - transaction was logged but balance not updated
                    # In a production system, this would require manual reconciliation
                    return False

                # Broadcast cache invalidation signal
                self._broadcast_cache_invalidation(guild_id, 'currency', user_id)

                return balance_after

            except Exception as e:
                logger.critical(f"CRITICAL: Failed to update balance after successful transaction log for user {user_id} in guild {guild_id}: {e}")
                # Transaction was logged but balance update failed - critical inconsistency
                # In production, this would trigger an alert for manual reconciliation
                return False

        except Exception as e:
            logger.error(f"Error in two-phase balance update for user {user_id} in guild {guild_id}: {e}")
            return False

    def _broadcast_cache_invalidation(self, guild_id: int, data_type: str, user_id: int = None):
        """
        Broadcast cache invalidation signal to all running instances.
        This implements the pub/sub mechanism for cache clearing.
        """
        try:
            # Import here to avoid circular imports
            from core.cache_manager import CacheManager

            # Get cache manager instance
            cache_manager = CacheManager.get_instance()

            # Broadcast invalidation signal
            cache_manager.invalidate_cache(guild_id, data_type, user_id)

        except ImportError:
            # Fallback if CacheManager not available
            logger = logging.getLogger(__name__)
            logger.warning("CacheManager not available for cache invalidation broadcast")
        except Exception as e:
            logger = logging.getLogger(__name__)
            logger.error(f"Error broadcasting cache invalidation: {e}")


    @app_commands.command(name='balance', description='Check your balance')
    @app_commands.guild_only()
    async def balance(self, interaction: discord.Interaction, user: discord.Member = None):
        """Check balance with recent transaction summary"""
        # Defer immediately for database operations
        await interaction.response.defer(ephemeral=True)

        target = user or interaction.user
        guild_id = interaction.guild.id

        try:
            # Ensure user exists FIRST
            self.data_manager.ensure_user_exists(guild_id, target.id)

            # Then load their data
            user_data = self.data_manager.load_user_data(guild_id, target.id)

            balance = user_data.get('balance', 0)
            symbol = self._get_currency_symbol(guild_id)

            embed = create_embed(
                title=f"💰 {target.display_name}'s Balance",
                description=f"{symbol}{balance:,}",
                color=0x2ecc71
            )

            # Get last 5 transactions via transaction_manager
            try:
                recent_txns = self.transaction_manager.get_transactions(
                    guild_id=guild_id,
                    user_id=target.id,
                    limit=5
                )['transactions']

                if recent_txns:
                    embed.add_field(
                        name="Recent Activity",
                        value="\n".join([
                            f"{'+' if txn['amount'] > 0 else ''}{symbol}{txn['amount']} - {txn['description'][:30]}{'...' if len(txn['description']) > 30 else ''}"
                            for txn in recent_txns
                        ]),
                        inline=False
                    )
            except Exception as e:
                logger = logging.getLogger(__name__)
                logger.error(f"Failed to load recent transactions for balance display: {e}")

            embed.set_footer(text=f"Server: {interaction.guild.name}")

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logger = logging.getLogger(__name__)
            logger.error(f"Error in balance command: {e}")
            # Check if already responded
            if interaction.response.is_done():
                await interaction.followup.send(
                    "❌ An error occurred while checking your balance.",
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    "❌ An error occurred while checking your balance.",
                    ephemeral=True
                )

    @app_commands.command(name="daily", description="Claim your daily reward of 100 coins")
    @app_commands.guild_only()
    async def daily(self, interaction: discord.Interaction):
        """Claim daily reward (per-server) with UTC timezone handling"""
        guild_id = interaction.guild.id
        user_id = interaction.user.id
        user_id_str = str(user_id)

        try:
            # Ensure user exists FIRST
            self.data_manager.ensure_user_exists(guild_id, user_id)

            # Load data once
            data = self.data_manager.load_guild_data(guild_id, "currency")

        except Exception as e:
            logger = logging.getLogger(__name__)
            logger.error(f"Error in daily command setup: {e}")
            await interaction.response.send_message("❌ An error occurred while setting up daily reward!", ephemeral=True)
            return

        last_daily = data["users"][user_id_str].get("last_daily")
        now_utc = datetime.now(timezone.utc)  # Use UTC timezone

        # Check cooldown BEFORE any balance operations with robust UTC handling
        if last_daily:
            try:
                # Parse with timezone awareness - handle multiple formats robustly
                if isinstance(last_daily, str):
                    # Handle various ISO format variations
                    if last_daily.endswith('Z'):
                        last_time = datetime.fromisoformat(last_daily.replace('Z', '+00:00'))
                    elif '+' in last_daily or last_daily.endswith(('UTC', 'GMT')):
                        # Handle timezone-aware strings
                        last_time = datetime.fromisoformat(last_daily.replace('UTC', '+00:00').replace('GMT', '+00:00'))
                    else:
                        # Assume naive datetime is UTC
                        last_time = datetime.fromisoformat(last_daily)
                        if last_time.tzinfo is None:
                            last_time = last_time.replace(tzinfo=timezone.utc)
                elif isinstance(last_daily, datetime):
                    # Handle datetime objects
                    if last_daily.tzinfo is None:
                        last_time = last_daily.replace(tzinfo=timezone.utc)
                    else:
                        last_time = last_daily.astimezone(timezone.utc)
                else:
                    # Invalid format, reset
                    logger.warning(f"Invalid last_daily type for user {user_id}: {type(last_daily)}, resetting")
                    last_daily = None
                    last_time = None

                if last_time:
                    # Ensure both times are UTC for accurate comparison
                    if last_time.tzinfo is None:
                        last_time = last_time.replace(tzinfo=timezone.utc)

                    # Calculate time difference in seconds
                    time_diff = (now_utc - last_time).total_seconds()

                    if time_diff < 86400:  # 24 hours in seconds
                        next_daily = last_time + timedelta(days=1)
                        remaining = next_daily - now_utc

                        # Handle negative remaining time (DST edge cases)
                        if remaining.total_seconds() <= 0:
                            # Reset if somehow in the past (DST or clock issues)
                            last_daily = None
                            data["users"][user_id_str]["last_daily"] = None
                            self.data_manager.save_guild_data(guild_id, "currency", data)
                        else:
                            hours = int(remaining.total_seconds() // 3600)
                            minutes = int((remaining.total_seconds() % 3600) // 60)

                            await interaction.response.send_message(
                                f"❌ Already claimed! Next daily in {hours}h {minutes}m",
                                ephemeral=True
                            )
                            return
            except (ValueError, TypeError, AttributeError) as e:
                logger.warning(f"Invalid last_daily format for user {user_id}: {last_daily} ({type(last_daily)}), resetting: {e}")
                # Reset invalid timestamp
                last_daily = None

        # Update last_daily timestamp BEFORE adding balance to prevent race conditions
        # Store in ISO format with Z suffix for UTC
        data["users"][user_id_str]["last_daily"] = now_utc.isoformat().replace('+00:00', 'Z')

        # Save timestamp update first
        if not self.data_manager.save_guild_data(guild_id, "currency", data):
            await interaction.response.send_message("❌ Failed to update daily cooldown!", ephemeral=True)
            return

        # Now add balance with atomic transaction
        reward = 100
        date_str = now_utc.strftime('%Y-%m-%d')
        idempotency_key = f"daily_{guild_id}_{user_id}_{date_str}"

        result = self._add_balance(guild_id, user_id, reward, "Daily reward", transaction_type='daily',
                                  metadata={"source": "discord_command", "command": "/daily", "idempotency_key": idempotency_key})

        if result is False:
            # Rollback timestamp if balance addition failed
            if last_daily:
                data["users"][user_id_str]["last_daily"] = last_daily
            else:
                data["users"][user_id_str].pop("last_daily", None)
            self.data_manager.save_guild_data(guild_id, "currency", data)
            await interaction.response.send_message("❌ Failed to claim daily reward!", ephemeral=True)
            return

        symbol = self._get_currency_symbol(guild_id)
        await interaction.response.send_message(f"🎉 Daily reward claimed! +{symbol}{reward}", ephemeral=True)

    @app_commands.command(name="leaderboard", description="Show the top 10 richest users in this server")
    @app_commands.guild_only()
    async def leaderboard(self, interaction: discord.Interaction):
        """Show richest users in THIS server"""
        guild_id = interaction.guild.id
        data = self.data_manager.load_guild_data(guild_id, "currency")

        # Sort users by balance
        sorted_users = sorted(
            data["users"].items(),
            key=lambda x: x[1]["balance"],
            reverse=True
        )[:10]

        if not sorted_users:
            await interaction.response.send_message("❌ No users found!", ephemeral=True)
            return

        symbol = self._get_currency_symbol(guild_id)
        embed = create_embed(
            title=f"💰 {interaction.guild.name} - Top 10 Richest",
            color=0xf1c40f
        )

        description = ""
        for i, (user_id, user_data) in enumerate(sorted_users, 1):
            try:
                user = await self.bot.fetch_user(int(user_id))
                name = user.name
            except:
                name = f"User {user_id}"

            balance = user_data["balance"]
            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
            description += f"{medal} **{name}** - {symbol}{balance:,}\n"

        embed.description = description
        embed.set_footer(text=f"Your balance: {symbol}{self._get_balance(guild_id, interaction.user.id):,}")

        # Leaderboard is non-ephemeral for visibility
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="give", description="Give currency to another user")
    @app_commands.guild_only()
    async def give_money(self, interaction: discord.Interaction, user: discord.Member, amount: int):
        """Give money to another user in this server"""
        # Defer immediately for database operations
        await interaction.response.defer(ephemeral=True)

        try:
            # Early validation checks
            if amount <= 0:
                await interaction.followup.send("❌ Amount must be positive!", ephemeral=True)
                return

            if user == interaction.user:
                await interaction.followup.send("❌ You cannot give money to yourself!", ephemeral=True)
                return

            if user.bot:
                await interaction.followup.send("❌ You cannot give money to bots!", ephemeral=True)
                return

            guild_id = interaction.guild.id

            # Ensure both users exist FIRST
            self.data_manager.ensure_user_exists(guild_id, interaction.user.id)
            self.data_manager.ensure_user_exists(guild_id, user.id)

            sender_balance = self._get_balance(guild_id, interaction.user.id)

            if sender_balance < amount:
                symbol = self._get_currency_symbol(guild_id)
                await interaction.followup.send(
                    f"❌ Insufficient funds! You have {symbol}{sender_balance:,} but need {symbol}{amount:,}",
                    ephemeral=True
                )
                return

            # Deduct from sender
            sender_result = self._add_balance(guild_id, interaction.user.id, -amount, f"Gave to {user.name}",
                                             transaction_type='transfer_send',
                                             metadata={"source": "discord_command", "command": "/give", "recipient_id": str(user.id)})

            # Add to receiver
            receiver_result = self._add_balance(guild_id, user.id, amount, f"Received from {interaction.user.name}",
                                               transaction_type='transfer_receive',
                                               metadata={"source": "discord_command", "command": "/give", "sender_id": str(interaction.user.id)})

            if sender_result is False or receiver_result is False:
                await interaction.followup.send("❌ Transfer failed!", ephemeral=True)
                return

            symbol = self._get_currency_symbol(guild_id)
            await interaction.followup.send(
                f"✅ {interaction.user.mention} gave {symbol}{amount:,} to {user.mention}!",
                ephemeral=True
            )

        except Exception as e:
            logger = logging.getLogger(__name__)
            logger.error(f"Error in give_money command: {e}")
            await interaction.followup.send("❌ An error occurred during the transfer.", ephemeral=True)

    def _add_to_inventory(self, guild_id: int, user_id: int, item_id: str, quantity: int):
        """Add items to user inventory"""
        data = self.data_manager.load_guild_data(guild_id, "currency")
        user_id_str = str(user_id)

        # Initialize inventory structure
        data.setdefault('inventory', {})
        data['inventory'].setdefault(user_id_str, {})
        data['inventory'][user_id_str][item_id] = \
            data['inventory'][user_id_str].get(item_id, 0) + quantity

        self.data_manager.save_guild_data(guild_id, "currency", data)

    @app_commands.command(name="shop", description="Display shop items in paginated embed")
    @app_commands.guild_only()
    async def shop(self, interaction: discord.Interaction, category: str = None):
        """Display shop items in paginated embed"""
        guild_id = interaction.guild.id

        # Get shop items
        items = self.shop_manager.get_shop_items(guild_id, category=category, active_only=True, include_out_of_stock=False)

        if not items:
            await interaction.response.send_message("No items available in the shop!", ephemeral=True)
            return

        # Create embed
        symbol = self._get_currency_symbol(guild_id)
        embed = discord.Embed(
            title="🏪 Shop",
            description=f"Available items{f' in {category}' if category else ''}",
            color=discord.Color.blue()
        )

        embed.add_field(
            name="Your Balance",
            value=f"{symbol}{self._get_balance(guild_id, interaction.user.id):,}",
            inline=False
        )

        # Show first 5 items
        item_list = list(items.values())[:5]
        for item in item_list:
            # Handle missing emoji field gracefully
            emoji = item.get('emoji', '🛍️')  # Default to shopping bag emoji
            stock_text = "♾️ Unlimited" if item['stock'] == -1 else f"📦 {item['stock']} available"
            embed.add_field(
                name=f"{emoji} {item['name']} - {symbol}{item['price']}",
                value=f"{item['description'][:100]}{'...' if len(item['description']) > 100 else ''}\n{stock_text}\nID: `{list(items.keys())[list(items.values()).index(item)]}`",
                inline=False
            )

        if len(items) > 5:
            embed.set_footer(text=f"Showing 1-5 of {len(items)} items")

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="inventory", description="Display user inventory in paginated embed")
    @app_commands.describe(user="View another user's inventory (optional)")
    @app_commands.guild_only()
    async def inventory(self, interaction: discord.Interaction, user: discord.Member = None):
        """Display user inventory in paginated embed"""
        target = user or interaction.user
        guild_id = interaction.guild.id

        # Get inventory with item details
        inventory = self.shop_manager.get_inventory(guild_id, target.id, include_item_details=True)

        if not inventory:
            await interaction.response.send_message(f"{target.display_name}'s inventory is empty!", ephemeral=True)
            return

        # Calculate total value
        total_value = sum(data['quantity'] * data['item']['price'] for data in inventory.values())
        symbol = self._get_currency_symbol(guild_id)

        embed = discord.Embed(
            title=f"🎒 {target.display_name}'s Inventory",
            description=f"Total value: {symbol}{total_value:,}",
            color=discord.Color.blue()
        )

        # Group by category
        categories = {}
        for item_id, data in inventory.items():
            category = data['item'].get('category', 'general')
            if category not in categories:
                categories[category] = []
            categories[category].append(data)

        # Show items by category (limit to avoid embed size limits)
        for category, items in list(categories.items())[:3]:  # Max 3 categories
            item_lines = []
            for data in items[:5]:  # Max 5 items per category
                # Handle missing emoji field gracefully
                emoji = data['item'].get('emoji', '🛍️')  # Default to shopping bag emoji
                item_lines.append(f"{emoji} {data['item']['name']} (x{data['quantity']}) - {symbol}{data['quantity'] * data['item']['price']}")

            if item_lines:
                embed.add_field(
                    name=f"{category.title()} Items",
                    value="\n".join(item_lines),
                    inline=False
                )

        embed.set_footer(text=f"Total items: {sum(data['quantity'] for data in inventory.values())}")

        await interaction.response.send_message(embed=embed, ephemeral=True)



    @app_commands.command(name="buy", description="Purchase item with confirmation")
    @app_commands.describe(
        item="The item to purchase",
        quantity="How many to buy (default: 1)"
    )
    @app_commands.guild_only()
    async def buy(self, interaction: discord.Interaction, item: str, quantity: int = 1):
        """Purchase item with confirmation"""
        guild_id = interaction.guild.id
        user_id = interaction.user.id

        # Show confirmation embed
        item_data = self.shop_manager.get_item(guild_id, item)
        if not item_data:
            await interaction.response.send_message("❌ Item not found!", ephemeral=True)
            return

        total_cost = item_data['price'] * quantity
        symbol = self._get_currency_symbol(guild_id)
        current_balance = self._get_balance(guild_id, user_id)

        # Handle missing emoji field gracefully
        emoji = item_data.get('emoji', '🛍️')  # Default to shopping bag emoji
        embed = discord.Embed(
            title="Confirm Purchase",
            description=f"**{emoji} {item_data['name']}**\n{item_data['description']}",
            color=discord.Color.blue()
        )
        embed.add_field(name="Quantity", value=str(quantity), inline=True)
        embed.add_field(name="Total Cost", value=f"{symbol}{total_cost}", inline=True)
        embed.add_field(name="Your Balance", value=f"{symbol}{current_balance}", inline=True)
        embed.add_field(name="After Purchase", value=f"{symbol}{current_balance - total_cost}", inline=True)

        # Create confirmation buttons
        view = PurchaseConfirmView(self.shop_manager, item, quantity, total_cost, symbol)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @buy.autocomplete('item')
    async def buy_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        """Autocomplete shop items (active only)"""
        items = self.shop_manager.get_shop_items(
            interaction.guild.id,
            active_only=True,
            include_out_of_stock=False
        )
        choices = []
        for item_id, item in items.items():
            if current.lower() in item['name'].lower():
                # Handle missing emoji field gracefully
                emoji = item.get('emoji', '🛍️')  # Default to shopping bag emoji
                choices.append(app_commands.Choice(
                    name=f"{emoji} {item['name']} - {item['price']}💰",
                    value=item_id
                ))
        return choices[:25]  # Discord limit



    @app_commands.command(name="view_tasks", description="View available tasks")
    @app_commands.guild_only()
    async def view_tasks(self, interaction: discord.Interaction):
        guild_id = str(interaction.guild.id)
        channel_id = str(interaction.channel.id)
        user_id = str(interaction.user.id)

        # Load task data
        task_data = self.data_manager.load_guild_data(guild_id, "tasks")
        tasks = task_data.get("tasks", {})
        user_tasks = task_data.get("user_tasks", {}).get(user_id, {})

        # Get config for global setting
        config = self.data_manager.load_guild_data(guild_id, "config")
        global_tasks = config.get("global_tasks", False)

        # Filter by channel unless global
        if not global_tasks:
            tasks = {k: v for k, v in tasks.items()
                     if v.get("channel_id") == channel_id and v.get("status") == "pending"}
        else:
            tasks = {k: v for k, v in tasks.items() if v.get("status") == "pending"}

        if not tasks:
            await interaction.response.send_message("No tasks available in this channel.", ephemeral=True)
            return

        # Create embed
        embed = discord.Embed(
            title="📋 Available Tasks",
            description="Claim a task to get started!",
            color=discord.Color.green()
        )

        for task_id, task in tasks.items():
            claimed = task_id in user_tasks
            status_emoji = "✅" if claimed else "⏳"
            embed.add_field(
                name=f"{status_emoji} {task['name']} - {task['reward']} {config.get('currency_symbol', '$')}",
                value=f"{task.get('description', 'No description')}\nDuration: {task.get('duration_hours', 24)}h\nID: `{task_id}`",
                inline=False
            )

        await interaction.response.send_message(embed=embed, ephemeral=False)

    @app_commands.command(name='claim', description='Claim a task')
    @app_commands.guild_only()
    async def claim_task(self, interaction: discord.Interaction, task_id: str):
        """Claim a task"""
        guild_id = interaction.guild.id
        user_id = interaction.user.id
        channel_id = str(interaction.channel.id)

        tasks_data = self.data_manager.load_guild_data(guild_id, "tasks")
        tasks = tasks_data.get('tasks', {})

        if task_id not in tasks:
            await interaction.response.send_message(f"❌ Task '{task_id}' not found!", ephemeral=True)
            return

        task = tasks[task_id]

        if task.get('status') != 'pending':
            await interaction.response.send_message("❌ This task is no longer available!", ephemeral=True)
            return

        # Check channel filtering unless global
        config = self.data_manager.load_guild_data(guild_id, "config")
        global_tasks = config.get("global_tasks", False)
        if not global_tasks and task.get("channel_id") != channel_id:
            await interaction.response.send_message("❌ This task is not available in this channel!", ephemeral=True)
            return

        # Check if user already has this task
        user_id_str = str(user_id)
        tasks_data.setdefault('user_tasks', {})
        user_tasks = tasks_data['user_tasks'].get(user_id_str, {})

        if task_id in user_tasks:
            await interaction.response.send_message("❌ You've already claimed this task!", ephemeral=True)
            return

        # Claim task
        now = datetime.now()
        deadline = now + timedelta(hours=task.get('duration_hours', 24))

        tasks_data['user_tasks'].setdefault(user_id_str, {})[task_id] = {
            'claimed_at': now.isoformat(),
            'deadline': deadline.isoformat(),
            'status': 'in_progress'
        }

        self.data_manager.save_guild_data(guild_id, "tasks", tasks_data)

        config = self.data_manager.load_guild_data(guild_id, "config")
        symbol = config.get('currency_symbol', '$')

        embed = discord.Embed(
            title="Task Claimed!",
            description=f"You've claimed: **{task['name']}**",
            color=discord.Color.green()
        )
        embed.add_field(name="Reward", value=f"{symbol}{task['reward']}")
        embed.add_field(name="Deadline", value=f"<t:{int(deadline.timestamp())}:R>")
        embed.set_footer(text=f"Use /task submit {task_id} when finished")

        await interaction.response.send_message(embed=embed, ephemeral=True)



    @app_commands.command(name='mytasks', description='View your claimed tasks')
    @app_commands.guild_only()
    async def my_tasks(self, interaction: discord.Interaction):
        """View your claimed tasks"""
        guild_id = interaction.guild.id
        user_id = interaction.user.id
        user_id_str = str(user_id)

        tasks_data = self.data_manager.load_guild_data(guild_id, "tasks")
        user_tasks = tasks_data.get('user_tasks', {}).get(user_id_str, {})

        if not user_tasks:
            await interaction.response.send_message("You haven't claimed any tasks!", ephemeral=True)
            return

        tasks = tasks_data.get('tasks', {})
        config = data_manager.load_guild_data(guild_id, "config")
        symbol = config.get('currency_symbol', '$')

        embed = discord.Embed(
            title="Your Tasks",
            color=discord.Color.blue()
        )

        for task_id, user_task in user_tasks.items():
            task = tasks.get(task_id)
            if not task:
                continue

            status = user_task.get('status', 'in_progress')
            deadline = datetime.fromisoformat(user_task['deadline'])

            status_emoji = {
                'in_progress': '⏳',
                'completed': '✅',
                'expired': '❌'
            }.get(status, '❓')

            embed.add_field(
                name=f"{status_emoji} {task['name']}",
                value=f"Reward: {symbol}{task['reward']}\n"
                      f"Deadline: <t:{int(deadline.timestamp())}:R>\n"
                      f"Status: {status.replace('_', ' ').title()}",
                inline=False
            )

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name='transactions', description='View recent transaction history')
    @app_commands.describe(
        user="View another user's transactions (optional)",
        limit="Number of transactions to show (default: 10)"
    )
    @app_commands.guild_only()
    async def view_transactions(self, interaction: discord.Interaction, user: discord.Member = None, limit: int = 10):
        """View recent transaction history"""
        target = user or interaction.user
        guild_id = interaction.guild.id
        user_id_str = str(target.id)

        # Check permissions for viewing other users
        if target.id != interaction.user.id:
            # For now, allow anyone to view other's transactions (remove moderator check for slash commands)
            pass

        # Use transaction manager instead of direct data loading
        try:
            result = self.transaction_manager.get_transactions(
                guild_id=str(guild_id),
                user_id=target.id,
                limit=limit
            )
            transactions = result['transactions']
        except Exception as e:
            logger = logging.getLogger(__name__)
            logger.error(f"Failed to load transactions via transaction manager: {e}")
            await interaction.response.send_message("❌ Error loading transaction history!", ephemeral=True)
            return

        if not transactions:
            await interaction.response.send_message(f"{target.mention} has no transaction history!", ephemeral=True)
            return

        config = self.data_manager.load_guild_data(guild_id, "config")
        symbol = config.get('currency_symbol', '$')

        embed = discord.Embed(
            title=f"{target.display_name}'s Transaction History",
            description=f"Showing last {len(transactions)} transactions",
            color=discord.Color.blue()
        )

        for txn in transactions:
            amount = txn.get('amount', 0)
            amount_str = f"+{symbol}{amount}" if amount > 0 else f"{symbol}{amount}"

            timestamp = datetime.fromisoformat(txn.get('timestamp', datetime.now().isoformat()))

            embed.add_field(
                name=f"{amount_str} - {txn.get('description', 'Unknown')}",
                value=f"Balance: {symbol}{txn.get('balance_before', 0)} → {symbol}{txn.get('balance_after', 0)}\n"
                      f"<t:{int(timestamp.timestamp())}:R>",
                inline=False
            )

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="admin_give", description="Give currency to any user (Admin only)")
    @app_commands.describe(
        user="The user to give currency to",
        amount="Amount of currency to give",
        reason="Reason for giving currency (optional)"
    )
    @app_commands.guild_only()
    async def admin_give_money(self, interaction: discord.Interaction, user: discord.Member, amount: int, reason: str = "Admin grant"):
        """Admin command to give currency to any user"""
        # Check admin permissions
        from core.permissions import is_admin
        if not is_admin(interaction.user, interaction.guild):
            await interaction.response.send_message("❌ You don't have permission to use this command!", ephemeral=True)
            return

        # Defer for database operations
        await interaction.response.defer(ephemeral=True)

        try:
            # Validation
            if amount <= 0:
                await interaction.followup.send("❌ Amount must be positive!", ephemeral=True)
                return

            if user.bot:
                await interaction.followup.send("❌ Cannot give money to bots!", ephemeral=True)
                return

            guild_id = interaction.guild.id

            # Ensure user exists
            self.data_manager.ensure_user_exists(guild_id, user.id)

            # Add balance
            result = self._add_balance(
                guild_id,
                user.id,
                amount,
                f"{reason} (by {interaction.user.name})",
                transaction_type='admin_grant',
                metadata={
                    "source": "discord_command",
                    "command": "/admin_give",
                    "admin_id": str(interaction.user.id),
                    "reason": reason
                }
            )

            if result is False:
                await interaction.followup.send("❌ Failed to give currency!", ephemeral=True)
                return

            symbol = self._get_currency_symbol(guild_id)
            embed = discord.Embed(
                title="✅ Currency Granted",
                description=f"Successfully gave {symbol}{amount:,} to {user.mention}",
                color=discord.Color.green()
            )
            embed.add_field(name="Reason", value=reason, inline=False)
            embed.add_field(name="New Balance", value=f"{symbol}{result:,}", inline=True)
            embed.add_field(name="Granted By", value=interaction.user.mention, inline=True)

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logger = logging.getLogger(__name__)
            logger.error(f"Error in admin_give_money command: {e}")
            await interaction.followup.send("❌ An error occurred while granting currency.", ephemeral=True)





class PurchaseConfirmView(discord.ui.View):
    """Confirmation buttons for purchase"""

    def __init__(self, shop_manager, item_id, quantity, total_cost, symbol):
        super().__init__(timeout=60)
        self.shop_manager = shop_manager
        self.item_id = item_id
        self.quantity = quantity
        self.total_cost = total_cost
        self.symbol = symbol

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.success)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Execute purchase"""
        result = self.shop_manager.purchase_item(
            interaction.guild.id,
            interaction.user.id,
            self.item_id,
            self.quantity,
            interaction
        )

        if result['success']:
            # Handle missing emoji field gracefully
            emoji = result['item'].get('emoji', '🛍️')  # Default to shopping bag emoji
            embed = discord.Embed(
                title="✅ Purchase Successful!",
                description=f"You bought **{self.quantity}x {emoji} {result['item']['name']}**",
                color=discord.Color.green()
            )
            embed.add_field(name="Total Cost", value=f"{self.symbol}{self.total_cost}")
            embed.add_field(name="New Balance", value=f"{self.symbol}{result['new_balance']}")
            embed.add_field(name="In Inventory", value=f"{result['inventory_total']}x")
        else:
            embed = discord.Embed(
                title="❌ Purchase Failed",
                description=result.get('error', 'Unknown error'),
                color=discord.Color.red()
            )

        await interaction.response.edit_message(embed=embed, view=None)
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Cancel purchase"""
        await interaction.response.edit_message(
            content="Purchase cancelled.",
            embed=None,
            view=None
        )
        self.stop()


async def setup(bot):
    """Setup the currency cog."""
    await bot.add_cog(Currency(bot))
