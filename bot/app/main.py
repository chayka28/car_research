from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message

from app.config import SETTINGS
from app.formatters import build_filter_summary, build_listing_card_text
from app.keyboards import (
    UICallback,
    color_picker_keyboard,
    filter_menu_keyboard,
    listing_keyboard,
    main_menu_keyboard,
    make_picker_keyboard,
    search_prompt_keyboard,
)
from app.openai_filters import extract_filters
from app.photo import resolve_listing_photo
from app.repository import (
    enqueue_scrape_request,
    favorite_cars,
    is_favorite,
    recent_cars,
    search_cars,
    toggle_favorite,
)
from app.schemas import PagedResult
from app.state import UserSession, init_session_store

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

dp = Dispatcher()
router = Router()
dp.include_router(router)
store = init_session_store(SETTINGS.bot_session_ttl_seconds)


async def _delete_photo_if_exists(*, bot: Bot, session: UserSession) -> None:
    if session.photo_message_id is None:
        return
    try:
        await bot.delete_message(chat_id=session.chat_id, message_id=session.photo_message_id)
    except Exception:
        pass
    finally:
        session.photo_message_id = None


async def _send_photo_if_available(*, bot: Bot, session: UserSession, url: str, title: str) -> None:
    await _delete_photo_if_exists(bot=bot, session=session)
    photo_url = await asyncio.to_thread(resolve_listing_photo, url)
    if not photo_url:
        return
    try:
        message = await bot.send_photo(chat_id=session.chat_id, photo=photo_url, caption=f"📸 {title}")
        session.photo_message_id = message.message_id
    except Exception:
        logger.warning("Failed to send photo for %s", url, exc_info=True)


def _message_for_empty(mode: str) -> str:
    if mode == "favorites":
        return "В избранном пока пусто."
    if mode == "recent":
        return "Новых объявлений пока нет."
    return "Подходящих предложений не найдено. Попробуйте изменить фильтры."


async def _load_result(session: UserSession) -> PagedResult:
    if session.mode == "recent":
        return await asyncio.to_thread(recent_cars, page=session.page, page_size=session.page_size)
    if session.mode == "favorites":
        return await asyncio.to_thread(favorite_cars, user_id=session.user_id, page=session.page, page_size=session.page_size)
    return await asyncio.to_thread(
        search_cars,
        filters=session.filters,
        page=session.page,
        page_size=session.page_size,
        query_text=session.query_text,
    )


async def _render_card(*, bot: Bot, session: UserSession, edit_message: Message | None = None) -> None:
    result = await _load_result(session)
    session.last_result = result
    session.page = result.page

    if not result.items:
        await _delete_photo_if_exists(bot=bot, session=session)
        text = _message_for_empty(session.mode)
        if session.mode == "search":
            trigger_query = session.query_text or build_filter_summary(session.filters)
            triggered = await asyncio.to_thread(enqueue_scrape_request, trigger_query)
            if triggered:
                text += "\nЗапустил обновление данных. Повторите запрос чуть позже."
            else:
                text += "\nОбновление данных уже запрошено."

        if edit_message is None:
            await bot.send_message(chat_id=session.chat_id, text=text)
        else:
            await edit_message.edit_text(text=text)
        return

    card = result.items[0]
    title = f"{card.maker} {card.model}, {card.year or 'год не указан'}"
    await _send_photo_if_available(bot=bot, session=session, url=card.url, title=title)

    favorite = await asyncio.to_thread(is_favorite, user_id=session.user_id, source=card.source, external_id=card.external_id)
    text = build_listing_card_text(card=card, page=result.page, pages=result.pages)
    keyboard = listing_keyboard(
        listing_url=card.url,
        is_favorite=favorite,
        page=result.page,
        pages=result.pages,
    )

    if edit_message is None:
        await bot.send_message(chat_id=session.chat_id, text=text, reply_markup=keyboard)
    else:
        await edit_message.edit_text(text=text, reply_markup=keyboard)


async def _show_filters(message: Message, session: UserSession) -> None:
    summary = build_filter_summary(session.filters)
    await message.answer(
        "Текущие фильтры:\n" + summary,
        reply_markup=filter_menu_keyboard(session.filters),
    )


def _parse_optional_int(value: str) -> int | None:
    stripped = value.strip().lower()
    if stripped in {"-", "нет", "none", "пропустить", "skip"}:
        return None
    if not stripped:
        return None
    cleaned = stripped.replace(" ", "")
    if not cleaned.isdigit():
        raise ValueError("Нужно число")
    return int(cleaned)


