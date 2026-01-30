"""
AD CLAIM MANAGER
Handles Monetag ad viewing and reward distribution for the permanent global task
"""

import logging
import secrets
import hashlib
import random
from core.evolved_lotus_api import evolved_lotus_api
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class AdClaimManager:
    """Manages ad viewing sessions and reward distribution"""
    
    def __init__(self, data_manager, transaction_manager):
        self.data_manager = data_manager
        self.transaction_manager = transaction_manager
        logger.info("✅ AdClaimManager initialized")
    
    def create_ad_session(self, user_id: str, guild_id: str, ip_address: str = None, user_agent: str = None) -> Dict:
        """
        Create a new ad viewing session for a user
        
        Args:
            user_id: Discord user ID
            guild_id: Discord guild ID
            ip_address: User's IP address (optional, for fraud prevention)
            user_agent: User's browser user agent (optional)
        
        Returns:
            Dict with session_id and viewer_url
        """
        try:
            # Enforce limits (rate limit, daily limit)
            self._check_ad_limits(user_id)

            # Generate unique session ID
            session_id = self._generate_session_id(user_id, guild_id)
            
            # Decide ad type (60/40 rotation between Custom EvolvedLotus ads and Monetag)
            ad_type = 'monetag_interstitial'
            custom_ad = None
            
            if random.random() < 0.6:  # 60% chance for Custom Ad (increased from 50%)
                custom_ad = evolved_lotus_api.get_random_ad(client_id='discord-task', include_rotating_blog=True)
                ad_type = 'custom_promo'
                logger.info(f"Selected custom ad {custom_ad.get('id')} for session {session_id}")

            # Create ad view record
            result = self.data_manager.admin_client.table('ad_views').insert({
                'user_id': user_id,
                'guild_id': guild_id,
                'ad_session_id': session_id,
                'ad_type': ad_type,
                'is_verified': False,
                'reward_amount': 10,
                'reward_granted': False,
                'ip_address': ip_address,
                'user_agent': user_agent,
                'metadata': {
                    'created_via': 'api',
                    'timestamp': datetime.now(timezone.utc).isoformat(),
                    'custom_ad': custom_ad
                }
            }).execute()
            
            if not result.data:
                raise Exception("Failed to create ad session")
            
            # Create global task claim record
            self.data_manager.admin_client.table('global_task_claims').insert({
                'user_id': user_id,
                'guild_id': guild_id,
                'task_key': 'ad_claim_task',
                'ad_session_id': session_id,
                'reward_amount': 10,
                'reward_granted': False
            }).execute()
            
            logger.info(f"Created ad session {session_id} for user {user_id} in guild {guild_id}")
            
            return {
                'success': True,
                'session_id': session_id,
                'viewer_url': f'/ad-viewer?session={session_id}',
                'reward': 10
            }
            
        except Exception as e:
            logger.error(f"Error creating ad session: {e}")
            raise
    
    def verify_ad_view(self, session_id: str, verification_data: Dict = None) -> Dict:
        """
        Verify that an ad was viewed and grant reward
        
        Args:
            session_id: The ad session ID
            verification_data: Optional verification data from Monetag postback
        
        Returns:
            Dict with verification status and reward info
        """
        try:
            # Get ad view record
            result = self.data_manager.admin_client.table('ad_views') \
                .select('*') \
                .eq('ad_session_id', session_id) \
                .execute()
            
            if not result.data or len(result.data) == 0:
                return {
                    'success': False,
                    'error': 'Invalid session ID'
                }
            
            ad_view = result.data[0]
            
            # Check if already verified
            if ad_view['is_verified']:
                return {
                    'success': False,
                    'error': 'Ad already verified',
                    'already_rewarded': True
                }
            
            # Mark as verified
            self.data_manager.admin_client.table('ad_views') \
                .update({
                    'is_verified': True,
                    'verified_at': datetime.now(timezone.utc).isoformat(),
                    'metadata': {
                        **ad_view.get('metadata', {}),
                        'verification_data': verification_data or {},
                        'verified_timestamp': datetime.now(timezone.utc).isoformat()
                    }
                }) \
                .eq('ad_session_id', session_id) \
                .execute()
            
            # Grant reward
            reward_result = self._grant_reward(
                ad_view['user_id'],
                ad_view['guild_id'],
                session_id,
                ad_view['reward_amount']
            )
            
            return {
                'success': True,
                'verified': True,
                'reward_granted': reward_result['success'],
                'reward_amount': ad_view['reward_amount'],
                'new_balance': reward_result.get('new_balance'),
                'transaction_id': reward_result.get('transaction_id')
            }
            
        except Exception as e:
            logger.error(f"Error verifying ad view: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def _grant_reward(self, user_id: str, guild_id: str, session_id: str, amount: int) -> Dict:
        """
        Grant currency reward to user for watching ad
        
        Args:
            user_id: Discord user ID
            guild_id: Discord guild ID
            session_id: Ad session ID
            amount: Reward amount
        
        Returns:
            Dict with reward status
        """
        try:
            # Use transaction manager to adjust balance
            transaction = self.transaction_manager.adjust_balance(
                user_id=int(user_id),
                guild_id=int(guild_id),
                amount=amount,
                reason=f"Watched ad - Session {session_id[:8]}"
            )
            
            # Check if transaction was created successfully (has an 'id' field)
            if transaction and transaction.get('id'):
                # Update ad_views record
                self.data_manager.admin_client.table('ad_views') \
                    .update({
                        'reward_granted': True,
                        'transaction_id': transaction.get('id')
                    }) \
                    .eq('ad_session_id', session_id) \
                    .execute()
                
                # Update global_task_claims record
                self.data_manager.admin_client.table('global_task_claims') \
                    .update({
                        'reward_granted': True,
                        'completed_at': datetime.now(timezone.utc).isoformat()
                    }) \
                    .eq('ad_session_id', session_id) \
                    .execute()
                
                logger.info(f"Granted {amount} currency to user {user_id} for ad view {session_id}")
                
                return {
                    'success': True,
                    'new_balance': transaction.get('balance_after'),
                    'transaction_id': transaction.get('id')
                }
            else:
                logger.error(f"Transaction failed for ad reward: {transaction}")
                return {
                    'success': False,
                    'error': 'Failed to create transaction'
                }
            
        except Exception as e:
            logger.error(f"Error granting reward: {e}", exc_info=True)
            return {
                'success': False,
                'error': str(e)
            }
    
    def get_user_ad_stats(self, user_id: str, guild_id: str = None) -> Dict:
        """
        Get ad viewing statistics for a user
        
        Args:
            user_id: Discord user ID
            guild_id: Optional guild ID to filter by
        
        Returns:
            Dict with ad statistics
        """
        try:
            query = self.data_manager.admin_client.table('ad_views') \
                .select('*') \
                .eq('user_id', user_id)
            
            if guild_id:
                query = query.eq('guild_id', guild_id)
            
            result = query.execute()
            
            views = result.data if result.data else []
            
            total_views = len(views)
            verified_views = sum(1 for v in views if v['is_verified'])
            total_earned = sum(v['reward_amount'] for v in views if v['reward_granted'])
            
            return {
                'success': True,
                'user_id': user_id,
                'total_views': total_views,
                'verified_views': verified_views,
                'total_earned': total_earned,
                'recent_views': views[:10]  # Last 10 views
            }
            
        except Exception as e:
            logger.error(f"Error getting ad stats: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def get_global_task(self, task_key: str = 'ad_claim_task') -> Optional[Dict]:
        """
        Get global task details
        
        Args:
            task_key: Task key identifier
        
        Returns:
            Dict with task details or None
        """
        try:
            result = self.data_manager.admin_client.table('global_tasks') \
                .select('*') \
                .eq('task_key', task_key) \
                .eq('is_active', True) \
                .execute()
            
            if result.data and len(result.data) > 0:
                return result.data[0]
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting global task: {e}")
            return None
    
    def get_all_global_tasks(self) -> List[Dict]:
        """
        Get all active global tasks
        
        Returns:
            List of global task dicts
        """
        try:
            result = self.data_manager.admin_client.table('global_tasks') \
                .select('*') \
                .eq('is_active', True) \
                .order('created_at') \
                .execute()
            
            return result.data if result.data else []
            
        except Exception as e:
            logger.error(f"Error getting global tasks: {e}")
            return []
    
    def _check_ad_limits(self, user_id: str):
        """
        Check daily limits and cooldowns for ad viewing
        """
        DAILY_LIMIT = 50
        COOLDOWN_SECONDS = 60
        
        now = datetime.now(timezone.utc)
        
        try:
            # 1. Check daily limit
            start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
            
            # Use count='exact' and head=True to get count without fetching data
            result = self.data_manager.admin_client.table('ad_views') \
                .select('ad_session_id', count='exact') \
                .eq('user_id', user_id) \
                .gte('created_at', start_of_day) \
                .execute()
                
            # supabase-py v2 returns count in the result object
            current_count = result.count if result.count is not None else len(result.data)
            
            if current_count >= DAILY_LIMIT:
                logger.info(f"User {user_id} reached daily limit: {current_count}/{DAILY_LIMIT}")
                raise Exception(f"Daily ad limit reached ({DAILY_LIMIT}). Please come back tomorrow!")

            # 2. Check cooldown (time since last created session)
            result = self.data_manager.admin_client.table('ad_views') \
                .select('created_at') \
                .eq('user_id', user_id) \
                .order('created_at', desc=True) \
                .limit(1) \
                .execute()
                
            if result.data and len(result.data) > 0:
                last_created_str = result.data[0]['created_at']
                # Handle potentially missing timezone info or different formats
                try:
                    # Basic ISO parsing
                    last_created = datetime.fromisoformat(last_created_str.replace('Z', '+00:00'))
                except ValueError:
                     # Fallback if format is weird
                     last_created = now - timedelta(seconds=COOLDOWN_SECONDS + 1)

                time_since = (now - last_created).total_seconds()
                
                if time_since < COOLDOWN_SECONDS:
                    wait_time = int(COOLDOWN_SECONDS - time_since)
                    raise Exception(f"Please wait {wait_time}s before watching another ad.")
                    
        except Exception as e:
            # Re-raise explicit limit exceptions, log others
            if "limit reached" in str(e) or "Please wait" in str(e):
                raise
            logger.error(f"Error checking ad limits: {e}")
            # Fail open or closed? Closed for safety.
            raise Exception("Service momentarily unavailable, please try again.")

    def _generate_session_id(self, user_id: str, guild_id: str) -> str:
        """
        Generate a unique session ID for an ad view
        
        Args:
            user_id: Discord user ID
            guild_id: Discord guild ID
        
        Returns:
            Unique session ID string
        """
        # Create a unique identifier
        timestamp = datetime.now(timezone.utc).isoformat()
        random_token = secrets.token_urlsafe(16)
        
        # Combine and hash
        data = f"{user_id}:{guild_id}:{timestamp}:{random_token}"
        session_hash = hashlib.sha256(data.encode()).hexdigest()[:32]
        
        return f"ad_{session_hash}"
    
    def handle_monetag_postback(self, postback_data: Dict) -> Dict:
        """
        Handle postback from Monetag when ad is viewed
        
        Args:
            postback_data: Data from Monetag postback
        
        Returns:
            Dict with processing status
        """
        try:
            # Extract session ID from postback data
            # This will depend on how you configure Monetag postback
            session_id = postback_data.get('session_id') or postback_data.get('subid')
            
            if not session_id:
                return {
                    'success': False,
                    'error': 'No session ID in postback'
                }
            
            # Verify the ad view
            result = self.verify_ad_view(session_id, postback_data)
            
            logger.info(f"Processed Monetag postback for session {session_id}: {result}")
            
            return result
            
        except Exception as e:
            logger.error(f"Error handling Monetag postback: {e}")
            return {
                'success': False,
                'error': str(e)
            }
