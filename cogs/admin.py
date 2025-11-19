"""
Admin commands for server-specific configuration
"""

import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timedelta
import asyncio
from core.permissions import admin_only, admin_only_interaction, feature_enabled, is_moderator, is_moderator_interaction
from core.utils import create_embed, add_embed_footer
from core.validator import DataValidator, Validator
from core.initializer import GuildInitializer
from core.shop_manager import ShopManager

class Admin(commands.Cog):
    """Server administration commands"""

    def __init__(self, bot):
        self.bot = bot
        # Initialize shop_manager lazily to avoid dependency issues during cog loading
        self._shop_manager = None

    @property
    def shop_manager(self):
        if self._shop_manager is None:
            currency_cog = self.bot.get_cog('Currency')
            if currency_cog:
                self._shop_manager = ShopManager(self.bot.data_manager, currency_cog.transaction_manager)
            else:
                # Fallback if Currency cog not available
                self._shop_manager = None
        return self._shop_manager

    def _get_item_emoji(self, item: dict) -> str:
        """Get emoji from item, handling missing emoji field gracefully"""
        emoji = item.get('emoji')
        if emoji:
            return emoji

        # Try to extract emoji from name
        name = item.get('name', '')
        if name and any(ord(c) > 127 for c in name[:5]):  # Check for unicode emoji
            extracted = ''.join(c for c in name[:5] if ord(c) > 127)
            if extracted:
                return extracted

        return '🛍️'  # Default shopping bag emoji

    @app_commands.command(name="setprefix", description="Change the bot prefix for this server")
    @app_commands.guild_only()
    @admin_only_interaction()
    async def set_prefix(self, interaction: discord.Interaction, new_prefix: str):
        """Change bot prefix for THIS server"""
        if len(new_prefix) > 5:
            await interaction.response.send_message("❌ Prefix too long! Maximum 5 characters.", ephemeral=True)
            return

        guild_id = interaction.guild.id
        config = self.bot.data_manager.load_guild_data(guild_id, "config")

        old_prefix = config.get("prefix", "!")
        config["prefix"] = new_prefix

        self.bot.data_manager.save_guild_data(guild_id, "config", config)

        embed = create_embed(
            title="✅ Prefix Changed",
            description=f"Changed from `{old_prefix}` to `{new_prefix}`",
            color=0x2ecc71
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @commands.command(name="setcurrency")
    @commands.guild_only()
    @admin_only()
    async def set_currency(self, ctx, symbol: str = None, name: str = None):
        """Customize currency for THIS server"""
        if not symbol and not name:
            await ctx.send("❌ Please provide either a symbol or name (or both)!")
            return

        if symbol and len(symbol) > 10:
            await ctx.send("❌ Currency symbol too long! Maximum 10 characters.")
            return

        if name and len(name) > 20:
            await ctx.send("❌ Currency name too long! Maximum 20 characters.")
            return

        guild_id = ctx.guild.id
        config = self.bot.data_manager.load_guild_data(guild_id, "config")

        changes = []
        if symbol:
            old_symbol = config.get("currency_symbol", "$")
            config["currency_symbol"] = symbol
            changes.append(f"Symbol: `{old_symbol}` → `{symbol}`")

        if name:
            old_name = config.get("currency_name", "coins")
            config["currency_name"] = name
            changes.append(f"Name: `{old_name}` → `{name}`")

        self.bot.data_manager.save_guild_data(guild_id, "config", config)

        embed = create_embed(
            title="✅ Currency Updated",
            description="\n".join(changes),
            color=0x2ecc71
        )
        add_embed_footer(embed, ctx)
        await ctx.send(embed=embed)

    @commands.command(name="serverconfig")
    @commands.guild_only()
    @admin_only()
    async def server_config(self, ctx):
        """View current server configuration"""
        guild_id = ctx.guild.id
        config = self.bot.data_manager.load_guild_data(guild_id, "config")

        embed = create_embed(
            title=f"⚙️ {ctx.guild.name} Configuration",
            color=0x3498db
        )

        embed.add_field(name="Prefix", value=f"`{config.get('prefix', '!')}`", inline=True)
        embed.add_field(
            name="Currency",
            value=f"{config.get('currency_symbol', '$')} ({config.get('currency_name', 'coins')})",
            inline=True
        )

        features = config.get("features", {})
        feature_list = "\n".join([
            f"{'✅' if v else '❌'} {k.title()}"
            for k, v in features.items()
        ])
        embed.add_field(name="Features", value=feature_list or "None", inline=False)

        # Role configurations
        admin_roles = config.get("admin_roles", [])
        mod_roles = config.get("moderator_roles", [])

        if admin_roles:
            admin_role_names = []
            for role_id in admin_roles:
                role = ctx.guild.get_role(role_id)
                admin_role_names.append(role.name if role else f"Unknown ({role_id})")
            embed.add_field(name="Admin Roles", value=", ".join(admin_role_names), inline=False)

        if mod_roles:
            mod_role_names = []
            for role_id in mod_roles:
                role = ctx.guild.get_role(role_id)
                mod_role_names.append(role.name if role else f"Unknown ({role_id})")
            embed.add_field(name="Moderator Roles", value=", ".join(mod_role_names), inline=False)

        add_embed_footer(embed, ctx)
        await ctx.send(embed=embed)

    @commands.command(name="togglefeature")
    @commands.guild_only()
    @admin_only()
    async def toggle_feature(self, ctx, feature: str):
        """Enable/disable features for THIS server"""
        valid_features = ["currency", "tasks", "moderation"]
        if feature.lower() not in valid_features:
            await ctx.send(f"❌ Invalid feature. Valid: {', '.join(valid_features)}")
            return

        guild_id = ctx.guild.id
        config = self.bot.data_manager.load_guild_data(guild_id, "config")

        features = config.get("features", {})
        current = features.get(feature.lower(), True)
        features[feature.lower()] = not current
        config["features"] = features

        self.bot.data_manager.save_guild_data(guild_id, "config", config)

        status = "enabled" if not current else "disabled"
        embed = create_embed(
            title="✅ Feature Toggled",
            description=f"**{feature.title()}** {status} for this server",
            color=0x2ecc71 if not current else 0xe74c3c
        )
        add_embed_footer(embed, ctx)
        await ctx.send(embed=embed)

    @commands.command(name="addadminrole")
    @commands.guild_only()
    @admin_only()
    async def add_admin_role(self, ctx, role: discord.Role):
        """Add a role to the admin roles list"""
        guild_id = ctx.guild.id
        config = self.bot.data_manager.load_guild_data(guild_id, "config")

        admin_roles = config.get("admin_roles", [])
        if role.id in admin_roles:
            await ctx.send(f"❌ Role {role.name} is already an admin role!")
            return

        admin_roles.append(role.id)
        config["admin_roles"] = admin_roles
        self.bot.data_manager.save_guild_data(guild_id, "config", config)

        embed = create_embed(
            title="✅ Admin Role Added",
            description=f"Role **{role.name}** added to admin roles",
            color=0x2ecc71
        )
        add_embed_footer(embed, ctx)
        await ctx.send(embed=embed)

    @commands.command(name="addmodrole")
    @commands.guild_only()
    @admin_only()
    async def add_mod_role(self, ctx, role: discord.Role):
        """Add a role to the moderator roles list"""
        guild_id = ctx.guild.id
        config = self.bot.data_manager.load_guild_data(guild_id, "config")

        admin_roles = config.get("admin_roles", [])
        if role.id in admin_roles:
            await ctx.send(f"❌ Role {role.name} is already an admin role!")
            return

        admin_roles.append(role.id)
        config["admin_roles"] = admin_roles
        self.bot.data_manager.save_guild_data(guild_id, "config", config)

        embed = create_embed(
            title="✅ Moderator Role Added",
            description=f"Role **{role.name}** added to moderator roles",
            color=0x2ecc71
        )
        add_embed_footer(embed, ctx)
        await ctx.send(embed=embed)

    @commands.command(name="removeadminrole")
    @commands.guild_only()
    @admin_only()
    async def remove_admin_role(self, ctx, role: discord.Role):
        """Remove a role from the admin roles list"""
        guild_id = ctx.guild.id
        config = self.bot.data_manager.load_guild_data(guild_id, "config")

        mod_roles = config.get("moderator_roles", [])
        if role.id in mod_roles:
            await ctx.send(f"❌ Role {role.name} is already a moderator role!")
            return

        mod_roles.append(role.id)
        config["moderator_roles"] = mod_roles
        self.bot.data_manager.save_guild_data(guild_id, "config", config)

        embed = create_embed(
            title="✅ Admin Role Removed",
            description=f"Role **{role.name}** removed from admin roles",
            color=0xe74c3c
        )
        add_embed_footer(embed, ctx)
        await ctx.send(embed=embed)

    @commands.command(name="removemodrole")
    @commands.guild_only()
    @admin_only()
    async def remove_mod_role(self, ctx, role: discord.Role):
        """Remove a role from the moderator roles list"""
        guild_id = ctx.guild.id
        config = self.bot.data_manager.load_guild_data(guild_id, "config")

        mod_roles = config.get("moderator_roles", [])
        if role.id not in mod_roles:
            await ctx.send(f"❌ Role {role.name} is not a moderator role!")
            return

        mod_roles.remove(role.id)
        config["moderator_roles"] = mod_roles
        self.bot.data_manager.save_guild_data(guild_id, "config", config)

        embed = create_embed(
            title="✅ Moderator Role Removed",
            description=f"Role **{role.name}** removed from moderator roles",
            color=0xe74c3c
        )
        add_embed_footer(embed, ctx)
        await ctx.send(embed=embed)

    @commands.command(name="backup")
    @commands.guild_only()
    @admin_only()
    async def create_backup(self, ctx):
        """Create a backup of this server's data"""
        guild_id = ctx.guild.id

        try:
            self.bot.data_manager.create_backup(guild_id)

            embed = create_embed(
                title="✅ Backup Created",
                description="Server data has been backed up successfully",
                color=0x2ecc71
            )
            add_embed_footer(embed, ctx)
            await ctx.send(embed=embed)
        except Exception as e:
            await ctx.send(f"❌ Failed to create backup: {str(e)}")

    @commands.command(name='addbalance')
    @commands.guild_only()
    @admin_only()
    async def add_balance(self, ctx, user: discord.Member, amount: int, *, reason: str = "Admin grant"):
        """Add currency to a user's balance"""
        if amount <= 0:
            await ctx.send("Amount must be positive!")
            return

        guild_id = ctx.guild.id

        # Use currency cog's method
        currency_cog = self.bot.get_cog('Currency')
        if not currency_cog:
            await ctx.send("Currency system not available!")
            return

        currency_cog._add_balance(guild_id, user.id, amount, f"{reason} (by {ctx.author.name})")

        config = self.bot.data_manager.load_guild_data(guild_id, "config")
        symbol = config.get('currency_symbol', '$')

        new_balance = currency_cog._get_balance(guild_id, user.id)

        embed = discord.Embed(
            title="Balance Added",
            description=f"Added {symbol}{amount} to {user.mention}",
            color=discord.Color.green()
        )
        embed.add_field(name="Reason", value=reason)
        embed.add_field(name="New Balance", value=f"{symbol}{new_balance}")

        await ctx.send(embed=embed)

    @commands.command(name='removebalance')
    @commands.guild_only()
    @admin_only()
    async def remove_balance(self, ctx, user: discord.Member, amount: int, *, reason: str = "Admin deduction"):
        """Remove currency from a user's balance"""
        if amount <= 0:
            await ctx.send("Amount must be positive!")
            return

        guild_id = ctx.guild.id

        currency_cog = self.bot.get_cog('Currency')
        if not currency_cog:
            await ctx.send("Currency system not available!")
            return

        current_balance = currency_cog._get_balance(guild_id, user.id)

        if current_balance < amount:
            await ctx.send(f"User only has {current_balance}! Cannot remove {amount}.")
            return

        currency_cog._add_balance(guild_id, user.id, -amount, f"{reason} (by {ctx.author.name})")

        config = self.bot.data_manager.load_guild_data(guild_id, "config")
        symbol = config.get('currency_symbol', '$')

        new_balance = currency_cog._get_balance(guild_id, user.id)

        embed = discord.Embed(
            title="Balance Removed",
            description=f"Removed {symbol}{amount} from {user.mention}",
            color=discord.Color.red()
        )
        embed.add_field(name="Reason", value=reason)
        embed.add_field(name="New Balance", value=f"{symbol}{new_balance}")

        await ctx.send(embed=embed)

    @commands.command(name='setbalance')
    @commands.guild_only()
    @admin_only()
    async def set_balance(self, ctx, user: discord.Member, amount: int, *, reason: str = "Admin adjustment"):
        """Set a user's balance to a specific amount"""
        if amount < 0:
            await ctx.send("Amount cannot be negative!")
            return

        guild_id = ctx.guild.id

        currency_cog = self.bot.get_cog('Currency')
        if not currency_cog:
            await ctx.send("Currency system not available!")
            return

        current_balance = currency_cog._get_balance(guild_id, user.id)
        difference = amount - current_balance

        currency_cog._add_balance(guild_id, user.id, difference, f"{reason} (by {ctx.author.name})")

        config = self.bot.data_manager.load_guild_data(guild_id, "config")
        symbol = config.get('currency_symbol', '$')

        embed = discord.Embed(
            title="Balance Set",
            description=f"Set {user.mention}'s balance to {symbol}{amount}",
            color=discord.Color.blue()
        )
        embed.add_field(name="Previous Balance", value=f"{symbol}{current_balance}")
        embed.add_field(name="Reason", value=reason)

        await ctx.send(embed=embed)

    @commands.command(name='reseteconomy')
    @commands.guild_only()
    @admin_only()
    async def reset_economy(self, ctx):
        """Reset the entire server economy (requires confirmation)"""

        # Confirmation message
        confirmation_msg = await ctx.send(
            "⚠️ **WARNING**: This will reset ALL currency data for this server!\n"
            "All user balances, inventories, shop items, and transactions will be deleted.\n\n"
            "Type CONFIRM RESET within 30 seconds to proceed."
        )

        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel and m.content == "CONFIRM RESET"

        try:
            await self.bot.wait_for('message', check=check, timeout=30.0)
        except asyncio.TimeoutError:
            await ctx.send("Economy reset cancelled - confirmation not received.")
            return

        guild_id = ctx.guild.id

        # Create backup before reset
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_data = {
            'currency': self.bot.data_manager.load_guild_data(guild_id, "currency"),
            'transactions': self.bot.data_manager.load_guild_data(guild_id, "transactions"),
            'backup_time': timestamp,
            'backup_by': str(ctx.author.id)
        }

        # Save backup
        self.bot.data_manager.save_guild_data(guild_id, f"backup_economy_{timestamp}", backup_data)

        # Reset currency data
        fresh_currency_data = {
            'users': {},
            'inventory': {},
            'shop_items': {},
            'metadata': {
                'version': '2.0',
                'total_currency': 0,
                'reset_at': datetime.now().isoformat(),
                'reset_by': str(ctx.author.id)
            }
        }

        self.bot.data_manager.save_guild_data(guild_id, "currency", fresh_currency_data)
        self.bot.data_manager.save_guild_data(guild_id, "transactions", [])

        embed = discord.Embed(
            title="✅ Economy Reset Complete",
            description="All economy data has been reset.",
            color=discord.Color.green()
        )
        embed.add_field(name="Backup Created", value=f"backup_economy_{timestamp}")
        embed.set_footer(text="Users will start fresh with 0 balance.")

        await ctx.send(embed=embed)

    @commands.command(name='economystats')
    @commands.guild_only()
    @admin_only()
    async def economy_stats(self, ctx):
        """View server economy statistics"""
        guild_id = ctx.guild.id
        currency_data = self.bot.data_manager.load_guild_data(guild_id, "currency")
        if not currency_data:
            await ctx.send("No economy data available!")
            return

        users = currency_data.get('users', {})
        shop_items = currency_data.get('shop_items', {})
        transactions = self.bot.data_manager.load_guild_data(guild_id, "transactions") or []

        # Calculate stats
        total_users = len(users)
        total_currency = sum(u.get('balance', 0) for u in users.values())
        total_earned = sum(u.get('total_earned', 0) for u in users.values())
        total_spent = sum(u.get('total_spent', 0) for u in users.values())

        # Get richest users
        sorted_users = sorted(users.items(), key=lambda x: x[1].get('balance', 0), reverse=True)
        top_3 = sorted_users[:3]

        # Get transaction count
        total_transactions = len(transactions)
        recent_transactions = len([t for t in transactions
                                   if datetime.fromisoformat(t.get('timestamp', '2000-01-01'))
                                   > datetime.now() - timedelta(days=7)])

        config = self.bot.data_manager.load_guild_data(guild_id, "config")
        symbol = config.get('currency_symbol', '$')
        currency_name = config.get('currency_name', 'currency')

        embed = discord.Embed(
            title=f"📊 {ctx.guild.name} Economy Statistics",
            color=discord.Color.gold()
        )

        embed.add_field(name="Total Users", value=total_users, inline=True)
        embed.add_field(name="Total Currency", value=f"{symbol}{total_currency}", inline=True)
        embed.add_field(name="Shop Items", value=len(shop_items), inline=True)

        embed.add_field(name="Total Earned", value=f"{symbol}{total_earned}", inline=True)
        embed.add_field(name="Total Spent", value=f"{symbol}{total_spent}", inline=True)
        embed.add_field(name="Transactions", value=total_transactions, inline=True)

        embed.add_field(name="Transactions (7d)", value=recent_transactions, inline=True)
        embed.add_field(name="Avg Balance", value=f"{symbol}{total_currency // total_users if total_users > 0 else 0}", inline=True)
        embed.add_field(name="Currency Name", value=currency_name, inline=True)

        # Top 3 richest
        if top_3:
            richest_text = "\n".join([
                f"{i+1}. <@{uid}>: {symbol}{data.get('balance', 0)}"
                for i, (uid, data) in enumerate(top_3)
            ])
            embed.add_field(name="💰 Richest Users", value=richest_text, inline=False)

        await ctx.send(embed=embed)

    @app_commands.command(name="validate", description="Run data integrity check")
    @app_commands.guild_only()
    @admin_only_interaction()
    async def validate_data(self, interaction: discord.Interaction):
        """Admin command to validate guild data"""
        await interaction.response.defer(ephemeral=True)

        validator = DataValidator(self.bot, self.bot.data_manager)
        report = await validator.validate_guild(interaction.guild.id)

        # Create embed with report
        embed = discord.Embed(
            title="🔍 Data Validation Report",
            color=discord.Color.blue(),
            timestamp=datetime.now()
        )

        if report["errors"]:
            embed.add_field(
                name=f"❌ Errors ({len(report['errors'])})",
                value="\n".join(report["errors"][:10]) or "None",
                inline=False
            )

        if report["warnings"]:
            embed.add_field(
                name=f"⚠️ Warnings ({len(report['warnings'])})",
                value="\n".join(report["warnings"][:10]) or "None",
                inline=False
            )

        if not report["errors"] and not report["warnings"]:
            embed.description = "✅ All data validated successfully!"
            embed.color = discord.Color.green()

        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="reinitialize", description="Force re-sync all Discord elements")
    @app_commands.guild_only()
    @admin_only_interaction()
    async def reinitialize_guild(self, interaction: discord.Interaction):
        """Force complete re-initialization of guild"""
        await interaction.response.defer(ephemeral=True)

        initializer = GuildInitializer(self.bot.data_manager, self.bot)

        try:
            await initializer.initialize_guild(interaction.guild)
            await interaction.followup.send(
                "✅ Guild re-initialized successfully! All data synced.",
                ephemeral=True
            )
        except Exception as e:
            await interaction.followup.send(
                f"❌ Re-initialization failed: {str(e)}",
                ephemeral=True
            )

    # === SHOP MANAGEMENT COMMANDS ===

    @app_commands.command(name="additem", description="Add new shop item")
    @app_commands.describe(
        item_id="Unique identifier for the item",
        name="Display name of the item",
        price="Price in currency",
        description="Item description",
        category="Item category (general, consumable, role, collectible)",
        stock="Stock quantity (-1 for unlimited)",
        emoji="Emoji to display with item"
    )
    @app_commands.guild_only()
    @admin_only_interaction()
    async def add_item(
        self,
        interaction: discord.Interaction,
        item_id: str,
        name: str,
        price: int,
        description: str = "No description",
        category: str = "general",
        stock: int = -1,
        emoji: str = "🛍️"
    ):
        """Add new shop item"""
        try:
            # VALIDATE ALL INPUTS
            item_id = Validator.validate_string(item_id, "Item ID", max_length=50)
            name = Validator.validate_string(name, "Name", max_length=100)
            price = Validator.validate_positive_integer(price, "Price", max_value=1000000)
            description = Validator.validate_string(description, "Description", max_length=500)
            category = Validator.validate_enum(category, "Category", ["general", "consumable", "role", "collectible"])
            stock = Validator.validate_non_negative_integer(stock, "Stock") if stock != -1 else stock
            emoji = Validator.validate_string(emoji, "Emoji", max_length=10)

            # Sanitize for SQL injection
            item_id = Validator.sanitize_sql_input(item_id)
            name = Validator.sanitize_sql_input(name)

            item = self.shop_manager.add_item(
                interaction.guild_id,
                item_id,
                name,
                description,
                price,
                category=category,
                stock=stock,
                emoji=emoji
            )

            # Sync Discord message
            await self.shop_manager.sync_discord_message(interaction.guild_id, item_id, self.bot)

            embed = discord.Embed(
                title="✅ Item Added",
                description=f"**{emoji} {name}** has been added to the shop",
                color=discord.Color.green()
            )
            embed.add_field(name="ID", value=f"`{item_id}`", inline=True)
            embed.add_field(name="Price", value=f"{price}💰", inline=True)
            embed.add_field(name="Stock", value="♾️ Unlimited" if stock == -1 else str(stock), inline=True)
            embed.add_field(name="Category", value=category.title(), inline=True)

            await interaction.response.send_message(embed=embed, ephemeral=True)

        except ValueError as e:
            await interaction.response.send_message(f"❌ {str(e)}", ephemeral=True)

    @app_commands.command(name="updateitem", description="Update existing shop item")
    @app_commands.describe(
        item_id="Item ID to update",
        name="New display name",
        price="New price",
        description="New description",
        stock="New stock quantity",
        active="Whether item is active"
    )
    @app_commands.guild_only()
    @admin_only_interaction()
    async def update_item(
        self,
        interaction: discord.Interaction,
        item_id: str,
        name: str = None,
        price: int = None,
        description: str = None,
        stock: int = None,
        active: bool = None
    ):
        """Update existing shop item"""
        updates = {}
        if name is not None:
            updates['name'] = name
        if price is not None:
            if price < 0:
                await interaction.response.send_message("❌ Price cannot be negative!", ephemeral=True)
                return
            updates['price'] = price
        if description is not None:
            updates['description'] = description
        if stock is not None:
            if stock < -1:
                await interaction.response.send_message("❌ Stock cannot be less than -1!", ephemeral=True)
                return
            updates['stock'] = stock
        if active is not None:
            updates['is_active'] = active

        if not updates:
            await interaction.response.send_message("❌ No updates specified!", ephemeral=True)
            return

        try:
            item = self.shop_manager.update_item(interaction.guild_id, item_id, updates)

            # Sync Discord message
            await self.shop_manager.sync_discord_message(interaction.guild_id, item_id, self.bot)

            embed = discord.Embed(
                title="✅ Item Updated",
                description=f"**{self._get_item_emoji(item)} {item['name']}** has been updated",
                color=discord.Color.blue()
            )

            changes = []
            for key, value in updates.items():
                if key == 'is_active':
                    changes.append(f"{key.title()}: {'Yes' if value else 'No'}")
                elif key == 'stock':
                    changes.append(f"{key.title()}: {'Unlimited' if value == -1 else value}")
                else:
                    changes.append(f"{key.title()}: {value}")

            embed.add_field(name="Changes", value="\n".join(changes), inline=False)

            await interaction.response.send_message(embed=embed, ephemeral=True)

        except ValueError as e:
            await interaction.response.send_message(f"❌ {str(e)}", ephemeral=True)

    @app_commands.command(name="deleteitem", description="Delete shop item")
    @app_commands.describe(
        item_id="Item ID to delete",
        archive="Whether to archive instead of permanent deletion"
    )
    @app_commands.guild_only()
    @admin_only_interaction()
    async def delete_item(
        self,
        interaction: discord.Interaction,
        item_id: str,
        archive: bool = True
    ):
        """Delete shop item"""
        # Get item info before deletion
        item = self.shop_manager.get_item(interaction.guild_id, item_id)
        if not item:
            await interaction.response.send_message("❌ Item not found!", ephemeral=True)
            return

        # Confirm deletion
        embed = discord.Embed(
            title="Confirm Deletion",
            description=f"Are you sure you want to {'archive' if archive else 'permanently delete'} **{self._get_item_emoji(item)} {item['name']}**?",
            color=discord.Color.red()
        )
        embed.add_field(name="Item ID", value=f"`{item_id}`", inline=True)
        embed.add_field(name="Price", value=f"{item['price']}💰", inline=True)
        embed.add_field(name="Stock", value="♾️ Unlimited" if item['stock'] == -1 else item['stock'], inline=True)

        view = DeleteConfirmView(self.shop_manager, interaction.guild_id, item_id, archive, item)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @app_commands.command(name="restock", description="Restock item or view stock levels")
    @app_commands.describe(
        item_id="Item ID to restock (leave empty to view all stock)",
        quantity="Quantity to add (leave empty to view current stock)",
        operation="How to modify stock"
    )
    @app_commands.choices(operation=[
        app_commands.Choice(name="Set to amount", value="set"),
        app_commands.Choice(name="Add to current", value="add"),
        app_commands.Choice(name="Subtract from current", value="subtract")
    ])
    @app_commands.guild_only()
    @admin_only_interaction()
    async def restock(
        self,
        interaction: discord.Interaction,
        item_id: str = None,
        quantity: int = None,
        operation: str = "set"
    ):
        """Restock item - PREVENT NEGATIVE STOCK"""
        if item_id is None:
            # Show all stock levels
            items = self.shop_manager.get_shop_items(interaction.guild_id, active_only=False, include_out_of_stock=True)

            embed = discord.Embed(
                title="📦 Stock Levels",
                description="Current stock for all shop items",
                color=discord.Color.blue()
            )

            for item_id, item in list(items.items())[:10]:  # Limit to 10 items
                stock_text = "♾️ Unlimited" if item['stock'] == -1 else f"{item['stock']} available"
                embed.add_field(
                    name=f"{self._get_item_emoji(item)} {item['name']}",
                    value=f"Stock: {stock_text}\nID: `{item_id}`",
                    inline=True
                )

            if len(items) > 10:
                embed.set_footer(text=f"Showing first 10 of {len(items)} items")

            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        # Restock specific item
        if quantity is None:
            # Show current stock
            stock_info = self.shop_manager.check_stock(interaction.guild_id, item_id)
            if not stock_info:
                await interaction.response.send_message("❌ Item not found!", ephemeral=True)
                return

            embed = discord.Embed(
                title="📦 Current Stock",
                description=f"Stock information for item `{item_id}`",
                color=discord.Color.blue()
            )
            embed.add_field(name="Current Stock", value=stock_info['current_stock'], inline=True)
            embed.add_field(name="Available", value="Yes" if stock_info['available'] else "No", inline=True)
            embed.add_field(name="Unlimited", value="Yes" if stock_info['unlimited'] else "No", inline=True)

            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        # VALIDATION: Prevent negative stock
        if quantity < 0:
            await interaction.response.send_message("Stock cannot be negative.", ephemeral=True)
            return

        # Update stock
        try:
            stock_info = self.shop_manager.update_stock(
                interaction.guild_id,
                item_id,
                quantity,
                operation
            )

            # Sync Discord message
            await self.shop_manager.sync_discord_message(interaction.guild_id, item_id, self.bot)

            embed = discord.Embed(
                title="✅ Stock Updated",
                description=f"Stock updated for item `{item_id}`",
                color=discord.Color.green()
            )
            embed.add_field(name="Operation", value=f"{operation.title()} {quantity}", inline=True)
            embed.add_field(name="New Stock", value=stock_info['current_stock'], inline=True)
            embed.add_field(name="Available", value="Yes" if stock_info['available'] else "No", inline=True)

            await interaction.response.send_message(embed=embed, ephemeral=True)

        except ValueError as e:
            await interaction.response.send_message(f"❌ {str(e)}", ephemeral=True)

    @app_commands.command(name="shopstats", description="View shop statistics")
    @app_commands.describe(period="Time period for statistics")
    @app_commands.choices(period=[
        app_commands.Choice(name="All time", value="all"),
        app_commands.Choice(name="Last 24 hours", value="day"),
        app_commands.Choice(name="Last 7 days", value="week"),
        app_commands.Choice(name="Last 30 days", value="month")
    ])
    @app_commands.guild_only()
    @admin_only_interaction()
    async def shop_stats(
        self,
        interaction: discord.Interaction,
        period: str = "all"
    ):
        """View shop statistics"""
        await interaction.response.defer(ephemeral=True)

        try:
            stats = self.shop_manager.get_shop_statistics(interaction.guild_id, period)

            embed = discord.Embed(
                title="📊 Shop Statistics",
                description=f"Statistics for {period if period != 'all' else 'all time'}",
                color=discord.Color.gold()
            )

            embed.add_field(name="Total Items", value=stats.get('total_items', 0), inline=True)
            embed.add_field(name="Active Items", value=stats.get('active_items', 0), inline=True)
            embed.add_field(name="Total Sales", value=f"{stats.get('total_sales', 0)}💰", inline=True)

            embed.add_field(name="Items Sold", value=stats.get('total_quantity_sold', 0), inline=True)
            embed.add_field(name="Revenue", value=f"{stats.get('total_revenue', 0)}💰", inline=True)
            embed.add_field(name="Avg Price", value=f"{stats.get('average_price', 0):.2f}💰", inline=True)

            # Top selling items
            if stats.get('top_items'):
                top_items = stats['top_items'][:5]
                top_text = "\n".join([
                    f"{self._get_item_emoji(item)} {item['name']}: {item['sales_count']} sold"
                    for item in top_items
                ])
                embed.add_field(name="🏆 Top Items", value=top_text, inline=False)

            # Category breakdown
            if stats.get('category_breakdown'):
                category_text = "\n".join([
                    f"{cat.title()}: {count} items"
                    for cat, count in stats['category_breakdown'].items()
                ])
                embed.add_field(name="📂 Categories", value=category_text, inline=False)

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            await interaction.followup.send(f"❌ Failed to load statistics: {str(e)}", ephemeral=True)

    @app_commands.command(name="completetask", description="Mark a task as completed and award reward")
    @app_commands.describe(
        task_id="ID of the task to complete",
        user="User who completed the task (leave empty for current user)"
    )
    @app_commands.guild_only()
    @admin_only_interaction()
    async def complete_task(
        self,
        interaction: discord.Interaction,
        task_id: str,
        user: discord.Member = None
    ):
        """Mark a task as completed and award the reward"""
        await interaction.response.defer(ephemeral=True)

        guild_id = interaction.guild_id
        tasks_data = data_manager.load_guild_data(guild_id, "tasks")

        # Find the task
        tasks = tasks_data.get("tasks", {})
        if task_id not in tasks:
            await interaction.followup.send("❌ Task not found!", ephemeral=True)
            return

        task = tasks[task_id]

        # Check if task is pending or claimed
        if task.get("status") not in ["pending", "claimed"]:
            await interaction.followup.send("❌ Task is not available for completion!", ephemeral=True)
            return

        # Determine the user who completed the task
        completing_user = user or interaction.user

        # If task is claimed, check if it's claimed by the specified user
        user_tasks = tasks_data.get("user_tasks", {})
        if str(completing_user.id) not in user_tasks:
            user_tasks[str(completing_user.id)] = {}

        user_task_data = user_tasks[str(completing_user.id)].get(task_id)
        if not user_task_data:
            # Task not claimed, create user task entry
            user_task_data = {
                "claimed_at": datetime.now().isoformat(),
                "deadline": (datetime.now() + timedelta(hours=task.get("duration_hours", 24))).isoformat(),
                "status": "completed"
            }
            user_tasks[str(completing_user.id)][task_id] = user_task_data
        else:
            # Update existing user task
            user_task_data["status"] = "completed"

        # Award the reward
        currency_cog = self.bot.get_cog('Currency')
        if currency_cog:
            reward = task.get("reward", 0)
            currency_cog._add_balance(
                guild_id,
                completing_user.id,
                reward,
                f"Task completed: {task.get('name', 'Unknown task')}"
            )

            # Update task status
            task["status"] = "completed"
            task["completed_by"] = str(completing_user.id)
            task["completed_at"] = datetime.now().isoformat()

            # Save data atomically
            updates = {
                "tasks": tasks_data,
                "currency": data_manager.load_guild_data(guild_id, "currency"),
                "transactions": data_manager.load_guild_data(guild_id, "transactions")
            }

            success = data_manager.atomic_transaction(guild_id, updates)

            if success:
                # Update Discord message
                await self._update_task_message(guild_id, task_id, task)

                # Send notification to user
                try:
                    config = data_manager.load_guild_data(guild_id, "config")
                    symbol = config.get('currency_symbol', '$')

                    embed = discord.Embed(
                        title="✅ Task Completed!",
                        description=f"You have completed **{task.get('name', 'Unknown task')}**",
                        color=discord.Color.green()
                    )
                    embed.add_field(name="Reward", value=f"{symbol}{reward}", inline=True)
                    embed.add_field(name="Task ID", value=f"`{task_id}`", inline=True)

                    await completing_user.send(embed=embed)
                except discord.Forbidden:
                    pass  # Can't DM user

                # Send success message
                embed = discord.Embed(
                    title="✅ Task Completed",
                    description=f"Task **{task.get('name', 'Unknown task')}** marked as completed",
                    color=discord.Color.green()
                )
                embed.add_field(name="User", value=completing_user.mention, inline=True)
                embed.add_field(name="Reward", value=f"{symbol}{reward}", inline=True)
                embed.add_field(name="Task ID", value=f"`{task_id}`", inline=True)

                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.followup.send("❌ Failed to complete task - data save error!", ephemeral=True)
        else:
            await interaction.followup.send("❌ Currency system not available!", ephemeral=True)

    async def _update_task_message(self, guild_id: int, task_id: str, task_data: dict):
        """Update the Discord message for a completed task"""
        try:
            message_id = task_data.get("message_id")
            if not message_id:
                return

            config = data_manager.load_guild_data(guild_id, "config")
            task_channel_id = config.get("task_channel_id")
            if not task_channel_id:
                return

            guild = self.bot.get_guild(guild_id)
            if not guild:
                return

            channel = guild.get_channel(int(task_channel_id))
            if not channel:
                return

            message = await channel.fetch_message(int(message_id))

            # Create updated embed
            embed = discord.Embed(
                title=f"✅ {task_data['name']}",
                description=task_data.get('description', 'No description'),
                color=discord.Color.green()
            )

            embed.add_field(name="Reward", value=f"💰 {task_data['reward']} coins", inline=True)
            embed.add_field(name="Status", value="✅ Completed", inline=True)

            duration = task_data.get('duration_hours', 24)
            embed.add_field(name="Time Limit", value=f"⏰ {duration} hours", inline=True)

            completed_by_id = task_data.get("completed_by")
            if completed_by_id:
                completed_by = guild.get_member(int(completed_by_id))
                if completed_by:
                    embed.add_field(name="Completed By", value=completed_by.mention, inline=True)

            embed.set_footer(text=f"Task ID: {task_id} | ✅ COMPLETED")

            await message.edit(embed=embed)

        except Exception as e:
            logger.error(f"Failed to update task message for {task_id}: {e}")

    @commands.command(name='cleanup')
    @commands.guild_only()
    @admin_only()
    async def cleanup_inactive_users(self, ctx, days: int = 30):
        """Clean up inactive users who haven't been seen for X days"""
        if days < 7:
            await ctx.send("❌ Days must be at least 7 for safety!")
            return

        guild_id = ctx.guild.id

        # Get all users from currency data
        currency_data = data_manager.load_guild_data(guild_id, 'currency')
        users = currency_data.get('users', {})

        # Find inactive users
        cutoff_date = datetime.now() - timedelta(days=days)
        inactive_users = []

        for user_id, user_data in users.items():
            if user_data.get('is_active', True):
                continue  # Skip active users

            left_at = user_data.get('left_at')
            if not left_at:
                continue  # No leave date recorded

            try:
                leave_date = datetime.fromisoformat(left_at)
                if leave_date < cutoff_date:
                    inactive_users.append((user_id, user_data))
            except (ValueError, TypeError):
                continue  # Invalid date format

        if not inactive_users:
            await ctx.send(f"✅ No inactive users found who left more than {days} days ago.")
            return

        # Create backup
        backup_data = {
            'inactive_users': inactive_users,
            'cleanup_date': datetime.now().isoformat(),
            'cleanup_by': str(ctx.author.id),
            'days_threshold': days
        }

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        data_manager.save_guild_data(guild_id, f"inactive_users_backup_{timestamp}", backup_data)

        # Remove inactive users
        removed_count = 0
        removed_balance = 0

        for user_id, user_data in inactive_users:
            balance = user_data.get('balance', 0)
            removed_balance += balance

            # Remove from users
            del currency_data['users'][user_id]

            # Remove from inventory
            inventory = currency_data.get('inventory', {})
            if user_id in inventory:
                del inventory[user_id]

            removed_count += 1

        # Update total currency
        currency_data['metadata']['total_currency'] = sum(
            u.get('balance', 0) for u in currency_data['users'].values()
        )

        # Save cleaned data
        data_manager.save_guild_data(guild_id, 'currency', currency_data)

        # Broadcast SSE event
        from backend import sse_manager
        sse_manager.broadcast_event('users_cleaned', {
            'guild_id': guild_id,
            'removed_count': removed_count,
            'removed_balance': removed_balance,
            'days_threshold': days
        })

        embed = discord.Embed(
            title="🧹 Inactive Users Cleaned",
            description=f"Removed {removed_count} inactive users who left more than {days} days ago",
            color=discord.Color.orange()
        )

        embed.add_field(name="Days Threshold", value=f"{days} days", inline=True)
        embed.add_field(name="Users Removed", value=removed_count, inline=True)
        embed.add_field(name="Balance Recovered", value=f"{removed_balance}💰", inline=True)
        embed.add_field(name="Backup Created", value=f"inactive_users_backup_{timestamp}", inline=False)

        await ctx.send(embed=embed)


