# Frontend (админ SPA)

React + Vite интерфейс для входа и просмотра списка автомобилей из защищенного API.

## Что реализовано
- `/login` — форма входа, JWT сохраняется в `localStorage`
- `/` — защищенный роут с таблицей автомобилей
- поиск, обновление данных, logout, адаптивный интерфейс

## Запуск через Docker Compose
Из корня репозитория:

```powershell
docker compose up -d --build db backend frontend
```

Открыть `http://localhost:8080`.

## Локальный запуск frontend
```powershell
cd frontend
npm install
npm run dev
```

Открыть `http://localhost:5173`.

## Зависимость от backend
Backend должен быть доступен на `http://localhost:8000`.
В dev-режиме Vite проксирует `/api` и `/health` на backend.

## Опциональная переменная
Можно задать `VITE_API_BASE_URL` в `.env` при необходимости:

```env
VITE_API_BASE_URL=http://localhost:8000
```
