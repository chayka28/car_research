import logging
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable

from bs4 import UnicodeDammit
from sqlalchemy import func, literal_column, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.config import (
    BATCH_PAUSE,
    CONCURRENCY,
    DELETE_AFTER_DAYS,
    INACTIVE_AFTER_DAYS,
    INTERVAL_SECONDS,
    JPY_TO_RUB_RATE,
    MAX_LISTINGS,
    MAX_SITEMAPS,
    PER_MAKE_LIMIT,
    POOL_SIZE,
    SOURCE_NAME,
    UPSERT_BATCH_SIZE,
    WORKER_RUN_ONCE,
)
from app.db import FailedScrape, Listing, SessionLocal
from app.scraper.client import HttpClient, HttpRequestError
from app.scraper.parser import ListingData, ParseFailure, parse_listing_html
from app.scraper.selector import select_candidates_by_make
from app.scraper.sitemaps import ListingCandidate, discover_candidates
from app.scraper.translator import translate_color, translate_make, translate_model


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


@dataclass
class ProcessResult:
    parsed: list[ListingData]
    failed_parse: int
    unavailable_external_ids: set[str]
    failed_rows: list[dict[str, object]]
    processed: int


def _chunked(values: list[object], size: int) -> Iterable[list[object]]:
    for idx in range(0, len(values), size):
        yield values[idx : idx + size]


def _touch_discovered(candidates: list[ListingCandidate]) -> int:
    if not candidates:
        return 0

    now = datetime.now(timezone.utc)
    external_ids = [c.external_id for c in candidates]
    placeholder_rows = [
        {
            "source": SOURCE_NAME,
            "external_id": c.external_id,
            "url": c.url,
            "maker": "Unknown",
            "model": "Unknown",
            "year": None,
            "price_jpy": None,
            "price_rub": None,
            "color": None,
            "last_seen_at": now,
            "is_active": True,
            "deleted_at": None,
        }
        for c in candidates
    ]

    reactivated = 0
    with SessionLocal() as session:
        for batch in _chunked(external_ids, UPSERT_BATCH_SIZE):
            reactivated += (
                session.scalar(
                    select(func.count())
                    .select_from(Listing)
                    .where(Listing.source == SOURCE_NAME)
                    .where(Listing.external_id.in_(batch))
                    .where(Listing.is_active.is_(False))
                )
                or 0
            )

        for batch in _chunked(placeholder_rows, UPSERT_BATCH_SIZE):
            stmt = pg_insert(Listing).values(batch)
            stmt = stmt.on_conflict_do_update(
                index_elements=[Listing.source, Listing.external_id],
                set_={
                    "url": stmt.excluded.url,
                    "last_seen_at": stmt.excluded.last_seen_at,
                    "is_active": True,
                    "deleted_at": None,
                },
            )
            session.execute(stmt)
        session.commit()

    return int(reactivated)


def _normalize_existing_translations() -> int:
    cjk_regex = r"[ぁ-んァ-ヶ一-龠]"
    needs_translation = or_(
        Listing.maker.op("~")(cjk_regex),
        Listing.model.op("~")(cjk_regex),
        func.coalesce(Listing.color, "").op("~")(cjk_regex),
    )
    updated = 0

    with SessionLocal() as session:
        rows = session.scalars(
            select(Listing).where(Listing.source == SOURCE_NAME).where(needs_translation)
        ).all()

        for row in rows:
            new_make = translate_make(row.maker) or row.maker
            new_model = translate_model(row.model) or row.model
            new_color = translate_color(row.color) if row.color else row.color

            if new_make != row.maker or new_model != row.model or new_color != row.color:
                row.maker = new_make
                row.model = new_model
                row.color = new_color
                updated += 1

        if updated:
            session.commit()

    return updated


def _process_single_candidate(
    *,
    client: HttpClient,
    candidate: ListingCandidate,
    html_cache: dict[str, str],
) -> tuple[ListingData | None, ParseFailure | None]:
    html: str | None = html_cache.get(candidate.url)
    final_url = candidate.url

    if html is None:
        try:
            response = client.get(candidate.url, allow_404=True)
            if response.status_code == 404:
                return None, ParseFailure(
                    error_type="http_404",
                    message="HTTP 404",
                    status_code=404,
                    unavailable=True,
                )
            final_url = str(response.url)
            html = UnicodeDammit(response.content, is_html=True).unicode_markup or response.text
        except HttpRequestError as exc:
            return None, ParseFailure(
                error_type="http_error",
                message=str(exc),
                status_code=exc.status_code,
                unavailable=(exc.status_code == 404),
            )

    parsed = parse_listing_html(
        html=html or "",
        url=candidate.url,
        external_id=candidate.external_id,
        final_url=final_url,
        jpy_to_rub_rate=JPY_TO_RUB_RATE,
    )
    if isinstance(parsed, ParseFailure):
        return None, parsed
    return parsed, None