class DeleteConfirmView(discord.ui.View):
    """Confirmation buttons for item deletion"""

    def __init__(self, shop_manager, guild_id, item_id, archive, item):
        super().__init__(timeout=60)
        self.shop_manager = shop_manager
        self.guild_id = guild_id
        self.item_id = item_id
        self.archive = archive
        self.item = item

    def _get_item_emoji(self, item: dict) -> str:
        """Get emoji from item, handling missing emoji field gracefully"""
        emoji = item.get('emoji')
        if emoji:
            return emoji

        # Try to extract emoji from name
        name = item.get('name', '')
        if name and any(ord(c) > 127 for c in name[:5]):  # Check for unicode emoji
            extracted = ''.join(c for c in name[:5] if ord(c) > 127)
            if extracted:
                return extracted

        return '🛍️'  # Default shopping bag emoji

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Execute deletion"""
        try:
            success = self.shop_manager.delete_item(self.guild_id, self.item_id, self.archive)

            if success:
                embed = discord.Embed(
                    title="✅ Item Deleted",
                    description=f"**{self._get_item_emoji(self.item)} {self.item['name']}** has been {'archived' if self.archive else 'permanently deleted'}",
                    color=discord.Color.red()
                )
                embed.add_field(name="Item ID", value=f"`{self.item_id}`", inline=True)
                embed.add_field(name="Action", value="Archived" if self.archive else "Deleted", inline=True)
            else:
                embed = discord.Embed(
                    title="❌ Deletion Failed",
                    description="Item could not be deleted",
                    color=discord.Color.red()
                )

            await interaction.response.edit_message(embed=embed, view=None)
            self.stop()

        except Exception as e:
            await interaction.response.edit_message(
                content=f"❌ Error: {str(e)}",
                embed=None,
                view=None
            )
            self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Cancel deletion"""
        await interaction.response.edit_message(
            content="Deletion cancelled.",
            embed=None,
            view=None
        )
        self.stop()


    async def post_embed(self, guild_id: int, embed_id: str, channel_id: str):
        """Post an embed message to Discord and return message info."""
        try:
            # Get embed data
            config = data_manager.load_guild_data(guild_id, 'config')
            embeds = config.get('embeds', {})
            embed_data = embeds.get(embed_id)

            if not embed_data:
                logger.warning(f"Embed {embed_id} not found in guild {guild_id}")
                return None

            guild = self.bot.get_guild(int(guild_id))
            if not guild:
                logger.error(f"Guild {guild_id} not found")
                return None

            channel = guild.get_channel(int(channel_id))
            if not channel:
                logger.error(f"Channel {channel_id} not found in guild {guild_id}")
                return None

            # Create embed
            from core.embed_builder import EmbedBuilder
            embed = EmbedBuilder.build_embed(embed_data)

            # Send message
            message = await channel.send(embed=embed)

            logger.info(f"Embed message posted: {message.id} for embed {embed_id} in guild {guild_id}")
            return str(message.id)

        except Exception as e:
            logger.error(f"Error posting embed to Discord: {e}", exc_info=True)
            return None

    async def post_announcement(self, guild_id: int, channel_id: str, content: str, embed_data: dict = None, mention_role: str = None):
        """Post an announcement message to Discord and return message info."""
        try:
            guild = self.bot.get_guild(int(guild_id))
            if not guild:
                logger.error(f"Guild {guild_id} not found")
                return None

            channel = guild.get_channel(int(channel_id))
            if not channel:
                logger.error(f"Channel {channel_id} not found in guild {guild_id}")
                return None

            # Create embed if provided
            embed = None
            if embed_data:
                from core.embed_builder import EmbedBuilder
                embed = EmbedBuilder.build_embed(embed_data)

            # Add role mention if specified
            mention_text = ""
            if mention_role:
                role = guild.get_role(int(mention_role))
                if role:
                    mention_text = f"{role.mention} "

            # Send message
            message = await channel.send(content=f"{mention_text}{content}", embed=embed)

            logger.info(f"Announcement message posted: {message.id} in guild {guild_id}")
            return {
                'message_id': str(message.id),
                'channel_id': str(channel_id),
                'content': content,
                'has_embed': embed_data is not None,
                'mention_role': mention_role
            }

        except Exception as e:
            logger.error(f"Error posting announcement to Discord: {e}", exc_info=True)
            return None


async def setup(bot):
    await bot.add_cog(Admin(bot))
