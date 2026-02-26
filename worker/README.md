# Worker

Carsensor scraper worker for `car_research`.

## Run
One cycle:
```powershell
docker compose run --rm -e WORKER_RUN_ONCE=1 worker
```

Continuous:
```powershell
docker compose up -d worker
```

## Discovery rules
- Do not use `/usedcar/search.php`.
- Use sitemap chain:
  - `https://www.carsensor.net/robots.txt`
  - `https://www.carsensor.net/usedcar-detail-index.xml`
  - `https://www.carsensor.net/usedcar-detail-*.xml`
- Parse `<sitemap><loc>` and `<url><loc>` with sitemap namespace support.

## Selection strategy
- Build candidate pool (`POOL_SIZE`).
- Pre-read make from listing pages.
- Select up to `MAX_LISTINGS` with per-make cap `PER_MAKE_LIMIT`.
- If unique makes are insufficient, fill remaining slots from leftover candidates.

## Required parsed fields
- `make` (English)
- `model` (English)
- `year`
- `price_jpy` and `price_rub`
- `color` (English)
- `url`
- `external_id`

## Reliability
- Retries: `MAX_RETRIES` on timeout/connection/5xx.
- Exponential backoff + jitter.
- Configurable connect/read timeouts.
- Concurrency limited by `CONCURRENCY`.
- Pause between request batches: `BATCH_PAUSE`.

## DB behavior
- Batch upsert into `listings` by `(source, external_id)`.
- On each discover: `last_seen_at=now`, `is_active=true`.
- Deactivate stale records older than `INACTIVE_AFTER_DAYS`.
- Delete old inactive records older than `DELETE_AFTER_DAYS`.
- Supports `scrape_requests` queue:
  - bot inserts `pending` requests when no results found;
  - worker detects pending requests and runs next cycle early.

## Main ENV
- `MAX_SITEMAPS`
- `POOL_SIZE`
- `MAX_LISTINGS`
- `PER_MAKE_LIMIT`
- `CONCURRENCY`
- `BATCH_PAUSE`
- `JPY_TO_RUB_RATE`
- `INACTIVE_AFTER_DAYS`
- `DELETE_AFTER_DAYS`
