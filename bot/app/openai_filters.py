from __future__ import annotations

import json
import logging
import re
from typing import Any

try:
    from openai import OpenAI
except Exception:  # pragma: no cover - fallback path for environments without openai package
    OpenAI = None

from app.config import SETTINGS
from app.schemas import SearchFilters

logger = logging.getLogger(__name__)

_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "extract_car_filters",
        "description": "Extract car search filters for database query.",
        "parameters": {
            "type": "object",
            "properties": {
                "makes": {"type": "array", "items": {"type": "string"}},
                "models": {"type": "array", "items": {"type": "string"}},
                "colors": {"type": "array", "items": {"type": "string"}},
                "exclude_colors": {"type": "array", "items": {"type": "string"}},
                "year_min": {"type": ["integer", "null"]},
                "year_max": {"type": ["integer", "null"]},
                "price_min_rub": {"type": ["integer", "null"]},
                "price_max_rub": {"type": ["integer", "null"]},
                "sort": {"type": "string", "enum": ["newest", "price_asc", "price_desc"]},
            },
        },
    },
}

_SYSTEM_PROMPT = (
    "Extract filters from user query for searching car listings in PostgreSQL. "
    "Return function arguments only. "
    "Normalize make/model/color to English when possible. "
    "Price values must be integer RUB."
)

_MAKE_ALIASES = {
    "bmw": "BMW",
    "бмв": "BMW",
    "бэха": "BMW",
    "беха": "BMW",
    "мерс": "Mercedes-Benz",
    "мерседес": "Mercedes-Benz",
    "mercedes": "Mercedes-Benz",
    "mercedes-benz": "Mercedes-Benz",
    "тойота": "Toyota",
    "toyota": "Toyota",
    "ниссан": "Nissan",
    "nissan": "Nissan",
    "хонда": "Honda",
    "honda": "Honda",
    "мазда": "Mazda",
    "mazda": "Mazda",
    "субару": "Subaru",
    "subaru": "Subaru",
    "лексус": "Lexus",
    "lexus": "Lexus",
    "ауди": "Audi",
    "audi": "Audi",
    "фольксваген": "Volkswagen",
    "volkswagen": "Volkswagen",
    "vw": "Volkswagen",
    "сузуки": "Suzuki",
    "suzuki": "Suzuki",
    "митсубиси": "Mitsubishi",
    "mitsubishi": "Mitsubishi",
    "дайхатсу": "Daihatsu",
    "daihatsu": "Daihatsu",
}

_COLOR_ALIASES = {
    "черн": "Black",
    "black": "Black",
    "бел": "White",
    "white": "White",
    "красн": "Red",
    "red": "Red",
    "син": "Blue",
    "blue": "Blue",
    "голуб": "Blue",
    "сер": "Gray",
    "gray": "Gray",
    "grey": "Gray",
    "сереб": "Silver",
    "silver": "Silver",
    "желт": "Yellow",
    "yellow": "Yellow",
    "зелен": "Green",
    "green": "Green",
    "оранж": "Orange",
    "orange": "Orange",
    "корич": "Brown",
    "brown": "Brown",
    "беж": "Beige",
    "beige": "Beige",
}

_PRICE_RANGE_RE = re.compile(
    r"(до|от)\s*([0-9][0-9\s]*(?:[.,][0-9]+)?)\s*(млн|мил|миллион|лям|лямчик|m|тыс|к|k)?",
    re.IGNORECASE,
)
_GENERIC_BUDGET_RE = re.compile(
    r"([0-9][0-9\s]*(?:[.,][0-9]+)?)\s*(млн|мил|миллион|лям|лямчик|m|тыс|к|k)",
    re.IGNORECASE,
)
_YEAR_PLUS_RE = re.compile(r"\b(19\d{2}|20\d{2})\s*\+", re.IGNORECASE)
_YEAR_RANGE_RE = re.compile(r"\b(19\d{2}|20\d{2})\s*[-–]\s*(19\d{2}|20\d{2})\b")
_YEAR_MAX_RE = re.compile(r"(?:до|не старше)\s*(19\d{2}|20\d{2})", re.IGNORECASE)
_YEAR_MIN_RE = re.compile(r"(?:от|с)\s*(19\d{2}|20\d{2})", re.IGNORECASE)
_EXCLUDE_SEGMENT_RE = re.compile(r"(?:^|[\s,.;:!?()\-])(?:не|кроме|без|not|except|without)\s+([^.;\n]+)", re.IGNORECASE)


