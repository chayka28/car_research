from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal


SortType = Literal["newest", "price_asc", "price_desc"]


@dataclass
class SearchFilters:
    make: str | None = None
    model: str | None = None
    color: str | None = None
    exclude_colors: list[str] = field(default_factory=list)
    year_min: int | None = None
    year_max: int | None = None
    price_min_rub: int | None = None
    price_max_rub: int | None = None
    sort: SortType = "newest"
    only_active: bool = True

    def is_empty(self) -> bool:
        return (
            self.make is None
            and self.model is None
            and self.color is None
            and not self.exclude_colors
            and self.year_min is None
            and self.year_max is None
            and self.price_min_rub is None
            and self.price_max_rub is None
        )

    def clear(self) -> None:
        self.make = None
        self.model = None
        self.color = None
        self.exclude_colors = []
        self.year_min = None
        self.year_max = None
        self.price_min_rub = None
        self.price_max_rub = None
        self.sort = "newest"
        self.only_active = True


@dataclass
class ListingCard:
    id: int
    external_id: str
    source: str
    url: str
    maker: str
    model: str
    year: int | None
    color: str | None
    price_rub: int | None
    last_seen_at: datetime | None
    is_active: bool


@dataclass
class PagedResult:
    items: list[ListingCard]
    total: int
    page: int
    pages: int
