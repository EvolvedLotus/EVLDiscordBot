import random
import logging
import os
import psycopg2
import json
import urllib.request
from psycopg2.extras import RealDictCursor
from typing import Dict, List, Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Blog colors based on category/tags
BLOG_CATEGORY_COLORS = {
    'youtube': '#FF0000',
    'tiktok': '#000000',
    'instagram': '#E4405F',
    'twitter': '#1DA1F2',
    'x': '#1DA1F2',
    'twitch': '#9146FF',
    'facebook': '#1877F2',
    'linkedin': '#0A66C2',
    'discord': '#5865F2',
    'podcast': '#8B5CF6',
    'seo': '#10B981',
    'ai': '#6366F1',
    'default': '#33bdef'  # EvolvedLotus cyan
}

class EvolvedLotusAPI:
    """
    EvolvedLotus Promotional API
    Serves custom ads for EvolvedLotus blog posts and tools.
    Uses Railway PostgreSQL for storage.
    Now supports dynamic rotating blog ads from all published posts!
    """
    
    def __init__(self, supabase_client=None):
        self.supabase_client = supabase_client
        self.db_url = os.getenv('DATABASE_URL')
        
        # Blog API endpoint for fetching all posts
        self.blog_api_url = 'https://blog.evolvedlotus.com/api/posts.json'
        
        # Cache for blog posts (refreshes every 30 minutes)
        self._blog_cache = []
        self._blog_cache_time = None
        self._blog_cache_duration = timedelta(minutes=30)
        
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
        logger.info(f"✅ EvolvedLotusAPI initialized (PostgreSQL: {'Yes' if self.db_url else 'No'}, Blog Rotation: Enabled)")

    def _get_db_connection(self):
        """Creates a connection to Railway PostgreSQL"""
        if not self.db_url:
            return None
        try:
            return psycopg2.connect(self.db_url)
        except Exception as e:
            logger.error(f"Failed to connect to Railway PostgreSQL: {e}")
            return None

    def get_blog_posts(self, force_refresh: bool = False) -> List[Dict]:
        """Fetch all blog posts from the blog API with caching"""
        now = datetime.now()
        
        # Return cached if still valid
        if not force_refresh and self._blog_cache and self._blog_cache_time:
            if now - self._blog_cache_time < self._blog_cache_duration:
                return self._blog_cache
        
        try:
            with urllib.request.urlopen(self.blog_api_url, timeout=10) as response:
                if response.status == 200:
                    data = json.loads(response.read().decode('utf-8'))
                    # The API uses 'blog' as the key for blog posts
                    posts = data.get('blog', data.get('posts', data)) if isinstance(data, dict) else data
                    
                    # Filter out drafts and sort by date (newest first)
                    active_posts = [p for p in posts if not p.get('draft', False)]
                    active_posts.sort(key=lambda x: x.get('date', ''), reverse=True)
                    
                    self._blog_cache = active_posts
                    self._blog_cache_time = now
                    logger.info(f"📝 Fetched {len(active_posts)} blog posts for rotation")
                    return active_posts
        except Exception as e:
            logger.warning(f"Failed to fetch blog posts for rotation: {e}")
        
        return self._blog_cache if self._blog_cache else []

    def _get_blog_color(self, post: Dict) -> str:
        """Determine ad color based on blog post tags/category"""
        tags = post.get('tags', [])
        category = post.get('category', '').lower()
        
        # Check tags first
        if isinstance(tags, list):
            for tag in tags:
                tag_lower = tag.lower()
                for key, color in BLOG_CATEGORY_COLORS.items():
                    if key in tag_lower:
                        return color
        
        # Check category
        for key, color in BLOG_CATEGORY_COLORS.items():
            if key in category:
                return color
        
        # Check title as fallback
        title = post.get('title', '').lower()
        for key, color in BLOG_CATEGORY_COLORS.items():
            if key in title:
                return color
        
        return BLOG_CATEGORY_COLORS['default']

    def _blog_to_ad(self, post: Dict) -> Dict:
        """Convert a blog post to ad format"""
        title = post.get('title', 'EvolvedLotus Blog')
        description = post.get('description', '')
        
        # Truncate description if too long
        if len(description) > 120:
            description = description[:117] + '...'
        
        # Build URL from post data
        url = post.get('url', '')
        if not url.startswith('http'):
            url = f"https://blog.evolvedlotus.com{url}"
        
        # Get image
        image = post.get('image', '')
        if image and not image.startswith('http'):
            image = f"https://blog.evolvedlotus.com{image}"
        
        return {
            "id": f"rotating_blog_{post.get('id', 'unknown')}",
            "type": "rotating_blog",
            "title": title,
            "headline": title[:60] + '...' if len(title) > 60 else title,
            "description": description,
            "cta": "Read Article",
            "url": url,
            "image": image,
            "color": self._get_blog_color(post)
        }

    def get_blog_posts(self, force_refresh: bool = False) -> List[Dict]:
        """Fetch all blog posts from the blog API with caching"""
        now = datetime.now()
        
        # Return cached if still valid
        if not force_refresh and self._blog_cache and self._blog_cache_time:
            if now - self._blog_cache_time < self._blog_cache_duration:
                return self._blog_cache
        
        try:
            response = requests.get(self.blog_api_url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                # The API uses 'blog' as the key for blog posts
                posts = data.get('blog', data.get('posts', data)) if isinstance(data, dict) else data
                
                # Filter out drafts and sort by date (newest first)
                active_posts = [p for p in posts if not p.get('draft', False)]
                active_posts.sort(key=lambda x: x.get('date', ''), reverse=True)
                
                self._blog_cache = active_posts
                self._blog_cache_time = now
                logger.info(f"📝 Fetched {len(active_posts)} blog posts for rotation")
                return active_posts
        except Exception as e:
            logger.warning(f"Failed to fetch blog posts for rotation: {e}")
        
        return self._blog_cache if self._blog_cache else []

    def get_rotating_blog_ad(self) -> Optional[Dict]:
        """Get a random blog post formatted as an ad"""
        posts = self.get_blog_posts()
        if posts:
            post = random.choice(posts)
            return self._blog_to_ad(post)
        return None

    def get_random_ad(self, client_id: Optional[str] = None, include_rotating_blog: bool = False) -> Dict:
        """
        Returns a random ad from the pool.
        
        Args:
            client_id: Optional client ID for tracking
            include_rotating_blog: If True, 40% chance to return a rotating blog ad
        """
        if client_id:
            self.track_client_request(client_id)
        
        # Check if we should return a rotating blog ad
        if include_rotating_blog and random.random() < 0.4:  # 40% chance for blog rotation
            blog_ad = self.get_rotating_blog_ad()
            if blog_ad:
                logger.debug(f"🔄 Serving rotating blog ad: {blog_ad.get('title')}")
                return blog_ad
        
        # Regular ad selection
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
