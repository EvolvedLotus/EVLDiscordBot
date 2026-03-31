"""
Currency cog with per-guild data isolation
"""

import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timedelta, timezone
import logging
from typing import List, Optional
from core import data_manager
from core.permissions import feature_enabled, is_moderator
from core.utils import format_currency, create_embed, add_embed_footer
from core.transaction_manager import TransactionManager
from core.shop_manager import ShopManager

logger = logging.getLogger(__name__)

class QuantityModal(discord.ui.Modal, title='Redeem Quantity'):
    def __init__(self, item_id, item_name, max_quantity, shop_manager, view):
        super().__init__()
        self.item_id = item_id
        self.shop_manager = shop_manager
        self.view = view
        self.max_quantity = max_quantity
        
        self.quantity = discord.ui.TextInput(
            label=f'Quantity (Max: {max_quantity})',
            placeholder='Enter amount to redeem...',
            default='1',
            min_length=1,
            max_length=len(str(max_quantity))
        )
        self.add_item(self.quantity)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            qty = int(self.quantity.value)
            if qty <= 0:
                await interaction.response.send_message("Quantity must be positive.", ephemeral=True)
                return
            if qty > self.max_quantity:
                await interaction.response.send_message(f"You only have {self.max_quantity} of this item.", ephemeral=True)
                return
            
            # Proceed with redemption
            await self.view.process_redemption(interaction, self.item_id, qty)
            
        except ValueError:
            await interaction.response.send_message("Please enter a valid number.", ephemeral=True)

class RedemptionSelect(discord.ui.Select):
    def __init__(self, inventory_items):
        options = []
        # Filter for redeemable items only (role and misc)
        redeemable_items = {
            k: v for k, v in inventory_items.items() 
            if v['item'].get('category') in ['role', 'misc', 'general', 'other']
        }
        
        for item_id, data in redeemable_items.items():
            item = data['item']
            quantity = data['quantity']
            emoji = item.get('emoji', '🛍️')
            
            # Truncate description
            desc = f"Quantity: {quantity} | {item.get('category', 'misc').title()}"
            
            options.append(discord.SelectOption(
                label=f"{item['name']}",
                value=item_id,
                description=desc,
                emoji=emoji
            ))
            
        super().__init__(
            placeholder="Select an item to redeem...", 
            min_values=1, 
            max_values=1, 
            options=options[:25],
            disabled=len(options) == 0
        )

    async def callback(self, interaction: discord.Interaction):
        item_id = self.values[0]
        await self.view.handle_selection(interaction, item_id)

class RedemptionView(discord.ui.View):
    def __init__(self, shop_manager, inventory_items, user_id):
        super().__init__(timeout=180)
        self.shop_manager = shop_manager
        self.inventory_items = inventory_items
        self.user_id = user_id
        
        # Add select menu
        self.add_item(RedemptionSelect(inventory_items))

    async def handle_selection(self, interaction: discord.Interaction, item_id: str):
        data = self.inventory_items.get(item_id)
        if not data:
            await interaction.response.send_message("Item not found.", ephemeral=True)
            return
            
        quantity = data['quantity']
        item_name = data['item']['name']
        
        if quantity > 1:
            # Show modal
            await interaction.response.send_modal(QuantityModal(item_id, item_name, quantity, self.shop_manager, self))
        else:
            # Defer immediately to prevent timeout
            await interaction.response.defer(ephemeral=True)
            # Auto redeem 1
            await self.process_redemption(interaction, item_id, 1)

    async def process_redemption(self, interaction: discord.Interaction, item_id: str, quantity: int):
        # Defer if not already deferred
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)
            
        guild_id = interaction.guild.id
        user_id = interaction.user.id
        
        try:
            result = await self.shop_manager.redeem_item(
                guild_id,
                user_id,
                item_id,
                quantity,
                interaction
            )

            if result['success']:
                embed = discord.Embed(
                    title="✅ Item Redeemed",
                    description=f"You successfully redeemed {quantity}x **{self.inventory_items[item_id]['item']['name']}**!",
                    color=discord.Color.green()
                )

                if result.get('effect') == 'role_assigned':
                    embed.add_field(
                        name="🎭 Role Assigned",
                        value=f"You now have the **{result['role_name']}** role for {result['duration_minutes']} minutes.",
                        inline=False
                    )
                elif result.get('effect') == 'log_message_sent':
                    embed.add_field(
                        name="📝 Request Sent",
                        value=f"A redemption request has been sent to the moderators.",
                        inline=False
                    )
                
                if interaction.response.is_done():
                    await interaction.followup.send(embed=embed, ephemeral=True)
                else:
                    await interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                if interaction.response.is_done():
                    await interaction.followup.send(f"❌ Redemption Failed: {result.get('error')}", ephemeral=True)
                else:
                    await interaction.response.send_message(f"❌ Redemption Failed: {result.get('error')}", ephemeral=True)
                    
        except Exception as e:
            logger.exception(f"Redeem error: {e}")
            msg = "❌ An error occurred while redeeming the item."
            if interaction.response.is_done():
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.response.send_message(msg, ephemeral=True)

