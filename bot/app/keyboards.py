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
                InlineKeyboardButton(text="⚙️ Настройки", callback_data=_cb("menu", "settings")),
                InlineKeyboardButton(text="ℹ️ Помощь", callback_data=_cb("menu", "help")),
            ],
            [InlineKeyboardButton(text="❌ Закрыть", callback_data=_cb("ui", "close"))],
        ]
    )


def help_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🔎 К поиску", callback_data=_cb("menu", "search")),
                InlineKeyboardButton(text="🎛 Фильтры", callback_data=_cb("menu", "filters")),
            ],
            [InlineKeyboardButton(text="⬅️ В меню", callback_data=_cb("menu", "home"))],
        ]
    )


def settings_keyboard(notify_enabled: bool) -> InlineKeyboardMarkup:
    notify_text = "🔔 Уведомления: вкл" if notify_enabled else "🔕 Уведомления: выкл"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=notify_text, callback_data=_cb("settings", "toggle_notify"))],
            [InlineKeyboardButton(text="⬅️ В меню", callback_data=_cb("menu", "home"))],
        ]
    )


def search_screen_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🎛 Настроить фильтры", callback_data=_cb("menu", "filters"))],
            [
                InlineKeyboardButton(text="🆕 Новые", callback_data=_cb("menu", "recent")),
                InlineKeyboardButton(text="⬅️ В меню", callback_data=_cb("menu", "home")),
            ],
            [InlineKeyboardButton(text="❌ Закрыть", callback_data=_cb("ui", "close"))],
        ]
    )


def listing_keyboard(
    *,
    listing_url: str,
    is_favorite: bool,
    page: int,
    pages: int,
    back_action: str = "home",
) -> InlineKeyboardMarkup:
    prev_callback = _cb("card", "prev") if page > 1 else _cb("card", "noop")
    next_callback = _cb("card", "next") if page < pages else _cb("card", "noop")
    return InlineKeyboardMarkup(
        inline_keyboard=[
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
            [
                InlineKeyboardButton(text="🔁 Обновить", callback_data=_cb("card", "refresh")),
                InlineKeyboardButton(text="🎛 Фильтры", callback_data=_cb("menu", "filters")),
            ],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data=_cb("menu", back_action))],
        ]
    )


def empty_result_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔁 Проверить снова", callback_data=_cb("empty", "retry"))],
            [InlineKeyboardButton(text="🔔 Уведомить, когда появится", callback_data=_cb("empty", "notify"))],
            [InlineKeyboardButton(text="🎛 Изменить фильтры", callback_data=_cb("menu", "filters"))],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data=_cb("menu", "home"))],
        ]
    )


def awaiting_input_keyboard(back_to: str = "filters") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад", callback_data=_cb("menu", back_to))],
            [InlineKeyboardButton(text="❌ Закрыть", callback_data=_cb("ui", "close"))],
        ]
    )


def filter_menu_keyboard(filters: SearchFilters) -> InlineKeyboardMarkup:
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
            [InlineKeyboardButton(text="⬅️ Назад", callback_data=_cb("menu", "home"))],
        ]
    )


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


def make_picker_keyboard(selected: list[str]) -> InlineKeyboardMarkup:
    values = [
        "Toyota",
        "Nissan",
        "Honda",
        "Mazda",
        "Subaru",
        "Lexus",
        "BMW",
        "Mercedes-Benz",
        "Audi",
        "Volkswagen",
    ]
    rows = _picker_rows(values=values, selected=set(selected), callback_action="set_make")
    rows.extend(
        [
            [InlineKeyboardButton(text="✍️ Ввести вручную", callback_data=_cb("filter", "make_manual"))],
            [InlineKeyboardButton(text="🧹 Очистить", callback_data=_cb("filter", "clear_make"))],
            [InlineKeyboardButton(text="⬅️ Назад к фильтрам", callback_data=_cb("menu", "filters"))],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def model_picker_keyboard(selected: list[str]) -> InlineKeyboardMarkup:
    values = [
        "Corolla",
        "Camry",
        "Prius",
        "Civic",
        "Fit",
        "X5",
        "3 Series",
        "1 Series",
        "NX",
        "C-Class",
        "A4",
        "Golf",
    ]
    rows = _picker_rows(values=values, selected=set(selected), callback_action="set_model")
    rows.extend(
        [
            [InlineKeyboardButton(text="✍️ Ввести вручную", callback_data=_cb("filter", "model_manual"))],
            [InlineKeyboardButton(text="🧹 Очистить", callback_data=_cb("filter", "clear_model"))],
            [InlineKeyboardButton(text="⬅️ Назад к фильтрам", callback_data=_cb("menu", "filters"))],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def color_picker_keyboard(selected: list[str], excluded: list[str]) -> InlineKeyboardMarkup:
    values = ["Black", "White", "Red", "Blue", "Gray", "Silver", "Yellow", "Green", "Other"]
    selected_set = set(selected)
    excluded_set = set(excluded)
    rows = _picker_rows(values=values, selected=selected_set, callback_action="set_color")
    rows.append(
        [
            InlineKeyboardButton(
                text=f"{'🚫 ' if color in excluded_set else ''}{color}",
                callback_data=_cb("filter", "toggle_excluded_color", color),
            )
            for color in ("Red", "Gray", "Black")
        ]
    )
    rows.extend(
        [
            [InlineKeyboardButton(text="🧹 Очистить", callback_data=_cb("filter", "clear_color"))],
            [InlineKeyboardButton(text="⬅️ Назад к фильтрам", callback_data=_cb("menu", "filters"))],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)

