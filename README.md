# 🤖 EVL Discord Bot

**A comprehensive Discord economy and community management bot with an integrated web-based admin dashboard.**

Built by **EvolvedLotus** | Powered by Python, discord.py, and Supabase

---

## 📋 Overview

EVL Discord Bot is a feature-rich, multi-server Discord bot designed for community managers who want to implement a reward-based economy system, task management, moderation tools, and more. The bot includes a powerful web-based CMS (Content Management System) for easy administration without needing to use Discord commands.

### ✨ Key Features

- 💰 **Full Economy System** - Currency, daily rewards, transactions, leaderboards
- 📋 **Task Management** - Create, assign, and reward users for completing tasks
- 🛒 **Shop System** - Customizable shop with items, roles, and inventory management
- 🛡️ **Advanced Moderation** - Warnings, mutes, kicks, bans, profanity filters, and auto-moderation
- 📢 **Announcements & Embeds** - Rich embed creator with scheduling capabilities
- 🤖 **AI Chat Integration** - Built-in AI assistant for server members
- 📊 **Web Admin Dashboard** - Full-featured CMS for managing all bot functions
- 💸 **Ad Reward System** - Monetag integration allowing users to earn currency by watching ads
- 🔄 **Real-time Sync** - Live updates between Discord and the web dashboard
- 🌐 **Multi-Server Support** - Manage multiple Discord servers with isolated data

---

## 🚀 Quick Start

### Prerequisites

