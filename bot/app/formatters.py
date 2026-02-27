from __future__ import annotations

from html import escape

from app.schemas import ListingCard, SearchFilters


def _safe(value: object | None, default: str = "не указано") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return escape(text) if text else default


def format_rub(value: int | None) -> str:
    if value is None:
        return "price not specified"
    return f"{value:,}".replace(",", " ") + " ₽"


def _join_values(values: list[str], limit: int = 3) -> str:
    cleaned = [item for item in values if item]
    if not cleaned:
        return "-"
    if len(cleaned) <= limit:
        return ", ".join(cleaned)
    return f"{', '.join(cleaned[:limit])} +{len(cleaned) - limit}"


def build_listing_card_text(*, card: ListingCard, page: int, pages: int, photo_found: bool) -> str:
    title = f"{_safe(card.maker)} {_safe(card.model)}, {_safe(card.year)}"
    status = "Активно" if card.is_active else "Неактивно"
    photo_line = "" if photo_found else "\nФото: отсутствует"
    return "\n".join(
        [
            f"<b>{title}</b>",
            f"Цвет: {_safe(card.color)}",
            f"Цена: {format_rub(card.price_rub)}",
            f"ID: {_safe(card.external_id)}",
            f"Статус: {status}",
            photo_line,
            "",
            f"{page}/{pages}",
        ]
    ).replace("\n\n\n", "\n\n")


def build_filter_summary(filters: SearchFilters) -> str:
    return "\n".join(
        [
            f"Марки: {_join_values(filters.makes)}",
            f"Модели: {_join_values(filters.models)}",
            f"Цвета: {_join_values(filters.colors)}",
            f"Исключить цвета: {_join_values(filters.exclude_colors)}",
            f"Год: {filters.year_min or '-'} .. {filters.year_max or '-'}",
            f"Цена, ₽: {filters.price_min_rub or '-'} .. {filters.price_max_rub or '-'}",
            f"Только активные: {'да' if filters.only_active else 'нет'}",
            f"Сортировка: {filters.sort}",
        ]
    )

