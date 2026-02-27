from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
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
    awaiting_input_keyboard,
    color_picker_keyboard,
    empty_result_keyboard,
    filter_menu_keyboard,
    help_keyboard,
    listing_keyboard,
    main_menu_keyboard,
    make_picker_keyboard,
    model_picker_keyboard,
    search_screen_keyboard,
    settings_keyboard,
)
from app.openai_filters import extract_filters
from app.photo import resolve_listing_photo, with_cache_bust
from app.repository import (
    EnqueueResult,
    enqueue_scrape_request,
    favorite_cars,
    is_favorite,
    recent_cars,
    search_cars,
    toggle_favorite,
)
from app.schemas import PagedResult
from app.state import UserSession, init_session_store
from app.ui import ScreenManager, ScreenPayload
from app.validators import parse_optional_rub, parse_optional_year, validate_filters

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

dp = Dispatcher()
router = Router()
dp.include_router(router)
store = init_session_store(SETTINGS.bot_session_ttl_seconds)
screen_manager = ScreenManager()


def _make_values_from_input(text: str) -> list[str]:
    items = [item.strip() for item in text.replace(";", ",").split(",")]
    values: list[str] = []
    for item in items:
        if not item:
            continue
        if len(item) <= 4 and item.isalpha():
            values.append(item.upper())
        else:
            values.append(item.title())
    return values


def _model_values_from_input(text: str) -> list[str]:
    items = [item.strip() for item in text.replace(";", ",").split(",")]
    return [item for item in items if item]


def _toggle_value(values: list[str], item: str) -> list[str]:
    candidate = item.strip()
    if not candidate:
        return values
    if candidate in values:
        return [value for value in values if value != candidate]
    return values + [candidate]


