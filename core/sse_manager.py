"""
Server-Sent Events Manager for real-time updates
Handles SSE connections and event broadcasting between bot and web dashboard
"""

import asyncio
import json
import logging
import threading
import time
from typing import Dict, List, Set, Callable, Any, Optional
from datetime import datetime
import queue

logger = logging.getLogger(__name__)

class SSEManager:
    """Manages Server-Sent Events for real-time web dashboard updates"""

    def __init__(self):
        self.clients: Dict[str, Set] = {}  # client_id -> set of subscriptions
        self.client_queues: Dict[str, asyncio.Queue] = {}  # client_id -> event queue
        self.client_metadata: Dict[str, Dict] = {}  # client_id -> metadata
        self.subscriptions: Dict[str, Set[str]] = {}  # event_type -> set of client_ids
        self.event_handlers: Dict[str, List[Callable]] = {}  # event_type -> list of handlers

        # Threading and async management
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self._running = False
        self._shutdown_event = threading.Event()

        # Performance monitoring
        self.stats = {
            'total_clients': 0,
            'total_events_sent': 0,
            'total_events_dropped': 0,
            'uptime': 0,
            'start_time': time.time()
        }

        # Cleanup settings
        self.client_timeout = 300  # 5 minutes
        self.max_queue_size = 100
        self.cleanup_interval = 60  # 1 minute

        logger.info("SSE Manager initialized")

    def set_event_loop(self, loop: asyncio.AbstractEventLoop):
        """Set the asyncio event loop for async operations"""
        self.loop = loop
        logger.info("Event loop set for SSE Manager")

    def start(self):
        """Start the SSE manager"""
        if self._running:
            return

        self._running = True
        self._shutdown_event.clear()

        # Start cleanup thread
        cleanup_thread = threading.Thread(target=self._cleanup_worker, daemon=True)
        cleanup_thread.start()

        logger.info("SSE Manager started")

    def stop(self):
        """Stop the SSE manager"""
        if not self._running:
            return

        self._running = False
        self._shutdown_event.set()

        # Disconnect all clients
        for client_id in list(self.clients.keys()):
            self._disconnect_client(client_id)

        logger.info("SSE Manager stopped")

    def register_client(self, client_id: str, subscriptions: List[str] = None, metadata: Dict = None) -> bool:
        """Register a new SSE client"""
        try:
            if client_id in self.clients:
                logger.warning(f"Client {client_id} already registered, reconnecting")
                self._disconnect_client(client_id)

            self.clients[client_id] = set(subscriptions or [])
            self.client_queues[client_id] = asyncio.Queue(maxsize=self.max_queue_size)
            self.client_metadata[client_id] = {
                'connected_at': time.time(),
                'last_activity': time.time(),
                'subscriptions': subscriptions or [],
                'user_agent': metadata.get('user_agent', 'Unknown') if metadata else 'Unknown',
                'ip': metadata.get('ip', 'Unknown') if metadata else 'Unknown',
                **(metadata or {})
            }

            # Register subscriptions
            for event_type in (subscriptions or []):
                if event_type not in self.subscriptions:
                    self.subscriptions[event_type] = set()
                self.subscriptions[event_type].add(client_id)

            self.stats['total_clients'] += 1
            logger.info(f"Client {client_id} registered with subscriptions: {subscriptions}")
            return True

        except Exception as e:
            logger.error(f"Failed to register client {client_id}: {e}")
            return False

    def unregister_client(self, client_id: str):
        """Unregister an SSE client"""
        if client_id not in self.clients:
            return

        self._disconnect_client(client_id)
        logger.info(f"Client {client_id} unregistered")

    def _disconnect_client(self, client_id: str):
        """Internal method to disconnect a client"""
        if client_id in self.clients:
            # Remove from subscriptions
            for event_type, clients in self.subscriptions.items():
                clients.discard(client_id)

            # Clean up client data
            del self.clients[client_id]
            del self.client_queues[client_id]
            del self.client_metadata[client_id]

    def update_subscriptions(self, client_id: str, subscriptions: List[str]) -> bool:
        """Update client subscriptions"""
        if client_id not in self.clients:
            return False

        try:
            # Remove from old subscriptions
            old_subs = self.clients[client_id].copy()
            for event_type in old_subs:
                if event_type in self.subscriptions:
                    self.subscriptions[event_type].discard(client_id)

            # Add to new subscriptions
            self.clients[client_id] = set(subscriptions)
            for event_type in subscriptions:
                if event_type not in self.subscriptions:
                    self.subscriptions[event_type] = set()
                self.subscriptions[event_type].add(client_id)

            # Update metadata
            self.client_metadata[client_id]['subscriptions'] = subscriptions
            self.client_metadata[client_id]['last_activity'] = time.time()

            logger.debug(f"Updated subscriptions for client {client_id}: {subscriptions}")
            return True

        except Exception as e:
            logger.error(f"Failed to update subscriptions for client {client_id}: {e}")
            return False

    def broadcast_event(self, event_type: str, data: Dict[str, Any], target_guild: str = None):
        """Broadcast an event to all subscribed clients"""
        try:
            # Create event payload
            event_data = {
                'type': event_type,
                'data': data,
                'timestamp': datetime.utcnow().isoformat() + 'Z',
                'guild_id': target_guild
            }

            # Filter clients by subscription and guild if specified
            target_clients = set()

            if event_type in self.subscriptions:
                target_clients.update(self.subscriptions[event_type])

            # If guild-specific, also check for guild-specific subscriptions
            if target_guild:
                guild_event_type = f"guild:{target_guild}:{event_type}"
                if guild_event_type in self.subscriptions:
                    target_clients.update(self.subscriptions[guild_event_type])

            if not target_clients:
                logger.debug(f"No clients subscribed to event type: {event_type}")
                return

            # Send to each client
            sent_count = 0
            for client_id in target_clients:
                if client_id in self.client_queues:
                    try:
                        # Use thread-safe approach for async queues
                        if self.loop and self.loop.is_running():
                            # Schedule async put using run_coroutine_threadsafe
                            future = asyncio.run_coroutine_threadsafe(
                                self._put_event_async(client_id, event_data),
                                self.loop
                            )
                            # Don't wait for completion to avoid blocking
                        else:
                            # Fallback: try direct put (may block briefly)
                            try:
                                self.client_queues[client_id].put_nowait(event_data)
                            except asyncio.QueueFull:
                                # If queue is full, remove oldest item and try again
                                try:
                                    self.client_queues[client_id].get_nowait()
                                    self.client_queues[client_id].put_nowait(event_data)
                                except asyncio.QueueEmpty:
                                    pass  # Queue became empty, item was lost

                        sent_count += 1
                        self.client_metadata[client_id]['last_activity'] = time.time()

                    except Exception as e:
                        logger.error(f"Failed to send event to client {client_id}: {e}")
                        self.stats['total_events_dropped'] += 1

            self.stats['total_events_sent'] += sent_count

            # Trigger event handlers synchronously (don't block event broadcasting)
            try:
                self._trigger_handlers(event_type, event_data)
            except Exception as e:
                logger.error(f"Error in event handlers for {event_type}: {e}")

            logger.debug(f"Broadcasted {event_type} event to {sent_count} clients")

        except Exception as e:
            logger.error(f"Failed to broadcast event {event_type}: {e}")

    async def _put_event_async(self, client_id: str, event_data: Dict):
        """Async helper to put event in client queue"""
        try:
            await self.client_queues[client_id].put(event_data)
        except asyncio.QueueFull:
            logger.warning(f"Async queue full for client {client_id}")
            raise

    def get_client_events(self, client_id: str) -> Optional[asyncio.Queue]:
        """Get the event queue for a client"""
        return self.client_queues.get(client_id)

    def register_event_handler(self, event_type: str, handler: Callable):
        """Register an event handler function"""
        if event_type not in self.event_handlers:
            self.event_handlers[event_type] = []
        self.event_handlers[event_type].append(handler)
        logger.info(f"Registered event handler for {event_type}")

    def _trigger_handlers(self, event_type: str, event_data: Dict):
        """Trigger registered event handlers"""
        if event_type in self.event_handlers:
            for handler in self.event_handlers[event_type]:
                try:
                    if asyncio.iscoroutinefunction(handler):
                        if self.loop and self.loop.is_running():
                            asyncio.run_coroutine_threadsafe(handler(event_data), self.loop)
                        else:
                            logger.warning(f"Cannot run async handler {handler} without event loop")
                    else:
                        handler(event_data)
                except Exception as e:
                    logger.error(f"Error in event handler {handler}: {e}")

    def get_stats(self) -> Dict[str, Any]:
        """Get SSE manager statistics"""
        self.stats['uptime'] = time.time() - self.stats['start_time']
        self.stats['active_clients'] = len(self.clients)

        # Calculate rates
        if self.stats['uptime'] > 0:
            self.stats['events_per_second'] = self.stats['total_events_sent'] / self.stats['uptime']
        else:
            self.stats['events_per_second'] = 0

        return self.stats.copy()

    def get_client_info(self, client_id: str = None) -> Dict[str, Any]:
        """Get information about clients"""
        if client_id:
            if client_id not in self.clients:
                return {}
            return {
                'client_id': client_id,
                'subscriptions': list(self.clients[client_id]),
                'metadata': self.client_metadata.get(client_id, {}),
                'queue_size': self.client_queues[client_id].qsize() if client_id in self.client_queues else 0
            }
        else:
            return {
                'total_clients': len(self.clients),
                'clients': [
                    {
                        'client_id': cid,
                        'subscriptions': list(self.clients[cid]),
                        'queue_size': self.client_queues[cid].qsize(),
                        'connected_at': self.client_metadata[cid]['connected_at']
                    }
                    for cid in self.clients
                ]
            }

    def _cleanup_worker(self):
        """Background thread for cleaning up inactive clients"""
        while not self._shutdown_event.is_set():
            try:
                self._cleanup_inactive_clients()
                self._shutdown_event.wait(self.cleanup_interval)
            except Exception as e:
                logger.error(f"Error in cleanup worker: {e}")
                time.sleep(5)  # Brief pause on error

    def _cleanup_inactive_clients(self):
        """Clean up clients that haven't been active"""
        current_time = time.time()
        to_remove = []

        for client_id, metadata in self.client_metadata.items():
            last_activity = metadata.get('last_activity', 0)
            if current_time - last_activity > self.client_timeout:
                to_remove.append(client_id)

        for client_id in to_remove:
            logger.info(f"Cleaning up inactive client: {client_id}")
            self._disconnect_client(client_id)

        if to_remove:
            logger.info(f"Cleaned up {len(to_remove)} inactive clients")

# Global SSE manager instance
sse_manager = SSEManager()
