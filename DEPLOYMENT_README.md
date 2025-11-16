# 🚀 Deployment Guide

This guide explains how to deploy the Discord Task Bot to Railway (backend) and Netlify (frontend).

## 📋 Prerequisites

1. **Railway Account**: https://railway.app
2. **Netlify Account**: https://netlify.com
3. **Supabase Account**: https://supabase.com (for database)
4. **Discord Bot Token**: From https://discord.com/developers/applications

## 🔧 Environment Variables Setup

### Railway (Backend) Configuration

In your Railway project, set these environment variables:

```bash
# Discord Bot Token (Required)
DISCORD_TOKEN=your_discord_bot_token_here

# Flask Configuration
FLASK_ENV=production
ENVIRONMENT=production
DATA_DIR=data

# CMS Admin Credentials (Change these!)
ADMIN_USERNAME=admin
ADMIN_PASSWORD=your_secure_admin_password_here

# JWT Configuration (Generate a secure key)
JWT_SECRET_KEY=your_secure_jwt_secret_key_here

# Supabase Configuration (Required)
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your_supabase_anon_key
SUPABASE_SERVICE_ROLE_KEY=your_supabase_service_role_key

# Railway specific
PORT=8080
```

### Netlify (Frontend) Configuration

In your Netlify site settings, set these build environment variables:

```bash
# API Base URL (points to your Railway backend)
API_BASE_URL=https://your-railway-app.railway.app
```

## 🗄️ Database Setup (Supabase)

1. Create a new Supabase project
2. Go to the SQL Editor
3. Run the `schema.sql` file to create all tables
4. Copy the project URL and API keys from Settings > API

## 🚀 Deployment Steps

### 1. Deploy Backend to Railway

1. Connect your GitHub repository to Railway
2. Set the environment variables listed above
3. Set the start command to: `python railway_start.py`
4. Deploy

### 2. Deploy Frontend to Netlify

1. Connect your GitHub repository to Netlify
2. Set the build command to: (leave empty)
3. Set the publish directory to: `.`
4. Set the API_BASE_URL environment variable
5. Deploy

## 🔐 Security Notes

- **Never commit secrets** to your repository
- **Generate new JWT keys** for production
- **Use strong passwords** for admin accounts
- **Keep API keys secure** and rotate them regularly

## 🔄 Updating Environment Variables

### Railway
- Go to your Railway project dashboard
- Navigate to Variables in the left sidebar
- Update the values and redeploy

### Netlify
- Go to your Netlify site dashboard
- Navigate to Site settings > Environment variables
- Update the values and trigger a new deploy

## 🧪 Testing Deployment

1. **Backend**: Visit `https://your-railway-app.railway.app/api/status`
2. **Frontend**: Visit your Netlify URL and try logging in
3. **Bot**: Check if the bot is online in your Discord server

## 🐛 Troubleshooting

### Common Issues:

1. **Bot not starting**: Check Railway logs for errors
2. **Login not working**: Verify JWT_SECRET_KEY is set
3. **Database errors**: Check Supabase connection and schema
4. **Frontend not loading**: Check API_BASE_URL is correct

### Logs:
- Railway: Check deployment logs in the Railway dashboard
- Netlify: Check deploy logs in the Netlify dashboard
