"""
Shared utility functions for the bot
"""

import discord
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import re

def format_currency(amount: int, symbol: str = "$") -> str:
    """Format currency amount with symbol"""
    if amount >= 0:
        return f"{symbol}{amount:,}"
    else:
        return f"-{symbol}{abs(amount):,}"

def format_timestamp(timestamp: str) -> str:
    """Format ISO timestamp for Discord"""
    try:
        dt = datetime.fromisoformat(timestamp)
        return f"<t:{int(dt.timestamp())}:R>"
    except:
        return "Unknown"

def parse_duration(duration_str: str) -> Optional[timedelta]:
    """Parse duration string like '1h 30m' or '2d'"""
    if not duration_str:
        return None

    total_seconds = 0
    pattern = r'(\d+)([smhd])'
    matches = re.findall(pattern, duration_str.lower())

    multipliers = {
        's': 1,
        'm': 60,
        'h': 3600,
        'd': 86400
    }

    for amount, unit in matches:
        total_seconds += int(amount) * multipliers.get(unit, 0)

    return timedelta(seconds=total_seconds) if total_seconds > 0 else None

def truncate_text(text: str, max_length: int = 100, suffix: str = "...") -> str:
    """Truncate text to max length with suffix"""
    if len(text) <= max_length:
        return text
    return text[:max_length - len(suffix)] + suffix

def create_embed(title: str = None, description: str = None,
                color: int = 0x3498db, **kwargs) -> discord.Embed:
    """Create a standardized embed"""
    embed = discord.Embed(
        title=title,
        description=description,
        color=color,
        **kwargs
    )
    return embed

def add_embed_footer(embed: discord.Embed, ctx, text: str = None):
    """Add standardized footer to embed"""
    footer_text = text or f"Requested by {ctx.author.name}"
    embed.set_footer(text=footer_text, icon_url=ctx.author.avatar.url if ctx.author.avatar else None)
    embed.timestamp = datetime.utcnow()

def calculate_level_xp(level: int) -> int:
    """Calculate XP required for a level (example RPG system)"""
    return level * 100 + (level - 1) * 50

def get_level_from_xp(xp: int) -> int:
    """Get level from XP amount"""
    level = 1
    while calculate_level_xp(level + 1) <= xp:
        level += 1
    return level

def format_number(num: int) -> str:
    """Format large numbers with K, M, B suffixes"""
    if num < 1000:
        return str(num)
    elif num < 1000000:
        return f"{num/1000:.1f}K"
    elif num < 1000000000:
        return f"{num/1000000:.1f}M"
    else:
        return f"{num/1000000000:.1f}B"

def validate_discord_id(discord_id: str) -> bool:
    """Validate Discord ID format"""
    return discord_id.isdigit() and 17 <= len(discord_id) <= 19

def get_user_display_name(user) -> str:
    """Get the best display name for a user"""
    if hasattr(user, 'display_name') and user.display_name:
        return user.display_name
    elif hasattr(user, 'name'):
        return user.name
    else:
        return str(user)

def safe_getattr(obj, attr: str, default=None):
    """Safely get attribute from object"""
    try:
        return getattr(obj, attr, default)
    except:
        return default

def chunk_list(lst: list, chunk_size: int):
    """Split list into chunks of specified size"""
    for i in range(0, len(lst), chunk_size):
        yield lst[i:i + chunk_size]

def find_closest_match(target: str, options: list, threshold: float = 0.8) -> Optional[str]:
    """Find closest string match using simple ratio"""
    try:
        from difflib import SequenceMatcher

        best_match = None
        best_ratio = 0

        for option in options:
            ratio = SequenceMatcher(None, target.lower(), option.lower()).ratio()
            if ratio > best_ratio and ratio >= threshold:
                best_match = option
                best_ratio = ratio

        return best_match
    except ImportError:
        # Fallback if difflib not available
        return None

def sanitize_filename(filename: str) -> str:
    """Sanitize filename for safe file operations"""
    return re.sub(r'[<>:"/\\|?*]', '_', filename)

