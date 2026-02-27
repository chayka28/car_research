from __future__ import annotations

import json
import logging
import time
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

import requests
from bs4 import BeautifulSoup

from app.config import SETTINGS

logger = logging.getLogger(__name__)

_CACHE_TTL_SECONDS = 60 * 30
_photo_cache: dict[str, tuple[float, str | None]] = {}


def _is_valid_photo_url(value: str | None) -> bool:
    if value is None:
        return False
    text = value.strip()
    if not text:
        return False
    if text.startswith("data:"):
        return False
    if text.startswith("//"):
        return True
    return text.startswith("http://") or text.startswith("https://") or text.startswith("/")


def _jsonld_image_candidates(soup: BeautifulSoup) -> list[str]:
    out: list[str] = []
    for node in soup.select('script[type="application/ld+json"]'):
        content = node.string or node.get_text(strip=True)
        if not content:
            continue
        try:
            payload = json.loads(content)
        except Exception:
            continue

        items = payload if isinstance(payload, list) else [payload]
        for item in items:
            if not isinstance(item, dict):
                continue
            image = item.get("image")
            if isinstance(image, str):
                out.append(image)
            elif isinstance(image, list):
                out.extend([entry for entry in image if isinstance(entry, str)])
            elif isinstance(image, dict):
                image_url = image.get("url")
                if isinstance(image_url, str):
                    out.append(image_url)
    return out


def _first_photo_url(soup: BeautifulSoup, base_url: str) -> str | None:
    selectors: list[tuple[str, str]] = [
        ('meta[property="og:image"]', "content"),
        ('meta[name="twitter:image"]', "content"),
        ('img.js-galleryMainImage', "src"),
        ('img.js-galleryMainImage', "data-src"),
        ("img.swiper-lazy", "data-src"),
        ('img[class*="gallery"]', "src"),
        ("img", "src"),
    ]
    for selector, attr in selectors:
        node = soup.select_one(selector)
        if node is None:
            continue
        raw_value = node.get(attr)
        if not _is_valid_photo_url(raw_value):
            continue
        return urljoin(base_url, raw_value)

    for raw_value in _jsonld_image_candidates(soup):
        if _is_valid_photo_url(raw_value):
            return urljoin(base_url, raw_value)

    return None


def resolve_listing_photo(listing_url: str) -> str | None:
    now = time.time()
    cached = _photo_cache.get(listing_url)
    if cached and now - cached[0] <= _CACHE_TTL_SECONDS:
        return cached[1]

    photo_url: str | None = None
    try:
        response = requests.get(
            listing_url,
            timeout=(5, SETTINGS.photo_timeout_seconds),
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                )
            },
        )
        if response.ok:
            soup = BeautifulSoup(response.text, "html.parser")
            photo_url = _first_photo_url(soup, str(response.url))
            if photo_url is None:
                logger.info("Photo not found in listing HTML: %s", listing_url)
        else:
            logger.info("Photo fetch failed with status=%s for %s", response.status_code, listing_url)
    except Exception:
        logger.warning("Photo fetch exception for %s", listing_url, exc_info=True)
        photo_url = None

    _photo_cache[listing_url] = (now, photo_url)
    return photo_url


def with_cache_bust(photo_url: str, cache_key: str) -> str:
    parts = urlsplit(photo_url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query["v"] = cache_key
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))

