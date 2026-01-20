import random
import logging
import os
import psycopg2
from psycopg2.extras import RealDictCursor
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

class EvolvedLotusAPI:
    """
    EvolvedLotus Promotional API
    Serves custom ads for EvolvedLotus blog posts and tools.
    Uses Railway PostgreSQL for storage.
    """
    
    def __init__(self, supabase_client=None):
        self.supabase_client = supabase_client
        self.db_url = os.getenv('DATABASE_URL')
        
        # Fallback ad pool if database is empty or unavailable
        self._fallback_ads = [
            {
                "id": "blog_yt_2026",
                "type": "blog",
                "title": "YouTube 2026: Trends & Growth Guide",
                "headline": "Is Your Strategy Ready for 2026?",
                "description": "Master the 2026 YouTube algorithm with our complete guide. Learn new satisfaction signals and how to grow your channel today!",
                "cta": "Read Growth Guide",
                "url": "https://blog.evolvedlotus.com/blog/2026-01-14-youtube-2026-trends-tips-and-how-to-grow-your-channel/",
                "image": "https://blog.evolvedlotus.com/assets/blog/youtube-2026-trends--tips--and-how-to-grow-your-channel.png",
                "color": "#FF0000"
            },
            {
                "id": "tool_tweetcraft",
                "type": "tool",
                "title": "TweetCraft AI",
                "headline": "AI-Powered Tweet Replies",
                "description": "Generate contextually relevant tweet replies in different tones instantly. Save hours of time and boost your Twitter engagement!",
                "cta": "Try TweetCraft AI",
                "url": "https://tools.evolvedlotus.com/twitterreplybot/",
                "image": "https://tools.evolvedlotus.com/twitterreplybot/favicon.ico",
                "color": "#1DA1F2"
            }
        ]
        logger.info(f"✅ EvolvedLotusAPI initialized (PostgreSQL: {'Yes' if self.db_url else 'No'})")

    def _get_db_connection(self):
        """Creates a connection to Railway PostgreSQL"""
        if not self.db_url:
            return None
        try:
            return psycopg2.connect(self.db_url)
        except Exception as e:
            logger.error(f"Failed to connect to Railway PostgreSQL: {e}")
            return None

    def get_random_ad(self, client_id: Optional[str] = None) -> Dict:
        """Returns a random ad from the pool (prefers Railway DB)"""
        if client_id:
            self.track_client_request(client_id)
            
        ads = self.get_all_ads()
        return random.choice(ads) if ads else random.choice(self._fallback_ads)
    
    def track_client_request(self, client_id: str):
        """Update last_request_at for a client"""
        conn = self._get_db_connection()
        if conn:
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE ad_clients SET last_request_at = NOW() WHERE client_id = %s",
                        (client_id,)
                    )
                conn.commit()
            except Exception as e:
                logger.error(f"Error tracking client request {client_id}: {e}")
            finally:
                conn.close()

    def get_all_ads(self) -> List[Dict]:
        """Returns all available ads from Railway PostgreSQL with fallback"""
        conn = self._get_db_connection()
        if conn:
            try:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("SELECT * FROM custom_ads WHERE is_active = TRUE")
                    rows = cur.fetchall()
                    
                    if rows:
                        formatted_ads = []
                        for ad in rows:
                            formatted_ads.append({
                                "id": ad['id'],
                                "type": ad['ad_type'],
                                "title": ad['title'],
                                "headline": ad.get('headline'),
                                "description": ad['description'],
                                "cta": ad.get('cta', 'Learn More'),
                                "url": ad['url'],
                                "image": ad.get('image'),
                                "color": ad.get('color', '#007bff')
                            })
                        return formatted_ads
            except Exception as e:
                logger.error(f"Error fetching ads from Railway PostgreSQL: {e}")
            finally:
                conn.close()
        
        # If Railway fails, DO NOT use Supabase as the user wants this isolated
        # Use hardcoded fallback instead
        return self._fallback_ads

    def get_ad_clients(self) -> List[Dict]:
        """Get all registered ad clients"""
        conn = self._get_db_connection()
        if conn:
            try:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("SELECT * FROM ad_clients ORDER BY priority DESC, weight DESC")
                    return cur.fetchall()
            except Exception as e:
                logger.error(f"Error fetching ad clients: {e}")
            finally:
                conn.close()
        return []

    def update_ad_client(self, client_id: str, data: Dict) -> bool:
        """Update ad client settings"""
        conn = self._get_db_connection()
        if conn:
            try:
                with conn.cursor() as cur:
                    fields = []
                    params = []
                    for key in ['name', 'priority', 'weight', 'is_active']:
                        if key in data:
                            fields.append(f"{key} = %s")
                            params.append(data[key])
                    
                    if not fields:
                        return True
                        
                    params.append(client_id)
                    query = f"UPDATE ad_clients SET {', '.join(fields)} WHERE client_id = %s"
                    cur.execute(query, tuple(params))
                conn.commit()
                return True
            except Exception as e:
                logger.error(f"Error updating ad client {client_id}: {e}")
            finally:
                conn.close()
        return False

# Singleton instance
evolved_lotus_api = EvolvedLotusAPI()
