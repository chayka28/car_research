import json
import logging
import re
from typing import Any

from openai import OpenAI

from app.config import SETTINGS
from app.schemas import SearchFilters

logger = logging.getLogger(__name__)


_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "extract_car_filters",
        "description": "Extract car filters from user text for PostgreSQL search.",
        "parameters": {
            "type": "object",
            "properties": {
                "make": {"type": ["string", "null"]},
                "model": {"type": ["string", "null"]},
                "color": {"type": ["string", "null"]},
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
    "Extract car search filters from a user query. "
    "Return only function arguments. "
    "Normalize make and color to English. "
    "Money values must be integer RUB. "
    "If unknown, return null. "
    "Sort: newest | price_asc | price_desc."
)

_MAKE_ALIASES = {
    "toyota": "Toyota",
    "тойота": "Toyota",
    "nissan": "Nissan",
    "ниссан": "Nissan",
    "honda": "Honda",
    "хонда": "Honda",
    "mazda": "Mazda",
    "мазда": "Mazda",
    "subaru": "Subaru",
    "субару": "Subaru",
    "mitsubishi": "Mitsubishi",
    "митсубиси": "Mitsubishi",
    "suzuki": "Suzuki",
    "сузуки": "Suzuki",
    "daihatsu": "Daihatsu",
    "daihatsu": "Daihatsu",
    "lexus": "Lexus",
    "лексус": "Lexus",
    "bmw": "BMW",
    "бмв": "BMW",
    "бэха": "BMW",
    "беха": "BMW",
    "бэха": "BMW",
    "бэху": "BMW",
    "mercedes": "Mercedes-Benz",
    "mercedes-benz": "Mercedes-Benz",
    "мерседес": "Mercedes-Benz",
    "audi": "Audi",
    "фиат": "Fiat",
    "fiat": "Fiat",
    "tesla": "Tesla",
    "тесла": "Tesla",
    "volkswagen": "Volkswagen",
    "vw": "Volkswagen",
    "фольксваген": "Volkswagen",
}

_COLOR_ALIASES = {
    "black": "Black",
    "черн": "Black",
    "white": "White",
    "бел": "White",
    "red": "Red",
    "красн": "Red",
    "blue": "Blue",
    "син": "Blue",
    "gray": "Gray",
    "grey": "Gray",
    "сер": "Gray",
    "silver": "Silver",
    "сереб": "Silver",
    "yellow": "Yellow",
    "желт": "Yellow",
    "green": "Green",
    "зелен": "Green",
    "orange": "Orange",
    "оранж": "Orange",
    "brown": "Brown",
    "корич": "Brown",
    "beige": "Beige",
    "беж": "Beige",
}

_PRICE_RANGE_RE = re.compile(
    r"(до|от)\s*([0-9][0-9\s]*(?:[.,][0-9]+)?)\s*(млн|мил|миллион|лям|лямчик|million|m|тыс|k|к)?",
    re.IGNORECASE,
)
_GENERIC_BUDGET_RE = re.compile(
    r"([0-9][0-9\s]*(?:[.,][0-9]+)?)\s*(млн|мил|миллион|лям|лямчик|million|m|тыс|k|к)",
    re.IGNORECASE,
)
_YEAR_PLUS_RE = re.compile(r"\b(19\d{2}|20\d{2})\s*\+", re.IGNORECASE)
_YEAR_RANGE_RE = re.compile(r"\b(19\d{2}|20\d{2})\s*[-–]\s*(19\d{2}|20\d{2})\b")
_YEAR_MAX_RE = re.compile(r"(?:до|не старше)\s*(19\d{2}|20\d{2})", re.IGNORECASE)
_YEAR_MIN_RE = re.compile(r"(?:от|с)\s*(19\d{2}|20\d{2})", re.IGNORECASE)
_EXCLUDE_SEGMENT_RE = re.compile(
    r"(?:^|[\s,.;:!?()\-])(?:не|кроме|без|not|except|without)\s+([^.;\n]+)",
    re.IGNORECASE,
)


def _normalize_make(value: str | None) -> str | None:
    if value is None:
        return None
    source = value.strip().lower()
    if not source:
        return None
    for key, normalized in _MAKE_ALIASES.items():
        if key in source:
            return normalized
    return value.strip().title()


def _normalize_color(value: str | None) -> str | None:
    if value is None:
        return None
    source = value.strip().lower()
    if not source:
        return None
    for key, normalized in _COLOR_ALIASES.items():
        if key in source:
            return normalized
    return value.strip().title()


def _normalize_color_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        if not isinstance(item, str):
            continue
        normalized = _normalize_color(item)
        if normalized and normalized not in out:
            out.append(normalized)
    return out


def _to_opt_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(round(value))
    if isinstance(value, str):
        text = value.replace(" ", "").replace(",", ".").strip()
        if not text:
            return None
        try:
            return int(round(float(text)))
        except ValueError:
            return None
    return None


def _parse_amount(number_text: str, unit: str | None) -> int | None:
    normalized = number_text.replace(" ", "").replace(",", ".")
    try:
        value = float(normalized)
    except ValueError:
        return None

    if unit is None:
        if value < 10_000:
            return None
        return int(round(value))

    unit_l = unit.lower()
    if unit_l in {"млн", "мил", "миллион", "лям", "лямчик", "million", "m"}:
        return int(round(value * 1_000_000))
    if unit_l in {"тыс", "k", "к"}:
        return int(round(value * 1_000))
    return int(round(value))


def _fallback_parse(text: str) -> SearchFilters:
    source = text.lower()
    filters = SearchFilters()

    for key, make in _MAKE_ALIASES.items():
        if key in source:
            filters.make = make
            break

    includes: list[str] = []
    for key, color in _COLOR_ALIASES.items():
        if key in source:
            includes.append(color)
    if includes:
        filters.color = includes[0]

    excludes: list[str] = []
    for match in _EXCLUDE_SEGMENT_RE.finditer(source):
        fragment = match.group(1)
        fragment = re.split(r"\b(до|от|но)\b", fragment, maxsplit=1)[0]
        for key, color in _COLOR_ALIASES.items():
            if key in fragment and color not in excludes:
                excludes.append(color)
    if filters.color in excludes:
        excludes = [item for item in excludes if item != filters.color]
    filters.exclude_colors = excludes

    for match in _PRICE_RANGE_RE.finditer(source):
        boundary = match.group(1).lower()
        amount = _parse_amount(match.group(2), match.group(3))
        if amount is None:
            continue
        if boundary == "до":
            filters.price_max_rub = amount if filters.price_max_rub is None else min(filters.price_max_rub, amount)
        else:
            filters.price_min_rub = amount if filters.price_min_rub is None else max(filters.price_min_rub, amount)

    if filters.price_max_rub is None and filters.price_min_rub is None:
        generic = _GENERIC_BUDGET_RE.search(source)
        if generic:
            amount = _parse_amount(generic.group(1), generic.group(2))
            if amount is not None:
                filters.price_max_rub = amount

    year_range = _YEAR_RANGE_RE.search(source)
    if year_range:
        filters.year_min = int(year_range.group(1))
        filters.year_max = int(year_range.group(2))
    else:
        year_plus = _YEAR_PLUS_RE.search(source)
        if year_plus:
            filters.year_min = int(year_plus.group(1))
        year_min = _YEAR_MIN_RE.search(source)
        if year_min:
            value = int(year_min.group(1))
            if filters.year_min is None:
                filters.year_min = value
        year_max = _YEAR_MAX_RE.search(source)
        if year_max:
            value = int(year_max.group(1))
            if filters.year_max is None:
                filters.year_max = value

    if "сначала деш" in source or "дешев" in source:
        filters.sort = "price_asc"
    elif "дорож" in source:
        filters.sort = "price_desc"
    else:
        filters.sort = "newest"

    return filters


def _normalize_payload(payload: dict[str, Any], fallback_text: str) -> SearchFilters:
    filters = SearchFilters(
        make=_normalize_make(payload.get("make")) if isinstance(payload.get("make"), str) else None,
        model=payload.get("model").strip() if isinstance(payload.get("model"), str) and payload.get("model").strip() else None,
        color=_normalize_color(payload.get("color")) if isinstance(payload.get("color"), str) else None,
        exclude_colors=_normalize_color_list(payload.get("exclude_colors")),
        year_min=_to_opt_int(payload.get("year_min")),
        year_max=_to_opt_int(payload.get("year_max")),
        price_min_rub=_to_opt_int(payload.get("price_min_rub")),
        price_max_rub=_to_opt_int(payload.get("price_max_rub")),
        sort=payload.get("sort") if payload.get("sort") in {"newest", "price_asc", "price_desc"} else "newest",
    )
    if filters.is_empty():
        return _fallback_parse(fallback_text)
    return filters


def extract_filters(user_text: str) -> SearchFilters:
    if not SETTINGS.llm_enabled or SETTINGS.openai_api_key is None:
        return _fallback_parse(user_text)

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
            logger.warning("LLM returned no tool calls; fallback parser used.")
            return _fallback_parse(user_text)

        payload = json.loads(tool_calls[0].function.arguments or "{}")
        if not isinstance(payload, dict):
            payload = {}
        return _normalize_payload(payload, user_text)
    except Exception:
        logger.warning("Failed to parse filters through OpenAI; fallback parser used.")
        return _fallback_parse(user_text)
