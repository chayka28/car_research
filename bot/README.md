# Telegram Bot

Telegram-бот для поиска объявлений по базе `listings`.

## Что умеет
- принимает запросы в свободной форме;
- через OpenAI Function Calling извлекает фильтры;
- ищет только в PostgreSQL (без обращения LLM к сайту);
- показывает карточки авто с inline-навигацией;
- отдает фото варианта (если удается получить с источника);
- если результатов нет — ставит задачу на обновление данных скрапером.

## Запуск
```powershell
docker compose up -d --build bot
```

## Обязательные ENV
- `TELEGRAM_BOT_TOKEN`
- `OPENAI_API_KEY` (или `LLM_API_KEY`)
- `OPENAI_MODEL` (по умолчанию `gpt-4o-mini`)
