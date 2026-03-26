import discord
from discord.ext import commands, tasks
from discord import app_commands
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from core.permissions import admin_only_interaction

logger = logging.getLogger(__name__)

class RaffleTicketModal(discord.ui.Modal):
    """Modal for purchasing raffle tickets."""
    def __init__(self, giveaway_id: str, giveaway: dict, giveaway_manager):
        super().__init__(title="Buy Raffle Tickets")
        self.giveaway_id = giveaway_id
        self.giveaway = giveaway
        self.giveaway_manager = giveaway_manager
        
        cost = giveaway.get('raffle_cost', 0)
        max_tix = giveaway.get('raffle_max_tickets_per_user', 10)
        
        self.tickets_input = discord.ui.TextInput(
            label="Number of Tickets",
            placeholder=f"Cost: {cost} each. Max: {max_tix}.",
            required=True,
            min_length=1,
            max_length=3
        )
        self.add_item(self.tickets_input)
        
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            tickets = int(self.tickets_input.value)
            res = self.giveaway_manager.enter_giveaway(
                self.giveaway_id,
                str(interaction.guild_id),
                str(interaction.user.id),
                tickets=tickets
            )
            await interaction.followup.send(f"✅ You've purchased {tickets} tickets! Total spent: {tickets * self.giveaway.get('raffle_cost', 0)}.", ephemeral=True)
        except ValueError as ve:
            await interaction.followup.send(f"❌ Cannot enter: {ve}", ephemeral=True)
        except Exception as e:
            logger.error(f"Error processing raffle tickets: {e}")
            await interaction.followup.send("❌ An unexpected error occurred.", ephemeral=True)

class GiveawayEntryView(discord.ui.View):
    def __init__(self, giveaway_id: str):
        super().__init__(timeout=None)
        self.giveaway_id = giveaway_id
        
        btn_enter = discord.ui.Button(label="🎉 Enter Giveaway", custom_id=f"giveaway_enter:{giveaway_id}", style=discord.ButtonStyle.success)
        btn_enter.callback = self.enter_button_callback
        self.add_item(btn_enter)
        
        btn_withdraw = discord.ui.Button(label="🚪 Withdraw Entry", custom_id=f"giveaway_withdraw:{giveaway_id}", style=discord.ButtonStyle.secondary)
        btn_withdraw.callback = self.withdraw_button_callback
        self.add_item(btn_withdraw)

    async def enter_button_callback(self, interaction: discord.Interaction):
        if interaction.user.bot:
            return
            
        manager = interaction.client.giveaway_manager
        if not manager:
            return await interaction.response.send_message("❌ System unavailable.", ephemeral=True)
            
        try:
            giveaway = manager.get_giveaway(self.giveaway_id, str(interaction.guild_id))
            if not giveaway or giveaway['status'] != 'active':
                return await interaction.response.send_message("❌ This giveaway is not active.", ephemeral=True)
                
            ends_at = datetime.fromisoformat(giveaway['ends_at'].replace('Z', '+00:00'))
            if ends_at <= datetime.now(timezone.utc):
                return await interaction.response.send_message("❌ This giveaway has ended.", ephemeral=True)

            mode = giveaway['entry_mode']
            
            if mode == 'raffle':
                modal = RaffleTicketModal(self.giveaway_id, giveaway, manager)
                await interaction.response.send_modal(modal)
            else:
                await interaction.response.defer(ephemeral=True)
                if mode == 'role_restricted':
                    required_roles = giveaway.get('required_role_ids', [])
                    user_roles = [str(r.id) for r in interaction.user.roles]
                    if not any(r in user_roles for r in required_roles):
                        return await interaction.followup.send("❌ You do not have the required roles to enter.", ephemeral=True)
                        
                res = manager.enter_giveaway(self.giveaway_id, str(interaction.guild_id), str(interaction.user.id))
                await interaction.followup.send("✅ You've entered the giveaway!", ephemeral=True)
                
        except ValueError as ve:
            if not interaction.response.is_done():
                await interaction.response.send_message(f"❌ {ve}", ephemeral=True)
            else:
                await interaction.followup.send(f"❌ {ve}", ephemeral=True)
        except Exception as e:
            logger.error(f"Error on enter button: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ An unexpected error occurred.", ephemeral=True)
            else:
                await interaction.followup.send("❌ An unexpected error occurred.", ephemeral=True)

    async def withdraw_button_callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        manager = interaction.client.giveaway_manager
        if not manager:
            return await interaction.followup.send("❌ System unavailable.", ephemeral=True)
            
        try:
            manager.withdraw_entry(self.giveaway_id, str(interaction.guild_id), str(interaction.user.id))
            await interaction.followup.send("✅ You've withdrawn from the giveaway.", ephemeral=True)
        except ValueError as ve:
            await interaction.followup.send(f"❌ Cannot withdraw: {ve}", ephemeral=True)
        except Exception as e:
            logger.error(f"Error on withdraw button: {e}")
            await interaction.followup.send("❌ An unexpected error occurred.", ephemeral=True)


