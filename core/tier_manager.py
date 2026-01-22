from typing import Dict, Any

class TierManager:
    TIERS = {
        "free": {
            "name": "Free Tier",
            "max_tasks": 5,
            "max_shop_items": 10,
            "show_ads": True,
            "can_use_global": False,
            "channel_schedules": False  # Premium feature
        },
        "premium": {
            "name": "Premium Tier",
            "max_tasks": float('inf'),
            "max_shop_items": float('inf'),
            "show_ads": False,
            "can_use_global": True,
            "channel_schedules": True  # Premium feature - scheduled channel locks
        }
    }

    @staticmethod
    def get_limits(tier: str) -> Dict[str, Any]:
        return TierManager.TIERS.get(tier, TierManager.TIERS["free"])

    @staticmethod
    def check_limit(tier: str, limit_type: str, current_count: int) -> bool:
        limits = TierManager.get_limits(tier)
        max_count = limits.get(limit_type, 0)
        return current_count < max_count

    @staticmethod
    def is_premium(tier: str) -> bool:
        return tier == "premium"
