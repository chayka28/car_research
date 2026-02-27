from __future__ import annotations

from html import escape

from app.schemas import ListingCard, SearchFilters

_UNKNOWN_VALUES = {"", "-", "unknown", "none", "null", "не указано", "n/a"}


def _normalize_text(value: object | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.lower() in _UNKNOWN_VALUES:
        return None
    return text


def _safe_display(value: object | None, default: str = "—") -> str:
    normalized = _normalize_text(value)
    return escape(normalized) if normalized is not None else default


def format_rub(value: int | None) -> str:
    if value is None:
        return "—"
    return f"{value:,}".replace(",", " ") + " ₽"


def _join_values(values: list[str], limit: int = 3) -> str:
    cleaned = [item for item in values if _normalize_text(item)]
    if not cleaned:
        return "-"
    if len(cleaned) <= limit:
        return ", ".join(cleaned)
    return f"{', '.join(cleaned[:limit])} +{len(cleaned) - limit}"


def build_listing_card_text(*, card: ListingCard, page: int, pages: int, photo_found: bool) -> str:
    maker = _safe_display(card.maker)
    model = _safe_display(card.model)
    year = _safe_display(card.year)
    color = _safe_display(card.color)
    external_id = _safe_display(card.external_id)
    status = "Активно" if card.is_active else "Неактивно"

    title = f"{maker} {model}".strip()
    if title == "— —":
        title = "Объявление"
    title = f"{title}, {year}" if year != "—" else title

    lines = [
        f"<b>{title}</b>",
        f"Марка: {maker}",
        f"Модель: {model}",
        f"Год: {year}",
        f"Цвет: {color}",
        f"Цена: {format_rub(card.price_rub)}",
        f"ID: {external_id}",
        f"Статус: {status}",
    ]
    if not photo_found:
        lines.append("Фото: —")
    lines.extend(["", f"{page}/{pages}"])
    return "\n".join(lines)


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

