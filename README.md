# Car Research

Система сбора автомобильных объявлений с `carsensor.net`, API, SPA-админкой и Telegram-ботом.

## Архитектура
- `backend` (`FastAPI`): JWT-авторизация, API для админки, Alembic-миграции, сидинг дефолтного администратора.
- `worker` (`Python + SQLAlchemy + requests/bs4`): сбор объявлений из sitemap-цепочки Carsensor, парсинг карточек и upsert в `listings`.
- `frontend` (`React + Vite + nginx`): SPA админ-панель с защищенными маршрутами.
- `bot` (`aiogram`): Telegram-интерфейс поиска, парсинг фильтров через LLM Function Calling, запросы к `listings`.
- `db` (`PostgreSQL 16`): единое хранилище для API, воркера и бота.

Поток данных: `carsensor.net -> worker -> PostgreSQL(listings) -> backend/frontend + bot`.

## Запуск
1. Создайте `.env`:
```powershell
if (!(Test-Path .env)) { Copy-Item .env.example .env }
```
2. Заполните минимум:
- `TELEGRAM_BOT_TOKEN`
- `OPENAI_API_KEY` или `LLM_API_KEY` (если используете LLM-парсинг)
3. Запустите проект:
```powershell
docker-compose up --build
```

## URL после старта
- Frontend: `http://localhost:8080`
- Backend healthcheck: `http://localhost:8000/health`
- Backend API: `http://localhost:8000/api`

## Дефолтный администратор
- Логин: `admin`
- Пароль: `admin123`

(Задается через `ADMIN_USERNAME` и `ADMIN_PASSWORD` в `.env`)

## API (минимум по ТЗ)
- `POST /api/login`
  - request: `{"username":"admin","password":"admin123"}`
  - response: `{"access_token":"<jwt>", "token_type":"bearer"}`
- `GET /api/cars`
  - header: `Authorization: Bearer <jwt>`
  - response: список автомобилей (марка, модель, год, цена, цвет, ссылка)

## Воркер и upsert
- Источник: `carsensor.net` (через `robots.txt` и sitemap-файлы `usedcar-detail-*.xml`).
- Required-поля для выдачи в API: марка, модель, год, цена, цвет, ссылка.
- Upsert-логика: уникальность по `(source, external_id)`, существующие записи обновляются, новые добавляются.
- Retry-логика: `MAX_RETRIES` + exponential backoff (`BACKOFF_SECONDS`, `BACKOFF_JITTER_SECONDS`) для сетевых ошибок.
- Интервал запуска: `INTERVAL_SECONDS` (или `WORKER_RUN_ONCE=1` для одноразового цикла).

Полезные команды:
```powershell
docker-compose logs -f worker
docker-compose run --rm -e WORKER_RUN_ONCE=1 worker
```

## Telegram-бот
- Принимает запросы вида: `Найди красную BMW до 2 млн`.
- Вызывает Function Calling для извлечения фильтров (`make/model/color/year/price/...`).
- Делает SQL-поиск в `listings` и возвращает карточки с результатами.
- При отсутствии совпадений может поставить запрос на повторный скрапинг.

Полезная команда:
```powershell
docker-compose logs -f bot
```

## Миграции и сидинг
- Alembic миграции применяются при старте контейнера backend:
  - `alembic upgrade head && uvicorn ...`
- Сидинг администратора выполняется на startup backend (`init_db()`).

Ручной запуск миграций:
```powershell
docker-compose run --rm backend alembic upgrade head
```

## Важные переменные окружения
- БД: `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_HOST`, `POSTGRES_PORT`
- Backend/Auth: `JWT_SECRET`, `JWT_ALGORITHM`, `ACCESS_TOKEN_EXPIRE_MINUTES`, `ADMIN_USERNAME`, `ADMIN_PASSWORD`
- Worker: `INTERVAL_SECONDS`, `MAX_RETRIES`, `BACKOFF_SECONDS`, `BACKOFF_JITTER_SECONDS`, `MAX_LISTINGS`, `PER_MAKE_LIMIT`, `UPSERT_BATCH_SIZE`
- Bot/LLM: `TELEGRAM_BOT_TOKEN`, `LLM_PROVIDER`, `OPENAI_API_KEY`, `LLM_API_KEY`, `OPENAI_MODEL`
