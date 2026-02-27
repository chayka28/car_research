from datetime import datetime, timezone

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Listing(Base):
    __tablename__ = "listings"
    __table_args__ = (UniqueConstraint("source", "external_id", name="uq_listings_source_external_id"),)

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    external_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    url: Mapped[str] = mapped_column(String(512), nullable=False)

    maker: Mapped[str] = mapped_column(String(128), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    grade: Mapped[str | None] = mapped_column(String(256), nullable=True)
    color: Mapped[str | None] = mapped_column(String(128), nullable=True)

    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mileage_km: Mapped[int | None] = mapped_column(Integer, nullable=True)
    price_jpy: Mapped[int | None] = mapped_column(Integer, nullable=True)
    price_rub: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_price_jpy: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_price_rub: Mapped[int | None] = mapped_column(Integer, nullable=True)

    prefecture: Mapped[str | None] = mapped_column(String(128), nullable=True)
    shop_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    shop_address: Mapped[str | None] = mapped_column(String(512), nullable=True)
    shop_phone: Mapped[str | None] = mapped_column(String(64), nullable=True)

    transmission: Mapped[str | None] = mapped_column(String(128), nullable=True)
    drive_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    engine_cc: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fuel: Mapped[str | None] = mapped_column(String(128), nullable=True)
    steering: Mapped[str | None] = mapped_column(String(64), nullable=True)
    body_type: Mapped[str | None] = mapped_column(String(128), nullable=True)

    scraped_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class FailedScrape(Base):
    __tablename__ = "failed_scrapes"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    url: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    source_listing_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    error_type: Mapped[str] = mapped_column(String(64), nullable=False)
    message: Mapped[str] = mapped_column(String(512), nullable=False)
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    debug_snippet: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, index=True)


class ScrapeRequest(Base):
    __tablename__ = "scrape_requests"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="carsensor", index=True)
    requested_by: Mapped[str] = mapped_column(String(64), nullable=False, default="telegram_bot")
    query_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending", index=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, index=True)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Favorite(Base):
    __tablename__ = "favorites"
    __table_args__ = (
        UniqueConstraint("user_id", "source", "external_id", name="uq_favorites_user_source_external_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="carsensor", index=True)
    external_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, index=True)
