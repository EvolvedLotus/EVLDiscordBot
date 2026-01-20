import discord
from discord import app_commands
from discord.ext import commands
import logging
from typing import Dict, List, Optional
from core.permissions import admin_only_interaction, moderator_only_interaction
from core.moderation.protection_manager import ProtectionManager
from core.moderation.scanner import MessageScanner
from core.moderation.enforcer import ProtectionEnforcer
from core.moderation.actions import ModerationActions
from core.moderation.scheduler import ModerationScheduler
from core.moderation.logger import ModerationLogger
from core.moderation.health import ModerationHealthChecker

logger = logging.getLogger(__name__)

class Moderation(commands.Cog):
    """Discord moderation system with profanity and link protection"""

    def __init__(self, bot):
        self.bot = bot
        self.data_manager = None  # Will be set by set_managers

        # Initialize moderation components with None data_manager initially
        self.protection_manager = ProtectionManager(None)
        self.scanner = MessageScanner(self.protection_manager)
        self.enforcer = ProtectionEnforcer(self.protection_manager, self.scanner, bot)
        self.actions = ModerationActions(self.protection_manager, bot)
        self.scheduler = ModerationScheduler(bot)
        self.logger = ModerationLogger(self.protection_manager, bot)
        self.health_checker = ModerationHealthChecker(
            self.protection_manager, self.scheduler, self.logger
        )

        logger.info("Moderation cog initialized")

    def set_managers(self, data_manager):
        """Set data manager reference"""
        self.data_manager = data_manager
        self.protection_manager.data_manager = data_manager

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Primary message listener hook that coordinates scanning, exemption checks, evaluation, and applying protection actions"""
        # Skip bot messages
        if message.author.bot:
            return

        # Skip DMs
        if not message.guild:
            return

        # Check if moderation is enabled for this guild
        config = self.protection_manager.load_protection_config(message.guild.id)
        if not config.get('enabled', True):
            return

        # Check if user is generally exempt (exempt roles/channels)
        if self.protection_manager.is_exempt_from_protection(
            message.guild.id, message.author.id, message.channel.id, message.author.roles
        ):
            return

        try:
            # Scan message for profanity violations (always applies)
            profanity_matches = self.scanner.scan_message_for_profanity(message.guild.id, message.content)

            # Check exemptions
            is_link_exempt = self.protection_manager.is_exempt_from_link_protection(message.guild.id, message.author)
            is_file_exempt = self.protection_manager.is_exempt_from_file_protection(message.guild.id, message.author)

            # Lists to store violations
            link_violations = []
            file_violations = []

            # 1. Scan for Links (if not exempt)
            if not is_link_exempt:
                link_violations = self.scanner.scan_message_for_links(message.guild.id, message.content)
                # Check embeds for links too
                embed_violations = self.scanner.scan_attachments_and_embeds(message.guild.id, message)
                # Extract only url-based violations from embed scan
                link_violations += [v for v in embed_violations if v['type'] in ['embed_url', 'embed_description']]

            # 2. Scan for Files/Attachments (if not exempt)
            if not is_file_exempt:
                # Check actual attachments
                if message.attachments:
                    for attachment in message.attachments:
                        file_violations.append({
                            'type': 'file_violation',
                            'filename': attachment.filename,
                            'url': attachment.url,
                            'reason': 'unauthorized_attachment'
                        })
                
                # Check embeds that look like images (gifs/images linked)
                if message.embeds:
                    for embed in message.embeds:
                        if embed.type in ['image', 'video', 'gifv']:
                            file_violations.append({
                                'type': 'file_violation',
                                'url': embed.url,
                                'reason': 'unauthorized_media_embed'
                            })

            # If no violations, return
            if not profanity_matches and not link_violations and not file_violations:
                return

            # Evaluate action plan
            action_plan = self.enforcer.evaluate_protection_action(
                message.guild.id, message, profanity_matches, link_violations, file_violations
            )

            # Apply action
            result = await self.enforcer.apply_protection_action(action_plan, message)

            # Log the action
            if result['success'] and result['action_taken'] != 'ignore':
                self.logger.create_moderation_audit_log(
                    message.guild.id,
                    result['action_taken'],
                    message.author.id,
                    self.bot.user.id,  # Automated action
                    message.id,
                    {
                        'reason': result['reason'],
                        'severity': action_plan.get('severity', 'low'),
                        'profanity_matches': len(profanity_matches),
                        'link_violations': len(link_violations),
                        'file_violations': len(file_violations)
                    }
                )

        except Exception as e:
            logger.error(f"Error in message moderation: {e}")

    @app_commands.command(name="add_profanity", description="Add a word to the profanity blacklist")
    @admin_only_interaction()
    async def command_add_profanity(self, interaction: discord.Interaction, word: str):
        """Slash command for admins to add profanity entries"""
        try:
            success, word_list = self.protection_manager.add_profanity_word(
                interaction.guild.id, word, interaction.user.id
            )

            if success:
                embed = discord.Embed(
                    title="✅ Profanity Word Added",
                    description=f"Added '{word}' to the profanity blacklist",
                    color=discord.Color.green()
                )
                embed.add_field(name="Total Words", value=str(len(word_list)), inline=True)
            else:
                embed = discord.Embed(
                    title="❌ Error",
                    description="Failed to add profanity word",
                    color=discord.Color.red()
                )

            await interaction.response.send_message(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error adding profanity word: {e}")
            embed = discord.Embed(
                title="❌ Error",
                description="An error occurred while adding the word",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="remove_profanity", description="Remove a word from the profanity blacklist")
    @admin_only_interaction()
    async def command_remove_profanity(self, interaction: discord.Interaction, word: str):
        """Slash command for admins to remove profanity entries"""
        try:
            success, word_list = self.protection_manager.remove_profanity_word(
                interaction.guild.id, word, interaction.user.id
            )

            if success:
                embed = discord.Embed(
                    title="✅ Profanity Word Removed",
                    description=f"Removed '{word}' from the profanity blacklist",
                    color=discord.Color.green()
                )
                embed.add_field(name="Total Words", value=str(len(word_list)), inline=True)
            else:
                embed = discord.Embed(
                    title="❌ Error",
                    description=f"Word '{word}' not found in blacklist",
                    color=discord.Color.red()
                )

            await interaction.response.send_message(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error removing profanity word: {e}")
            embed = discord.Embed(
                title="❌ Error",
                description="An error occurred while removing the word",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="list_profanity", description="List current profanity blacklist")
    @admin_only_interaction()
    async def command_list_profanity(self, interaction: discord.Interaction, page: int = 1):
        """Admin command to paginate and view current blacklist and custom rules"""
        try:
            word_list = self.protection_manager.get_profanity_list(interaction.guild.id)

            if not word_list:
                embed = discord.Embed(
                    title="📝 Profanity Blacklist",
                    description="No profanity words configured",
                    color=discord.Color.blue()
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return

            # Paginate results (20 per page)
            per_page = 20
            start_idx = (page - 1) * per_page
            end_idx = start_idx + per_page

            page_words = word_list[start_idx:end_idx]
            total_pages = (len(word_list) - 1) // per_page + 1

            embed = discord.Embed(
                title="📝 Profanity Blacklist",
                description=f"Page {page}/{total_pages} • Total: {len(word_list)} words",
                color=discord.Color.blue()
            )

            word_text = "\n".join(f"• {word}" for word in page_words)
            embed.add_field(name="Words", value=word_text, inline=False)

            await interaction.response.send_message(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error listing profanity words: {e}")
            embed = discord.Embed(
                title="❌ Error",
                description="An error occurred while retrieving the list",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="add_whitelist", description="Add a domain to the link whitelist")
    @admin_only_interaction()
    async def command_add_whitelist(self, interaction: discord.Interaction, domain_or_regex: str):
        """Slash command to add a whitelisted domain/pattern"""
        try:
            success = self.protection_manager.add_whitelist_domain(
                interaction.guild.id, domain_or_regex, interaction.user.id
            )

            if success:
                embed = discord.Embed(
                    title="✅ Domain Whitelisted",
                    description=f"Added '{domain_or_regex}' to the link whitelist",
                    color=discord.Color.green()
                )
            else:
                embed = discord.Embed(
                    title="❌ Error",
                    description="Failed to add domain to whitelist",
                    color=discord.Color.red()
                )

            await interaction.response.send_message(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error adding whitelist domain: {e}")
            embed = discord.Embed(
                title="❌ Error",
                description="An error occurred while adding the domain",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="remove_whitelist", description="Remove a domain from the link whitelist")
    @admin_only_interaction()
    async def command_remove_whitelist(self, interaction: discord.Interaction, domain_or_regex: str):
        """Slash command to remove whitelisted domain/pattern"""
        try:
            success = self.protection_manager.remove_whitelist_domain(
                interaction.guild.id, domain_or_regex, interaction.user.id
            )

            if success:
                embed = discord.Embed(
                    title="✅ Domain Removed",
                    description=f"Removed '{domain_or_regex}' from the link whitelist",
                    color=discord.Color.green()
                )
            else:
                embed = discord.Embed(
                    title="❌ Error",
                    description=f"Domain '{domain_or_regex}' not found in whitelist",
                    color=discord.Color.red()
                )

            await interaction.response.send_message(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error removing whitelist domain: {e}")
            embed = discord.Embed(
                title="❌ Error",
                description="An error occurred while removing the domain",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="set_protection_level", description="Set protection strictness level")
    @admin_only_interaction()
    @app_commands.choices(level=[
        app_commands.Choice(name="Off", value="off"),
        app_commands.Choice(name="Monitor", value="monitor"),
        app_commands.Choice(name="Moderate", value="moderate"),
        app_commands.Choice(name="Strict", value="strict")
    ])
    async def command_set_protection_level(self, interaction: discord.Interaction, level: str):
        """Admin command to set protection strictness (off, monitor, moderate, strict)"""
        try:
            config = self.protection_manager.load_protection_config(interaction.guild.id)
            config['profanity_level'] = level
            success = self.protection_manager.save_protection_config(interaction.guild.id, config)

            if success:
                embed = discord.Embed(
                    title="✅ Protection Level Updated",
                    description=f"Protection level set to: **{level.title()}**",
                    color=discord.Color.green()
                )

                # Broadcast SSE event
                try:
                    from backend import sse_manager
                    sse_manager.broadcast_event('moderation_config_update', {
                        'guild_id': str(interaction.guild.id),
                        'config': config
                    })
                except Exception as sse_error:
                    logger.warning(f"Failed to broadcast SSE event: {sse_error}")

            else:
                embed = discord.Embed(
                    title="❌ Error",
                    description="Failed to update protection level",
                    color=discord.Color.red()
                )

            await interaction.response.send_message(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error setting protection level: {e}")
            embed = discord.Embed(
                title="❌ Error",
                description="An error occurred while updating the protection level",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot):
    """Setup the moderation cog"""
    cog = Moderation(bot)
    # Managers will be set later by the bot
    await bot.add_cog(cog)
    logger.info("Moderation cog loaded")
