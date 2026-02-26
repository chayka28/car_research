# car_research

Service for collecting car listings from Carsensor, exposing them in admin API/UI, and storing data in PostgreSQL.

## Stack
- `backend`: FastAPI + JWT auth + SQLAlchemy + Alembic
- `frontend`: SPA admin panel
- `worker`: Carsensor scraper (sitemaps -> detail pages -> PostgreSQL upsert)
- `db`: PostgreSQL 16

## Quick start
1. Prepare env:
```powershell
if (!(Test-Path .env)) { Copy-Item .env.example .env }
```
2. Build and run:
```powershell
docker compose up -d --build
```
3. Open:
- frontend: `http://localhost:8080`
- backend health: `http://localhost:8000/health`

## Default admin credentials
- username: `admin`
- password: `admin123`

## API
- `POST /api/login` -> returns JWT (`access_token`)
- `GET /api/cars` -> JWT-protected list of cars

## Worker (Carsensor scraper)
Run one cycle manually:
```powershell
docker compose run --rm -e WORKER_RUN_ONCE=1 worker
```

Follow logs:
```powershell
docker compose logs -f worker
```

### Worker pipeline
1. Reads sitemap chain from Carsensor (`robots.txt` -> `usedcar-detail-index.xml` -> `usedcar-detail-*.xml`).
2. Builds candidate pool from detail listing URLs.
3. Selects final set with per-make diversity (`PER_MAKE_LIMIT`).
4. Scrapes detail pages with retry/backoff.
5. Parses required fields: make, model, year, price, color, url, external_id.
6. Converts prices JPY -> RUB (`JPY_TO_RUB_RATE`).
7. Batch upserts into `listings` by `(source, external_id)`.
8. Marks stale rows inactive based on `INACTIVE_AFTER_DAYS`.

### Key env for worker
- `MAX_SITEMAPS`
- `POOL_SIZE`
- `MAX_LISTINGS`
- `PER_MAKE_LIMIT`
- `CONCURRENCY`
- `BATCH_PAUSE`
- `JPY_TO_RUB_RATE`
- `INACTIVE_AFTER_DAYS`
- `DELETE_AFTER_DAYS`

## Migrations
Backend applies Alembic automatically at container startup.

Manual migration:
```powershell
docker compose run --rm backend alembic upgrade head
```
