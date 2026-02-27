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
    waitlist_keyboard,
)
from app.openai_filters import extract_filters
from app.photo import resolve_listing_photo, with_cache_bust
from app.repository import (
    EnqueueResult,
    enqueue_scrape_request,
    favorite_cars,
    is_favorite,
    list_filter_makes,
    list_filter_models,
    recent_cars,
    search_cars,
    toggle_favorite,
)
from app.schemas import PagedResult, SearchFilters
from app.state import UserSession, WaitlistEntry, init_session_store
from app.ui import ScreenManager, ScreenPayload
from app.validators import parse_optional_rub, parse_optional_year, validate_filters

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

dp = Dispatcher()
router = Router()
dp.include_router(router)
store = init_session_store(SETTINGS.bot_session_ttl_seconds)
screen_manager = ScreenManager()
DEFAULT_COLOR_OPTIONS = ["Black", "White", "Red", "Blue", "Gray", "Silver", "Yellow", "Green", "Other"]


def _normalize_csv(text: str) -> list[str]:
    raw_items = [item.strip() for item in text.replace(";", ",").split(",")]
    return [item for item in raw_items if item]


def _make_values_from_input(text: str) -> list[str]:
    values: list[str] = []
    for item in _normalize_csv(text):
        if len(item) <= 4 and item.isalpha():
            values.append(item.upper())
        else:
            values.append(item.title())
    return values


def _model_values_from_input(text: str) -> list[str]:
    return _normalize_csv(text)


def _toggle_value(values: list[str], item: str) -> list[str]:
    candidate = item.strip()
    if not candidate:
        return values
    if candidate in values:
        return [value for value in values if value != candidate]
    return values + [candidate]


def _value_in_options(value: str, options: list[str]) -> bool:
    value_norm = value.strip().lower()
    return any(value_norm == option.strip().lower() for option in options)


def _keep_only_allowed(values: list[str], options: list[str]) -> list[str]:
    allowed = {item.strip().lower() for item in options}
    return [item for item in values if item.strip().lower() in allowed]


def _filters_payload(filters: SearchFilters) -> dict[str, object]:
    return {
        "makes": list(filters.makes),
        "models": list(filters.models),
        "colors": list(filters.colors),
        "exclude_colors": list(filters.exclude_colors),
        "year_min": filters.year_min,
        "year_max": filters.year_max,
        "price_min_rub": filters.price_min_rub,
        "price_max_rub": filters.price_max_rub,
        "sort": filters.sort,
        "only_active": filters.only_active,
    }


