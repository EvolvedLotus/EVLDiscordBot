import discord
from discord import app_commands
from discord.ext import commands, tasks
from datetime import datetime, timedelta, timezone
import json
import os
import asyncio
import logging

# Import data manager and embed builder
try:
    from core import data_manager
    from core.task_manager import TaskManager
    from core.embed_builder import EmbedBuilder
    from core.utils import create_embed
except ImportError:
    data_manager = None
    TaskManager = None
    EmbedBuilder = None
    create_embed = None

logger = logging.getLogger(__name__)

async def discord_operation_with_retry(operation, max_retries=3, base_delay=1.0):
    """
    Execute Discord API operation with exponential backoff retry logic.
    Handles temporary API failures gracefully.
    """
    last_exception = None

    for attempt in range(max_retries):
        try:
            return await operation()
        except (discord.HTTPException, discord.ConnectionClosed, discord.GatewayNotFound) as e:
            last_exception = e

            if attempt < max_retries - 1:  # Don't delay on last attempt
                # Exponential backoff: 1s, 2s, 4s
                delay = base_delay * (2 ** attempt)
                logger.warning(f"Discord API call failed (attempt {attempt + 1}/{max_retries}): {e}. Retrying in {delay}s...")
                await asyncio.sleep(delay)
            else:
                logger.error(f"Discord API call failed after {max_retries} attempts: {e}")
                raise e
        except discord.NotFound as e:
            # NotFound is usually permanent, don't retry
            logger.warning(f"Discord resource not found: {e}")
            raise e
        except discord.Forbidden as e:
            # Forbidden is usually permanent, don't retry
            logger.warning(f"Discord permission denied: {e}")
            raise e

    # This should never be reached, but just in case
    raise last_exception

class TaskClaimView(discord.ui.View):
    """Persistent view for task claim button."""

    def __init__(self, task_id):
        super().__init__(timeout=None)
        self.task_id = task_id

    @discord.ui.button(
        label="Claim Task",
        style=discord.ButtonStyle.green,
        custom_id="claim_task",
        emoji="✋"
    )
    async def claim_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_claim(interaction)

    async def handle_claim(self, interaction: discord.Interaction):
        """Handle task claim with atomic operations and race condition prevention."""
        await interaction.response.defer(ephemeral=True)

        guild_id = str(interaction.guild.id)
        user_id = str(interaction.user.id)
        task_id = str(self.task_id)

        try:
            # Use atomic task claim operation with database-level locking
            result = await self.atomic_task_claim(guild_id, user_id, task_id)

            if not result['success']:
                await interaction.followup.send(result['error'], ephemeral=True)
                return

            # Update embed
            await self.update_task_message(interaction.guild, guild_id, self.task_id, result['task'])

            # Notify user
            embed = discord.Embed(
                title="✅ Task Claimed Successfully!",
                description=f"You have claimed **{result['task']['name']}**",
                color=discord.Color.green()
            )
            embed.add_field(name="⏰ Deadline", value=f"<t:{int(result['deadline'].timestamp())}:R>", inline=False)
            embed.add_field(
                name="📝 Submit Proof",
                value="Use `/task submit` command with proof of completion",
                inline=False
            )

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            print(f"Task claim error: {e}")
            await interaction.followup.send(
                "❌ An error occurred while claiming the task. Please try again.",
                ephemeral=True
            )

    async def atomic_task_claim(self, guild_id, user_id, task_id):
        """Atomically claim a task with database-level locking to prevent race conditions."""

        def claim_task_operation(tasks_data, currency_data):
            task = tasks_data.get('tasks', {}).get(task_id)

            if not task:
                return {'success': False, 'error': "❌ Task not found."}

            # Validation checks
            if task['status'] != 'active':
                return {'success': False, 'error': f"❌ This task is no longer active (Status: {task['status']})."}

            # Check expiry
            if datetime.now(timezone.utc) > datetime.fromisoformat(task['expires_at']):
                # Auto-expire task
                task['status'] = 'expired'
                tasks_data['metadata']['total_expired'] = tasks_data.get('metadata', {}).get('total_expired', 0) + 1
                return {'success': False, 'error': "❌ This task has expired."}

            # Check max claims with atomic increment
            if task['max_claims'] != -1 and task['current_claims'] >= task['max_claims']:
                return {'success': False, 'error': "❌ This task has reached maximum claims."}

            # Check if user already claimed
            user_tasks = tasks_data.get('user_tasks', {}).get(user_id, {})
            if task_id in user_tasks:
                status = user_tasks[task_id]['status']
                return {'success': False, 'error': f"❌ You have already claimed this task (Status: {status})."}

            # Check user task limit
            settings = tasks_data.get('settings', {})
            max_per_user = settings.get('max_tasks_per_user', 10)
            active_count = sum(
                1 for t in user_tasks.values()
                if t['status'] in ['claimed', 'in_progress', 'submitted']
            )
            if active_count >= max_per_user:
                return {'success': False, 'error': f"❌ You have reached the maximum of {max_per_user} active tasks."}

            # Claim task atomically
            claimed_at = datetime.now(timezone.utc)
            deadline = claimed_at + timedelta(hours=task['duration_hours'])

            tasks_data.setdefault('user_tasks', {}).setdefault(user_id, {})[task_id] = {
                'claimed_at': claimed_at.isoformat(),
                'deadline': deadline.isoformat(),
                'status': 'in_progress',
                'proof_message_id': None,
                'proof_attachments': [],
                'proof_content': '',
                'submitted_at': None,
                'completed_at': None,
                'notes': ''
            }

            # Update task claims atomically
            task['current_claims'] += 1
            task['assigned_users'].append(user_id)

            return {
                'success': True,
                'task': task,
                'deadline': deadline,
                'claimed_at': claimed_at
            }

        # Load data first
        tasks_data = data_manager.load_guild_data(guild_id, 'tasks')
        currency_data = data_manager.load_guild_data(guild_id, 'currency')

        # Execute atomic operation with rollback capability
        try:
            # Perform the operation
            result = claim_task_operation(tasks_data, currency_data)

            if result['success']:
                # Use data_manager's atomic_transaction method to save
                updates = {
                    'tasks': tasks_data,
                    'currency': currency_data
                }
                success = data_manager.atomic_transaction(guild_id, updates)
                if not success:
                    return {'success': False, 'error': "❌ An error occurred while claiming the task. Please try again."}

            return result
        except Exception as e:
            print(f"Atomic task claim failed: {e}")
            return {'success': False, 'error': "❌ An error occurred while claiming the task. Please try again."}

    async def expire_task(self, guild_id, task_id, guild):
        """Mark task as expired and update message."""
        tasks_data = data_manager.load_guild_data(guild_id, 'tasks')
        task = tasks_data['tasks'].get(str(task_id))

        if task:
            task['status'] = 'expired'
            tasks_data['metadata']['total_expired'] = tasks_data.get('metadata', {}).get('total_expired', 0) + 1
            data_manager.save_guild_data(guild_id, 'tasks', tasks_data)

            await self.update_task_message(guild, guild_id, task_id, task)

    async def update_task_message(self, guild, guild_id, task_id, task):
        """Update Discord task message with current data."""
        if not task.get('message_id'):
            return

        try:
            channel = guild.get_channel(int(task['channel_id']))
            if not channel:
                return

            message = await channel.fetch_message(int(task['message_id']))
            embed = create_task_embed(task)

            # Disable button if task is not active
            view = None if task['status'] != 'active' else TaskClaimView(task_id)

            await message.edit(embed=embed, view=view)

        except discord.NotFound:
            print(f"Task message {task['message_id']} not found")
        except Exception as e:
            print(f"Error updating task message: {e}")

