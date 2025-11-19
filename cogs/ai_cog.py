"""
AI Cog - Gemini AI Integration for Discord Bot
Provides /chat slash command for AI-powered conversations
"""

import discord
from discord import app_commands
from discord.ext import commands
import logging
import os
from typing import Optional
import google.generativeai as genai

logger = logging.getLogger(__name__)

class AICog(commands.Cog):
    """AI Cog for Gemini integration"""

    def __init__(self, bot):
        self.bot = bot
        self.api_key = os.getenv('GEMINI_API_KEY')

        if not self.api_key:
            logger.error("GEMINI_API_KEY not found in environment variables")
            raise ValueError("GEMINI_API_KEY environment variable is required")

        # Configure Gemini
        genai.configure(api_key=self.api_key)

        # Initialize model - try newer model first, fallback to older if needed
        try:
            self.model = genai.GenerativeModel('gemini-1.5-flash')
        except Exception as e:
            logger.warning(f"Failed to initialize gemini-1.5-flash: {e}, trying gemini-1.0-pro")
            try:
                self.model = genai.GenerativeModel('gemini-1.0-pro')
            except Exception as e2:
                logger.error(f"Failed to initialize gemini-1.0-pro: {e2}")
                raise ValueError("No compatible Gemini model available")

        # Store conversation history per user per guild
        self.conversations = {}

        logger.info("AI Cog initialized with Gemini API")

    def get_conversation_key(self, guild_id: int, user_id: int) -> str:
        """Get unique conversation key for user in guild"""
        return f"{guild_id}_{user_id}"

    def get_conversation_history(self, guild_id: int, user_id: int) -> list:
        """Get conversation history for user, create if doesn't exist"""
        key = self.get_conversation_key(guild_id, user_id)

        if key not in self.conversations:
            self.conversations[key] = []

        return self.conversations[key]

    def add_to_conversation(self, guild_id: int, user_id: int, role: str, content: str):
        """Add message to conversation history"""
        key = self.get_conversation_key(guild_id, user_id)
        history = self.get_conversation_history(guild_id, user_id)

        # Add new message
        history.append({"role": role, "content": content})

        # Keep only last 20 messages to avoid token limits
        if len(history) > 20:
            history.pop(0)

        self.conversations[key] = history

    def clear_conversation(self, guild_id: int, user_id: int):
        """Clear conversation history for user"""
        key = self.get_conversation_key(guild_id, user_id)
        self.conversations[key] = []

    @app_commands.command(name="chat", description="Chat with AI assistant")
    @app_commands.describe(
        message="Your message to the AI",
        reset="Reset conversation history (optional)"
    )
    async def chat(
        self,
        interaction: discord.Interaction,
        message: str,
        reset: Optional[bool] = False
    ):
        """Chat with Gemini AI"""

        # Check if feature is enabled for this guild
        if hasattr(self.bot, 'data_manager'):
            config = self.bot.data_manager.load_guild_data(interaction.guild.id, 'config')
            if not config.get('features', {}).get('ai_chat', True):
                await interaction.response.send_message(
                    "❌ AI chat is disabled for this server.",
                    ephemeral=True
                )
                return

        # Defer response since AI calls can take time
        await interaction.response.defer(ephemeral=True)

        try:
            user_id = interaction.user.id
            guild_id = interaction.guild.id

            # Reset conversation if requested
            if reset:
                self.clear_conversation(guild_id, user_id)
                await interaction.followup.send(
                    "🧹 Conversation history cleared! What would you like to talk about?",
                    ephemeral=True
                )
                return

            # Get conversation history
            history = self.get_conversation_history(guild_id, user_id)

            # Add user message to history
            self.add_to_conversation(guild_id, user_id, "user", message)

            # Prepare messages for Gemini (convert to Gemini format)
            gemini_messages = []
            for msg in history:
                if msg["role"] == "user":
                    gemini_messages.append(f"User: {msg['content']}")
                elif msg["role"] == "assistant":
                    gemini_messages.append(f"Assistant: {msg['content']}")

            # Add current user message
            gemini_messages.append(f"User: {message}")

            # Create prompt with conversation context
            prompt = "\n".join(gemini_messages)
            prompt += "\n\nAssistant:"

            # Generate response
            response = self.model.generate_content(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=0.7,
                    top_p=0.8,
                    top_k=40,
                    max_output_tokens=1024,
                )
            )

            ai_response = response.text.strip()

            # Add AI response to conversation history
            self.add_to_conversation(guild_id, user_id, "assistant", ai_response)

            # Send response (truncate if too long for Discord)
            if len(ai_response) > 1900:  # Leave room for formatting
                ai_response = ai_response[:1900] + "...\n\n*(Response truncated)*"

            embed = discord.Embed(
                title="🤖 AI Assistant",
                description=ai_response,
                color=discord.Color.blue()
            )

            embed.set_footer(text=f"Conversation with {interaction.user.display_name}")

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error in AI chat command: {e}")

            # Provide helpful error message
            error_embed = discord.Embed(
                title="❌ AI Error",
                description="Sorry, I encountered an error while processing your request. Please try again later.",
                color=discord.Color.red()
            )

            try:
                await interaction.followup.send(embed=error_embed, ephemeral=True)
            except:
                # If followup fails, try to send a simple message
                await interaction.followup.send(
                    "❌ Sorry, I encountered an error. Please try again.",
                    ephemeral=True
                )

    @app_commands.command(name="clear_chat", description="Clear your AI conversation history")
    async def clear_chat(self, interaction: discord.Interaction):
        """Clear user's conversation history"""

        guild_id = interaction.guild.id
        user_id = interaction.user.id

        # Clear conversation
        self.clear_conversation(guild_id, user_id)

        embed = discord.Embed(
            title="🧹 Chat Cleared",
            description="Your conversation history has been cleared. Start fresh!",
            color=discord.Color.green()
        )

        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot):
    """Setup function for cog loading"""
    await bot.add_cog(AICog(bot))
