# Telegram Bot

Telegram-бот для поиска объявлений в PostgreSQL (`listings`) без прямого обращения LLM к внешним сайтам.

## Команды
- `/start` — приветствие + главное меню.
- `/help` — справка и примеры запросов.
- `/search` — ввод запроса текстом + кнопка открытия фильтров.
- `/filters` — inline-меню фильтров.
- `/recent` — последние объявления (пагинация карточек).
- `/favorites` — избранное пользователя (пагинация карточек).
- `/settings` — состояние LLM.

## Что умеет
- свободный текстовый поиск (`тойота до 2 млн`, `бэху найди`, и т.д.);
- LLM extraction через OpenAI Function Calling (если включен);
- fallback-парсер, который работает даже при `LLM_PROVIDER=none`;
- карточки с кнопками: открыть, избранное, пагинация, фильтры, обновить;
- фото объявления (если удалось извлечь из страницы);
- если совпадений нет — ставит `scrape_requests` для воркера.

## Запуск
```powershell
docker compose up -d --build bot
```

## ENV
- `TELEGRAM_BOT_TOKEN` — обязателен.
- `LLM_PROVIDER` — `openai` или `none`.
- `OPENAI_API_KEY`/`LLM_API_KEY` — нужен только если `LLM_PROVIDER=openai`.
- `OPENAI_MODEL` — по умолчанию `gpt-4o-mini`.
