from __future__ import annotations

import time
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from app.config import SETTINGS

_CACHE_TTL_SECONDS = 60 * 30
_photo_cache: dict[str, tuple[float, str | None]] = {}


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
            candidates = [
                soup.select_one('meta[property="og:image"]'),
                soup.select_one('meta[name="twitter:image"]'),
                soup.select_one("img.js-galleryMainImage"),
                soup.select_one("img"),
            ]
            for node in candidates:
                if node is None:
                    continue
                content = node.get("content") or node.get("src")
                if not content:
                    continue
                photo_url = urljoin(str(response.url), content)
                break
    except Exception:
        photo_url = None

    _photo_cache[listing_url] = (now, photo_url)
    return photo_url
