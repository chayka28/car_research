from __future__ import annotations

import time
import uuid
from dataclasses import dataclass

from app.schemas import ListingCard


@dataclass
class SearchSession:
    token: str
    chat_id: int
    query: str
    listings: list[ListingCard]
    current_index: int
    created_ts: float
    photo_message_id: int | None = None


class SessionStore:
    def __init__(self, ttl_seconds: int) -> None:
        self._ttl_seconds = ttl_seconds
        self._sessions: dict[str, SearchSession] = {}

    def _cleanup(self) -> None:
        now = time.time()
        expired = [token for token, session in self._sessions.items() if now - session.created_ts > self._ttl_seconds]
        for token in expired:
            self._sessions.pop(token, None)

    def create(self, chat_id: int, query: str, listings: list[ListingCard]) -> SearchSession:
        self._cleanup()
        token = uuid.uuid4().hex[:12]
        session = SearchSession(
            token=token,
            chat_id=chat_id,
            query=query,
            listings=listings,
            current_index=0,
            created_ts=time.time(),
        )
        self._sessions[token] = session
        return session

    def get(self, token: str) -> SearchSession | None:
        self._cleanup()
        return self._sessions.get(token)

    def set_index(self, token: str, index: int) -> SearchSession | None:
        session = self.get(token)
        if session is None:
            return None
        bounded = max(0, min(index, len(session.listings) - 1))
        session.current_index = bounded
        return session


SESSION_STORE: SessionStore | None = None


def init_session_store(ttl_seconds: int) -> SessionStore:
    global SESSION_STORE
    SESSION_STORE = SessionStore(ttl_seconds)
    return SESSION_STORE
