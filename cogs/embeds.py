import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional, Literal
import asyncio
from datetime import datetime
from core.embed_builder import EmbedBuilder

class EmbedsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.data_manager = bot.data_manager
        self._edit_locks = {}  # Prevent concurrent edits

    def _get_lock(self, guild_id: int, embed_id: str):
        """Get or create lock for embed editing"""
        key = f"{guild_id}_{embed_id}"
        if key not in self._edit_locks:
            self._edit_locks[key] = asyncio.Lock()
        return self._edit_locks[key]

    @app_commands.command(name="embed_create", description="Create a custom embed")
    @app_commands.describe(
        title="Embed title",
        description="Embed description",
        color="Color (hex or name)",
        channel="Channel to send embed"
    )
    async def create_embed(
        self,
        interaction: discord.Interaction,
        title: str,
        description: str,
        color: Optional[str] = None,
        channel: Optional[discord.TextChannel] = None
    ):
        """Create and send a custom embed"""
        await interaction.response.defer()

        guild_id = interaction.guild_id
        channel = channel or interaction.channel

        # Build embed data
        embed_data = {
            'title': title,
            'description': description,
            'color': color or '#7289da',
            'type': 'custom',
            'created_by': str(interaction.user.id),
            'created_at': datetime.utcnow().isoformat(),
            'channel_id': str(channel.id)
        }

        # Validate
        valid, error = EmbedBuilder.validate_embed_data(embed_data)
        if not valid:
            await interaction.followup.send(f"❌ Validation error: {error}", ephemeral=True)
            return

        # Build Discord embed
        embed = EmbedBuilder.build_embed(embed_data)

        # Send to Discord
        try:
            message = await channel.send(embed=embed)
        except discord.Forbidden:
            await interaction.followup.send("❌ Missing permissions to send embeds", ephemeral=True)
            return
        except Exception as e:
            await interaction.followup.send(f"❌ Error sending embed: {e}", ephemeral=True)
            return

        # Store in database
        embed_id = f"emb_{int(datetime.utcnow().timestamp() * 1000)}"
        embed_data['id'] = embed_id
        embed_data['message_id'] = str(message.id)
        embed_data['is_active'] = True

        embeds_data = self.data_manager.load_guild_data(guild_id, 'embeds')
        if embeds_data is None:
            embeds_data = {'embeds': {}, 'templates': {}, 'settings': {}}

        embeds_data['embeds'][embed_id] = embed_data
        self.data_manager.save_guild_data(guild_id, 'embeds', embeds_data)

        await interaction.followup.send(
            f"✅ Embed created! ID: `{embed_id}`\n"
            f"Message: {message.jump_url}",
            ephemeral=True
        )

    @app_commands.command(name="embed_edit", description="Edit an existing embed")
    @app_commands.describe(
        embed_id="Embed ID to edit",
        title="New title (optional)",
        description="New description (optional)",
        color="New color (optional)"
    )
    async def edit_embed(
        self,
        interaction: discord.Interaction,
        embed_id: str,
        title: Optional[str] = None,
        description: Optional[str] = None,
        color: Optional[str] = None
    ):
        """Edit an existing embed by ID"""
        await interaction.response.defer()

        guild_id = interaction.guild_id

        # Get lock to prevent concurrent edits
        async with self._get_lock(guild_id, embed_id):
            # Load embed data
            embeds_data = self.data_manager.load_guild_data(guild_id, 'embeds')
            if not embeds_data or embed_id not in embeds_data.get('embeds', {}):
                await interaction.followup.send("❌ Embed not found", ephemeral=True)
                return

            embed_data = embeds_data['embeds'][embed_id]

            # Update fields
            if title is not None:
                embed_data['title'] = title
            if description is not None:
                embed_data['description'] = description
            if color is not None:
                embed_data['color'] = color

            embed_data['updated_at'] = datetime.utcnow().isoformat()

            # Validate
            valid, error = EmbedBuilder.validate_embed_data(embed_data)
            if not valid:
                await interaction.followup.send(f"❌ Validation error: {error}", ephemeral=True)
                return

            # Update Discord message
            try:
                channel = self.bot.get_channel(int(embed_data['channel_id']))
                if not channel:
                    await interaction.followup.send("❌ Channel not found", ephemeral=True)
                    return

                message = await channel.fetch_message(int(embed_data['message_id']))
                new_embed = EmbedBuilder.build_embed(embed_data)
                await message.edit(embed=new_embed)

            except discord.NotFound:
                await interaction.followup.send("❌ Message not found in Discord", ephemeral=True)
                return
            except discord.Forbidden:
                await interaction.followup.send("❌ Missing permissions to edit", ephemeral=True)
                return
            except Exception as e:
                await interaction.followup.send(f"❌ Error editing: {e}", ephemeral=True)
                return

            # Save to database
            self.data_manager.save_guild_data(guild_id, 'embeds', embeds_data)

            await interaction.followup.send(
                f"✅ Embed updated!\n{message.jump_url}",
                ephemeral=True
            )

    @app_commands.command(name="embed_delete", description="Delete an embed")
    @app_commands.describe(embed_id="Embed ID to delete")
    async def delete_embed(
        self,
        interaction: discord.Interaction,
        embed_id: str
    ):
        """Delete an embed and its message"""
        await interaction.response.defer()

        guild_id = interaction.guild_id

        # Load embed data
        embeds_data = self.data_manager.load_guild_data(guild_id, 'embeds')
        if not embeds_data or embed_id not in embeds_data.get('embeds', {}):
            await interaction.followup.send("❌ Embed not found", ephemeral=True)
            return

        embed_data = embeds_data['embeds'][embed_id]

        # Delete Discord message
        try:
            channel = self.bot.get_channel(int(embed_data['channel_id']))
            if channel:
                message = await channel.fetch_message(int(embed_data['message_id']))
                await message.delete()
        except discord.NotFound:
            pass  # Message already deleted
        except Exception as e:
            # Continue with database deletion even if Discord fails
            pass

        # Remove from database
        del embeds_data['embeds'][embed_id]
        self.data_manager.save_guild_data(guild_id, 'embeds', embeds_data)

        await interaction.followup.send("✅ Embed deleted", ephemeral=True)

    @app_commands.command(name="embed_list", description="List all embeds")
    async def list_embeds(self, interaction: discord.Interaction):
        """List all embeds in the server"""
        guild_id = interaction.guild_id

        embeds_data = self.data_manager.load_guild_data(guild_id, 'embeds')
        if not embeds_data or not embeds_data.get('embeds'):
            await interaction.response.send_message("No embeds found", ephemeral=True)
            return

        embed = discord.Embed(
            title="📋 Server Embeds",
            color=discord.Color.blue()
        )

        for embed_id, data in list(embeds_data['embeds'].items())[:10]:
            channel = self.bot.get_channel(int(data['channel_id']))
            channel_mention = channel.mention if channel else "Unknown"

            embed.add_field(
                name=f"ID: {embed_id}",
                value=f"**{data.get('title', 'No title')}**\n"
                      f"Type: {data.get('type', 'custom')}\n"
                      f"Channel: {channel_mention}",
                inline=False
            )

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="announce_embed", description="Send an announcement embed")
    @app_commands.describe(
        title="Announcement title",
        message="Announcement message",
        channel="Channel to send to (defaults to current)",
        mention_everyone="Mention @everyone"
    )
    async def announce(
        self,
        interaction: discord.Interaction,
        title: str,
        message: str,
        channel: Optional[discord.TextChannel] = None,
        mention_everyone: bool = False
    ):
        """Send an announcement using embeds"""
        # Check permissions
        if not interaction.user.guild_permissions.manage_messages:
            await interaction.response.send_message(
                "❌ You need Manage Messages permission to use this command",
                ephemeral=True
            )
            return

        await interaction.response.defer()

        channel = channel or interaction.channel
        guild_id = interaction.guild_id

        # Build announcement embed
        embed_data = {
            'type': 'announcement',
            'title': f"📢 {title}",
            'description': message,
            'color': '#e74c3c',
            'footer_text': f"Announced by {interaction.user.name}",
            'footer_icon_url': str(interaction.user.display_avatar.url),
            'created_by': str(interaction.user.id),
            'created_at': datetime.utcnow().isoformat(),
            'channel_id': str(channel.id)
        }

        # Validate
        valid, error = EmbedBuilder.validate_embed_data(embed_data)
        if not valid:
            await interaction.followup.send(f"❌ Validation error: {error}", ephemeral=True)
            return

        # Build and send
        embed = EmbedBuilder.build_embed(embed_data)

        try:
            content = "@everyone" if mention_everyone else None
            msg = await channel.send(content=content, embed=embed)
        except discord.Forbidden:
            await interaction.followup.send("❌ Missing permissions", ephemeral=True)
            return
        except Exception as e:
            await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)
            return

        # Store embed
        embed_id = f"emb_{int(datetime.utcnow().timestamp() * 1000)}"
        embed_data['id'] = embed_id
        embed_data['message_id'] = str(msg.id)
        embed_data['is_active'] = True

        embeds_data = self.data_manager.load_guild_data(guild_id, 'embeds')
        if not embeds_data:
            embeds_data = {'embeds': {}, 'templates': {}, 'settings': {}}

        embeds_data['embeds'][embed_id] = embed_data
        self.data_manager.save_guild_data(guild_id, 'embeds', embeds_data)

        await interaction.followup.send(
            f"✅ Announcement sent! Embed ID: `{embed_id}`",
            ephemeral=True
        )

async def setup(bot):
    await bot.add_cog(EmbedsCog(bot))