def is_valid_url(url: str) -> bool:
    """Basic URL validation"""
    url_pattern = re.compile(
        r'^https?://'  # http:// or https://
        r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # domain...
        r'localhost|'  # localhost...
        r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # ...or ip
        r'(?::\d+)?'  # optional port
        r'(?:/?|[/?]\S+)$', re.IGNORECASE)

    return url_pattern.match(url) is not None

def format_time_remaining(target_time: datetime) -> str:
    """Format time remaining until target time"""
    now = datetime.now()
    if target_time <= now:
        return "Expired"

    diff = target_time - now
    days = diff.days
    hours, remainder = divmod(diff.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)

    parts = []
    if days > 0:
        parts.append(f"{days}d")
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes}m")
    if seconds > 0 and not parts:  # Only show seconds if no larger units
        parts.append(f"{seconds}s")

    return " ".join(parts) if parts else "Less than a minute"

# === VALIDATION FUNCTIONS ===

def validate_currency_amount(amount: int, min_value: int = 1, max_value: int = 1000000):
    """
    Validate currency amount is within acceptable range.
    Raises ValueError with user-friendly message if invalid.
    """
    if amount < min_value:
        raise ValueError(f"Amount must be at least {min_value}")
    if amount > max_value:
        raise ValueError(f"Amount cannot exceed {max_value}")
    return amount

def validate_target_user(interaction, target_user):
    """
    Validate target user for transactions.
    Check not a bot, not the command user (for transfers), exists in guild.
    Returns True if valid, raises ValueError with message if not.
    """
    if target_user.bot:
        raise ValueError("Cannot give currency to bots")
    if target_user.id == interaction.user.id:
        raise ValueError("Cannot give currency to yourself")
    if target_user not in interaction.guild.members:
        raise ValueError("User not found in this server")
    return True

def validate_channel_permissions(guild, channel_id, required_permissions):
    """
    Validate bot has required permissions in channel.
    required_permissions: list like ['send_messages', 'embed_links', 'attach_files']
    Returns True if has all permissions, raises ValueError if missing any.
    """
    channel = guild.get_channel(int(channel_id))
    if not channel:
        raise ValueError("Channel not found")

    bot_member = guild.get_member(guild.me.id)
    permissions = channel.permissions_for(bot_member)

    missing_perms = []
    for perm in required_permissions:
        if not getattr(permissions, perm, False):
            missing_perms.append(perm)

    if missing_perms:
        raise ValueError(f"Missing permissions in channel: {', '.join(missing_perms)}")

    return True

# === CURRENCY SYSTEM HELPERS ===

def ensure_user_exists(guild_id, user_id):
    """Create user entry if doesn't exist, return user data"""
    from core import data_manager
    currency_data = data_manager.load_guild_data(guild_id, 'currency')

    if str(user_id) not in currency_data.get('users', {}):
        currency_data.setdefault('users', {})[str(user_id)] = {
            'balance': 0,
            'total_earned': 0,
            'total_spent': 0,
            'created_at': datetime.now().isoformat(),
            'is_active': True
        }
        data_manager.save_guild_data(guild_id, 'currency', currency_data)

    return currency_data['users'][str(user_id)]

def get_balance(guild_id, user_id):
    """Safely get balance, return 0 if user not found"""
    from core import data_manager
    currency_data = data_manager.load_guild_data(guild_id, 'currency')
    user_data = currency_data.get('users', {}).get(str(user_id), {})
    return user_data.get('balance', 0)

def check_sufficient_balance(guild_id, user_id, required_amount):
    """Return bool if user can afford amount"""
    balance = get_balance(guild_id, user_id)
    return balance >= required_amount

# === TASK SYSTEM HELPERS ===

def validate_task_active(task):
    """Check if task status is 'active' and not expired"""
    from datetime import datetime
    if task.get('status') != 'active':
        return False

    expires_at = task.get('expires_at')
    if expires_at:
        try:
            expiry = datetime.fromisoformat(expires_at)
            if datetime.now() > expiry:
                return False
        except (ValueError, TypeError):
            pass  # Invalid date format, assume active

    return True

