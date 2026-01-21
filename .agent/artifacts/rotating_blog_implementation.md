# Rotating Blog Ads Feature Implementation

## Overview
This feature allows the EvolvedLotus API to serve dynamic ads sourced from all published blog posts on `blog.evolvedlotus.com`. This ensures that promotional content is always fresh and drives traffic to a wide variety of articles, not just a few manually selected ones.

## Key Components

### 1. API Backend (`task-bot-discord`)
- **File**: `core/evolved_lotus_api.py`
- **Method**: `get_rotating_blog_ad()`
- **Logic**:
  - Fetches `https://blog.evolvedlotus.com/api/posts.json`
  - Caches the result for 30 minutes to minimize latency.
  - Parsed the `blog` array from the JSON.
  - Converts a random blog post into an Ad format (Title, Headline, Description, Image, URL).
  - Assigns a color dynamically based on tags (e.g., YouTube -> Red, Discord -> Blurple).
- **Endpoint**: `GET /api/ad`
  - Added query param `include_blogs=true`.
  - When true, there is a **40% chance** the API returns a rotating blog ad instead of a static custom ad.

### 2. Ad Banner Component (`EVLReplyBot`)
- **File**: `src/components/EvlAdBanner.jsx`
- **Update**:
  - Switched from hardcoded/fallback ads to the live Railway API (`https://evl-task-bot-discord-production.up.railway.app`).
  - Passes `include_blogs=true` to enable the rotation feature.
  - Gracefully falls back to static ads if the API is unreachable.

### 3. Blog Admin CMS (`blog`)
- **File**: `src/admin/index.html`
- **Updates**:
  - **API Endpoint**: Corrected to point to Railway (`evl-task-bot-discord-production.up.railway.app`) instead of the placeholder `api.evolvedlotus.com`.
  - **Stats**: Logic added to fetch and display the count of blog posts currently available for rotation.
  - **UI**: Added a "Rotating Blog Ads" status card explaining the feature to admins.

## Usage
To enable this feature on other platforms, simply append `include_blogs=true` to the request:

```http
GET https://evl-task-bot-discord-production.up.railway.app/api/ad?client_id=YOUR_CLIENT_ID&include_blogs=true
```

## Maintenance
- The blog cache auto-refreshes every 30 minutes.
- No database updates are required for new blog posts; they are picked up automatically from the Blog's JSON feed.
