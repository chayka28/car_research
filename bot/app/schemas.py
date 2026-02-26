from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class SearchFilters:
    include_makes: list[str] = field(default_factory=list)
    exclude_makes: list[str] = field(default_factory=list)
    include_models: list[str] = field(default_factory=list)
    exclude_models: list[str] = field(default_factory=list)
    include_colors: list[str] = field(default_factory=list)
    exclude_colors: list[str] = field(default_factory=list)

    max_price_rub: int | None = None
    min_price_rub: int | None = None
    min_year: int | None = None
    max_year: int | None = None

    only_active: bool = True


@dataclass
class ListingCard:
    id: int
    external_id: str
    source: str
    url: str

    maker: str
    model: str
    grade: str | None
    color: str | None
    year: int | None
    mileage_km: int | None

    price_jpy: int | None
    price_rub: int | None
    total_price_jpy: int | None
    total_price_rub: int | None
    effective_price_rub: int | None

    prefecture: str | None
    shop_name: str | None
    shop_address: str | None
    shop_phone: str | None

    transmission: str | None
    drive_type: str | None
    engine_cc: int | None
    fuel: str | None
    steering: str | None
    body_type: str | None

    is_active: bool
    last_seen_at: datetime
