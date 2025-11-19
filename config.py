"""
Configuration management for Task Bot Discord
Centralized configuration with environment variable loading
"""

import os
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class Config:
    """Centralized configuration management"""

    def __init__(self):
        # Load environment variables
        self._load_environment()

        # Validate critical configuration
        self._validate_config()

    def _load_environment(self):
        """Load all environment variables"""

        # Discord Configuration
        self.discord_token = os.getenv('DISCORD_TOKEN')
        self.discord_client_id = os.getenv('DISCORD_CLIENT_ID')
        self.discord_client_secret = os.getenv('DISCORD_CLIENT_SECRET')

        # Database Configuration
        self.supabase_url = os.getenv('SUPABASE_URL')
        self.supabase_anon_key = os.getenv('SUPABASE_ANON_KEY')
        self.supabase_service_role_key = os.getenv('SUPABASE_SERVICE_ROLE_KEY')

        # AI Configuration
        self.gemini_api_key = os.getenv('GEMINI_API_KEY')

        # Authentication
        self.jwt_secret_key = os.getenv('JWT_SECRET_KEY', 'dev-secret-key-change-me')

        # Server Configuration
        self.port = int(os.getenv('PORT', '5000'))
        self.host = os.getenv('HOST', '0.0.0.0')
        self.environment = os.getenv('ENVIRONMENT', 'development')
        self.debug = self.environment == 'development'

        # Internal Communication
        self.bot_webhook_port = int(os.getenv('BOT_WEBHOOK_PORT', '5001'))
        self.bot_webhook_host = os.getenv('BOT_WEBHOOK_HOST', 'localhost')

        # CORS Configuration
        self.allowed_origins = self._parse_allowed_origins()

        # Feature Flags
        self.enable_ai_chat = os.getenv('ENABLE_AI_CHAT', 'true').lower() == 'true'
        self.enable_moderation = os.getenv('ENABLE_MODERATION', 'true').lower() == 'true'

        # Performance Settings
        self.max_connections = int(os.getenv('MAX_CONNECTIONS', '20'))
        self.connection_timeout = int(os.getenv('CONNECTION_TIMEOUT', '30'))

        # Cache Settings
        self.cache_ttl = int(os.getenv('CACHE_TTL', '300'))
        self.max_cache_size = int(os.getenv('MAX_CACHE_SIZE', '1000'))

        # Logging
        self.log_level = os.getenv('LOG_LEVEL', 'INFO').upper()

    def _parse_allowed_origins(self) -> list:
        """Parse allowed CORS origins from environment"""
        origins_env = os.getenv('ALLOWED_ORIGINS', '')

        if origins_env:
            origins = [origin.strip() for origin in origins_env.split(',') if origin.strip()]
            if origins:
                return origins

        # Default origins based on environment
        if self.environment == 'production':
            return [
                'https://evolvedlotus.github.io',
                'https://evolvedlotus.github.io/EVLDiscordBot',
            ]
        else:
            return [
                'http://localhost:3000',
                'http://localhost:5000',
                'http://127.0.0.1:3000',
                'http://127.0.0.1:5000',
                'https://evolvedlotus.github.io',
            ]

    def _validate_config(self):
        """Validate critical configuration values"""

        required_vars = {
            'DISCORD_TOKEN': self.discord_token,
            'SUPABASE_URL': self.supabase_url,
            'SUPABASE_ANON_KEY': self.supabase_anon_key,
            'SUPABASE_SERVICE_ROLE_KEY': self.supabase_service_role_key,
            'JWT_SECRET_KEY': self.jwt_secret_key,
        }

        # Only require Gemini API key if AI is enabled
        if self.enable_ai_chat:
            required_vars['GEMINI_API_KEY'] = self.gemini_api_key

        missing = []
        for var_name, value in required_vars.items():
            if not value:
                missing.append(var_name)

        if missing:
            error_msg = f"Missing required environment variables: {', '.join(missing)}"
            logger.error(error_msg)
            raise ValueError(error_msg)

        logger.info("✅ Configuration validation passed")

    def get_database_config(self) -> Dict[str, Any]:
        """Get database configuration"""
        return {
            'url': self.supabase_url,
            'anon_key': self.supabase_anon_key,
            'service_key': self.supabase_service_role_key,
            'max_connections': self.max_connections,
            'timeout': self.connection_timeout,
        }

    def get_bot_config(self) -> Dict[str, Any]:
        """Get bot configuration"""
        return {
            'token': self.discord_token,
            'webhook_port': self.bot_webhook_port,
            'webhook_host': self.bot_webhook_host,
            'command_prefix': '!',
        }

    def get_flask_config(self) -> Dict[str, Any]:
        """Get Flask configuration"""
        return {
            'host': self.host,
            'port': self.port,
            'debug': self.debug,
            'secret_key': self.jwt_secret_key,
            'cors_origins': self.allowed_origins,
        }

    def get_ai_config(self) -> Dict[str, Any]:
        """Get AI configuration"""
        return {
            'api_key': self.gemini_api_key,
            'enabled': self.enable_ai_chat,
            'model': 'gemini-pro',
        }

    def is_production(self) -> bool:
        """Check if running in production"""
        return self.environment == 'production'

    def get_internal_webhook_url(self, endpoint: str = '') -> str:
        """Get internal webhook URL for bot communication"""
        base_url = f"http://{self.bot_webhook_host}:{self.bot_webhook_port}"
        return f"{base_url}/{endpoint.lstrip('/')}"

# Global configuration instance
config = Config()