def check_user_can_claim(guild_id, user_id, task_id):
    """Verify user eligible to claim task"""
    from core import data_manager
    tasks_data = data_manager.load_guild_data(guild_id, 'tasks')

    task = tasks_data.get('tasks', {}).get(str(task_id))
    if not task:
        raise ValueError("Task not found")

    if not validate_task_active(task):
        raise ValueError("Task is not active")

    # Check max claims
    if task.get('max_claims', -1) != -1:
        if task.get('current_claims', 0) >= task['max_claims']:
            raise ValueError("Task has reached maximum claims")

    # Check if user already claimed
    user_tasks = tasks_data.get('user_tasks', {}).get(str(user_id), {})
    if str(task_id) in user_tasks:
        status = user_tasks[str(task_id)].get('status', 'unknown')
        raise ValueError(f"You have already claimed this task (Status: {status})")

    # Check user task limit
    settings = tasks_data.get('settings', {})
    max_per_user = settings.get('max_tasks_per_user', 10)
    active_count = sum(
        1 for t in user_tasks.values()
        if t.get('status') in ['claimed', 'in_progress', 'submitted']
    )
    if active_count >= max_per_user:
        raise ValueError(f"You have reached the maximum of {max_per_user} active tasks")

    return True

def calculate_task_deadline(claimed_at, duration_hours):
    """Return deadline datetime"""
    from datetime import datetime, timedelta
    if isinstance(claimed_at, str):
        claimed_at = datetime.fromisoformat(claimed_at)
    return claimed_at + timedelta(hours=duration_hours)

def check_max_claims_reached(task):
    """Return bool if task at capacity"""
    max_claims = task.get('max_claims', -1)
    if max_claims == -1:  # Unlimited
        return False
    current_claims = task.get('current_claims', 0)
    return current_claims >= max_claims

# === SHOP SYSTEM HELPERS ===

def validate_item_active(item):
    """Check item exists and is_active = true"""
    return item.get('is_active', True)

def check_stock_available(item, quantity):
    """Verify sufficient stock for purchase"""
    stock = item.get('stock', -1)
    if stock == -1:  # Unlimited
        return True
    return stock >= quantity

def calculate_total_cost(item, quantity):
    """Return price × quantity"""
    return item.get('price', 0) * quantity

def update_item_stock(guild_id, item_id, quantity_change):
    """Atomic stock update"""
    from core import data_manager
    currency_data = data_manager.load_guild_data(guild_id, 'currency')
    shop_items = currency_data.get('shop_items', {})

    if item_id not in shop_items:
        raise ValueError("Item not found")

    item = shop_items[item_id]
    current_stock = item.get('stock', -1)

    if current_stock != -1:  # Only update if not unlimited
        new_stock = current_stock + quantity_change
        if new_stock < 0:
            raise ValueError("Insufficient stock")

        item['stock'] = new_stock
        data_manager.save_guild_data(guild_id, 'currency', currency_data)

    return item

def add_to_inventory(guild_id, user_id, item_id, quantity):
    """Add items to user inventory"""
    from core import data_manager
    currency_data = data_manager.load_guild_data(guild_id, 'currency')
    inventory = currency_data.get('inventory', {}).setdefault(str(user_id), {})

    current_quantity = inventory.get(item_id, 0)
    inventory[item_id] = current_quantity + quantity

    data_manager.save_guild_data(guild_id, 'currency', currency_data)
    return inventory

def remove_from_inventory(guild_id, user_id, item_id, quantity):
    """Remove items from inventory, return success bool"""
    from core import data_manager
    currency_data = data_manager.load_guild_data(guild_id, 'currency')
    inventory = currency_data.get('inventory', {}).get(str(user_id), {})

    current_quantity = inventory.get(item_id, 0)
    if current_quantity < quantity:
        return False

    if current_quantity == quantity:
        del inventory[item_id]
    else:
        inventory[item_id] = current_quantity - quantity

    data_manager.save_guild_data(guild_id, 'currency', currency_data)
    return True

