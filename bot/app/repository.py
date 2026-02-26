from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, or_, select

from app.config import SETTINGS
from app.db import SessionLocal
from app.models import Listing, ScrapeRequest
from app.schemas import ListingCard, SearchFilters


def _norm(term: str) -> str:
    return term.strip().lower()


def _price_rub(row: Listing) -> int | None:
    if row.total_price_rub and row.total_price_rub > 0:
        return row.total_price_rub
    if row.price_rub and row.price_rub > 0:
        return row.price_rub
    if row.total_price_jpy and row.total_price_jpy > 0:
        return int(round(row.total_price_jpy * SETTINGS.jpy_to_rub_rate))
    if row.price_jpy and row.price_jpy > 0:
        return int(round(row.price_jpy * SETTINGS.jpy_to_rub_rate))
    return None


def _card_from_row(row: Listing) -> ListingCard:
    return ListingCard(
        id=row.id,
        external_id=row.external_id,
        source=row.source,
        url=row.url,
        maker=row.maker,
        model=row.model,
        grade=row.grade,
        color=row.color,
        year=row.year,
        mileage_km=row.mileage_km,
        price_jpy=row.price_jpy,
        price_rub=row.price_rub,
        total_price_jpy=row.total_price_jpy,
        total_price_rub=row.total_price_rub,
        effective_price_rub=_price_rub(row),
        prefecture=row.prefecture,
        shop_name=row.shop_name,
        shop_address=row.shop_address,
        shop_phone=row.shop_phone,
        transmission=row.transmission,
        drive_type=row.drive_type,
        engine_cc=row.engine_cc,
        fuel=row.fuel,
        steering=row.steering,
        body_type=row.body_type,
        is_active=row.is_active,
        last_seen_at=row.last_seen_at,
    )


def search_listings(filters: SearchFilters, limit: int) -> list[ListingCard]:
    like = lambda value: f"%{_norm(value)}%"  # noqa: E731

    with SessionLocal() as session:
        stmt = (
            select(Listing)
            .where(Listing.source == "carsensor")
            .where(Listing.deleted_at.is_(None))
            .where(Listing.maker != "Unknown")
            .where(Listing.model != "Unknown")
        )

        if filters.only_active:
            stmt = stmt.where(Listing.is_active.is_(True))

        if filters.include_makes:
            stmt = stmt.where(or_(*[func.lower(Listing.maker).like(like(item)) for item in filters.include_makes]))
        if filters.include_models:
            stmt = stmt.where(or_(*[func.lower(Listing.model).like(like(item)) for item in filters.include_models]))
        if filters.include_colors:
            stmt = stmt.where(
                or_(*[func.lower(func.coalesce(Listing.color, "")).like(like(item)) for item in filters.include_colors])
            )

        for item in filters.exclude_makes:
            stmt = stmt.where(func.lower(Listing.maker).not_like(like(item)))
        for item in filters.exclude_models:
            stmt = stmt.where(func.lower(Listing.model).not_like(like(item)))
        for item in filters.exclude_colors:
            stmt = stmt.where(func.lower(func.coalesce(Listing.color, "")).not_like(like(item)))

        if filters.min_year is not None:
            stmt = stmt.where(Listing.year.is_not(None)).where(Listing.year >= filters.min_year)
        if filters.max_year is not None:
            stmt = stmt.where(Listing.year.is_not(None)).where(Listing.year <= filters.max_year)

        preload_limit = max(limit * 8, 200)
        rows = session.scalars(stmt.order_by(Listing.last_seen_at.desc(), Listing.id.desc()).limit(preload_limit)).all()

    cards: list[ListingCard] = []
    for row in rows:
        card = _card_from_row(row)

        if filters.max_price_rub is not None and (card.effective_price_rub is None or card.effective_price_rub > filters.max_price_rub):
            continue
        if filters.min_price_rub is not None and (card.effective_price_rub is None or card.effective_price_rub < filters.min_price_rub):
            continue

        cards.append(card)
        if len(cards) >= limit:
            break

    return cards


def enqueue_scrape_request(query_text: str) -> bool:
    now = datetime.now(timezone.utc)
    threshold = now - timedelta(seconds=SETTINGS.scrape_trigger_debounce_seconds)

    with SessionLocal() as session:
        existing = (
            session.scalar(
                select(func.count())
                .select_from(ScrapeRequest)
                .where(ScrapeRequest.status == "pending")
                .where(ScrapeRequest.requested_at >= threshold)
                .where(ScrapeRequest.query_text == query_text)
            )
            or 0
        )

        if existing > 0:
            return False

        session.add(
            ScrapeRequest(
                source="carsensor",
                requested_by="telegram_bot",
                query_text=query_text,
                status="pending",
            )
        )
        session.commit()
        return True
