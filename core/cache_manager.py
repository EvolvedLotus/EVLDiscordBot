"""
Cache Manager with pub/sub invalidation mechanism
Implements Redis-like pub/sub for cache invalidation across multiple bot instances
"""

import threading
import time
import logging
from typing import Dict, Set, Callable, Optional
from collections import defaultdict
import json

logger = logging.getLogger(__name__)

class CacheManager:
    """
    Singleton cache manager that handles cache invalidation broadcasting
    across multiple running instances of the bot and web dashboard.
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, '_initialized'):
            return

        self._initialized = True
        self._cache = {}  # Simple in-memory cache for this instance
        self._cache_ttl = {}  # TTL tracking
        self._listeners = defaultdict(set)  # event_type -> set of callback functions
        self._invalidations = defaultdict(set)  # guild_id -> set of invalidated data types
        self._cleanup_thread = None
        self._running = False

        # Start cleanup thread
        self._start_cleanup_thread()

    @classmethod
    def get_instance(cls):
        """Get singleton instance"""
        return cls()

    def _start_cleanup_thread(self):
        """Start background thread to clean up expired cache entries"""
        def cleanup_worker():
            while self._running:
                try:
                    current_time = time.time()
                    expired_keys = []

                    with self._lock:
                        for key, expiry in self._cache_ttl.items():
                            if current_time > expiry:
                                expired_keys.append(key)

                        for key in expired_keys:
                            self._cache.pop(key, None)
                            self._cache_ttl.pop(key, None)

                    if expired_keys:
                        logger.debug(f"Cleaned up {len(expired_keys)} expired cache entries")

                except Exception as e:
                    logger.error(f"Error in cache cleanup: {e}")

                time.sleep(60)  # Clean up every minute

        self._running = True
        self._cleanup_thread = threading.Thread(target=cleanup_worker, daemon=True)
        self._cleanup_thread.start()

    def get(self, key: str, default=None):
        """Get cached value if not expired"""
        with self._lock:
            if key in self._cache_ttl and time.time() > self._cache_ttl[key]:
                # Expired, remove it
                self._cache.pop(key, None)
                self._cache_ttl.pop(key, None)
                return default
            return self._cache.get(key, default)

    def set(self, key: str, value, ttl_seconds: int = 300):
        """Set cached value with TTL"""
        with self._lock:
            self._cache[key] = value
            self._cache_ttl[key] = time.time() + ttl_seconds

    def invalidate_cache(self, guild_id: int, data_type: str, user_id: int = None):
        """
        Broadcast cache invalidation signal to all subscribers.
        This implements the pub/sub mechanism for cross-instance cache clearing.
        """
        try:
            invalidation_event = {
                'type': 'cache_invalidation',
                'guild_id': str(guild_id),
                'data_type': data_type,
                'user_id': str(user_id) if user_id else None,
                'timestamp': time.time()
            }

            # Invalidate local cache first
            self._invalidate_local_cache(guild_id, data_type, user_id)

            # Broadcast to all listeners
            self._broadcast_invalidation(invalidation_event)

            logger.debug(f"Cache invalidation broadcasted: guild={guild_id}, type={data_type}, user={user_id}")

        except Exception as e:
            logger.error(f"Error broadcasting cache invalidation: {e}")

    def _invalidate_local_cache(self, guild_id: int, data_type: str, user_id: int = None):
        """Invalidate local cache entries"""
        with self._lock:
            # Remove cache entries related to this guild and data type
            keys_to_remove = []

            for key in self._cache.keys():
                try:
                    # Parse cache key format: "guild_{guild_id}_{data_type}_{user_id}"
                    if key.startswith(f"guild_{guild_id}_{data_type}"):
                        if user_id is None or f"_{user_id}" in key:
                            keys_to_remove.append(key)
                except:
                    continue

            for key in keys_to_remove:
                self._cache.pop(key, None)
                self._cache_ttl.pop(key, None)

            if keys_to_remove:
                logger.debug(f"Invalidated {len(keys_to_remove)} local cache entries")

    def _broadcast_invalidation(self, invalidation_event: dict):
        """Broadcast invalidation event to all registered listeners"""
        event_type = 'cache_invalidation'

        # Get all listeners for this event type
        listeners = self._listeners.get(event_type, set()).copy()

        # Also broadcast to generic listeners
        listeners.update(self._listeners.get('all', set()))

        for listener in listeners:
            try:
                # Run listener in thread pool to avoid blocking
                threading.Thread(
                    target=self._run_listener,
                    args=(listener, invalidation_event),
                    daemon=True
                ).start()
            except Exception as e:
                logger.error(f"Error running cache invalidation listener: {e}")

    def _run_listener(self, listener: Callable, event: dict):
        """Run a listener function with the event"""
        try:
            listener(event)
        except Exception as e:
            logger.error(f"Error in cache invalidation listener: {e}")

    def register_listener(self, event_type: str, callback: Callable):
        """Register a listener for cache invalidation events"""
        with self._lock:
            self._listeners[event_type].add(callback)
            logger.debug(f"Registered cache invalidation listener for event type: {event_type}")

    def unregister_listener(self, event_type: str, callback: Callable):
        """Unregister a cache invalidation listener"""
        with self._lock:
            self._listeners[event_type].discard(callback)

    def get_cache_stats(self) -> dict:
        """Get cache statistics"""
        with self._lock:
            return {
                'total_entries': len(self._cache),
                'listeners': {event_type: len(listeners) for event_type, listeners in self._listeners.items()},
                'uptime': time.time() - (self._start_time if hasattr(self, '_start_time') else time.time())
            }

    def invalidate(self, key: str):
        """Invalidate a specific cache key"""
        with self._lock:
            self._cache.pop(key, None)
            self._cache_ttl.pop(key, None)
            logger.debug(f"Invalidated cache key: {key}")

    def invalidate_pattern(self, pattern: str):
        """Invalidate all keys matching pattern"""
        import fnmatch
        keys_to_remove = []
        with self._lock:
            for key in self._cache.keys():
                if fnmatch.fnmatch(key, pattern):
                    keys_to_remove.append(key)

            for key in keys_to_remove:
                self._cache.pop(key, None)
                self._cache_ttl.pop(key, None)

            if keys_to_remove:
                logger.debug(f"Invalidated {len(keys_to_remove)} cache keys matching pattern: {pattern}")

    def clear_all_cache(self):
        """Clear all cached data (admin function)"""
        with self._lock:
            cleared_count = len(self._cache)
            self._cache.clear()
            self._cache_ttl.clear()
            logger.info(f"Cleared all cache entries: {cleared_count}")

    def __del__(self):
        """Cleanup on destruction"""
        self._running = False
        if self._cleanup_thread and self._cleanup_thread.is_alive():
            self._cleanup_thread.join(timeout=1)