class ShopConfirmView(discord.ui.View):
    def __init__(self, currency_cog, item_id, item_data):
        super().__init__(timeout=60)
        self.currency_cog = currency_cog
        self.item_id = item_id
        self.item_data = item_data

    @discord.ui.button(label="Confirm Purchase", style=discord.ButtonStyle.green, emoji="🛒")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Disable buttons to prevent double clicks
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(view=self)
        
        # Process purchase with locked-in price
        await self.currency_cog._process_purchase(
            interaction, 
            self.item_id, 
            1, 
            expected_price=self.item_data.get('price')
        )

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.grey)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="Purchase cancelled.", view=None)

class ShopSelect(discord.ui.Select):
    def __init__(self, items, currency_cog, guild_id, category=None):
        self.currency_cog = currency_cog
        self.guild_id = guild_id
        self.items = items
        self.category = category
        
        options = []
        # Filter items and take first 25
        shop_items = list(items.items())[:25]
        
        for item_id, item in shop_items:
            # Determine status emoji
            if item['stock'] == 0:
                status = "❌"
                desc = "(Out of Stock) "
            elif item['stock'] == -1:
                status = "♾️"
                desc = ""
            else:
                status = f"📦{item['stock']}"
                desc = ""
                
            desc += f"{item['price']} coins"
            if item['description']:
                desc += f" - {item['description'][:30]}"
                
            emoji = item.get('emoji', '🛍️')
            
            options.append(discord.SelectOption(
                label=f"{item['name']}",
                description=desc,
                value=item_id,
                emoji=emoji,
                default=False
            ))

        super().__init__(
            placeholder="Select an item to buy...",
            min_values=1,
            max_values=1,
            options=options,
            disabled=len(options) == 0
        )

    async def callback(self, interaction: discord.Interaction):
        item_id = self.values[0]
        item = self.items.get(item_id)
        
        if not item:
            await interaction.response.send_message("Item info unavailable.", ephemeral=True)
            return
            
        if item['stock'] == 0:
            await interaction.response.send_message("❌ This item is out of stock!", ephemeral=True)
            return

        # Create confirmation view
        view = ShopConfirmView(self.currency_cog, item_id, item)
        
        symbol = self.currency_cog._get_currency_symbol(self.guild_id)
        embed = discord.Embed(
            title="Confirm Purchase",
            description=f"Are you sure you want to buy **{item['name']}** for **{symbol}{item['price']}**?",
            color=discord.Color.green()
        )
        if item.get('description'):
            embed.add_field(name="Description", value=item['description'])
            
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

class ShopView(discord.ui.View):
    def __init__(self, currency_cog, items, guild_id, category=None):
        super().__init__(timeout=180)
        self.add_item(ShopSelect(items, currency_cog, guild_id, category))

