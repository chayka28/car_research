from __future__ import annotations

import logging
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import NamedTuple

from sqlalchemy import and_, func, or_, select

from app.config import SETTINGS
from app.db import SessionLocal
from app.models import Favorite, Listing, ScrapeRequest
from app.schemas import ListingCard, PagedResult, SearchFilters

logger = logging.getLogger(__name__)

SENTINEL_PRICE_MAX = 2_147_483_647
PLACEHOLDER_PRICE_VALUES = {999_999_999, 99_999_999, 69_999_999, 619_999_999}
MAX_REASONABLE_PRICE_RUB = 80_000_000
UNKNOWN_TEXT_VALUES = {"", "-", "unknown", "none", "null", "не указано", "n/a"}


class EnqueueResult(NamedTuple):
    triggered: bool
    reason: str


def _normalize_text(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    return text if text else None


def _is_unknown_text(value: str | None) -> bool:
    normalized = _normalize_text(value)
    if normalized is None:
        return True
    return normalized.lower() in UNKNOWN_TEXT_VALUES


def _norm_like(value: str) -> str:
    return f"%{value.strip().lower()}%"


def _norm_eq_values(values: list[str]) -> list[str]:
    return [item.strip().lower() for item in values if item and item.strip()]


def _price_value_valid(value: int | None) -> bool:
    if value is None:
        return False
    if value <= 0:
        return False
    if value >= SENTINEL_PRICE_MAX:
        return False
    if value in PLACEHOLDER_PRICE_VALUES:
        return False
    if value > MAX_REASONABLE_PRICE_RUB:
        return False
    return True


def _effective_price_rub(row: Listing) -> int | None:
    candidate_values: list[int | None] = [
        row.total_price_rub,
        row.price_rub,
        int(round(row.total_price_jpy * SETTINGS.jpy_to_rub_rate)) if row.total_price_jpy is not None else None,
        int(round(row.price_jpy * SETTINGS.jpy_to_rub_rate)) if row.price_jpy is not None else None,
    ]
    for value in candidate_values:
        if _price_value_valid(value):
            return value
    return None


def _card(row: Listing) -> ListingCard:
    return ListingCard(
        id=row.id,
        external_id=row.external_id,
        source=row.source,
        url=row.url,
        maker=row.maker,
        model=row.model,
        year=row.year,
        color=row.color,
        price_rub=_effective_price_rub(row),
        last_seen_at=row.last_seen_at,
        is_active=row.is_active,
    )


def _base_listing_stmt(filters: SearchFilters, query_text: str | None = None):
    stmt = (
        select(Listing)
        .where(Listing.source == "carsensor")
        .where(Listing.deleted_at.is_(None))
        .where(func.length(func.trim(func.coalesce(Listing.external_id, ""))) > 0)
        .where(func.length(func.trim(func.coalesce(Listing.url, ""))) > 0)
        .where(func.lower(func.trim(func.coalesce(Listing.maker, ""))) != "unknown")
        .where(func.lower(func.trim(func.coalesce(Listing.model, ""))) != "unknown")
    )

    if filters.only_active:
        stmt = stmt.where(Listing.is_active.is_(True))

    if filters.makes:
        normalized_makes = _norm_eq_values(filters.makes)
        if normalized_makes:
            stmt = stmt.where(func.lower(func.trim(Listing.maker)).in_(normalized_makes))

    if filters.models:
        normalized_models = _norm_eq_values(filters.models)
        if normalized_models:
            stmt = stmt.where(func.lower(func.trim(Listing.model)).in_(normalized_models))

    if filters.colors:
        stmt = stmt.where(
            or_(*[func.lower(func.coalesce(Listing.color, "")).like(_norm_like(item)) for item in filters.colors])
        )

    for item in filters.exclude_colors:
        stmt = stmt.where(func.lower(func.coalesce(Listing.color, "")).not_like(_norm_like(item)))

    if filters.year_min is not None:
        stmt = stmt.where(Listing.year.is_not(None)).where(Listing.year >= filters.year_min)
    if filters.year_max is not None:
        stmt = stmt.where(Listing.year.is_not(None)).where(Listing.year <= filters.year_max)

    if query_text and filters.is_empty():
        term = _norm_like(query_text)
        stmt = stmt.where(
            or_(
                func.lower(Listing.maker).like(term),
                func.lower(Listing.model).like(term),
                func.lower(func.coalesce(Listing.color, "")).like(term),
                func.lower(Listing.external_id).like(term),
            )
        )

    return stmt


def _ordered_rows(*, filters: SearchFilters, query_text: str | None) -> list[Listing]:
    stmt = _base_listing_stmt(filters, query_text=query_text).order_by(Listing.last_seen_at.desc(), Listing.id.desc())
    with SessionLocal() as session:
        rows = session.scalars(stmt.limit(5000)).all()
    return rows


def _paginate(items: list[ListingCard], page: int, page_size: int) -> PagedResult:
    safe_page_size = max(1, page_size)
    total = len(items)
    pages = max(1, (total + safe_page_size - 1) // safe_page_size) if total else 1
    current = min(max(1, page), pages)
    start = (current - 1) * safe_page_size
    end = start + safe_page_size
    return PagedResult(items=items[start:end], total=total, page=current, pages=pages)


def search_cars(
    *,
    filters: SearchFilters,
    page: int,
    page_size: int,
    query_text: str | None = None,
) -> PagedResult:
    rows = _ordered_rows(filters=filters, query_text=query_text)
    cards = [_card(row) for row in rows]

    filtered_cards: list[ListingCard] = []
    for item in cards:
        if filters.price_min_rub is not None:
            if item.price_rub is None or item.price_rub < filters.price_min_rub:
                continue
        if filters.price_max_rub is not None:
            if item.price_rub is None or item.price_rub > filters.price_max_rub:
                continue
        filtered_cards.append(item)

    if filters.sort == "price_asc":
        filtered_cards.sort(key=lambda item: (item.price_rub is None, item.price_rub or 0, item.id))
    elif filters.sort == "price_desc":
        filtered_cards.sort(key=lambda item: (item.price_rub is None, -(item.price_rub or 0), -item.id))
    else:
        filtered_cards.sort(key=lambda item: (item.last_seen_at or datetime.min, item.id), reverse=True)

    return _paginate(filtered_cards, page=page, page_size=page_size)


def _recent_skip_reason(row: Listing) -> str | None:
    if _normalize_text(row.external_id) is None:
        return "missing_external_id"
    if _normalize_text(row.url) is None:
        return "missing_url"
    if row.year is None:
        return "missing_year"
    if _effective_price_rub(row) is None:
        return "missing_price"
    if _is_unknown_text(row.maker) and _is_unknown_text(row.model):
        return "missing_make_model"
    return None


def recent_cars(*, page: int, page_size: int) -> PagedResult:
    with SessionLocal() as session:
        stmt = (
            select(Listing)
            .where(Listing.source == "carsensor")
            .where(Listing.deleted_at.is_(None))
            .where(Listing.is_active.is_(True))
            .order_by(Listing.id.desc())
            .limit(1000)
        )
        rows = session.scalars(stmt).all()

    skipped = Counter()
    cards: list[ListingCard] = []
    for row in rows:
        reason = _recent_skip_reason(row)
        if reason is not None:
            skipped[reason] += 1
            continue
        cards.append(_card(row))
        if len(cards) >= 50:
            break

    logger.info(
        "Recent cards selected=%s scanned=%s skipped=%s",
        len(cards),
        len(rows),
        dict(skipped),
    )
    return _paginate(cards, page=page, page_size=page_size)


def favorite_cars(*, user_id: int, page: int, page_size: int) -> PagedResult:
    with SessionLocal() as session:
        stmt = (
            select(Listing)
            .join(
                Favorite,
                and_(
                    Favorite.source == Listing.source,
                    Favorite.external_id == Listing.external_id,
                ),
            )
            .where(Favorite.user_id == user_id)
            .where(Listing.deleted_at.is_(None))
            .order_by(Favorite.created_at.desc(), Listing.id.desc())
            .limit(5000)
        )
        rows = session.scalars(stmt).all()

    cards = [_card(row) for row in rows]
    logger.info("Favorite cards user_id=%s count=%s", user_id, len(cards))
    return _paginate(cards, page=page, page_size=page_size)


def list_filter_makes(*, only_active: bool = True, limit: int = 10) -> list[str]:
    stmt = (
        select(Listing.maker, func.count(Listing.id).label("cnt"))
        .where(Listing.source == "carsensor")
        .where(Listing.deleted_at.is_(None))
        .where(func.length(func.trim(func.coalesce(Listing.maker, ""))) > 0)
        .group_by(Listing.maker)
        .order_by(func.count(Listing.id).desc(), func.lower(Listing.maker))
        .limit(limit * 3)
    )
    if only_active:
        stmt = stmt.where(Listing.is_active.is_(True))

    with SessionLocal() as session:
        rows = session.execute(stmt).all()
    values = [maker.strip() for maker, _ in rows if maker and not _is_unknown_text(maker)]
    return values[:limit]


def list_filter_models(
    *,
    makes: list[str] | None = None,
    only_active: bool = True,
    limit: int = 10,
) -> list[str]:
    stmt = (
        select(Listing.model, func.count(Listing.id).label("cnt"))
        .where(Listing.source == "carsensor")
        .where(Listing.deleted_at.is_(None))
        .where(func.length(func.trim(func.coalesce(Listing.model, ""))) > 0)
        .group_by(Listing.model)
        .order_by(func.count(Listing.id).desc(), func.lower(Listing.model))
        .limit(limit * 3)
    )
    if only_active:
        stmt = stmt.where(Listing.is_active.is_(True))
    if makes:
        normalized_makes = _norm_eq_values(makes)
        if normalized_makes:
            stmt = stmt.where(func.lower(func.trim(Listing.maker)).in_(normalized_makes))

    with SessionLocal() as session:
        rows = session.execute(stmt).all()
    values = [model.strip() for model, _ in rows if model and not _is_unknown_text(model)]
    return values[:limit]


def list_filter_colors(
    *,
    makes: list[str] | None = None,
    models: list[str] | None = None,
    only_active: bool = True,
    limit: int = 100,
) -> list[str]:
    stmt = (
        select(Listing.color)
        .where(Listing.source == "carsensor")
        .where(Listing.deleted_at.is_(None))
        .where(func.length(func.trim(func.coalesce(Listing.color, ""))) > 0)
    )
    if only_active:
        stmt = stmt.where(Listing.is_active.is_(True))
    if makes:
        stmt = stmt.where(or_(*[func.lower(Listing.maker).like(_norm_like(make)) for make in makes]))
    if models:
        stmt = stmt.where(or_(*[func.lower(Listing.model).like(_norm_like(model)) for model in models]))
    stmt = stmt.distinct().limit(limit * 3)

    with SessionLocal() as session:
        rows = session.scalars(stmt).all()
    values = sorted({item.strip() for item in rows if item and not _is_unknown_text(item)}, key=str.lower)
    values = values[:limit]
    return values


def is_favorite(*, user_id: int, source: str, external_id: str) -> bool:
    with SessionLocal() as session:
        row = session.scalar(
            select(Favorite.id)
            .where(Favorite.user_id == user_id)
            .where(Favorite.source == source)
            .where(Favorite.external_id == external_id)
        )
    return row is not None


def toggle_favorite(*, user_id: int, source: str, external_id: str) -> bool:
    with SessionLocal() as session:
        existing = session.scalar(
            select(Favorite)
            .where(Favorite.user_id == user_id)
            .where(Favorite.source == source)
            .where(Favorite.external_id == external_id)
        )
        if existing is not None:
            session.delete(existing)
            session.commit()
            return False

        session.add(Favorite(user_id=user_id, source=source, external_id=external_id))
        session.commit()
        return True


def enqueue_scrape_request(query_text: str) -> EnqueueResult:
    now = datetime.now(timezone.utc)
    threshold = now - timedelta(seconds=SETTINGS.scrape_trigger_debounce_seconds)
    clean_query = _normalize_text(query_text)

    try:
        with SessionLocal() as session:
            pending_count = (
                session.scalar(
                    select(func.count())
                    .select_from(ScrapeRequest)
                    .where(ScrapeRequest.source == "carsensor")
                    .where(ScrapeRequest.status == "pending")
                )
                or 0
            )
            if pending_count >= SETTINGS.bot_max_pending_scrape_requests:
                return EnqueueResult(False, "queue_full")

            existing = (
                session.scalar(
                    select(func.count())
                    .select_from(ScrapeRequest)
                    .where(ScrapeRequest.source == "carsensor")
                    .where(ScrapeRequest.status == "pending")
                    .where(ScrapeRequest.requested_at >= threshold)
                    .where(ScrapeRequest.query_text == clean_query)
                )
                or 0
            )
            if existing > 0:
                return EnqueueResult(False, "duplicate")

            session.add(
                ScrapeRequest(
                    source="carsensor",
                    requested_by="telegram_bot",
                    query_text=clean_query,
                    status="pending",
                )
            )
            session.commit()
            return EnqueueResult(True, "queued")
    except Exception:
        logger.exception("Failed to enqueue scrape request")
        return EnqueueResult(False, "error")