def get_user_inventory(guild_id, user_id):
    """Return user's full inventory dict"""
    from core import data_manager
    currency_data = data_manager.load_guild_data(guild_id, 'currency')
    return currency_data.get('inventory', {}).get(str(user_id), {})

def check_inventory_has_item(guild_id, user_id, item_id, quantity):
    """Verify user owns items"""
    inventory = get_user_inventory(guild_id, user_id)
    return inventory.get(item_id, 0) >= quantity

# === ANNOUNCEMENT SYSTEM HELPERS ===

def build_announcement_embed(announcement_data):
    """Convert data dict to discord.Embed object"""
    import discord
    embed = discord.Embed(
        title=announcement_data.get('title', 'Announcement'),
        description=announcement_data.get('content', ''),
        color=int(announcement_data.get('embed_color', '#5865F2').lstrip('#'), 16)
    )

    if announcement_data.get('thumbnail'):
        embed.set_thumbnail(url=announcement_data['thumbnail'])

    embed.set_footer(text=announcement_data.get('author_name', 'System'))
    embed.timestamp = datetime.now()

    return embed

async def post_announcement(guild, channel_id, embed_data):
    """Post embed to Discord, return message_id"""
    import discord
    channel = guild.get_channel(int(channel_id))
    if not channel:
        raise ValueError("Channel not found")

    embed = build_announcement_embed(embed_data)
    message = await channel.send(embed=embed)
    return str(message.id)

async def edit_announcement(guild, channel_id, message_id, new_embed):
    """Update existing announcement"""
    channel = guild.get_channel(int(channel_id))
    if not channel:
        raise ValueError("Channel not found")

    message = await channel.fetch_message(int(message_id))
    await message.edit(embed=new_embed)

async def delete_announcement(guild, channel_id, message_id):
    """Remove announcement message"""
    channel = guild.get_channel(int(channel_id))
    if not channel:
        return

    try:
        message = await channel.fetch_message(int(message_id))
        await message.delete()
    except discord.NotFound:
        pass  # Already deleted

async def pin_message(guild, channel_id, message_id):
    """Pin announcement in channel"""
    channel = guild.get_channel(int(channel_id))
    if not channel:
        raise ValueError("Channel not found")

    message = await channel.fetch_message(int(message_id))
    await message.pin()

async def unpin_message(guild, channel_id, message_id):
    """Unpin announcement"""
    channel = guild.get_channel(int(channel_id))
    if not channel:
        return

    try:
        message = await channel.fetch_message(int(message_id))
        await message.unpin()
    except discord.NotFound:
        pass

# === EMBED SYSTEM HELPERS ===

def create_embed_from_data(embed_dict):
    """Convert data dict to discord.Embed object"""
    import discord
    embed = discord.Embed(
        title=embed_dict.get('title'),
        description=embed_dict.get('description'),
        color=int(embed_dict.get('color', '#7289da').lstrip('#'), 16)
    )

    # Add fields
    for field in embed_dict.get('fields', []):
        embed.add_field(
            name=field.get('name', ''),
            value=field.get('value', ''),
            inline=field.get('inline', False)
        )

    # Set footer
    if embed_dict.get('footer_text'):
        embed.set_footer(
            text=embed_dict['footer_text'],
            icon_url=embed_dict.get('footer_icon_url')
        )

    # Set author
    if embed_dict.get('author_name'):
        embed.set_author(
            name=embed_dict['author_name'],
            icon_url=embed_dict.get('author_icon_url')
        )

    # Set images
    if embed_dict.get('thumbnail_url'):
        embed.set_thumbnail(url=embed_dict['thumbnail_url'])
    if embed_dict.get('image_url'):
        embed.set_image(url=embed_dict['image_url'])

    return embed

