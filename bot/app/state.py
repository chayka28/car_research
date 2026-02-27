from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from threading import RLock
from typing import Iterator, Literal

from app.schemas import ListingCard, PagedResult, SearchFilters


ScreenType = Literal[
    "menu",
    "help",
    "search",
    "filters",
    "filter_make",
    "filter_model",
    "filter_color",
    "input",
    "results",
    "empty",
    "waitlist",
]


@dataclass
class PaginationState:
    page: int = 1
    pages: int = 1
    total: int = 0
    page_size: int = 1


@dataclass
class WaitlistEntry:
    query_hash: str
    title: str
    query_text: str | None
    filters: SearchFilters
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class UserSession:
    user_id: int
    chat_id: int
    filters: SearchFilters = field(default_factory=SearchFilters)
    mode: Literal["search", "recent", "favorites"] = "search"
    query_text: str | None = None
    awaiting_input: str | None = None
    notify_on_match: bool = False

    screen_message_id: int | None = None
    screen_has_photo: bool = False
    last_screen_type: ScreenType | None = None
    last_query_hash: str | None = None
    pagination_state: PaginationState = field(default_factory=PaginationState)
    filter_back_action: str = "home"
    empty_retry_used: bool = False
    waitlist: list[WaitlistEntry] = field(default_factory=list)

    current_listing: ListingCard | None = None
    last_result: PagedResult | None = None
    last_user_activity: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def touch(self) -> None:
        self.last_user_activity = datetime.now(timezone.utc)


class SessionStore:
    def __init__(self, ttl_seconds: int) -> None:
        self._ttl = timedelta(seconds=max(60, ttl_seconds))
        self._sessions: dict[tuple[int, int], UserSession] = {}
        self._lock = RLock()

    def _cleanup_locked(self) -> None:
        threshold = datetime.now(timezone.utc) - self._ttl
        stale_keys = [key for key, session in self._sessions.items() if session.last_user_activity < threshold]
        for key in stale_keys:
            del self._sessions[key]

    def get_or_create(self, *, user_id: int, chat_id: int) -> UserSession:
        key = (chat_id, user_id)
        with self._lock:
            self._cleanup_locked()
            session = self._sessions.get(key)
            if session is None:
                session = UserSession(user_id=user_id, chat_id=chat_id)
                self._sessions[key] = session
            session.touch()
            return session

    def iter_sessions(self) -> Iterator[UserSession]:
        with self._lock:
            self._cleanup_locked()
            sessions = list(self._sessions.values())
        for session in sessions:
            yield session


def init_session_store(ttl_seconds: int) -> SessionStore:
    return SessionStore(ttl_seconds=ttl_seconds)
