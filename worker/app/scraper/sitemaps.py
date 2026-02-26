import logging
import re
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

from app.config import (
    BATCH_PAUSE,
    CARSENSOR_BASE_URL,
    CARSENSOR_ROBOTS_URL,
    CARSENSOR_SITEMAP_INDEX_URL,
    CONCURRENCY,
    MAX_SITEMAPS,
    POOL_SIZE,
    URLS_PER_SITEMAP,
)
from app.scraper.client import HttpClient, HttpRequestError


logger = logging.getLogger(__name__)

SITEMAP_NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
DETAIL_INDEX_RE = re.compile(r"/usedcar-detail-index\.xml$", re.IGNORECASE)
DETAIL_SITEMAP_RE = re.compile(r"/usedcar-detail-\d+\.xml$", re.IGNORECASE)
DETAIL_URL_RE = re.compile(r"/usedcar/detail/([^/]+)/index\.html", re.IGNORECASE)
BASE_PARSED = urlparse(CARSENSOR_BASE_URL)


@dataclass(frozen=True)
class ListingCandidate:
    external_id: str
    url: str
    lastmod: datetime


def extract_external_id(url: str) -> str | None:
    match = DETAIL_URL_RE.search(urlparse(url).path)
    if match is None:
        return None
    return match.group(1)


def _parse_datetime(value: str | None, fallback: datetime) -> datetime:
    if value is None:
        return fallback
    text = value.strip()
    if not text:
        return fallback
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed
    except ValueError:
        return fallback


def _canonical_detail_url(raw_url: str) -> str | None:
    absolute = urljoin(f"{CARSENSOR_BASE_URL}/", raw_url)
    parsed = urlparse(absolute)
    match = DETAIL_URL_RE.search(parsed.path)
    if match is None:
        return None
    external_id = match.group(1)
    scheme = BASE_PARSED.scheme or parsed.scheme
    netloc = BASE_PARSED.netloc or parsed.netloc
    return f"{scheme}://{netloc}/usedcar/detail/{external_id}/index.html"


def _load_sitemap_index_url_from_robots(client: HttpClient) -> str:
    try:
        robots_response = client.get(CARSENSOR_ROBOTS_URL)
    except HttpRequestError as exc:
        logger.warning("Failed to read robots.txt (%s), fallback to default sitemap index", exc)
        return CARSENSOR_SITEMAP_INDEX_URL

    candidates: list[str] = []
    for line in robots_response.text.splitlines():
        if not line.lower().startswith("sitemap:"):
            continue
        sitemap_url = line.split(":", 1)[1].strip()
        if sitemap_url:
            candidates.append(sitemap_url)

    for candidate in candidates:
        absolute = urljoin(f"{CARSENSOR_BASE_URL}/", candidate)
        if DETAIL_INDEX_RE.search(urlparse(absolute).path):
            return absolute

    logger.warning("robots.txt does not contain usedcar-detail-index.xml, using default URL")
    return CARSENSOR_SITEMAP_INDEX_URL


def _parse_sitemap_index(xml_text: str) -> list[str]:
    root = ET.fromstring(xml_text)
    loc_nodes = root.findall("./sm:sitemap/sm:loc", SITEMAP_NS)
    if not loc_nodes:
        loc_nodes = root.findall(".//{*}sitemap/{*}loc")

    urls: list[str] = []
    for node in loc_nodes:
        if node.text is None or not node.text.strip():
            continue
        sitemap_url = urljoin(f"{CARSENSOR_BASE_URL}/", node.text.strip())
        if DETAIL_SITEMAP_RE.search(urlparse(sitemap_url).path):
            urls.append(sitemap_url)

    return urls[:MAX_SITEMAPS]


def _parse_detail_sitemap(xml_text: str) -> list[ListingCandidate]:
    root = ET.fromstring(xml_text)
    discovered_at = datetime.now(timezone.utc)

    url_nodes = root.findall("./sm:url", SITEMAP_NS)
    if not url_nodes:
        url_nodes = root.findall(".//{*}url")

    out: list[ListingCandidate] = []
    for node in url_nodes[:URLS_PER_SITEMAP]:
        loc_node = node.find("./sm:loc", SITEMAP_NS)
        if loc_node is None:
            loc_node = node.find("./{*}loc")
        if loc_node is None or loc_node.text is None:
            continue

        canonical_url = _canonical_detail_url(loc_node.text.strip())
        if canonical_url is None:
            continue
        external_id = extract_external_id(canonical_url)
        if external_id is None:
            continue

        lastmod_node = node.find("./sm:lastmod", SITEMAP_NS)
        if lastmod_node is None:
            lastmod_node = node.find("./{*}lastmod")
        lastmod = _parse_datetime(lastmod_node.text if lastmod_node is not None else None, discovered_at)

        out.append(ListingCandidate(external_id=external_id, url=canonical_url, lastmod=lastmod))
    return out


def discover_candidates(client: HttpClient) -> list[ListingCandidate]:
    sitemap_index_url = _load_sitemap_index_url_from_robots(client)
    sitemap_index_response = client.get(sitemap_index_url)
    detail_sitemaps = _parse_sitemap_index(sitemap_index_response.text)
    per_sitemap_cap = max(1, (POOL_SIZE + max(1, len(detail_sitemaps)) - 1) // max(1, len(detail_sitemaps)))

    logger.info(
        "Loaded detail sitemap index: total=%s selected=%s per_sitemap_cap=%s source=%s",
        len(detail_sitemaps),
        len(detail_sitemaps),
        per_sitemap_cap,
        sitemap_index_url,
    )

    by_url: dict[str, ListingCandidate] = {}
    processed_sitemaps = 0
    failed_sitemaps = 0

    for offset in range(0, len(detail_sitemaps), CONCURRENCY):
        batch = detail_sitemaps[offset : offset + CONCURRENCY]
        with ThreadPoolExecutor(max_workers=CONCURRENCY) as executor:
            future_to_url = {executor.submit(client.get, sitemap_url): sitemap_url for sitemap_url in batch}
            for future in as_completed(future_to_url):
                sitemap_url = future_to_url[future]
                try:
                    response = future.result()
                    parsed = _parse_detail_sitemap(response.text)[:per_sitemap_cap]
                    processed_sitemaps += 1
                except (HttpRequestError, ET.ParseError) as exc:
                    failed_sitemaps += 1
                    logger.warning("Failed to process detail sitemap %s: %s", sitemap_url, exc)
                    continue

                for candidate in parsed:
                    existing = by_url.get(candidate.url)
                    if existing is None or candidate.lastmod > existing.lastmod:
                        by_url[candidate.url] = candidate

        if offset + CONCURRENCY < len(detail_sitemaps):
            time.sleep(BATCH_PAUSE)

    candidates = sorted(by_url.values(), key=lambda item: item.lastmod, reverse=True)[:POOL_SIZE]
    logger.info(
        "Discovered candidate pool=%s (processed_sitemaps=%s failed_sitemaps=%s pool_limit=%s)",
        len(candidates),
        processed_sitemaps,
        failed_sitemaps,
        POOL_SIZE,
    )
    return candidates
