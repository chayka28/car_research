import logging
import re
import time
from typing import Any

import requests

from app.config import (
    CARSENSOR_API_URL,
    WORKER_BACKOFF_SECONDS,
    WORKER_MAX_RETRIES,
    WORKER_REQUEST_TIMEOUT_SECONDS,
)

logger = logging.getLogger(__name__)


def _extract_items(payload: Any) -> list[Any]:
    if isinstance(payload, list):
        return payload

    if not isinstance(payload, dict):
        return []

    for key in ("items", "results", "data", "cars", "listings"):
        value = payload.get(key)
        if isinstance(value, list):
            return value

    if all(key in payload for key in ("brand", "model", "year", "price", "color", "link")):
        return [payload]

    return []


def _pick_value(item: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        value = item.get(key)
        if value is not None and value != "":
            return value
    return None


def _to_clean_str(value: Any) -> str | None:
    if value is None:
        return None
    value_str = str(value).strip()
    return value_str or None


def _to_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value

    digits = re.sub(r"[^\d-]", "", str(value))
    if not digits or digits == "-":
        return None

    try:
        return int(digits)
    except ValueError:
        return None


def fetch_payload_with_retry() -> Any:
    last_error: Exception | None = None

    for attempt in range(1, WORKER_MAX_RETRIES + 1):
        try:
            response = requests.get(CARSENSOR_API_URL, timeout=WORKER_REQUEST_TIMEOUT_SECONDS)
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError) as exc:
            last_error = exc
            if attempt >= WORKER_MAX_RETRIES:
                break

            sleep_seconds = WORKER_BACKOFF_SECONDS * (2 ** (attempt - 1))
            logger.warning(
                "Carsensor request failed (%s/%s): %s. Retry in %.1fs.",
                attempt,
                WORKER_MAX_RETRIES,
                exc,
                sleep_seconds,
            )
            time.sleep(sleep_seconds)

    raise RuntimeError("Unable to fetch data from carsensor.net after retries.") from last_error


def normalize_cars(payload: Any) -> list[dict[str, Any]]:
    items = _extract_items(payload)
    normalized: list[dict[str, Any]] = []
    skipped = 0

    for item in items:
        if not isinstance(item, dict):
            skipped += 1
            continue

        brand = _to_clean_str(_pick_value(item, ("brand", "make", "manufacturer")))
        model = _to_clean_str(_pick_value(item, ("model", "name", "model_name")))
        year = _to_int(_pick_value(item, ("year", "production_year")))
        price = _to_int(_pick_value(item, ("price", "amount", "cost", "price_value")))
        color = _to_clean_str(_pick_value(item, ("color", "colour")))
        link = _to_clean_str(_pick_value(item, ("link", "url", "source_url", "listing_url")))

        if None in (brand, model, year, price, color, link):
            skipped += 1
            continue

        normalized.append(
            {
                "brand": brand,
                "model": model,
                "year": year,
                "price": price,
                "color": color,
                "link": link,
            }
        )

    if skipped:
        logger.warning("Skipped %s records due to missing/invalid fields.", skipped)

    return normalized
