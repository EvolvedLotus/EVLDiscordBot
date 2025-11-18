# Enhanced Discord CMS with Bidirectional Synchronization

## 🎯 Overview

This enhanced Discord CMS provides **full bidirectional synchronization** between a Flask web interface and Discord bot functionality. The system enables seamless management of Discord server content through a web dashboard while maintaining real-time synchronization with Discord.

## 🚀 Key Features

### ✅ **Bidirectional Synchronization**
- **Real-time sync** between CMS and Discord
- **Conflict resolution** with multiple strategies
- **Automatic message management** for tasks, shop items, announcements, and embeds
- **State tracking** and recovery mechanisms

### 🔐 **Enhanced Authentication**
- **JWT-based authentication** with session management
- **Role-based access control** (Admin, Moderator, User)
- **Secure API endpoints** with proper validation
- **Session timeout** and cleanup

### 📊 **Comprehensive Audit Logging**
- **Complete audit trail** for all system activities
- **Moderation action tracking** with detailed metadata
- **Content management audit** trails
- **Currency transaction logging** with integrity checks
- **Export capabilities** for compliance reporting

### 🎮 **Advanced Content Management**
- **Task Management**: Create, update, and track tasks with Discord integration
- **Shop System**: Full inventory management with real-time pricing updates
- **Announcement System**: Rich announcements with embed support
- **Embed Builder**: Visual embed creation and management
- **Currency System**: Complete economy management with transaction history

### 🤖 **Intelligent Moderation**
- **Content filtering** with profanity and link protection
- **Automated actions** based on violation severity
- **Custom word lists** and domain whitelisting
- **Role-based exemptions** and channel-specific rules

## 🏗️ **System Architecture**

### **Core Components**

#### **1. SyncManager** (`core/sync_manager.py`)
```python
# Bidirectional synchronization engine
sync_manager = SyncManager(data_manager, audit_manager, sse_manager)

# Sync entity from CMS to Discord
await sync_manager.sync_from_cms(SyncEntity.TASK, "task_123", guild_id, changes)

# Sync entity from Discord to CMS
await sync_manager.sync_from_discord(SyncEntity.USER_BALANCE, "user_456", guild_id, changes)

# Bidirectional sync
await sync_manager.bidirectional_sync(SyncEntity.TASK, "task_123", guild_id)
```

#### **2. AuthManager** (`core/auth_manager.py`)
```python
# JWT-based authentication
auth_manager = AuthManager(data_manager, jwt_secret)

# Generate tokens
token = auth_manager.generate_token({"user_id": "123", "role": "admin"})

# Verify tokens
result = auth_manager.verify_token(token)

# Session management
session_id = auth_manager.create_session(user_data)
session = auth_manager.get_session(session_id)
```

#### **3. AuditManager** (`core/audit_manager.py`)
```python
# Comprehensive audit logging
audit_manager = AuditManager(data_manager)

# Log various events
audit_manager.log_moderation_action("kick", guild_id, user_id, moderator_id, "reason")
audit_manager.log_content_action("create", guild_id, user_id, "task", "task_123")
audit_manager.log_currency_action("grant", guild_id, user_id, 100, "reward")

# Retrieve audit logs
logs = audit_manager.get_audit_logs(guild_id, filters={"event_type": "moderation.kick"})
```

### **Enhanced Backend** (`backend.py`)
- **Integrated managers** with automatic initialization
- **Enhanced SSE system** with selective subscriptions
- **Real-time broadcasting** of all changes
- **Comprehensive health checks** and monitoring

### **Real-time Communication**
```javascript
// Subscribe to specific events
const eventSource = new EventSource('/api/stream?guilds=123456&events=task_update,balance_update');

eventSource.onmessage = function(event) {
    const data = JSON.parse(event.data);
    if (data.type === 'task_update') {
        updateTaskDisplay(data);
    }
};
```

## 📋 **API Endpoints**

### **Authentication**
```
POST   /api/auth/login          # User login
GET    /api/auth/me             # Get current user
POST   /api/auth/logout         # User logout
GET    /api/auth/validate       # Validate session
```

