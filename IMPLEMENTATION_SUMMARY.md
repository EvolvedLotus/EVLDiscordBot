# EVLBot — Complete Implementation Outline

> **Living Document** — Reflects the exact architecture and features of the codebase.
> Last Updated: March 2026

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Entry Points & Startup](#2-entry-points--startup)
3. [Core Managers](#3-core-managers)
4. [Currency & Economy System](#4-currency--economy-system)
5. [Task System](#5-task-system)
6. [Shop & Inventory System](#6-shop--inventory-system)
7. [Moderation System](#7-moderation-system)
8. [Announcements & Embeds](#8-announcements--embeds)
9. [General Utility Commands](#9-general-utility-commands)
10. [Admin & Bot Admin Commands](#10-admin--bot-admin-commands)
11. [Ad Claim / Monetization System](#11-ad-claim--monetization-system)
12. [Server Boost Rewards](#12-server-boost-rewards)
13. [Voting System (Top.gg)](#13-voting-system-topgg)
14. [Premium Sync System](#14-premium-sync-system)
15. [Flask Backend (CMS API)](#15-flask-backend-cms-api)
16. [Security & Compliance](#16-security--compliance)
17. [Database & Migrations](#17-database--migrations)
18. [Environment Variables](#18-environment-variables)

---

## 1. Architecture Overview

### Hybrid Process Model
The application runs as a **single process** containing two concurrent systems:
- **Discord Bot** — `discord.py` async event loop (commands, events, background tasks)
- **Flask Backend** — CMS REST API served in a background thread

**File:** `start.py` orchestrates both. Flask is launched in a `threading.Thread`, then the Discord bot starts asynchronously.

### Data Flow
```
Discord Users ─→ Cogs (slash/prefix commands) ─→ Core Managers ─→ Supabase DB
                                                        ↕
CMS Dashboard ─→ Flask API Routes (backend.py) ─→ Core Managers ─→ Supabase DB
                                                        ↓
                                               SSE Manager ─→ Real-time Dashboard Updates
```

### Project Structure
```
task-bot-discord/
├── start.py              # Main entry point (launches Flask + Bot)
├── bot.py                # Bot initialization, cog loading, event handlers
├── backend.py            # Flask CMS API (3100+ lines)
├── config.py             # Centralized configuration & env validation
├── cogs/                 # Discord command extensions (13 files)
│   ├── currency.py       # Economy: balance, daily, transfer, shop commands
│   ├── tasks.py          # Task system: claim, submit, review flows
│   ├── moderation.py     # Auto-moderation, manual actions
│   ├── general.py        # Utility: ping, stats, polls, reminders
│   ├── admin.py          # Server admin: prefix, task completion
│   ├── bot_admin.py      # Full CMS parity: create tasks/items, balance mgmt
│   ├── announcements.py  # Announcement creation & scheduling
│   ├── embeds.py         # Custom embed CRUD
│   ├── ad_claim.py       # Ad-watching reward commands
│   ├── server_boost.py   # Boost detection & rewards
│   ├── vote.py           # Top.gg voting integration
│   └── premium_sync.py   # Subscription sync with external tools DB
├── core/                 # Business logic managers (34 files)
│   ├── data_manager.py   # Supabase CRUD, caching, guild data
│   ├── transaction_manager.py  # Two-phase commit balance operations
│   ├── task_manager.py   # Task lifecycle (create → claim → submit → review)
│   ├── shop_manager.py   # Shop item CRUD, purchase logic
│   ├── cache_manager.py  # In-memory caching layer
│   ├── auth_manager.py   # Session management (Supabase-backed)
│   ├── audit_manager.py  # Event logging & audit trail
│   ├── sse_manager.py    # Server-Sent Events for real-time CMS updates
│   ├── ad_claim_manager.py    # Ad session creation & verification
│   ├── channel_lock_manager.py # Channel lock state persistence
│   ├── announcement_manager.py # Announcement lifecycle
│   ├── embed_builder.py  # Embed construction & validation
│   ├── embed_manager.py  # Embed persistence layer
│   ├── sync_manager.py   # Discord ↔ DB synchronization
│   ├── tier_manager.py   # Subscription tier management
│   ├── evolved_lotus_api.py   # Internal ad network API
│   ├── discord_oauth.py  # OAuth2 flow for CMS login
│   ├── permissions.py    # Role/permission decorators
│   ├── validator.py      # Input validation utilities
│   ├── initializer.py    # Guild initialization logic
│   ├── utils.py          # Embed helpers, number formatting
│   ├── events.py         # Event definitions
│   ├── shared_state.py   # Cross-module shared references
│   ├── client.py         # Custom bot client class
│   ├── task_channel_monitor.py # Task channel message sync
│   └── moderation/       # Moderation sub-package (7 files)
│       ├── protection_manager.py  # Config: profanity list, whitelist, levels
│       ├── scanner.py     # Message scanning (profanity, links, files)
│       ├── enforcer.py    # Action evaluation & application
│       ├── actions.py     # Warn, mute, kick, ban implementations
│       ├── scheduler.py   # Timed moderation actions (unmute, etc.)
│       ├── logger.py      # Moderation audit logging
│       └── health.py      # Moderation system health checks
├── migrations/           # SQL migration files for Supabase
├── docs/                 # Static files served by Flask (CMS frontend)
└── data/                 # Local data (reminders, premium links)
```

---

## 2. Entry Points & Startup

### `start.py` — Main Entry Point
- Loads environment variables via `dotenv`
- Validates configuration via `config.py`
- Starts Flask backend in a daemon `Thread` (calls `backend.run_backend()`)
- Starts the Discord bot asynchronously (calls `bot.run_bot()`)
- Handles graceful shutdown with signal handlers

### `bot.py` — Bot Initialization
- **`run_bot()`**: Creates bot instance, initializes all core managers in dependency order, loads all cogs
- **`on_ready()`**: Post-startup tasks:
  - Guild setup & slash command syncing
  - Persistent view registration (task claim buttons survive restarts)
  - Background task startup (sync, cleanup, backups)
- **Cog Loading Order**: `general` → `currency` → `tasks` → `moderation` → `admin` → `bot_admin` → `announcements` → `embeds` → `ad_claim` → `server_boost` → `vote` → `premium_sync`
- **Manager injection**: After loading, `set_managers()` is called on cogs that need `data_manager` and `transaction_manager`

### `config.py` — Configuration
- `Config` class loads all environment variables with defaults
- **Production validation**: Raises `ValueError` if `JWT_SECRET_KEY` is a default value
- Provides helpers: `get_supabase_config()`, `get_discord_config()`, `allowed_origins`
- CORS origins configured per-environment

---

## 3. Core Managers

### `DataManager` (`core/data_manager.py`)
- Primary Supabase client initialization (`supabase` and `admin_client`)
- `load_guild_data(guild_id, data_type)` — Load guild-scoped data with caching
- `save_guild_data(guild_id, data_type, data)` — Persist guild data
- `ensure_user_exists(guild_id, user_id)` — Upsert user record
- `atomic_transaction(guild_id, updates)` — Multi-table atomic writes
- `invalidate_cache(guild_id, data_type)` — Cache busting after mutations
- `get_all_guilds()` — List all known guild IDs

### `TransactionManager` (`core/transaction_manager.py`)
- **Source of truth** for all currency operations
- **Two-phase commit pattern**:
  1. Log the transaction (amount, balance_before, balance_after, metadata)
  2. Update the user's balance
  - If step 2 fails, step 1 provides a recovery record
- `log_transaction(user_id, guild_id, amount, type, balance_before, balance_after, description, metadata)`
- `get_transactions(guild_id, user_id, limit)` — Paginated history
- `add_transaction(guild_id, user_id, amount, type, description)` — Combined log + balance update

### `TaskManager` (`core/task_manager.py`)
- `create_task(guild_id, task_data)` — Create with auto-incrementing ID
- `claim_task(guild_id, user_id, task_id)` — Validates: active status, expiry, max claims, user limits, duplicate claims
- `submit_task(guild_id, user_id, task_id, proof)` — Mark as submitted, store proof
- `approve_task(guild_id, user_id, task_id)` — Award reward, update status
- `reject_task(guild_id, user_id, task_id, reason)` — Reject with feedback
- `delete_task(guild_id, task_id)` — Remove task and associated data
- Integrates with `SSEManager` and `CacheManager` via setters

### `ShopManager` (`core/shop_manager.py`)
- `create_item(guild_id, item_data)` — Create shop item
- `update_item(guild_id, item_id, updates)` — Partial update
- `delete_item(guild_id, item_id)` — Remove or archive
- `get_shop_items(guild_id, active_only, include_out_of_stock)` — Filtered listing
- `get_inventory(guild_id, user_id, include_item_details)` — User inventory with item metadata
- `purchase_item(guild_id, user_id, item_id, quantity, interaction)` — Full purchase flow

### `CacheManager` (`core/cache_manager.py`)
- In-memory caching layer for frequently accessed data
- TTL-based expiration
- Guild-scoped cache keys

### `AuthManager` (`core/auth_manager.py`)
- **Supabase-backed sessions** (persisted in `web_sessions` table)
- `create_session(user_data)` → session token
- `validate_session(token)` → user data or `None`
- `revoke_session(token)` — Server-side session invalidation
- Sessions survive bot restarts

### `AuditManager` (`core/audit_manager.py`)
- `log_event(event_type, guild_id, user_id, moderator_id, details)` — Structured audit trail
- `AuditEventType` enum: `CMS_ACTION`, `BALANCE_UPDATE`, `TASK_ACTION`, etc.

### `SSEManager` (`core/sse_manager.py`)
- Singleton pattern for Server-Sent Events
- `broadcast_event(event_type, data)` — Push real-time updates to CMS dashboard
- Events: `purchase`, `balance_update`, `task_created`, `shop_item_created`, `moderation_config_update`

### `AdClaimManager` (`core/ad_claim_manager.py`)
- `create_ad_session(user_id, guild_id)` — Generate unique session for ad viewing
- `verify_ad_view(session_id)` — Validate ad was watched, grant 10-point reward
- `get_user_ad_stats(user_id, guild_id)` — Aggregate view/earn statistics
- **Abuse Prevention**: 50 ads/day limit, 60-second cooldown

### `ChannelLockManager` (`core/channel_lock_manager.py`)
- Persists channel lock state in database
- Bot instance setter for Discord API access

### Other Managers
- **`AnnouncementManager`** — Announcement lifecycle, pinning, task announcements
- **`EmbedBuilder`** — Embed construction with validation (title/description limits, color parsing)
- **`EmbedManager`** — Embed persistence and retrieval
- **`SyncManager`** — Discord ↔ Database reconciliation (pending messages, deleted tasks)
- **`TierManager`** — Subscription tier checks and feature gating
- **`DiscordOAuthManager`** — OAuth2 flow: authorization URL, token exchange, user guild fetching
- **`EvolvedLotusAPI`** — Internal ad network: random ad selection, click tracking, blog integration

---

## 4. Currency & Economy System

**Cog:** `cogs/currency.py` (1588 lines)
**Core Manager:** `TransactionManager`, `ShopManager`

### User-Facing Commands

| Command | Description | Permission |
|---------|-------------|------------|
| `/balance [user]` | Check own or another user's balance | Everyone |
| `/daily` | Claim daily reward (24h cooldown) | Everyone |
| `/leaderboard` | Top richest users in the server | Everyone |
| `/transfer <user> <amount> [reason]` | Send coins to another user | Everyone |
| `/transactions [user] [limit]` | View transaction history | Everyone |
| `/admin_give <user> <amount> [reason]` | Grant currency (admin) | Admin |

### Transfer Validation
- ❌ Self-transfer blocked
- ❌ Negative/zero amounts blocked
- ❌ Bot recipients blocked
- ❌ Insufficient balance checked
- ✅ Double-entry transaction logging (sender debit + receiver credit)
- ✅ Cache invalidation after transfer

### Balance Operations (`_add_balance`)
- Two-phase commit: transaction log first, then balance update
- Returns new balance on success, `False` on failure
- Metadata tagging for source tracking (`discord_command`, `admin_grant`, etc.)

---

## 5. Task System

**Cog:** `cogs/tasks.py` (2032 lines)
**Core Manager:** `TaskManager`

### Task Lifecycle
```
Create (Admin/CMS) → Post to Discord Channel (with Claim Button)
    → User Claims (validates eligibility)
        → User Submits Proof (modal with text + file upload)
            → Moderator Reviews (Accept/Reject buttons)
                → Accept: Award reward, mark completed
                → Reject: Notify user with reason
```

### User Commands

| Command | Description |
|---------|-------------|
| `/tasks` | Browse available tasks (paginated) |
| `/mytasks` | View claimed tasks + submit proof (select menu) |
| `/claim <task_id>` | Claim a task |
| `/task_submit <task_id> <proof> [attachment]` | Submit proof for claimed task |
| `/task_claim_proof <task_id> <proof> [attachment]` | Claim + submit in one step |

### Admin Commands (via `bot_admin.py`)

| Command | Description |
|---------|-------------|
| `/create_task` | Create task with name, description, reward, duration, channel, max claims, category, role reward |
| `/list_tasks [status] [category] [user]` | List tasks with filtering |
| `/delete_task <task_id>` | Delete a task |
| `/completetask <task_id> [user]` | Manually complete a task and award reward |

### Interactive UI Components
- **`TaskClaimView`** — Persistent buttons: "Claim Task" + "Submit Proof" (survives bot restarts)
- **`TaskReviewView`** — Accept/Reject buttons for moderator review
- **`TaskListPaginator`** — Previous/Next page navigation
- **`MyTasksView` / `MyTasksSelect`** — Select menu to choose task for proof submission
- **`GeneralTaskProofModal`** — Modal with proof text + notes (fallback for file upload)
- **Raw API Modal** — Custom Discord API payload with `FileUpload` component (type 19) for file attachments

### Task Categories
- **General** — Opens a proof modal with text + file upload on claim
- **Standard** — Claim first, then submit proof separately

### Background Tasks
- Discord API retry with exponential backoff (`discord_operation_with_retry`)
- Persistent view re-registration on bot restart (`on_ready`)
- Custom modal submission handling via `on_interaction` listener

---

## 6. Shop & Inventory System

**Cog:** `cogs/currency.py` (shop commands embedded in Currency cog)
**Core Manager:** `ShopManager`

### User Commands

| Command | Description |
|---------|-------------|
| `/shop` | Browse shop items |
| `/buy <item> [quantity]` | Purchase item (with autocomplete) |
| `/inventory` | View owned items |
| `/redeem` | Redeem an item from inventory |

### Admin Commands

| Command | Description |
|---------|-------------|
| `/shop_create` | Create shop item (name, description, price, stock, category, emoji) |
| `/shop_edit <item_id>` | Edit item fields (partial update) |
| `/shop_delete <item_id>` | Delete shop item |
| `/create_item` (bot_admin) | Create item with Discord channel posting |
| `/list_items` (bot_admin) | List items with category/stock filtering |

### Purchase Flow (`_process_purchase`)
1. Validate item exists and is active
2. Check stock availability
3. Verify user has sufficient balance (double-check with fresh DB read)
4. Deduct balance
5. Update stock count
6. Increment inventory (read-then-upsert to avoid overwrite bug)
7. Log transaction via `TransactionManager`
8. Invalidate cache
9. Broadcast SSE event

### Interactive UI
- **`PurchaseConfirmView`** — Confirm/Cancel buttons for purchase
- **`RedemptionView`** — Select menu for redeemable items
- **`ShopView`** — Paginated shop display
- **Buy Autocomplete** — Live search of active, in-stock items

---

## 7. Moderation System

**Cog:** `cogs/moderation.py` (493 lines)
**Core Sub-Package:** `core/moderation/` (7 modules)

### Architecture
```
on_message event
    → ProtectionManager: Load config, check exemptions
    → MessageScanner: Scan for profanity, links, file violations
    → ProtectionEnforcer: Evaluate severity, determine action
    → ProtectionEnforcer: Apply action (delete, warn, mute, etc.)
    → ModerationLogger: Create audit log entry
```

### Auto-Moderation Features
- **Profanity Filter** — Custom blacklist per guild, scanned on every message
- **Link Protection** — Block unauthorized links, whitelist trusted domains
- **File/Media Protection** — Block unauthorized attachments and media embeds
- **Exemption System** — Per-user, per-channel, per-role exemptions
- **Protection Levels**: `Off`, `Monitor`, `Moderate`, `Strict`

### Manual Action Commands

| Command | Permission | Description |
|---------|-----------|-------------|
| `/warn <user> <reason>` | Moderator | Issue warning (strike) |
| `/mute <user> <duration> <reason>` | Moderator | Temporary mute (minutes) |
| `/unmute <user> [reason]` | Moderator | Remove mute/timeout |
| `/timeout <user> <duration> [reason]` | Moderator | Discord timeout (minutes) |
| `/kick <user> <reason>` | Moderator | Kick from server |
| `/ban <user> <reason>` | Admin | Ban from server |
| `/unban <user_id> [reason]` | Admin | Unban user |
| `/softban <user> [reason]` | Moderator | Ban + immediate unban (clears 7 days of messages) |
| `/pardon <user> [reason]` | Moderator | Remove active strikes/warnings |
| `/clear <amount> [user]` | Moderator | Purge messages (optionally filtered by user) |
| `/slowmode <delay>` | Moderator | Set channel slowmode |
| `/lock [reason]` | Moderator | Lock channel (deny @everyone send) |
| `/unlock [reason]` | Moderator | Unlock channel |

### Configuration Commands

| Command | Permission | Description |
|---------|-----------|-------------|
| `/add_profanity <word>` | Admin | Add to profanity blacklist |
| `/remove_profanity <word>` | Admin | Remove from blacklist |
| `/list_profanity [page]` | Admin | View blacklist (paginated) |
| `/add_whitelist <domain>` | Admin | Whitelist a link domain |
| `/remove_whitelist <domain>` | Admin | Remove from whitelist |
| `/set_protection_level <level>` | Admin | Set strictness (off/monitor/moderate/strict) |

### Logging & Statistics

| Command | Permission | Description |
|---------|-----------|-------------|
| `/warnings <user>` | Moderator | View user's warning history (last 5) |
| `/clearwarnings <user> [reason]` | Moderator | Clear all warnings for a user |
| `/moderation_logs [amount]` | Moderator | View recent moderation log entries |
| `/moderation_stats` | Moderator | Aggregated action breakdown |

### Moderation Sub-Modules
| Module | Responsibility |
|--------|---------------|
| `protection_manager.py` | Config persistence, exemption checks, profanity/whitelist CRUD |
| `scanner.py` | Pattern matching: profanity regex, URL extraction, embed/attachment scanning |
| `enforcer.py` | Severity evaluation engine, action application (delete → warn → mute escalation) |
| `actions.py` | Warn, mute, kick, ban, pardon implementations with Discord API calls |
| `scheduler.py` | Timed actions: scheduled unmutes, temporary bans |
| `logger.py` | Audit log creation with structured metadata |
| `health.py` | System health checks for moderation pipeline |

---

## 8. Announcements & Embeds

### Announcements Cog (`cogs/announcements.py`, 598 lines)

| Command | Permission | Description |
|---------|-----------|-------------|
| `/announce <title> <content> [channel] [mention_everyone] [pin]` | Admin | Create & post announcement |
| `/announce-task <task_id> [channel] [pin]` | Admin | Post task-specific announcement |
| `/scheduleannouncement <title> <content> <delay_minutes> [...]` | Admin (Premium) | Schedule delayed announcement |
| `/create_embed <title> <description> [color] [channel]` | Admin | Simple custom embed |
| `/create_rich_embed <title> <description> [fields...] [color] [thumbnail] [channel]` | Admin | Rich embed with fields |
| `/schedule_rich_embed <delay> <title> <description> [...]` | Admin (Premium) | Schedule delayed embed |
| `/pin-announcement <id>` | Manage Messages | Pin an announcement message |
| `/unpin-announcement <id>` | Manage Messages | Unpin an announcement message |

### Features
- **Scheduled Announcements** — Background loop checks every 60s, sends when `scheduled_for` time is reached
- **Premium Gating** — Scheduling requires `subscription_tier == 'premium'` (checked via `guilds` table)
- **Embed Types** — Regular announcements use plain text + embed; rich embeds support fields, thumbnails, custom colors
- **Auto-Pin** — Optional pinning of sent messages

### Embeds Cog (`cogs/embeds.py`, 315 lines)

| Command | Description |
|---------|-------------|
| `/embed_create` | Create and send a custom embed |
| `/embed_edit <id>` | Edit title, description, or color of existing embed |
| `/embed_delete <id>` | Delete embed and its Discord message |
| `/embed_list` | List all embeds in the server |
| `/announce_embed` | Send an announcement-style embed |

### Features
- **Concurrent Edit Protection** — `asyncio.Lock` per embed ID prevents race conditions
- **Persistence** — Embeds stored in `embeds` guild data with `message_id` tracking
- **Live Editing** — Edits update both DB and the Discord message in-place
- **EmbedBuilder Validation** — Title/description length limits, hex color parsing

---

## 9. General Utility Commands

**Cog:** `cogs/general.py` (814 lines)

### Information Commands

| Command | Type | Description |
|---------|------|-------------|
| `/help` | Slash | Categorized command list (currency, tasks, moderation, general) |
| `!help` | Prefix | Same, for prefix commands |
| `/ping` | Slash | Latency check with color-coded status (🟢 <100ms, 🟡 <200ms, 🔴 >200ms) |
| `/stats` | Slash | Bot statistics: servers, users, uptime, CPU, RAM, Python version, economy totals |
| `/serverinfo` | Slash | Server details: owner, member counts, channels, roles, bot config |
| `/userinfo [user]` | Slash | User profile: roles, join dates, balance, activity |
| `/botinfo` | Prefix | Bot version, features, server count |
| `/avatar [user]` | Slash | Display user avatar (large format with direct link) |
| `/roleinfo <role>` | Slash | Role details: permissions, member count, color, position |

### Interactive Commands

| Command | Description |
|---------|-------------|
| `/poll <question> <option1> <option2> [option3..10]` | Create reaction-based poll (up to 10 options) |
| `/remind <time> <message>` | Set personal reminder (30s–7d, DM delivered) |
| `/clear_channel` | Admin: purge up to 1000 messages |

### Reminder System
- Reminders stored in `data/reminders.json`
- Background loop checks every 30 seconds
- DM delivery with embed formatting
- Auto-cleanup after delivery

---

## 10. Admin & Bot Admin Commands

### Admin Cog (`cogs/admin.py`, 351 lines)

| Command | Description |
|---------|-------------|
| `/setprefix <prefix>` | Change bot prefix (max 5 chars) |
| `/completetask <task_id> [user]` | Manually complete task, award reward, update Discord message |

### Features
- **Task Completion Flow**: Claims task for user if not already claimed → Awards currency reward → Updates task status → Edits Discord message → DMs user with confirmation
- **`DeleteConfirmView`** — Confirm/Cancel buttons for shop item deletion with expired interaction handling

### Bot Admin Cog (`cogs/bot_admin.py`, 765 lines)
Full CMS parity via Discord slash commands.

#### User Management

| Command | Description |
|---------|-------------|
| `/removebalance <user> <amount> [reason]` | Remove currency from user |
| `/setbalance <user> <amount> [reason]` | Set exact balance |
| `/user_balance <user> <action> [amount] [reason]` | Combined: check/set/add/subtract with validation |

#### Task Management

| Command | Description |
|---------|-------------|
| `/create_task` | Full task creation with channel posting and claim button |
| `/list_tasks [status] [category] [user]` | Filtered task listing (paginated) |

#### Shop Management

| Command | Description |
|---------|-------------|
| `/create_item` | Create shop item with Discord channel posting |
| `/list_items [category] [in_stock_only]` | Filtered item listing |

### Features
- All balance modifications create transaction logs
- SSE events broadcast on every mutation
- `_modify_user_balance` helper handles set/add/subtract with non-negative enforcement

---

## 11. Ad Claim / Monetization System

**Cog:** `cogs/ad_claim.py` (206 lines)
**Core Manager:** `AdClaimManager`

### Commands

| Command | Description |
|---------|-------------|
| `/claim-ad` | Create ad session, get link to watch ad and earn 10 points |
| `/ad-stats` | View total views, verified views, total earned |

### Flow
```
/claim-ad → AdClaimManager.create_ad_session() → Generate session ID
    → User clicks "Watch Ad" button (URL link to ad-viewer.html)
        → Ad viewer page loads Monetag Rewarded Popup
            → User watches ad → Clicks "Claim Reward"
                → POST /api/ad-claim/verify → AdClaimManager.verify_ad_view()
                    → Grant 10 points via TransactionManager
```

### Backend Endpoints (in `backend.py`)
- `GET /api/ad-claim/session/<id>` — Get session details for ad viewer
- `POST /api/ad-claim/verify` — Verify ad view, grant reward
- `POST /api/ad-claim/create` — Create session (for CMS use)

### Abuse Prevention
- **Daily limit**: 50 ad views per user per day
- **Cooldown**: 60 seconds between claims
- **IP/User-Agent tracking** for fraud detection

---

## 12. Server Boost Rewards

**Cog:** `cogs/server_boost.py` (460 lines)

### Automatic Detection
- `on_member_update` listener detects `premium_since` changes
- **New boost**: Awards configured reward + DM thank you message
- **Unboost**: Marks boost as inactive in `server_boosts` DB table

### Monthly Recurring Rewards
- Background task runs every 24 hours
- Checks `last_reward_at` for boosts older than 30 days
- Verifies member is still boosting before awarding
- Updates `last_reward_at` on successful reward

### Commands

| Command | Permission | Description |
|---------|-----------|-------------|
| `/boost-settings [enabled] [reward_amount] [log_channel]` | Admin | Configure boost rewards |
| `/boosters` | Everyone | View all current boosters with duration |

### Configuration (stored in `guilds` table)
- `boost_reward_enabled` (bool)
- `boost_reward_amount` (int, default: 1000)
- `boost_log_channel_id` (string)

---

## 13. Voting System (Top.gg)

**Cog:** `cogs/vote.py` (300 lines)

### Commands

| Command | Description |
|---------|-------------|
| `/vote` | Show voting link with reward info and cooldown timer |
| `/votestats` | Personal voting history: total votes, coins earned, recent votes |
| `/votetop` | Monthly leaderboard: top 10 voters |

### Features
- **Server voting** (not bot voting) via Top.gg
- **Server ID extraction** from `TOPGG_TOKEN` JWT payload
- **Rewards**: 100 coins per vote, 200 on weekends, 12-hour cooldown
- **Vote logs** stored in `vote_logs` table (via admin_client)
- **Webhook handler** in `backend.py` processes incoming vote notifications

### UI
- **`VoteView`** — Link button to Top.gg voting page

---

## 14. Premium Sync System

**Cog:** `cogs/premium_sync.py` (181 lines)

### Purpose
Syncs premium subscription status from an external **Tools Database** (separate Supabase instance) to the bot's guild records.

### Commands

| Command | Description |
|---------|-------------|
| `/link_premium <email>` | Link Discord account to premium subscription email |

### Flow
```
User runs /link_premium
    → Checks Tools DB for email in premium_users table
    → Validates: is_premium == true, premium_tier == 'growth_insider'
    → Stores link in data/global/premium_links.json
    → Triggers immediate sync
```

### Background Sync (every 5 minutes)
- Iterates all linked users
- Checks Tools DB for current premium status
- Finds guilds owned by the user
- **Upgrades** guild to `'growth_insider'` if user is premium
- **Downgrades** guild to `'free'` if subscription expired
- DMs owner on tier change

### Environment Variables
- `TOOLS_SUPABASE_URL` — External Tools database URL
- `TOOLS_SUPABASE_KEY` — External Tools database key

---

## 15. Flask Backend (CMS API)

**File:** `backend.py` (3159 lines)

### Security Middleware
- **CORS** — Configurable allowed origins (from `config.py`)
- **CSRF** — `Flask-WTF` with 1-hour token lifetime (webhooks exempted)
- **HTTPS** — `Flask-Talisman` security headers (HTTPS enforced at Railway edge)
- **Rate Limiting** — `Flask-Limiter`: 200/day, 50/hour per IP
- **Session Cookies** — `Secure`, `HttpOnly`, `SameSite=None` in production

### Authentication
- **Master Login** — Username/password with bcrypt hashing
- **Discord OAuth2** — `/api/auth/discord/url` → `/api/auth/discord/callback` → session creation
- **Session Validation** — `require_auth` decorator checks session token cookie
- **Guild Access** — `require_guild_access` decorator validates user has access to specific guild

### Key API Route Groups
1. **Health & Status** — `/api/health`, `/api/status`, `/api/bot/config`
2. **Authentication** — `/api/auth/login`, `/api/auth/discord/*`, `/api/auth/logout`
3. **Server Management** — `/api/servers/<id>/config`, `/api/servers/<id>/users`
4. **Currency** — `/api/servers/<id>/currency/*`, balance updates, transaction history
5. **Tasks** — `/api/servers/<id>/tasks/*` — CRUD, approval, user tasks
6. **Shop** — `/api/servers/<id>/shop/*` — Item CRUD, purchase history
7. **Announcements** — `/api/servers/<id>/announcements/*` — Create, schedule, manage
8. **Embeds** — `/api/servers/<id>/embeds/*` — Embed CRUD with live Discord sync
9. **Moderation** — `/api/servers/<id>/moderation/*` — Config, logs, actions
10. **Ad System** — `/api/ad`, `/api/ad-claim/*` — Ad serving and reward verification
11. **Webhooks** — `/api/webhooks/stripe`, `/api/webhooks/topgg` — Payment & vote processing
12. **Admin** — `/api/admin/*` — Superadmin-only: ad stats, client management, CMS action logging
13. **SSE** — `/api/sse/stream` — Server-Sent Events for real-time dashboard updates

### Manager Initialization
- `initialize_managers()` creates all core managers on startup
- `set_bot_instance(bot)` links bot reference for Discord API access
- Managers are initialized independently of Flask to avoid blocking healthcheck

### Internal Communication
- `get_bot_webhook_url()` — Railway internal networking (`http://bot:5001`)
- `send_admin_message_to_bot()` — Admin messages via internal webhook
- `send_sse_signal_to_bot()` — SSE events via internal webhook

---

## 16. Security & Compliance

### Secrets Management
- `config.py` validates `JWT_SECRET_KEY` is not a default value in production
- All secrets loaded from environment variables

### Session Security
- Sessions stored in Supabase (`web_sessions` table), not memory
- Server-side revocation support
- 24-hour session lifetime with secure cookie flags

### CSRF Protection
- `Flask-WTF` with `CSRFProtect` middleware
- Webhook endpoints exempted (`@csrf.exempt`)
- 1-hour CSRF token lifetime

### HTTPS Enforcement
- `Flask-Talisman` adds security headers (HSTS)
- Railway handles TLS termination at edge (no internal HTTPS redirect)

### Input Validation
- `core/validator.py` — Centralized validation utilities
- Command-level validation: amount > 0, string length limits, bot prevention
- API-level validation: required fields, type checking

### Rate Limiting
- API: 200 requests/day, 50/hour per IP
- Ad claims: 50/day, 60s cooldown per user
- Voting: 12-hour cooldown

### Permission System (`core/permissions.py`)
- Decorators: `@admin_only`, `@admin_only_interaction`, `@moderator_only_interaction`
- Helper functions: `is_admin()`, `is_moderator()`, `is_admin_interaction()`
- Guild-scoped permission checks

### Legal Pages
- `docs/privacy.html` — Privacy policy (Discord, Monetag, Whop data handling)
- `docs/terms.html` — Terms of service

---

## 17. Database & Migrations

### Primary Database: Supabase (PostgreSQL)

#### Key Tables
| Table | Purpose |
|-------|---------|
| `users` | User records (balance, total_earned, total_spent, guild scoping) |
| `guilds` | Guild config, subscription_tier, boost settings |
| `tasks` | Task definitions (name, reward, status, channel, expiry) |
| `user_tasks` | Task claims (status, proof, attachments, deadlines) |
| `shop_items` | Shop item catalog |
| `inventory` | User item ownership (quantity per item) |
| `transactions` | Transaction history (balance audit trail) |
| `web_sessions` | CMS login sessions |
| `ad_views` | Ad claim sessions and verification |
| `global_task_claims` | Global ad-watching task records |
| `vote_logs` | Top.gg vote records |
| `server_boosts` | Boost tracking (active/inactive, last_reward_at) |
| `premium_users` | (Tools DB) Subscription records |

### Migration Files (`migrations/`)
- `001_security_tables.sql` — Session tables, auth infrastructure
- `002_ad_tables.sql` — `ad_views`, `global_task_claims`
- `003_discord_rpc.sql` — RPC functions for Discord user syncing

### Local Data (`data/`)
- `data/reminders.json` — Personal reminder storage
- `data/global/premium_links.json` — Discord ID ↔ email mappings

---

## 18. Environment Variables

### Required
| Variable | Purpose |
|----------|---------|
| `DISCORD_TOKEN` | Bot authentication token |
| `SUPABASE_URL` | Primary database URL |
| `SUPABASE_ANON_KEY` | Public Supabase key |
| `SUPABASE_SERVICE_ROLE_KEY` | Admin Supabase key |
| `JWT_SECRET_KEY` | Session signing key (must not be default in production) |

### Optional / Feature-Specific
| Variable | Purpose |
|----------|---------|
| `PORT` | Flask backend port (default: 5000) |
| `DISCORD_CLIENT_ID` | OAuth2 client ID for CMS login |
| `DISCORD_CLIENT_SECRET` | OAuth2 client secret |
| `TOPGG_TOKEN` | Top.gg API token (JWT containing server ID) |
| `STRIPE_SECRET_KEY` | Stripe payment processing |
| `STRIPE_WEBHOOK_SECRET` | Stripe webhook signature verification |
| `TOOLS_SUPABASE_URL` | External tools DB for premium sync |
| `TOOLS_SUPABASE_KEY` | External tools DB key |
| `BACKEND_URL` | Override for ad viewer URL construction |
| `RAILWAY_PUBLIC_DOMAIN` | Auto-detected on Railway deployment |
| `RAILWAY_ENVIRONMENT` | Environment detection (`production`) |

---

## Architectural Notes

### Future Milestones
1. **Process Separation** — Split Bot + Flask into separate Railway services. Requires migrating shared state to Redis/distributed store.
2. **Gunicorn Workers** — Production Flask should use multiple workers (currently single-threaded).
3. **Comprehensive Input Validation Audit** — Ongoing work to ensure all API endpoints and commands have complete validation.

### Known Patterns
- **Two-Phase Commit** — `TransactionManager` logs before updating, creating an audit trail for recovery
- **Persistent Views** — Task claim buttons re-registered on bot restart via `on_ready`
- **Lazy Manager Initialization** — Cogs receive managers via `set_managers()` after bot initialization to avoid circular imports
- **SSE Broadcast** — All mutations emit events for real-time CMS dashboard updates
- **Cache Invalidation** — `invalidate_cache()` called after every data mutation
