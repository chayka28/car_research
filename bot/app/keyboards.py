from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup

from app.schemas import SearchFilters


class UICallback(CallbackData, prefix="ui"):
    scope: str
    action: str
    value: str


def _cb(scope: str, action: str, value: str = "_") -> str:
    return UICallback(scope=scope, action=action, value=value).pack()


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🔎 Поиск"), KeyboardButton(text="🧰 Фильтры")],
            [KeyboardButton(text="⭐ Избранное"), KeyboardButton(text="🆕 Новые")],
            [KeyboardButton(text="❓ Помощь")],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
    )


def search_prompt_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🧰 Открыть фильтры", callback_data=_cb("filter", "open"))],
        ]
    )


def listing_keyboard(*, listing_url: str, is_favorite: bool, page: int, pages: int) -> InlineKeyboardMarkup:
    prev_page = max(1, page - 1)
    next_page = min(pages, page + 1)

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
            [InlineKeyboardButton(text="🧰 Фильтры", callback_data=_cb("filter", "open"))],
            [InlineKeyboardButton(text="🔁 Обновить", callback_data=_cb("card", "refresh"))],
        ]
    )


def filter_menu_keyboard(filters: SearchFilters) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"Марка: {filters.make or '-'}",
                    callback_data=_cb("filter", "make_menu"),
                )
            ],
            [
                InlineKeyboardButton(
                    text=f"Модель: {filters.model or '-'}",
                    callback_data=_cb("filter", "model_manual"),
                )
            ],
            [
                InlineKeyboardButton(
                    text=f"Цвет: {filters.color or '-'}",
                    callback_data=_cb("filter", "color_menu"),
                )
            ],
            [InlineKeyboardButton(text="Год", callback_data=_cb("filter", "year_input"))],
            [InlineKeyboardButton(text="Цена", callback_data=_cb("filter", "price_input"))],
            [
                InlineKeyboardButton(text="Сбросить", callback_data=_cb("filter", "reset")),
                InlineKeyboardButton(text="Применить", callback_data=_cb("filter", "apply")),
            ],
        ]
    )


def make_picker_keyboard() -> InlineKeyboardMarkup:
    makes = [
        "Toyota",
        "Nissan",
        "Honda",
        "Mazda",
        "Subaru",
        "BMW",
        "Lexus",
        "Mercedes-Benz",
        "Audi",
    ]
    rows: list[list[InlineKeyboardButton]] = []
    for idx in range(0, len(makes), 3):
        row_values = makes[idx : idx + 3]
        rows.append(
            [InlineKeyboardButton(text=item, callback_data=_cb("filter", "set_make", item)) for item in row_values]
        )
    rows.append([InlineKeyboardButton(text="Ввести вручную", callback_data=_cb("filter", "make_manual"))])
    rows.append([InlineKeyboardButton(text="Назад", callback_data=_cb("filter", "open"))])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def color_picker_keyboard() -> InlineKeyboardMarkup:
    values = [
        ("Black", "black"),
        ("White", "white"),
        ("Red", "red"),
        ("Blue", "blue"),
        ("Gray", "gray"),
        ("Silver", "silver"),
        ("Yellow", "yellow"),
        ("Green", "green"),
        ("Other", "other"),
    ]
    rows: list[list[InlineKeyboardButton]] = []
    for idx in range(0, len(values), 3):
        segment = values[idx : idx + 3]
        rows.append([InlineKeyboardButton(text=text, callback_data=_cb("filter", "set_color", value)) for text, value in segment])
    rows.append([InlineKeyboardButton(text="Сбросить цвет", callback_data=_cb("filter", "clear_color"))])
    rows.append([InlineKeyboardButton(text="Назад", callback_data=_cb("filter", "open"))])
    return InlineKeyboardMarkup(inline_keyboard=rows)
