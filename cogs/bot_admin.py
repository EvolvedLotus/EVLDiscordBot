import discord
from discord import app_commands
from discord.ext import commands
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, List
import json

logger = logging.getLogger(__name__)

class BotAdmin(commands.Cog):
    """Admin commands cog providing full CMS dashboard parity via Discord slash commands."""

    def __init__(self, bot):
        self.bot = bot
        self.data_manager = None
        self.transaction_manager = None

    def set_managers(self, data_manager, transaction_manager):
        """Set data and transaction managers"""
        self.data_manager = data_manager
        self.transaction_manager = transaction_manager

    # ===== USER MANAGEMENT =====

    @app_commands.command(name="addbalance", description="Add currency to a user's balance (Admin only)")
    @app_commands.describe(
        user="The user to add currency to",
        amount="Amount of currency to add",
        reason="Reason for adding currency (optional)"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def addbalance(self, interaction: discord.Interaction, user: discord.Member, amount: int, reason: str = "Admin adjustment"):
        """Add currency to a user's balance"""
        result = await self._modify_user_balance(interaction, user, amount, reason, "add")
        await self._send_balance_result(interaction, result, "added to", user, amount)

    @app_commands.command(name="removebalance", description="Remove currency from a user's balance (Admin only)")
    @app_commands.describe(
        user="The user to remove currency from",
        amount="Amount of currency to remove",
        reason="Reason for removing currency (optional)"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def removebalance(self, interaction: discord.Interaction, user: discord.Member, amount: int, reason: str = "Admin adjustment"):
        """Remove currency from a user's balance"""
        if amount < 0:
            amount = -amount  # Ensure positive for removal
        result = await self._modify_user_balance(interaction, user, -amount, reason, "subtract")
        await self._send_balance_result(interaction, result, "removed from", user, amount)

    @app_commands.command(name="setbalance", description="Set a user's balance to exact amount (Admin only)")
    @app_commands.describe(
        user="The user whose balance to set",
        amount="The exact balance amount to set",
        reason="Reason for setting balance (optional)"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def setbalance(self, interaction: discord.Interaction, user: discord.Member, amount: int, reason: str = "Admin adjustment"):
        """Set a user's balance to an exact amount"""
        result = await self._modify_user_balance(interaction, user, amount, reason, "set")
        await self._send_balance_result(interaction, result, "set to", user, amount)

    async def _modify_user_balance(self, interaction: discord.Interaction, user: discord.Member, amount: int, reason: str, action: str):
        """Helper method to modify user balance"""
        guild_id = str(interaction.guild.id)
        user_id = str(user.id)

        try:
            # Load currency data
            currency_data = self.data_manager.load_guild_data(guild_id, 'currency')
            users = currency_data.get('users', {})

            # Get current balance
            user_data = users.get(user_id, {'balance': 0, 'total_earned': 0, 'total_spent': 0})
            current_balance = user_data.get('balance', 0)

            # Calculate new balance
            if action == "set":
                new_balance = max(0, amount)  # Ensure non-negative
                actual_change = new_balance - current_balance
            elif action == "add":
                new_balance = current_balance + amount
                actual_change = amount
            elif action == "subtract":
                new_balance = max(0, current_balance - amount)
                actual_change = -(min(amount, current_balance))
            else:
                return {"success": False, "error": "Invalid action"}

            # Initialize user if doesn't exist
            if user_id not in users:
                users[user_id] = {
                    'balance': 0,
                    'total_earned': 0,
                    'total_spent': 0,
                    'created_at': datetime.now().isoformat(),
                    'is_active': True,
                    'username': user.name,
                    'display_name': user.display_name
                }
                user_data = users[user_id]

            # Update balance
            user_data['balance'] = new_balance

            # Update totals
            if actual_change > 0:
                user_data['total_earned'] = user_data.get('total_earned', 0) + actual_change
            elif actual_change < 0:
                user_data['total_spent'] = user_data.get('total_spent', 0) + abs(actual_change)

            # Create transaction log
            transaction_data = {
                'id': f"txn_{int(datetime.now().timestamp() * 1000)}",
                'user_id': user_id,
                'amount': actual_change,
                'balance_before': current_balance,
                'balance_after': new_balance,
                'type': 'admin_adjustment',
                'description': reason,
                'timestamp': datetime.now().isoformat(),
                'source': 'discord_admin'
            }

            # Save transaction
            transactions = self.data_manager.load_guild_data(guild_id, 'transactions') or []
            transactions.append(transaction_data)
            self.data_manager.save_guild_data(guild_id, 'transactions', transactions)

            # Save currency data
            self.data_manager.save_guild_data(guild_id, 'currency', currency_data)

            return {
                "success": True,
                "user": user,
                "old_balance": current_balance,
                "new_balance": new_balance,
                "change": actual_change,
                "action": action
            }

        except Exception as e:
            logger.error(f"Error modifying user balance: {e}")
            return {"success": False, "error": str(e)}

    async def _send_balance_result(self, interaction: discord.Interaction, result: dict, action_text: str, user: discord.Member, amount: int):
        """Send the result of a balance modification"""
        if result["success"]:
            embed = discord.Embed(
                title="✅ Balance Updated",
                description=f"Successfully {action_text} {user.mention}",
                color=discord.Color.green()
            )
            embed.add_field(name="Old Balance", value=f"{result['old_balance']} coins", inline=True)
            embed.add_field(name="New Balance", value=f"{result['new_balance']} coins", inline=True)
            embed.add_field(name="Change", value=f"{result['change']} coins", inline=True)
            if result.get("error"):
                embed.add_field(name="Note", value=result["error"], inline=False)
        else:
            embed = discord.Embed(
                title="❌ Balance Update Failed",
                description=result.get("error", "Unknown error"),
                color=discord.Color.red()
            )

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="user_balance", description="View or modify a user's balance")
    @app_commands.describe(
        user="The user to check/modify",
        action="Action to perform",
        amount="Amount for set/add/subtract operations",
        reason="Reason for the balance change"
    )
    @app_commands.choices(action=[
        app_commands.Choice(name="Check Balance", value="check"),
        app_commands.Choice(name="Set Balance", value="set"),
        app_commands.Choice(name="Add Currency", value="add"),
        app_commands.Choice(name="Subtract Currency", value="subtract")
    ])
    @app_commands.checks.has_permissions(administrator=True)
    async def user_balance(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        action: str,
        amount: Optional[int] = None,
        reason: str = "Admin adjustment via Discord"
    ):
        """Check or modify user balance with full validation."""
        await interaction.response.defer(ephemeral=True)

        guild_id = str(interaction.guild.id)
        user_id = str(user.id)

        try:
            # Load currency data
            currency_data = self.data_manager.load_guild_data(guild_id, 'currency')
            users = currency_data.get('users', {})

            # Get current balance
            user_data = users.get(user_id, {'balance': 0, 'total_earned': 0, 'total_spent': 0})
            current_balance = user_data.get('balance', 0)

            if action == "check":
                # Just show current balance
                embed = discord.Embed(
                    title="💰 User Balance",
                    color=discord.Color.blue()
                )
                embed.add_field(name="User", value=user.mention, inline=True)
                embed.add_field(name="Balance", value=f"{current_balance} coins", inline=True)
                embed.add_field(name="Total Earned", value=f"{user_data.get('total_earned', 0)} coins", inline=True)
                embed.add_field(name="Total Spent", value=f"{user_data.get('total_spent', 0)} coins", inline=True)

                await interaction.followup.send(embed=embed, ephemeral=True)
                return

            # Validate amount for modification actions
            if amount is None or amount < 0:
                await interaction.followup.send("❌ Amount must be a positive number for balance modifications.", ephemeral=True)
                return

            # Validate reason
            if not reason or len(reason.strip()) < 3:
                await interaction.followup.send("❌ Reason must be at least 3 characters long.", ephemeral=True)
                return

            # Calculate new balance
            if action == "set":
                new_balance = amount
                actual_change = amount - current_balance
            elif action == "add":
                new_balance = current_balance + amount
                actual_change = amount
            elif action == "subtract":
                new_balance = max(0, current_balance - amount)  # Prevent negative balance
                actual_change = -(min(amount, current_balance))
            else:
                await interaction.followup.send("❌ Invalid action.", ephemeral=True)
                return

            # Initialize user if doesn't exist
            if user_id not in users:
                users[user_id] = {
                    'balance': 0,
                    'total_earned': 0,
                    'total_spent': 0,
                    'created_at': datetime.now().isoformat(),
                    'is_active': True,
                    'username': user.name,
                    'display_name': user.display_name
                }
                user_data = users[user_id]

            # Update balance
            user_data['balance'] = new_balance

            # Update totals
            if actual_change > 0:
                user_data['total_earned'] = user_data.get('total_earned', 0) + actual_change
            elif actual_change < 0:
                user_data['total_spent'] = user_data.get('total_spent', 0) + abs(actual_change)

            # Create transaction log
            transaction_data = {
                'id': f"txn_{int(datetime.now().timestamp() * 1000)}",
                'user_id': user_id,
                'amount': actual_change,
                'balance_before': current_balance,
                'balance_after': new_balance,
                'type': 'admin_adjustment',
                'description': reason,
                'timestamp': datetime.now().isoformat(),
                'source': 'discord_admin'
            }

            # Save transaction
            transactions = self.data_manager.load_guild_data(guild_id, 'transactions') or []
            transactions.append(transaction_data)
            self.data_manager.save_guild_data(guild_id, 'transactions', transactions)

            # Save currency data
            self.data_manager.save_guild_data(guild_id, 'currency', currency_data)

            # Broadcast SSE event
            from backend import sse_manager
            sse_manager.broadcast_event('balance_update', {
                'guild_id': guild_id,
                'user_id': user_id,
                'balance_before': current_balance,
                'balance_after': new_balance,
                'change': actual_change,
                'reason': reason,
                'source': 'discord_admin'
            })

            # Create response embed
            embed = discord.Embed(
                title="✅ Balance Updated",
                color=discord.Color.green() if actual_change >= 0 else discord.Color.orange()
            )
            embed.add_field(name="User", value=user.mention, inline=True)
            embed.add_field(name="Action", value=f"{action.title()} {amount} coins", inline=True)
            embed.add_field(name="Previous Balance", value=f"{current_balance} coins", inline=True)
            embed.add_field(name="New Balance", value=f"{new_balance} coins", inline=True)
            embed.add_field(name="Change", value=f"{'+' if actual_change >= 0 else ''}{actual_change} coins", inline=True)
            embed.add_field(name="Reason", value=reason, inline=False)

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error in user_balance command: {e}")
            await interaction.followup.send("❌ An error occurred while updating the balance.", ephemeral=True)

    # ===== TASK MANAGEMENT =====

    @app_commands.command(name="create_task", description="Create a new task")
    @app_commands.describe(
        name="Task name",
        description="Task description",
        reward="Reward amount in coins",
        duration_hours="Time limit in hours",
        channel="Channel to post the task in (optional)",
        max_claims="Maximum number of claims (unlimited if not set)",
        category="Task category",
        role_reward="Role to grant upon completion (optional)"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def create_task(
        self,
        interaction: discord.Interaction,
        name: str,
        description: str,
        reward: int,
        duration_hours: int,
        channel: Optional[discord.TextChannel] = None,
        max_claims: Optional[int] = None,
        category: str = "General",
        role_reward: Optional[discord.Role] = None
    ):
        """Create a new task with Discord posting."""
        await interaction.response.defer()

        try:
            # Validate inputs
            if reward < 0:
                await interaction.followup.send("❌ Reward must be positive.", ephemeral=True)
                return
            if duration_hours < 1:
                await interaction.followup.send("❌ Duration must be at least 1 hour.", ephemeral=True)
                return
            if len(name.strip()) < 3:
                await interaction.followup.send("❌ Task name must be at least 3 characters.", ephemeral=True)
                return
            if len(description.strip()) < 10:
                await interaction.followup.send("❌ Task description must be at least 10 characters.", ephemeral=True)
                return

            guild_id = str(interaction.guild.id)

            # Get task channel from config if not provided
            if not channel:
                config = self.data_manager.load_guild_data(guild_id, 'config')
                task_channel_id = config.get('task_channel_id')
                if task_channel_id:
                    channel = interaction.guild.get_channel(int(task_channel_id))

            if not channel:
                await interaction.followup.send("❌ No task channel configured. Please specify a channel or set one in server config.", ephemeral=True)
                return

            # Load tasks data
            tasks_data = self.data_manager.load_guild_data(guild_id, 'tasks')
            if not tasks_data:
                tasks_data = {'tasks': {}, 'user_tasks': {}, 'settings': {'next_task_id': 1}}

            # Generate task ID
            task_id = str(tasks_data.get('settings', {}).get('next_task_id', 1))

            # Calculate expiry
            created = datetime.now(timezone.utc)
            expires_at = created + timedelta(hours=duration_hours)

            # Prepare task data
            task_data = {
                'id': int(task_id),
                'name': name.strip(),
                'description': description.strip(),
                'reward': reward,
                'duration_hours': duration_hours,
                'status': 'active',
                'created_at': created.isoformat(),
                'expires_at': expires_at.isoformat(),
                'channel_id': str(channel.id),
                'max_claims': max_claims or -1,
                'current_claims': 0,
                'assigned_users': [],
                'category': category,
                'role_name': role_reward.name if role_reward else None
            }

            # Create Discord embed
            embed = discord.Embed(
                title=f"📋 {task_data['name']}",
                description=task_data['description'],
                color=discord.Color.blue(),
                timestamp=created
            )
            embed.add_field(name="💰 Reward", value=f"{reward} coins", inline=True)
            embed.add_field(name="⏱️ Duration", value=f"{duration_hours} hours", inline=True)
            embed.add_field(name="Status", value="🟢 Active", inline=True)

            max_claims_text = "Unlimited" if max_claims == -1 or max_claims is None else str(max_claims)
            embed.add_field(name="👥 Max Claims", value=max_claims_text, inline=True)
            embed.add_field(name="🏷️ Category", value=category, inline=True)

            if role_reward:
                embed.add_field(name="🎭 Role Reward", value=role_reward.name, inline=True)

            embed.add_field(
                name="⏰ Expires",
                value=f"<t:{int(expires_at.timestamp())}:R>",
                inline=True
            )

            embed.set_footer(text=f"Task ID: {task_id} | Use /claim_task {task_id} to start")

            # Create claim button
            from cogs.tasks import TaskClaimView
            view = TaskClaimView(task_id)

            # Send message
            message = await channel.send(embed=embed, view=view)
            task_data['message_id'] = str(message.id)

            # Save task
            if 'tasks' not in tasks_data:
                tasks_data['tasks'] = {}
            tasks_data['tasks'][task_id] = task_data

            # Update next task ID
            if 'settings' not in tasks_data:
                tasks_data['settings'] = {}
            tasks_data['settings']['next_task_id'] = int(task_id) + 1

            self.data_manager.save_guild_data(guild_id, 'tasks', tasks_data)

            # Broadcast SSE event
            from backend import sse_manager
            sse_manager.broadcast_event('task_created', {
                'guild_id': guild_id,
                'task_id': task_id,
                'task': task_data
            })

            await interaction.followup.send(f"✅ Task created successfully! Posted in {channel.mention}")

        except Exception as e:
            logger.error(f"Error creating task: {e}")
            await interaction.followup.send("❌ Failed to create task.", ephemeral=True)

    @app_commands.command(name="list_tasks", description="List all tasks with filtering")
    @app_commands.describe(
        status="Filter by task status",
        category="Filter by category",
        user="Show tasks for specific user"
    )
    @app_commands.choices(status=[
        app_commands.Choice(name="Active", value="active"),
        app_commands.Choice(name="Completed", value="completed"),
        app_commands.Choice(name="Expired", value="expired"),
        app_commands.Choice(name="Cancelled", value="cancelled"),
        app_commands.Choice(name="All", value="all")
    ])
    async def list_tasks(
        self,
        interaction: discord.Interaction,
        status: str = "active",
        category: Optional[str] = None,
        user: Optional[discord.Member] = None
    ):
        """List tasks with advanced filtering."""
        await interaction.response.defer()

        guild_id = str(interaction.guild.id)
        target_user_id = str(user.id) if user else None

        try:
            # Debug logging
            print(f"Debug: Loading tasks for guild {guild_id}")
            tasks_data = self.data_manager.load_guild_data(guild_id, 'tasks')
            print(f"Debug: Loaded tasks_data: {tasks_data}")

            if not tasks_data:
                print("Debug: No tasks_data returned")
                await interaction.followup.send("📋 No tasks found. (Data Manager returned None)", ephemeral=True)
                return

            tasks = tasks_data.get('tasks', {})
            user_tasks = tasks_data.get('user_tasks', {})
            print(f"Debug: Found {len(tasks)} tasks and {len(user_tasks)} user task records")

            # Show some task details for debugging
            for task_id, task in list(tasks.items())[:3]:  # Show first 3 tasks
                print(f"Debug: Task {task_id}: {task.get('name')} - status: {task.get('status')}")

            if not tasks:
                print("Debug: Tasks dict is empty")
                await interaction.followup.send("📋 No tasks found. (Empty tasks data)", ephemeral=True)
                return

            # Filter tasks
            filtered_tasks = []
            for task_id, task in tasks.items():
                # Status filter
                if status != "all" and task['status'] != status:
                    continue

                # Category filter
                if category and task.get('category', '').lower() != category.lower():
                    continue

                # User filter
                user_task_data = None
                if target_user_id:
                    user_task_data = user_tasks.get(target_user_id, {}).get(task_id)

                filtered_tasks.append((task_id, task, user_task_data))

            print(f"Debug: After filtering, {len(filtered_tasks)} tasks match criteria")

            if not filtered_tasks:
                await interaction.followup.send(f"📋 No {status} tasks found after filtering.", ephemeral=True)
                return

            # Create paginated response
            embeds = []
            for i in range(0, len(filtered_tasks), 5):  # 5 tasks per embed
                embed = discord.Embed(
                    title=f"📋 {status.title()} Tasks" + (f" for {user.display_name}" if user else ""),
                    color=discord.Color.blue(),
                    timestamp=datetime.now(timezone.utc)
                )

                page_tasks = filtered_tasks[i:i+5]
                for task_id, task, user_task_data in page_tasks:
                    status_emoji = {
                        'active': '🟢',
                        'completed': '✅',
                        'expired': '⏰',
                        'cancelled': '❌'
                    }

                    task_info = f"{status_emoji.get(task['status'], '⚪')} **{task['name']}**\n"
                    task_info += f"💰 {task['reward']} coins | ⏱️ {task['duration_hours']}h\n"
                    task_info += f"👥 {task['current_claims']}"
                    if task['max_claims'] != -1:
                        task_info += f"/{task['max_claims']}"
                    task_info += " claims"

                    if user_task_data:
                        user_status = user_task_data['status']
                        task_info += f"\n🔸 Your status: {user_status.title()}"

                    embed.add_field(
                        name=f"Task #{task_id}",
                        value=task_info,
                        inline=False
                    )

                embed.set_footer(text=f"Page {len(embeds)+1} | Total: {len(filtered_tasks)} tasks")
                embeds.append(embed)

            # Send first embed
            if len(embeds) == 1:
                await interaction.followup.send(embed=embeds[0])
            else:
                # TODO: Implement pagination for multiple embeds
                await interaction.followup.send(embed=embeds[0])

        except Exception as e:
            print(f"Error listing tasks: {e}")
            await interaction.followup.send(f"❌ Failed to load tasks: {str(e)}", ephemeral=True)

    # ===== SHOP MANAGEMENT =====

    @app_commands.command(name="create_item", description="Create a new shop item")
    @app_commands.describe(
        name="Item name",
        description="Item description",
        price="Item price in coins",
        category="Item category",
        stock="Stock quantity (-1 for unlimited)",
        emoji="Item emoji",
        channel="Channel to post the item in (optional)"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def create_item(
        self,
        interaction: discord.Interaction,
        name: str,
        description: str,
        price: int,
        category: str = "general",
        stock: int = -1,
        emoji: str = "🛒",
        channel: Optional[discord.TextChannel] = None
    ):
        """Create a new shop item with Discord posting."""
        await interaction.response.defer()

        try:
            # Validate inputs
            if price < 0:
                await interaction.followup.send("❌ Price must be positive.", ephemeral=True)
                return
            if stock < -1:
                await interaction.followup.send("❌ Stock must be -1 (unlimited) or positive.", ephemeral=True)
                return

            guild_id = str(interaction.guild.id)

            # Get shop channel from config if not provided
            if not channel:
                config = self.data_manager.load_guild_data(guild_id, 'config')
                shop_channel_id = config.get('shop_channel_id')
                if shop_channel_id:
                    channel = interaction.guild.get_channel(int(shop_channel_id))

            if not channel:
                await interaction.followup.send("❌ No shop channel configured. Please specify a channel or set one in server config.", ephemeral=True)
                return

            # Generate item ID
            item_id = f"item_{int(datetime.now().timestamp() * 1000)}"

            # Prepare item data
            item_data = {
                'name': name.strip(),
                'description': description.strip(),
                'price': price,
                'category': category.lower(),
                'stock': stock,
                'emoji': emoji,
                'is_active': True,
                'created_at': datetime.now(timezone.utc).isoformat()
            }

            # Create Discord embed
            embed = discord.Embed(
                title=f"{emoji} {name}",
                description=description,
                color=discord.Color.green()
            )
            embed.add_field(name="💰 Price", value=f"{price} coins", inline=True)

            stock_text = "♾️ Unlimited" if stock == -1 else f"📦 {stock} available"
            embed.add_field(name="📦 Stock", value=stock_text, inline=True)
            embed.add_field(name="🏷️ Category", value=category.title(), inline=True)

            embed.set_footer(text=f"Item ID: {item_id} | Use /buy_item {item_id} to purchase")

            # Send message
            message = await channel.send(embed=embed)
            item_data['message_id'] = str(message.id)
            item_data['channel_id'] = str(channel.id)

            # Save to database
            currency_data = self.data_manager.load_guild_data(guild_id, 'currency')
            if 'shop_items' not in currency_data:
                currency_data['shop_items'] = {}

            currency_data['shop_items'][item_id] = item_data
            self.data_manager.save_guild_data(guild_id, 'currency', currency_data)

            # Broadcast SSE event
            from backend import sse_manager
            sse_manager.broadcast_event('shop_item_created', {
                'guild_id': guild_id,
                'item_id': item_id,
                'item': item_data
            })

            await interaction.followup.send(f"✅ Item created successfully! Posted in {channel.mention}")

        except Exception as e:
            logger.error(f"Error creating shop item: {e}")
            await interaction.followup.send("❌ Failed to create item.", ephemeral=True)

    @app_commands.command(name="list_items", description="List shop items with filtering")
    @app_commands.describe(
        category="Filter by category",
        in_stock_only="Show only items in stock"
    )
    async def list_items(
        self,
        interaction: discord.Interaction,
        category: Optional[str] = None,
        in_stock_only: bool = False
    ):
        """List shop items with filtering."""
        await interaction.response.defer()

        guild_id = str(interaction.guild.id)

        try:
            currency_data = self.data_manager.load_guild_data(guild_id, 'currency')
            shop_items = currency_data.get('shop_items', {})

            if not shop_items:
                await interaction.followup.send("🛒 No shop items found.", ephemeral=True)
                return

            # Filter items
            filtered_items = []
            for item_id, item in shop_items.items():
                if not item.get('is_active', True):
                    continue

                if category and item.get('category', '').lower() != category.lower():
                    continue

                if in_stock_only and item.get('stock', -1) == 0:
                    continue

                filtered_items.append((item_id, item))

            if not filtered_items:
                await interaction.followup.send("🛒 No items match your filters.", ephemeral=True)
                return

            # Create response embed
            embed = discord.Embed(
                title="🛒 Shop Items",
                color=discord.Color.green(),
                timestamp=datetime.now(timezone.utc)
            )

            for item_id, item in filtered_items[:10]:  # Limit to 10 items
                stock = item.get('stock', -1)
                stock_text = "♾️ Unlimited" if stock == -1 else f"📦 {stock}"

                item_info = f"{item.get('emoji', '🛒')} **{item['name']}**\n"
                item_info += f"💰 {item['price']} coins | {stock_text}\n"
                item_info += f"🏷️ {item.get('category', 'general').title()}"

                embed.add_field(
                    name=f"Item {item_id}",
                    value=item_info,
                    inline=False
                )

            if len(filtered_items) > 10:
                embed.set_footer(text=f"Showing 10 of {len(filtered_items)} items")

            await interaction.followup.send(embed=embed)

        except Exception as e:
            logger.error(f"Error listing shop items: {e}")
            await interaction.followup.send("❌ Failed to load shop items.", ephemeral=True)

    # ===== ANNOUNCEMENT MANAGEMENT =====

    @app_commands.command(name="create_announcement", description="Create and post an announcement")
    @app_commands.describe(
        title="Announcement title",
        content="Announcement content",
        channel="Channel to post in",
        mention_everyone="Mention @everyone",
        mention_role="Role to mention (optional)"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def create_announcement(
        self,
        interaction: discord.Interaction,
        title: str,
        content: str,
        channel: discord.TextChannel,
        mention_everyone: bool = False,
        mention_role: Optional[discord.Role] = None
    ):
        """Create and post an announcement."""
        await interaction.response.defer()

        try:
            guild_id = str(interaction.guild.id)

            # Create announcement via announcement manager
            announcement_data = {
                'title': title,
                'content': content,
                'channel_id': str(channel.id),
                'author_id': str(interaction.user.id),
                'author_name': interaction.user.display_name,
                'type': 'general',
                'embed': None,
                'mentions': {
                    'everyone': mention_everyone,
                    'roles': [str(mention_role.id)] if mention_role else [],
                    'users': []
                }
            }

            # Get announcement manager
            announcement_cog = self.bot.get_cog('Announcements')
            if not announcement_cog:
                await interaction.followup.send("❌ Announcement system not available.", ephemeral=True)
                return

            future = asyncio.run_coroutine_threadsafe(
                announcement_cog.announcement_manager.create_announcement(
                    guild_id=guild_id,
                    **announcement_data
                ),
                self.bot.loop
            )

            result = future.result(timeout=10)

            if result.get('success'):
                await interaction.followup.send(f"✅ Announcement posted in {channel.mention}")
            else:
                await interaction.followup.send(f"❌ Failed to post announcement: {result.get('error', 'Unknown error')}", ephemeral=True)

        except Exception as e:
            logger.error(f"Error creating announcement: {e}")
            await interaction.followup.send("❌ Failed to create announcement.", ephemeral=True)

    # ===== SERVER STATISTICS =====

    @app_commands.command(name="server_stats", description="View server statistics")
    async def server_stats(self, interaction: discord.Interaction):
        """Display comprehensive server statistics."""
        await interaction.response.defer()

        guild_id = str(interaction.guild.id)

        try:
            # Get various data
            config = self.data_manager.load_guild_data(guild_id, 'config')
            currency_data = self.data_manager.load_guild_data(guild_id, 'currency')
            tasks_data = self.data_manager.load_guild_data(guild_id, 'tasks')
            transactions = self.data_manager.load_guild_data(guild_id, 'transactions') or []

            # Calculate statistics
            users = currency_data.get('users', {})
            active_users = [u for u in users.values() if u.get('is_active', True)]
            total_balance = sum(u.get('balance', 0) for u in active_users)

            tasks = tasks_data.get('tasks', {})
            active_tasks = [t for t in tasks.values() if t['status'] == 'active']

            embed = discord.Embed(
                title=f"📊 {interaction.guild.name} Statistics",
                color=discord.Color.blue(),
                timestamp=datetime.now(timezone.utc)
            )

            embed.add_field(name="👥 Members", value=f"{interaction.guild.member_count}", inline=True)
            embed.add_field(name="💰 Active Users", value=f"{len(active_users)}", inline=True)
            embed.add_field(name="💵 Total Currency", value=f"{total_balance} coins", inline=True)

            embed.add_field(name="📋 Active Tasks", value=f"{len(active_tasks)}", inline=True)
            embed.add_field(name="🛒 Shop Items", value=f"{len(currency_data.get('shop_items', {}))}", inline=True)
            embed.add_field(name="💸 Transactions", value=f"{len(transactions)}", inline=True)

            # Recent activity
            if transactions and 'transactions' in transactions:
                recent_txns = transactions['transactions'][-5:]  # Last 5 transactions
                activity_text = ""
                for txn in reversed(recent_txns):
                    amount = txn.get('amount', 0)
                    activity_text += f"{'📈' if amount > 0 else '📉'} {abs(amount)} coins\n"
                embed.add_field(name="🔄 Recent Activity", value=activity_text or "None", inline=False)

            embed.set_footer(text=f"Server ID: {guild_id}")

            await interaction.followup.send(embed=embed)

        except Exception as e:
            logger.error(f"Error getting server stats: {e}")
            await interaction.followup.send("❌ Failed to load server statistics.", ephemeral=True)

    # ===== CONFIGURATION MANAGEMENT =====

    @app_commands.command(name="setcurrency", description="Customize server currency (symbol and name)")
    @app_commands.describe(
        symbol="Currency symbol (e.g., $, £, €)",
        name="Currency name (e.g., coins, points)"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def setcurrency(
        self,
        interaction: discord.Interaction,
        symbol: str,
        name: str = None
    ):
        """Customize server currency settings."""
        await interaction.response.defer(ephemeral=True)

        guild_id = str(interaction.guild.id)

        try:
            # Validate symbol
            if len(symbol.strip()) > 5:
                await interaction.followup.send("❌ Currency symbol must be 5 characters or less.", ephemeral=True)
                return

            # Update config
            config = self.data_manager.load_guild_data(guild_id, 'config')
            config['currency_symbol'] = symbol.strip()

            if name:
                if len(name.strip()) > 20:
                    await interaction.followup.send("❌ Currency name must be 20 characters or less.", ephemeral=True)
                    return
                config['currency_name'] = name.lower().strip()

            self.data_manager.save_guild_data(guild_id, 'config', config)
            self.data_manager.invalidate_cache(guild_id, 'config')

            currency_name = name or config.get('currency_name', 'coins')
            await interaction.followup.send(f"✅ Currency updated: {symbol} {currency_name}", ephemeral=True)

        except Exception as e:
            logger.error(f"Error setting currency: {e}")
            await interaction.followup.send("❌ Failed to update currency settings.", ephemeral=True)

    @app_commands.command(name="economystats", description="View detailed economy statistics")
    @app_commands.checks.has_permissions(administrator=True)
    async def economystats(self, interaction: discord.Interaction):
        """View detailed economy statistics for admins."""
        await interaction.response.defer(ephemeral=True)

        guild_id = str(interaction.guild.id)

        try:
            currency_data = self.data_manager.load_guild_data(guild_id, 'currency')
            transactions = self.data_manager.load_guild_data(guild_id, 'transactions') or []

            users = currency_data.get('users', {})

            # Calculate statistics
            total_users = len([u for u in users.values() if u.get('is_active', True)])
            total_balance = sum(u.get('balance', 0) for u in users.values() if u.get('is_active', True))
            total_earned = sum(u.get('total_earned', 0) for u in users.values() if u.get('is_active', True))
            total_spent = sum(u.get('total_spent', 0) for u in users.values() if u.get('is_active', True))

            # Transaction stats
            total_transactions = len(transactions) if isinstance(transactions, list) else len(transactions.get('transactions', []))
            recent_txns = self._get_recent_transactions(transactions, 10)

            config = self.data_manager.load_guild_data(guild_id, 'config')
            symbol = config.get('currency_symbol', '$')

            embed = discord.Embed(
                title="📊 Economy Statistics",
                description=f"Detailed economy stats for {interaction.guild.name}",
                color=discord.Color.gold(),
                timestamp=datetime.now(timezone.utc)
            )

            embed.add_field(name="👥 Active Users", value=f"{total_users}", inline=True)
            embed.add_field(name="💰 Total Balance", value=f"{symbol}{total_balance:,}", inline=True)
            embed.add_field(name="📈 Total Earned", value=f"{symbol}{total_earned:,}", inline=True)
            embed.add_field(name="📉 Total Spent", value=f"{symbol}{total_spent:,}", inline=True)
            embed.add_field(name="💸 Transactions", value=f"{total_transactions}", inline=True)

            if recent_txns:
                txn_text = "\n".join([
                    f"{symbol}{abs(txn.get('amount', 0)):+g} - {txn.get('description', 'Unknown')[:25]}"
                    for txn in recent_txns[:5]
                ])
                embed.add_field(name="🔄 Recent Transactions", value=txn_text, inline=False)

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error getting economy stats: {e}")
            await interaction.followup.send("❌ Failed to load economy statistics.", ephemeral=True)

    def _get_recent_transactions(self, transactions, limit=10):
        """Helper to get recent transactions."""
        if isinstance(transactions, list):
            return sorted(transactions, key=lambda x: x.get('timestamp', ''), reverse=True)[:limit]
        elif isinstance(transactions, dict):
            return transactions.get('transactions', [])[-limit:]
        return []

    @app_commands.command(name="serverconfig", description="View all server configuration settings")
    @app_commands.checks.has_permissions(administrator=True)
    async def serverconfig(self, interaction: discord.Interaction):
        """Display comprehensive server configuration."""
        await interaction.response.defer(ephemeral=True)

        guild_id = str(interaction.guild.id)

        try:
            config = self.data_manager.load_guild_data(guild_id, 'config')

            embed = discord.Embed(
                title="⚙️ Complete Server Configuration",
                description="All server settings and configuration",
                color=discord.Color.blue(),
                timestamp=datetime.now(timezone.utc)
            )

            # Basic settings
            embed.add_field(name="🤖 Prefix", value=f"`{config.get('prefix', '!')}`", inline=True)
            embed.add_field(name="💰 Currency", value=f"`{config.get('currency_symbol', '$')} {config.get('currency_name', 'coins')}`", inline=True)

            # Feature toggles
            features = []
            for feature in ['currency', 'tasks', 'shop', 'announcements', 'moderation']:
                enabled = config.get(f'feature_{feature}', True)
                icon = "✅" if enabled else "❌"
                features.append(f"{icon} {feature.title()}")
            embed.add_field(name="🔧 Features", value="\n".join(features), inline=False)

            # Channels
            channels = []
            channel_configs = {
                'task_channel_id': 'Task Channel',
                'shop_channel_id': 'Shop Channel',
                'welcome_channel': 'Welcome Channel',
                'log_channel': 'Log Channel'
            }
            for key, name in channel_configs.items():
                channel_id = config.get(key)
                if channel_id and interaction.guild:
                    channel = interaction.guild.get_channel(int(channel_id))
                    value = f"#{channel.name}" if channel else f"Unknown ({channel_id})"
                elif channel_id:
                    value = f"<#{channel_id}>"
                else:
                    value = "Not set"
                channels.append(f"📢 {name}: {value}")
            embed.add_field(name="📋 Channels", value="\n".join(channels), inline=False)

            # Roles
            admin_roles = config.get('admin_roles', [])
            moderator_roles = config.get('moderator_roles', [])

            if admin_roles:
                admin_role_names = []
                for role_id in admin_roles:
                    if interaction.guild:
                        role = interaction.guild.get_role(int(role_id))
                        admin_role_names.append(role.name if role else f"Unknown ({role_id})")
                embed.add_field(name="👑 Admin Roles", value=", ".join(admin_role_names), inline=False)

            if moderator_roles:
                mod_role_names = []
                for role_id in moderator_roles:
                    if interaction.guild:
                        role = interaction.guild.get_role(int(role_id))
                        mod_role_names.append(role.name if role else f"Unknown ({role_id})")
                embed.add_field(name="🛡️ Moderator Roles", value=", ".join(mod_role_names), inline=False)

            # Global settings
            embed.add_field(name="🌐 Global Tasks", value="Yes" if config.get('global_tasks') else "No", inline=True)
            embed.add_field(name="🛒 Global Shop", value="Yes" if config.get('global_shop') else "No", inline=True)

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error getting server config: {e}")
            await interaction.followup.send("❌ Failed to load server configuration.", ephemeral=True)

    @app_commands.command(name="set_config", description="Update server configuration")
    @app_commands.describe(
        setting="Configuration setting to update",
        value="New value for the setting"
    )
    @app_commands.choices(setting=[
        app_commands.Choice(name="Prefix", value="prefix"),
        app_commands.Choice(name="Currency Name", value="currency_name"),
        app_commands.Choice(name="Currency Symbol", value="currency_symbol"),
        app_commands.Choice(name="Task Channel", value="task_channel_id"),
        app_commands.Choice(name="Shop Channel", value="shop_channel_id"),
        app_commands.Choice(name="Log Channel", value="log_channel"),
        app_commands.Choice(name="Welcome Channel", value="welcome_channel")
    ])
    @app_commands.checks.has_permissions(administrator=True)
    async def set_config(
        self,
        interaction: discord.Interaction,
        setting: str,
        value: str
    ):
        """Update server configuration settings."""
        await interaction.response.defer(ephemeral=True)

        guild_id = str(interaction.guild.id)

        try:
            config = self.data_manager.load_guild_data(guild_id, 'config')

            # Validate and convert values
            if setting in ['task_channel_id', 'shop_channel_id', 'log_channel', 'welcome_channel']:
                # Convert channel mention/ID to ID
                if value.startswith('<#') and value.endswith('>'):
                    value = value[2:-1]
                # Validate channel exists
                try:
                    channel = interaction.guild.get_channel(int(value))
                    if not channel:
                        await interaction.followup.send("❌ Channel not found in this server.", ephemeral=True)
                        return
                    value = str(channel.id)
                except ValueError:
                    await interaction.followup.send("❌ Invalid channel format.", ephemeral=True)
                    return

            # Update config
            config[setting] = value
            self.data_manager.save_guild_data(guild_id, 'config', config)

            # Clear cache for immediate effect
            self.data_manager.invalidate_cache(guild_id, 'config')

            await interaction.followup.send(f"✅ {setting.replace('_', ' ').title()} updated successfully!", ephemeral=True)

        except Exception as e:
            logger.error(f"Error updating config: {e}")
            await interaction.followup.send("❌ Failed to update configuration.", ephemeral=True)

    @app_commands.command(name="set_admin_roles", description="Add admin roles to server configuration")
    @app_commands.describe(
        role1="First admin role to add",
        role2="Second admin role to add (optional)",
        role3="Third admin role to add (optional)",
        role4="Fourth admin role to add (optional)",
        role5="Fifth admin role to add (optional)"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def set_admin_roles(
        self,
        interaction: discord.Interaction,
        role1: discord.Role,
        role2: discord.Role = None,
        role3: discord.Role = None,
        role4: discord.Role = None,
        role5: discord.Role = None
    ):
        """Add admin roles (roles that can perform admin actions)."""
        await interaction.response.defer(ephemeral=True)

        # Collect provided roles
        roles = [role for role in [role1, role2, role3, role4, role5] if role is not None]
        if not roles:
            await interaction.followup.send("❌ Please specify at least one role.", ephemeral=True)
            return

        guild_id = str(interaction.guild.id)

        try:
            config = self.data_manager.load_guild_data(guild_id, 'config')

            # Get current admin roles
            current_admin_roles = set(config.get('admin_roles', []))
            current_admin_role_ids = {str(role.id) for role in roles}

            # Add new roles
            current_admin_roles.update(current_admin_role_ids)
            config['admin_roles'] = list(current_admin_roles)

            self.data_manager.save_guild_data(guild_id, 'config', config)
            self.data_manager.invalidate_cache(guild_id, 'config')

            role_names = [role.name for role in roles]
            await interaction.followup.send(f"✅ Added {len(roles)} admin role(s): {', '.join(role_names)}", ephemeral=True)

        except Exception as e:
            logger.error(f"Error setting admin roles: {e}")
            await interaction.followup.send("❌ Failed to update admin roles.", ephemeral=True)

    @app_commands.command(name="set_moderator_roles", description="Add moderator roles to server configuration")
    @app_commands.describe(
        role1="First moderator role to add",
        role2="Second moderator role to add (optional)",
        role3="Third moderator role to add (optional)",
        role4="Fourth moderator role to add (optional)",
        role5="Fifth moderator role to add (optional)"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def set_moderator_roles(
        self,
        interaction: discord.Interaction,
        role1: discord.Role,
        role2: discord.Role = None,
        role3: discord.Role = None,
        role4: discord.Role = None,
        role5: discord.Role = None
    ):
        """Add moderator roles (roles that can perform moderation actions)."""
        await interaction.response.defer(ephemeral=True)

        # Collect provided roles
        roles = [role for role in [role1, role2, role3, role4, role5] if role is not None]
        if not roles:
            await interaction.followup.send("❌ Please specify at least one role.", ephemeral=True)
            return

        guild_id = str(interaction.guild.id)

        try:
            config = self.data_manager.load_guild_data(guild_id, 'config')

            # Get current moderator roles
            current_moderator_roles = set(config.get('moderator_roles', []))
            current_moderator_role_ids = {str(role.id) for role in roles}

            # Add new roles
            current_moderator_roles.update(current_moderator_role_ids)
            config['moderator_roles'] = list(current_moderator_roles)

            self.data_manager.save_guild_data(guild_id, 'config', config)
            self.data_manager.invalidate_cache(guild_id, 'config')

            role_names = [role.name for role in roles]
            await interaction.followup.send(f"✅ Added {len(roles)} moderator role(s): {', '.join(role_names)}", ephemeral=True)

        except Exception as e:
            logger.error(f"Error setting moderator roles: {e}")
            await interaction.followup.send("❌ Failed to update moderator roles.", ephemeral=True)

    @app_commands.command(name="remove_admin_roles", description="Remove admin roles from server configuration")
    @app_commands.describe(
        role1="First admin role to remove",
        role2="Second admin role to remove (optional)",
        role3="Third admin role to remove (optional)",
        role4="Fourth admin role to remove (optional)",
        role5="Fifth admin role to remove (optional)"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def remove_admin_roles(
        self,
        interaction: discord.Interaction,
        role1: discord.Role,
        role2: discord.Role = None,
        role3: discord.Role = None,
        role4: discord.Role = None,
        role5: discord.Role = None
    ):
        """Remove admin roles."""
        await interaction.response.defer(ephemeral=True)

        # Collect provided roles
        roles = [role for role in [role1, role2, role3, role4, role5] if role is not None]
        if not roles:
            await interaction.followup.send("❌ Please specify at least one role.", ephemeral=True)
            return

        guild_id = str(interaction.guild.id)

        try:
            config = self.data_manager.load_guild_data(guild_id, 'config')

            # Get current admin roles
            current_admin_roles = set(config.get('admin_roles', []))
            roles_to_remove = {str(role.id) for role in roles}

            # Remove roles
            current_admin_roles -= roles_to_remove
            config['admin_roles'] = list(current_admin_roles)

            self.data_manager.save_guild_data(guild_id, 'config', config)
            self.data_manager.invalidate_cache(guild_id, 'config')

            role_names = [role.name for role in roles]
            await interaction.followup.send(f"✅ Removed {len(roles)} admin role(s): {', '.join(role_names)}", ephemeral=True)

        except Exception as e:
            logger.error(f"Error removing admin roles: {e}")
            await interaction.followup.send("❌ Failed to remove admin roles.", ephemeral=True)

    @app_commands.command(name="remove_moderator_roles", description="Remove moderator roles from server configuration")
    @app_commands.describe(
        role1="First moderator role to remove",
        role2="Second moderator role to remove (optional)",
        role3="Third moderator role to remove (optional)",
        role4="Fourth moderator role to remove (optional)",
        role5="Fifth moderator role to remove (optional)"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def remove_moderator_roles(
        self,
        interaction: discord.Interaction,
        role1: discord.Role,
        role2: discord.Role = None,
        role3: discord.Role = None,
        role4: discord.Role = None,
        role5: discord.Role = None
    ):
        """Remove moderator roles."""
        await interaction.response.defer(ephemeral=True)

        # Collect provided roles
        collected_roles = [role for role in [role1, role2, role3, role4, role5] if role is not None]
        if not collected_roles:
            await interaction.followup.send("❌ Please specify at least one role.", ephemeral=True)
            return

        guild_id = str(interaction.guild.id)

        try:
            config = self.data_manager.load_guild_data(guild_id, 'config')

            # Get current moderator roles
            current_moderator_roles = set(config.get('moderator_roles', []))
            roles_to_remove = {str(role.id) for role in collected_roles}

            # Remove roles
            current_moderator_roles -= roles_to_remove
            config['moderator_roles'] = list(current_moderator_roles)

            self.data_manager.save_guild_data(guild_id, 'config', config)
            self.data_manager.invalidate_cache(guild_id, 'config')

            role_names = [role.name for role in roles]
            await interaction.followup.send(f"✅ Removed {len(roles)} moderator role(s): {', '.join(role_names)}", ephemeral=True)

        except Exception as e:
            logger.error(f"Error removing moderator roles: {e}")
            await interaction.followup.send("❌ Failed to remove moderator roles.", ephemeral=True)

    @app_commands.command(name="clear_roles", description="Clear all admin or moderator roles")
    @app_commands.describe(
        role_type="Type of roles to clear"
    )
    @app_commands.choices(role_type=[
        app_commands.Choice(name="Admin Roles", value="admin"),
        app_commands.Choice(name="Moderator Roles", value="moderator"),
        app_commands.Choice(name="All Roles", value="all")
    ])
    @app_commands.checks.has_permissions(administrator=True)
    async def clear_roles(
        self,
        interaction: discord.Interaction,
        role_type: str
    ):
        """Clear admin or moderator roles."""
        await interaction.response.defer(ephemeral=True)

        guild_id = str(interaction.guild.id)

        try:
            config = self.data_manager.load_guild_data(guild_id, 'config')

            if role_type in ['admin', 'all']:
                config['admin_roles'] = []
                admin_cleared = True
            else:
                admin_cleared = False

            if role_type in ['moderator', 'all']:
                config['moderator_roles'] = []
                moderator_cleared = True
            else:
                moderator_cleared = False

            self.data_manager.save_guild_data(guild_id, 'config', config)
            self.data_manager.invalidate_cache(guild_id, 'config')

            message = ""
            if admin_cleared and moderator_cleared:
                message = "✅ Cleared all admin and moderator roles."
            elif admin_cleared:
                message = "✅ Cleared all admin roles."
            elif moderator_cleared:
                message = "✅ Cleared all moderator roles."

            await interaction.followup.send(message, ephemeral=True)

        except Exception as e:
            logger.error(f"Error clearing roles: {e}")
            await interaction.followup.send("❌ Failed to clear roles.", ephemeral=True)

    @app_commands.command(name="get_config", description="View current server configuration")
    async def get_config(self, interaction: discord.Interaction):
        """Display current server configuration."""
        await interaction.response.defer(ephemeral=True)

        guild_id = str(interaction.guild.id)

        try:
            config = self.data_manager.load_guild_data(guild_id, 'config')

            embed = discord.Embed(
                title="⚙️ Server Configuration",
                color=discord.Color.blue(),
                timestamp=datetime.now(timezone.utc)
            )

            embed.add_field(name="Prefix", value=config.get('prefix', '!'), inline=True)
            embed.add_field(name="Currency Name", value=config.get('currency_name', 'coins'), inline=True)
            embed.add_field(name="Currency Symbol", value=config.get('currency_symbol', '$'), inline=True)

            # Channel configurations
            task_channel_id = config.get('task_channel_id')
            shop_channel_id = config.get('shop_channel_id')
            log_channel_id = config.get('log_channel')
            welcome_channel_id = config.get('welcome_channel')

            embed.add_field(
                name="Task Channel",
                value=f"<#{task_channel_id}>" if task_channel_id else "Not set",
                inline=True
            )
            embed.add_field(
                name="Shop Channel",
                value=f"<#{shop_channel_id}>" if shop_channel_id else "Not set",
                inline=True
            )
            embed.add_field(
                name="Log Channel",
                value=f"<#{log_channel_id}>" if log_channel_id else "Not set",
                inline=True
            )
            embed.add_field(
                name="Welcome Channel",
                value=f"<#{welcome_channel_id}>" if welcome_channel_id else "Not set",
                inline=True
            )

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error getting config: {e}")
            await interaction.followup.send("❌ Failed to load configuration.", ephemeral=True)

    @app_commands.command(name="set_bot_status", description="Set the bot's status message (saved across restarts)")
    @app_commands.describe(
        message="The status message (leave empty to reset to default)",
        type="The activity type"
    )
    @app_commands.choices(type=[
        app_commands.Choice(name="Watching", value="watching"),
        app_commands.Choice(name="Playing", value="playing"),
        app_commands.Choice(name="Listening to", value="listening"),
        app_commands.Choice(name="Streaming", value="streaming")
    ])
    @app_commands.checks.has_permissions(administrator=True)
    async def set_bot_status(
        self,
        interaction: discord.Interaction,
        message: str = None,
        type: str = "watching"
    ):
        """Set bot status message that persists across restarts."""
        await interaction.response.defer(ephemeral=True)

        # Allow empty message for specific use cases
        if message is None or message.strip() == "":
            # Reset to default based on guild count
            guild_count = len(interaction.client.guilds)
            message = f"{guild_count} servers"
            type = "watching"

        try:
            # First, try the database approach
            guild_result = self.data_manager.supabase.table('guilds').select('bot_status_message, bot_status_type, server_name').eq('guild_id', str(interaction.guild.id)).execute()

            guild_data = None
            server_name = interaction.guild.name if interaction.guild else 'Unknown Server'

            if not guild_result.data or len(guild_result.data) == 0:
                await interaction.followup.send("❌ Guild configuration not found.", ephemeral=True)
                return

            guild_data = guild_result.data[0]

        except Exception as db_error:
            # Database columns don't exist yet
            if 'bot_status_message does not exist' in str(db_error):
                embed = discord.Embed(
                    title="⚠️ Database Update Required",
                    description="The bot status feature requires a database schema update.",
                    color=discord.Color.orange()
                )
                embed.add_field(
                    name="Required SQL",
                    value="```sql\nALTER TABLE guilds\nADD COLUMN IF NOT EXISTS bot_status_message TEXT,\nADD COLUMN IF NOT EXISTS bot_status_type TEXT DEFAULT 'watching';\n```",
                    inline=False
                )
                embed.add_field(
                    name="Instructions",
                    value="Run this SQL in your Supabase SQL editor, then try the command again.",
                    inline=False
                )

                # Still apply the status temporarily for testing
                activity_type_map = {
                    'watching': discord.ActivityType.watching,
                    'playing': discord.ActivityType.playing,
                    'listening': discord.ActivityType.listening,
                    'streaming': discord.ActivityType.streaming
                }

                try:
                    activity = discord.Activity(
                        type=activity_type_map.get(type, discord.ActivityType.watching),
                        name=message
                    )
                    await interaction.client.change_presence(activity=activity)

                    embed.add_field(
                        name="Status Set Temporarily",
                        value=f"Type: **{type.title()}**\nMessage: **{message}**",
                        inline=False
                    )
                except Exception as status_error:
                    logger.error(f"Error setting temp status: {status_error}")

                await interaction.followup.send(embed=embed, ephemeral=True)
                return
            else:
                # Other database error
                await interaction.followup.send("❌ Database connection error.", ephemeral=True)
                return

        try:
            # Update database
            self.data_manager.supabase.table('guilds').update({
                'bot_status_message': message,
                'bot_status_type': type
            }).eq('guild_id', str(interaction.guild.id)).execute()

            # Clear cache
            self.data_manager.invalidate_cache(str(interaction.guild.id), 'config')

            # Apply status immediately
            activity_type_map = {
                'watching': discord.ActivityType.watching,
                'playing': discord.ActivityType.playing,
                'listening': discord.ActivityType.listening,
                'streaming': discord.ActivityType.streaming
            }

            activity = discord.Activity(
                type=activity_type_map.get(type, discord.ActivityType.watching),
                name=message
            )

            await interaction.client.change_presence(activity=activity)

            await interaction.followup.send(f"✅ Bot status updated!\n🔸 Type: **{type.title()}**\n🔸 Message: **{message}**", ephemeral=True)

        except Exception as e:
            logger.error(f"Error setting bot status: {e}")
            await interaction.followup.send("❌ Failed to update bot status.", ephemeral=True)

    @app_commands.command(name="get_bot_status", description="View current bot status settings")
    async def get_bot_status(self, interaction: discord.Interaction):
        """View current bot status settings."""
        await interaction.response.defer(ephemeral=True)

        server_name = interaction.guild.name if interaction.guild else 'Unknown Server'

        try:
            # Load current status from database
            guild_result = self.data_manager.supabase.table('guilds').select('bot_status_message, bot_status_type, server_name').eq('guild_id', str(interaction.guild.id)).execute()

            if not guild_result.data or len(guild_result.data) == 0:
                await interaction.followup.send("❌ Guild configuration not found.", ephemeral=True)
                return

            guild_data = guild_result.data[0]
            current_message = guild_data.get('bot_status_message')
            current_type = guild_data.get('bot_status_type', 'watching')

            embed = discord.Embed(
                title="🤖 Bot Status Settings",
                description=f"Current settings for **{server_name}**",
                color=discord.Color.blue(),
                timestamp=datetime.now(timezone.utc)
            )

            embed.add_field(
                name="Activity Type",
                value=current_type.title(),
                inline=True
            )

            embed.add_field(
                name="Status Message",
                value=current_message or "Default (server count)",
                inline=True
            )

            # Get current presence
            presence = interaction.client.user.activity
            if presence:
                status_type = str(presence.type).split('.')[1].title()
                embed.add_field(
                    name="Current Live Status",
                    value=f"{status_type}: {presence.name}",
                    inline=False
                )
            else:
                embed.add_field(
                    name="Current Live Status",
                    value="None set",
                    inline=False
                )

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as db_error:
            # Database columns don't exist yet
            if 'bot_status_message does not exist' in str(db_error):
                embed = discord.Embed(
                    title="⚠️ Database Update Required",
                    description="The bot status feature requires a database schema update.",
                    color=discord.Color.orange()
                )
                embed.add_field(
                    name="Required SQL",
                    value="```sql\nALTER TABLE guilds\nADD COLUMN IF NOT EXISTS bot_status_message TEXT,\nADD COLUMN IF NOT EXISTS bot_status_type TEXT DEFAULT 'watching';\n```",
                    inline=False
                )
                embed.add_field(
                    name="Instructions",
                    value="Run this SQL in your Supabase SQL editor to enable bot status management.",
                    inline=False
                )

                # Show current status for information
                presence = interaction.client.user.activity
                if presence:
                    status_type = str(presence.type).split('.')[1].title()
                    embed.add_field(
                        name="Current Live Status",
                        value=f"{status_type}: {presence.name}",
                        inline=False
                    )
