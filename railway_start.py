#!/usr/bin/env python3
"""
Discord Bot - Railway Deployment Entry Point
Run with: python railway_start.py
"""

import os
import sys
import asyncio
import logging
from dotenv import load_dotenv

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Verify token exists
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
if not DISCORD_TOKEN:
    logger.error("❌ DISCORD_TOKEN not found in environment variables!")
    sys.exit(1)

logger.info("✅ DISCORD_TOKEN found")

async def main():
    """Main entry point for Railway"""
    try:
        logger.info("🚀 Starting Discord Bot on Railway...")
        
        # Import and run bot
        from bot import run_bot
        
        logger.info("📥 Importing bot module...")
        await run_bot()
        
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("✋ Shutdown requested")
    except Exception as e:
        logger.error(f"❌ Error: {e}", exc_info=True)
        sys.exit(1)