def _unique(values: list[str]) -> list[str]:
    out: list[str] = []
    for item in values:
        cleaned = item.strip()
        if cleaned and cleaned not in out:
            out.append(cleaned)
    return out


def _normalize_make(value: str | None) -> str | None:
    if not value:
        return None
    source = value.strip().lower()
    for key, mapped in _MAKE_ALIASES.items():
        if key in source:
            return mapped
    if len(source) <= 4 and source.isalpha():
        return source.upper()
    return value.strip().title()


def _normalize_color(value: str | None) -> str | None:
    if not value:
        return None
    source = value.strip().lower()
    for key, mapped in _COLOR_ALIASES.items():
        if key in source:
            return mapped
    return value.strip().title()


def _to_opt_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(round(value))
    if isinstance(value, str):
        normalized = value.replace(" ", "").replace(",", ".").strip()
        if not normalized:
            return None
        try:
            return int(round(float(normalized)))
        except ValueError:
            return None
    return None


def _parse_amount(number_text: str, unit: str | None) -> int | None:
    normalized = number_text.replace(" ", "").replace(",", ".")
    try:
        value = float(normalized)
    except ValueError:
        return None

    if not unit:
        return int(round(value)) if value >= 10_000 else None

    u = unit.lower()
    if u in {"млн", "мил", "миллион", "лям", "лямчик", "m"}:
        return int(round(value * 1_000_000))
    if u in {"тыс", "к", "k"}:
        return int(round(value * 1_000))
    return int(round(value))


def _extract_aliases(source: str, aliases: dict[str, str], normalizer) -> list[str]:
    found: list[str] = []
    for key, mapped in aliases.items():
        if key in source:
            normalized = normalizer(mapped)
            if normalized and normalized not in found:
                found.append(normalized)
    return found


def _fallback_parse(text: str) -> SearchFilters:
    source = text.lower()
    filters = SearchFilters()

    filters.makes = _extract_aliases(source, _MAKE_ALIASES, _normalize_make)
    filters.colors = _extract_aliases(source, _COLOR_ALIASES, _normalize_color)

    excluded: list[str] = []
    for match in _EXCLUDE_SEGMENT_RE.finditer(source):
        fragment = match.group(1)
        fragment = re.split(r"\b(до|от|но)\b", fragment, maxsplit=1)[0]
        excluded.extend(_extract_aliases(fragment, _COLOR_ALIASES, _normalize_color))
    filters.exclude_colors = _unique(excluded)
    filters.colors = [item for item in filters.colors if item not in filters.exclude_colors]

    for match in _PRICE_RANGE_RE.finditer(source):
        bound = match.group(1).lower()
        amount = _parse_amount(match.group(2), match.group(3))
        if amount is None:
            continue
        if bound == "до":
            filters.price_max_rub = amount if filters.price_max_rub is None else min(filters.price_max_rub, amount)
        else:
            filters.price_min_rub = amount if filters.price_min_rub is None else max(filters.price_min_rub, amount)

    if filters.price_min_rub is None and filters.price_max_rub is None:
        generic = _GENERIC_BUDGET_RE.search(source)
        if generic:
            amount = _parse_amount(generic.group(1), generic.group(2))
            if amount is not None:
                filters.price_max_rub = amount

    range_match = _YEAR_RANGE_RE.search(source)
    if range_match:
        filters.year_min = int(range_match.group(1))
        filters.year_max = int(range_match.group(2))
    else:
        plus_match = _YEAR_PLUS_RE.search(source)
        if plus_match:
            filters.year_min = int(plus_match.group(1))
        min_match = _YEAR_MIN_RE.search(source)
        if min_match and filters.year_min is None:
            filters.year_min = int(min_match.group(1))
        max_match = _YEAR_MAX_RE.search(source)
        if max_match and filters.year_max is None:
            filters.year_max = int(max_match.group(1))

    if any(word in source for word in ("дешевле", "подешевле", "минимальная цена")):
        filters.sort = "price_asc"
    elif any(word in source for word in ("дороже", "подороже", "максимальная цена")):
        filters.sort = "price_desc"
    else:
        filters.sort = "newest"

    return filters