def _compute_query_hash(session: UserSession) -> str:
    payload = {
        "mode": session.mode,
        "query_text": session.query_text or "",
        "filters": _filters_payload(session.filters),
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha1(encoded).hexdigest()


def _make_search_hash(query_text: str | None, filters: SearchFilters) -> str:
    payload = {"query_text": query_text or "", "filters": _filters_payload(filters)}
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha1(encoded).hexdigest()


def _waitlist_entry_title(query_text: str | None, filters: SearchFilters) -> str:
    if query_text and query_text.strip():
        return query_text.strip()[:80]
    parts: list[str] = []
    if filters.makes:
        parts.append("/".join(filters.makes[:2]))
    if filters.models:
        parts.append("/".join(filters.models[:2]))
    if filters.colors:
        parts.append("/".join(filters.colors[:2]))
    if filters.price_max_rub is not None:
        parts.append(f"до {filters.price_max_rub:,} ₽".replace(",", " "))
    if filters.year_min is not None:
        parts.append(f"{filters.year_min}+")
    return " | ".join(parts) if parts else "Запрос без текста"


def _clone_filters(filters: SearchFilters) -> SearchFilters:
    return SearchFilters(
        makes=list(filters.makes),
        models=list(filters.models),
        colors=list(filters.colors),
        exclude_colors=list(filters.exclude_colors),
        year_min=filters.year_min,
        year_max=filters.year_max,
        price_min_rub=filters.price_min_rub,
        price_max_rub=filters.price_max_rub,
        sort=filters.sort,
        only_active=filters.only_active,
    )


def _add_waitlist_entry(session: UserSession) -> bool:
    entry_hash = _make_search_hash(session.query_text, session.filters)
    if any(item.query_hash == entry_hash for item in session.waitlist):
        return False

    session.waitlist.insert(
        0,
        WaitlistEntry(
            query_hash=entry_hash,
            title=_waitlist_entry_title(session.query_text, session.filters),
            query_text=session.query_text,
            filters=_clone_filters(session.filters),
        ),
    )
    if len(session.waitlist) > 20:
        session.waitlist = session.waitlist[:20]
    return True


def _back_action_for_mode(mode: str) -> str:
    if mode == "search":
        return "search"
    return "home"


def _derive_filters_back_action(session: UserSession) -> str:
    if session.last_screen_type in {"results", "empty"}:
        return _back_action_for_mode(session.mode)
    if session.last_screen_type == "search":
        return "search"
    if session.last_screen_type in {"filter_make", "filter_model", "filter_color", "filters", "input"}:
        return session.filter_back_action
    return "home"


def _message_for_empty(mode: str) -> str:
    if mode == "favorites":
        return "В избранном пока нет объявлений."
    if mode == "recent":
        return "Новые объявления пока не найдены."
    return "Пока нет подходящих предложений в базе."


def _is_top_level_mode(mode: str) -> bool:
    return mode in {"recent", "favorites"}


async def _available_make_options(session: UserSession, *, limit: int = 10) -> list[str]:
    return await asyncio.to_thread(list_filter_makes, only_active=session.filters.only_active, limit=limit)


async def _available_model_options(session: UserSession, *, limit: int = 10) -> list[str]:
    return await asyncio.to_thread(
        list_filter_models,
        makes=session.filters.makes,
        only_active=session.filters.only_active,
        limit=limit,
    )


async def _available_color_options(_: UserSession) -> list[str]:
    return list(DEFAULT_COLOR_OPTIONS)


async def _sync_dependent_filters(session: UserSession) -> None:
    model_options = await _available_model_options(session, limit=5000)
    session.filters.models = _keep_only_allowed(session.filters.models, model_options)
    color_options = await _available_color_options(session)
    session.filters.colors = _keep_only_allowed(session.filters.colors, color_options)
    session.filters.exclude_colors = _keep_only_allowed(session.filters.exclude_colors, color_options)


async def _render_main_menu(
    bot: Bot,
    session: UserSession,
    *,
    source_message: Message | None = None,
    notice: str | None = None,
) -> None:
    text = (
        "CarResearch — умный поиск автомобилей 🚗✨\n\n"
        "Мы автоматически собираем актуальные предложения и помогаем вам быстро найти лучший вариант.\n\n"
        "Что вы можете сделать:\n"
        "• Посмотреть новые объявления\n"
        "• Настроить фильтры поиска\n"
        "• Сохранить авто в избранное\n"
        "• Быстро искать нужные вам авто\n\n"
        "Используйте меню ниже и найдите свой идеальный автомобиль уже сейчас."
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


async def _render_help(
    bot: Bot,
    session: UserSession,
    *,
    source_message: Message | None = None,
    back_action: str = "home",
) -> None:
    show_back = back_action != "home"
    text = (
        "Как пользоваться:\n"
        "1. Нажмите «🔎 Поиск» и отправьте запрос свободным текстом.\n"
        "2. Или задайте условия через «🎛 Фильтры».\n"
        "3. Листайте карточки кнопками ◀️/▶️.\n\n"
        "Примеры запросов:\n"
        "• тойота до 2 миллионов\n"
        "• найди белый ниссан до 10 млн, не красный\n"
        "• BMW 2015+"
    )
    await screen_manager.render(
        bot,
        session,
        ScreenPayload(text=text, keyboard=help_keyboard(back_action=back_action, show_back=show_back)),
        screen_type="help",
        source_message=source_message,
    )


async def _render_search_screen(
    bot: Bot,
    session: UserSession,
    *,
    source_message: Message | None = None,
    notice: str | None = None,
    back_action: str = "home",
) -> None:
    show_back = back_action != "home"
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
        ScreenPayload(text=text, keyboard=search_screen_keyboard(back_action=back_action, show_back=show_back)),
        screen_type="search",
        source_message=source_message,
    )


async def _render_filters(
    bot: Bot,
    session: UserSession,
    *,
    source_message: Message | None = None,
    notice: str | None = None,
    back_action: str | None = None,
) -> None:
    effective_back = back_action or _derive_filters_back_action(session)
    show_back = effective_back != "home"
    session.filter_back_action = effective_back

    text = "Текущие фильтры:\n" + build_filter_summary(session.filters)
    if notice:
        text = f"{notice}\n\n{text}"
    await screen_manager.render(
        bot,
        session,
        ScreenPayload(
            text=text,
            keyboard=filter_menu_keyboard(
                session.filters,
                back_action=effective_back,
                show_back=show_back,
            ),
        ),
        screen_type="filters",
        source_message=source_message,
    )


async def _render_make_picker(
    bot: Bot,
    session: UserSession,
    *,
    source_message: Message | None = None,
) -> None:
    top_options = await _available_make_options(session, limit=10)
    all_options = await _available_make_options(session, limit=5000)
    if not all_options:
        await screen_manager.render(
            bot,
            session,
            ScreenPayload(
                text="Нет доступных марок в данных. Попробуйте обновить базу позже.",
                keyboard=awaiting_input_keyboard(back_to="filters", show_back=True),
            ),
            screen_type="filter_make",
            source_message=source_message,
        )
        return

    session.filters.makes = _keep_only_allowed(session.filters.makes, all_options)
    extra_selected = [item for item in session.filters.makes if item not in top_options]
    options = top_options + extra_selected
    await screen_manager.render(
        bot,
        session,
        ScreenPayload(
            text="Выберите марки (показаны 10 популярных, любую можно ввести вручную):",
            keyboard=make_picker_keyboard(options=options, selected=session.filters.makes, back_action="filters"),
        ),
        screen_type="filter_make",
        source_message=source_message,
    )


async def _render_model_picker(
    bot: Bot,
    session: UserSession,
    *,
    source_message: Message | None = None,
) -> None:
    top_options = await _available_model_options(session, limit=10)
    all_options = await _available_model_options(session, limit=5000)
    session.filters.models = _keep_only_allowed(session.filters.models, all_options)
    options = top_options + [item for item in session.filters.models if item not in top_options]

    if not all_options:
        await screen_manager.render(
            bot,
            session,
            ScreenPayload(
                text="Нет моделей для выбранных марок.",
                keyboard=awaiting_input_keyboard(back_to="filters", show_back=True),
            ),
            screen_type="filter_model",
            source_message=source_message,
        )
        return

    await screen_manager.render(
        bot,
        session,
        ScreenPayload(
            text="Выберите модели (показаны 10 популярных, остальные можно ввести вручную):",
            keyboard=model_picker_keyboard(options=options, selected=session.filters.models, back_action="filters"),
        ),
        screen_type="filter_model",
        source_message=source_message,
    )


async def _render_color_picker(
    bot: Bot,
    session: UserSession,
    *,
    source_message: Message | None = None,
) -> None:
    options = await _available_color_options(session)
    session.filters.colors = _keep_only_allowed(session.filters.colors, options)
    session.filters.exclude_colors = _keep_only_allowed(session.filters.exclude_colors, options)

    await screen_manager.render(
        bot,
        session,
        ScreenPayload(
            text="Выберите цвета (обычный выбор):",
            keyboard=color_picker_keyboard(
                options=options,
                selected=session.filters.colors,
                excluded=session.filters.exclude_colors,
                back_action="filters",
            ),
        ),
        screen_type="filter_color",
        source_message=source_message,
    )


async def _render_waitlist(
    bot: Bot,
    session: UserSession,
    *,
    source_message: Message | None = None,
    notice: str | None = None,
) -> None:
    text = "Лист ожидания\n\n"
    if session.waitlist:
        text += "Нажмите на запрос, чтобы повторить поиск одним кликом."
    else:
        text += "Лист ожидания пуст. Когда по запросу ничего не найдено, добавьте его кнопкой «Проверить снова»."
    if notice:
        text = f"{notice}\n\n{text}"

    labels = [entry.title for entry in session.waitlist]
    await screen_manager.render(
        bot,
        session,
        ScreenPayload(
            text=text,
            keyboard=waitlist_keyboard(labels, back_action="home", show_back=False),
        ),
        screen_type="waitlist",
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
        ScreenPayload(text=text, keyboard=awaiting_input_keyboard(back_to=back_to, show_back=True)),
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
    trigger_scrape: bool = True,
) -> None:
    text = _message_for_empty(session.mode)
    if session.mode == "search" and trigger_scrape:
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
        ScreenPayload(
            text=text,
            keyboard=empty_result_keyboard(
                back_action=_back_action_for_mode(session.mode),
                show_filters=session.mode == "search",
                show_retry=session.mode == "search" and not session.empty_retry_used,
                show_back=session.mode == "search",
            ),
        ),
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
    skip_reasons: list[str] = []
    if not card.external_id:
        skip_reasons.append("missing_id")
    if not card.url:
        skip_reasons.append("missing_url")
    if session.mode == "recent" and card.year is None:
        skip_reasons.append("missing_year")
    if session.mode == "recent" and card.price_rub is None:
        skip_reasons.append("missing_price")

    if skip_reasons:
        logger.info(
            "Skip card chat_id=%s mode=%s reasons=%s listing_id=%s",
            session.chat_id,
            session.mode,
            ",".join(skip_reasons),
            card.id,
        )
        if session.pagination_state.page < session.pagination_state.pages:
            session.pagination_state.page += 1
            await _render_card(bot, session, source_message=source_message, notice="Пропущена неполная карточка.")
            return
        session.current_listing = None
        await _render_empty(bot, session, source_message=source_message, notice="Нет валидных карточек для показа.")
        return

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
        photo_url = with_cache_bust(photo_url, f"{card.external_id}:{card.id}")

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
                show_filters=session.mode == "search",
                show_back=not _is_top_level_mode(session.mode),
            ),
            photo_url=photo_url,
        ),
        screen_type="results",
        source_message=source_message,
    )


