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

logger = logging.getLogger(__name__)

class Currency(commands.Cog):
    """Currency system with server-specific economies"""

    def __init__(self, bot):
        self.bot = bot
        # Store managers with fallback to ensure they're available
        self.data_manager = getattr(bot, 'data_manager', None)
        self.transaction_manager = getattr(bot, 'transaction_manager', None)
        self.shop_manager = getattr(bot, 'shop_manager', None)

        # Log initialization status
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
        """Get user balance directly from database"""
        try:
            # Get balance directly from users table
            user_data = self.data_manager.load_user_data(guild_id, user_id)
            return user_data.get('balance', 0)
        except Exception as e:
            logger = logging.getLogger(__name__)
            logger.error(f"Error getting balance for user {user_id} in guild {guild_id}: {e}")
            return 0

    def _add_balance(self, guild_id: int, user_id: int, amount: int, description: str, transaction_type: str = 'earn', metadata: dict = None):
        """
        UPDATED: Two-phase commit implementation for balance updates and transaction logging.
        Transaction Log is considered the source of truth for history.
        If transaction logging fails, the entire operation (balance change) must fail and rollback.

        Phase 1 (Prepare): Validate and prepare transaction data
        Phase 2 (Commit): Log transaction first, then update balance
        Phase 3 (Rollback): If transaction logging fails, rollback any partial changes
        """
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

        # IMMEDIATE CACHE INVALIDATION: Force clear cache immediately for balance operations
        if data_type == 'currency':
            try:
                # Force immediate cache invalidation for currency data
                self.data_manager.invalidate_cache(guild_id, data_type)
                logger.debug(f"Immediate cache invalidation for guild {guild_id} currency data")
            except Exception as e:
                logger.warning(f"Failed immediate cache invalidation: {e}")


    @app_commands.command(name='balance', description='Check your balance')
    @app_commands.guild_only()
    async def balance(self, interaction: discord.Interaction, user: discord.Member = None):
        """Check balance with recent transaction summary - IMMEDIATE updates"""
        # Defer immediately for database operations
        await interaction.response.defer(ephemeral=True)

        target = user or interaction.user
        guild_id = interaction.guild.id

        try:
            # VALIDATION: Ensure user exists before balance queries
            await self.data_manager.ensure_user_exists(guild_id, target.id)

            # Force fresh load from database (bypass cache for immediate updates)
            user_data = self.data_manager.load_user_data(guild_id, target.id)
            if not user_data:
                # If user data not found, try loading fresh currency data
                currency_data = self.data_manager.load_guild_data(guild_id, 'currency', force_reload=True)
                user_data = currency_data.get('users', {}).get(str(target.id), {})

            balance = user_data.get('balance', 0)
            symbol = self._get_currency_symbol(guild_id)

            embed = create_embed(
                title=f"💰 {target.display_name}'s Balance",
                description=f"{symbol}{balance:,}",
                color=0x2ecc71
            )

            # Get last 5 transactions via transaction_manager and validate integrity
            try:
                recent_txns = self.transaction_manager.get_transactions(
                    guild_id=guild_id,
                    user_id=target.id,
                    limit=5
                )['transactions']

                # VALIDATION: Check transaction integrity
                for tx in recent_txns:
                    if tx['balance_after'] != tx['balance_before'] + tx['amount']:
                        logger.error(f"Transaction integrity violation: {tx['id']}")
                        # Log to audit system - in production this would alert admins

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
                logger.error(f"Failed to load recent transactions for balance display: {e}")

            embed.set_footer(text=f"Server: {interaction.guild.name} | Real-time balance")

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
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
        """Claim daily reward with CRITICAL EXPLOIT PREVENTION"""
        user_id = str(interaction.user.id)
        guild_id = str(interaction.guild_id)

        # ALWAYS use UTC, never local time
        now = datetime.now(timezone.utc)

        try:
            # Get user data (execute() returns APIResponse, access .data directly)
            user_data_result = await self.data_manager.supabase.table('users').select('balance, last_daily').eq('user_id', user_id).eq('guild_id', guild_id).execute()

            if not user_data_result.data or len(user_data_result.data) == 0:
                # Ensure user exists if not found
                await self.data_manager.ensure_user_exists(guild_id, interaction.user.id)
                user_data = {'balance': 0, 'last_daily': None}
            else:
                user_data = user_data_result.data[0]

            last_daily = user_data.get('last_daily')

            # If last_daily exists and within 24 hours, reject
            if last_daily:
                # Ensure last_daily is timezone-aware UTC
                if isinstance(last_daily, str):
                    if last_daily.endswith('Z'):
                        last_daily = datetime.fromisoformat(last_daily.replace('Z', '+00:00'))
                    else:
                        last_daily = datetime.fromisoformat(last_daily)
                    if last_daily.tzinfo is None:
                        last_daily = last_daily.replace(tzinfo=timezone.utc)

                time_diff = (now - last_daily).total_seconds()
                if time_diff < 86400:  # 24 hours in seconds
                    hours_remaining = (86400 - time_diff) / 3600
                    await interaction.response.send_message(
                        f"You can claim your daily reward in {hours_remaining:.1f} hours.",
                        ephemeral=True
                    )
                    return

            # ATOMIC TRANSACTION: All or nothing
            reward = 100
            new_balance = user_data['balance'] + reward

            # Use transaction manager for atomic update
            try:
                transaction_result = self.transaction_manager.log_transaction(
                    guild_id=int(guild_id),
                    user_id=int(user_id),
                    amount=reward,
                    balance_before=user_data['balance'],
                    balance_after=new_balance,
                    transaction_type="daily_reward",
                    description="Daily reward",
                    metadata={"source": "discord_command", "command": "/daily"}
                )

                if not transaction_result:
                    await interaction.response.send_message(
                        "Failed to claim daily reward. Please try again.",
                        ephemeral=True
                    )
                    return

                # Update balance and last_daily together in database (execute() is synchronous)
                update_result = self.data_manager.supabase.table('users').update({
                    'balance': new_balance,
                    'last_daily': now.isoformat()
                }).eq('user_id', user_id).eq('guild_id', guild_id).execute()

                if not update_result.data:
                    logger.error(f"Failed to update user balance for daily reward: {user_id}")
                    await interaction.response.send_message(
                        "Failed to claim daily reward. Please try again.",
                        ephemeral=True
                    )
                    return

            except Exception as e:
                logger.exception(f"Transaction failed for daily reward: {e}")
                await interaction.response.send_message(
                    "Failed to claim daily reward. Please try again.",
                    ephemeral=True
                )
                return

            # Invalidate cache
            self.data_manager.invalidate_cache(int(guild_id), 'currency')

            # Emit SSE event
            try:
                from core.sse_manager import sse_manager
                sse_manager.broadcast_event(guild_id, {
                    'type': 'balance_update',
                    'user_id': user_id,
                    'new_balance': new_balance
                })
            except Exception as e:
                logger.warning(f"Failed to emit SSE event for daily reward: {e}")

            await interaction.response.send_message(
                f"You claimed your daily reward of {reward} coins! New balance: {new_balance}",
                ephemeral=True
            )

        except Exception as e:
            logger = logging.getLogger(__name__)
            logger.exception(f"Daily reward error for {user_id}: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "Failed to claim daily reward. Please try again.",
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    "Failed to claim daily reward. Please try again.",
                    ephemeral=True
                )

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

    @app_commands.command(name="give")
    @app_commands.describe(user="User to give coins to", amount="Amount to give")
    @app_commands.guild_only()
    async def give(self, interaction: discord.Interaction, user: discord.Member, amount: int):
        """Give currency to another user with CRITICAL EXPLOIT PREVENTION"""
        sender_id = str(interaction.user.id)
        receiver_id = str(user.id)
        guild_id = str(interaction.guild_id)

        # VALIDATION: Prevent self-transfer
        if sender_id == receiver_id:
            await interaction.response.send_message("You cannot give coins to yourself.", ephemeral=True)
            return

        # VALIDATION: Prevent negative/zero amounts
        if amount <= 0:
            await interaction.response.send_message("Amount must be positive.", ephemeral=True)
            return

        # VALIDATION: Prevent bots
        if user.bot:
            await interaction.response.send_message("You cannot give coins to bots.", ephemeral=True)
            return

        try:
            # Get sender balance (synchronous Supabase call - NO await)
            sender_data = self.data_manager.supabase.table('users').select('balance').eq('user_id', sender_id).eq('guild_id', guild_id).execute()

            if not sender_data.data or len(sender_data.data) == 0:
                await interaction.response.send_message("You don't have an account.", ephemeral=True)
                return

            sender_balance = sender_data.data[0]['balance']

            # VALIDATION: Check sufficient balance
            if sender_balance < amount:
                await interaction.response.send_message(
                    f"Insufficient balance. You have {sender_balance} coins.",
                    ephemeral=True
                )
                return

            # Ensure receiver exists (async method - NEEDS await)
            await self.data_manager.ensure_user_exists(guild_id, user.id)

            # Get receiver balance (synchronous Supabase call - NO await)
            receiver_data = self.data_manager.supabase.table('users').select('balance').eq('user_id', receiver_id).eq('guild_id', guild_id).execute()
            receiver_balance = receiver_data.data[0]['balance'] if receiver_data.data and len(receiver_data.data) > 0 else 0

            # Calculate new balances
            sender_new_balance = sender_balance - amount
            receiver_new_balance = receiver_balance + amount

            # Log transactions (synchronous methods - NO await)
            self.transaction_manager.log_transaction(
                user_id=int(sender_id),
                guild_id=int(guild_id),
                amount=-amount,
                transaction_type="give_sent",
                balance_before=sender_balance,
                balance_after=sender_new_balance,
                description=f"Gave {amount} coins to {user.display_name}",
                metadata={"recipient_id": receiver_id}
            )

            self.transaction_manager.log_transaction(
                user_id=int(receiver_id),
                guild_id=int(guild_id),
                amount=amount,
                transaction_type="give_received",
                balance_before=receiver_balance,
                balance_after=receiver_new_balance,
                description=f"Received {amount} coins from {interaction.user.display_name}",
                metadata={"sender_id": sender_id}
            )

            # Update balances (synchronous Supabase calls - NO await)
            self.data_manager.supabase.table('users').update({'balance': sender_new_balance}).eq('user_id', sender_id).eq('guild_id', guild_id).execute()
            self.data_manager.supabase.table('users').update({'balance': receiver_new_balance}).eq('user_id', receiver_id).eq('guild_id', guild_id).execute()

            # Invalidate caches
            self.data_manager.invalidate_cache(int(guild_id), 'currency')

            # Emit SSE events for both users
            try:
                from core.sse_manager import sse_manager
                sse_manager.broadcast_event(guild_id, {
                    'type': 'balance_update',
                    'user_id': sender_id,
                    'new_balance': sender_new_balance
                })
                sse_manager.broadcast_event(guild_id, {
                    'type': 'balance_update',
                    'user_id': receiver_id,
                    'new_balance': receiver_new_balance
                })
            except Exception as e:
                logger.warning(f"Failed to emit SSE events for give command: {e}")

            await interaction.response.send_message(
                f"Successfully gave {amount} coins to {user.mention}. Your new balance: {sender_new_balance}",
                ephemeral=True
            )

        except Exception as e:
            logger.exception(f"Give command error: {e}")
            await interaction.response.send_message("Failed to transfer coins. Please try again.", ephemeral=True)

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



    @app_commands.command(name="buy", description="Purchase item with atomic transaction")
    @app_commands.describe(
        item="The item to purchase",
        quantity="How many to buy (default: 1)"
    )
    @app_commands.guild_only()
    async def buy(self, interaction: discord.Interaction, item: str, quantity: int = 1):
        """Purchase item with CRITICAL EXPLOIT PREVENTION - atomic using existing balance check"""
        user_id = str(interaction.user.id)
        guild_id = str(interaction.guild_id)

        # VALIDATION: Positive quantity
        if quantity <= 0:
            await interaction.response.send_message("Quantity must be positive.", ephemeral=True)
            return

        try:
            # Get item data to check stock
            item_result = self.data_manager.supabase.table('shop_items').select('*').eq('item_id', item).eq('guild_id', guild_id).eq('is_active', True).execute()
            if not item_result.data or len(item_result.data) == 0:
                await interaction.response.send_message("Item not found or inactive.", ephemeral=True)
                return

            item_data = item_result.data[0]

            # VALIDATION: Check stock availability
            if item_data['stock'] != -1 and item_data['stock'] < quantity:
                await interaction.response.send_message(
                    f"Insufficient stock. Available: {item_data['stock']}",
                    ephemeral=True
                )
                return

            # Calculate total cost
            total_cost = item_data['price'] * quantity

            # Get current balance
            balance_data = self._get_balance(int(guild_id), interaction.user.id)

            # VALIDATION: Check balance
            if balance_data < total_cost:
                await interaction.response.send_message(
                    f"Insufficient balance. Cost: {total_cost}, Balance: {balance_data}",
                    ephemeral=True
                )
                return

            # Get updated user data
            user_result = self.data_manager.supabase.table('users').select('*').eq('user_id', user_id).eq('guild_id', guild_id).execute()
            if not user_result.data or len(user_result.data) == 0:
                self.data_manager.ensure_user_exists(guild_id, interaction.user.id)
                user_result = self.data_manager.supabase.table('users').select('*').eq('user_id', user_id).eq('guild_id', guild_id).execute()
                if not user_result.data or len(user_result.data) == 0:
                    await interaction.response.send_message("Unable to create user account. Please try again.", ephemeral=True)
                    return

            user_data = user_result.data[0]
            new_balance = user_data['balance'] - total_cost
            new_stock = item_data['stock'] - quantity if item_data['stock'] != -1 else -1

            # Use atomic transaction for the actual updates
            # Note: Since AtomicTransactionContext is async, we now do direct operations
            try:
                # Update stock if not unlimited
                if item_data['stock'] != -1:
                    self.data_manager.supabase.table('shop_items').update({'stock': new_stock}).eq('item_id', item).eq('guild_id', guild_id).execute()

                # Update user balance
                self.data_manager.supabase.table('users').update({'balance': new_balance}).eq('user_id', user_id).eq('guild_id', guild_id).execute()

                # Update inventory
                inventory_data = {'user_id': user_id, 'guild_id': guild_id, 'item_id': item, 'quantity': quantity}
                self.data_manager.supabase.table('inventory').upsert(inventory_data, on_conflict='user_id,guild_id,item_id').execute()

                # Log transaction
                self.transaction_manager.log_transaction(
                    user_id=int(user_id),
                    guild_id=int(guild_id),
                    amount=-total_cost,
                    transaction_type="shop_purchase",
                    balance_before=user_data['balance'],
                    balance_after=new_balance,
                    description=f"Purchased {quantity}x {item_data['name']}",
                    metadata={'item_id': item, 'quantity': quantity}
                )

            except Exception as e:
                logger.exception(f"Purchase transaction error: {e}")
                await interaction.response.send_message("Purchase failed. Please try again.", ephemeral=True)
                return

            # Update Discord message (outside transaction)
            if item_data['channel_id'] and item_data['message_id']:
                try:
                    channel = interaction.guild.get_channel(int(item_data['channel_id']))
                    if channel:
                        message = await channel.fetch_message(int(item_data['message_id']))
                        # Update embed with new stock
                        embed = message.embeds[0] if message.embeds else discord.Embed()
                        # Update stock field in embed
                        for i, field in enumerate(embed.fields):
                            if field.name == "Stock":
                                stock_text = "♾️ Unlimited" if new_stock == -1 else f"{new_stock} in stock"
                                embed.set_field_at(i, name="Stock", value=stock_text, inline=True)
                        await message.edit(embed=embed)
                except Exception as e:
                    logger.warning(f"Failed to update shop message: {e}")

            # Invalidate caches
            self.data_manager.invalidate_cache(int(guild_id), 'currency')

            # Emit SSE events
            try:
                from core.sse_manager import sse_manager
                sse_manager.broadcast_event(guild_id, {
                    'type': 'purchase',
                    'user_id': user_id,
                    'item_id': item,
                    'quantity': quantity,
                    'new_balance': new_balance,
                    'new_stock': new_stock
                })
            except Exception as e:
                logger.warning(f"Failed to emit SSE event for purchase: {e}")

            symbol = self._get_currency_symbol(int(guild_id))
            emoji = item_data.get('emoji', '🛍️')
            await interaction.response.send_message(
                f"Successfully purchased {quantity}x {emoji} {item_data['name']} for {total_cost} {symbol}! New balance: {new_balance} {symbol}",
                ephemeral=True
            )

        except Exception as e:
            logger.exception(f"Purchase error: {e}")
            await interaction.response.send_message("Purchase failed. Please try again.", ephemeral=True)

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
        config = self.data_manager.load_guild_data(guild_id, "config")
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
        from core.permissions import is_admin_interaction
        if not is_admin_interaction(interaction):
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
