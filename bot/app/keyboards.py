from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


NOOP_CALLBACK = "noop"


def _nav_callback(token: str, index: int) -> str:
    return f"nav:{token}:{index}"


def listing_keyboard(*, token: str, index: int, total: int, listing_url: str) -> InlineKeyboardMarkup:
    prev_index = max(0, index - 1)
    next_index = min(total - 1, index + 1)

    prev_callback = _nav_callback(token, prev_index) if index > 0 else NOOP_CALLBACK
    next_callback = _nav_callback(token, next_index) if index < total - 1 else NOOP_CALLBACK

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="⬅️", callback_data=prev_callback),
                InlineKeyboardButton(text=f"{index + 1}/{total}", callback_data=NOOP_CALLBACK),
                InlineKeyboardButton(text="➡️", callback_data=next_callback),
            ],
            [InlineKeyboardButton(text="Открыть источник", url=listing_url)],
        ]
    )