class Currency(commands.Cog):
    """Currency system with server-specific economies"""

    def __init__(self, bot):
        self.bot = bot
        # Store managers with fallback to ensure they're available
        self.data_manager = getattr(bot, 'data_manager', None)
        self.transaction_manager = getattr(bot, 'transaction_manager', None)
        self.shop_manager = getattr(bot, 'shop_manager', None)
        self.task_manager = getattr(bot, 'task_manager', None)

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
        ATOMIC balance update using the process_balance_change Postgres RPC.
        Both the transaction log INSERT and the balance UPDATE happen inside
        a single Postgres transaction — either both succeed or both roll back.
        Row-level locking (SELECT FOR UPDATE) prevents race conditions.
        """
        try:
            result = self.data_manager.admin_client.rpc(
                'process_balance_change',
                {
                    'p_guild_id': str(guild_id),
                    'p_user_id': str(user_id),
                    'p_amount': amount,
                    'p_transaction_type': transaction_type,
                    'p_description': description,
                    'p_metadata': metadata or {}
                }
            ).execute()

            if not result.data or len(result.data) == 0:
                logger.error(f"Atomic balance change returned no data for user {user_id} in guild {guild_id}")
                return False

            row = result.data[0]
            new_balance = row['new_balance']

            # Broadcast SSE event
            try:
                from core.sse_manager import sse_manager
                sse_manager.broadcast_event('transaction', {
                    'guild_id': str(guild_id),
                    'user_id': str(user_id),
                    'new_balance': new_balance,
                    'amount': amount,
                    'type': transaction_type
                })
            except Exception as e:
                logger.warning(f"Failed to broadcast SSE event: {e}")

            # Invalidate caches
            self._broadcast_cache_invalidation(guild_id, 'currency', user_id)

            return new_balance

        except Exception as e:
            error_msg = str(e)
            if 'Insufficient balance' in error_msg:
                logger.info(f"Insufficient balance for user {user_id} in guild {guild_id}: {error_msg}")
                return False
            logger.error(f"Atomic balance change failed for user {user_id} in guild {guild_id}: {e}")
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
        """Claim daily reward — ATOMIC + IDEMPOTENT via Postgres RPC.
        Uses the daily_claims table as an idempotency gate:
        INSERT ON CONFLICT DO NOTHING prevents double-fire from
        concurrent requests or network retries.
        """
        user_id = str(interaction.user.id)
        guild_id = str(interaction.guild_id)

        try:
            # Ensure user exists before RPC call
            await self.data_manager.ensure_user_exists(guild_id, interaction.user.id)

            # Single atomic RPC: idempotency check + transaction log + balance update
            result = self.data_manager.admin_client.rpc(
                'claim_daily_reward',
                {
                    'p_guild_id': guild_id,
                    'p_user_id': user_id,
                    'p_reward': 100
                }
            ).execute()

            if not result.data or len(result.data) == 0:
                await interaction.response.send_message(
                    "Failed to claim daily reward. Please try again.",
                    ephemeral=True
                )
                return

            row = result.data[0]

            if row.get('already_claimed'):
                # Already claimed today — show when next claim is available
                next_claim = row.get('next_claim_at', '')
                if next_claim:
                    try:
                        next_dt = datetime.fromisoformat(str(next_claim).replace('Z', '+00:00'))
                        if next_dt.tzinfo is None:
                            next_dt = next_dt.replace(tzinfo=timezone.utc)
                        now = datetime.now(timezone.utc)
                        remaining = (next_dt - now).total_seconds()
                        hours_remaining = max(0, remaining / 3600)
                        await interaction.response.send_message(
                            f"You already claimed your daily reward today! Try again in {hours_remaining:.1f} hours.",
                            ephemeral=True
                        )
                    except Exception:
                        await interaction.response.send_message(
                            "You already claimed your daily reward today!",
                            ephemeral=True
                        )
                else:
                    await interaction.response.send_message(
                        "You already claimed your daily reward today!",
                        ephemeral=True
                    )
                return

            new_balance = row.get('new_balance', 0)

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
                f"You claimed your daily reward of 100 coins! New balance: {new_balance}",
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

    @app_commands.command(name="shop", description="Display all shop items")
    @app_commands.guild_only()
    async def shop(self, interaction: discord.Interaction, category: str = None):
        """Display all shop items (ephemeral response)"""
        guild_id = interaction.guild.id

        # Get ALL shop items
        items = self.shop_manager.get_shop_items(guild_id, category=category, active_only=True, include_out_of_stock=True)

        if not items:
            await interaction.response.send_message("No items available in the shop!", ephemeral=True)
            return

        # Create embed
        symbol = self._get_currency_symbol(guild_id)
        embed = discord.Embed(
            title="🏪 Shop",
            description=f"Browsing {category if category else 'all items'}",
            color=discord.Color.blue()
        )

        embed.add_field(
            name="💰 Your Balance",
            value=f"{symbol}{self._get_balance(guild_id, interaction.user.id):,}",
            inline=False
        )

        item_list = list(items.items())[:20]
        
        for item_id, item in item_list:
            emoji = item.get('emoji', '🛍️')
            
            if item['stock'] == -1:
                stock_text = "♾️"
            elif item['stock'] == 0:
                stock_text = "❌ OUT OF STOCK"
            else:
                stock_text = f"📦 {item['stock']}"
            
            description = item['description'][:50] + '...' if len(item['description']) > 50 else item['description']
            
            embed.add_field(
                name=f"{emoji} {item['name']}",
                value=f"**{symbol}{item['price']:,}** • {stock_text}\n{description}",
                inline=True
            )

        # Attach View
        view = ShopView(self, items, guild_id, category)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

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

        # Add redemption view if viewing own inventory
        view = None
        if target.id == interaction.user.id:
            view = RedemptionView(self.shop_manager, inventory, target.id)

        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @app_commands.command(name="redeem", description="Redeem an item from your inventory")
    @app_commands.guild_only()
    async def redeem(self, interaction: discord.Interaction):
        """Redeem shop item from inventory (Interactive)"""
        # We don't defer immediately because we might need to send a modal (which requires no deferral or specific handling)
        # But here we are sending a View first, so deferral is fine? 
        # Actually, if we want to send a Modal later from the View, the initial interaction must be valid.
        # Let's defer ephemeral.
        await interaction.response.defer(ephemeral=True)

        user_id = interaction.user.id
        guild_id = interaction.guild.id

        # Get user's inventory with item details
        inventory = self.shop_manager.get_inventory(guild_id, user_id, include_item_details=True)

        # Filter for redeemable items
        redeemable_items = {
            k: v for k, v in inventory.items() 
            if v['item'].get('category') in ['role', 'misc', 'general', 'other']
        }

        if not redeemable_items:
            await interaction.followup.send("❌ You don't have any redeemable items in your inventory!", ephemeral=True)
            return

        # Create view
        view = RedemptionView(self.shop_manager, inventory, user_id)
        
        await interaction.followup.send(
            "🎁 **Select an item to redeem:**",
            view=view,
            ephemeral=True
        )

    async def _process_purchase(self, interaction: discord.Interaction, item_id: str, quantity: int, expected_price: int = None):
        """Helper to process purchase logic via atomic RPC"""
        # If response not started, defer
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)

        user_id = interaction.user.id
        guild_id = interaction.guild.id

        try:
            result = self.shop_manager.purchase_item(
                guild_id=guild_id,
                user_id=user_id,
                item_id=item_id,
                quantity=quantity,
                interaction=interaction,
                expected_price=expected_price
            )

            if not result['success']:
                error_msg = result.get('error', 'Unknown error occurred')
                if "Price changed" in error_msg:
                    await interaction.followup.send(f"❌ {error_msg}", ephemeral=True)
                else:
                    await interaction.followup.send(f"❌ Purchase failed: {error_msg}", ephemeral=True)
                return

            item = result['item']
            symbol = self._get_currency_symbol(guild_id)
            emoji = item.get('emoji', '🛍️')

            embed = discord.Embed(
                title="✅ Purchase Successful!",
                description=f"You bought **{quantity}x {emoji} {item['name']}**",
                color=discord.Color.green()
            )
            embed.add_field(name="Total Cost", value=f"{symbol}{result['total_cost']}")
            embed.add_field(name="New Balance", value=f"{symbol}{result['new_balance']}")
            embed.add_field(name="In Inventory", value=f"{result['inventory_total']}x")

            await interaction.followup.send(embed=embed, ephemeral=True)


        except Exception as e:
            logger.exception(f"Purchase error: {e}")
            await interaction.followup.send("❌ Purchase failed due to an error. Please try again.", ephemeral=True)

    @app_commands.command(name="buy", description="Purchase item with atomic transaction")
    @app_commands.describe(
        item="The item to purchase",
        quantity="How many to buy (default: 1)"
    )
    @app_commands.guild_only()
    async def buy(self, interaction: discord.Interaction, item: str, quantity: int = 1):
        """Purchase item"""
        if quantity <= 0:
            await interaction.response.send_message("Quantity must be positive.", ephemeral=True)
            return

        # Extract expected price if it was included by autocomplete
        expected_price = None
        actual_item_id = item
        if "::" in item:
            parts = item.split("::")
            actual_item_id = parts[0]
            try:
                expected_price = int(parts[1])
            except ValueError:
                pass

        await self._process_purchase(interaction, actual_item_id, quantity, expected_price=expected_price)

    @buy.autocomplete('item')
    async def buy_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        """Autocomplete shop items (active only)"""
        items = self.shop_manager.get_shop_items(
            interaction.guild.id,
            active_only=True,
            include_out_of_stock=False
        )
        choices = []
        for item_id, item_data in items.items():
            if current.lower() in item_data['name'].lower():
                emoji = item_data.get('emoji', '🛍️')
                # Embed the price-at-time-of-view into the value string
                choices.append(app_commands.Choice(
                    name=f"{emoji} {item_data['name']} - {item_data['price']}💰",
                    value=f"{item_id}::{item_data['price']}"
                ))
        return choices[:25]

    @app_commands.command(name="transfer", description="Send coins to another user")
    @app_commands.describe(
        user="The user to send coins to",
        amount="Amount of coins to send",
        reason="Optional reason for the transfer"
    )
    @app_commands.guild_only()
    async def transfer_coins(self, interaction: discord.Interaction, user: discord.Member, amount: int, reason: str = ""):
        """Transfer coins — ATOMIC via Postgres RPC.
        Uses process_transfer() which locks both user rows with SELECT FOR UPDATE,
        validates the sender balance inside the DB transaction, and performs all
        4 writes (2 transaction logs + 2 balance updates) atomically.
        """
        sender_id = str(interaction.user.id)
        receiver_id = str(user.id)
        guild_id = str(interaction.guild_id)

        # VALIDATION: Prevent self-transfer
        if sender_id == receiver_id:
            await interaction.response.send_message("You cannot transfer coins to yourself.", ephemeral=True)
            return

        # VALIDATION: Prevent negative/zero amounts
        if amount <= 0:
            await interaction.response.send_message("Amount must be positive.", ephemeral=True)
            return

        # VALIDATION: Prevent bots
        if user.bot:
            await interaction.response.send_message("You cannot transfer coins to bots.", ephemeral=True)
            return

        try:
            # Ensure receiver exists before the atomic RPC
            await self.data_manager.ensure_user_exists(guild_id, user.id)

            reason_text = reason if reason else "Coin transfer"

            # Single atomic RPC: locks both rows, validates balance, logs 2 transactions, updates 2 balances
            result = self.data_manager.admin_client.rpc(
                'process_transfer',
                {
                    'p_guild_id': guild_id,
                    'p_sender_id': sender_id,
                    'p_receiver_id': receiver_id,
                    'p_amount': amount,
                    'p_description_send': f"Sent {amount} coins to {user.display_name}" + (f" - {reason}" if reason else ""),
                    'p_description_recv': f"Received {amount} coins from {interaction.user.display_name}" + (f" - {reason}" if reason else ""),
                    'p_metadata_send': {"recipient_id": receiver_id},
                    'p_metadata_recv': {"sender_id": sender_id}
                }
            ).execute()

            if not result.data or len(result.data) == 0:
                await interaction.response.send_message(
                    "Failed to transfer coins. Please try again.",
                    ephemeral=True
                )
                return

            row = result.data[0]
            sender_new_balance = row['sender_new_balance']

            # Invalidate caches
            self.data_manager.invalidate_cache(int(guild_id), 'currency')

            # Broadcast SSE events
            try:
                from core.sse_manager import sse_manager
                sse_manager.broadcast_event('transaction', {
                    'guild_id': guild_id,
                    'type': 'transfer',
                    'sender_id': sender_id,
                    'receiver_id': receiver_id,
                    'amount': amount
                })
            except Exception as e:
                logger.warning(f"Failed to broadcast transfer SSE event: {e}")

            await interaction.response.send_message(
                f"Successfully transferred {amount} coins to {user.mention}. Your new balance: {sender_new_balance}" + (f"\nReason: {reason}" if reason else ""),
                ephemeral=True
            )

        except Exception as e:
            error_msg = str(e)
            if 'Insufficient balance' in error_msg:
                await interaction.response.send_message(
                    "Insufficient balance for this transfer.",
                    ephemeral=True
                )
            elif 'Sender account not found' in error_msg:
                await interaction.response.send_message(
                    "You don't have an account yet. Try earning some coins first!",
                    ephemeral=True
                )
            else:
                logger.exception(f"Transfer command error: {e}")
                if not interaction.response.is_done():
                    await interaction.response.send_message("Failed to transfer coins. Please try again.", ephemeral=True)

    @app_commands.command(name="shop_create", description="Create a shop item (Admin only)")
    @app_commands.describe(
        name="Item name",
        description="Item description",
        price="Item price in coins",
        stock="Stock quantity (-1 for unlimited)",
        category="Item category",
        emoji="Item emoji/icon"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def create_shop_item_cmd(
        self,
        interaction: discord.Interaction,
        name: str,
        description: str,
        price: int,
        stock: int = -1,
        category: str = "general",
        emoji: str = "🛍️"
    ):
        """Create a new shop item."""
        await interaction.response.defer(ephemeral=True)

        guild_id = interaction.guild.id

        try:
            # Validate inputs
            if price <= 0:
                await interaction.followup.send("❌ Price must be positive.", ephemeral=True)
                return

            # Create item data
            item_data = {
                'name': name,
                'description': description,
                'price': price,
                'stock': stock,
                'category': category,
                'emoji': emoji,
                'is_active': True,
                'created_at': datetime.now(timezone.utc).isoformat()
            }

            # Use ShopManager to create item
            item = self.shop_manager.create_item(guild_id, item_data)

            if item:
                embed = discord.Embed(
                    title="✅ Shop Item Created",
                    description=f"Successfully created **{name}**",
                    color=discord.Color.green()
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.followup.send("❌ Failed to create item.", ephemeral=True)

        except Exception as e:
            logger.error(f"Error creating shop item: {e}")
            await interaction.followup.send(f"❌ Error: {str(e)}", ephemeral=True)

    @app_commands.command(name="shop_delete", description="Delete a shop item (Admin only)")
    @app_commands.describe(item_id="ID of the item to delete")
    @app_commands.checks.has_permissions(administrator=True)
    async def delete_shop_item_cmd(self, interaction: discord.Interaction, item_id: str):
        """Delete a shop item."""
        await interaction.response.defer(ephemeral=True)
        
        guild_id = interaction.guild.id
        
        try:
            # Use ShopManager to delete item
            success = self.shop_manager.delete_item(guild_id, item_id)
            
            if success:
                await interaction.followup.send(f"✅ Shop item `{item_id}` deleted successfully.", ephemeral=True)
            else:
                await interaction.followup.send(f"❌ Failed to delete item `{item_id}`. Item not found.", ephemeral=True)
                
        except Exception as e:
            logger.error(f"Error deleting shop item: {e}")
            await interaction.followup.send(f"❌ An error occurred: {str(e)}", ephemeral=True)

    @app_commands.command(name="shop_edit", description="Edit a shop item (Admin only)")
    @app_commands.describe(
        item_id="ID of item to edit",
        name="New name (optional)",
        description="New description (optional)",
        price="New price (optional)",
        stock="New stock (optional)",
        category="New category (optional)",
        emoji="New emoji (optional)"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def edit_shop_item_cmd(
        self,
        interaction: discord.Interaction,
        item_id: str,
        name: str = None,
        description: str = None,
        price: int = None,
        stock: int = None,
        category: str = None,
        emoji: str = None
    ):
        """Edit an existing shop item."""
        await interaction.response.defer(ephemeral=True)

        guild_id = interaction.guild.id

        try:
            # Check if item exists
            items = self.shop_manager.get_shop_items(guild_id, active_only=False)
            if item_id not in items:
                await interaction.followup.send("❌ Item not found.", ephemeral=True)
                return

            item = items[item_id]

            # Build updates
            updates = {}
            if name is not None:
                updates['name'] = name
            if description is not None:
                updates['description'] = description
            if price is not None:
                if price <= 0:
                    await interaction.followup.send("❌ Price must be positive.", ephemeral=True)
                    return
                updates['price'] = price
            if stock is not None:
                updates['stock'] = stock
            if category is not None:
                updates['category'] = category
            if emoji is not None:
                updates['emoji'] = emoji

            if not updates:
                await interaction.followup.send("❌ No changes specified.", ephemeral=True)
                return

            # Update item
            success = self.shop_manager.update_item(guild_id, item_id, updates)

            if success:
                embed = discord.Embed(
                    title="✅ Shop Item Updated",
                    description=f"Successfully updated **{item['name']}**",
                    color=discord.Color.blue()
                )

                # Show changes
                for field, value in updates.items():
                    if field == 'stock':
                        value = "Unlimited" if value == -1 else str(value)
                    embed.add_field(name=field.title(), value=str(value), inline=True)

                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.followup.send("❌ Failed to update shop item.", ephemeral=True)

        except Exception as e:
            logger.exception(f"Shop item edit error: {e}")
            await interaction.followup.send("❌ Error updating shop item.", ephemeral=True)





    # NOTE: /view_tasks command removed - use /tasks or /view_tasks from tasks.py cog instead

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

        if task.get('status') != 'active':
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
            await self.data_manager.ensure_user_exists(guild_id, user.id)

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

    @app_commands.command(name='delete_task', description='[Admin] Delete a task')
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(administrator=True)
    async def delete_task_cmd(self, interaction: discord.Interaction, task_id: int):
        """Delete a task (Admin only)"""
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Call the async delete_task method
            result = await self.task_manager.delete_task(interaction.guild.id, task_id)
            
            if result.get('success'):
                embed = discord.Embed(
                    title="✅ Task Deleted",
                    description=f"Task #{task_id} has been successfully deleted.",
                    color=discord.Color.green()
                )
            else:
                embed = discord.Embed(
                    title="❌ Delete Failed",
                    description=result.get('error', 'Failed to delete task'),
                    color=discord.Color.red()
                )
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            logger.error(f"Error deleting task: {e}")
            await interaction.followup.send(
                f"❌ Error deleting task: {str(e)}",
                ephemeral=True
            )


async def setup(bot):
    """Setup the currency cog."""
    await bot.add_cog(Currency(bot))
