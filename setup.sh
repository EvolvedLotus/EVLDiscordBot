#!/bin/bash
# Save as setup.sh and run: chmod +x setup.sh && ./setup.sh

echo "🚀 Setting up EVL Discord Bot..."

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install discord.py flask python-dotenv psutil

# Create directory structure
mkdir -p data/guilds data/global data/backups logs static templates cogs core

# Create .env file if it doesn't exist
if [ ! -f .env ]; then
    echo "DISCORD_TOKEN=your_token_here" > .env
    echo "⚠️  Please edit .env and add your Discord bot token"
fi

# Create requirements.txt
cat > requirements.txt << EOF
discord.py>=2.3.0
flask>=2.3.0
python-dotenv>=1.0.0
psutil>=5.9.0
EOF

echo "✅ Setup complete! Edit .env with your bot token, then run: python bot.py"
