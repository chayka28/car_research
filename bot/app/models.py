from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Listing(Base):
    __tablename__ = "listings"

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(32), index=True)
    external_id: Mapped[str] = mapped_column(String(32), index=True)
    url: Mapped[str] = mapped_column(String(512))

    maker: Mapped[str] = mapped_column(String(128))
    model: Mapped[str] = mapped_column(String(128))
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

    scraped_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, index=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ScrapeRequest(Base):
    __tablename__ = "scrape_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(32), default="carsensor", nullable=False, index=True)
    requested_by: Mapped[str] = mapped_column(String(64), nullable=False, default="telegram_bot")
    query_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending", index=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), index=True)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