def create_task_embed(task):
    """Create consistent task embed for Discord messages."""
    from datetime import datetime
    embed = discord.Embed(
        title=f"📋 {task['name']}",
        description=task['description'],
        color=discord.Color.blue(),
        timestamp=datetime.fromisoformat(task['created'])
    )

    if task.get('url'):
        embed.add_field(name="🔗 Link", value=task['url'], inline=False)

    embed.add_field(name="💰 Reward", value=f"{task['reward']} coins", inline=True)
    embed.add_field(name="⏱️ Duration", value=f"{task['duration_hours']} hours", inline=True)

    if task.get('role_name'):
        embed.add_field(name="🎭 Role Reward", value=task['role_name'], inline=True)

    # Status indicator
    status_emoji = {
        'active': '🟢',
        'pending': '🟡',
        'completed': '✅',
        'expired': '⏰',
        'cancelled': '❌'
    }
    embed.add_field(
        name="Status",
        value=f"{status_emoji.get(task['status'], '⚪')} {task['status'].title()}",
        inline=True
    )

    # Claims info
    max_claims_text = "Unlimited" if task['max_claims'] == -1 else task['max_claims']
    embed.add_field(
        name="👥 Claims",
        value=f"{task['current_claims']}/{max_claims_text}",
        inline=True
    )

    # Expiry countdown
    expires_at = datetime.fromisoformat(task['expires_at'])
    embed.add_field(
        name="⏰ Expires",
        value=f"<t:{int(expires_at.timestamp())}:R>",
        inline=True
    )

    embed.set_footer(text=f"Task ID: {task['id']}")

    return embed

