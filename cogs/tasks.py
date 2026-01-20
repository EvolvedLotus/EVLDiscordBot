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
    from core.transaction_manager import TransactionManager
    from core.task_manager import TaskManager
    from core.embed_builder import EmbedBuilder
    from core.utils import create_embed
except ImportError as e:
    print(f"Import error in tasks.py: {e}")
    data_manager = None
    TransactionManager = None
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

class TaskListPaginator(discord.ui.View):
    """Paginator view for task listings."""

    def __init__(self, pages, user_id, timeout=300):
        super().__init__(timeout=timeout)
        self.pages = pages
        self.current_page = 0
        self.user_id = user_id
        self.update_buttons()

    def update_buttons(self):
        """Update navigation button states."""
        previous_button = self.previous_button
        next_button = self.next_button

        previous_button.disabled = self.current_page == 0
        next_button.disabled = self.current_page == len(self.pages) - 1

    @discord.ui.button(label="◀️ Previous", style=discord.ButtonStyle.secondary)
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Go to previous page."""
        if str(interaction.user.id) != self.user_id:
            await interaction.response.send_message("❌ You can't use this menu.", ephemeral=True)
            return

        if self.current_page > 0:
            self.current_page -= 1
            self.update_buttons()
            await interaction.response.edit_message(embed=self.pages[self.current_page], view=self)
        else:
            await interaction.response.send_message("❌ Already on first page.", ephemeral=True)

    @discord.ui.button(label="Next ▶️", style=discord.ButtonStyle.secondary)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Go to next page."""
        if str(interaction.user.id) != self.user_id:
            await interaction.response.send_message("❌ You can't use this menu.", ephemeral=True)
            return

        if self.current_page < len(self.pages) - 1:
            self.current_page += 1
            self.update_buttons()
            await interaction.response.edit_message(embed=self.pages[self.current_page], view=self)
        else:
            await interaction.response.send_message("❌ Already on last page.", ephemeral=True)


async def send_general_task_proof_modal(interaction: discord.Interaction, task_id: int, task_name: str):
    """
    Send a custom modal with FileUpload support using raw Discord API.
    Discord API supports FileUpload (type 19) but discord.py hasn't added it yet.
    """
    # Build the modal payload with FileUpload component (type 19) wrapped in Label (type 18)
    modal_payload = {
        "type": 9,  # MODAL interaction response type
        "data": {
            "custom_id": f"general_task_proof_modal_{task_id}",
            "title": f"Submit Proof - Task #{task_id}",
            "components": [
                # Label component (type 18) wrapping Text Input for proof
                {
                    "type": 18,  # Label
                    "label": "Proof of Completion",
                    "description": "Describe how you completed this task",
                    "component": {
                        "type": 4,  # Text Input
                        "custom_id": "proof_input",
                        "style": 2,  # Paragraph
                        "min_length": 10,
                        "max_length": 1000,
                        "placeholder": "Describe how you completed this task, or paste a link to your proof...",
                        "required": True
                    }
                },
                # Label component wrapping Text Input for notes
                {
                    "type": 18,  # Label  
                    "label": "Additional Notes (Optional)",
                    "component": {
                        "type": 4,  # Text Input
                        "custom_id": "notes_input",
                        "style": 1,  # Short
                        "max_length": 500,
                        "placeholder": "Any extra information for the reviewer...",
                        "required": False
                    }
                },
                # Label component wrapping FileUpload (type 19)
                {
                    "type": 18,  # Label
                    "label": "Upload Proof (Optional)",
                    "description": "Attach screenshots or files as proof",
                    "component": {
                        "type": 19,  # FileUpload
                        "custom_id": "proof_files",
                        "min_values": 0,
                        "max_values": 5,
                        "required": False
                    }
                }
            ]
        }
    }
    
    # Send modal via raw HTTP request
    try:
        route = discord.http.Route(
            'POST', 
            '/interactions/{interaction_id}/{interaction_token}/callback',
            interaction_id=interaction.id,
            interaction_token=interaction.token
        )
        await interaction.client.http.request(route, json=modal_payload)
        return True
    except Exception as e:
        print(f"Error sending custom modal: {e}")
        # Fallback to standard discord.py modal without file upload
        return False


