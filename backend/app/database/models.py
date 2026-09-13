"""Supabase application tables; corpus and RAG data remain outside Supabase."""

USERS_TABLE = "profiles"
SESSIONS_TABLE = "chat_sessions"
MESSAGES_TABLE = "messages"
FEEDBACK_TABLE = "feedback"
BOOKMARKS_TABLE = "bookmarks"

__all__ = ["USERS_TABLE", "SESSIONS_TABLE", "MESSAGES_TABLE", "FEEDBACK_TABLE", "BOOKMARKS_TABLE"]
