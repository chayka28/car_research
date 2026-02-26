from __future__ import annotations

from html import escape

from app.schemas import ListingCard, SearchFilters


def _safe(value: object | None, default: str = "не указано") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return escape(text) if text else default


def _price(value: int | None) -> str:
    if value is None:
        return "price not specified"
    return f"{value:,}".replace(",", " ") + " ₽"


def build_listing_card_text(*, card: ListingCard, page: int, pages: int) -> str:
    title = f"{_safe(card.maker)} {_safe(card.model)}, {_safe(card.year)}"
    return "\n".join(
        [
            f"<b>{title}</b>",
            f"Цвет: {_safe(card.color)}",
            f"Цена: {_price(card.price_rub)}",
            f"Ссылка: {_safe(card.url)}",
            f"ID: {_safe(card.external_id)}",
            "",
            f"{page}/{pages}",
        ]
    )


def build_filter_summary(filters: SearchFilters) -> str:
    parts = [
        f"Марка: {_safe(filters.make, '-')}",
        f"Модель: {_safe(filters.model, '-')}",
        f"Цвет: {_safe(filters.color, '-')}",
        f"Исключить цвета: {', '.join(filters.exclude_colors) if filters.exclude_colors else '-'}",
        f"Год: {filters.year_min or '-'} .. {filters.year_max or '-'}",
        f"Цена, ₽: {filters.price_min_rub or '-'} .. {filters.price_max_rub or '-'}",
        f"Сортировка: {filters.sort}",
    ]
    return "\n".join(parts)
