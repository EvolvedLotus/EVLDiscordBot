"""
Announcement management with loop prevention and Discord sync
"""
import discord
from datetime import datetime
from typing import Optional, Dict, Any, List
import asyncio
from core.data_manager import DataManager
import logging

logger = logging.getLogger(__name__)

class AnnouncementManager:
    def __init__(self, data_manager: DataManager, bot=None):
        self.data_manager = data_manager
        self.bot = bot
        self._processing_lock = asyncio.Lock()
        self._sync_in_progress = set()  # Prevents sync loops

    def set_bot(self, bot):
        """Set the bot instance (for delayed initialization)"""
        self.bot = bot

    def _generate_announcement_id(self) -> str:
        """Generate unique announcement ID"""
        timestamp = int(datetime.utcnow().timestamp() * 1000)
        return f"ann_{timestamp}"

    async def create_announcement(
        self,
        guild_id: str,
        title: str,
        content: str,
        channel_id: str,
        author_id: str,
        author_name: str,
        announcement_type: str = "general",
        mentions: Dict[str, Any] = None,
        embed_color: str = "#5865F2",
        thumbnail: str = None,
        auto_pin: bool = False
    ) -> Dict[str, Any]:
        """
        Create announcement and post to Discord
        Returns: announcement object with message_id
        """
        async with self._processing_lock:
            # Prevent duplicate processing
            announcement_id = self._generate_announcement_id()
            if announcement_id in self._sync_in_progress:
                raise ValueError("Announcement already being processed")

            self._sync_in_progress.add(announcement_id)

            try:
                # Load announcement data
                ann_data = self.data_manager.load_guild_data(guild_id, "announcements")
                if not ann_data:
                    ann_data = {
                        "announcements": {},
                        "task_announcements": {},
                        "settings": {
                            "default_announcement_channel": None,
                            "auto_pin_task_announcements": True,
                            "announcement_role": None
                        }
                    }

                # Get guild and channel
                guild = self.bot.get_guild(int(guild_id))
                if not guild:
                    raise ValueError(f"Guild {guild_id} not found")

                channel = guild.get_channel(int(channel_id))
                if not channel:
                    raise ValueError(f"Channel {channel_id} not found")

                # Check bot permissions
                permissions = channel.permissions_for(guild.me)
                if not permissions.send_messages:
                    raise PermissionError("Bot lacks send_messages permission")
                if auto_pin and not permissions.manage_messages:
                    raise PermissionError("Bot lacks manage_messages permission for pinning")

                # Create announcement object BEFORE Discord post
                announcement = {
                    "id": announcement_id,
                    "title": title,
                    "content": content,
                    "type": announcement_type,
                    "channel_id": channel_id,
                    "message_id": None,  # Will be set after Discord post
                    "author_id": author_id,
                    "author_name": author_name,
                    "created_at": datetime.utcnow().isoformat(),
                    "pinned": False,
                    "mentions": mentions or {"everyone": False, "roles": [], "users": []},
                    "embed": {
                        "color": embed_color,
                        "thumbnail": thumbnail,
                        "footer": f"Posted by {author_name}"
                    }
                }

                # Save to data BEFORE Discord post (prevents race condition)
                ann_data["announcements"][announcement_id] = announcement
                self.data_manager.save_guild_data(guild_id, "announcements", ann_data)

                # Create Discord embed
                embed = self._create_announcement_embed(announcement)

                # Build mention content
                mention_content = self._build_mention_string(guild, mentions)

                # Post to Discord
                try:
                    message = await channel.send(content=mention_content, embed=embed)

                    # Update with message_id
                    announcement["message_id"] = str(message.id)

                    # Pin if requested
                    if auto_pin:
                        try:
                            await message.pin()
                            announcement["pinned"] = True
                        except discord.HTTPException as e:
                            # Pin failed but announcement posted - log but don't fail
                            print(f"Failed to pin announcement {announcement_id}: {e}")

                    # Save updated announcement with message_id
                    ann_data["announcements"][announcement_id] = announcement
                    self.data_manager.save_guild_data(guild_id, "announcements", ann_data)

                    return announcement

                except discord.HTTPException as e:
                    # Discord post failed - remove from data
                    del ann_data["announcements"][announcement_id]
                    self.data_manager.save_guild_data(guild_id, "announcements", ann_data)
                    raise RuntimeError(f"Failed to post announcement to Discord: {e}")

            finally:
                self._sync_in_progress.discard(announcement_id)

    async def create_task_announcement(
        self,
        guild_id: str,
        task_id: str,
        channel_id: str,
        author_id: str,
        author_name: str,
        auto_pin: bool = None
    ) -> Dict[str, Any]:
        """
        Create announcement for a task
        Links announcement to task for tracking
        """
        # Load task data
        task_data = self.data_manager.load_guild_data(guild_id, "tasks")
        if not task_data or str(task_id) not in task_data.get("tasks", {}):
            raise ValueError(f"Task {task_id} not found")

        task = task_data["tasks"][str(task_id)]

        # Load config for auto-pin setting
        if auto_pin is None:
            ann_data = self.data_manager.load_guild_data(guild_id, "announcements")
            auto_pin = ann_data.get("settings", {}).get("auto_pin_task_announcements", True)

        # Build task announcement content
        title = f"📋 New Task Available: {task['name']}"
        content = f"{task.get('description', 'No description provided')}\n\n"
        content += f"**Reward:** {task['reward']} coins\n"
        content += f"**Duration:** {task.get('duration_hours', 24)} hours\n"
        if task.get('url'):
            content += f"**Link:** {task['url']}\n"
        content += f"\n*Use `/claim {task_id}` to start this task!*"

        # Create announcement
        announcement = await self.create_announcement(
            guild_id=guild_id,
            title=title,
            content=content,
            channel_id=channel_id,
            author_id=author_id,
            author_name=author_name,
            announcement_type="task",
            embed_color="#FFA500",
            auto_pin=auto_pin
        )

        # Link announcement to task
        ann_data = self.data_manager.load_guild_data(guild_id, "announcements")
        ann_data["task_announcements"][str(task_id)] = {
            "announcement_id": announcement["id"],
            "task_id": str(task_id),
            "posted_at": announcement["created_at"]
        }
        self.data_manager.save_guild_data(guild_id, "announcements", ann_data)

        # Update task with announcement reference
        task["announcement_id"] = announcement["id"]
        task_data["tasks"][str(task_id)] = task
        self.data_manager.save_guild_data(guild_id, "tasks", task_data)

        return announcement

    async def edit_announcement(
        self,
        guild_id: str,
        announcement_id: str,
        title: str = None,
        content: str = None,
        embed_color: str = None
    ) -> Dict[str, Any]:
        """
        Edit existing announcement and sync to Discord
        """
        async with self._processing_lock:
            if announcement_id in self._sync_in_progress:
                raise ValueError("Announcement currently being modified")

            self._sync_in_progress.add(announcement_id)

            try:
                # Load announcement
                ann_data = self.data_manager.load_guild_data(guild_id, "announcements")
                if announcement_id not in ann_data.get("announcements", {}):
                    raise ValueError(f"Announcement {announcement_id} not found")

                announcement = ann_data["announcements"][announcement_id]

                # Update fields
                if title is not None:
                    announcement["title"] = title
                if content is not None:
                    announcement["content"] = content
                if embed_color is not None:
                    announcement["embed"]["color"] = embed_color

                # Save to data first
                ann_data["announcements"][announcement_id] = announcement
                self.data_manager.save_guild_data(guild_id, "announcements", ann_data)

                # Update Discord message
                if announcement.get("message_id"):
                    guild = self.bot.get_guild(int(guild_id))
                    if guild:
                        channel = guild.get_channel(int(announcement["channel_id"]))
                        if channel:
                            try:
                                message = await channel.fetch_message(int(announcement["message_id"]))
                                embed = self._create_announcement_embed(announcement)
                                await message.edit(embed=embed)
                            except discord.NotFound:
                                # Message deleted - clear message_id
                                announcement["message_id"] = None
                                ann_data["announcements"][announcement_id] = announcement
                                self.data_manager.save_guild_data(guild_id, "announcements", ann_data)
                            except discord.HTTPException as e:
                                print(f"Failed to edit Discord message: {e}")

                return announcement

            finally:
                self._sync_in_progress.discard(announcement_id)

    async def delete_announcement(
        self,
        guild_id: str,
        announcement_id: str,
        delete_discord_message: bool = True
    ) -> bool:
        """
        Delete announcement from data and optionally from Discord
        """
        async with self._processing_lock:
            if announcement_id in self._sync_in_progress:
                raise ValueError("Announcement currently being modified")

            self._sync_in_progress.add(announcement_id)

            try:
                ann_data = self.data_manager.load_guild_data(guild_id, "announcements")
                if announcement_id not in ann_data.get("announcements", {}):
                    return False

                announcement = ann_data["announcements"][announcement_id]

                # Delete Discord message first
                if delete_discord_message and announcement.get("message_id"):
                    guild = self.bot.get_guild(int(guild_id))
                    if guild:
                        channel = guild.get_channel(int(announcement["channel_id"]))
                        if channel:
                            try:
                                message = await channel.fetch_message(int(announcement["message_id"]))
                                await message.delete()
                            except discord.NotFound:
                                pass  # Already deleted
                            except discord.HTTPException as e:
                                print(f"Failed to delete Discord message: {e}")

                # Remove from data
                del ann_data["announcements"][announcement_id]

                # Remove task link if exists
                task_links = [tid for tid, link in ann_data.get("task_announcements", {}).items()
                             if link.get("announcement_id") == announcement_id]
                for task_id in task_links:
                    del ann_data["task_announcements"][task_id]

                self.data_manager.save_guild_data(guild_id, "announcements", ann_data)
                return True

            finally:
                self._sync_in_progress.discard(announcement_id)

    async def pin_announcement(self, guild_id: str, announcement_id: str) -> bool:
        """Pin announcement message in Discord"""
        ann_data = self.data_manager.load_guild_data(guild_id, "announcements")
        if announcement_id not in ann_data.get("announcements", {}):
            raise ValueError(f"Announcement {announcement_id} not found")

        announcement = ann_data["announcements"][announcement_id]

        if not announcement.get("message_id"):
            raise ValueError("Announcement has no Discord message")

        guild = self.bot.get_guild(int(guild_id))
        if not guild:
            raise ValueError(f"Guild {guild_id} not found")

        channel = guild.get_channel(int(announcement["channel_id"]))
        if not channel:
            raise ValueError(f"Channel not found")

        try:
            message = await channel.fetch_message(int(announcement["message_id"]))
            await message.pin()

            # Update data
            announcement["pinned"] = True
            ann_data["announcements"][announcement_id] = announcement
            self.data_manager.save_guild_data(guild_id, "announcements", ann_data)

            return True
        except discord.HTTPException as e:
            raise RuntimeError(f"Failed to pin message: {e}")

    async def unpin_announcement(self, guild_id: str, announcement_id: str) -> bool:
        """Unpin announcement message in Discord"""
        ann_data = self.data_manager.load_guild_data(guild_id, "announcements")
        if announcement_id not in ann_data.get("announcements", {}):
            raise ValueError(f"Announcement {announcement_id} not found")

        announcement = ann_data["announcements"][announcement_id]

        if not announcement.get("message_id"):
            raise ValueError("Announcement has no Discord message")

        guild = self.bot.get_guild(int(guild_id))
        channel = guild.get_channel(int(announcement["channel_id"]))

        try:
            message = await channel.fetch_message(int(announcement["message_id"]))
            await message.unpin()

            announcement["pinned"] = False
            ann_data["announcements"][announcement_id] = announcement
            self.data_manager.save_guild_data(guild_id, "announcements", ann_data)

            return True
        except discord.HTTPException as e:
            raise RuntimeError(f"Failed to unpin message: {e}")

    def _create_announcement_embed(self, announcement: Dict[str, Any]) -> discord.Embed:
        """Create Discord embed from announcement data"""
        color = int(announcement["embed"]["color"].replace("#", ""), 16)
        embed = discord.Embed(
            title=announcement["title"],
            description=announcement["content"],
            color=color,
            timestamp=datetime.fromisoformat(announcement["created_at"])
        )

        if announcement["embed"].get("thumbnail"):
            embed.set_thumbnail(url=announcement["embed"]["thumbnail"])

        embed.set_footer(text=announcement["embed"]["footer"])

        return embed

    def _build_mention_string(self, guild: discord.Guild, mentions: Dict[str, Any]) -> str:
        """Build mention string from mentions dict"""
        if not mentions:
            return ""

        parts = []

        if mentions.get("everyone"):
            parts.append("@everyone")

        for role_id in mentions.get("roles", []):
            role = guild.get_role(int(role_id))
            if role:
                parts.append(role.mention)

        for user_id in mentions.get("users", []):
            parts.append(f"<@{user_id}>")

        return " ".join(parts) if parts else ""

    def _build_announcement_embed(self, announcement_data: Dict[str, Any]) -> discord.Embed:
        """Convert announcement data to Discord embed"""
        color = int(announcement_data["embed"]["color"].replace("#", ""), 16)
        embed = discord.Embed(
            title=announcement_data["title"],
            description=announcement_data["content"],
            color=color,
            timestamp=datetime.fromisoformat(announcement_data["created_at"])
        )

        if announcement_data["embed"].get("thumbnail"):
            embed.set_thumbnail(url=announcement_data["embed"]["thumbnail"])

        embed.set_footer(text=announcement_data["embed"]["footer"])
        return embed

    async def _post_announcement(self, guild, channel_id: str, embed_data: discord.Embed) -> str:
        """Post announcement to Discord, return message_id"""
        channel = guild.get_channel(int(channel_id))
        if not channel:
            raise ValueError(f"Channel {channel_id} not found")

        message = await channel.send(embed=embed_data)
        return str(message.id)

    async def _edit_announcement(self, guild, channel_id: str, message_id: str, new_embed: discord.Embed) -> bool:
        """Update existing announcement message"""
        channel = guild.get_channel(int(channel_id))
        if not channel:
            return False

        try:
            message = await channel.fetch_message(int(message_id))
            await message.edit(embed=new_embed)
            return True
        except discord.NotFound:
            return False

    async def _delete_announcement(self, guild, channel_id: str, message_id: str) -> bool:
        """Remove announcement message from Discord"""
        channel = guild.get_channel(int(channel_id))
        if not channel:
            return False

        try:
            message = await channel.fetch_message(int(message_id))
            await message.delete()
            return True
        except discord.NotFound:
            return False

    def get_announcements(self, guild_id: str) -> List[Dict]:
        """
        Get all announcements for a guild.
        
        Args:
            guild_id: Guild ID
            
        Returns:
            List of announcement dictionaries
        """
        try:
            data = self.data_manager.load_guild_data(guild_id, 'announcements')
            announcements_dict = data.get('announcements', {})
            
            announcements_list = []
            for ann_id, ann in announcements_dict.items():
                ann['announcement_id'] = ann_id
                announcements_list.append(ann)
                
            # Sort by creation date (newest first)
            announcements_list.sort(key=lambda x: x.get('created_at', ''), reverse=True)
            
            return announcements_list
        except Exception as e:
            logger.error(f"Failed to get announcements for guild {guild_id}: {e}")
            return []

    def _pin_message(self, guild, channel_id: str, message_id: str):
        """Pin announcement in channel"""
        if not guild:
            return
            
        try:
            channel = guild.get_channel(int(channel_id))
            if channel:
                # We need to schedule this as a coroutine since we're in a sync context potentially
                # But AnnouncementManager methods are usually called from async contexts
                # For now, we'll assume the caller handles the async nature or we use the bot loop
                if self.bot:
                    asyncio.run_coroutine_threadsafe(
                        self._async_pin(channel, int(message_id)),
                        self.bot.loop
                    )
        except Exception as e:
            logger.error(f"Failed to pin message: {e}")

    async def _async_pin(self, channel, message_id):
        try:
            message = await channel.fetch_message(message_id)
            await message.pin()
        except Exception as e:
            logger.error(f"Async pin failed: {e}")

    def _unpin_message(self, guild, channel_id: str, message_id: str):
        """Unpin announcement from channel"""
        if not guild:
            return
            
        try:
            channel = guild.get_channel(int(channel_id))
            if channel:
                if self.bot:
                    asyncio.run_coroutine_threadsafe(
                        self._async_unpin(channel, int(message_id)),
                        self.bot.loop
                    )
        except Exception as e:
            logger.error(f"Failed to unpin message: {e}")

    async def _async_unpin(self, channel, message_id):
        try:
            message = await channel.fetch_message(message_id)
            await message.unpin()
        except Exception as e:
            logger.error(f"Async unpin failed: {e}")
