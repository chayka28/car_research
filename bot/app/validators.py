from __future__ import annotations

import re

from app.schemas import SearchFilters

_SKIP_TOKENS = {"-", "нет", "none", "skip", "пропустить"}
_MONEY_CLEAN_RE = re.compile(r"(?:₽|руб\.?|rur|rub)", re.IGNORECASE)
_MONEY_VALUE_RE = re.compile(r"^\s*([0-9][0-9\s]*(?:[.,][0-9]+)?)\s*([a-zа-яё]+)?\s*$", re.IGNORECASE)


def parse_optional_year(value: str) -> int | None:
    text = value.strip().lower()
    if text in _SKIP_TOKENS or not text:
        return None
    normalized = text.replace(" ", "")
    if not normalized.isdigit():
        raise ValueError("Введите год числом или '-' для пропуска.")
    year = int(normalized)
    if year < 1950 or year > 2100:
        raise ValueError("Год должен быть в диапазоне 1950..2100.")
    return year


def parse_optional_rub(value: str) -> int | None:
    text = value.strip().lower()
    if text in _SKIP_TOKENS or not text:
        return None

    cleaned = _MONEY_CLEAN_RE.sub("", text).strip()
    match = _MONEY_VALUE_RE.match(cleaned)
    if not match:
        raise ValueError("Введите цену в RUB: 2000000, 2 000 000, 2м, 2 млн.")

    raw_value = match.group(1).replace(" ", "").replace(",", ".")
    unit = (match.group(2) or "").strip()

    try:
        number = float(raw_value)
    except ValueError as exc:
        raise ValueError("Не удалось распознать цену.") from exc

    multiplier = 1
    if unit in {"м", "млн", "мил", "миллион", "миллиона", "лям", "ляма", "лямчик", "m", "mln"}:
        multiplier = 1_000_000
    elif unit in {"к", "тыс", "тысяч", "k"}:
        multiplier = 1_000

    value_rub = int(round(number * multiplier))
    if value_rub < 0:
        raise ValueError("Цена не может быть отрицательной.")
    return value_rub


def validate_filters(filters: SearchFilters) -> list[str]:
    errors: list[str] = []
    if filters.year_min is not None and filters.year_max is not None and filters.year_min > filters.year_max:
        errors.append("Минимальный год не может быть больше максимального.")
    if (
        filters.price_min_rub is not None
        and filters.price_max_rub is not None
        and filters.price_min_rub > filters.price_max_rub
    ):
        errors.append("Минимальная цена не может быть больше максимальной.")
    return errors


# Smoke cases for quick manual verification:
# parse_optional_rub("2м") -> 2000000
# parse_optional_rub("2 000 000") -> 2000000
# validate_filters(SearchFilters(year_min=2010, year_max=2000)) -> ["...больше..."]