async def _start_search_from_text(message: Message, session: UserSession, query_text: str) -> None:
    session.awaiting_input = None
    session.mode = "search"
    session.empty_retry_used = False
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

    session.query_text = query_text
    session.filters = parsed
    session.pagination_state.page = 1
    session.notify_on_match = False
    await _sync_dependent_filters(session)
    await _render_card(message.bot, session)


async def _handle_waiting_input(message: Message, session: UserSession) -> bool:
    if session.awaiting_input is None or message.text is None:
        return False

    user_text = message.text.strip()
    mode = session.awaiting_input

    if mode == "search_query":
        await _start_search_from_text(message, session, user_text)
        return True

    if mode == "make_manual":
        options = await _available_make_options(session, limit=5000)
        entered = _make_values_from_input(user_text)
        accepted = [item for item in entered if _value_in_options(item, options)]
        session.filters.makes = accepted
        session.awaiting_input = None
        await _sync_dependent_filters(session)
        notice = "Марки обновлены." if accepted else "Нет совпадений по маркам в текущих данных."
        await _render_filters(message.bot, session, notice=notice, back_action=session.filter_back_action)
        return True

    if mode == "model_manual":
        options = await _available_model_options(session, limit=5000)
        entered = _model_values_from_input(user_text)
        accepted = [item for item in entered if _value_in_options(item, options)]
        session.filters.models = accepted
        session.awaiting_input = None
        await _sync_dependent_filters(session)
        notice = "Модели обновлены." if accepted else "Нет моделей для выбранных марок."
        await _render_filters(message.bot, session, notice=notice, back_action=session.filter_back_action)
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
        await _render_filters(message.bot, session, notice="Диапазон года обновлен.", back_action=session.filter_back_action)
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
        await _render_filters(message.bot, session, notice="Диапазон цены обновлен.", back_action=session.filter_back_action)
        return True

    return False


