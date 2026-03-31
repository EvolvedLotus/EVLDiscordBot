"""
Server Boost Rewards System
Automatically rewards users with coins when they boost the server.
Supports monthly recurring rewards as long as the boost is active.
"""

import discord
from discord.ext import commands, tasks
from discord import app_commands
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

logger = logging.getLogger(__name__)


class ServerBoost(commands.Cog):
    """Handles server boost detection and rewards"""
    
    def __init__(self, bot):
        self.bot = bot
        self.data_manager = bot.data_manager
        self.transaction_manager = bot.transaction_manager
        
        # Default reward amount (can be configured per guild)
        self.default_boost_reward = 1000
        
        # Start the monthly boost reward task
        self.monthly_boost_rewards.start()
        
        logger.info("✅ ServerBoost cog initialized")
    
    def cog_unload(self):
        """Clean up when cog is unloaded"""
        self.monthly_boost_rewards.cancel()
    
    async def get_boost_settings(self, guild_id: str) -> dict:
        """Get boost reward settings for a guild"""
        try:
            result = self.data_manager.supabase.table('guilds').select(
                'boost_reward_amount, boost_reward_enabled, boost_log_channel_id'
            ).eq('guild_id', guild_id).execute()
            
            if result.data and len(result.data) > 0:
                settings = result.data[0]
                return {
                    'enabled': settings.get('boost_reward_enabled', True),
                    'reward_amount': settings.get('boost_reward_amount', self.default_boost_reward),
                    'log_channel_id': settings.get('boost_log_channel_id')
                }
            
            # Return defaults if not found
            return {
                'enabled': True,
                'reward_amount': self.default_boost_reward,
                'log_channel_id': None
            }
        except Exception as e:
            logger.error(f"Error fetching boost settings for guild {guild_id}: {e}")
            return {
                'enabled': True,
                'reward_amount': self.default_boost_reward,
                'log_channel_id': None
            }
    
    async def record_boost(self, guild_id: str, user_id: str, boost_type: str = 'new'):
        """Record a server boost in the database"""
        try:
            boost_data = {
                'guild_id': guild_id,
                'user_id': user_id,
                'boost_type': boost_type,  # 'new' or 'renewed'
                'boosted_at': datetime.now(timezone.utc).isoformat(),
                'last_reward_at': datetime.now(timezone.utc).isoformat(),
                'is_active': True
            }
            
            # Insert or update boost record
            self.data_manager.supabase.table('server_boosts').upsert(
                boost_data,
                on_conflict='guild_id,user_id'
            ).execute()
            
            logger.info(f"Recorded {boost_type} boost for user {user_id} in guild {guild_id}")
            
        except Exception as e:
            logger.error(f"Error recording boost: {e}")
    
    async def reward_booster(self, guild: discord.Guild, member: discord.Member, boost_type: str = 'new'):
        """Reward a user for boosting the server"""
        guild_id = str(guild.id)
        user_id = str(member.id)
        
        try:
            # Get boost settings
            settings = await self.get_boost_settings(guild_id)
            
            if not settings['enabled']:
                logger.info(f"Boost rewards disabled for guild {guild_id}")
                return
            
            reward_amount = settings['reward_amount']
            
            # Award coins using transaction manager
            result = self.transaction_manager.add_transaction(
                guild_id=guild_id,
                user_id=user_id,
                amount=reward_amount,
                transaction_type='boost_reward',
                description=f"Server boost reward ({boost_type})"
            )
            
            if result['success']:
                # Record the boost
                await self.record_boost(guild_id, user_id, boost_type)
                
                # Send thank you message
                try:
                    embed = discord.Embed(
                        title="🚀 Thank You for Boosting!",
                        description=f"Thank you for boosting **{guild.name}**!",
                        color=discord.Color.from_rgb(255, 115, 250)  # Nitro pink
                    )
                    embed.add_field(
                        name="💰 Reward",
                        value=f"You've been rewarded **{reward_amount:,}** coins!",
                        inline=False
                    )
                    embed.add_field(
                        name="🔄 Monthly Rewards",
                        value="You'll continue to receive this reward monthly as long as you keep boosting!",
                        inline=False
                    )
                    embed.set_thumbnail(url=member.display_avatar.url)
                    embed.set_footer(text=f"New Balance: {result['new_balance']:,} coins")
                    
                    await member.send(embed=embed)
                    logger.info(f"Sent boost reward DM to {member.name}")
                except discord.Forbidden:
                    logger.warning(f"Could not DM {member.name} - DMs disabled")
                except Exception as dm_error:
                    logger.error(f"Error sending boost reward DM: {dm_error}")
                
                # Log to boost log channel if configured
                if settings['log_channel_id']:
                    try:
                        log_channel = guild.get_channel(int(settings['log_channel_id']))
                        if log_channel:
                            log_embed = discord.Embed(
                                title="🚀 Server Boost Detected",
                                description=f"{member.mention} has boosted the server!",
                                color=discord.Color.from_rgb(255, 115, 250),
                                timestamp=datetime.now(timezone.utc)
                            )
                            log_embed.add_field(
                                name="Reward Given",
                                value=f"{reward_amount:,} coins",
                                inline=True
                            )
                            log_embed.add_field(
                                name="Boost Type",
                                value=boost_type.capitalize(),
                                inline=True
                            )
                            log_embed.set_thumbnail(url=member.display_avatar.url)
                            
                            await log_channel.send(embed=log_embed)
                    except Exception as log_error:
                        logger.error(f"Error logging boost to channel: {log_error}")
                
                logger.info(f"✅ Rewarded {member.name} with {reward_amount} coins for boosting {guild.name}")
            else:
                logger.error(f"Failed to reward booster: {result.get('error')}")
                
        except Exception as e:
            logger.error(f"Error rewarding booster {member.name} in {guild.name}: {e}", exc_info=True)
    
    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        """Detect when a member boosts the server"""
        # Check if premium_since changed (indicates boost status change)
        if before.premium_since is None and after.premium_since is not None:
            # User just started boosting (or re-boosting)
            logger.info(f"🚀 {after.name} started boosting {after.guild.name}")
            
            # Check for 48-hour grace period
            try:
                # Query boost record without a match filter first to handle case-insensitivity or existing data
                existing = self.data_manager.supabase.table('server_boosts').select('*').match({
                    'guild_id': str(after.guild.id),
                    'user_id': str(after.id)
                }).execute()
                
                if existing.data:
                    boost = existing.data[0]
                    unboosted_at_str = boost.get('unboosted_at')
                    
                    if unboosted_at_str:
                        unboosted_at = datetime.fromisoformat(unboosted_at_str.replace('Z', '+00:00'))
                        grace_period = timedelta(hours=48)
                        
                        if datetime.now(timezone.utc) - unboosted_at < grace_period:
                            # WITHIN GRACE PERIOD: Restore boost, keep original boosted_at (streak preserved)
                            logger.info(f"✅ {after.name} re-boosted within 48h grace period. Streak preserved.")
                            self.data_manager.supabase.table('server_boosts').update({
                                'is_active': True,
                                'unboosted_at': None,
                                'boost_type': 'renewed'
                            }).match({
                                'guild_id': str(after.guild.id),
                                'user_id': str(after.id)
                            }).execute()
                            
                            # Log restoration to server log
                            await self.log_boost_event(after.guild, after, "Restored (Grace Period)")
                            return

                # If no record, or past grace period, treat as a NEW boost streak
                await self.reward_booster(after.guild, after, boost_type='new')
                
            except Exception as e:
                logger.error(f"Error handling boost grace period: {e}")
                # Fallback to standard reward procedure
                await self.reward_booster(after.guild, after, boost_type='new')
        
        elif before.premium_since is not None and after.premium_since is None:
            # User stopped boosting
            logger.info(f"💔 {after.name} stopped boosting {after.guild.name}")
            
            # Instead of deactivating immediately, set unboosted_at
            # The background cleanup loop will officially deactivate after 48h.
            # This allows re-boosting within the grace window to preserve the streak.
            try:
                self.data_manager.supabase.table('server_boosts').update({
                    'unboosted_at': datetime.now(timezone.utc).isoformat(),
                    'updated_at': datetime.now(timezone.utc).isoformat()
                }).match({
                    'guild_id': str(after.guild.id),
                    'user_id': str(after.id)
                }).execute()
            except Exception as e:
                logger.error(f"Error recording boost lapse: {e}")
    
    @tasks.loop(hours=24)
    async def monthly_boost_rewards(self):
        """Check for boosters who should receive their monthly reward"""
        logger.info("Running monthly boost rewards check...")
        
        # 1. CLEANUP: Permanently deactivate boosts that lapsed > 48 hours ago
        try:
            grace_cutoff = datetime.now(timezone.utc) - timedelta(hours=48)
            cleanup_res = self.data_manager.supabase.table('server_boosts').update({
                'is_active': False,
                'updated_at': datetime.now(timezone.utc).isoformat()
            }).match({
                'is_active': True
            }).lt('unboosted_at', grace_cutoff.isoformat()).execute()
            
            if cleanup_res.data:
                logger.info(f"🧹 Deactivated {len(cleanup_res.data)} boosts past 48h grace window")
        except Exception as e:
            logger.error(f"Error cleaning up lapsed boosts: {e}")

        try:
            # 2. SCAN: Get active boosts (excluding those in grace period lapse)
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=30)
            
            result = self.data_manager.supabase.table('server_boosts').select('*').match({
                'is_active': True,
                'unboosted_at': None  # Only reward those currently boosting
            }).lt('last_reward_at', cutoff_date.isoformat()).execute()
            
            if not result.data:
                logger.info("No boosters currently due for monthly rewards")
                return
            
            rewards_given = 0
            for boost in result.data:
                guild_id = boost['guild_id']
                user_id = boost['user_id']
                
                try:
                    # Validate guild/member still exist/boost (second line of defense)
                    guild = self.bot.get_guild(int(guild_id))
                    member = guild.get_member(int(user_id)) if guild else None
                    
                    if not guild or not member or member.premium_since is None:
                        # Mark as lapsed if they are no longer found or boosting
                        self.data_manager.supabase.table('server_boosts').update({
                            'unboosted_at': datetime.now(timezone.utc).isoformat()
                        }).match({'guild_id': guild_id, 'user_id': user_id}).execute()
                        continue
                    
                    # Get reward amount
                    settings = await self.get_boost_settings(guild_id)
                    if not settings.get('enabled', True):
                        continue
                    
                    reward_amount = settings.get('reward_amount', 1000)

                    # 3. ATOMIC REWARD: Use RPC to claim and award in one atomic transaction
                    # This prevents double-rewards if the bot restarts mid-loop.
                    claim_result = self.data_manager.admin_client.rpc(
                        'claim_monthly_boost_reward',
                        {
                            'p_guild_id': str(guild_id),
                            'p_user_id': str(user_id),
                            'p_amount': reward_amount
                        }
                    ).execute()

                    if claim_result.data and claim_result.data.get('success'):
                        data = claim_result.data
                        rewards_given += 1
                        
                        # Send DM notification
                        try:
                            embed = discord.Embed(
                                title="🎁 Monthly Boost Reward",
                                description=f"Thank you for continuing to boost **{guild.name}**!",
                                color=discord.Color.from_rgb(255, 115, 250)
                            )
                            embed.add_field(name="💰 Reward", value=f"**{reward_amount:,}** coins", inline=True)
                            embed.set_footer(text=f"New Balance: {int(data['new_balance']):,} coins")
                            await member.send(embed=embed)
                        except:
                            pass # DMs blocked
                        
                        logger.info(f"✅ Atomic reward granted to {member.name} in {guild.name}")
                    else:
                        error_msg = claim_result.data.get('error', 'Unknown error') if claim_result.data else 'No response'
                        logger.debug(f"Skipped {user_id}: {error_msg}")

                except Exception as e:
                    logger.error(f"Error rewarding booster {user_id}: {e}")
            
            logger.info(f"Monthly rewards cycle complete: {rewards_given} users rewarded")
            
        except Exception as e:
            logger.error(f"Error in monthly boost rewards task: {e}", exc_info=True)
    
    @monthly_boost_rewards.before_loop
    async def before_monthly_boost_rewards(self):
        """Wait until bot is ready before starting the task"""
        await self.bot.wait_until_ready()
        logger.info("Monthly boost rewards task initialized")
    
    # ============= ADMIN COMMANDS =============
    
    @app_commands.command(name="boost-settings", description="Configure server boost rewards")
    @app_commands.describe(
        enabled="Enable or disable boost rewards",
        reward_amount="Amount of coins to reward per boost",
        log_channel="Channel to log boost events"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def boost_settings(
        self,
        interaction: discord.Interaction,
        enabled: Optional[bool] = None,
        reward_amount: Optional[int] = None,
        log_channel: Optional[discord.TextChannel] = None
    ):
        """Configure boost reward settings for this server"""
        guild_id = str(interaction.guild_id)
        
        try:
            # Get current settings
            current_settings = await self.get_boost_settings(guild_id)
            
            # Prepare update data
            update_data = {}
            
            if enabled is not None:
                update_data['boost_reward_enabled'] = enabled
            
            if reward_amount is not None:
                if reward_amount < 0:
                    await interaction.response.send_message(
                        "❌ Reward amount must be positive!",
                        ephemeral=True
                    )
                    return
                update_data['boost_reward_amount'] = reward_amount
            
            if log_channel is not None:
                update_data['boost_log_channel_id'] = str(log_channel.id)
            
            # Update settings if there are changes
            if update_data:
                self.data_manager.supabase.table('guilds').update(
                    update_data
                ).eq('guild_id', guild_id).execute()
            
            # Get updated settings
            new_settings = await self.get_boost_settings(guild_id)
            
            # Create response embed
            embed = discord.Embed(
                title="🚀 Server Boost Settings",
                color=discord.Color.from_rgb(255, 115, 250),
                timestamp=datetime.now(timezone.utc)
            )
            
            embed.add_field(
                name="Status",
                value="✅ Enabled" if new_settings['enabled'] else "❌ Disabled",
                inline=True
            )
            embed.add_field(
                name="Reward Amount",
                value=f"{new_settings['reward_amount']:,} coins",
                inline=True
            )
            
            if new_settings['log_channel_id']:
                channel = interaction.guild.get_channel(int(new_settings['log_channel_id']))
                embed.add_field(
                    name="Log Channel",
                    value=channel.mention if channel else "Not set",
                    inline=True
                )
            else:
                embed.add_field(
                    name="Log Channel",
                    value="Not set",
                    inline=True
                )
            
            embed.set_footer(text=f"Configured by {interaction.user.name}")
            
            await interaction.response.send_message(embed=embed)
            
        except Exception as e:
            logger.error(f"Error updating boost settings: {e}", exc_info=True)
            await interaction.response.send_message(
                f"❌ Error updating boost settings: {str(e)}",
                ephemeral=True
            )
    
    @app_commands.command(name="boosters", description="View all current server boosters")
    async def view_boosters(self, interaction: discord.Interaction):
        """View all members currently boosting the server"""
        guild = interaction.guild
        
        try:
            # Get all boosters from the guild
            boosters = [member for member in guild.members if member.premium_since is not None]
            
            if not boosters:
                await interaction.response.send_message(
                    "💔 No one is currently boosting this server.",
                    ephemeral=True
                )
                return
            
            # Sort by boost date (oldest first)
            boosters.sort(key=lambda m: m.premium_since)
            
            # Create embed
            embed = discord.Embed(
                title=f"🚀 Server Boosters ({len(boosters)})",
                description=f"Thank you to all our boosters! 💖",
                color=discord.Color.from_rgb(255, 115, 250),
                timestamp=datetime.now(timezone.utc)
            )
            
            # Add boosters to embed (max 25 fields)
            for i, member in enumerate(boosters[:25]):
                boost_duration = datetime.now(timezone.utc) - member.premium_since
                days = boost_duration.days
                
                embed.add_field(
                    name=f"{i+1}. {member.display_name}",
                    value=f"Boosting for {days} days",
                    inline=True
                )
            
            if len(boosters) > 25:
                embed.set_footer(text=f"And {len(boosters) - 25} more boosters...")
            else:
                embed.set_footer(text=f"Total Boosts: {guild.premium_subscription_count}")
            
            await interaction.response.send_message(embed=embed)
            
        except Exception as e:
            logger.error(f"Error viewing boosters: {e}", exc_info=True)
            await interaction.response.send_message(
                f"❌ Error viewing boosters: {str(e)}",
                ephemeral=True
            )


async def setup(bot):
    """Load the ServerBoost cog"""
    await bot.add_cog(ServerBoost(bot))
