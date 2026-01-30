#!/usr/bin/env python3
"""
EVL Discord Bot - Single Command Startup
Run with: python start.py
Runs both Flask backend AND Discord bot concurrently
"""

import os
import sys
import subprocess
import asyncio
import threading
from pathlib import Path

def check_requirements():
    """Check if all requirements are installed"""
    print("🔍 Checking requirements...")

    required_packages = [
        'discord',
        'flask',
        'flask-cors',
        'python-dotenv',
        'psutil',
        'bcrypt',
        'cryptography',
        'PyJWT',
        'python-dateutil',
        'aiohttp'
    ]

    missing = []
    for package in required_packages:
        try:
            __import__(package.replace('-', '_'))
        except ImportError:
            missing.append(package)

    if missing:
        print(f"❌ Missing packages: {', '.join(missing)}")
        print("📦 Installing requirements...")
        subprocess.check_call([sys.executable, '-m', 'pip', 'install', '-r', 'requirements.txt'])
        print("✅ Requirements installed!")
    else:
        print("✅ All requirements satisfied!")

def check_env():
    """Check if .env file exists and has token"""
    if not Path('.env').exists():
        print("❌ .env file not found!")
        token = input("Enter your Discord Bot Token: ").strip()
        with open('.env', 'w') as f:
            f.write(f"DISCORD_TOKEN={token}\n")
            f.write("ADMIN_USERNAME=admin\n")
            f.write("ADMIN_PASSWORD=changeme123\n")
            f.write("FLASK_ENV=development\n")
            f.write("DATA_DIR=data\n")
        print("✅ .env file created!")
    else:
        with open('.env', 'r') as f:
            content = f.read()
            if 'your_token_here' in content or not content.strip():
                print("⚠️  Please edit .env and add your Discord bot token")
                return False
    return True

def create_directories():
    """Create necessary directories"""
    print("📁 Creating directories...")

    directories = [
        'data/guilds',
        'data/global',
        'data/backups',
        'logs',
        'static',
        'templates',
        'cogs',
        'core'
    ]

    for directory in directories:
        Path(directory).mkdir(parents=True, exist_ok=True)

    print("✅ Directories created!")

def run_flask_app():
    """Run Flask in a separate thread"""
    port = int(os.getenv('PORT', 5000))
    print(f"[Flask] Starting web server on http://0.0.0.0:{port}")
    try:
        from backend import app, init_sse
        init_sse()  # Initialize SSE system
        app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False, threaded=True)
    except Exception as e:
        print(f"[Flask] Error starting Flask app: {e}")
        import traceback
        traceback.print_exc()

async def run_discord_bot():
    """Run Discord bot asynchronously"""
    print("[Discord] Starting Discord bot...")
    try:
        import bot
        await bot.run_bot()
    except Exception as e:
        print(f"[Discord] Error starting Discord bot: {e}")
        import traceback
        traceback.print_exc()

async def main():
    """Main function to run both bot and Flask concurrently"""
    print("=" * 50)
    print("🤖 EVL Discord Bot - Startup")
    print("=" * 50)
    print()

    try:
        # Create directories
        create_directories()

        # Check requirements
        check_requirements()

        # Check environment
        if not check_env():
            return

        print()
        print("=" * 50)
        print("🚀 Starting services...")
        print("=" * 50)
        print()

        # Start Flask in a separate thread
        flask_thread = threading.Thread(target=run_flask_app, daemon=True)
        flask_thread.start()
        print("[Flask] Web server thread started")

        # Wait a moment for Flask to initialize
        await asyncio.sleep(2)

        # Start Discord bot (this will block)
        print("[Discord] Starting Discord bot...")
        await run_discord_bot()

    except KeyboardInterrupt:
        print("\n\n✋ Shutdown requested")
        print("[Shutdown] Shutting down both services...")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("[Shutdown] Graceful shutdown complete")
        sys.exit(0)
