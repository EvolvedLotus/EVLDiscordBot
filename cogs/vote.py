"""
Vote Cog - Commands for voting on Top.gg and other bot lists
"""

import discord
from discord.ext import commands, tasks
from discord import app_commands
import logging
import os
import aiohttp
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)


class VoteCog(commands.Cog):
    """Commands for voting and vote rewards"""
    
    def __init__(self, bot):
        self.bot = bot
        self.data_manager = bot.data_manager
        # Bot and server IDs for vote links
        self.bot_id = "1155751362764742676"  # EVLBot ID
        
        # Start stats loop if token exists
        self.topgg_token = os.getenv('TOPGG_TOKEN')
        if self.topgg_token:
            self.post_stats.start()
            
    def cog_unload(self):
        """Clean up tasks when cog is unloaded"""
        if self.topgg_token:
            self.post_stats.cancel()
            
    @tasks.loop(minutes=30)
    async def post_stats(self):
        """Post server count to Top.gg"""
        if not self.topgg_token:
            return
            
        try:
            # Use bot.user.id if available, fallback to hardcoded
            bot_id = self.bot.user.id if self.bot.user else self.bot_id
            
            async with aiohttp.ClientSession() as session:
                url = f"https://top.gg/api/bots/{bot_id}/stats"
                payload = {"server_count": len(self.bot.guilds)}
                headers = {"Authorization": self.topgg_token}
                
                async with session.post(url, json=payload, headers=headers) as resp:
                    if resp.status == 200:
                        logger.info(f"✅ Posted server count ({len(self.bot.guilds)}) to Top.gg")
                    else:
                        resp_text = await resp.text()
                        logger.warning(f"⚠️ Failed to post Top.gg stats: {resp.status} - {resp_text}")
        except Exception as e:
            logger.error(f"Error posting Top.gg stats: {e}")

    @post_stats.before_loop
    async def before_post_stats(self):
        await self.bot.wait_until_ready()
        
    @app_commands.command(name="vote", description="🗳️ Vote for the bot and earn coins!")
    async def vote(self, interaction: discord.Interaction):
        """Show voting links and rewards info"""
        
        embed = discord.Embed(
            title="🗳️ Vote for EVLBot!",
            description="Support us by voting and earn **coins** as a reward!",
            color=discord.Color.gold()
        )
        
        # Vote links
        embed.add_field(
            name="📊 Top.gg",
            value=f"[**Vote Now →**](https://top.gg/bot/{self.bot_id}/vote)",
            inline=True
        )
        
        # Rewards info
        embed.add_field(
            name="🪙 Rewards",
            value="• **100 coins** per vote\n• **200 coins** on weekends!\n• Can vote every 12 hours",
            inline=True
        )
        
        # Check if user has voted recently
        try:
            result = self.data_manager.admin_client.table('vote_logs').select('created_at').eq(
                'user_id', str(interaction.user.id)
            ).order('created_at', desc=True).limit(1).execute()
            
            if result.data:
                last_vote = datetime.fromisoformat(result.data[0]['created_at'].replace('Z', '+00:00'))
                next_vote = last_vote + timedelta(hours=12)
                now = datetime.now(timezone.utc)
                
                if now < next_vote:
                    time_left = next_vote - now
                    hours, remainder = divmod(int(time_left.total_seconds()), 3600)
                    minutes = remainder // 60
                    embed.add_field(
                        name="⏰ Next Vote",
                        value=f"You can vote again in **{hours}h {minutes}m**",
                        inline=False
                    )
                else:
                    embed.add_field(
                        name="✅ Vote Ready!",
                        value="You can vote now!",
                        inline=False
                    )
            else:
                embed.add_field(
                    name="🆕 First Vote",
                    value="You haven't voted yet - be the first!",
                    inline=False
                )
        except Exception as e:
            logger.error(f"Error checking vote status: {e}")
        
        embed.set_footer(text="Thank you for supporting EVLBot! 💜")
        embed.set_thumbnail(url=self.bot.user.display_avatar.url if self.bot.user else None)
        
        # Create button view
        view = VoteView(self.bot_id)
        
        await interaction.response.send_message(embed=embed, view=view)
    
    @app_commands.command(name="votestats", description="📊 Check your voting history and stats")
    async def votestats(self, interaction: discord.Interaction):
        """Show user's voting statistics"""
        
        try:
            # Get all votes for this user
            result = self.data_manager.admin_client.table('vote_logs').select('*').eq(
                'user_id', str(interaction.user.id)
            ).order('created_at', desc=True).execute()
            
            votes = result.data if result.data else []
            total_votes = len(votes)
            total_coins = sum(v.get('reward', 100) for v in votes)
            
            embed = discord.Embed(
                title=f"📊 Vote Stats for {interaction.user.display_name}",
                color=discord.Color.blue()
            )
            
            embed.add_field(
                name="🗳️ Total Votes",
                value=f"**{total_votes}** votes",
                inline=True
            )
            
            embed.add_field(
                name="🪙 Coins Earned",
                value=f"**{total_coins:,}** coins",
                inline=True
            )
            
            # Recent votes
            if votes:
                recent = votes[:5]
                recent_text = ""
                for vote in recent:
                    date = datetime.fromisoformat(vote['created_at'].replace('Z', '+00:00'))
                    weekend_bonus = " 🌟" if vote.get('is_weekend') else ""
                    recent_text += f"• {date.strftime('%b %d')} - **{vote.get('reward', 100)}** coins{weekend_bonus}\n"
                
                embed.add_field(
                    name="📅 Recent Votes",
                    value=recent_text or "No recent votes",
                    inline=False
                )
                
                # Last vote time
                last_vote = datetime.fromisoformat(votes[0]['created_at'].replace('Z', '+00:00'))
                next_vote = last_vote + timedelta(hours=12)
                now = datetime.now(timezone.utc)
                
                if now < next_vote:
                    time_left = next_vote - now
                    hours, remainder = divmod(int(time_left.total_seconds()), 3600)
                    minutes = remainder // 60
                    status = f"⏰ Vote again in **{hours}h {minutes}m**"
                else:
                    status = "✅ **Ready to vote!**"
                    
                embed.add_field(
                    name="Status",
                    value=status,
                    inline=False
                )
            else:
                embed.add_field(
                    name="📅 Recent Votes",
                    value="No votes yet! Use `/vote` to get started.",
                    inline=False
                )
            
            embed.set_thumbnail(url=interaction.user.display_avatar.url)
            embed.set_footer(text="Vote every 12 hours to maximize rewards!")
            
            await interaction.response.send_message(embed=embed)
            
        except Exception as e:
            logger.error(f"Error getting vote stats: {e}")
            await interaction.response.send_message(
                "❌ Error loading vote stats. Please try again later.",
                ephemeral=True
            )
    
    @app_commands.command(name="votetop", description="🏆 See the top voters this month")
    async def votetop(self, interaction: discord.Interaction):
        """Show top voters leaderboard"""
        
        try:
            # Get votes from the last 30 days
            thirty_days_ago = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
            
            result = self.data_manager.admin_client.table('vote_logs').select(
                'user_id, reward'
            ).gte('created_at', thirty_days_ago).execute()
            
            if not result.data:
                await interaction.response.send_message(
                    "📊 No votes recorded in the last 30 days!",
                    ephemeral=True
                )
                return
            
            # Aggregate votes by user
            user_votes = {}
            for vote in result.data:
                uid = vote['user_id']
                if uid not in user_votes:
                    user_votes[uid] = {'count': 0, 'coins': 0}
                user_votes[uid]['count'] += 1
                user_votes[uid]['coins'] += vote.get('reward', 100)
            
            # Sort by vote count
            sorted_users = sorted(user_votes.items(), key=lambda x: x[1]['count'], reverse=True)[:10]
            
            embed = discord.Embed(
                title="🏆 Top Voters (Last 30 Days)",
                color=discord.Color.gold()
            )
            
            leaderboard = ""
            medals = ["🥇", "🥈", "🥉"]
            
            for i, (user_id, stats) in enumerate(sorted_users):
                medal = medals[i] if i < 3 else f"**{i+1}.**"
                
                # Try to get username
                try:
                    user = await self.bot.fetch_user(int(user_id))
                    username = user.display_name
                except:
                    username = f"User {user_id[:8]}..."
                
                leaderboard += f"{medal} **{username}** - {stats['count']} votes ({stats['coins']:,} coins)\n"
            
            embed.description = leaderboard or "No voters to display"
            embed.set_footer(text="Vote with /vote to appear on this leaderboard!")
            
            await interaction.response.send_message(embed=embed)
            
        except Exception as e:
            logger.error(f"Error getting vote leaderboard: {e}")
            await interaction.response.send_message(
                "❌ Error loading leaderboard. Please try again later.",
                ephemeral=True
            )


class VoteView(discord.ui.View):
    """Button view for voting links"""
    
    def __init__(self, bot_id: str):
        super().__init__(timeout=None)
        self.bot_id = bot_id
        
        # Add vote button (links to Top.gg)
        self.add_item(discord.ui.Button(
            label="Vote on Top.gg",
            style=discord.ButtonStyle.link,
            url=f"https://top.gg/bot/{bot_id}/vote",
            emoji="🗳️"
        ))


async def setup(bot):
    await bot.add_cog(VoteCog(bot))
    logger.info("✓ Vote cog loaded")