@router.message(CommandStart())
async def on_start(message: Message) -> None:
    session = store.get_or_create(user_id=message.from_user.id, chat_id=message.chat.id)
    session.awaiting_input = None
    await _render_main_menu(message.bot, session)


@router.message(Command("help"))
async def on_help(message: Message) -> None:
    session = store.get_or_create(user_id=message.from_user.id, chat_id=message.chat.id)
    session.awaiting_input = None
    await _render_help(message.bot, session, back_action="home")


@router.message(Command("search"))
async def on_search(message: Message) -> None:
    session = store.get_or_create(user_id=message.from_user.id, chat_id=message.chat.id)
    session.awaiting_input = "search_query"
    session.empty_retry_used = False
    await _render_search_screen(message.bot, session, back_action="home")


@router.message(Command("filters"))
async def on_filters(message: Message) -> None:
    session = store.get_or_create(user_id=message.from_user.id, chat_id=message.chat.id)
    session.awaiting_input = None
    await _render_filters(message.bot, session, back_action="home")


@router.message(Command("recent"))
async def on_recent(message: Message) -> None:
    session = store.get_or_create(user_id=message.from_user.id, chat_id=message.chat.id)
    session.mode = "recent"
    session.awaiting_input = None
    session.pagination_state.page = 1
    session.empty_retry_used = False
    await _render_card(message.bot, session)