### **Server Management**
```
GET    /api/servers             # List all servers
GET    /api/<guild_id>/config   # Get server config
PUT    /api/<guild_id>/config   # Update server config
```

### **Content Management**
```
# Tasks
GET    /api/<guild_id>/tasks                    # List tasks
POST   /api/<guild_id>/tasks                    # Create task
PUT    /api/<guild_id>/tasks/<task_id>          # Update task
DELETE /api/<guild_id>/tasks/<task_id>          # Delete task

# Shop Items
GET    /api/<guild_id>/shop                     # List shop items
POST   /api/<guild_id>/shop                     # Create shop item
PUT    /api/<guild_id>/shop/<item_id>           # Update shop item
DELETE /api/<guild_id>/shop/<item_id>           # Delete shop item
PUT    /api/<guild_id>/shop/<item_id>/stock     # Update stock

# Announcements
GET    /api/<guild_id>/announcements            # List announcements
POST   /api/<guild_id>/announcements            # Create announcement
PUT    /api/<guild_id>/announcements/<id>       # Edit announcement
DELETE /api/<guild_id>/announcements/<id>       # Delete announcement

# Embeds
GET    /api/<guild_id>/embeds                   # List embeds
PUT    /api/<guild_id>/embeds/<embed_id>        # Update embed
DELETE /api/<guild_id>/embeds/<embed_id>        # Delete embed
```

### **User Management**
```
GET    /api/<guild_id>/users                    # List users with pagination
GET    /api/<guild_id>/users/<user_id>          # Get user details
PUT    /api/<guild_id>/users/<user_id>/balance  # Modify balance
POST   /api/<guild_id>/users/cleanup            # Cleanup inactive users
```

### **Transactions & Economy**
```
GET    /api/<guild_id>/transactions             # Get transaction history
GET    /api/<guild_id>/transactions/statistics  # Transaction statistics
POST   /api/<guild_id>/transactions/archive     # Archive old transactions
```

### **Audit & Monitoring**
```
GET    /api/<guild_id>/audit/logs               # Get audit logs
GET    /api/<guild_id>/audit/stats              # Audit statistics
POST   /api/<guild_id>/audit/export             # Export audit logs
```

### **Real-time Updates**
```
GET    /api/stream                              # Server-Sent Events
POST   /api/stream/test                         # Test SSE events
```

## 🔧 **Configuration**

### **Environment Variables**
```bash
# Required
DISCORD_TOKEN=your_bot_token
SUPABASE_URL=your_supabase_url
SUPABASE_SERVICE_ROLE_KEY=your_service_role_key
JWT_SECRET_KEY=your_jwt_secret

# Optional
ADMIN_USERNAME=admin
ADMIN_PASSWORD=admin
PORT=5000
DATA_DIR=data
```

### **Server Configuration**
Each Discord server can be configured through the web interface:
- **Prefix**: Bot command prefix
- **Currency**: Symbol and name
- **Channels**: Task, shop, announcement channels
- **Roles**: Admin and moderator roles
- **Features**: Enable/disable specific features
- **Moderation**: Content filtering settings

## 🧪 **Testing**

### **Running Tests**
```bash
# Run all tests
python tests/run_tests.py

# Run specific test file
pytest tests/test_sync_manager.py -v

# Run with coverage
pytest --cov=core --cov-report=html
```

### **Test Structure**
```
tests/
├── test_sync_manager.py     # SyncManager tests
├── test_auth_manager.py     # AuthManager tests
├── test_audit_manager.py    # AuditManager tests (future)
├── test_integration.py      # Integration tests (future)
├── run_tests.py            # Test runner script
└── __init__.py
```

## 🚀 **Deployment**

### **Railway Deployment**
1. **Set Environment Variables** in Railway dashboard
2. **Deploy**: Railway auto-deploys from GitHub
3. **Health Check**: Visit `/api/health` to verify deployment

### **Local Development**
```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
cp .env.example .env
# Edit .env with your values

# Run the application
python start.py
```

