from datetime import datetime
import discord
from core.data_manager import DataManager
import re

class Validator:
    """Input validation utilities"""

    @staticmethod
    def validate_positive_integer(value, field_name, max_value=None):
        """Validate positive integer"""
        if not isinstance(value, int):
            raise ValueError(f"{field_name} must be an integer")
        if value <= 0:
            raise ValueError(f"{field_name} must be positive")
        if max_value and value > max_value:
            raise ValueError(f"{field_name} cannot exceed {max_value}")
        return value

    @staticmethod
    def validate_non_negative_integer(value, field_name):
        """Validate non-negative integer"""
        if not isinstance(value, int):
            raise ValueError(f"{field_name} must be an integer")
        if value < 0:
            raise ValueError(f"{field_name} cannot be negative")
        return value

    @staticmethod
    def validate_string(value, field_name, min_length=1, max_length=None):
        """Validate string length"""
        if not isinstance(value, str):
            raise ValueError(f"{field_name} must be a string")
        if len(value) < min_length:
            raise ValueError(f"{field_name} must be at least {min_length} characters")
        if max_length and len(value) > max_length:
            raise ValueError(f"{field_name} cannot exceed {max_length} characters")
        return value.strip()

    @staticmethod
    def validate_discord_id(value, field_name):
        """Validate Discord ID format"""
        if not isinstance(value, str):
            value = str(value)
        if not value.isdigit() or len(value) < 17 or len(value) > 19:
            raise ValueError(f"{field_name} is not a valid Discord ID")
        return value

    @staticmethod
    def validate_enum(value, field_name, allowed_values):
        """Validate value is in allowed set"""
        if value not in allowed_values:
            raise ValueError(
                f"{field_name} must be one of: {', '.join(allowed_values)}"
            )
        return value

    @staticmethod
    def sanitize_sql_input(value):
        """Basic SQL injection prevention"""
        if isinstance(value, str):
            # Remove potentially dangerous characters
            dangerous_chars = ["'", '"', ";", "--", "/*", "*/", "xp_", "sp_"]
            for char in dangerous_chars:
                if char in value:
                    raise ValueError("Input contains invalid characters")
        return value

class DataValidator:
    """Validates data integrity across bot and CMS"""

    def __init__(self, bot, data_manager: DataManager):
        self.bot = bot
        self.data_manager = data_manager

    async def validate_guild(self, guild_id: int) -> dict:
        """Run complete validation check and return report"""
        report = {
            "guild_id": guild_id,
            "timestamp": datetime.now().isoformat(),
            "errors": [],
            "warnings": [],
            "fixed": []
        }

        guild = self.bot.get_guild(guild_id)
        if not guild:
            report["errors"].append("Guild not found")
            return report

        # Validate tasks
        await self._validate_tasks(guild, report)

        # Validate shop
        await self._validate_shop(guild, report)

        # Validate user data
        await self._validate_users(guild, report)

        return report

    async def _validate_tasks(self, guild, report):
        """Validate task data and Discord messages match"""
        tasks_data = self.data_manager.load_guild_data(guild.id, "tasks")
        config = self.data_manager.load_guild_data(guild.id, "config")

        task_channel_id = config.get("task_channel_id")

        if not task_channel_id:
            report["warnings"].append("No task channel configured")
            return

        task_channel = guild.get_channel(int(task_channel_id))
        if not task_channel:
            report["errors"].append(f"Task channel {task_channel_id} not found")
            return

        tasks = tasks_data.get("tasks", {})

        for task_id, task_data in tasks.items():
            message_id = task_data.get("message_id")

            if not message_id:
                report["warnings"].append(f"Task {task_id} has no Discord message")
                continue

            # Verify message exists
            try:
                await task_channel.fetch_message(int(message_id))
            except discord.NotFound:
                report["errors"].append(f"Task {task_id} message {message_id} not found")
            except discord.Forbidden:
                report["errors"].append(f"Cannot access task channel messages")
                break

    async def _validate_shop(self, guild, report):
        """Validate shop data matches Discord"""
        currency_data = self.data_manager.load_guild_data(guild.id, "currency")
        config = self.data_manager.load_guild_data(guild.id, "config")

        shop_items = currency_data.get("shop_items", {})

        for item_id, item_data in shop_items.items():
            if not item_data.get("is_active", True):
                continue

            if not item_data.get("message_id"):
                report["warnings"].append(f"Shop item {item_id} has no Discord message")

    async def _validate_users(self, guild, report):
        """Validate user data integrity"""
        currency_data = self.data_manager.load_guild_data(guild.id, "currency")
        users = currency_data.get("users", {})
        inventory = currency_data.get("inventory", {})

        # Check for negative balances
        for user_id, user_data in users.items():
            balance = user_data.get("balance", 0)
            if balance < 0:
                report["errors"].append(f"User {user_id} has negative balance: {balance}")

        # Check for inventory without user data
        for user_id in inventory.keys():
            if user_id not in users:
                report["warnings"].append(f"User {user_id} has inventory but no currency data")

        # Validate total_earned >= total_spent
        for user_id, user_data in users.items():
            earned = user_data.get("total_earned", 0)
            spent = user_data.get("total_spent", 0)
            balance = user_data.get("balance", 0)

            # Balance should equal earned - spent (approximately, accounting for gifts)
            # This is a soft check
            if abs(balance - (earned - spent)) > earned + spent:  # Large discrepancy
                report["warnings"].append(
                    f"User {user_id} has inconsistent totals: "
                    f"balance={balance}, earned={earned}, spent={spent}"
                )
