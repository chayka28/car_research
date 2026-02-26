from datetime import datetime

from pydantic import BaseModel


class ListingOut(BaseModel):
    id: int
    external_id: str
    source: str
    brand: str
    model: str
    year: int | None
    price: int | None
    price_text: str | None
    price_jpy: int | None
    price_rub: int | None
    color: str | None
    link: str
    is_active: bool
    last_seen_at: datetime


class ListingPageOut(BaseModel):
    items: list[ListingOut]
    total: int
    page: int
    per_page: int
    pages: int