def _to_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        item = value.strip()
        return [item] if item else []
    if isinstance(value, list):
        out: list[str] = []
        for item in value:
            if isinstance(item, str) and item.strip():
                out.append(item.strip())
        return out
    return []


def _normalize_payload(payload: dict[str, Any]) -> SearchFilters:
    makes = [_normalize_make(item) for item in _to_list(payload.get("makes"))]
    if not makes and isinstance(payload.get("make"), str):
        single = _normalize_make(payload.get("make"))
        if single:
            makes = [single]

    models = _unique(_to_list(payload.get("models")))
    if not models and isinstance(payload.get("model"), str) and payload.get("model").strip():
        models = [payload.get("model").strip()]

    colors = [_normalize_color(item) for item in _to_list(payload.get("colors"))]
    if not colors and isinstance(payload.get("color"), str):
        single_color = _normalize_color(payload.get("color"))
        if single_color:
            colors = [single_color]

    exclude_colors = [_normalize_color(item) for item in _to_list(payload.get("exclude_colors"))]

    return SearchFilters(
        makes=_unique([item for item in makes if item]),
        models=_unique([item for item in models if item]),
        colors=_unique([item for item in colors if item]),
        exclude_colors=_unique([item for item in exclude_colors if item]),
        year_min=_to_opt_int(payload.get("year_min")),
        year_max=_to_opt_int(payload.get("year_max")),
        price_min_rub=_to_opt_int(payload.get("price_min_rub")),
        price_max_rub=_to_opt_int(payload.get("price_max_rub")),
        sort=payload.get("sort") if payload.get("sort") in {"newest", "price_asc", "price_desc"} else "newest",
    )


def _merge_filters(base: SearchFilters, llm: SearchFilters) -> SearchFilters:
    merged = SearchFilters()
    merged.makes = _unique(base.makes + llm.makes)
    merged.models = _unique(base.models + llm.models)
    merged.colors = _unique(base.colors + llm.colors)
    merged.exclude_colors = _unique(base.exclude_colors + llm.exclude_colors)
    merged.colors = [item for item in merged.colors if item not in merged.exclude_colors]

    if base.year_min is not None and llm.year_min is not None:
        merged.year_min = max(base.year_min, llm.year_min)
    else:
        merged.year_min = base.year_min if base.year_min is not None else llm.year_min

    if base.year_max is not None and llm.year_max is not None:
        merged.year_max = min(base.year_max, llm.year_max)
    else:
        merged.year_max = base.year_max if base.year_max is not None else llm.year_max

    if base.price_min_rub is not None and llm.price_min_rub is not None:
        merged.price_min_rub = max(base.price_min_rub, llm.price_min_rub)
    else:
        merged.price_min_rub = base.price_min_rub if base.price_min_rub is not None else llm.price_min_rub

    if base.price_max_rub is not None and llm.price_max_rub is not None:
        merged.price_max_rub = min(base.price_max_rub, llm.price_max_rub)
    else:
        merged.price_max_rub = base.price_max_rub if base.price_max_rub is not None else llm.price_max_rub

    merged.sort = llm.sort if llm.sort != "newest" else base.sort
    return merged


def extract_filters(user_text: str) -> SearchFilters:
    fallback = _fallback_parse(user_text)
    if OpenAI is None:
        return fallback
    if not SETTINGS.llm_enabled or SETTINGS.openai_api_key is None:
        return fallback

    client = OpenAI(api_key=SETTINGS.openai_api_key)
    try:
        completion = client.chat.completions.create(
            model=SETTINGS.openai_model,
            temperature=0,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_text},
            ],
            tools=[_TOOL_SCHEMA],
            tool_choice={"type": "function", "function": {"name": "extract_car_filters"}},
        )
        message = completion.choices[0].message
        tool_calls = message.tool_calls or []
        if not tool_calls:
            return fallback

        payload = json.loads(tool_calls[0].function.arguments or "{}")
        if not isinstance(payload, dict):
            return fallback

        llm_filters = _normalize_payload(payload)
        merged = _merge_filters(fallback, llm_filters)
        return merged if not merged.is_empty() else fallback
    except Exception:
        logger.warning("OpenAI filter extraction failed, fallback parser used.", exc_info=True)
        return fallback
