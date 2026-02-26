from __future__ import annotations

import time
from dataclasses import dataclass, field

from app.schemas import ListingCard, PagedResult, SearchFilters


@dataclass
class UserSession:
    user_id: int
    chat_id: int
    mode: str = "search"
    query_text: str | None = None
    filters: SearchFilters = field(default_factory=SearchFilters)
    page: int = 1
    page_size: int = 1
    awaiting_input: str | None = None
    created_ts: float = field(default_factory=time.time)
    updated_ts: float = field(default_factory=time.time)
    last_result: PagedResult | None = None
    photo_message_id: int | None = None

    def touch(self) -> None:
        self.updated_ts = time.time()

    @property
    def current_listing(self) -> ListingCard | None:
        if self.last_result is None:
            return None
        if not self.last_result.items:
            return None
        return self.last_result.items[0]


class SessionStore:
    def __init__(self, ttl_seconds: int) -> None:
        self._ttl_seconds = ttl_seconds
        self._sessions: dict[int, UserSession] = {}

    def _cleanup(self) -> None:
        now = time.time()
        expired = [user_id for user_id, item in self._sessions.items() if now - item.updated_ts > self._ttl_seconds]
        for user_id in expired:
            self._sessions.pop(user_id, None)

    def get_or_create(self, *, user_id: int, chat_id: int) -> UserSession:
        self._cleanup()
        session = self._sessions.get(user_id)
        if session is None:
            session = UserSession(user_id=user_id, chat_id=chat_id)
            self._sessions[user_id] = session
        else:
            session.chat_id = chat_id
            session.touch()
        return session


SESSION_STORE: SessionStore | None = None


def init_session_store(ttl_seconds: int) -> SessionStore:
    global SESSION_STORE
    SESSION_STORE = SessionStore(ttl_seconds)
    return SESSION_STORE
