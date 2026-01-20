import os
import psycopg2
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def init_db():
    db_url = os.getenv('DATABASE_URL')
    if not db_url:
        logger.error("No DATABASE_URL found in environment")
        return

    logger.info(f"Connecting to database...")
    try:
        conn = psycopg2.connect(db_url)
        conn.autocommit = True
        with conn.cursor() as cur:
            logger.info("Creating custom_ads table...")
            cur.execute("""
                CREATE TABLE IF NOT EXISTS custom_ads (
                    id TEXT PRIMARY KEY,
                    ad_type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    headline TEXT,
                    description TEXT,
                    cta TEXT,
                    url TEXT NOT NULL,
                    image TEXT,
                    color TEXT,
                    is_active BOOLEAN DEFAULT true,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    metadata JSONB DEFAULT '{}'
                );
            """)

            logger.info("Creating ad_clients table...")
            cur.execute("""
                CREATE TABLE IF NOT EXISTS ad_clients (
                    client_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    priority INTEGER DEFAULT 1,
                    weight INTEGER DEFAULT 10,
                    is_active BOOLEAN DEFAULT true,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    last_request_at TIMESTAMP WITH TIME ZONE
                );
            """)
            
            logger.info("Inserting initial ads...")
            cur.execute("""
                INSERT INTO custom_ads (id, ad_type, title, headline, description, cta, url, image, color)
                VALUES 
                ('blog_yt_2026', 'blog', 'YouTube 2026: Trends & Growth Guide', 'Is Your Strategy Ready for 2026?', 'Master the 2026 YouTube algorithm with our complete guide.', 'Read Growth Guide', 'https://blog.evolvedlotus.com/blog/2026-01-14-youtube-2026-trends-tips-and-how-to-grow-your-channel/', 'https://blog.evolvedlotus.com/assets/blog/youtube-2026-trends--tips--and-how-to-grow-your-channel.png', '#FF0000'),
                ('tool_tweetcraft', 'tool', 'TweetCraft AI', 'AI-Powered Tweet Replies', 'Generate contextually relevant tweet replies in different tones instantly.', 'Try TweetCraft AI', 'https://tools.evolvedlotus.com/twitterreplybot/', 'https://tools.evolvedlotus.com/twitterreplybot/favicon.ico', '#1DA1F2')
                ON CONFLICT (id) DO NOTHING;
            """)

            logger.info("Inserting initial ad clients...")
            cur.execute("""
                INSERT INTO ad_clients (client_id, name, priority, weight)
                VALUES 
                ('tools', 'EVL Tools', 1, 40),
                ('blog', 'EVL Blog', 1, 30),
                ('main', 'Main Website', 2, 30)
                ON CONFLICT (client_id) DO NOTHING;
            """)
            logger.info("✅ Database initialized successfully")
        conn.close()
    except Exception as e:
        logger.error(f"❌ Initialization failed: {e}")

if __name__ == "__main__":
    init_db()