def validate_embed_data(embed_dict):
    """Check all fields valid (title length, field count, etc)"""
    # Title length check
    title = embed_dict.get('title', '')
    if len(title) > 256:
        raise ValueError("Embed title too long (max 256 characters)")

    # Description length check
    description = embed_dict.get('description', '')
    if len(description) > 4096:
        raise ValueError("Embed description too long (max 4096 characters)")

    # Field count check
    fields = embed_dict.get('fields', [])
    if len(fields) > 25:
        raise ValueError("Too many embed fields (max 25)")

    # Individual field validation
    for field in fields:
        name = field.get('name', '')
        value = field.get('value', '')
        if len(name) > 256:
            raise ValueError("Field name too long (max 256 characters)")
        if len(value) > 1024:
            raise ValueError("Field value too long (max 1024 characters)")

    # Footer length check
    footer_text = embed_dict.get('footer_text', '')
    if len(footer_text) > 2048:
        raise ValueError("Footer text too long (max 2048 characters)")

    return True

async def post_embed_to_channel(guild, channel_id, embed_data):
    """Send embed, return message_id"""
    import discord
    channel = guild.get_channel(int(channel_id))
    if not channel:
        raise ValueError("Channel not found")

    embed = create_embed_from_data(embed_data)
    message = await channel.send(embed=embed)
    return str(message.id)

async def edit_embed_message(guild, channel_id, message_id, new_embed_data):
    """Update embed message"""
    channel = guild.get_channel(int(channel_id))
    if not channel:
        raise ValueError("Channel not found")

    message = await channel.fetch_message(int(message_id))
    new_embed = create_embed_from_data(new_embed_data)
    await message.edit(embed=new_embed)

# === DATA MANAGER HELPERS ===

def atomic_write(file_path, data):
    """Write with temp file + atomic rename"""
    import json
    import tempfile
    import os

    # Create temp file
    temp_fd, temp_path = tempfile.mkstemp(dir=os.path.dirname(file_path))
    try:
        with os.fdopen(temp_fd, 'w') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        # Atomic rename
        os.replace(temp_path, file_path)
    except Exception:
        # Clean up temp file on error
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        raise

def create_backup(file_path):
    """Copy file to .backup before modifications"""
    import shutil
    backup_path = file_path.with_suffix('.backup.json')
    try:
        shutil.copy2(file_path, backup_path)
        return backup_path
    except OSError:
        return None

def restore_from_backup(file_path):
    """Restore file from .backup on corruption"""
    import shutil
    backup_path = file_path.with_suffix('.backup.json')
    if backup_path.exists():
        shutil.copy(backup_path, file_path)
        return True
    return False

def validate_json_structure(data, schema):
    """Verify data matches expected schema"""
    # Basic validation - can be extended with jsonschema
    if not isinstance(data, dict):
        raise ValueError("Data must be a dictionary")
    return True

# === PERMISSION SYSTEM HELPERS ===

def is_server_owner(guild, user_id):
    """Check if user is guild owner"""
    return guild.owner_id == user_id

def is_admin(guild, user_id, config):
    """Check if user has admin role or is owner"""
    if is_server_owner(guild, user_id):
        return True

    admin_roles = config.get('admin_roles', [])
    user_roles = [role.id for role in guild.get_member(user_id).roles]
    return any(role_id in admin_roles for role_id in user_roles)

def is_moderator(guild, user_id, config):
    """Check if user has moderator role"""
    # Admins are also moderators
    if is_admin(guild, user_id, config):
        return True

    mod_roles = config.get('moderator_roles', [])
    user_roles = [role.id for role in guild.get_member(user_id).roles]
    return any(role_id in mod_roles for role_id in user_roles)

def has_manage_messages(guild, user_id, channel_id):
    """Check if user can manage messages in channel"""
    channel = guild.get_channel(int(channel_id))
    if not channel:
        return False

    member = guild.get_member(user_id)
    if not member:
        return False

    return channel.permissions_for(member).manage_messages

def has_manage_roles(guild, user_id):
    """Check if user can grant roles"""
    member = guild.get_member(user_id)
    if not member:
        return False

    return member.guild_permissions.manage_roles
