# EvolvedLotus Unified API - Comprehensive Design Concept

## 🎯 Vision

A centralized API that powers all EvolvedLotus properties, providing unified content management, cross-platform analytics, promotional ad serving, and user engagement tracking across:

1. **EvolvedLotusWebsite** (Main brand site)
2. **Task-Bot-Discord** (Discord economy bot)
3. **Blog** (Content marketing platform)
4. **EVLReplyBot** (Twitter tools suite)

---

## 🏗️ Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                   BLOG ADMIN CMS                            │
│            (Central Control Panel)                          │
└─────────────────────┬───────────────────────────────────────┘
                      │ REST API / GraphQL
                      ▼
┌─────────────────────────────────────────────────────────────┐
│              EVOLVEDLOTUS UNIFIED API                       │
│                (Railway PostgreSQL)                         │
│                                                             │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐           │
│  │   Ads       │ │  Analytics  │ │  Content    │           │
│  │   Module    │ │   Module    │ │   Module    │           │
│  └─────────────┘ └─────────────┘ └─────────────┘           │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐           │
│  │   Users     │ │  Campaigns  │ │  Webhooks   │           │
│  │   Module    │ │   Module    │ │   Module    │           │
│  └─────────────┘ └─────────────┘ └─────────────┘           │
└─────────────────────────────────────────────────────────────┘
                      │
          ┌───────────┼───────────┬───────────┐
          ▼           ▼           ▼           ▼
    ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐
    │ Website  │ │ Discord  │ │   Blog   │ │ Twitter  │
    │          │ │   Bot    │ │          │ │  Tools   │
    └──────────┘ └──────────┘ └──────────┘ └──────────┘
```

---

## 📊 Database Schema (Railway PostgreSQL)

### Core Tables

```sql
-- =====================================================
-- CUSTOM ADS TABLE (Promotional Content)
-- =====================================================
CREATE TABLE custom_ads (
    id TEXT PRIMARY KEY,
    ad_type TEXT NOT NULL,  -- 'blog', 'tool', 'product', 'affiliate'
    title TEXT NOT NULL,
    headline TEXT,
    description TEXT,
    cta TEXT,
    url TEXT NOT NULL,
    image TEXT,
    color TEXT,
    priority INTEGER DEFAULT 1,  -- Higher = more likely to show
    target_platforms TEXT[] DEFAULT ARRAY['all'],  -- 'discord', 'web', 'twitter'
    is_active BOOLEAN DEFAULT true,
    impressions INTEGER DEFAULT 0,
    clicks INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'
);

-- =====================================================
-- ANALYTICS TABLE (Cross-Platform Tracking)
-- =====================================================
CREATE TABLE analytics_events (
    id SERIAL PRIMARY KEY,
    event_type TEXT NOT NULL,  -- 'impression', 'click', 'conversion', 'page_view'
    platform TEXT NOT NULL,    -- 'discord', 'blog', 'website', 'twitter_tools'
    ad_id TEXT REFERENCES custom_ads(id),
    user_id TEXT,              -- Optional user identifier
    session_id TEXT,
    ip_hash TEXT,              -- Hashed for privacy
    user_agent TEXT,
    referrer TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'
);

-- =====================================================
-- CONTENT SYNC TABLE (Blog/Tool Updates)
-- =====================================================
CREATE TABLE content_items (
    id TEXT PRIMARY KEY,
    content_type TEXT NOT NULL,  -- 'blog_post', 'tool', 'page'
    title TEXT NOT NULL,
    description TEXT,
    url TEXT NOT NULL,
    image TEXT,
    tags TEXT[],
    published_at TIMESTAMP WITH TIME ZONE,
    is_featured BOOLEAN DEFAULT false,
    view_count INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'
);

-- =====================================================
-- CAMPAIGNS TABLE (Marketing Campaigns)
-- =====================================================
CREATE TABLE campaigns (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    start_date TIMESTAMP WITH TIME ZONE,
    end_date TIMESTAMP WITH TIME ZONE,
    target_platforms TEXT[],
    ad_ids TEXT[],  -- Array of custom_ads IDs
    budget_cents INTEGER,
    spent_cents INTEGER DEFAULT 0,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'
);