async def _handle_waiting_input(message: Message, session: UserSession) -> bool:
    if message.text is None or session.awaiting_input is None:
        return False

    text = message.text.strip()
    kind = session.awaiting_input

    if kind == "search_query":
        session.awaiting_input = None
        await _start_search_from_text(message, session, text)
        return True

    if kind == "make_manual":
        if not text:
            session.filters.make = None
        elif len(text) <= 4 and text.isalpha():
            session.filters.make = text.upper()
        else:
            session.filters.make = text.title()
        session.awaiting_input = None
        await _show_filters(message, session)
        return True

    if kind == "model_manual":
        session.filters.model = text if text else None
        session.awaiting_input = None
        await _show_filters(message, session)
        return True

    if kind == "year_min":
        try:
            value = _parse_optional_int(text)
        except ValueError:
            await message.answer("Неверный ввод. Введите год числом или '-' для пропуска.")
            return True
        if value is not None and not (1950 <= value <= 2100):
            await message.answer("Год должен быть в диапазоне 1950..2100.")
            return True
        session.filters.year_min = value
        session.awaiting_input = "year_max"
        await message.answer("Введите максимальный год (например 2024) или '-' для пропуска.")
        return True

    if kind == "year_max":
        try:
            value = _parse_optional_int(text)
        except ValueError:
            await message.answer("Неверный ввод. Введите год числом или '-' для пропуска.")
            return True
        if value is not None and not (1950 <= value <= 2100):
            await message.answer("Год должен быть в диапазоне 1950..2100.")
            return True
        session.filters.year_max = value
        session.awaiting_input = None
        await _show_filters(message, session)
        return True

    if kind == "price_min":
        try:
            value = _parse_optional_int(text)
        except ValueError:
            await message.answer("Неверный ввод. Введите цену числом в рублях или '-' для пропуска.")
            return True
        session.filters.price_min_rub = value
        session.awaiting_input = "price_max"
        await message.answer("Введите максимальную цену (₽) или '-' для пропуска.")
        return True

    if kind == "price_max":
        try:
            value = _parse_optional_int(text)
        except ValueError:
            await message.answer("Неверный ввод. Введите цену числом в рублях или '-' для пропуска.")
            return True
        session.filters.price_max_rub = value
        session.awaiting_input = None
        await _show_filters(message, session)
        return True

    return False


async def _start_search_from_text(message: Message, session: UserSession, query_text: str) -> None:
    status = await message.answer("Обрабатываю запрос и ищу варианты...")
    parsed = await asyncio.to_thread(extract_filters, query_text)
    if parsed.is_empty():
        await status.edit_text(
            "Не удалось понять критерии. Уточните марку/цвет/бюджет, например:\n"
            "• Toyota до 2 млн\n"
            "• Белый Nissan от 2020\n"
            "• BMW 2018+ до 3 000 000"
        )
        return

    session.mode = "search"
    session.query_text = query_text
    session.filters = parsed
    session.page = 1
    await status.delete()
    await _render_card(bot=message.bot, session=session)


@router.message(CommandStart())
async def on_start(message: Message) -> None:
    session = store.get_or_create(user_id=message.from_user.id, chat_id=message.chat.id)
    session.awaiting_input = None
    await message.answer(
        "Добро пожаловать в Car Research Bot.\n"
        "Используйте меню ниже или отправьте запрос текстом.",
        reply_markup=main_menu_keyboard(),
    )


@router.message(Command("help"))
async def on_help(message: Message) -> None:
    await message.answer(
        "Примеры запросов:\n"
        "• тойота до 2 миллионов\n"
        "• найди белый ниссан до 10 лямчиков, но не серый или красный\n"
        "• BMW 2018+ до 3 000 000\n\n"
        "Команды: /search /filters /recent /favorites /settings",
        reply_markup=main_menu_keyboard(),
    )


@router.message(Command("search"))
async def on_search(message: Message) -> None:
    session = store.get_or_create(user_id=message.from_user.id, chat_id=message.chat.id)
    session.awaiting_input = "search_query"
    await message.answer(
        "Напишите запрос свободным текстом.\nНапример: Toyota до 2 млн 2018+",
        reply_markup=search_prompt_keyboard(),
    )


@router.message(Command("filters"))
async def on_filters(message: Message) -> None:
    session = store.get_or_create(user_id=message.from_user.id, chat_id=message.chat.id)
    await _show_filters(message, session)


@router.message(Command("recent"))
async def on_recent(message: Message) -> None:
    session = store.get_or_create(user_id=message.from_user.id, chat_id=message.chat.id)
    session.mode = "recent"
    session.page = 1
    session.awaiting_input = None
    await _render_card(bot=message.bot, session=session)


@router.message(Command("favorites"))
async def on_favorites(message: Message) -> None:
    session = store.get_or_create(user_id=message.from_user.id, chat_id=message.chat.id)
    session.mode = "favorites"
    session.page = 1
    session.awaiting_input = None
    await _render_card(bot=message.bot, session=session)


@router.message(Command("settings"))
async def on_settings(message: Message) -> None:
    status = "включен" if SETTINGS.llm_enabled else "выключен"
    provider = SETTINGS.llm_provider
    await message.answer(
        f"Настройки:\nLLM: {status}\nПровайдер: {provider}\nМодель: {SETTINGS.openai_model}",
        reply_markup=main_menu_keyboard(),
    )


@router.message(F.text == "🔎 Поиск")
async def on_menu_search(message: Message) -> None:
    await on_search(message)


@router.message(F.text == "🧰 Фильтры")
async def on_menu_filters(message: Message) -> None:
    await on_filters(message)


@router.message(F.text == "⭐ Избранное")
async def on_menu_favorites(message: Message) -> None:
    await on_favorites(message)


