#!/usr/bin/env python3
"""
Discord Bot - Railway Deployment Entry Point
Run with: python railway_start.py
Runs both Flask backend AND Discord bot concurrently
"""

import os
import sys
import asyncio
import logging
import threading
from pathlib import Path

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment variables (only for local development)
if os.getenv('ENVIRONMENT') != 'production':
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass  # dotenv not installed in production

# Verify token exists
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
if not DISCORD_TOKEN:
    logger.error("❌ DISCORD_TOKEN not found in environment variables!")
    sys.exit(1)

logger.info("✅ DISCORD_TOKEN found")

def run_flask_app():
    """Run Flask in a separate thread"""
    logger.info("[Flask] Starting web server on http://0.0.0.0:5000")
    try:
        from backend import run_backend
        run_backend()
    except Exception as e:
        logger.error(f"[Flask] Error starting Flask app: {e}")
        import traceback
        traceback.print_exc()

async def run_discord_bot():
    """Run Discord bot asynchronously"""
    logger.info("[Discord] Starting Discord bot...")
    try:
        from bot import run_bot
        await run_bot()
    except Exception as e:
        logger.error(f"[Discord] Error starting Discord bot: {e}")
        import traceback
        traceback.print_exc()

async def main():
    """Main function to run both bot and Flask concurrently"""
    logger.info("=" * 50)
    logger.info("🤖 Discord Economy Bot - Railway Startup")
    logger.info("=" * 50)

    try:
        # Create directories if they don't exist
        directories = ['data/guilds', 'data/global', 'logs']
        for directory in directories:
            Path(directory).mkdir(parents=True, exist_ok=True)

        logger.info("=" * 50)
        logger.info("🚀 Starting Railway services...")
        logger.info("=" * 50)

        # Start Flask in a separate thread
        flask_thread = threading.Thread(target=run_flask_app, daemon=True)
        flask_thread.start()
        logger.info("[Flask] Web server thread started")

        # Wait a moment for Flask to initialize
        await asyncio.sleep(3)

        # Start Discord bot (this will block)
        logger.info("[Discord] Starting Discord bot...")
        await run_discord_bot()

    except KeyboardInterrupt:
        logger.info("\n\n✋ Shutdown requested")
        logger.info("[Shutdown] Shutting down both services...")
    except Exception as e:
        logger.error(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    try:
        runner = asyncio.Runner()
        runner.run(main())
    except KeyboardInterrupt:
        logger.info("[Shutdown] Graceful shutdown complete")
        sys.exit(0)
    finally:
        runner.close()