@router.message(Command("favorites"))
async def on_favorites(message: Message) -> None:
    session = store.get_or_create(user_id=message.from_user.id, chat_id=message.chat.id)
    session.mode = "favorites"
    session.awaiting_input = None
    session.pagination_state.page = 1
    session.empty_retry_used = False
    await _render_card(message.bot, session)


@router.message(Command("waitlist"))
async def on_waitlist(message: Message) -> None:
    session = store.get_or_create(user_id=message.from_user.id, chat_id=message.chat.id)
    session.awaiting_input = None
    await _render_waitlist(message.bot, session)

@router.message(F.text)
async def on_text(message: Message) -> None:
    if message.from_user is None:
        return
    session = store.get_or_create(user_id=message.from_user.id, chat_id=message.chat.id)

    if await _handle_waiting_input(message, session):
        return

    text = (message.text or "").strip()
    if not text:
        await _render_search_screen(message.bot, session, notice="Пустой запрос.", back_action="home")
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
        session.empty_retry_used = False
        await _render_search_screen(callback.bot, session, source_message=callback.message, back_action="home")
    elif action == "filters":
        session.awaiting_input = None
        await _render_filters(callback.bot, session, source_message=callback.message)
    elif action == "recent":
        session.mode = "recent"
        session.awaiting_input = None
        session.empty_retry_used = False
        session.pagination_state.page = 1
        await _render_card(callback.bot, session, source_message=callback.message)
    elif action == "favorites":
        session.mode = "favorites"
        session.awaiting_input = None
        session.empty_retry_used = False
        session.pagination_state.page = 1
        await _render_card(callback.bot, session, source_message=callback.message)
    elif action == "help":
        session.awaiting_input = None
        await _render_help(callback.bot, session, source_message=callback.message, back_action="home")
    elif action == "waitlist":
        session.awaiting_input = None
        await _render_waitlist(callback.bot, session, source_message=callback.message)


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
            session.empty_retry_used = True
            await _render_card(callback.bot, session, source_message=callback.message, notice="Проверяю снова...")
            if session.mode == "search" and session.last_screen_type == "empty":
                added = _add_waitlist_entry(session)
                waitlist_note = "Запрос добавлен в лист ожидания." if added else "Запрос уже есть в листе ожидания."
                await _render_empty(
                    callback.bot,
                    session,
                    source_message=callback.message,
                    notice=waitlist_note + " Откройте «Лист ожидания», чтобы запускать его одним кликом.",
                    trigger_scrape=False,
                )
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
            await _sync_dependent_filters(session)
            await _render_make_picker(callback.bot, session, source_message=callback.message)
            await callback.answer()
            return
        if action == "clear_make":
            session.filters.makes = []
            await _sync_dependent_filters(session)
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
            model_options = await _available_model_options(session, limit=5000)
            if not _value_in_options(value, model_options):
                await callback.answer("Модель недоступна для выбранных марок", show_alert=True)
                await _render_model_picker(callback.bot, session, source_message=callback.message)
                return
            session.filters.models = _toggle_value(session.filters.models, value)
            await _sync_dependent_filters(session)
            await _render_model_picker(callback.bot, session, source_message=callback.message)
            await callback.answer()
            return
        if action == "clear_model":
            session.filters.models = []
            await _sync_dependent_filters(session)
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
            color_options = await _available_color_options(session)
            if not _value_in_options(value, color_options):
                await callback.answer("Цвет недоступен для текущих условий", show_alert=True)
                await _render_color_picker(callback.bot, session, source_message=callback.message)
                return
            color = value.title()
            session.filters.colors = _toggle_value(session.filters.colors, color)
            session.filters.exclude_colors = [item for item in session.filters.exclude_colors if item != color]
            await _render_color_picker(callback.bot, session, source_message=callback.message)
            await callback.answer()
            return
        if action == "toggle_excluded_color":
            color_options = await _available_color_options(session)
            if not _value_in_options(value, color_options):
                await callback.answer("Цвет недоступен для текущих условий", show_alert=True)
                await _render_color_picker(callback.bot, session, source_message=callback.message)
                return
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
            await _sync_dependent_filters(session)
            await _render_filters(
                callback.bot,
                session,
                source_message=callback.message,
                back_action=session.filter_back_action,
            )
            await callback.answer("Фильтр активности обновлен")
            return

        if action == "reset":
            session.filters.clear()
            session.query_text = None
            session.awaiting_input = None
            session.notify_on_match = False
            session.empty_retry_used = False
            await _render_filters(
                callback.bot,
                session,
                source_message=callback.message,
                notice="Фильтры сброшены.",
                back_action=session.filter_back_action,
            )
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
                    back_action=session.filter_back_action,
                )
                await callback.answer()
                return
            session.mode = "search"
            session.query_text = None
            session.awaiting_input = None
            session.pagination_state.page = 1
            session.empty_retry_used = False
            await _sync_dependent_filters(session)
            await _render_card(callback.bot, session, source_message=callback.message)
            await callback.answer()
            return

    if callback_data.scope == "waitlist":
        if callback_data.action == "run":
            try:
                idx = int(callback_data.value)
            except ValueError:
                await callback.answer("Некорректный пункт", show_alert=True)
                return

            if idx < 0 or idx >= len(session.waitlist):
                await _render_waitlist(callback.bot, session, source_message=callback.message, notice="Пункт не найден.")
                await callback.answer()
                return

            entry = session.waitlist[idx]
            session.mode = "search"
            session.awaiting_input = None
            session.query_text = entry.query_text
            session.filters = _clone_filters(entry.filters)
            session.pagination_state.page = 1
            session.empty_retry_used = False
            session.notify_on_match = False
            await _sync_dependent_filters(session)
            await _render_card(callback.bot, session, source_message=callback.message, notice=f"Повторяю запрос: {entry.title}")
            await callback.answer()
            return

        if callback_data.action == "clear":
            session.waitlist = []
            await _render_waitlist(callback.bot, session, source_message=callback.message, notice="Лист ожидания очищен.")
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

