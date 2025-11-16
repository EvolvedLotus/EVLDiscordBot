import discord
from datetime import datetime
from typing import Dict, List, Optional, Union
import re

class EmbedBuilder:
    """Centralized embed creation and parsing with validation"""

    # Discord embed limits
    TITLE_MAX = 256
    DESCRIPTION_MAX = 4096
    FIELD_NAME_MAX = 256
    FIELD_VALUE_MAX = 1024
    FIELDS_MAX = 25
    FOOTER_MAX = 2048
    AUTHOR_MAX = 256
    TOTAL_CHARS_MAX = 6000

    @staticmethod
    def parse_color(color_input: Union[str, int]) -> int:
        """
        Parse color from hex string, color name, or integer
        Returns discord.Color compatible integer

        Examples:
        - "#FF5733" -> 16734003
        - "red" -> discord.Color.red().value
        - 16734003 -> 16734003
        """
        if isinstance(color_input, int):
            return color_input

        if isinstance(color_input, str):
            # Remove # if present
            color_input = color_input.strip().lstrip('#')

            # Try hex conversion
            try:
                return int(color_input, 16)
            except ValueError:
                pass

            # Try color name
            color_map = {
                'red': discord.Color.red().value,
                'blue': discord.Color.blue().value,
                'green': discord.Color.green().value,
                'yellow': discord.Color.yellow().value,
                'purple': discord.Color.purple().value,
                'orange': discord.Color.orange().value,
                'gold': discord.Color.gold().value,
                'teal': discord.Color.teal().value,
            }
            return color_map.get(color_input.lower(), discord.Color.blue().value)

        return discord.Color.blue().value

    @staticmethod
    def validate_embed_data(data: Dict) -> tuple[bool, Optional[str]]:
        """Validate embed data against Discord limits"""
        total_chars = 0

        # Title validation
        if 'title' in data and data['title']:
            if len(data['title']) > EmbedBuilder.TITLE_MAX:
                return False, f"Title exceeds {EmbedBuilder.TITLE_MAX} characters"
            total_chars += len(data['title'])

        # Description validation
        if 'description' in data and data['description']:
            if len(data['description']) > EmbedBuilder.DESCRIPTION_MAX:
                return False, f"Description exceeds {EmbedBuilder.DESCRIPTION_MAX} characters"
            total_chars += len(data['description'])

        # Fields validation
        if 'fields' in data and data['fields']:
            if len(data['fields']) > EmbedBuilder.FIELDS_MAX:
                return False, f"Too many fields (max {EmbedBuilder.FIELDS_MAX})"

            for field in data['fields']:
                if len(field.get('name', '')) > EmbedBuilder.FIELD_NAME_MAX:
                    return False, f"Field name exceeds {EmbedBuilder.FIELD_NAME_MAX} characters"
                if len(field.get('value', '')) > EmbedBuilder.FIELD_VALUE_MAX:
                    return False, f"Field value exceeds {EmbedBuilder.FIELD_VALUE_MAX} characters"
                total_chars += len(field.get('name', '')) + len(field.get('value', ''))

        # Footer validation
        if 'footer_text' in data and data['footer_text']:
            if len(data['footer_text']) > EmbedBuilder.FOOTER_MAX:
                return False, f"Footer exceeds {EmbedBuilder.FOOTER_MAX} characters"
            total_chars += len(data['footer_text'])

        # Author validation
        if 'author_name' in data and data['author_name']:
            if len(data['author_name']) > EmbedBuilder.AUTHOR_MAX:
                return False, f"Author name exceeds {EmbedBuilder.AUTHOR_MAX} characters"
            total_chars += len(data['author_name'])

        # Total character limit
        if total_chars > EmbedBuilder.TOTAL_CHARS_MAX:
            return False, f"Total characters exceed {EmbedBuilder.TOTAL_CHARS_MAX}"

        return True, None

    @staticmethod
    def build_embed(data: Dict) -> discord.Embed:
        """Build discord.Embed from data dictionary"""
        # Parse color
        color = EmbedBuilder.parse_color(data.get('color', '#7289da'))

        # Create base embed
        embed = discord.Embed(
            title=data.get('title'),
            description=data.get('description'),
            color=color,
            timestamp=datetime.utcnow() if data.get('timestamp', True) else None
        )

        # Add fields
        for field in data.get('fields', []):
            embed.add_field(
                name=field['name'],
                value=field['value'],
                inline=field.get('inline', False)
            )

        # Set thumbnail
        if data.get('thumbnail_url'):
            embed.set_thumbnail(url=data['thumbnail_url'])

        # Set image
        if data.get('image_url'):
            embed.set_image(url=data['image_url'])

        # Set footer
        if data.get('footer_text'):
            embed.set_footer(
                text=data['footer_text'],
                icon_url=data.get('footer_icon_url')
            )

        # Set author
        if data.get('author_name'):
            embed.set_author(
                name=data['author_name'],
                icon_url=data.get('author_icon_url')
            )

        return embed

    @staticmethod
    def embed_to_dict(embed: discord.Embed) -> Dict:
        """Convert discord.Embed to storable dictionary"""
        data = {
            'title': embed.title,
            'description': embed.description,
            'color': f"#{embed.color.value:06x}" if embed.color else None,
            'fields': [],
            'thumbnail_url': embed.thumbnail.url if embed.thumbnail else None,
            'image_url': embed.image.url if embed.image else None,
            'footer_text': embed.footer.text if embed.footer else None,
            'footer_icon_url': embed.footer.icon_url if embed.footer else None,
            'author_name': embed.author.name if embed.author else None,
            'author_icon_url': embed.author.icon_url if embed.author else None,
        }

        for field in embed.fields:
            data['fields'].append({
                'name': field.name,
                'value': field.value,
                'inline': field.inline
            })

        return data

    @staticmethod
    def apply_template(data: Dict, template: Dict) -> Dict:
        """Apply template defaults to embed data"""
        result = template.copy()
        result.update(data)
        return result

    @staticmethod
    def create_task_embed(task_data: Dict) -> discord.Embed:
        """Create embed for task display"""
        embed = discord.Embed(
            title=f"📋 {task_data['name']}",
            description=task_data.get('description', 'No description'),
            color=discord.Color.blue()
        )

        embed.add_field(name="Reward", value=f"💰 {task_data['reward']} coins", inline=True)
        embed.add_field(name="Time Limit", value=f"⏰ {task_data.get('duration_hours', 24)} hours", inline=True)

        status = task_data.get('status', 'pending')
        status_emoji = {"pending": "🟡", "active": "🟢", "completed": "✅"}.get(status, "⚪")
        embed.add_field(name="Status", value=f"{status_emoji} {status.title()}", inline=True)

        embed.set_footer(text=f"Task ID: {task_data['id']} | Use /claim {task_data['id']} to start")

        return embed

    @staticmethod
    def create_shop_embed(item_data: Dict, config: Dict) -> discord.Embed:
        """Create embed for shop item display"""
        currency_symbol = config.get('currency_symbol', '$')

        embed = discord.Embed(
            title=item_data['name'],
            description=item_data.get('description', 'No description'),
            color=discord.Color.green() if item_data.get('is_active', True) else discord.Color.grey()
        )

        embed.add_field(
            name="Price",
            value=f"{currency_symbol}{item_data['price']}",
            inline=True
        )

        stock = item_data.get('stock', -1)
        stock_text = "♾️ Unlimited" if stock == -1 else f"📦 {stock} available"
        embed.add_field(name="Stock", value=stock_text, inline=True)

        category = item_data.get('category', 'misc')
        embed.add_field(name="Category", value=f"🏷️ {category.title()}", inline=True)

        embed.set_footer(text="Use /buy <item_id> to purchase")

        return embed

    @staticmethod
    def create_announcement_embed(announcement_data: Dict) -> discord.Embed:
        """Create embed for announcement display"""
        color = EmbedBuilder.parse_color(announcement_data.get('embed', {}).get('color', '#5865F2'))

        embed = discord.Embed(
            title=announcement_data['title'],
            description=announcement_data['content'],
            color=color,
            timestamp=datetime.fromisoformat(announcement_data['created_at'])
        )

        if announcement_data.get('embed', {}).get('thumbnail'):
            embed.set_thumbnail(url=announcement_data['embed']['thumbnail'])

        embed.set_footer(text=announcement_data['embed']['footer'])

        return embed

    @staticmethod
    def create_error_embed(title: str, description: str, color: str = "red") -> discord.Embed:
        """Create standardized error embed"""
        color_value = EmbedBuilder.parse_color(color)

        embed = discord.Embed(
            title=f"❌ {title}",
            description=description,
            color=color_value,
            timestamp=datetime.utcnow()
        )

        embed.set_footer(text="Error Notification")
        return embed

    @staticmethod
    def create_success_embed(title: str, description: str, color: str = "green") -> discord.Embed:
        """Create standardized success embed"""
        color_value = EmbedBuilder.parse_color(color)

        embed = discord.Embed(
            title=f"✅ {title}",
            description=description,
            color=color_value,
            timestamp=datetime.utcnow()
        )

        embed.set_footer(text="Success")
        return embed
