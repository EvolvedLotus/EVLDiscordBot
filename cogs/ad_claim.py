"""
AD CLAIM COG
Discord commands for the permanent global ad-watching task
"""

import discord
from discord.ext import commands
from discord import app_commands
import logging
from typing import Optional
import os

logger = logging.getLogger(__name__)


class AdClaimCog(commands.Cog, name="Ad Claims"):
    """Commands for claiming rewards by watching ads"""
    
    def __init__(self, bot):
        self.bot = bot
        self.data_manager = bot.data_manager
        self.ad_claim_manager = getattr(bot, 'ad_claim_manager', None)
        
        if self.ad_claim_manager:
            logger.info("✅ AdClaimCog initialized with ad_claim_manager from bot")
        else:
            logger.warning("⚠️ ad_claim_manager not found on bot instance")
    
    @app_commands.command(name="claim-ad", description="Watch an ad to earn 10 points!")
    async def claim_ad(self, interaction: discord.Interaction):
        """
        Create an ad viewing session and send the user a link to watch the ad
        """
        try:
            await interaction.response.defer(ephemeral=True)
            
            if not self.ad_claim_manager:
                await interaction.followup.send(
                    "❌ Ad claim system is not available. Please contact an administrator.",
                    ephemeral=True
                )
                return
            
            user_id = str(interaction.user.id)
            guild_id = str(interaction.guild.id)
            
            # Create ad session
            result = self.ad_claim_manager.create_ad_session(
                user_id=user_id,
                guild_id=guild_id
            )
            
            if not result.get('success'):
                await interaction.followup.send(
                    f"❌ Failed to create ad session: {result.get('error', 'Unknown error')}",
                    ephemeral=True
                )
                return
            
            # Get the viewer URL
            session_id = result['session_id']
            
            # Construct the full URL
            # Try BACKEND_URL first, then Railway's public domain, then localhost
            backend_url = os.getenv('BACKEND_URL')
            if not backend_url:
                railway_domain = os.getenv('RAILWAY_PUBLIC_DOMAIN') or os.getenv('RAILWAY_STATIC_URL')
                if railway_domain:
                    backend_url = f"https://{railway_domain}"
                else:
                    backend_url = 'http://localhost:5000'
            
            viewer_url = f"{backend_url}/ad-viewer.html?session={session_id}"
            
            # Create embed with instructions
            embed = discord.Embed(
                title="🎁 Claim Your Free Points!",
                description="Click the button below to watch an ad and earn **10 points**!",
                color=discord.Color.purple()
            )
            
            embed.add_field(
                name="How it works:",
                value=(
                    "1️⃣ Click the **Watch Ad** button below\n"
                    "2️⃣ Wait for the ad to load and display\n"
                    "3️⃣ Click **Claim Reward** after viewing\n"
                    "4️⃣ Get **10 points** added to your balance!"
                ),
                inline=False
            )
            
            embed.add_field(
                name="📊 Your Stats:",
                value=f"You can claim this reward **unlimited times**!",
                inline=False
            )
            
            embed.set_footer(
                text="Disclaimer: Ads are from third-party networks. We don't control their content."
            )
            
            # Create button view
            view = AdClaimView(viewer_url)
            
            await interaction.followup.send(
                embed=embed,
                view=view,
                ephemeral=True
            )
            
            logger.info(f"Created ad session {session_id} for user {user_id} in guild {guild_id}")
            
        except Exception as e:
            logger.error(f"Error in claim_ad command: {e}", exc_info=True)
            await interaction.followup.send(
                "❌ An error occurred. Please try again later.",
                ephemeral=True
            )
    
    @app_commands.command(name="ad-stats", description="View your ad watching statistics")
    async def ad_stats(self, interaction: discord.Interaction):
        """
        Show user's ad watching statistics
        """
        try:
            await interaction.response.defer(ephemeral=True)
            
            if not self.ad_claim_manager:
                await interaction.followup.send(
                    "❌ Ad claim system is not available.",
                    ephemeral=True
                )
                return
            
            user_id = str(interaction.user.id)
            guild_id = str(interaction.guild.id)
            
            # Get stats
            stats = self.ad_claim_manager.get_user_ad_stats(user_id, guild_id)
            
            if not stats.get('success'):
                await interaction.followup.send(
                    "❌ Failed to retrieve statistics.",
                    ephemeral=True
                )
                return
            
            # Create stats embed
            embed = discord.Embed(
                title="📊 Your Ad Watching Statistics",
                color=discord.Color.blue()
            )
            
            embed.add_field(
                name="Total Ad Views",
                value=f"**{stats['total_views']}** ads watched",
                inline=True
            )
            
            embed.add_field(
                name="Verified Views",
                value=f"**{stats['verified_views']}** verified",
                inline=True
            )
            
            embed.add_field(
                name="Total Earned",
                value=f"**{stats['total_earned']}** points",
                inline=True
            )
            
            embed.set_footer(text=f"User ID: {user_id}")
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            logger.error(f"Error in ad_stats command: {e}", exc_info=True)
            await interaction.followup.send(
                "❌ An error occurred. Please try again later.",
                ephemeral=True
            )


class AdClaimView(discord.ui.View):
    """View with button to open ad viewer"""
    
    def __init__(self, viewer_url: str):
        super().__init__(timeout=300)  # 5 minute timeout
        self.viewer_url = viewer_url
        
        # Add button with the viewer URL
        button = discord.ui.Button(
            label="Watch Ad & Earn 10 Points",
            style=discord.ButtonStyle.primary,
            emoji="🎁",
            url=viewer_url
        )
        self.add_item(button)


async def setup(bot):
    """Setup function to add the cog to the bot"""
    await bot.add_cog(AdClaimCog(bot))
    logger.info("✅ AdClaimCog loaded")