### **Docker Deployment**
```dockerfile
FROM python:3.9-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
EXPOSE 5000

CMD ["python", "start.py"]
```

## 🔒 **Security Features**

### **Authentication**
- JWT tokens with expiration
- Session-based authentication
- Secure password hashing
- Rate limiting on sensitive operations

### **Authorization**
- Role-based access control
- Command-level permissions
- Guild-specific permissions
- API endpoint protection

### **Data Protection**
- Input validation and sanitization
- SQL injection prevention
- XSS protection
- CSRF protection

### **Audit & Compliance**
- Complete audit trail
- Data integrity checks
- Export capabilities
- Retention policies

## 📊 **Monitoring & Health Checks**

### **Health Endpoints**
```
GET /api/health        # Comprehensive health check
GET /api/status        # Bot and system status
```

### **Metrics Tracked**
- System resource usage (CPU, memory, disk)
- Database connection health
- Bot connectivity status
- Active sync operations
- Error rates and performance

### **Logging**
- Structured logging with levels
- Performance monitoring
- Error tracking with context
- Audit event logging

## 🔄 **Synchronization Details**

### **Conflict Resolution Strategies**
1. **Last Modified**: Use most recent change
2. **CMS Wins**: Always prefer CMS changes
3. **Discord Wins**: Always prefer Discord changes
4. **Merge**: Attempt to merge changes
5. **Manual**: Require manual resolution

### **Sync Entities**
- **Tasks**: Creation, updates, completion, deletion
- **Shop Items**: Inventory, pricing, descriptions
- **Announcements**: Content, embeds, channels
- **Embeds**: Visual content and formatting
- **User Balances**: Currency transactions
- **Roles**: Permission updates
- **Channels**: Configuration changes

### **Real-time Broadcasting**
- Server-Sent Events (SSE) for live updates
- Selective subscriptions by guild and event type
- Batch processing for performance
- Automatic client cleanup

## 🛠️ **Development**

### **Project Structure**
```
├── backend.py              # Flask application
├── bot.py                  # Discord bot
├── core/                   # Core managers
│   ├── auth_manager.py     # Authentication
│   ├── audit_manager.py    # Audit logging
│   ├── sync_manager.py     # Synchronization
│   ├── data_manager.py     # Database operations
│   └── ...
├── cogs/                   # Discord cogs
├── web/                    # Frontend files
├── tests/                  # Test suite
└── docs/                   # Documentation
```

### **Adding New Features**
1. **Create Manager**: Add new manager in `core/`
2. **Update Backend**: Integrate in `backend.py`
3. **Add API Routes**: Create REST endpoints
4. **Update Sync**: Add to `SyncManager` if needed
5. **Add Tests**: Create comprehensive tests
6. **Update Docs**: Document new functionality

## 📈 **Performance Considerations**

### **Optimization Features**
- **Connection Pooling**: Efficient database connections
- **Caching**: Redis-based caching for frequently accessed data
- **Batch Processing**: Event batching for SSE
- **Lazy Loading**: On-demand resource loading
- **Background Tasks**: Async processing for heavy operations

### **Scalability**
- **Horizontal Scaling**: Stateless design
- **Database Sharding**: Guild-based data partitioning
- **CDN Integration**: Static asset delivery
- **Rate Limiting**: API protection and fair usage

## 🤝 **Contributing**

1. **Fork** the repository
2. **Create** a feature branch
3. **Write** comprehensive tests
4. **Implement** the feature
5. **Update** documentation
6. **Submit** a pull request

### **Code Standards**
- **Type Hints**: Use type annotations
- **Documentation**: Comprehensive docstrings
- **Testing**: 80%+ test coverage
- **Linting**: Follow PEP 8 standards

## 📄 **License**

This project is licensed under the MIT License - see the LICENSE file for details.

## 🆘 **Support**

- **Issues**: GitHub Issues for bug reports
- **Discussions**: GitHub Discussions for questions
- **Documentation**: Comprehensive in-code documentation

---

**Version**: 2.0.0
**Last Updated**: November 2025
**Maintainer**: Discord CMS Team