def _process_candidates(
    *,
    client: HttpClient,
    candidates: list[ListingCandidate],
    html_cache: dict[str, str],
) -> ProcessResult:
    parsed_rows: list[ListingData] = []
    failed_rows: list[dict[str, object]] = []
    unavailable_external_ids: set[str] = set()
    failed_parse = 0
    processed = 0

    for offset in range(0, len(candidates), CONCURRENCY):
        batch = candidates[offset : offset + CONCURRENCY]
        with ThreadPoolExecutor(max_workers=CONCURRENCY) as executor:
            future_to_candidate = {
                executor.submit(
                    _process_single_candidate,
                    client=client,
                    candidate=candidate,
                    html_cache=html_cache,
                ): candidate
                for candidate in batch
            }
            for future in as_completed(future_to_candidate):
                processed += 1
                candidate = future_to_candidate[future]
                listing, failure = future.result()
                if listing is not None:
                    parsed_rows.append(listing)
                    continue

                failed_parse += 1
                if failure and failure.unavailable:
                    unavailable_external_ids.add(candidate.external_id)

                failed_rows.append(
                    {
                        "url": candidate.url,
                        "source_listing_id": candidate.external_id,
                        "error_type": failure.error_type if failure else "unknown",
                        "message": failure.message if failure else "Unknown parse failure",
                        "status_code": failure.status_code if failure else None,
                        "debug_snippet": failure.debug_snippet if failure else None,
                        "created_at": datetime.now(timezone.utc),
                    }
                )

        if offset + CONCURRENCY < len(candidates):
            time.sleep(BATCH_PAUSE)

    return ProcessResult(
        parsed=parsed_rows,
        failed_parse=failed_parse,
        unavailable_external_ids=unavailable_external_ids,
        failed_rows=failed_rows,
        processed=processed,
    )


def _upsert_listings(rows: list[ListingData]) -> tuple[int, int]:
    if not rows:
        return 0, 0

    now = datetime.now(timezone.utc)
    payload = [
        {
            "source": SOURCE_NAME,
            "external_id": row.external_id,
            "url": row.url,
            "maker": row.make,
            "model": row.model,
            "grade": row.grade,
            "color": row.color,
            "year": row.year,
            "mileage_km": row.mileage_km,
            "price_jpy": row.price_jpy,
            "price_rub": row.price_rub,
            "total_price_jpy": row.total_price_jpy,
            "total_price_rub": row.total_price_rub,
            "prefecture": row.prefecture,
            "shop_name": row.shop_name,
            "shop_address": row.shop_address,
            "shop_phone": row.shop_phone,
            "transmission": row.transmission,
            "drive_type": row.drive_type,
            "engine_cc": row.engine_cc,
            "fuel": row.fuel,
            "steering": row.steering,
            "body_type": row.body_type,
            "scraped_at": row.scraped_at,
            "last_seen_at": now,
            "is_active": True,
            "deleted_at": None,
        }
        for row in rows
    ]

    inserted = 0
    updated = 0
    with SessionLocal() as session:
        for batch in _chunked(payload, UPSERT_BATCH_SIZE):
            stmt = pg_insert(Listing).values(batch)
            stmt = stmt.on_conflict_do_update(
                index_elements=[Listing.source, Listing.external_id],
                set_={
                    "url": stmt.excluded.url,
                    "maker": stmt.excluded.maker,
                    "model": stmt.excluded.model,
                    "grade": stmt.excluded.grade,
                    "color": stmt.excluded.color,
                    "year": stmt.excluded.year,
                    "mileage_km": stmt.excluded.mileage_km,
                    "price_jpy": stmt.excluded.price_jpy,
                    "price_rub": stmt.excluded.price_rub,
                    "total_price_jpy": stmt.excluded.total_price_jpy,
                    "total_price_rub": stmt.excluded.total_price_rub,
                    "prefecture": stmt.excluded.prefecture,
                    "shop_name": stmt.excluded.shop_name,
                    "shop_address": stmt.excluded.shop_address,
                    "shop_phone": stmt.excluded.shop_phone,
                    "transmission": stmt.excluded.transmission,
                    "drive_type": stmt.excluded.drive_type,
                    "engine_cc": stmt.excluded.engine_cc,
                    "fuel": stmt.excluded.fuel,
                    "steering": stmt.excluded.steering,
                    "body_type": stmt.excluded.body_type,
                    "scraped_at": stmt.excluded.scraped_at,
                    "last_seen_at": stmt.excluded.last_seen_at,
                    "is_active": True,
                    "deleted_at": None,
                },
            ).returning(literal_column("xmax = 0").label("inserted"))

            result = session.execute(stmt).all()
            inserted_batch = sum(1 for item in result if item.inserted)
            inserted += inserted_batch
            updated += len(result) - inserted_batch
        session.commit()
    return inserted, updated


