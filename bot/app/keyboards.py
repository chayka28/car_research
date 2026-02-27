from __future__ import annotations

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.schemas import SearchFilters


class UICallback(CallbackData, prefix="ui"):
    scope: str
    action: str
    value: str


def _cb(scope: str, action: str, value: str = "_") -> str:
    return UICallback(scope=scope, action=action, value=value).pack()


def _preview(values: list[str], fallback: str = "-") -> str:
    cleaned = [value for value in values if value]
    if not cleaned:
        return fallback
    if len(cleaned) <= 2:
        return ", ".join(cleaned)
    return f"{cleaned[0]}, {cleaned[1]} +{len(cleaned) - 2}"


def main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🆕 Новые", callback_data=_cb("menu", "recent")),
                InlineKeyboardButton(text="🔎 Поиск", callback_data=_cb("menu", "search")),
            ],
            [
                InlineKeyboardButton(text="🎛 Фильтры", callback_data=_cb("menu", "filters")),
                InlineKeyboardButton(text="⭐ Избранное", callback_data=_cb("menu", "favorites")),
            ],
            [
                InlineKeyboardButton(text="🗂 Лист ожидания", callback_data=_cb("menu", "waitlist")),
                InlineKeyboardButton(text="ℹ️ Помощь", callback_data=_cb("menu", "help")),
            ],
        ]
    )


def help_keyboard(*, back_action: str = "home", show_back: bool = False) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(text="🔎 К поиску", callback_data=_cb("menu", "search")),
            InlineKeyboardButton(text="🎛 Фильтры", callback_data=_cb("menu", "filters")),
        ]
    ]
    nav_row: list[InlineKeyboardButton] = []
    if show_back:
        nav_row.append(InlineKeyboardButton(text="⬅ Назад", callback_data=_cb("menu", back_action)))
    nav_row.append(InlineKeyboardButton(text="🏠 Меню", callback_data=_cb("menu", "home")))
    rows.append(nav_row)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def search_screen_keyboard(*, back_action: str = "home", show_back: bool = False) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text="🎛 Настроить фильтры", callback_data=_cb("menu", "filters"))],
        [InlineKeyboardButton(text="🆕 Новые", callback_data=_cb("menu", "recent"))],
    ]
    nav_row: list[InlineKeyboardButton] = []
    if show_back:
        nav_row.append(InlineKeyboardButton(text="⬅ Назад", callback_data=_cb("menu", back_action)))
    nav_row.append(InlineKeyboardButton(text="🏠 Меню", callback_data=_cb("menu", "home")))
    rows.append(nav_row)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def listing_keyboard(
    *,
    listing_url: str,
    is_favorite: bool,
    page: int,
    pages: int,
    back_action: str,
    show_filters: bool,
    show_back: bool = True,
) -> InlineKeyboardMarkup:
    prev_callback = _cb("card", "prev") if page > 1 else _cb("card", "noop")
    next_callback = _cb("card", "next") if page < pages else _cb("card", "noop")

    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(text="🔗 Открыть", url=listing_url),
            InlineKeyboardButton(
                text="✅ В избранном" if is_favorite else "⭐ В избранное",
                callback_data=_cb("card", "favorite"),
            ),
        ],
        [
            InlineKeyboardButton(text="⬅️", callback_data=prev_callback),
            InlineKeyboardButton(text=f"{page}/{pages}", callback_data=_cb("card", "noop")),
            InlineKeyboardButton(text="➡️", callback_data=next_callback),
        ],
    ]

    action_row = [InlineKeyboardButton(text="🔁 Обновить", callback_data=_cb("card", "refresh"))]
    if show_filters:
        action_row.append(InlineKeyboardButton(text="🎛 Фильтры", callback_data=_cb("menu", "filters")))
    rows.append(action_row)
    nav_row: list[InlineKeyboardButton] = []
    if show_back:
        nav_row.append(InlineKeyboardButton(text="⬅ Назад", callback_data=_cb("menu", back_action)))
    nav_row.append(InlineKeyboardButton(text="🏠 Меню", callback_data=_cb("menu", "home")))
    rows.append(nav_row)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def empty_result_keyboard(
    *,
    back_action: str,
    show_filters: bool = True,
    show_retry: bool = True,
    show_back: bool = True,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text="🔔 Уведомить, когда появится", callback_data=_cb("empty", "notify"))],
    ]
    if show_retry:
        rows.insert(0, [InlineKeyboardButton(text="🔁 Проверить снова", callback_data=_cb("empty", "retry"))])
    if show_filters:
        rows.append([InlineKeyboardButton(text="🎛 Изменить фильтры", callback_data=_cb("menu", "filters"))])
    nav_row: list[InlineKeyboardButton] = []
    if show_back:
        nav_row.append(InlineKeyboardButton(text="⬅ Назад", callback_data=_cb("menu", back_action)))
    nav_row.append(InlineKeyboardButton(text="🏠 Меню", callback_data=_cb("menu", "home")))
    rows.append(nav_row)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def awaiting_input_keyboard(*, back_to: str = "filters", show_back: bool = True) -> InlineKeyboardMarkup:
    nav_row: list[InlineKeyboardButton] = []
    if show_back:
        nav_row.append(InlineKeyboardButton(text="⬅ Назад", callback_data=_cb("menu", back_to)))
    nav_row.append(InlineKeyboardButton(text="🏠 Меню", callback_data=_cb("menu", "home")))
    return InlineKeyboardMarkup(inline_keyboard=[nav_row])


