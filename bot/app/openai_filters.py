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
        "description": "Extract structured filters for searching car listings in PostgreSQL.",
        "parameters": {
            "type": "object",
            "properties": {
                "include_makes": {"type": "array", "items": {"type": "string"}},
                "exclude_makes": {"type": "array", "items": {"type": "string"}},
                "include_models": {"type": "array", "items": {"type": "string"}},
                "exclude_models": {"type": "array", "items": {"type": "string"}},
                "include_colors": {"type": "array", "items": {"type": "string"}},
                "exclude_colors": {"type": "array", "items": {"type": "string"}},
                "max_price_rub": {"type": ["integer", "null"]},
                "min_price_rub": {"type": ["integer", "null"]},
                "min_year": {"type": ["integer", "null"]},
                "max_year": {"type": ["integer", "null"]},
                "only_active": {"type": "boolean"},
            },
        },
    },
}

_SYSTEM_PROMPT = (
    "You extract car search filters from user text. "
    "Output only via function call. "
    "Normalize makes/models/colors to English because DB values are in English. "
    "For money, return integer RUB in max_price_rub/min_price_rub. "
    "Examples: 'до 2 миллионов' => 2000000, '10 лямчиков' => 10000000. "
    "If user says 'not red', put it into exclude_colors. "
    "Default only_active=true."
)


_MILLION_HINT_RE = re.compile(r"(\d+(?:[\.,]\d+)?)\s*(млн|мил|миллион|лям|лямчик|million|m)", re.IGNORECASE)
_NUMBER_HINT_RE = re.compile(r"до\s*(\d{2,9})", re.IGNORECASE)
_PRICE_RANGE_RE = re.compile(
    r"(до|от)\s*([0-9][0-9\s]*(?:[\.,][0-9]+)?)\s*(млн|мил|миллион|лям|лямчик|million|m)?",
    re.IGNORECASE,
)
_EXCLUDE_SEGMENT_RE = re.compile(r"(?:не|кроме|without|except|без|not)\s+([^.;\\n]+)", re.IGNORECASE)

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
    "lexus": "Lexus",
    "лексус": "Lexus",
    "bmw": "BMW",
    "mercedes": "Mercedes-Benz",
    "мерседес": "Mercedes-Benz",
    "audi": "Audi",
    "fiat": "Fiat",
    "tesla": "Tesla",
}

_COLOR_ALIASES = {
    "white": "White",
    "бел": "White",
    "black": "Black",
    "черн": "Black",
    "red": "Red",
    "красн": "Red",
    "blue": "Blue",
    "син": "Blue",
    "gray": "Gray",
    "grey": "Gray",
    "сер": "Gray",
    "silver": "Silver",
    "сереб": "Silver",
    "green": "Green",
    "зелен": "Green",
    "yellow": "Yellow",
    "желт": "Yellow",
    "beige": "Beige",
    "беж": "Beige",
    "brown": "Brown",
    "корич": "Brown",
    "orange": "Orange",
    "оранж": "Orange",
}


def _to_clean_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        if not isinstance(item, str):
            continue
        cleaned = item.strip()
        if cleaned:
            out.append(cleaned)
    return out


def _to_opt_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(round(value))
    if isinstance(value, str):
        candidate = value.strip().replace(" ", "")
        if not candidate:
            return None
        candidate = candidate.replace(",", ".")
        try:
            return int(round(float(candidate)))
        except ValueError:
            return None
    return None


def _naive_budget_fallback(text: str) -> int | None:
    million_match = _MILLION_HINT_RE.search(text)
    if million_match:
        try:
            return int(round(float(million_match.group(1).replace(",", ".")) * 1_000_000))
        except ValueError:
            return None

    number_match = _NUMBER_HINT_RE.search(text)
    if number_match:
        try:
            return int(number_match.group(1))
        except ValueError:
            return None

    return None