def _compute_query_hash(session: UserSession) -> str:
    payload = {
        "mode": session.mode,
        "query_text": session.query_text or "",
        "filters": {
            "makes": session.filters.makes,
            "models": session.filters.models,
            "colors": session.filters.colors,
            "exclude_colors": session.filters.exclude_colors,
            "year_min": session.filters.year_min,
            "year_max": session.filters.year_max,
            "price_min_rub": session.filters.price_min_rub,
            "price_max_rub": session.filters.price_max_rub,
            "sort": session.filters.sort,
            "only_active": session.filters.only_active,
        },
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha1(encoded).hexdigest()


def _back_action_for_mode(mode: str) -> str:
    if mode == "recent":
        return "recent"
    if mode == "favorites":
        return "favorites"
    return "search"


def _message_for_empty(mode: str) -> str:
    if mode == "favorites":
        return "Избранных объявлений пока нет."
    if mode == "recent":
        return "Новых объявлений пока нет."
    return "Пока нет подходящих объявлений в базе."


async def _safe_delete_user_message(message: Message) -> None:
    try:
        await message.delete()
    except Exception:
        pass


async def _render_main_menu(
    bot: Bot,
    session: UserSession,
    *,
    source_message: Message | None = None,
    notice: str | None = None,
) -> None:
    text = (
        "Привет! Я помогу найти авто в базе Carsensor.\n\n"
        "Примеры запроса:\n"
        "• Найди красную BMW до 2 млн\n"
        "• Toyota 2018+ до 3 000 000\n"
        "• Белый Nissan, но не серый\n\n"
        "Используйте кнопки ниже или отправьте текстовый запрос."
    )
    if notice:
        text = f"{notice}\n\n{text}"
    await screen_manager.render(
        bot,
        session,
        ScreenPayload(text=text, keyboard=main_menu_keyboard()),
        screen_type="menu",
        source_message=source_message,
    )


async def _render_help(bot: Bot, session: UserSession, *, source_message: Message | None = None) -> None:
    text = (
        "Как пользоваться ботом:\n"
        "1. Нажмите «🔎 Поиск» и отправьте запрос свободным текстом.\n"
        "2. Либо задайте условия через «🎛 Фильтры».\n"
        "3. Листайте карточки кнопками ⬅️/➡️.\n\n"
        "Примеры:\n"
        "• тойота до 2 миллионов\n"
        "• найди белый ниссан до 10 млн, не красный\n"
        "• BMW 2015+"
    )
    await screen_manager.render(
        bot,
        session,
        ScreenPayload(text=text, keyboard=help_keyboard()),
        screen_type="help",
        source_message=source_message,
    )


async def _render_settings(bot: Bot, session: UserSession, *, source_message: Message | None = None) -> None:
    llm_state = "включен" if SETTINGS.llm_enabled else "выключен"
    notify_state = "включены" if session.notify_on_match else "выключены"
    text = (
        "Настройки:\n"
        f"LLM: {llm_state}\n"
        f"Провайдер: {SETTINGS.llm_provider}\n"
        f"Модель: {SETTINGS.openai_model}\n"
        f"Уведомления: {notify_state}"
    )
    await screen_manager.render(
        bot,
        session,
        ScreenPayload(text=text, keyboard=settings_keyboard(session.notify_on_match)),
        screen_type="settings",
        source_message=source_message,
    )


async def _render_search_screen(
    bot: Bot,
    session: UserSession,
    *,
    source_message: Message | None = None,
    notice: str | None = None,
) -> None:
    text = (
        "Экран поиска\n\n"
        "Напишите запрос свободным текстом.\n"
        "Например: «Найди красную BMW до 2 млн 2015+»."
    )
    if notice:
        text = f"{notice}\n\n{text}"
    await screen_manager.render(
        bot,
        session,
        ScreenPayload(text=text, keyboard=search_screen_keyboard()),
        screen_type="search",
        source_message=source_message,
    )


async def _render_filters(
    bot: Bot,
    session: UserSession,
    *,
    source_message: Message | None = None,
    notice: str | None = None,
) -> None:
    text = "Текущие фильтры:\n" + build_filter_summary(session.filters)
    if notice:
        text = f"{notice}\n\n{text}"
    await screen_manager.render(
        bot,
        session,
        ScreenPayload(text=text, keyboard=filter_menu_keyboard(session.filters)),
        screen_type="filters",
        source_message=source_message,
    )


async def _render_make_picker(bot: Bot, session: UserSession, *, source_message: Message | None = None) -> None:
    await screen_manager.render(
        bot,
        session,
        ScreenPayload(
            text="Выберите марки (можно несколько):",
            keyboard=make_picker_keyboard(session.filters.makes),
        ),
        screen_type="filter_make",
        source_message=source_message,
    )


async def _render_model_picker(bot: Bot, session: UserSession, *, source_message: Message | None = None) -> None:
    await screen_manager.render(
        bot,
        session,
        ScreenPayload(
            text="Выберите модели (можно несколько):",
            keyboard=model_picker_keyboard(session.filters.models),
        ),
        screen_type="filter_model",
        source_message=source_message,
    )


async def _render_color_picker(bot: Bot, session: UserSession, *, source_message: Message | None = None) -> None:
    await screen_manager.render(
        bot,
        session,
        ScreenPayload(
            text="Выберите цвета (можно несколько):",
            keyboard=color_picker_keyboard(session.filters.colors, session.filters.exclude_colors),
        ),
        screen_type="filter_color",
        source_message=source_message,
    )


async def _render_input_prompt(
    bot: Bot,
    session: UserSession,
    *,
    text: str,
    source_message: Message | None = None,
    back_to: str = "filters",
) -> None:
    await screen_manager.render(
        bot,
        session,
        ScreenPayload(text=text, keyboard=awaiting_input_keyboard(back_to)),
        screen_type="input",
        source_message=source_message,
    )


async def _enqueue_scrape_for_session(session: UserSession) -> EnqueueResult:
    query = session.query_text or build_filter_summary(session.filters)
    return await asyncio.to_thread(enqueue_scrape_request, query)


def _load_result(session: UserSession) -> PagedResult:
    if session.mode == "recent":
        return recent_cars(page=session.pagination_state.page, page_size=session.pagination_state.page_size)
    if session.mode == "favorites":
        return favorite_cars(
            user_id=session.user_id,
            page=session.pagination_state.page,
            page_size=session.pagination_state.page_size,
        )
    return search_cars(
        filters=session.filters,
        page=session.pagination_state.page,
        page_size=session.pagination_state.page_size,
        query_text=session.query_text if session.filters.is_empty() else None,
    )


async def _render_empty(
    bot: Bot,
    session: UserSession,
    *,
    source_message: Message | None = None,
    notice: str | None = None,
) -> None:
    text = _message_for_empty(session.mode)
    if session.mode == "search":
        result = await _enqueue_scrape_for_session(session)
        if result.triggered:
            text += "\nЗапустил обновление базы. Повторите запрос чуть позже."
        elif result.reason == "queue_full":
            text += "\nОчередь обновления перегружена. Попробуйте немного позже."
        elif result.reason == "duplicate":
            text += "\nПохожий запрос на обновление уже стоит в очереди."
        else:
            text += "\nНе удалось поставить задачу на обновление."
    if notice:
        text = f"{notice}\n\n{text}"
    await screen_manager.render(
        bot,
        session,
        ScreenPayload(text=text, keyboard=empty_result_keyboard()),
        screen_type="empty",
        source_message=source_message,
    )


async def _render_card(
    bot: Bot,
    session: UserSession,
    *,
    source_message: Message | None = None,
    notice: str | None = None,
) -> None:
    result = await asyncio.to_thread(_load_result, session)
    session.last_result = result
    session.pagination_state.page = result.page
    session.pagination_state.pages = result.pages
    session.pagination_state.total = result.total

    if not result.items:
        session.current_listing = None
        await _render_empty(bot, session, source_message=source_message, notice=notice)
        return

    card = result.items[0]
    session.current_listing = card
    session.last_query_hash = _compute_query_hash(session)

    favorite = await asyncio.to_thread(
        is_favorite,
        user_id=session.user_id,
        source=card.source,
        external_id=card.external_id,
    )

    photo_url = await asyncio.to_thread(resolve_listing_photo, card.url)
    if photo_url:
        photo_url = with_cache_bust(photo_url, card.external_id)

    text = build_listing_card_text(card=card, page=result.page, pages=result.pages, photo_found=bool(photo_url))
    if notice:
        text = f"{notice}\n\n{text}"

    await screen_manager.render(
        bot,
        session,
        ScreenPayload(
            text=text,
            keyboard=listing_keyboard(
                listing_url=card.url,
                is_favorite=favorite,
                page=result.page,
                pages=result.pages,
                back_action=_back_action_for_mode(session.mode),
            ),
            photo_url=photo_url,
        ),
        screen_type="results",
        source_message=source_message,
    )


async def _start_search_from_text(message: Message, session: UserSession, query_text: str) -> None:
    session.awaiting_input = None
    await _render_search_screen(message.bot, session, notice="Ищу подходящие варианты...")

    parsed = await asyncio.to_thread(extract_filters, query_text)
    validation_errors = validate_filters(parsed)
    if validation_errors:
        await _render_search_screen(
            message.bot,
            session,
            notice="Ошибка в диапазонах: " + "; ".join(validation_errors),
        )
        return

    if parsed.is_empty():
        await _render_search_screen(
            message.bot,
            session,
            notice=(
                "Не удалось извлечь условия из запроса. "
                "Уточните марку, цвет, год или бюджет."
            ),
        )
        return

    session.mode = "search"
    session.query_text = query_text
    session.filters = parsed
    session.pagination_state.page = 1
    session.notify_on_match = False
    await _render_card(message.bot, session)


async def _handle_waiting_input(message: Message, session: UserSession) -> bool:
    if session.awaiting_input is None or message.text is None:
        return False

    user_text = message.text.strip()
    mode = session.awaiting_input

    if mode == "search_query":
        await _start_search_from_text(message, session, user_text)
        return True

    await _safe_delete_user_message(message)

    if mode == "make_manual":
        session.filters.makes = _make_values_from_input(user_text)
        session.awaiting_input = None
        await _render_filters(message.bot, session, notice="Марки обновлены.")
        return True

    if mode == "model_manual":
        session.filters.models = _model_values_from_input(user_text)
        session.awaiting_input = None
        await _render_filters(message.bot, session, notice="Модели обновлены.")
        return True

    if mode == "year_min":
        try:
            session.filters.year_min = parse_optional_year(user_text)
        except ValueError as exc:
            await _render_input_prompt(message.bot, session, text=f"{exc}\n\nВведите минимальный год или '-'.")
            return True
        session.awaiting_input = "year_max"
        await _render_input_prompt(message.bot, session, text="Введите максимальный год или '-'.")
        return True

    if mode == "year_max":
        try:
            session.filters.year_max = parse_optional_year(user_text)
        except ValueError as exc:
            await _render_input_prompt(message.bot, session, text=f"{exc}\n\nВведите максимальный год или '-'.")
            return True
        errors = validate_filters(session.filters)
        if errors:
            session.awaiting_input = "year_max"
            await _render_input_prompt(message.bot, session, text="; ".join(errors))
            return True
        session.awaiting_input = None
        await _render_filters(message.bot, session, notice="Диапазон года обновлен.")
        return True

    if mode == "price_min":
        try:
            session.filters.price_min_rub = parse_optional_rub(user_text)
        except ValueError as exc:
            await _render_input_prompt(
                message.bot,
                session,
                text=f"{exc}\n\nВведите минимальную цену в RUB или '-'.",
            )
            return True
        session.awaiting_input = "price_max"
        await _render_input_prompt(message.bot, session, text="Введите максимальную цену в RUB или '-'.")
        return True

    if mode == "price_max":
        try:
            session.filters.price_max_rub = parse_optional_rub(user_text)
        except ValueError as exc:
            await _render_input_prompt(
                message.bot,
                session,
                text=f"{exc}\n\nВведите максимальную цену в RUB или '-'.",
            )
            return True
        errors = validate_filters(session.filters)
        if errors:
            session.awaiting_input = "price_max"
            await _render_input_prompt(message.bot, session, text="; ".join(errors))
            return True
        session.awaiting_input = None
        await _render_filters(message.bot, session, notice="Диапазон цены обновлен.")
        return True

    return False


async def _handle_legacy_menu_text(message: Message, session: UserSession) -> bool:
    if message.text is None:
        return False

    text = message.text.strip().lower()
    mapping = {
        "🔎 поиск": "search",
        "🆕 новые": "recent",
        "🎛 фильтры": "filters",
        "⭐ избранное": "favorites",
        "ℹ️ помощь": "help",
        "❓ помощь": "help",
    }
    action = mapping.get(text)
    if action is None:
        return False

    await _safe_delete_user_message(message)
    if action == "search":
        session.awaiting_input = "search_query"
        await _render_search_screen(message.bot, session)
    elif action == "recent":
        session.mode = "recent"
        session.awaiting_input = None
        session.pagination_state.page = 1
        await _render_card(message.bot, session)
    elif action == "filters":
        session.awaiting_input = None
        await _render_filters(message.bot, session)
    elif action == "favorites":
        session.mode = "favorites"
        session.awaiting_input = None
        session.pagination_state.page = 1
        await _render_card(message.bot, session)
    else:
        await _render_help(message.bot, session)
    return True


@router.message(CommandStart())
async def on_start(message: Message) -> None:
    session = store.get_or_create(user_id=message.from_user.id, chat_id=message.chat.id)
    session.awaiting_input = None
    await _render_main_menu(message.bot, session)


@router.message(Command("help"))
async def on_help(message: Message) -> None:
    session = store.get_or_create(user_id=message.from_user.id, chat_id=message.chat.id)
    session.awaiting_input = None
    await _render_help(message.bot, session)


@router.message(Command("search"))
async def on_search(message: Message) -> None:
    session = store.get_or_create(user_id=message.from_user.id, chat_id=message.chat.id)
    session.awaiting_input = "search_query"
    await _render_search_screen(message.bot, session)


@router.message(Command("filters"))
async def on_filters(message: Message) -> None:
    session = store.get_or_create(user_id=message.from_user.id, chat_id=message.chat.id)
    session.awaiting_input = None
    await _render_filters(message.bot, session)


@router.message(Command("recent"))
async def on_recent(message: Message) -> None:
    session = store.get_or_create(user_id=message.from_user.id, chat_id=message.chat.id)
    session.mode = "recent"
    session.awaiting_input = None
    session.pagination_state.page = 1
    await _render_card(message.bot, session)


@router.message(Command("favorites"))
async def on_favorites(message: Message) -> None:
    session = store.get_or_create(user_id=message.from_user.id, chat_id=message.chat.id)
    session.mode = "favorites"
    session.awaiting_input = None
    session.pagination_state.page = 1
    await _render_card(message.bot, session)


@router.message(Command("settings"))
async def on_settings(message: Message) -> None:
    session = store.get_or_create(user_id=message.from_user.id, chat_id=message.chat.id)
    session.awaiting_input = None
    await _render_settings(message.bot, session)


@router.message(F.text)
async def on_text(message: Message) -> None:
    if message.from_user is None:
        return
    session = store.get_or_create(user_id=message.from_user.id, chat_id=message.chat.id)

    if await _handle_waiting_input(message, session):
        return
    if await _handle_legacy_menu_text(message, session):
        return

    text = (message.text or "").strip()
    if not text:
        await _render_search_screen(message.bot, session, notice="Пустой запрос.")
        return
    await _start_search_from_text(message, session, text)


async def _handle_menu_callback(callback: CallbackQuery, session: UserSession, action: str) -> None:
    if callback.message is None:
        return
    if action == "home":
        session.awaiting_input = None
        await _render_main_menu(callback.bot, session, source_message=callback.message)
    elif action == "search":
        session.awaiting_input = "search_query"
        await _render_search_screen(callback.bot, session, source_message=callback.message)
    elif action == "filters":
        session.awaiting_input = None
        await _render_filters(callback.bot, session, source_message=callback.message)
    elif action == "recent":
        session.mode = "recent"
        session.awaiting_input = None
        session.pagination_state.page = 1
        await _render_card(callback.bot, session, source_message=callback.message)
    elif action == "favorites":
        session.mode = "favorites"
        session.awaiting_input = None
        session.pagination_state.page = 1
        await _render_card(callback.bot, session, source_message=callback.message)
    elif action == "help":
        session.awaiting_input = None
        await _render_help(callback.bot, session, source_message=callback.message)
    elif action == "settings":
        session.awaiting_input = None
        await _render_settings(callback.bot, session, source_message=callback.message)


@router.callback_query(UICallback.filter())
async def on_ui_callback(callback: CallbackQuery, callback_data: UICallback) -> None:
    if callback.message is None:
        await callback.answer()
        return

    session = store.get_or_create(user_id=callback.from_user.id, chat_id=callback.message.chat.id)
    if session.screen_message_id is not None and callback.message.message_id != session.screen_message_id:
        await screen_manager.close(callback.bot, session, callback.message)
        await callback.answer("Экран устарел")
        return

    if callback_data.scope == "ui" and callback_data.action == "close":
        await screen_manager.close(callback.bot, session, callback.message)
        await callback.answer("Закрыто")
        return

    if callback_data.scope == "menu":
        await _handle_menu_callback(callback, session, callback_data.action)
        await callback.answer()
        return

    if callback_data.scope == "settings" and callback_data.action == "toggle_notify":
        session.notify_on_match = not session.notify_on_match
        await _render_settings(callback.bot, session, source_message=callback.message)
        await callback.answer("Настройка обновлена")
        return

    if callback_data.scope == "card":
        if callback_data.action == "noop":
            await callback.answer()
            return
        if callback_data.action == "prev":
            session.pagination_state.page = max(1, session.pagination_state.page - 1)
            await _render_card(callback.bot, session, source_message=callback.message)
            await callback.answer()
            return
        if callback_data.action == "next":
            session.pagination_state.page = session.pagination_state.page + 1
            await _render_card(callback.bot, session, source_message=callback.message)
            await callback.answer()
            return
        if callback_data.action == "refresh":
            await _render_card(callback.bot, session, source_message=callback.message, notice="Обновлено")
            await callback.answer()
            return
        if callback_data.action == "favorite":
            if session.current_listing is None:
                await callback.answer("Карточка устарела", show_alert=True)
                return
            now_favorite = await asyncio.to_thread(
                toggle_favorite,
                user_id=session.user_id,
                source=session.current_listing.source,
                external_id=session.current_listing.external_id,
            )
            await _render_card(callback.bot, session, source_message=callback.message)
            await callback.answer("Добавлено в избранное" if now_favorite else "Удалено из избранного")
            return

    if callback_data.scope == "empty":
        if callback_data.action == "retry":
            session.pagination_state.page = 1
            await _render_card(callback.bot, session, source_message=callback.message)
            await callback.answer()
            return
        if callback_data.action == "notify":
            session.notify_on_match = True
            enqueue = await _enqueue_scrape_for_session(session)
            if enqueue.triggered:
                notice = "Уведомление включено. Поставил обновление в очередь."
            elif enqueue.reason == "queue_full":
                notice = "Уведомление включено, но очередь обновления сейчас перегружена."
            elif enqueue.reason == "duplicate":
                notice = "Уведомление включено. Похожий запрос уже в очереди."
            else:
                notice = "Уведомление включено, но задачу в очередь поставить не удалось."
            await _render_empty(callback.bot, session, source_message=callback.message, notice=notice)
            await callback.answer()
            return

    if callback_data.scope == "filter":
        action = callback_data.action
        value = callback_data.value

        if action == "make_menu":
            await _render_make_picker(callback.bot, session, source_message=callback.message)
            await callback.answer()
            return
        if action == "set_make":
            session.filters.makes = _toggle_value(session.filters.makes, value)
            await _render_make_picker(callback.bot, session, source_message=callback.message)
            await callback.answer()
            return
        if action == "clear_make":
            session.filters.makes = []
            await _render_make_picker(callback.bot, session, source_message=callback.message)
            await callback.answer()
            return
        if action == "make_manual":
            session.awaiting_input = "make_manual"
            await _render_input_prompt(
                callback.bot,
                session,
                source_message=callback.message,
                text="Введите марки через запятую. Пример: BMW, Toyota, Nissan",
            )
            await callback.answer()
            return

        if action == "model_menu":
            await _render_model_picker(callback.bot, session, source_message=callback.message)
            await callback.answer()
            return
        if action == "set_model":
            session.filters.models = _toggle_value(session.filters.models, value)
            await _render_model_picker(callback.bot, session, source_message=callback.message)
            await callback.answer()
            return
        if action == "clear_model":
            session.filters.models = []
            await _render_model_picker(callback.bot, session, source_message=callback.message)
            await callback.answer()
            return
        if action == "model_manual":
            session.awaiting_input = "model_manual"
            await _render_input_prompt(
                callback.bot,
                session,
                source_message=callback.message,
                text="Введите модели через запятую. Пример: X5, Camry, Corolla",
            )
            await callback.answer()
            return

        if action == "color_menu":
            await _render_color_picker(callback.bot, session, source_message=callback.message)
            await callback.answer()
            return
        if action == "set_color":
            color = value.title()
            session.filters.colors = _toggle_value(session.filters.colors, color)
            session.filters.exclude_colors = [item for item in session.filters.exclude_colors if item != color]
            await _render_color_picker(callback.bot, session, source_message=callback.message)
            await callback.answer()
            return
        if action == "toggle_excluded_color":
            color = value.title()
            session.filters.exclude_colors = _toggle_value(session.filters.exclude_colors, color)
            session.filters.colors = [item for item in session.filters.colors if item != color]
            await _render_color_picker(callback.bot, session, source_message=callback.message)
            await callback.answer()
            return
        if action == "clear_color":
            session.filters.colors = []
            session.filters.exclude_colors = []
            await _render_color_picker(callback.bot, session, source_message=callback.message)
            await callback.answer()
            return

        if action == "year_input":
            session.awaiting_input = "year_min"
            await _render_input_prompt(
                callback.bot,
                session,
                source_message=callback.message,
                text="Введите минимальный год (например 2015) или '-' для пропуска.",
            )
            await callback.answer()
            return
        if action == "price_input":
            session.awaiting_input = "price_min"
            await _render_input_prompt(
                callback.bot,
                session,
                source_message=callback.message,
                text="Введите минимальную цену в RUB (например 2м) или '-' для пропуска.",
            )
            await callback.answer()
            return

        if action == "toggle_active":
            session.filters.only_active = not session.filters.only_active
            await _render_filters(callback.bot, session, source_message=callback.message)
            await callback.answer("Фильтр активности обновлен")
            return

        if action == "reset":
            session.filters.clear()
            session.query_text = None
            session.awaiting_input = None
            session.notify_on_match = False
            await _render_filters(callback.bot, session, source_message=callback.message, notice="Фильтры сброшены.")
            await callback.answer()
            return

        if action == "apply":
            errors = validate_filters(session.filters)
            if errors:
                await _render_filters(
                    callback.bot,
                    session,
                    source_message=callback.message,
                    notice="Ошибка в фильтрах: " + "; ".join(errors),
                )
                await callback.answer()
                return
            session.mode = "search"
            session.query_text = None
            session.awaiting_input = None
            session.pagination_state.page = 1
            await _render_card(callback.bot, session, source_message=callback.message)
            await callback.answer()
            return

    await callback.answer()


async def _notification_loop(bot: Bot) -> None:
    while True:
        await asyncio.sleep(45)
        for session in store.iter_sessions():
            if not session.notify_on_match or session.mode != "search":
                continue
            try:
                result = await asyncio.to_thread(
                    search_cars,
                    filters=session.filters,
                    page=1,
                    page_size=1,
                    query_text=None,
                )
                if not result.items:
                    continue
                session.notify_on_match = False
                session.pagination_state.page = 1
                await _render_card(bot, session, notice="Появились новые варианты по вашему запросу.")
            except Exception:
                logger.exception("Notification refresh failed for chat_id=%s", session.chat_id)


async def _main() -> None:
    while True:
        bot = Bot(
            token=SETTINGS.telegram_bot_token,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        )
        notification_task: asyncio.Task | None = None
        try:
            logger.info(
                "Telegram bot started. llm_enabled=%s provider=%s model=%s",
                SETTINGS.llm_enabled,
                SETTINGS.llm_provider,
                SETTINGS.openai_model,
            )
            notification_task = asyncio.create_task(_notification_loop(bot))
            await dp.start_polling(bot)
            return
        except Exception:
            logger.exception("Bot polling failed. Retrying in 10s.")
            await asyncio.sleep(10)
        finally:
            if notification_task is not None:
                notification_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await notification_task
            await bot.session.close()


if __name__ == "__main__":
    asyncio.run(_main())