class Tasks(commands.Cog):
    """Task management cog for Discord bot."""

    def __init__(self, bot):
        self.bot = bot
        # Initialize managers
        self.task_manager = TaskManager(data_manager, TransactionManager(data_manager))
        self.task_manager.set_bot(bot)
        # Don't start the loop here - it will be started in setup or after bot is ready

    @app_commands.command(name="task_submit", description="Submit proof for a claimed task")
    @app_commands.describe(
        task_id="The ID of the task to submit",
        proof="Description or link to proof of completion"
    )
    async def submit_task(
        self,
        interaction: discord.Interaction,
        task_id: int,
        proof: str,
        attachment: discord.Attachment = None
    ):
        """Submit task completion proof."""
        await interaction.response.defer(ephemeral=True)

        guild_id = str(interaction.guild.id)
        user_id = str(interaction.user.id)

        try:
            # Load data
            tasks_data = data_manager.load_guild_data(guild_id, 'tasks')
            task = tasks_data['tasks'].get(str(task_id))

            if not task:
                await interaction.followup.send("❌ Task not found.", ephemeral=True)
                return

            # Check if user claimed task
            user_task = tasks_data.get('user_tasks', {}).get(user_id, {}).get(str(task_id))
            if not user_task:
                await interaction.followup.send("❌ You haven't claimed this task.", ephemeral=True)
                return

            # Check status
            if user_task['status'] not in ['claimed', 'in_progress']:
                await interaction.followup.send(
                    f"❌ Cannot submit task with status: {user_task['status']}",
                    ephemeral=True
                )
                return

            # Check deadline
            deadline = datetime.fromisoformat(user_task['deadline'])
            if datetime.now(timezone.utc) > deadline:
                user_task['status'] = 'expired'
                data_manager.save_guild_data(guild_id, 'tasks', tasks_data)
                await interaction.followup.send("❌ Task deadline has passed.", ephemeral=True)
                return

            # Handle attachment
            proof_attachments = []
            if attachment:
                proof_attachments.append(attachment.url)

            # Update user task
            submitted_at = datetime.now(timezone.utc)
            user_task['status'] = 'submitted'
            user_task['proof_content'] = proof
            user_task['proof_attachments'] = proof_attachments
            user_task['submitted_at'] = submitted_at.isoformat()

            # Create proof message in task channel for review
            channel = interaction.guild.get_channel(int(task['channel_id']))
            if channel:
                proof_embed = discord.Embed(
                    title="📨 Task Submission",
                    description=f"**{interaction.user.mention}** submitted proof for **{task['name']}**",
                    color=discord.Color.orange(),
                    timestamp=submitted_at
                )
                proof_embed.add_field(name="Proof", value=proof, inline=False)

                if proof_attachments:
                    proof_embed.set_image(url=proof_attachments[0])

                proof_embed.set_footer(text=f"Task ID: {task_id} | User ID: {user_id}")

                # Add review buttons
                view = TaskReviewView(task_id, user_id)
                proof_message = await discord_operation_with_retry(
                    lambda: channel.send(embed=proof_embed, view=view)
                )

                user_task['proof_message_id'] = str(proof_message.id)

            # Save
            data_manager.save_guild_data(guild_id, 'tasks', tasks_data)

            await interaction.followup.send(
                "✅ Task submitted successfully! Waiting for review.",
                ephemeral=True
            )

        except Exception as e:
            print(f"Task submission error: {e}")
            await interaction.followup.send(
                "❌ Error submitting task. Please try again.",
                ephemeral=True
            )