@router.message(F.text == "🆕 Новые")
async def on_menu_recent(message: Message) -> None:
    await on_recent(message)


@router.message(F.text == "❓ Помощь")
async def on_menu_help(message: Message) -> None:
    await on_help(message)


@router.message(F.text)
async def on_text(message: Message) -> None:
    session = store.get_or_create(user_id=message.from_user.id, chat_id=message.chat.id)
    if await _handle_waiting_input(message, session):
        return

    text = (message.text or "").strip()
    if not text:
        await message.answer("Пустой запрос.")
        return
    await _start_search_from_text(message, session, text)


@router.callback_query(UICallback.filter())
async def on_ui_callback(callback: CallbackQuery, callback_data: UICallback) -> None:
    if callback.message is None:
        await callback.answer()
        return

    session = store.get_or_create(user_id=callback.from_user.id, chat_id=callback.message.chat.id)

    if callback_data.scope == "card":
        if callback_data.action == "noop":
            await callback.answer()
            return
        if callback_data.action == "prev":
            session.page = max(1, session.page - 1)
            await _render_card(bot=callback.bot, session=session, edit_message=callback.message)
            await callback.answer()
            return
        if callback_data.action == "next":
            session.page = session.page + 1
            await _render_card(bot=callback.bot, session=session, edit_message=callback.message)
            await callback.answer()
            return
        if callback_data.action == "refresh":
            await _render_card(bot=callback.bot, session=session, edit_message=callback.message)
            await callback.answer("Обновлено")
            return
        if callback_data.action == "favorite":
            current = session.current_listing
            if current is None:
                await callback.answer("Карточка устарела", show_alert=True)
                return
            now_favorite = await asyncio.to_thread(
                toggle_favorite,
                user_id=session.user_id,
                source=current.source,
                external_id=current.external_id,
            )
            await _render_card(bot=callback.bot, session=session, edit_message=callback.message)
            await callback.answer("Добавлено в избранное" if now_favorite else "Удалено из избранного")
            return

    if callback_data.scope == "filter":
        if callback_data.action == "open":
            await callback.message.answer(
                "Настройка фильтров:\n" + build_filter_summary(session.filters),
                reply_markup=filter_menu_keyboard(session.filters),
            )
            await callback.answer()
            return

        if callback_data.action == "make_menu":
            await callback.message.answer("Выберите марку:", reply_markup=make_picker_keyboard())
            await callback.answer()
            return

        if callback_data.action == "set_make":
            session.filters.make = callback_data.value
            session.awaiting_input = None
            await callback.message.answer("Марка обновлена.", reply_markup=filter_menu_keyboard(session.filters))
            await callback.answer()
            return

        if callback_data.action == "make_manual":
            session.awaiting_input = "make_manual"
            await callback.message.answer("Введите марку вручную (например Toyota):")
            await callback.answer()
            return

        if callback_data.action == "model_manual":
            session.awaiting_input = "model_manual"
            await callback.message.answer("Введите модель вручную (например Camry):")
            await callback.answer()
            return

        if callback_data.action == "color_menu":
            await callback.message.answer("Выберите цвет:", reply_markup=color_picker_keyboard())
            await callback.answer()
            return

        if callback_data.action == "set_color":
            session.filters.color = callback_data.value.title()
            await callback.message.answer("Цвет обновлен.", reply_markup=filter_menu_keyboard(session.filters))
            await callback.answer()
            return

        if callback_data.action == "clear_color":
            session.filters.color = None
            await callback.message.answer("Цвет очищен.", reply_markup=filter_menu_keyboard(session.filters))
            await callback.answer()
            return

        if callback_data.action == "year_input":
            session.awaiting_input = "year_min"
            await callback.message.answer("Введите минимальный год (например 2016) или '-' для пропуска.")
            await callback.answer()
            return

        if callback_data.action == "price_input":
            session.awaiting_input = "price_min"
            await callback.message.answer("Введите минимальную цену в рублях или '-' для пропуска.")
            await callback.answer()
            return

        if callback_data.action == "reset":
            session.filters.clear()
            session.query_text = None
            session.awaiting_input = None
            await callback.message.answer("Фильтры сброшены.", reply_markup=filter_menu_keyboard(session.filters))
            await callback.answer()
            return

        if callback_data.action == "apply":
            session.mode = "search"
            session.page = 1
            session.query_text = None
            await _render_card(bot=callback.bot, session=session, edit_message=callback.message)
            await callback.answer()
            return

    await callback.answer()


async def _main() -> None:
    while True:
        bot = Bot(
            token=SETTINGS.telegram_bot_token,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        )
        try:
            logger.info(
                "Telegram bot started. llm_enabled=%s provider=%s model=%s",
                SETTINGS.llm_enabled,
                SETTINGS.llm_provider,
                SETTINGS.openai_model,
            )
            await dp.start_polling(bot)
            return
        except Exception:
            logger.exception("Bot polling failed. Retrying in 10s.")
            await asyncio.sleep(10)
        finally:
            await bot.session.close()


if __name__ == "__main__":
    asyncio.run(_main())