def _parse_price_value(raw_number: str, unit: str | None) -> int | None:
    normalized = raw_number.replace(" ", "").replace(",", ".")
    try:
        value = float(normalized)
    except ValueError:
        return None

    if unit:
        return int(round(value * 1_000_000))
    return int(round(value))


def _extract_naive_filters(user_text: str) -> dict[str, Any]:
    text_lower = user_text.lower()

    include_makes: set[str] = set()
    exclude_makes: set[str] = set()
    include_colors: set[str] = set()
    exclude_colors: set[str] = set()

    max_price: int | None = None
    min_price: int | None = None

    for match in _PRICE_RANGE_RE.finditer(text_lower):
        boundary = match.group(1).lower()
        value = _parse_price_value(match.group(2), match.group(3))
        if value is None:
            continue
        if boundary == "до":
            max_price = value if max_price is None else min(max_price, value)
        else:
            min_price = value if min_price is None else max(min_price, value)

    if max_price is None:
        max_price = _naive_budget_fallback(text_lower)

    exclude_fragments: list[str] = []
    for match in _EXCLUDE_SEGMENT_RE.finditer(text_lower):
        fragment = match.group(1)
        fragment = re.split(r"\b(до|от|но)\b", fragment, maxsplit=1)[0]
        exclude_fragments.extend(re.split(r"(?:,|/|\s+или\s+|\s+or\s+|\s+and\s+)", fragment))

    def _match_aliases(aliases: dict[str, str], source_text: str) -> set[str]:
        found: set[str] = set()
        for key, normalized in aliases.items():
            if key in source_text:
                found.add(normalized)
        return found

    include_makes |= _match_aliases(_MAKE_ALIASES, text_lower)
    include_colors |= _match_aliases(_COLOR_ALIASES, text_lower)

    exclude_text = " ".join(exclude_fragments)
    exclude_makes |= _match_aliases(_MAKE_ALIASES, exclude_text)
    exclude_colors |= _match_aliases(_COLOR_ALIASES, exclude_text)

    include_makes -= exclude_makes
    include_colors -= exclude_colors

    return {
        "include_makes": sorted(include_makes),
        "exclude_makes": sorted(exclude_makes),
        "include_colors": sorted(include_colors),
        "exclude_colors": sorted(exclude_colors),
        "max_price_rub": max_price,
        "min_price_rub": min_price,
    }


def _normalize_filters(payload: dict[str, Any], user_text: str) -> SearchFilters:
    max_price = _to_opt_int(payload.get("max_price_rub"))
    min_price = _to_opt_int(payload.get("min_price_rub"))

    if max_price is None:
        max_price = _naive_budget_fallback(user_text)

    return SearchFilters(
        include_makes=_to_clean_list(payload.get("include_makes")),
        exclude_makes=_to_clean_list(payload.get("exclude_makes")),
        include_models=_to_clean_list(payload.get("include_models")),
        exclude_models=_to_clean_list(payload.get("exclude_models")),
        include_colors=_to_clean_list(payload.get("include_colors")),
        exclude_colors=_to_clean_list(payload.get("exclude_colors")),
        max_price_rub=max_price,
        min_price_rub=min_price,
        min_year=_to_opt_int(payload.get("min_year")),
        max_year=_to_opt_int(payload.get("max_year")),
        only_active=bool(payload.get("only_active", True)),
    )


def extract_filters(user_text: str) -> SearchFilters:
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
            logger.warning("OpenAI response has no tool calls, falling back to naive parsing.")
            return _normalize_filters(_extract_naive_filters(user_text), user_text)

        args_text = tool_calls[0].function.arguments or "{}"
        payload = json.loads(args_text)
        if not isinstance(payload, dict):
            payload = {}
        return _normalize_filters(payload, user_text)
    except Exception:
        logger.warning("Failed to extract filters via OpenAI, using fallback parser.")
        return _normalize_filters(_extract_naive_filters(user_text), user_text)