def _insert_failures(rows: list[dict[str, object]]) -> None:
    if not rows:
        return
    with SessionLocal() as session:
        for batch in _chunked(rows, UPSERT_BATCH_SIZE):
            session.execute(pg_insert(FailedScrape).values(batch))
        session.commit()


def _mark_unavailable(external_ids: set[str]) -> int:
    if not external_ids:
        return 0
    now = datetime.now(timezone.utc)
    with SessionLocal() as session:
        stmt = (
            update(Listing)
            .where(Listing.source == SOURCE_NAME)
            .where(Listing.external_id.in_(list(external_ids)))
            .values(is_active=False, deleted_at=now, last_seen_at=now)
        )
        result = session.execute(stmt)
        session.commit()
    return int(result.rowcount or 0)


def _cleanup_stale() -> tuple[int, int]:
    now = datetime.now(timezone.utc)
    deactivate_before = now - timedelta(days=INACTIVE_AFTER_DAYS)
    delete_before = now - timedelta(days=DELETE_AFTER_DAYS)

    with SessionLocal() as session:
        deactivate_stmt = (
            update(Listing)
            .where(Listing.source == SOURCE_NAME)
            .where(Listing.is_active.is_(True))
            .where(Listing.last_seen_at < deactivate_before)
            .values(is_active=False, deleted_at=now)
        )
        deactivated = int((session.execute(deactivate_stmt).rowcount or 0))

        delete_stmt = (
            Listing.__table__.delete()
            .where(Listing.source == SOURCE_NAME)
            .where(Listing.is_active.is_(False))
            .where(Listing.last_seen_at < delete_before)
        )
        deleted = int((session.execute(delete_stmt).rowcount or 0))

        session.commit()
    return deactivated, deleted


def run_cycle() -> None:
    client = HttpClient()
    candidates = discover_candidates(client)
    discovered = len(candidates)
    if not candidates:
        logger.warning("No listing candidates discovered.")
        return

    _touch_discovered(candidates)
    normalized = _normalize_existing_translations()
    selected, html_cache, selected_distribution = select_candidates_by_make(
        client=client,
        candidates=candidates,
        max_listings=MAX_LISTINGS,
        per_make_limit=PER_MAKE_LIMIT,
    )

    process_result = _process_candidates(client=client, candidates=selected, html_cache=html_cache)
    inserted, updated = _upsert_listings(process_result.parsed)
    _insert_failures(process_result.failed_rows)

    immediate_deactivated = _mark_unavailable(process_result.unavailable_external_ids)
    stale_deactivated, deleted = _cleanup_stale()

    parsed_make_distribution = dict(Counter([item.make for item in process_result.parsed]))
    logger.info(
        "Worker summary: discovered=%s processed=%s inserted=%s updated=%s deactivated=%s failed_parse=%s normalized=%s distribution_selected=%s distribution_parsed=%s",
        discovered,
        process_result.processed,
        inserted,
        updated,
        immediate_deactivated + stale_deactivated,
        process_result.failed_parse,
        normalized,
        selected_distribution,
        parsed_make_distribution,
    )
    logger.info("Worker cleanup: deleted=%s", deleted)


def main() -> None:
    logger.info(
        "Carsensor scraper worker started. run_once=%s interval=%ss concurrency=%s max_sitemaps=%s pool_size=%s max_listings=%s per_make_limit=%s batch_pause=%.2fs inactive_after_days=%s delete_after_days=%s",
        WORKER_RUN_ONCE,
        INTERVAL_SECONDS,
        CONCURRENCY,
        MAX_SITEMAPS,
        POOL_SIZE,
        MAX_LISTINGS,
        PER_MAKE_LIMIT,
        BATCH_PAUSE,
        INACTIVE_AFTER_DAYS,
        DELETE_AFTER_DAYS,
    )

    while True:
        started = time.time()
        try:
            run_cycle()
        except Exception:
            logger.exception("Worker cycle failed.")

        if WORKER_RUN_ONCE:
            logger.info("Run-once mode enabled. Worker stopping.")
            return

        elapsed = time.time() - started
        sleep_seconds = max(1, INTERVAL_SECONDS - int(elapsed))
        logger.info("Next cycle in %ss.", sleep_seconds)
        time.sleep(sleep_seconds)
