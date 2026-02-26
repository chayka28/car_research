import logging
import random
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

from bs4 import UnicodeDammit

from app.config import BATCH_PAUSE, CONCURRENCY, MAX_LISTINGS, PER_MAKE_LIMIT
from app.scraper.client import HttpClient, HttpRequestError
from app.scraper.parser import quick_extract_make_model
from app.scraper.sitemaps import ListingCandidate


logger = logging.getLogger(__name__)


def _prefetch_make_and_html(
    client: HttpClient, candidates: list[ListingCandidate], max_needed: int
) -> tuple[dict[str, str], dict[str, str]]:
    make_by_url: dict[str, str] = {}
    html_cache: dict[str, str] = {}
    total_batches = (len(candidates) + CONCURRENCY - 1) // CONCURRENCY
    prefetch_pause = max(0.1, BATCH_PAUSE / 4)

    for offset in range(0, len(candidates), CONCURRENCY):
        if len(make_by_url) >= max_needed:
            break

        batch = candidates[offset : offset + CONCURRENCY]
        with ThreadPoolExecutor(max_workers=CONCURRENCY) as executor:
            future_to_candidate = {
                executor.submit(client.get, candidate.url, allow_404=True): candidate for candidate in batch
            }
            for future in as_completed(future_to_candidate):
                candidate = future_to_candidate[future]
                try:
                    response = future.result()
                    if response.status_code == 404:
                        continue
                    html = UnicodeDammit(response.content, is_html=True).unicode_markup or response.text
                    html_cache[candidate.url] = html
                    quick = quick_extract_make_model(html)
                    make_by_url[candidate.url] = quick.make or "Unknown"
                except HttpRequestError:
                    continue

        batch_no = (offset // CONCURRENCY) + 1
        if batch_no % 20 == 0 or batch_no == total_batches:
            logger.info(
                "Prefetch progress: fetched=%s target=%s batches=%s/%s",
                len(make_by_url),
                max_needed,
                batch_no,
                total_batches,
            )

        if offset + CONCURRENCY < len(candidates):
            time.sleep(prefetch_pause)

    return make_by_url, html_cache


def select_candidates_by_make(
    *,
    client: HttpClient,
    candidates: list[ListingCandidate],
    max_listings: int = MAX_LISTINGS,
    per_make_limit: int = PER_MAKE_LIMIT,
) -> tuple[list[ListingCandidate], dict[str, str], dict[str, int]]:
    if max_listings <= 0:
        return [], {}, {}

    sampling_candidates = list(candidates)
    random.shuffle(sampling_candidates)

    prefetch_target = max_listings + max(100, per_make_limit * 30)
    prefetch_target = min(prefetch_target, len(sampling_candidates))

    make_by_url, html_cache = _prefetch_make_and_html(client, sampling_candidates, max_needed=prefetch_target)

    grouped: dict[str, list[ListingCandidate]] = defaultdict(list)
    leftovers: list[ListingCandidate] = []
    for candidate in sampling_candidates:
        maker = make_by_url.get(candidate.url)
        if maker is None:
            leftovers.append(candidate)
            continue
        grouped[maker].append(candidate)

    selected: list[ListingCandidate] = []
    selected_counter: Counter[str] = Counter()
    make_order = sorted(grouped.keys())

    while len(selected) < max_listings:
        progressed = False
        for make in make_order:
            if len(selected) >= max_listings:
                break
            if not grouped[make]:
                continue
            if selected_counter[make] >= per_make_limit:
                continue

            selected.append(grouped[make].pop(0))
            selected_counter[make] += 1
            progressed = True

        if not progressed:
            break

    if len(selected) < max_listings:
        for make in make_order:
            while grouped[make] and len(selected) < max_listings:
                selected.append(grouped[make].pop(0))
                selected_counter[make] += 1
            if len(selected) >= max_listings:
                break

    if len(selected) < max_listings and leftovers:
        missing = max_listings - len(selected)
        selected.extend(leftovers[:missing])

    distribution = {make: count for make, count in selected_counter.items()}
    logger.info(
        "Selection completed: selected=%s max=%s per_make_limit=%s unique_makes=%s prefetched=%s prefetch_target=%s leftovers_used=%s",
        len(selected),
        max_listings,
        per_make_limit,
        len(distribution),
        len(make_by_url),
        prefetch_target,
        max(0, len(selected) - sum(distribution.values())),
    )
    return selected, html_cache, distribution