class GeneralTaskProofModal(discord.ui.Modal):
    """Fallback modal for submitting proof (used if raw API modal fails)."""
    
    def __init__(self, task_id: int, task_name: str):
        super().__init__(title=f"Submit Proof - Task #{task_id}")
        self.task_id = task_id
        self.task_name = task_name
        
        # Proof description input
        self.proof_input = discord.ui.TextInput(
            label="Proof of Completion",
            placeholder="Describe how you completed this task, or paste a link to your proof...",
            style=discord.TextStyle.paragraph,
            required=True,
            min_length=10,
            max_length=1000
        )
        self.add_item(self.proof_input)
        
        # Optional notes
        self.notes_input = discord.ui.TextInput(
            label="Additional Notes (Optional)",
            placeholder="Any extra information for the reviewer...",
            style=discord.TextStyle.short,
            required=False,
            max_length=500
        )
        self.add_item(self.notes_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        """Handle the modal submission - claim task and submit proof."""
        await interaction.response.defer(ephemeral=True)
        
        guild_id = interaction.guild.id
        user_id = interaction.user.id
        proof = self.proof_input.value
        notes = self.notes_input.value
        
        # Get file attachments if FileUpload component is available
        attachments = []
        attachment_urls = []
        if self.file_upload is not None and hasattr(self.file_upload, 'attachments'):
            attachments = self.file_upload.attachments or []
            attachment_urls = [att.url for att in attachments if hasattr(att, 'url')]
        
        try:
            # Get tasks cog
            tasks_cog = interaction.client.get_cog('Tasks')
            if not tasks_cog or not tasks_cog.task_manager:
                await interaction.followup.send("❌ Task management system not available.", ephemeral=True)
                return

            # 1. Claim the task
            claim_result = await tasks_cog.task_manager.claim_task(guild_id, user_id, self.task_id)
            
            if not claim_result['success']:
                await interaction.followup.send(claim_result['error'], ephemeral=True)
                return

            task_data = claim_result['task']

            # 2. Submit the proof
            submit_result = await tasks_cog.task_manager.submit_task(guild_id, user_id, self.task_id, proof)
            
            if not submit_result['success']:
                await interaction.followup.send(f"✅ Task claimed, but submission failed: {submit_result['error']}", ephemeral=True)
                return

            # 3. Update notes and attachments if provided
            update_data = {}
            if notes:
                update_data['notes'] = notes
            if attachment_urls:
                update_data['proof_attachments'] = attachment_urls
            
            if update_data:
                tasks_cog.data_manager.supabase.table('user_tasks').update(update_data).eq('user_id', str(user_id)).eq('guild_id', str(guild_id)).eq('task_id', str(self.task_id)).execute()

            # 4. Post to Log Channel
            settings = tasks_cog.data_manager.load_guild_data(str(guild_id), 'config')
            log_channel_id = settings.get('log_channel_id')
            
            if log_channel_id:
                channel = interaction.guild.get_channel(int(log_channel_id))
                if channel:
                    proof_embed = discord.Embed(
                        title="📨 General Task Submission",
                        description=f"**{interaction.user.mention}** submitted proof for **{self.task_name}**",
                        color=discord.Color.orange(),
                        timestamp=datetime.now(timezone.utc)
                    )
                    proof_embed.add_field(name="📝 Proof Description", value=proof, inline=False)
                    if notes:
                        proof_embed.add_field(name="📋 Additional Notes", value=notes, inline=False)
                    if attachment_urls:
                        attachments_text = "\n".join([f"📎 [Attachment {i+1}]({url})" for i, url in enumerate(attachment_urls)])
                        proof_embed.add_field(name="📁 Uploaded Files", value=attachments_text, inline=False)
                        # Set the first image as the embed thumbnail if it's an image
                        if attachment_urls and any(url.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp')) for url in attachment_urls):
                            for url in attachment_urls:
                                if url.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp')):
                                    proof_embed.set_image(url=url)
                                    break
                    proof_embed.add_field(name="🆔 Task ID", value=str(self.task_id), inline=True)
                    proof_embed.add_field(name="👤 User ID", value=str(user_id), inline=True)

                    # Add review buttons (use globals to get TaskReviewView which is defined later in file)
                    ReviewView = globals().get('TaskReviewView')
                    if ReviewView:
                        view = ReviewView(self.task_id, user_id)
                    else:
                        view = None
                    proof_message = await discord_operation_with_retry(
                        lambda: channel.send(embed=proof_embed, view=view)
                    )

                    # Update proof_message_id in DB
                    tasks_cog.data_manager.supabase.table('user_tasks').update({
                        'proof_message_id': str(proof_message.id)
                    }).eq('user_id', str(user_id)).eq('guild_id', str(guild_id)).eq('task_id', str(self.task_id)).execute()

                    # Success message with nice embed
                    success_embed = discord.Embed(
                        title="✅ Task Submitted Successfully!",
                        description=f"Your proof for **{self.task_name}** has been submitted for review.",
                        color=discord.Color.green()
                    )
                    success_embed.add_field(name="📋 Status", value="⏳ Pending Review", inline=True)
                    success_embed.add_field(name="💡 Next Steps", value="A moderator will review your submission.", inline=False)
                    
                    await interaction.followup.send(embed=success_embed, ephemeral=True)
                else:
                    await interaction.followup.send(
                        "✅ Task claimed and submitted, but log channel not found. Please contact an admin.",
                        ephemeral=True
                    )
            else:
                await interaction.followup.send(
                    "✅ Task claimed and submitted, but log channel is not configured. Please contact an admin.",
                    ephemeral=True
                )

        except Exception as e:
            print(f"GeneralTaskProofModal error: {e}")
            await interaction.followup.send(
                "❌ An error occurred. Please try again.",
                ephemeral=True
            )


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

    @discord.ui.button(
        label="Submit Proof",
        style=discord.ButtonStyle.blurple,
        custom_id="submit_proof",
        emoji="📤"
    )
    async def submit_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Handle proof submission request."""
        # Check if user has claimed this task
        guild_id = str(interaction.guild.id)
        user_id = str(interaction.user.id)
        
        # Get Tasks cog
        tasks_cog = interaction.client.get_cog('Tasks')
        if not tasks_cog:
            await interaction.response.send_message("System error.", ephemeral=True)
            return

        # Check DB for user claim
        # We need to check 'user_tasks' table
        try:
            result = tasks_cog.data_manager.supabase.table('user_tasks').select('status').eq('user_id', user_id).eq('guild_id', guild_id).eq('task_id', self.task_id).execute()
            
            if not result.data or result.data[0]['status'] not in ['claimed', 'in_progress']:
                await interaction.response.send_message("❌ You haven't claimed this task or it's already completed.", ephemeral=True)
                return
                
            # Open submission modal
            # Get task name for title
            task_res = tasks_cog.data_manager.supabase.table('tasks').select('name').eq('guild_id', guild_id).eq('task_id', self.task_id).execute()
            task_name = task_res.data[0]['name'] if task_res.data else f"Task #{self.task_id}"
            
            modal = GeneralTaskProofModal(self.task_id, task_name)
            await interaction.response.send_modal(modal)
            
        except Exception as e:
            await interaction.response.send_message(f"Error: {e}", ephemeral=True)

    async def handle_claim(self, interaction: discord.Interaction):
        """Handle task claim using TaskManager with proper error handling."""
        # Check if interaction already responded
        if interaction.response.is_done():
            # Try to send a follow-up message outside the original interaction
            try:
                await interaction.followup.send(
                    "⚠️ This interaction has expired. Please try claiming the task again.",
                    ephemeral=True
                )
            except Exception:
                pass
            return

        try:
            guild_id = interaction.guild.id
            user_id = interaction.user.id

            # Get tasks cog
            tasks_cog = interaction.client.get_cog('Tasks')
            if not tasks_cog or not tasks_cog.task_manager:
                await interaction.response.send_message("❌ Task management system not available.", ephemeral=True)
                return

            # Check task category BEFORE deferring (so we can show modal if needed)
            try:
                task_check = tasks_cog.data_manager.supabase.table('tasks').select('category, name').eq('guild_id', str(guild_id)).eq('task_id', self.task_id).execute()
                if task_check.data and len(task_check.data) > 0:
                    category = task_check.data[0].get('category')
                    task_name = task_check.data[0].get('name', f'Task #{self.task_id}')
                    
                    if category == 'General':
                        # Try to send custom modal with FileUpload support
                        success = await send_general_task_proof_modal(interaction, self.task_id, task_name)
                        if success:
                            return
                        # Fallback to standard discord.py modal without file upload
                        modal = GeneralTaskProofModal(self.task_id, task_name)
                        await interaction.response.send_modal(modal)
                        return
            except Exception as e:
                print(f"Error checking task category: {e}")
                # Continue with normal claim if check fails (fallback)

            # For non-General tasks, defer and process normally
            await interaction.response.defer(ephemeral=True)

            # Use TaskManager to claim task (expects integers)
            result = await tasks_cog.task_manager.claim_task(guild_id, user_id, self.task_id)

            if not result['success']:
                await interaction.followup.send(result['error'], ephemeral=True)
                return

            task_data = result['task']
            deadline = result['deadline']

            # Update embed using task data
            task_info = {
                'name': task_data['name'],
                'status': 'active',  # Still active since just claimed
                'channel_id': task_data.get('channel_id', str(interaction.channel.id)),
                'message_id': task_data.get('message_id'),
                'task_id': task_data['task_id']
            }
            await self.update_task_message(interaction.guild, str(guild_id), self.task_id, task_info)

            # Notify user
            embed = discord.Embed(
                title="✅ Task Claimed Successfully!",
                description=f"You have claimed **{task_data['name']}**",
                color=discord.Color.green()
            )
            embed.add_field(name="⏰ Deadline", value=f"<t:{int(deadline.timestamp())}:R>", inline=False)
            embed.add_field(
                name="📝 Submit Proof",
                value="Use `/task submit` command with proof of completion",
                inline=False
            )

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            print(f"Task claim error: {e}")
            try:
                await interaction.followup.send(
                    "❌ An error occurred while claiming the task. Please try again.",
                    ephemeral=True
                )
            except Exception:
                # If followup also fails, ignore
                pass

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
            
            # Ensure assigned_users is a list before appending
            if 'assigned_users' not in task or not isinstance(task['assigned_users'], list):
                task['assigned_users'] = []
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
        timestamp=datetime.fromisoformat(task.get('created_at', task.get('created', datetime.now().isoformat())))
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

    embed.set_footer(text=f"Task ID: {task['task_id']}")

    return embed

class MyTasksSelect(discord.ui.Select):
    """Select menu to choose a task to submit proof for."""
    def __init__(self, tasks_data):
        options = []
        # tasks_data is a list of dicts: {task_id, name, status}
        for task in tasks_data[:25]:
            label = task['name'][:100]
            description = f"ID: {task['task_id']} | Status: {task['status'].title()}"
            emoji = "📝" if task['status'] == 'in_progress' else "✅"
            
            options.append(discord.SelectOption(
                label=label,
                description=description,
                value=str(task['task_id']),
                emoji=emoji
            ))
            
        super().__init__(
            placeholder="Select a task to submit proof...",
            min_values=1,
            max_values=1,
            options=options,
            disabled=len(options) == 0
        )

    async def callback(self, interaction: discord.Interaction):
        task_id = self.values[0]
        # Find task details for the modal title
        selected_option = next(opt for opt in self.options if opt.value == task_id)
        task_name = selected_option.label
        
        # Open the GeneralTaskProofModal
        modal = GeneralTaskProofModal(int(task_id), task_name)
        await interaction.response.send_modal(modal)

class MyTasksView(discord.ui.View):
    def __init__(self, tasks_data):
        super().__init__(timeout=180)
        self.add_item(MyTasksSelect(tasks_data))

class Tasks(commands.Cog):
    """Task management cog for Discord bot."""

    def __init__(self, bot):
        self.bot = bot
        self.data_manager = data_manager
        self.transaction_manager = TransactionManager
        # Initialize managers lazily to avoid dependency issues during cog loading
        # Don't start the loop here - it will be started in setup or after bot is ready

    @commands.Cog.listener()
    async def on_ready(self):
        """Register persistent views when bot is ready."""
        print("Tasks cog: on_ready triggered - registering persistent views...")
        await self.bot.wait_until_ready()
        
        # Wait a bit to ensure guilds are fully loaded
        await asyncio.sleep(5)
        
        count = 0
        for guild in self.bot.guilds:
            guild_id = str(guild.id)
            try:
                # Get active tasks from database
                active_tasks = self.data_manager.supabase.table('tasks').select('*').eq('guild_id', guild_id).eq('status', 'active').execute()

                for task in active_tasks.data or []:
                    if task.get('message_id'):
                        # TaskClaimView expects int task_id
                        view = TaskClaimView(int(task['task_id']))
                        self.bot.add_view(view, message_id=int(task['message_id']))
                        count += 1
            except Exception as e:
                print(f"Error registering views for guild {guild_id}: {e}")
        
        print(f"Tasks cog: Registered {count} persistent task views.")

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        """Handle custom modal submissions (for FileUpload support)."""
        # Only handle modal submissions with our custom_id pattern
        if interaction.type != discord.InteractionType.modal_submit:
            return
        
        custom_id = interaction.data.get('custom_id', '')
        if not custom_id.startswith('general_task_proof_modal_'):
            return
        
        # Extract task_id from custom_id
        try:
            task_id = int(custom_id.replace('general_task_proof_modal_', ''))
        except ValueError:
            return
        
        await interaction.response.defer(ephemeral=True)
        
        guild_id = interaction.guild.id
        user_id = interaction.user.id
        
        # Extract form data from the interaction
        proof = ""
        notes = ""
        attachment_urls = []
        
        components = interaction.data.get('components', [])
        for component in components:
            # Handle Label wrapper (type 18)
            if component.get('type') == 18:
                inner = component.get('component', component.get('components', [{}])[0] if component.get('components') else {})
            else:
                inner = component
            
            custom_id_inner = inner.get('custom_id', '')
            
            if custom_id_inner == 'proof_input':
                proof = inner.get('value', '')
            elif custom_id_inner == 'notes_input':
                notes = inner.get('value', '')
            elif custom_id_inner == 'proof_files':
                # FileUpload returns array of attachment IDs in 'values'
                file_ids = inner.get('values', [])
                # Get resolved attachments
                resolved = interaction.data.get('resolved', {})
                attachments = resolved.get('attachments', {})
                for file_id in file_ids:
                    att = attachments.get(str(file_id), {})
                    if att.get('url'):
                        attachment_urls.append(att['url'])
        
        try:
            # Get task name
            task_check = self.data_manager.supabase.table('tasks').select('name').eq('guild_id', str(guild_id)).eq('task_id', task_id).execute()
            task_name = task_check.data[0].get('name', f'Task #{task_id}') if task_check.data else f'Task #{task_id}'
            
            # 1. Claim the task
            claim_result = await self.task_manager.claim_task(guild_id, user_id, task_id)
            
            if not claim_result['success']:
                await interaction.followup.send(claim_result['error'], ephemeral=True)
                return

            # 2. Submit the proof
            submit_result = await self.task_manager.submit_task(guild_id, user_id, task_id, proof)
            
            if not submit_result['success']:
                await interaction.followup.send(f"✅ Task claimed, but submission failed: {submit_result['error']}", ephemeral=True)
                return

            # 3. Update notes and attachments if provided
            update_data = {}
            if notes:
                update_data['notes'] = notes
            if attachment_urls:
                update_data['proof_attachments'] = attachment_urls
            
            if update_data:
                self.data_manager.supabase.table('user_tasks').update(update_data).eq('user_id', str(user_id)).eq('guild_id', str(guild_id)).eq('task_id', str(task_id)).execute()

            # 4. Post to Log Channel
            settings = self.data_manager.load_guild_data(str(guild_id), 'config')
            log_channel_id = settings.get('log_channel_id')
            
            if log_channel_id:
                channel = interaction.guild.get_channel(int(log_channel_id))
                if channel:
                    proof_embed = discord.Embed(
                        title="📨 General Task Submission",
                        description=f"**{interaction.user.mention}** submitted proof for **{task_name}**",
                        color=discord.Color.orange(),
                        timestamp=datetime.now(timezone.utc)
                    )
                    proof_embed.add_field(name="📝 Proof Description", value=proof or "No description provided", inline=False)
                    if notes:
                        proof_embed.add_field(name="📋 Additional Notes", value=notes, inline=False)
                    if attachment_urls:
                        attachments_text = "\n".join([f"📎 [Attachment {i+1}]({url})" for i, url in enumerate(attachment_urls)])
                        proof_embed.add_field(name="📁 Uploaded Files", value=attachments_text, inline=False)
                        # Set the first image as the embed image if it's an image type
                        for url in attachment_urls:
                            if any(ext in url.lower() for ext in ['.png', '.jpg', '.jpeg', '.gif', '.webp']):
                                proof_embed.set_image(url=url)
                                break
                    proof_embed.add_field(name="🆔 Task ID", value=str(task_id), inline=True)
                    proof_embed.add_field(name="👤 User ID", value=str(user_id), inline=True)

                    # Add review buttons
                    view = TaskReviewView(task_id, user_id)
                    proof_message = await discord_operation_with_retry(
                        lambda: channel.send(embed=proof_embed, view=view)
                    )

                    # Update proof_message_id in DB
                    self.data_manager.supabase.table('user_tasks').update({
                        'proof_message_id': str(proof_message.id)
                    }).eq('user_id', str(user_id)).eq('guild_id', str(guild_id)).eq('task_id', str(task_id)).execute()

            # Success message
            success_embed = discord.Embed(
                title="✅ Task Submitted Successfully!",
                description=f"Your proof for **{task_name}** has been submitted for review.",
                color=discord.Color.green()
            )
            success_embed.add_field(name="📋 Status", value="⏳ Pending Review", inline=True)
            if attachment_urls:
                success_embed.add_field(name="📎 Files Uploaded", value=f"{len(attachment_urls)} file(s)", inline=True)
            success_embed.add_field(name="💡 Next Steps", value="A moderator will review your submission.", inline=False)
            
            await interaction.followup.send(embed=success_embed, ephemeral=True)

        except Exception as e:
            print(f"Custom modal submission error: {e}")
            import traceback
            traceback.print_exc()
            await interaction.followup.send(
                "❌ An error occurred while processing your submission. Please try again.",
                ephemeral=True
            )

    def set_managers(self, data_manager, transaction_manager):
        """Set data and transaction managers"""
        self.data_manager = data_manager
        self.transaction_manager = transaction_manager
        # Now that we have managers, initialize task_manager
        from core.task_manager import TaskManager
        self.task_manager = TaskManager(data_manager, transaction_manager)
        self.task_manager.set_bot(self.bot)
        self.task_manager.set_cache_manager(self.bot.cache_manager)
        try:
            sse_manager = self.bot.sse_manager
            if sse_manager:
                self.task_manager.set_sse_manager(sse_manager)
        except AttributeError:
            pass  # SSE manager not available yet

    @app_commands.command(name="task_claim_proof", description="Claim and submit proof for a General task")
    @app_commands.describe(
        task_id="The ID of the task to claim and submit",
        proof="Description or link to proof of completion",
        attachment="Optional screenshot/image proof"
    )
    async def task_claim_proof(
        self,
        interaction: discord.Interaction,
        task_id: int,
        proof: str,
        attachment: discord.Attachment = None
    ):
        """Claim and submit proof for a General task."""
        await interaction.response.defer(ephemeral=True)

        guild_id = interaction.guild.id
        user_id = interaction.user.id

        try:
            # 1. Claim the task
            claim_result = await self.task_manager.claim_task(guild_id, user_id, task_id)
            
            if not claim_result['success']:
                await interaction.followup.send(claim_result['error'], ephemeral=True)
                return

            task_data = claim_result['task']

            # 2. Submit the proof
            submit_result = await self.task_manager.submit_task(guild_id, user_id, task_id, proof)
            
            if not submit_result['success']:
                await interaction.followup.send(f"✅ Task claimed, but submission failed: {submit_result['error']}", ephemeral=True)
                return

            # 3. Handle attachment
            proof_attachments = []
            if attachment:
                proof_attachments.append(attachment.url)
                # Update proof attachments in DB
                self.data_manager.supabase.table('user_tasks').update({
                    'proof_attachments': proof_attachments
                }).eq('user_id', str(user_id)).eq('guild_id', str(guild_id)).eq('task_id', str(task_id)).execute()

            # 4. Post to Log Channel
            # Get log channel ID from config
            settings = self.data_manager.load_guild_data(str(guild_id), 'config')
            log_channel_id = settings.get('log_channel_id')
            
            if log_channel_id:
                channel = interaction.guild.get_channel(int(log_channel_id))
                if channel:
                    proof_embed = discord.Embed(
                        title="📨 General Task Submission",
                        description=f"**{interaction.user.mention}** submitted proof for **{task_data['name']}**",
                        color=discord.Color.orange(),
                        timestamp=datetime.now(timezone.utc)
                    )
                    proof_embed.add_field(name="Proof Description", value=proof, inline=False)
                    proof_embed.add_field(name="Task ID", value=str(task_id), inline=True)
                    proof_embed.add_field(name="User ID", value=str(user_id), inline=True)

                    if proof_attachments:
                        proof_embed.set_image(url=proof_attachments[0])

                    # Add review buttons
                    view = TaskReviewView(task_id, user_id)
                    proof_message = await discord_operation_with_retry(
                        lambda: channel.send(embed=proof_embed, view=view)
                    )

                    # Update proof_message_id in DB
                    self.data_manager.supabase.table('user_tasks').update({
                        'proof_message_id': str(proof_message.id)
                    }).eq('user_id', str(user_id)).eq('guild_id', str(guild_id)).eq('task_id', str(task_id)).execute()

                    await interaction.followup.send(
                        "✅ Task claimed and submitted successfully! Waiting for moderator review.",
                        ephemeral=True
                    )
                else:
                    await interaction.followup.send(
                        "✅ Task claimed and submitted, but log channel not found. Please contact an admin.",
                        ephemeral=True
                    )
            else:
                await interaction.followup.send(
                    "✅ Task claimed and submitted, but log channel is not configured. Please contact an admin.",
                    ephemeral=True
                )

        except Exception as e:
            print(f"Task claim_proof error: {e}")
            await interaction.followup.send(
                "❌ An error occurred. Please try again.",
                ephemeral=True
            )

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

        guild_id = interaction.guild.id
        user_id = interaction.user.id

        try:
            # Use TaskManager to submit
            result = await self.task_manager.submit_task(guild_id, user_id, task_id, proof)

            if not result['success']:
                await interaction.followup.send(result['error'], ephemeral=True)
                return

            # Handle attachment
            proof_attachments = []
            if attachment:
                proof_attachments.append(attachment.url)
                # Update proof attachments in DB
                self.data_manager.supabase.table('user_tasks').update({
                    'proof_attachments': proof_attachments
                }).eq('user_id', str(user_id)).eq('guild_id', str(guild_id)).eq('task_id', str(task_id)).execute()

            # Get task details for embed
            task_result = self.data_manager.supabase.table('tasks').select('name').eq('guild_id', str(guild_id)).eq('task_id', task_id).execute()
            task_name = task_result.data[0]['name'] if task_result.data else "Unknown Task"

            # Post to Log Channel (or Task Channel if log not set, but user requested log channel for general)
            # For regular tasks, we might still want to post to log channel if configured
            settings = self.data_manager.load_guild_data(str(guild_id), 'config')
            log_channel_id = settings.get('log_channel_id')
            
            target_channel = None
            if log_channel_id:
                target_channel = interaction.guild.get_channel(int(log_channel_id))
            
            if target_channel:
                proof_embed = discord.Embed(
                    title="📨 Task Submission",
                    description=f"**{interaction.user.mention}** submitted proof for **{task_name}**",
                    color=discord.Color.orange(),
                    timestamp=datetime.now(timezone.utc)
                )
                proof_embed.add_field(name="Proof", value=proof, inline=False)
                proof_embed.add_field(name="Task ID", value=str(task_id), inline=True)
                proof_embed.add_field(name="User ID", value=str(user_id), inline=True)

                if proof_attachments:
                    proof_embed.set_image(url=proof_attachments[0])

                # Add review buttons
                view = TaskReviewView(task_id, user_id)
                proof_message = await discord_operation_with_retry(
                    lambda: target_channel.send(embed=proof_embed, view=view)
                )

                # Update proof_message_id
                self.data_manager.supabase.table('user_tasks').update({
                    'proof_message_id': str(proof_message.id)
                }).eq('user_id', str(user_id)).eq('guild_id', str(guild_id)).eq('task_id', str(task_id)).execute()

                await interaction.followup.send(
                    "✅ Task submitted successfully! Waiting for review.",
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    "✅ Task submitted, but no log channel configured for review.",
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
        """Handle task review decision with proper role ID checking from Supabase."""
        # Check permissions
        if not interaction.user.guild_permissions.administrator:
            # Verify user is an active member of this guild
            member = interaction.guild.get_member(interaction.user.id)
            if not member:
                await interaction.response.send_message(
                    "❌ You must be an active member of this server to review tasks.",
                    ephemeral=True
                )
                return

            # Get admin roles from Supabase
            tasks_cog = interaction.client.get_cog('Tasks')
            if not tasks_cog or not tasks_cog.data_manager:
                await interaction.response.send_message(
                    "❌ Data system not available.",
                    ephemeral=True
                )
                return

            guild_config = tasks_cog.data_manager.supabase.table('guilds').select('admin_roles').eq('guild_id', str(interaction.guild.id)).execute()
            admin_roles = guild_config.data[0]['admin_roles'] if guild_config.data else []

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

                # Award currency using the currency cog's atomic method
                currency_cog = self.bot.get_cog('Currency')
                if currency_cog:
                    balance_result = currency_cog._add_balance(
                        int(guild_id),
                        int(self.user_id),
                        task['reward'],
                        f"Completed task: {task['name']}",
                        transaction_type='task_reward',
                        metadata={
                            'task_id': str(self.task_id),
                            'task_name': task['name'],
                            'reviewer_id': str(interaction.user.id)
                        }
                    )

                    if balance_result is False:
                        await interaction.followup.send("❌ Failed to award currency - balance update failed.", ephemeral=True)
                        return
                else:
                    await interaction.followup.send("❌ Currency system not available.", ephemeral=True)
                    return

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

    @app_commands.command(name="view_tasks", description="View available tasks with interactive buttons")
    async def view_tasks(
        self,
        interaction: discord.Interaction,
        filter: str = "active"
    ):
        """Display interactive task cards with claim buttons in table format like /list_tasks."""
        await interaction.response.defer()

        guild_id = str(interaction.guild.id)

        try:
            # Use the TaskManager to get tasks from Supabase (same as list_tasks)
            available_tasks = self.task_manager.get_available_tasks(guild_id, str(interaction.user.id))

            if not available_tasks:
                await interaction.followup.send("📋 No active tasks available for claiming.", ephemeral=True)
                return

            # Filter tasks (same logic as list_tasks)
            tasks = available_tasks
            if filter != 'all':
                tasks = [task for task in tasks if task.get('status') == filter]

            if not tasks:
                await interaction.followup.send(
                    f"📋 No {filter} tasks available.",
                    ephemeral=True
                )
                return

            # Create paginated embeds (10 tasks per page) - SAME FORMAT AS list_tasks
            pages = []
            for i in range(0, len(tasks), 10):
                embed = discord.Embed(
                    title=f"📋 Available Tasks ({len(tasks)})",
                    description="Tasks you can claim:",
                    color=discord.Color.blue(),
                    timestamp=datetime.now(timezone.utc)
                )

                page_tasks = tasks[i:i+10]
                for task in page_tasks:
                    status_emoji = {
                        'active': '🟢',
                        'pending': '🟡',
                        'completed': '✅',
                        'expired': '⏰',
                        'cancelled': '❌'
                    }

                    # Task info - SAME FORMAT AS list_tasks
                    task_info = f"{status_emoji.get(task['status'], '⚪')} **{task['name']}**\n"
                    task_info += f"💰 {task['reward']} coins | ⏱️ {task['duration_hours']}h\n"
                    task_info += f"👥 {task['current_claims']}"
                    if task['max_claims'] != -1:
                        task_info += f"/{task['max_claims']}"
                    task_info += " claims"

                    # Add expiry info
                    expires_timestamp = int(datetime.fromisoformat(str(task['expires_at'])).timestamp())
                    task_info += f"\n⏰ Expires: <t:{expires_timestamp}:R>"

                    embed.add_field(
                        name=f"Task #{task['id']}",
                        value=task_info,
                        inline=False
                    )

                embed.set_footer(text=f"Page {len(pages)+1} | Total: {len(tasks)} tasks")
                pages.append(embed)

            # Send with pagination if multiple pages
            if len(pages) == 1:
                await interaction.followup.send(embed=pages[0])
            else:
                view = TaskListPaginator(pages, interaction.user.id)
                await interaction.followup.send(embed=pages[0], view=view)

        except Exception as e:
            print(f"View tasks error: {e}")
            await interaction.followup.send(
                "❌ Error loading interactive task view.",
                ephemeral=True
            )

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
            # Use the TaskManager to get tasks from Supabase
            available_tasks = self.task_manager.get_available_tasks(guild_id, target_user_id)

            if not available_tasks:
                await interaction.followup.send("📋 No tasks available.", ephemeral=True)
                return

            tasks = available_tasks
            # Filter by status if needed
            if filter != 'all':
                tasks = [task for task in tasks if task.get('status') == filter]

            if not tasks:
                await interaction.followup.send(
                    f"📋 No {filter} tasks found.",
                    ephemeral=True
                )
                return

            # Get user tasks if needed
            user_tasks = []
            if user:
                user_tasks = self.task_manager.get_user_tasks(guild_id, target_user_id)

            # Filter and format tasks
            filtered_tasks = []
            for task in tasks:
                task_status = task.get('status', 'active')

                # Apply status filter
                if filter != 'all' and task_status != filter:
                    continue

                # If showing user tasks, check if they claimed it
                user_task_data = None
                if user:
                    # Find matching user task
                    for user_task in user_tasks:
                        if user_task.get('task_id') == task.get('id'):
                            user_task_data = user_task.get('user_task')
                            break

                filtered_tasks.append((task.get('id'), task, user_task_data))

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
            
            # Ensure assigned_users is a list before appending
            if 'assigned_users' not in task or not isinstance(task['assigned_users'], list):
                task['assigned_users'] = []
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



    @app_commands.command(name="mytasks", description="View your claimed tasks & Submit Proof")
    @app_commands.guild_only()
    async def mytasks(self, interaction: discord.Interaction):
        """View your claimed tasks and submit proof via menu."""
        await interaction.response.defer(ephemeral=True)
        
        guild_id = str(interaction.guild.id)
        user_id = str(interaction.user.id)
        
        # Fetch user tasks from DB
        try:
            user_tasks_res = self.data_manager.supabase.table('user_tasks').select('*').eq('user_id', user_id).eq('guild_id', guild_id).in_('status', ['claimed', 'in_progress']).execute()
            
            if not user_tasks_res.data:
                await interaction.followup.send("You don't have any active tasks.", ephemeral=True)
                return

            user_tasks = user_tasks_res.data
            
            # Prepare data for Select Menu
            task_ids = [t['task_id'] for t in user_tasks]
            
            # Fetch task names
            if task_ids:
                tasks_res = self.data_manager.supabase.table('tasks').select('task_id, name').eq('guild_id', guild_id).in_('task_id', task_ids).execute()
                task_map = {t['task_id']: t['name'] for t in tasks_res.data} if tasks_res.data else {}
            else:
                task_map = {}
            
            # Build list for View
            view_data = []
            embed_desc = ""
            
            for ut in user_tasks:
                tid = ut['task_id']
                name = task_map.get(tid, f"Task #{tid}")
                status = ut['status']
                deadline_ts = datetime.fromisoformat(ut['deadline']).timestamp() if ut.get('deadline') else None
                deadline = f"<t:{int(deadline_ts)}:R>" if deadline_ts else "No deadline"
                
                view_data.append({
                    'task_id': tid,
                    'name': name,
                    'status': status
                })
                
                embed_desc += f"**{name}** (ID: `{tid}`)\nStatus: {status.title()} | Deadline: {deadline}\n\n"
                
            embed = discord.Embed(
                title="📋 Your Active Tasks",
                description=embed_desc or "No details available.",
                color=discord.Color.blue()
            )
            embed.set_footer(text="Select a task below to submit proof")
            
            view = MyTasksView(view_data)
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)
            
        except Exception as e:
            logger.error(f"Error in mytasks: {e}")
            await interaction.followup.send("An error occurred while fetching your tasks.", ephemeral=True)

async def setup(bot):
    """Setup the tasks cog."""
    cog = Tasks(bot)
    await bot.add_cog(cog)

    # Set managers after cog is loaded
    data_manager_instance = getattr(bot, 'data_manager', None)
    transaction_manager_instance = getattr(bot, 'transaction_manager', None)
    if data_manager_instance and transaction_manager_instance:
        cog.set_managers(data_manager_instance, transaction_manager_instance)

    # Register persistent views for existing tasks
    # This is now handled in the on_ready listener within the Tasks cog
    pass
