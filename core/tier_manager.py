from typing import Dict, Any

class TierManager:
    TIERS = {
        "free": {
            "name": "Free Tier",
            "max_tasks": 5,
            "max_shop_items": 10,
            "show_ads": True,
            "can_use_global": False,
            "channel_schedules": False
        },
        "supporter": {
            "name": "Supporter",
            "max_tasks": 10,
            "max_shop_items": 20,
            "show_ads": True,
            "can_use_global": False,
            "channel_schedules": False
        },
        "growth_insider": {
            "name": "Growth Insider",
            "max_tasks": float('inf'),
            "max_shop_items": float('inf'),
            "show_ads": False,
            "can_use_global": True,
            "channel_schedules": True  # Premium feature - scheduled channel locks
        }
    }

    # Legacy alias for backward compatibility
    TIERS["premium"] = TIERS["growth_insider"]

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
        """Check if a tier has full premium (Growth Insider) access"""
        return tier in ("growth_insider", "premium")

    @staticmethod
    def is_paid(tier: str) -> bool:
        """Check if a tier is any paid tier (Supporter or Growth Insider)"""
        return tier in ("supporter", "growth_insider", "premium")