- Python 3.9 or higher
- A Discord Bot Token ([Create one here](https://discord.com/developers/applications))
- A Supabase account ([Sign up here](https://supabase.com))
- Administrator permissions for your Discord server

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/EvolvedLotus/EVLDiscordBot.git
   cd EVLDiscordBot
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure environment variables**
   
   Copy `.env.example` to `.env` and fill in your credentials:
   ```env
   DISCORD_TOKEN=your_discord_bot_token
   SUPABASE_URL=your_supabase_project_url
   SUPABASE_ANON_KEY=your_supabase_anon_key
   SUPABASE_SERVICE_ROLE_KEY=your_supabase_service_role_key
   JWT_SECRET_KEY=your_jwt_secret_for_cms_auth
   PORT=8080
   ```

4. **Set up the database**
   
   Import the `schema.sql` file into your Supabase project to create all necessary tables.

5. **Run the bot**
   ```bash
   python start.py
   ```

---

## 📚 Command Reference

The bot includes **76+ slash commands** organized into the following categories:

### 💰 Currency & Economy
- `/balance` - Check your balance
- `/daily` - Claim daily reward (100 coins)
- `/leaderboard` - View top 10 richest users
- `/transfer` - Send coins to another user
- `/transactions` - View your transaction history

### 🛒 Shop Commands
- `/shop` - Browse available items
- `/buy` - Purchase an item
- `/inventory` - View your items
- `/redeem` - Redeem purchased items
- `/shop_create` - Create shop items (Admin)
- `/shop_edit` - Edit shop items (Admin)
- `/shop_delete` - Delete shop items (Admin)

### 📋 Task Management
- `/tasks` - View available tasks
- `/claim` - Claim a task
- `/mytasks` - View your claimed tasks
- `/task_submit` - Submit proof for a task
- `/create_task` - Create new tasks (Admin)
- `/task_assign` - Assign tasks to users (Admin)
- `/completetask` - Mark task as complete (Admin)

### 🛡️ Moderation
- `/warn` - Issue a warning
- `/mute` / `/timeout` - Temporarily mute a user
- `/kick` - Kick a user
- `/ban` / `/unban` - Ban/unban users
- `/softban` - Ban and immediately unban (clears messages)
- `/warnings` - View user warnings
- `/clearwarnings` - Clear warnings
- `/lock` / `/unlock` - Lock/unlock channels
- `/slowmode` - Set channel slowmode
- `/clear` - Bulk delete messages

### 📢 Announcements & Embeds
- `/announce` - Create an announcement
- `/embed_create` - Create custom embeds
- `/embed_edit` - Edit existing embeds
- `/embed_list` - List all embeds
- `/scheduleannouncement` - Schedule announcements
- `/pin-announcement` / `/unpin-announcement` - Pin/unpin announcements

### 🤖 AI & Utility
- `/chat` - Chat with AI assistant
- `/clear_chat` - Clear your AI conversation history
- `/help` - Display help information
- `/ping` - Check bot latency
- `/stats` - View bot statistics
- `/serverinfo` - Display server information
- `/userinfo` - Display user information
- `/poll` - Create polls with up to 10 options
- `/remind` - Set personal reminders

For a complete list of commands, see [`commandlist.txt`](commandlist.txt).

---

## 🖥️ Web Admin Dashboard

Access the web-based CMS at your deployment URL (e.g., `https://your-bot.railway.app` or GitHub Pages).

### Dashboard Features:
- 📊 **Dashboard** - Overview of server statistics and activity
- 👥 **User Management** - View users, manage balances, assign roles
- 🛒 **Shop Management** - Create, edit, and manage shop items
- 📋 **Task Management** - Create and monitor tasks
- 📢 **Announcements** - Create and schedule announcements
- 📧 **Embed Builder** - Visual embed creator
- ⚙️ **Server Settings** - Configure channels, bot status, and permissions
- 📝 **Logs** - View system logs and moderation history

### Authentication
The CMS uses Discord OAuth2 for secure authentication. Server owners and administrators can log in to manage their servers.

---

## 🏗️ Architecture

### Tech Stack
- **Bot Framework**: discord.py 2.x
- **Backend API**: aiohttp (async web server)
- **Database**: Supabase (PostgreSQL)
- **Frontend**: Vanilla HTML/CSS/JavaScript
- **Deployment**: Railway / GitHub Pages (CMS)
- **Ad Integration**: Monetag

### Project Structure
```
├── bot.py                 # Main bot instance and event handlers
├── backend.py             # REST API for web dashboard
├── start.py               # Unified startup script
├── cogs/                  # Command modules
│   ├── currency.py        # Economy commands
│   ├── tasks.py           # Task management
│   ├── moderation.py      # Moderation features
│   ├── admin.py           # Admin commands
│   └── ...
├── core/                  # Core managers and utilities
│   ├── data_manager.py    # Database operations
│   ├── task_manager.py    # Task logic
│   ├── shop_manager.py    # Shop logic
│   └── ...
├── docs/                  # Web dashboard files
│   ├── index.html         # Dashboard UI
│   ├── app.js             # Dashboard logic
│   └── styles.css         # Dashboard styles
└── schema.sql             # Database schema
```

---

## 🔧 Configuration

### Bot Settings (via CMS)
- **Bot Status**: Customize the bot's activity status
- **Channel Configuration**: Set log channels, announcement channels, shop channels
- **Moderation Settings**: Configure auto-moderation, profanity filters, link whitelists
- **Economy Settings**: Adjust daily rewards, starting balance, transaction limits

### Environment Variables
All sensitive configuration is managed through environment variables. See `.env.example` for the complete list.

---

## 🌐 Deployment

### Railway (Recommended)
1. Connect your GitHub repository to Railway
2. Add all environment variables from `.env.example`
3. Railway will automatically deploy using `railway_start.py`

### GitHub Pages (CMS Only)
The `docs/` folder is configured for GitHub Pages deployment to host the admin dashboard.

---

## 📊 Database Schema

The bot uses Supabase with the following main tables:
- `guilds` - Server configurations
- `users` - User data per server
- `tasks` - Task definitions and assignments
- `shop_items` - Shop inventory
- `transactions` - Currency transaction history
- `moderation_logs` - Moderation actions
- `announcements` - Scheduled announcements
- `embeds` - Saved embed templates

See `schema.sql` for the complete database structure.

---

## 🤝 Support & Contributing

This is an open-source project maintained by **EvolvedLotus**.

### Reporting Issues
If you encounter bugs or have feature requests, please open an issue on GitHub.

### Contributing
Contributions are welcome! Please ensure your code follows the existing style and includes appropriate documentation.

---

## 📜 License

This project is open source. Feel free to use, modify, and distribute as needed.

---

## 🙏 Acknowledgments

- Built with [discord.py](https://github.com/Rapptz/discord.py)
- Database powered by [Supabase](https://supabase.com)
- Deployed on [Railway](https://railway.app)

---

**Made with ❤️ by EvolvedLotus**
