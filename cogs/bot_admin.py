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
                    task_info += f"👥 {task['current_claims']} / {task.get('max_claims', '∞')} claims"

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

async def setup(bot):
    """Setup the bot admin cog."""
    cog = BotAdmin(bot)
    # Set managers after cog creation
    cog.data_manager = getattr(bot, 'data_manager', None)
    cog.transaction_manager = getattr(bot, 'transaction_manager', None)
    await bot.add_cog(cog)
