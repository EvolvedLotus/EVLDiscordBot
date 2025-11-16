@echo off
REM Save as setup.bat and run by double-clicking

echo Setting up Discord Economy Bot...

REM Create virtual environment
python -m venv venv
call venv\Scripts\activate.bat

REM Install dependencies
pip install discord.py flask python-dotenv psutil

REM Create directory structure
mkdir data\guilds 2>nul
mkdir data\global 2>nul
mkdir data\backups 2>nul
mkdir logs 2>nul
mkdir static 2>nul
mkdir templates 2>nul
mkdir cogs 2>nul
mkdir core 2>nul

REM Create .env file if it doesn't exist
if not exist .env (
    echo DISCORD_TOKEN=your_token_here > .env
    echo Please edit .env and add your Discord bot token
)

REM Create requirements.txt
echo discord.py>=2.3.0 > requirements.txt
echo flask>=2.3.0 >> requirements.txt
echo python-dotenv>=1.0.0 >> requirements.txt
echo psutil>=5.9.0 >> requirements.txt

echo Setup complete! Edit .env with your bot token, then run: python bot.py
pause
