"""
Core bot functionality - shared across all modules
"""

from .data_manager import DataManager
from . import client
from . import events
from . import permissions
from . import utils

# Global data manager instance - set by bot.py
data_manager = None

__all__ = ['data_manager', 'client', 'events', 'permissions', 'utils']
