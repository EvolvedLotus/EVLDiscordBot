import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone
import uuid

logger = logging.getLogger(__name__)

class EmbedManager:
    """
    Manager for custom Discord embeds with persistence.
    """

    def __init__(self, data_manager):
        self.data_manager = data_manager

    def get_embeds(self, guild_id: int) -> List[Dict]:
        """
        Get all embeds for a guild.
        
        Args:
            guild_id: Guild ID
            
        Returns:
            List of embed dictionaries
        """
        try:
            data = self.data_manager.load_guild_data(guild_id, 'embeds')
            embeds_dict = data.get('embeds', {})
            
            # Convert dict to list
            embeds_list = []
            for embed_id, embed_data in embeds_dict.items():
                # Ensure ID is included
                embed_data['embed_id'] = embed_id
                embeds_list.append(embed_data)
                
            # Sort by creation date (newest first)
            embeds_list.sort(key=lambda x: x.get('created_at', ''), reverse=True)
            
            return embeds_list
        except Exception as e:
            logger.error(f"Failed to get embeds for guild {guild_id}: {e}")
            return []

    def get_embed(self, guild_id: int, embed_id: str) -> Optional[Dict]:
        """
        Get a specific embed.
        
        Args:
            guild_id: Guild ID
            embed_id: Embed ID
            
        Returns:
            Embed dictionary or None
        """
        try:
            data = self.data_manager.load_guild_data(guild_id, 'embeds')
            embeds = data.get('embeds', {})
            return embeds.get(embed_id)
        except Exception as e:
            logger.error(f"Failed to get embed {embed_id} for guild {guild_id}: {e}")
            return None

    def create_embed(self, guild_id: int, embed_data: Dict) -> Optional[Dict]:
        """
        Create a new embed.
        
        Args:
            guild_id: Guild ID
            embed_data: Embed data
            
        Returns:
            Created embed dictionary
        """
        try:
            # Generate ID if not provided
            embed_id = embed_data.get('embed_id') or str(uuid.uuid4())
            
            # Prepare embed object
            new_embed = {
                'embed_id': embed_id,
                'title': embed_data.get('title', 'Untitled Embed'),
                'description': embed_data.get('description', ''),
                'color': embed_data.get('color', '#5865F2'),
                'fields': embed_data.get('fields', []),
                'footer': embed_data.get('footer'),
                'thumbnail': embed_data.get('thumbnail'),
                'image': embed_data.get('image'),
                'channel_id': embed_data.get('channel_id'),
                'created_at': datetime.now(timezone.utc).isoformat(),
                'created_by': embed_data.get('created_by', 'System')
            }
            
            # Load current data
            data = self.data_manager.load_guild_data(guild_id, 'embeds')
            if 'embeds' not in data:
                data['embeds'] = {}
                
            # Add new embed
            data['embeds'][embed_id] = new_embed
            
            # Save data
            self.data_manager.save_guild_data(guild_id, 'config', {'embeds': data['embeds']})
            
            return new_embed
        except Exception as e:
            logger.error(f"Failed to create embed for guild {guild_id}: {e}")
            return None

    def update_embed(self, guild_id: int, embed_id: str, updates: Dict) -> Optional[Dict]:
        """
        Update an existing embed.
        
        Args:
            guild_id: Guild ID
            embed_id: Embed ID
            updates: Dictionary of updates
            
        Returns:
            Updated embed dictionary
        """
        try:
            # Load current data
            data = self.data_manager.load_guild_data(guild_id, 'embeds')
            embeds = data.get('embeds', {})
            
            if embed_id not in embeds:
                return None
                
            # Update fields
            embed = embeds[embed_id]
            for key, value in updates.items():
                if key != 'embed_id' and key != 'created_at':
                    embed[key] = value
            
            embed['updated_at'] = datetime.now(timezone.utc).isoformat()
            
            # Save data
            self.data_manager.save_guild_data(guild_id, 'config', {'embeds': embeds})
            
            return embed
        except Exception as e:
            logger.error(f"Failed to update embed {embed_id} for guild {guild_id}: {e}")
            return None

    def delete_embed(self, guild_id: int, embed_id: str) -> bool:
        """
        Delete an embed.
        
        Args:
            guild_id: Guild ID
            embed_id: Embed ID
            
        Returns:
            True if successful
        """
        try:
            # Load current data
            data = self.data_manager.load_guild_data(guild_id, 'embeds')
            embeds = data.get('embeds', {})
            
            if embed_id not in embeds:
                return False
                
            # Remove embed
            del embeds[embed_id]
            
            # Save data (passing the whole embeds dict to be saved via config/embeds path)
            # Note: DataManager.save_guild_data logic for 'config' handles 'embeds' key
            self.data_manager.save_guild_data(guild_id, 'config', {'embeds': embeds})
            
            return True
        except Exception as e:
            logger.error(f"Failed to delete embed {embed_id} for guild {guild_id}: {e}")
            return False
