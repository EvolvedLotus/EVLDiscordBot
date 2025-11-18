"""
Tests for the AuthManager authentication system
"""

import pytest
from unittest.mock import Mock, patch
from datetime import datetime, timedelta
import jwt

from core.auth_manager import AuthManager
from core.data_manager import DataManager


class TestAuthManager:
    """Test suite for AuthManager"""

    @pytest.fixture
    def mock_data_manager(self):
        """Mock data manager for testing"""
        dm = Mock(spec=DataManager)
        dm.admin_client = Mock()
        return dm

    @pytest.fixture
    def auth_manager(self, mock_data_manager):
        """Create AuthManager instance for testing"""
        return AuthManager(mock_data_manager, "test_secret_key")

    def test_generate_token(self, auth_manager):
        """Test JWT token generation"""
        payload = {"user_id": "123", "username": "testuser", "role": "admin"}

        token = auth_manager.generate_token(payload)

        assert token is not None
        assert isinstance(token, str)

        # Decode and verify
        decoded = jwt.decode(token, "test_secret_key", algorithms=["HS256"])
        assert decoded["user_id"] == "123"
        assert decoded["username"] == "testuser"
        assert decoded["role"] == "admin"

    def test_verify_token_valid(self, auth_manager):
        """Test verification of valid JWT token"""
        payload = {"user_id": "123", "username": "testuser", "role": "admin"}
        token = auth_manager.generate_token(payload)

        result = auth_manager.verify_token(token)

        assert result["valid"] == True
        assert result["payload"]["user_id"] == "123"
        assert result["payload"]["username"] == "testuser"
        assert result["payload"]["role"] == "admin"

    def test_verify_token_expired(self, auth_manager):
        """Test verification of expired JWT token"""
        # Create token that expires immediately
        payload = {"user_id": "123", "exp": datetime.utcnow() - timedelta(seconds=1)}
        token = jwt.encode(payload, "test_secret_key", algorithm="HS256")

        result = auth_manager.verify_token(token)

        assert result["valid"] == False
        assert result["error"] == "Token has expired"

    def test_verify_token_invalid(self, auth_manager):
        """Test verification of invalid JWT token"""
        result = auth_manager.verify_token("invalid.token.here")

        assert result["valid"] == False
        assert "error" in result

    def test_verify_token_wrong_secret(self, auth_manager):
        """Test verification with wrong secret key"""
        payload = {"user_id": "123"}
        token = jwt.encode(payload, "wrong_secret", algorithm="HS256")

        result = auth_manager.verify_token(token)

        assert result["valid"] == False
        assert "error" in result

    def test_authenticate_user_success(self, auth_manager):
        """Test successful user authentication"""
        with patch('core.auth_manager.os.getenv') as mock_getenv:
            mock_getenv.side_effect = lambda key: {
                'ADMIN_USERNAME': 'admin',
                'ADMIN_PASSWORD': 'hashed_password'
            }.get(key)

            with patch('core.auth_manager.hashlib.sha256') as mock_sha256:
                # Mock the hash function
                mock_hash = Mock()
                mock_hash.hexdigest.return_value = 'hashed_password'
                mock_sha256.return_value = mock_hash

                result = auth_manager.authenticate_user('admin', 'password')

                assert result is not None
                assert result['username'] == 'admin'
                assert result['role'] == 'admin'

    def test_authenticate_user_failure(self, auth_manager):
        """Test failed user authentication"""
        with patch('core.auth_manager.os.getenv') as mock_getenv:
            mock_getenv.side_effect = lambda key: {
                'ADMIN_USERNAME': 'admin',
                'ADMIN_PASSWORD': 'correct_hash'
            }.get(key)

            with patch('core.auth_manager.hashlib.sha256') as mock_sha256:
                # Mock different hashes
                mock_hash1 = Mock()
                mock_hash1.hexdigest.return_value = 'wrong_hash'
                mock_hash2 = Mock()
                mock_hash2.hexdigest.return_value = 'correct_hash'

                mock_sha256.side_effect = [mock_hash1, mock_hash2]

                result = auth_manager.authenticate_user('admin', 'wrong_password')

                assert result is None

    def test_create_session(self, auth_manager):
        """Test session creation"""
        user_data = {"username": "testuser", "role": "admin"}

        session_id = auth_manager.create_session(user_data)

        assert session_id is not None
        assert isinstance(session_id, str)
        assert len(session_id) == 64  # 32 bytes * 2 for hex

        # Verify session was stored
        assert session_id in auth_manager.sessions
        assert auth_manager.sessions[session_id]['user'] == user_data

    def test_get_session_valid(self, auth_manager):
        """Test retrieving valid session"""
        user_data = {"username": "testuser", "role": "admin"}
        session_id = auth_manager.create_session(user_data)

        session = auth_manager.get_session(session_id)

        assert session is not None
        assert session['user'] == user_data
        assert 'created_at' in session
        assert 'expires_at' in session

    def test_get_session_expired(self, auth_manager):
        """Test retrieving expired session"""
        user_data = {"username": "testuser", "role": "admin"}

        # Create session with immediate expiration
        session_id = "test_session_123"
        auth_manager.sessions[session_id] = {
            'user': user_data,
            'created_at': datetime.now() - timedelta(hours=2),
            'expires_at': datetime.now() - timedelta(hours=1)  # Already expired
        }

        session = auth_manager.get_session(session_id)

        assert session is None
        # Session should be cleaned up
        assert session_id not in auth_manager.sessions

    def test_get_session_not_found(self, auth_manager):
        """Test retrieving non-existent session"""
        session = auth_manager.get_session("non_existent_session")

        assert session is None

    def test_destroy_session(self, auth_manager):
        """Test session destruction"""
        user_data = {"username": "testuser", "role": "admin"}
        session_id = auth_manager.create_session(user_data)

        # Verify session exists
        assert session_id in auth_manager.sessions

        # Destroy session
        auth_manager.destroy_session(session_id)

        # Verify session is gone
        assert session_id not in auth_manager.sessions

    def test_cleanup_expired_sessions(self, auth_manager):
        """Test cleanup of expired sessions"""
        # Create valid session
        user_data = {"username": "testuser", "role": "admin"}
        valid_session_id = auth_manager.create_session(user_data)

        # Create expired session manually
        expired_session_id = "expired_session_123"
        auth_manager.sessions[expired_session_id] = {
            'user': user_data,
            'created_at': datetime.now() - timedelta(hours=2),
            'expires_at': datetime.now() - timedelta(hours=1)
        }

        # Run cleanup
        auth_manager.cleanup_expired_sessions()

        # Valid session should remain
        assert valid_session_id in auth_manager.sessions
        # Expired session should be removed
        assert expired_session_id not in auth_manager.sessions

    def test_get_active_sessions_count(self, auth_manager):
        """Test getting count of active sessions"""
        # Create some sessions
        user_data = {"username": "testuser", "role": "admin"}
        session1 = auth_manager.create_session(user_data)
        session2 = auth_manager.create_session(user_data)

        # Create expired session
        expired_session_id = "expired_session_123"
        auth_manager.sessions[expired_session_id] = {
            'user': user_data,
            'created_at': datetime.now() - timedelta(hours=2),
            'expires_at': datetime.now() - timedelta(hours=1)
        }

        count = auth_manager.get_active_sessions_count()

        assert count == 2  # Only valid sessions count

    def test_validate_session_token_valid(self, auth_manager):
        """Test session token validation with valid token"""
        user_data = {"username": "testuser", "role": "admin"}
        session_id = auth_manager.create_session(user_data)

        result = auth_manager.validate_session_token(session_id)

        assert result["valid"] == True
        assert result["user"] == user_data

    def test_validate_session_token_invalid(self, auth_manager):
        """Test session token validation with invalid token"""
        result = auth_manager.validate_session_token("invalid_session_id")

        assert result["valid"] == False
        assert result["error"] == "Session not found or expired"

    def test_refresh_token_valid(self, auth_manager):
        """Test token refresh with valid token"""
        payload = {"user_id": "123", "username": "testuser", "role": "admin"}
        token = auth_manager.generate_token(payload)

        new_token = auth_manager.refresh_token(token)

        assert new_token is not None
        assert new_token != token  # Should be a new token

        # Verify new token is valid
        decoded = jwt.decode(new_token, "test_secret_key", algorithms=["HS256"])
        assert decoded["user_id"] == "123"

    def test_refresh_token_invalid(self, auth_manager):
        """Test token refresh with invalid token"""
        new_token = auth_manager.refresh_token("invalid.token.here")

        assert new_token is None

    def test_get_user_permissions(self, auth_manager):
        """Test getting user permissions"""
        user_data = {"username": "testuser", "role": "admin"}

        permissions = auth_manager.get_user_permissions(user_data)

        assert permissions is not None
        assert isinstance(permissions, dict)
        assert "role" in permissions
        assert permissions["role"] == "admin"

    def test_is_admin_user(self, auth_manager):
        """Test admin user check"""
        admin_user = {"username": "admin", "role": "admin"}
        regular_user = {"username": "user", "role": "user"}

        assert auth_manager.is_admin_user(admin_user) == True
        assert auth_manager.is_admin_user(regular_user) == False

    def test_is_moderator_user(self, auth_manager):
        """Test moderator user check"""
        admin_user = {"username": "admin", "role": "admin"}
        mod_user = {"username": "mod", "role": "moderator"}
        regular_user = {"username": "user", "role": "user"}

        assert auth_manager.is_moderator_user(admin_user) == True  # Admins are mods
        assert auth_manager.is_moderator_user(mod_user) == True
        assert auth_manager.is_moderator_user(regular_user) == False

    def test_log_auth_event(self, auth_manager):
        """Test authentication event logging"""
        user_data = {"username": "testuser", "role": "admin"}

        auth_manager.log_auth_event("login", user_data, "127.0.0.1")

        # Verify audit manager was called
        auth_manager.audit_manager.log_event.assert_called_once()

    def test_get_auth_stats(self, auth_manager):
        """Test getting authentication statistics"""
        # Create some sessions
        user_data = {"username": "testuser", "role": "admin"}
        auth_manager.create_session(user_data)
        auth_manager.create_session(user_data)

        stats = auth_manager.get_auth_stats()

        assert stats["active_sessions"] == 2
        assert "total_logins" in stats
        assert "failed_attempts" in stats