def filter_menu_keyboard(
    filters: SearchFilters,
    *,
    back_action: str = "home",
    show_back: bool = True,
) -> InlineKeyboardMarkup:
    year_value = f"{filters.year_min or '-'} .. {filters.year_max or '-'}"
    price_value = f"{filters.price_min_rub or '-'} .. {filters.price_max_rub or '-'} ₽"
    activity = "Да" if filters.only_active else "Нет"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"Марка: {_preview(filters.makes)}", callback_data=_cb("filter", "make_menu"))],
            [InlineKeyboardButton(text=f"Модель: {_preview(filters.models)}", callback_data=_cb("filter", "model_menu"))],
            [InlineKeyboardButton(text=f"Цвет: {_preview(filters.colors)}", callback_data=_cb("filter", "color_menu"))],
            [InlineKeyboardButton(text=f"Год: {year_value}", callback_data=_cb("filter", "year_input"))],
            [InlineKeyboardButton(text=f"Цена: {price_value}", callback_data=_cb("filter", "price_input"))],
            [InlineKeyboardButton(text=f"Только активные: {activity}", callback_data=_cb("filter", "toggle_active"))],
            [
                InlineKeyboardButton(text="✅ Применить", callback_data=_cb("filter", "apply")),
                InlineKeyboardButton(text="♻️ Сбросить", callback_data=_cb("filter", "reset")),
            ],
            _nav_row(back_action=back_action, show_back=show_back),
        ]
    )


def _nav_row(*, back_action: str, show_back: bool) -> list[InlineKeyboardButton]:
    row: list[InlineKeyboardButton] = []
    if show_back:
        row.append(InlineKeyboardButton(text="⬅ Назад", callback_data=_cb("menu", back_action)))
    row.append(InlineKeyboardButton(text="🏠 Меню", callback_data=_cb("menu", "home")))
    return row


def _picker_rows(
    *,
    values: list[str],
    selected: set[str],
    callback_action: str,
    row_size: int = 3,
) -> list[list[InlineKeyboardButton]]:
    rows: list[list[InlineKeyboardButton]] = []
    for idx in range(0, len(values), row_size):
        batch = values[idx : idx + row_size]
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{'✅ ' if item in selected else ''}{item}",
                    callback_data=_cb("filter", callback_action, item),
                )
                for item in batch
            ]
        )
    return rows


def make_picker_keyboard(*, options: list[str], selected: list[str], back_action: str = "filters") -> InlineKeyboardMarkup:
    rows = _picker_rows(values=options, selected=set(selected), callback_action="set_make")
    rows.extend(
        [
            [InlineKeyboardButton(text="✍️ Ввести вручную", callback_data=_cb("filter", "make_manual"))],
            [InlineKeyboardButton(text="🧹 Очистить", callback_data=_cb("filter", "clear_make"))],
            _nav_row(back_action=back_action, show_back=True),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def model_picker_keyboard(*, options: list[str], selected: list[str], back_action: str = "filters") -> InlineKeyboardMarkup:
    rows = _picker_rows(values=options, selected=set(selected), callback_action="set_model")
    rows.extend(
        [
            [InlineKeyboardButton(text="✍️ Ввести вручную", callback_data=_cb("filter", "model_manual"))],
            [InlineKeyboardButton(text="🧹 Очистить", callback_data=_cb("filter", "clear_model"))],
            _nav_row(back_action=back_action, show_back=True),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def color_picker_keyboard(
    *,
    options: list[str],
    selected: list[str],
    excluded: list[str],
    back_action: str = "filters",
) -> InlineKeyboardMarkup:
    selected_set = set(selected)
    _ = excluded  # keep signature stable; exclude-color UX is disabled in favor of regular selection
    rows = _picker_rows(values=options, selected=selected_set, callback_action="set_color")
    rows.extend(
        [
            [InlineKeyboardButton(text="🧹 Очистить", callback_data=_cb("filter", "clear_color"))],
            _nav_row(back_action=back_action, show_back=True),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def waitlist_keyboard(entries: list[str], *, back_action: str = "home", show_back: bool = False) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for idx, label in enumerate(entries, start=1):
        rows.append([InlineKeyboardButton(text=f"🔁 {idx}. {label}", callback_data=_cb("waitlist", "run", str(idx - 1)))])
    if entries:
        rows.append([InlineKeyboardButton(text="🧹 Очистить лист ожидания", callback_data=_cb("waitlist", "clear"))])
    rows.append(_nav_row(back_action=back_action, show_back=show_back))
    return InlineKeyboardMarkup(inline_keyboard=rows)