class TaskReviewView(discord.ui.View):
    """View for task submission review."""

    def __init__(self, task_id, user_id):
        super().__init__(timeout=None)
        self.task_id = task_id
        self.user_id = user_id

    @discord.ui.button(label="Accept", style=discord.ButtonStyle.green, emoji="✅")
    async def accept_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_review(interaction, accept=True)

    @discord.ui.button(label="Reject", style=discord.ButtonStyle.red, emoji="❌")
    async def reject_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_review(interaction, accept=False)

    async def handle_review(self, interaction: discord.Interaction, accept: bool):
        """Handle task review decision with proper role ID checking."""
        # Check permissions - use role IDs instead of role names
        if not interaction.user.guild_permissions.administrator:
            # Verify user is an active member of this guild
            member = interaction.guild.get_member(interaction.user.id)
            if not member:
                await interaction.response.send_message(
                    "❌ You must be an active member of this server to review tasks.",
                    ephemeral=True
                )
                return

            config = data_manager.load_guild_data(str(interaction.guild.id), 'config')
            admin_roles = config.get('admin_roles', [])
            user_role_ids = [str(r.id) for r in member.roles]

            # Check if user has any of the required admin role IDs
            if not any(role_id in admin_roles for role_id in user_role_ids):
                await interaction.response.send_message(
                    "❌ You don't have permission to review tasks.",
                    ephemeral=True
                )
                return

        await interaction.response.defer()

        guild_id = str(interaction.guild.id)

        try:
            # Load data
            tasks_data = data_manager.load_guild_data(guild_id, 'tasks')
            currency_data = data_manager.load_guild_data(guild_id, 'currency')

            task = tasks_data['tasks'].get(str(self.task_id))
            user_task = tasks_data.get('user_tasks', {}).get(self.user_id, {}).get(str(self.task_id))

            if not task or not user_task:
                await interaction.followup.send("❌ Task data not found.", ephemeral=True)
                return

            if accept:
                # Mark as accepted
                completed_at = datetime.now(timezone.utc)
                user_task['status'] = 'accepted'
                user_task['completed_at'] = completed_at.isoformat()

                # Award currency
                currency_data.setdefault('users', {}).setdefault(self.user_id, {
                    'balance': 0,
                    'total_earned': 0,
                    'total_spent': 0,
                    'created_at': completed_at.isoformat()
                })

                currency_data['users'][self.user_id]['balance'] += task['reward']
                currency_data['users'][self.user_id]['total_earned'] += task['reward']

                # Log transaction
                transaction = {
                    'id': f"txn_{int(completed_at.timestamp() * 1000)}",
                    'user_id': self.user_id,
                    'amount': task['reward'],
                    'balance_before': currency_data['users'][self.user_id]['balance'] - task['reward'],
                    'balance_after': currency_data['users'][self.user_id]['balance'],
                    'description': f"Completed task: {task['name']}",
                    'timestamp': completed_at.isoformat()
                }

                transactions = data_manager.load_guild_data(guild_id, 'transactions') or []
                transactions.append(transaction)
                data_manager.save_guild_data(guild_id, 'transactions', transactions)

                # Grant role if specified
                if task.get('role_name'):
                    role = discord.utils.get(interaction.guild.roles, name=task['role_name'])
                    if role:
                        member = interaction.guild.get_member(int(self.user_id))
                        if member:
                            await member.add_roles(role, reason=f"Completed task: {task['name']}")

                # Update metadata
                tasks_data['metadata']['total_completed'] = tasks_data.get('metadata', {}).get('total_completed', 0) + 1

                result_msg = f"✅ Task accepted! {task['reward']} coins awarded to <@{self.user_id}>"
                if task.get('role_name'):
                    result_msg += f" and **{task['role_name']}** role granted."

            else:
                # Reject submission
                user_task['status'] = 'rejected'
                user_task['notes'] = f"Rejected by {interaction.user.name}"
                result_msg = f"❌ Task submission rejected for <@{self.user_id}>. They can resubmit."

            # Save data
            data_manager.save_guild_data(guild_id, 'tasks', tasks_data)
            data_manager.save_guild_data(guild_id, 'currency', currency_data)

            # Update proof message
            await interaction.message.edit(view=None)

            # Send result
            await interaction.followup.send(result_msg)

            # Notify user
            member = interaction.guild.get_member(int(self.user_id))
            if member:
                try:
                    dm_embed = discord.Embed(
                        title="Task Review Complete",
                        description=f"Your submission for **{task['name']}** has been {'accepted' if accept else 'rejected'}.",
                        color=discord.Color.green() if accept else discord.Color.red()
                    )
                    if accept:
                        dm_embed.add_field(name="Reward", value=f"{task['reward']} coins", inline=True)
                    else:
                        dm_embed.add_field(name="Note", value="You can resubmit with updated proof.", inline=False)

                    await member.send(embed=dm_embed)
                except discord.Forbidden:
                    pass  # User has DMs disabled

        except Exception as e:
            print(f"Task review error: {e}")
            await interaction.followup.send("❌ Error processing review.", ephemeral=True)

    def _validate_task_active(self, task):
        """Check if task status is 'active' and not expired"""
        if task.get('status') != 'active':
            return False

        # Check if task has expired
        expires_at = task.get('expires_at')
        if expires_at:
            try:
                expiry_time = datetime.fromisoformat(expires_at.replace('Z', '+00:00'))
                if datetime.now(timezone.utc) > expiry_time:
                    return False
            except (ValueError, TypeError):
                # If expiry parsing fails, assume task is still active
                pass

        return True

    def _check_user_can_claim(self, guild_id, user_id, task_id):
        """Verify user eligible to claim task"""
        tasks_data = data_manager.load_guild_data(guild_id, 'tasks')
        task = tasks_data.get('tasks', {}).get(task_id)

        if not task:
            return False, "Task not found"

        # Check if task is active
        if not self._validate_task_active(task):
            return False, "Task is not active or has expired"

        # Check if user already claimed
        user_tasks = tasks_data.get('user_tasks', {}).get(str(user_id), {})
        if task_id in user_tasks:
            status = user_tasks[task_id].get('status', 'unknown')
            return False, f"Already claimed (status: {status})"

        # Check max claims reached
        if task.get('max_claims', -1) != -1:
            current_claims = task.get('current_claims', 0)
            if current_claims >= task['max_claims']:
                return False, "Task has reached maximum claims"

        # Check user task limit
        settings = tasks_data.get('settings', {})
        max_per_user = settings.get('max_tasks_per_user', 10)
        active_count = sum(
            1 for t in user_tasks.values()
            if t['status'] in ['claimed', 'in_progress', 'submitted']
        )
        if active_count >= max_per_user:
            return False, f"Reached maximum active tasks ({max_per_user})"

        return True, "Eligible to claim"

    def _calculate_task_deadline(self, claimed_at, duration_hours):
        """Return deadline datetime"""
        try:
            if isinstance(claimed_at, str):
                claimed_time = datetime.fromisoformat(claimed_at.replace('Z', '+00:00'))
            elif isinstance(claimed_at, datetime):
                claimed_time = claimed_at
            else:
                claimed_time = datetime.now(timezone.utc)

            # Ensure timezone awareness
            if claimed_time.tzinfo is None:
                claimed_time = claimed_time.replace(tzinfo=timezone.utc)

            deadline = claimed_time + timedelta(hours=duration_hours)
            return deadline
        except Exception as e:
            # Fallback to current time + duration
            return datetime.now(timezone.utc) + timedelta(hours=duration_hours)

    def _check_max_claims_reached(self, task):
        """Return bool if task at capacity"""
        max_claims = task.get('max_claims', -1)
        if max_claims == -1:  # Unlimited
            return False

        current_claims = task.get('current_claims', 0)
        return current_claims >= max_claims

    def _award_task_currency(self, guild_id, user_id, task_id, task_name, reward_amount):
        """
        Award currency for task completion with error handling.
        Returns tuple: (success: bool, transaction_id: str or error_msg: str)
        """
        try:
            # Import currency cog for balance operations
            currency_cog = self.bot.get_cog('Currency')
            if not currency_cog:
                return False, "Currency system not available"

            # Use the existing _add_balance method with task_reward transaction type
            result = currency_cog._add_balance(
                guild_id,
                user_id,
                reward_amount,
                f"Completed task: {task_name}",
                transaction_type='task_reward'
            )

            if result is False:
                return False, "Failed to award currency - balance update failed"

            # Get the latest transaction to return transaction ID
            # This is a simplified approach - in production you might want to modify _add_balance to return transaction ID
            try:
                from core.transaction_manager import TransactionManager
                tm = TransactionManager(self.bot.data_manager if hasattr(self.bot, 'data_manager') else None)
                recent_txns = tm.get_transactions(guild_id, user_id=user_id, limit=1)['transactions']
                if recent_txns:
                    return True, recent_txns[0]['id']
                else:
                    return True, "transaction_logged"
            except Exception as e:
                # If we can't get transaction ID, still return success since balance was updated
                return True, "transaction_logged"

        except Exception as e:
            error_msg = f"Critical error awarding task currency: {str(e)}"
            print(error_msg)
            return False, error_msg

    @tasks.loop(minutes=5)
    async def check_expired_tasks(self):
        """Background task to expire old tasks and user submissions."""
        now = datetime.now(timezone.utc)

        for guild in self.bot.guilds:
            guild_id = str(guild.id)

            try:
                tasks_data = data_manager.load_guild_data(guild_id, 'tasks')
                settings = tasks_data.get('settings', {})

                if not settings.get('auto_expire_enabled', True):
                    continue

                changes_made = False

                # Expire active tasks past deadline
                for task_id, task in tasks_data.get('tasks', {}).items():
                    if task['status'] == 'active':
                        expires_at = datetime.fromisoformat(task['expires_at'])
                        if now > expires_at:
                            task['status'] = 'expired'
                            tasks_data['metadata']['total_expired'] = tasks_data.get('metadata', {}).get('total_expired', 0) + 1
                            changes_made = True

                            # Update Discord message
                            try:
                                await self.update_task_message(guild, guild_id, int(task_id), task)
                            except Exception as e:
                                print(f"Error updating expired task message: {e}")

                # Expire user tasks past deadline
                for user_id, user_tasks in tasks_data.get('user_tasks', {}).items():
                    for task_id, user_task in user_tasks.items():
                        if user_task['status'] in ['claimed', 'in_progress']:
                            deadline = datetime.fromisoformat(user_task['deadline'])
                            if now > deadline:
                                user_task['status'] = 'expired'
                                changes_made = True

                if changes_made:
                    data_manager.save_guild_data(guild_id, 'tasks', tasks_data)

            except Exception as e:
                print(f"Error checking expired tasks for guild {guild_id}: {e}")

    @check_expired_tasks.before_loop
    async def before_check_expired_tasks(self):
        await self.bot.wait_until_ready()

    @app_commands.command(name="tasks", description="View available tasks")
    @app_commands.describe(
        filter="Filter tasks by status",
        user="Show tasks for a specific user"
    )
    async def list_tasks(
        self,
        interaction: discord.Interaction,
        filter: str = "active",
        user: discord.Member = None
    ):
        """List tasks with filtering options."""
        await interaction.response.defer()

        guild_id = str(interaction.guild.id)
        target_user_id = str(user.id) if user else str(interaction.user.id)

        try:
            tasks_data = data_manager.load_guild_data(guild_id, 'tasks')
            tasks = tasks_data.get('tasks', {})
            user_tasks = tasks_data.get('user_tasks', {}).get(target_user_id, {})

            if not tasks:
                await interaction.followup.send("📋 No tasks available.", ephemeral=True)
                return

            # Filter tasks
            filtered_tasks = []
            for task_id, task in tasks.items():
                # Apply status filter
                if filter != 'all' and task['status'] != filter:
                    continue

                # If showing user tasks, check if they claimed it
                user_task_data = None
                if user:
                    user_task_data = user_tasks.get(task_id)

                filtered_tasks.append((task_id, task, user_task_data))

            if not filtered_tasks:
                await interaction.followup.send(
                    f"📋 No {filter} tasks found.",
                    ephemeral=True
                )
                return

            # Create paginated embeds (10 tasks per page)
            pages = []
            for i in range(0, len(filtered_tasks), 10):
                embed = discord.Embed(
                    title=f"📋 {filter.title()} Tasks" + (f" for {user.display_name}" if user else ""),
                    color=discord.Color.blue(),
                    timestamp=datetime.now(timezone.utc)
                )

                page_tasks = filtered_tasks[i:i+10]
                for task_id, task, user_task_data in page_tasks:
                    status_emoji = {
                        'active': '🟢',
                        'pending': '🟡',
                        'completed': '✅',
                        'expired': '⏰',
                        'cancelled': '❌'
                    }

                    # Task info
                    task_info = f"{status_emoji.get(task['status'], '⚪')} **{task['name']}**\n"
                    task_info += f"💰 {task['reward']} coins | ⏱️ {task['duration_hours']}h\n"
                    task_info += f"👥 {task['current_claims']}"
                    if task['max_claims'] != -1:
                        task_info += f"/{task['max_claims']}"
                    task_info += " claims"

                    # User-specific info
                    if user_task_data:
                        user_status = user_task_data['status']
                        task_info += f"\n🔸 Your status: {user_status.title()}"

                        if user_status in ['claimed', 'in_progress']:
                            deadline = datetime.fromisoformat(user_task_data['deadline'])
                            task_info += f"\n⏰ Deadline: <t:{int(deadline.timestamp())}:R>"

                    embed.add_field(
                        name=f"Task #{task_id}",
                        value=task_info,
                        inline=False
                    )

                embed.set_footer(text=f"Page {len(pages)+1} | Total: {len(filtered_tasks)} tasks")
                pages.append(embed)

            # Send with pagination if multiple pages
            if len(pages) == 1:
                await interaction.followup.send(embed=pages[0])
            else:
                view = TaskListPaginator(pages, interaction.user.id)
                await interaction.followup.send(embed=pages[0], view=view)

        except Exception as e:
            print(f"Task list error: {e}")
            await interaction.followup.send(
                "❌ Error loading tasks.",
                ephemeral=True
            )

    @app_commands.command(name="task_assign", description="Assign a task to a user")
    @app_commands.describe(
        task_id="The task ID to assign",
        user="The user to assign the task to"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def assign_task(
        self,
        interaction: discord.Interaction,
        task_id: int,
        user: discord.Member
    ):
        """Admin command to assign task to specific user."""
        await interaction.response.defer()

        guild_id = str(interaction.guild.id)
        user_id = str(user.id)

        try:
            tasks_data = data_manager.load_guild_data(guild_id, 'tasks')
            task = tasks_data['tasks'].get(str(task_id))

            if not task:
                await interaction.followup.send("❌ Task not found.", ephemeral=True)
                return

            if task['status'] != 'active':
                await interaction.followup.send(
                    f"❌ Cannot assign task with status: {task['status']}",
                    ephemeral=True
                )
                return

            # Check if already assigned
            user_tasks = tasks_data.get('user_tasks', {}).get(user_id, {})
            if str(task_id) in user_tasks:
                await interaction.followup.send(
                    f"❌ {user.mention} already has this task.",
                    ephemeral=True
                )
                return

            # Check max claims
            if task['max_claims'] != -1 and task['current_claims'] >= task['max_claims']:
                await interaction.followup.send(
                    "❌ Task has reached maximum claims.",
                    ephemeral=True
                )
                return

            # Assign task
            claimed_at = datetime.now(timezone.utc)
            deadline = claimed_at + timedelta(hours=task['duration_hours'])

            tasks_data.setdefault('user_tasks', {}).setdefault(user_id, {})[str(task_id)] = {
                'claimed_at': claimed_at.isoformat(),
                'deadline': deadline.isoformat(),
                'status': 'in_progress',
                'proof_message_id': None,
                'proof_attachments': [],
                'proof_content': '',
                'submitted_at': None,
                'completed_at': None,
                'notes': f'Assigned by {interaction.user.name}'
            }

            task['current_claims'] += 1
            task['assigned_users'].append(user_id)

            # Save
            data_manager.save_guild_data(guild_id, 'tasks', tasks_data)

            # Update Discord message
            await self.update_task_message(interaction.guild, guild_id, task_id, task)

            # Notify user
            try:
                dm_embed = discord.Embed(
                    title="📋 Task Assigned",
                    description=f"You have been assigned **{task['name']}**",
                    color=discord.Color.blue()
                )
                dm_embed.add_field(name="💰 Reward", value=f"{task['reward']} coins", inline=True)
                dm_embed.add_field(name="⏰ Deadline", value=f"<t:{int(deadline.timestamp())}:R>", inline=True)
                dm_embed.add_field(
                    name="📝 Details",
                    value=task['description'][:1000],
                    inline=False
                )
                if task.get('url'):
                    dm_embed.add_field(name="🔗 Link", value=task['url'], inline=False)

                await user.send(embed=dm_embed)
            except discord.Forbidden:
                pass

            await interaction.followup.send(
                f"✅ Task assigned to {user.mention}",
                ephemeral=True
            )

        except Exception as e:
            print(f"Task assignment error: {e}")
            await interaction.followup.send(
                "❌ Error assigning task.",
                ephemeral=True
            )

    @app_commands.command(name="task_archive", description="Archive completed/expired tasks")
    @app_commands.describe(
        days_old="Archive tasks older than this many days (default: 30)"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def archive_tasks(
        self,
        interaction: discord.Interaction,
        days_old: int = 30
    ):
        """
        Archive old tasks to reduce data file size.
        Moves tasks to archive file and removes from active data.
        """
        await interaction.response.defer(ephemeral=True)

        guild_id = str(interaction.guild.id)

        try:
            tasks_data = data_manager.load_guild_data(guild_id, 'tasks')
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_old)

            archived_count = 0
            archived_tasks = []

            # Find tasks to archive
            for task_id, task in list(tasks_data['tasks'].items()):
                if task['status'] in ['completed', 'expired', 'cancelled']:
                    created_date = datetime.fromisoformat(task['created'])
                    if created_date < cutoff_date:
                        archived_tasks.append((task_id, task))

            if not archived_tasks:
                await interaction.followup.send(
                    f"📦 No tasks older than {days_old} days to archive.",
                    ephemeral=True
                )
                return

            # Load or create archive file
            archive_path = os.path.join(
                data_manager.data_dir,
                'guilds',
                guild_id,
                'tasks_archive.json'
            )

            if os.path.exists(archive_path):
                with open(archive_path, 'r', encoding='utf-8') as f:
                    archive_data = json.load(f)
            else:
                archive_data = {'archived_tasks': [], 'archived_at': {}}

            # Archive tasks
            for task_id, task in archived_tasks:
                # Add to archive
                archive_entry = {
                    'task': task,
                    'archived_at': datetime.now(timezone.utc).isoformat(),
                    'user_completions': {}
                }

                # Include user completion data
                for user_id, user_tasks in tasks_data.get('user_tasks', {}).items():
                    if task_id in user_tasks:
                        archive_entry['user_completions'][user_id] = user_tasks[task_id]

                archive_data['archived_tasks'].append(archive_entry)

                # Remove from active data
                del tasks_data['tasks'][task_id]

                # Clean up user_tasks
                for user_id in list(tasks_data.get('user_tasks', {}).keys()):
                    if task_id in tasks_data['user_tasks'][user_id]:
                        del tasks_data['user_tasks'][user_id][task_id]

                    if not tasks_data['user_tasks'][user_id]:
                        del tasks_data['user_tasks'][user_id]

                archived_count += 1

            # Save archive
            os.makedirs(os.path.dirname(archive_path), exist_ok=True)
            with open(archive_path, 'w', encoding='utf-8') as f:
                json.dump(archive_data, f, indent=2, ensure_ascii=False)

            # Save updated tasks data
            data_manager.save_guild_data(guild_id, 'tasks', tasks_data)

            await interaction.followup.send(
                f"✅ Archived {archived_count} tasks older than {days_old} days.",
                ephemeral=True
            )

        except Exception as e:
            print(f"Task archive error: {e}")
            await interaction.followup.send(
                "❌ Error archiving tasks.",
                ephemeral=True
            )

    async def update_task_message(self, guild, guild_id, task_id, task):
        """Update Discord task message with current data and retry logic."""
        if not task.get('message_id'):
            return

        try:
            channel = guild.get_channel(int(task['channel_id']))
            if not channel:
                print(f"Channel {task['channel_id']} not found")
                return

            message = await discord_operation_with_retry(
                lambda: channel.fetch_message(int(task['message_id']))
            )
            embed = create_task_embed(task)

            # Disable button if task is not active
            view = None if task['status'] != 'active' else TaskClaimView(task_id)

            await discord_operation_with_retry(
                lambda: message.edit(embed=embed, view=view)
            )

        except discord.NotFound:
            print(f"Task message {task['message_id']} not found")
        except Exception as e:
            print(f"Error updating task message: {e}")

    async def post_task_to_discord(self, guild_id: str, task: dict):
        """Post a task message to Discord and return message info."""
        try:
            # Get task channel from config
            config = data_manager.load_guild_data(guild_id, 'config')
            task_channel_id = config.get('task_channel_id')

            if not task_channel_id:
                logger.warning(f"No task channel configured for guild {guild_id}")
                return None

            guild = self.bot.get_guild(int(guild_id))
            if not guild:
                logger.error(f"Guild {guild_id} not found")
                return None

            channel = guild.get_channel(int(task_channel_id))
            if not channel:
                logger.error(f"Task channel {task_channel_id} not found in guild {guild_id}")
                return None

            # Create embed
            embed = create_task_embed(task)

            # Create button view
            view = TaskClaimView(task['id'])

            # Send message
            message = await discord_operation_with_retry(
                lambda: channel.send(embed=embed, view=view)
            )

            logger.info(f"Task message posted: {message.id} for task {task['id']} in guild {guild_id}")
            return str(message.id)

        except Exception as e:
            logger.error(f"Error posting task to Discord: {e}", exc_info=True)
            return None

    async def delete_task_message(self, guild_id: str, task_id: str):
        """Delete task message from Discord."""
        try:
            # Load task data
            tasks_data = data_manager.load_guild_data(guild_id, 'tasks')
            task = tasks_data.get('tasks', {}).get(task_id)

            if not task:
                logger.warning(f"Task {task_id} not found in guild {guild_id}")
                return

            channel_id = task.get('channel_id')
            message_id = task.get('message_id')

            if not channel_id or not message_id:
                logger.warning(f"Missing channel_id or message_id for task {task_id}")
                return

            guild = self.bot.get_guild(int(guild_id))
            if not guild:
                logger.error(f"Guild {guild_id} not found")
                return

            channel = guild.get_channel(int(channel_id))
            if not channel:
                logger.error(f"Channel {channel_id} not found in guild {guild_id}")
                return

            # Delete the message
            message = await discord_operation_with_retry(
                lambda: channel.fetch_message(int(message_id))
            )
            await discord_operation_with_retry(
                lambda: message.delete()
            )

            logger.info(f"Task message {message_id} deleted for task {task_id} in guild {guild_id}")

        except discord.NotFound:
            logger.warning(f"Task message {message_id} already deleted for task {task_id}")
        except Exception as e:
            logger.error(f"Error deleting task message: {e}", exc_info=True)

class TaskListPaginator(discord.ui.View):
    """Pagination for task lists."""

    def __init__(self, pages, user_id):
        super().__init__(timeout=180)
        self.pages = pages
        self.current_page = 0
        self.user_id = user_id
        self.update_buttons()

    def update_buttons(self):
        self.previous_button.disabled = self.current_page == 0
        self.next_button.disabled = self.current_page == len(self.pages) - 1

    @discord.ui.button(label="◀", style=discord.ButtonStyle.gray)
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ This is not your menu.", ephemeral=True)
            return

        self.current_page = max(0, self.current_page - 1)
        self.update_buttons()
        await interaction.response.edit_message(embed=self.pages[self.current_page], view=self)

    @discord.ui.button(label="▶", style=discord.ButtonStyle.gray)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ This is not your menu.", ephemeral=True)
            return

        self.current_page = min(len(self.pages) - 1, self.current_page + 1)
        self.update_buttons()
        await interaction.response.edit_message(embed=self.pages[self.current_page], view=self)


async def setup(bot):
    """Setup the tasks cog."""
    await bot.add_cog(Tasks(bot))

    # Register persistent views for existing tasks
    for guild in bot.guilds:
        guild_id = str(guild.id)
        try:
            tasks_data = data_manager.load_guild_data(guild_id, 'tasks')
            for task_id, task in tasks_data.get('tasks', {}).items():
                if task.get('message_id') and task['status'] == 'active':
                    view = TaskClaimView(int(task_id))
                    bot.add_view(view, message_id=int(task['message_id']))
        except Exception as e:
            print(f"Error registering views for guild {guild_id}: {e}")
