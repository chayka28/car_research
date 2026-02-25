# car_research
Сервис для поиска объявлений по продаже автомобилей 

## Smoke test (Day 1 Step 6)

### 1) Prepare environment

```powershell
if (!(Test-Path .env)) { Copy-Item .env.example .env }
docker compose up -d --build db backend
```

Wait until API is healthy:

```powershell
Invoke-RestMethod -Method Get -Uri "http://localhost:8000/health"
```

Expected result:

```json
{"status":"ok"}
```

### 2) Automatic smoke check

Run the script:

```powershell
./scripts/smoke_day1_step6.ps1
```

Expected outcome:
- process exit code is `0`
- output ends with: `Smoke test passed: login and JWT-protected /api/cars work as expected.`

### 3) Manual smoke check

Login and get JWT token:

```powershell
$loginBody = @{ username = "admin"; password = "admin123" } | ConvertTo-Json
$login = Invoke-RestMethod -Method Post -Uri "http://localhost:8000/api/login" -ContentType "application/json" -Body $loginBody
$token = $login.access_token
$login
```

Expected:
- HTTP `200`
- response contains `access_token`
- `token_type` equals `bearer`

Negative case (no token):

```powershell
Invoke-WebRequest -Method Get -Uri "http://localhost:8000/api/cars"
```

Expected:
- HTTP `401 Unauthorized`

Positive case (with token):

```powershell
Invoke-RestMethod -Method Get -Uri "http://localhost:8000/api/cars" -Headers @{ Authorization = "Bearer $token" }
```

Expected:
- HTTP `200`
- JSON array with at least one object
- each object includes `brand`, `model`, `year`, `price`, `color`, `link`

### 4) Troubleshooting

- Backend is unavailable:
  - verify containers: `docker compose ps`
  - check backend logs: `docker compose logs backend --tail=200`
- Invalid credentials:
  - verify `ADMIN_USERNAME` and `ADMIN_PASSWORD` in `.env`
  - restart backend after env changes: `docker compose up -d --build backend`
- Empty cars response:
  - check DB/backend logs
  - ensure initial seeding ran during backend startup

## Admin frontend

Запуск через Docker Compose (backend + frontend):

```powershell
docker compose up -d --build db backend frontend
```

Открыть: `http://localhost:8080`.

Локальный режим разработки frontend:

```powershell
cd frontend
npm install
npm run dev
```

Открыть: `http://localhost:5173`.

Поток авторизации:
- `/login` -> `POST /api/login`
- `/` (защищенный) -> `GET /api/cars` с JWT в `Authorization: Bearer ...`

## Day 2 additions: Alembic + Worker

### Alembic migrations
Backend now runs migrations automatically on startup.

Manual commands (inside `backend/`):

```powershell
alembic upgrade head
```

Migration files:
- `backend/alembic/`
- `backend/alembic/versions/20260225_0001_create_users_and_cars.py`

### Worker (carsensor ingestion)
Worker is now part of docker compose and runs periodically.

Run full stack:

```powershell
docker compose up -d --build db backend frontend worker
```

Worker behavior:
- fetches from `CARSENSOR_API_URL`
- retries network failures with exponential backoff
- normalizes required fields
- performs PostgreSQL upsert by unique `link`
