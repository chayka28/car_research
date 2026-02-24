# Car Research — тестовое задание (старт)

Этот репозиторий содержит стартовую структуру проекта для тестового задания по сервису автообъявлений.

## Что уже сделано

- Подготовлен подробный план работ на 2–3 дня: `docs/implementation_plan.md`.
- Добавлен базовый `docker-compose.yml` со всеми ключевыми сервисами.
- Подготовлен `.env.example` с переменными окружения.
- Создан стартовый backend на FastAPI:
  - `POST /api/login` — выдача JWT;
  - `GET /api/cars` — защищённый эндпоинт списка автомобилей.

## Быстрый запуск (на текущем этапе)

```bash
docker compose up --build
```

> Сейчас это стартовый каркас. Следующие шаги (миграции Alembic, воркер-парсер carsensor.net, фронтенд и Telegram-бот) описаны в `docs/implementation_plan.md`.

## Дефолтные креды администратора

- Логин: `admin`
- Пароль: `admin123`

## Стек (черновой)

- Backend: FastAPI + SQLAlchemy + JWT
- DB: PostgreSQL
- Frontend: React (Vite)
- Telegram bot: aiogram
- Оркестрация: Docker Compose


## Подробные объяснения для старта

Если ты только входишь в стек (PostgreSQL, Docker, Alembic, JWT) и хочешь понять, как работать с проектом шаг за шагом, смотри подробный документ:

- `docs/onboarding_explained_ru.md`
