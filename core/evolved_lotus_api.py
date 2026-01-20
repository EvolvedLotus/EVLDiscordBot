import random
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

class EvolvedLotusAPI:
    """
    EvolvedLotus Promotional API
    Serves custom ads for EvolvedLotus blog posts and tools.
    """
    
    def __init__(self):
        # Initial ad pool generated from blog posts and tools
        self.ads = [
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
                "id": "blog_tiktok_views",
                "type": "blog",
                "title": "Skyrocket Your TikTok Views",
                "headline": "Stuck at 200 Views?",
                "description": "Discover the simple content strategy that actually works. We jumped from 300 to 3,000 views in just 7 days!",
                "cta": "Get More Views",
                "url": "https://blog.evolvedlotus.com/blog/2025-05-13-how-to-skyrocket-your-tiktok-views-and-engagement-a-simple-content-strategy/",
                "image": "https://blog.evolvedlotus.com/assets/blog/how-to-skyrocket-your-tiktok-views-and-engagement-a-simple-content-strategy.png",
                "color": "#EE1D52"
            },
            {
                "id": "tool_tweetcraft",
                "type": "tool",
                "title": "TweetCraft AI",
                "headline": "AI-Powered Tweet Replies",
                "description": "Generate contextually relevant tweet replies in different tones instantly. Save hours of time and boost your Twitter engagement!",
                "cta": "Try TweetCraft AI",
                "url": "https://tools.evolvedlotus.com/TwitterReplyBot/",
                "image": "https://tools.evolvedlotus.com/TwitterReplyBot/favicon.ico",
                "color": "#1DA1F2"
            },
            {
                "id": "tool_this_weeks_yt",
                "type": "tool",
                "title": "This Week's YouTube",
                "headline": "What's Trending on YouTube?",
                "description": "The most engaging YouTube content of the week, curated for you. See what's viral before everyone else.",
                "cta": "See Trending Now",
                "url": "https://tools.evolvedlotus.com/ThisWeeksYT/",
                "image": "https://cdn.pixabay.com/photo/2016/07/03/18/36/youtube-1495277_1280.png",
                "color": "#FFC107"
            },
            {
                "id": "blog_viral_caption",
                "type": "blog",
                "title": "Viral Captions for 2025",
                "headline": "Stop Writing Boring Captions",
                "description": "Learn how to write viral captions that drive engagement across all social platforms. Complete 2025 strategy inside!",
                "cta": "Read Guide",
                "url": "https://blog.evolvedlotus.com/blog/2025-01-29-how-to-write-a-viral-caption-for-social-media/",
                "image": "https://blog.evolvedlotus.com/assets/blog/how-to-write-a-viral-caption-for-social-media.png",
                "color": "#9C27B0"
            }
        ]
        logger.info(f"✅ EvolvedLotusAPI initialized with {len(self.ads)} ad creatives")

    def get_random_ad(self) -> Dict:
        """Returns a random ad from the pool"""
        return random.choice(self.ads)
    
    def get_ad_by_id(self, ad_id: str) -> Optional[Dict]:
        """Returns a specific ad by ID"""
        for ad in self.ads:
            if ad['id'] == ad_id:
                return ad
        return None

    def get_all_ads(self) -> List[Dict]:
        """Returns all available ads"""
        return self.ads

# Singleton instance
evolved_lotus_api = EvolvedLotusAPI()
