from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message

from app.config import SETTINGS
from app.formatters import build_listing_text
from app.keyboards import NOOP_CALLBACK, listing_keyboard
from app.openai_filters import extract_filters
from app.photo import resolve_listing_photo
from app.repository import enqueue_scrape_request, search_listings
from app.state import SearchSession, init_session_store

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


dp = Dispatcher()
store = init_session_store(SETTINGS.bot_session_ttl_seconds)


async def _send_or_update_card(
    *,
    bot: Bot,
    session: SearchSession,
    card_message: Message | None,
) -> None:
    card = session.listings[session.current_index]

    photo_url = await asyncio.to_thread(resolve_listing_photo, card.url)

    if session.photo_message_id:
        try:
            await bot.delete_message(chat_id=session.chat_id, message_id=session.photo_message_id)
        except Exception:
            pass
        finally:
            session.photo_message_id = None

    if photo_url:
        try:
            photo_message = await bot.send_photo(
                chat_id=session.chat_id,
                photo=photo_url,
                caption=f"📸 {card.maker} {card.model} ({card.year or 'год не указан'})",
            )
            session.photo_message_id = photo_message.message_id
        except Exception:
            logger.warning("Failed to send listing photo: %s", photo_url, exc_info=True)

    text = build_listing_text(card, session.current_index, len(session.listings), session.query)
    keyboard = listing_keyboard(
        token=session.token,
        index=session.current_index,
        total=len(session.listings),
        listing_url=card.url,
    )

    if card_message is None:
        await bot.send_message(chat_id=session.chat_id, text=text, reply_markup=keyboard)
        return

    await card_message.edit_text(text=text, reply_markup=keyboard)


@dp.message(CommandStart())
async def on_start(message: Message) -> None:
    await message.answer(
        "Привет! Напиши запрос в свободной форме, например:\n"
        "• Toyota до 2 миллионов\n"
        "• Найди белый Nissan до 10 лямчиков, но не красный\n\n"
        "Я разберу запрос через LLM, поищу в БД и покажу карточки вариантов."
    )


@dp.message(Command("help"))
async def on_help(message: Message) -> None:
    await message.answer(
        "Как пользоваться:\n"
        "1) Отправь текстовый запрос с пожеланиями (марка/модель/цвет/цена/год).\n"
        "2) Переключай варианты кнопками ⬅️ и ➡️.\n"
        "3) Кнопка 'Открыть источник' ведет на исходное объявление."
    )


@dp.message(F.text)
async def on_query(message: Message) -> None:
    if message.text is None:
        return

    query = message.text.strip()
    if not query:
        await message.answer("Пустой запрос. Опиши, что ищешь.")
        return

    status_message = await message.answer("Ищу подходящие варианты...")

    filters = await asyncio.to_thread(extract_filters, query)
    listings = await asyncio.to_thread(search_listings, filters, SETTINGS.bot_results_limit)

    if not listings:
        triggered = await asyncio.to_thread(enqueue_scrape_request, query)
        msg = "Подходящих предложений пока не найдено. Попробуйте чуть позже."
        if triggered:
            msg += "\nЯ запустил обновление базы объявлений, чтобы поиск подтянул новые варианты."
        else:
            msg += "\nОбновление базы уже запрошено недавно."

        await status_message.edit_text(msg)
        return

    session = store.create(chat_id=message.chat.id, query=query, listings=listings)
    await status_message.delete()
    await _send_or_update_card(bot=message.bot, session=session, card_message=None)


@dp.callback_query(F.data == NOOP_CALLBACK)
async def on_noop(callback: CallbackQuery) -> None:
    await callback.answer()


@dp.callback_query(F.data.startswith("nav:"))
async def on_nav(callback: CallbackQuery) -> None:
    if callback.message is None or callback.data is None:
        await callback.answer()
        return

    parts = callback.data.split(":", maxsplit=2)
    if len(parts) != 3:
        await callback.answer("Некорректная команда")
        return

    token = parts[1]
    try:
        index = int(parts[2])
    except ValueError:
        await callback.answer("Некорректный индекс")
        return

    session = store.set_index(token, index)
    if session is None or session.chat_id != callback.message.chat.id:
        await callback.answer("Сессия устарела. Отправь запрос заново.", show_alert=True)
        return

    await _send_or_update_card(bot=callback.bot, session=session, card_message=callback.message)
    await callback.answer()


async def _main() -> None:
    while True:
        bot = Bot(
            token=SETTINGS.telegram_bot_token,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        )

        try:
            logger.info("Telegram bot started. model=%s", SETTINGS.openai_model)
            await dp.start_polling(bot)
            return
        except Exception:
            logger.exception("Bot polling failed. Retrying in 10s.")
            await asyncio.sleep(10)
        finally:
            await bot.session.close()


if __name__ == "__main__":
    asyncio.run(_main())
