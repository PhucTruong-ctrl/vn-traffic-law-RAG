"""Supabase-backed application persistence."""

from .models import BOOKMARKS_TABLE, FEEDBACK_TABLE, MESSAGES_TABLE, SESSIONS_TABLE, USERS_TABLE
from .session import SupabaseClient, get_db, get_supabase_client

__all__ = [
    "BOOKMARKS_TABLE",
    "FEEDBACK_TABLE",
    "MESSAGES_TABLE",
    "SESSIONS_TABLE",
    "USERS_TABLE",
    "SupabaseClient",
    "get_db",
    "get_supabase_client",
]