-- =====================================================
-- API KEYS TABLE (Authentication)
-- =====================================================
CREATE TABLE api_keys (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    key_hash TEXT NOT NULL,
    permissions TEXT[],  -- ['read', 'write', 'admin']
    rate_limit INTEGER DEFAULT 1000,  -- requests per hour
    is_active BOOLEAN DEFAULT true,
    last_used_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

---

## 🔌 API Endpoints

### Base URL
```
https://api.evolvedlotus.com/v1
```

### Authentication
All requests require an API key in the header:
```
Authorization: Bearer evl_sk_xxxxxxxxxxxxx
```

### Ads Module

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/ads` | Get all active ads |
| GET | `/ads/random` | Get a random ad (weighted by priority) |
| GET | `/ads/:id` | Get specific ad by ID |
| POST | `/ads` | Create new ad |
| PUT | `/ads/:id` | Update ad |
| DELETE | `/ads/:id` | Delete ad |
| POST | `/ads/:id/impression` | Track impression |
| POST | `/ads/:id/click` | Track click |

### Analytics Module

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/analytics/overview` | Dashboard overview stats |
| GET | `/analytics/ads/:id` | Stats for specific ad |
| GET | `/analytics/platform/:platform` | Stats by platform |
| POST | `/analytics/event` | Track custom event |

### Content Module

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/content` | List all content items |
| GET | `/content/featured` | Get featured content |
| GET | `/content/:id` | Get specific content |
| POST | `/content/sync` | Trigger content sync from sources |
| PUT | `/content/:id` | Update content metadata |

### Campaigns Module

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/campaigns` | List all campaigns |
| GET | `/campaigns/active` | Get active campaigns |
| POST | `/campaigns` | Create campaign |
| PUT | `/campaigns/:id` | Update campaign |
| DELETE | `/campaigns/:id` | Delete campaign |

---

## 🖥️ Blog Admin CMS Integration

### New CMS Section: "EvolvedLotus API"

```
📊 EvolvedLotus API
├── 📢 Promotional Ads
│   ├── View All Ads
│   ├── Create New Ad
│   ├── Edit Ad
│   └── Ad Performance
├── 📈 Analytics Dashboard
│   ├── Overview
│   ├── Platform Breakdown
│   └── Top Performers
├── 📝 Content Library
│   ├── Blog Posts
│   ├── Tools
│   └── Sync Status
└── 🎯 Campaigns
    ├── Active Campaigns
    ├── Create Campaign
    └── Campaign Analytics
```

### CMS Features

1. **Ad Editor**
   - WYSIWYG preview for each platform
   - A/B testing setup
   - Scheduling (start/end dates)
   - Priority weighting
   - Target platform selection

2. **Analytics Dashboard**
   - Real-time impressions/clicks
   - Conversion tracking
   - Platform comparison
   - Time-series charts

3. **Content Sync**
   - Auto-import blog posts
   - Auto-import tool pages
   - Manual refresh trigger
   - Featured content picker

---

## 🔗 Platform Integration Details

### 1. Task-Bot-Discord Integration

**Current Implementation:**
- `core/evolved_lotus_api.py` fetches ads from Railway DB
- `core/ad_claim_manager.py` rotates between Monetag and custom ads
- `docs/ad-viewer.html` displays the ad viewer

**Enhanced Integration:**
```python
# In ad_claim_manager.py
from core.evolved_lotus_api import evolved_lotus_api

def create_ad_session(self, user_id, guild_id):
    # Get ad with platform targeting
    ad = evolved_lotus_api.get_random_ad(platform='discord')
    
    # Track impression
    evolved_lotus_api.track_event('impression', ad['id'], platform='discord')
    
    # ... rest of session creation
```

### 2. Blog Integration

**Implementation:**
```javascript
// In blog/_includes/ad-banner.njk
<script>
async function loadEvolvedLotusAd() {
    const response = await fetch('https://api.evolvedlotus.com/v1/ads/random?platform=blog');
    const ad = await response.json();
    
    document.getElementById('evl-ad').innerHTML = `
        <a href="${ad.url}" onclick="trackClick('${ad.id}')">
            <img src="${ad.image}" alt="${ad.title}">
            <h3>${ad.headline}</h3>
            <p>${ad.description}</p>
            <button>${ad.cta}</button>
        </a>
    `;
}
</script>
```

### 3. EVLReplyBot Integration

**Implementation:**
```javascript
// In TwitterReplyBot/src/components/AdBanner.js
import { useEffect, useState } from 'react';

export function AdBanner() {
    const [ad, setAd] = useState(null);
    
    useEffect(() => {
        fetch('https://api.evolvedlotus.com/v1/ads/random?platform=twitter_tools')
            .then(res => res.json())
            .then(setAd);
    }, []);
    
    if (!ad) return null;
    
    return (
        <div className="evl-ad-banner" style={{borderColor: ad.color}}>
            <img src={ad.image} alt={ad.title} />
            <div>
                <h4>{ad.headline}</h4>
                <p>{ad.description}</p>
                <a href={ad.url}>{ad.cta}</a>
            </div>
        </div>
    );
}
```

### 4. EvolvedLotusWebsite Integration

**Implementation:**
```html
<!-- In EvolvedLotusWebsite/index.html -->
<section id="featured-content">
    <div id="evl-featured"></div>
</section>

<script>
async function loadFeatured() {
    const response = await fetch('https://api.evolvedlotus.com/v1/content/featured');
    const items = await response.json();
    
    document.getElementById('evl-featured').innerHTML = items.map(item => `
        <article>
            <img src="${item.image}" alt="${item.title}">
            <h3>${item.title}</h3>
            <p>${item.description}</p>
            <a href="${item.url}">Learn More</a>
        </article>
    `).join('');
}
loadFeatured();
</script>
```

---

## 🚀 Implementation Phases

### Phase 1: Foundation (Current)
- ✅ Railway PostgreSQL database setup
- ✅ `custom_ads` table created
- ✅ Basic `EvolvedLotusAPI` class in Discord bot
- ✅ Ad rotation in Discord bot working

### Phase 2: API Service
- [ ] Create standalone Flask/FastAPI service
- [ ] Implement all endpoint modules
- [ ] Add authentication via API keys
- [ ] Deploy to Railway as separate service

### Phase 3: CMS Integration
- [ ] Add "EvolvedLotus API" section to blog admin
- [ ] Build ad editor UI
- [ ] Build analytics dashboard
- [ ] Connect to API endpoints

### Phase 4: Platform Integration
- [ ] Update Discord bot to use API endpoints
- [ ] Add ad banners to blog
- [ ] Add ad banners to EVLReplyBot tools
- [ ] Add featured content to main website

### Phase 5: Analytics & Optimization
- [ ] Implement real-time analytics
- [ ] Add A/B testing framework
- [ ] Build campaign management
- [ ] Implement smart ad rotation (ML-based)

---

## 🔒 Security Considerations

1. **API Key Management**
   - Keys hashed with bcrypt
   - Different permission levels
   - Rate limiting per key

2. **Data Privacy**
   - IP addresses hashed
   - No PII stored
   - GDPR compliant

3. **Cross-Origin**
   - CORS configured per domain
   - Allowlist for API access

---

## 📝 Environment Variables

```env
# Railway PostgreSQL (EvolvedLotus API Only)
DATABASE_URL=postgresql://...

# API Configuration
EVL_API_SECRET_KEY=your-secret-key
EVL_API_RATE_LIMIT=1000

# Platform API Keys
EVL_DISCORD_API_KEY=evl_sk_discord_xxx
EVL_BLOG_API_KEY=evl_sk_blog_xxx
EVL_TWITTER_TOOLS_API_KEY=evl_sk_twitter_xxx
EVL_WEBSITE_API_KEY=evl_sk_website_xxx
```

---

## 📊 Success Metrics

1. **Engagement**: Click-through rate > 2%
2. **Cross-Promotion**: 10% traffic increase between properties
3. **Monetization**: Support Monetag revenue with own content
4. **User Experience**: Ad relevance score > 4/5

---

## 🎯 Next Steps

1. **Immediate**: Push current changes and deploy Discord bot update
2. **This Week**: Design CMS UI mockups for ad management
3. **Next Week**: Build standalone API service
4. **Month 1**: Full CMS integration complete
5. **Month 2**: All platforms integrated with analytics

---

*Document Version: 1.0*
*Last Updated: 2026-01-20*
