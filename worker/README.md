# Worker

Воркер периодически читает данные с `CARSENSOR_API_URL`, нормализует записи и сохраняет в PostgreSQL.

## Что делает воркер
- запрос к `carsensor.net` с retry/backoff на сетевых ошибках;
- нормализация полей: `brand`, `model`, `year`, `price`, `color`, `link`;
- upsert по `link`: новые записи вставляются, существующие обновляются.

## Переменные окружения
- `CARSENSOR_API_URL`
- `SCRAPER_INTERVAL_SECONDS`
- `WORKER_MAX_RETRIES` (по умолчанию `3`)
- `WORKER_BACKOFF_SECONDS` (по умолчанию `1.5`)
- `WORKER_REQUEST_TIMEOUT_SECONDS` (по умолчанию `20`)
- `WORKER_RUN_ONCE=1` для одноразового цикла
