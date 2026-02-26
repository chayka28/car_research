from __future__ import annotations

from datetime import datetime
from html import escape

from app.schemas import ListingCard


def _text(value: object | None, fallback: str = "не указано") -> str:
    if value is None:
        return fallback
    text = str(value).strip()
    return escape(text) if text else fallback


def _price(value: int | None) -> str:
    if value is None:
        return "price not specified"
    return f"{value:,}".replace(",", " ") + " ₽"


def _jpy(value: int | None) -> str:
    if value is None:
        return "price not specified"
    return f"{value:,}".replace(",", " ") + " JPY"


def _date(value: datetime | None) -> str:
    if value is None:
        return "не указано"
    return value.strftime("%d.%m.%Y %H:%M")


def build_listing_text(card: ListingCard, index: int, total: int, query: str) -> str:
    return "\n".join(
        [
            f"<b>Вариант {index + 1} из {total}</b>",
            f"<b>Запрос:</b> {_text(query)}",
            "",
            f"<b>Марка:</b> {_text(card.maker)}",
            f"<b>Модель:</b> {_text(card.model)}",
            f"<b>Комплектация:</b> {_text(card.grade)}",
            f"<b>Год:</b> {_text(card.year)}",
            f"<b>Цвет:</b> {_text(card.color)}",
            f"<b>Пробег:</b> {_text(card.mileage_km, '-') } км",
            "",
            f"<b>Цена (RUB):</b> {_price(card.effective_price_rub)}",
            f"<b>Цена авто (JPY):</b> {_jpy(card.price_jpy)}",
            f"<b>Итоговая цена (JPY):</b> {_jpy(card.total_price_jpy)}",
            "",
            f"<b>Регион:</b> {_text(card.prefecture)}",
            f"<b>Трансмиссия:</b> {_text(card.transmission)}",
            f"<b>Привод:</b> {_text(card.drive_type)}",
            f"<b>Объем двигателя:</b> {_text(card.engine_cc)}",
            f"<b>Топливо:</b> {_text(card.fuel)}",
            f"<b>Руль:</b> {_text(card.steering)}",
            f"<b>Кузов:</b> {_text(card.body_type)}",
            "",
            f"<b>Салон:</b> {_text(card.shop_name)}",
            f"<b>Адрес:</b> {_text(card.shop_address)}",
            f"<b>Телефон:</b> {_text(card.shop_phone)}",
            "",
            f"<b>Статус:</b> {'активно' if card.is_active else 'неактивно'}",
            f"<b>Обновлено:</b> {_date(card.last_seen_at)}",
            f"<b>ID:</b> {_text(card.external_id)}",
            f"<b>Источник:</b> <a href=\"{escape(card.url)}\">открыть объявление</a>",
        ]
    )