class GiveawayReviewView(discord.ui.View):
    def __init__(self, giveaway_id: str):
        super().__init__(timeout=300)
        self.giveaway_id = giveaway_id

    @discord.ui.button(label="🔄 Reroll", custom_id="giveaway_reroll", style=discord.ButtonStyle.primary)
    async def reroll_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Admin check
        manager = interaction.client.giveaway_manager
        
        # Verify permissions matching @admin_only_interaction roughly
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ You do not have permission to reroll.", ephemeral=True)
            
        await interaction.response.defer(ephemeral=True)
        try:
            winners = await manager.reroll_giveaway(self.giveaway_id, str(interaction.guild_id))
            if winners:
                win_str = ", ".join([f"<@{w}>" for w in winners])
                await interaction.followup.send(f"✅ Rerolled successfully! New winner(s): {win_str}")
            else:
                await interaction.followup.send("✅ Rerolled, but no eligible entries were found.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Reroll failed: {e}", ephemeral=True)


class Giveaways(commands.GroupCog, name="giveaway"):
    """Giveaway commands for administrators and users."""
    
    def __init__(self, bot):
        self.bot = bot
        self.giveaway_manager = None
        self.lifecycle_loop.start()

    def cog_unload(self):
        self.lifecycle_loop.cancel()

    def set_managers(self, data_manager):
        # Used by initialiser if needed, but we set giveaway_manager directly
        if hasattr(self.bot, 'giveaway_manager'):
            self.giveaway_manager = self.bot.giveaway_manager

    def get_manager(self):
        if not self.giveaway_manager and hasattr(self.bot, 'giveaway_manager'):
            self.giveaway_manager = self.bot.giveaway_manager
        return self.giveaway_manager

    @app_commands.command(name="create", description="Create a new giveaway")
    @admin_only_interaction()
    @app_commands.describe(
        channel="The channel to post the giveaway in",
        prize_name="Name of the prize",
        duration="Duration (e.g., 1h, 30m, 2d)",
        entry_mode="open, role_restricted, or raffle",
        winner_count="Number of winners (1-20)",
        prize_description="Extra description for the prize",
        raffle_cost="Cost per ticket if raffle mode",
        raffle_max_tickets="Max tickets per user if raffle mode",
        required_role="A role required to enter if role_restricted"
    )
    async def create(self, interaction: discord.Interaction, 
                     channel: discord.TextChannel, 
                     prize_name: str, 
                     duration: str, 
                     entry_mode: str, 
                     winner_count: int = 1,
                     prize_description: str = None,
                     raffle_cost: int = None,
                     raffle_max_tickets: int = 10,
                     required_role: discord.Role = None):
                     
        await interaction.response.defer(ephemeral=True)
        
        manager = self.get_manager()
        if not manager:
            return await interaction.followup.send("❌ Giveaway system is not initialized.", ephemeral=True)

        try:
            # Parse duration logic
            # E.g. simple parser for 1h, 30m, 2d
            unit = duration[-1]
            val = int(duration[:-1])
            td = None
            if unit == 'h': td = timedelta(hours=val)
            elif unit == 'm': td = timedelta(minutes=val)
            elif unit == 'd': td = timedelta(days=val)
            else:
                # Default minutes
                td = timedelta(minutes=val)
                
            ends_at = datetime.now(timezone.utc) + td
            
            req_roles = []
            if required_role:
                req_roles.append(str(required_role.id))

            config_dict = {
                'channel_id': str(channel.id),
                'prize_name': prize_name,
                'prize_description': prize_description,
                'ends_at': ends_at.isoformat(),
                'entry_mode': entry_mode.lower(),
                'winner_count': winner_count,
                'raffle_cost': raffle_cost,
                'raffle_max_tickets_per_user': raffle_max_tickets,
                'required_role_ids': req_roles,
                'prize_source': 'custom'
            }
            
            giveaway = manager.create_giveaway(str(interaction.guild_id), str(interaction.user.id), config_dict)
            
            if giveaway['status'] == 'active':
                ch, msg = await manager.post_giveaway_embed(giveaway['id'])
                if ch and msg:
                    await interaction.followup.send(f"✅ Giveaway posted in <#{ch}>!", ephemeral=True)
                else:
                    await interaction.followup.send(f"⚠️ Created but failed to post embed in <#{channel.id}>. Check permissions.", ephemeral=True)
            else:
                await interaction.followup.send(f"✅ Giveaway scheduled to start at {giveaway['start_at']}.", ephemeral=True)
                
        except ValueError as ve:
            await interaction.followup.send(f"❌ Configuration error: {ve}", ephemeral=True)
        except Exception as e:
            logger.error(f"Error creating giveaway: {e}")
            await interaction.followup.send(f"❌ Failed to create giveaway: {e}", ephemeral=True)

    @app_commands.command(name="end", description="End a giveaway early")
    @admin_only_interaction()
    async def end_cmd(self, interaction: discord.Interaction, giveaway_id: str):
        await interaction.response.defer(ephemeral=True)
        manager = self.get_manager()
        try:
            winners = await manager.end_giveaway(giveaway_id)
            w_str = ", ".join([f"<@{w}>" for w in winners]) if winners else "None"
            await interaction.followup.send(f"✅ Giveaway {giveaway_id} ended. Winners: {w_str}", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Failed to end giveaway: {e}", ephemeral=True)

    @app_commands.command(name="cancel", description="Cancel a giveaway and refund entries")
    @admin_only_interaction()
    async def cancel_cmd(self, interaction: discord.Interaction, giveaway_id: str):
        await interaction.response.defer(ephemeral=True)
        manager = self.get_manager()
        try:
            res = manager.cancel_giveaway(giveaway_id, str(interaction.guild_id), str(interaction.user.id))
            await interaction.followup.send(f"✅ Cancelled giveaway. Refunded {res.get('refund_count', 0)} entries.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Failed to cancel giveaway: {e}", ephemeral=True)

    @app_commands.command(name="reroll", description="Reroll an ended giveaway")
    @admin_only_interaction()
    async def reroll_cmd(self, interaction: discord.Interaction, giveaway_id: str):
        await interaction.response.defer(ephemeral=True)
        manager = self.get_manager()
        try:
            winners = await manager.reroll_giveaway(giveaway_id, str(interaction.guild_id))
            w_str = ", ".join([f"<@{w}>" for w in winners]) if winners else "None"
            await interaction.followup.send(f"✅ Rerolled! New winners: {w_str}")
        except Exception as e:
            await interaction.followup.send(f"❌ Failed to reroll: {e}", ephemeral=True)

    @app_commands.command(name="myentries", description="View your active giveaway entries")
    async def myentries_cmd(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        manager = self.get_manager()
        try:
            entries = manager.data_manager.admin_client.table('giveaway_entries').select('*, giveaways!inner(*)').eq('guild_id', str(interaction.guild_id)).eq('user_id', str(interaction.user.id)).execute()
            if not entries.data:
                return await interaction.followup.send("📝 You haven't entered any giveaways in this server.", ephemeral=True)
                
            desc = ""
            for e in entries.data:
                g = e['giveaways']
                desc += f"**{g['prize_name']}** — Tickets: {e['tickets']} — Status: {g['status']}\n"
                
            embed = discord.Embed(title="Your Giveaway Entries", description=desc, color=0x3498DB)
            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            logger.error(f"Error fetching entries: {e}")
            await interaction.followup.send("❌ An unexpected error occurred.", ephemeral=True)

    @app_commands.command(name="info", description="View giveaway info")
    async def info_cmd(self, interaction: discord.Interaction, giveaway_id: str):
        await interaction.response.defer(ephemeral=True)
        manager = self.get_manager()
        try:
            g = manager.get_giveaway(giveaway_id, str(interaction.guild_id))
            if not g:
                return await interaction.followup.send("❌ Giveaway not found.", ephemeral=True)
            e = manager.get_user_entry(giveaway_id, str(interaction.user.id))
            
            embed = discord.Embed(title=f"Giveaway Info: {g['prize_name']}", color=0x3498DB)
            embed.add_field(name="Mode", value=g['entry_mode'])
            embed.add_field(name="Status", value=g['status'])
            embed.add_field(name="Total Entries", value=str(g['total_entries']))
            
            if e:
                embed.add_field(name="Your Entry", value=f"{e['tickets']} ticket(s)", inline=False)
            else:
                embed.add_field(name="Your Entry", value="Not entered", inline=False)
                
            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Error fetching info: {e}", ephemeral=True)


    @tasks.loop(seconds=30)
    async def lifecycle_loop(self):
        """Background task for activating, ending, and refreshing giveaways."""
        await self.bot.wait_until_ready()
        manager = self.get_manager()
        if not manager: return
        
        now = datetime.now(timezone.utc).isoformat()
        
        # Step 1: Activate scheduled
        try:
            scheduled = manager.data_manager.admin_client.table('giveaways').select('*').eq('status', 'scheduled').lte('start_at', now).execute()
            for g in scheduled.data:
                manager.data_manager.admin_client.table('giveaways').update({'status': 'active'}).eq('id', g['id']).execute()
                await manager.post_giveaway_embed(g['id'])
        except Exception as e:
            logger.error(f"Lifecycle loop scheduled activate error: {e}")

        # Step 2: End expired active
        try:
            expired = manager.data_manager.admin_client.table('giveaways').select('*').eq('status', 'active').lte('ends_at', now).execute()
            for g in expired.data:
                await manager.end_giveaway(g['id'])
        except Exception as e:
             logger.error(f"Lifecycle loop end expired error: {e}")

        # Step 3: Refresh live embeds
        try:
            # We fetch all active with messages. Large servers might need limit/offset processing
            active_m = manager.data_manager.admin_client.table('giveaways').select('id, ends_at').eq('status', 'active').not_.is_('message_id', 'null').execute()
            # Basic throttling logic
            for g in active_m.data:
                ends_dt = datetime.fromisoformat(g['ends_at'].replace('Z', '+00:00'))
                time_left = (ends_dt - datetime.now(timezone.utc)).total_seconds()
                
                # If less than 10 mins left, refresh every tick (30s)
                # Ignore ones > 10m unless it matches a mod 10 loop. We will just simplify it here to refresh all for now.
                # Proper throttling can be added by storing last_refresh or similar.
                if time_left < 3600:
                   await manager.refresh_giveaway_embed(g['id'])
                
        except Exception as e:
            logger.error(f"Lifecycle loop refresh embed error: {e}")

        # Step 4: Repost missing embeds
        try:
            missing = manager.data_manager.admin_client.table('giveaways').select('id, channel_id').eq('status', 'active').is_('message_id', 'null').execute()
            for g in missing.data:
                await manager.post_giveaway_embed(g['id'])
        except Exception as e:
            logger.error(f"Lifecycle loop repost embed error: {e}")

async def setup(bot):
    await bot.add_cog(Giveaways(bot))
