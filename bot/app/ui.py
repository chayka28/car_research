from __future__ import annotations

import logging
from dataclasses import dataclass

from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardMarkup, InputMediaPhoto, Message

from app.state import UserSession

logger = logging.getLogger(__name__)


@dataclass
class ScreenPayload:
    text: str
    keyboard: InlineKeyboardMarkup | None = None
    photo_url: str | None = None


class ScreenManager:
    async def _safe_delete(self, bot: Bot, chat_id: int, message_id: int) -> bool:
        try:
            await bot.delete_message(chat_id=chat_id, message_id=message_id)
            return True
        except Exception:
            return False

    async def _deactivate(self, bot: Bot, chat_id: int, message_id: int) -> None:
        try:
            await bot.edit_message_reply_markup(chat_id=chat_id, message_id=message_id, reply_markup=None)
        except Exception:
            pass

    async def close(self, bot: Bot, session: UserSession, message: Message | None = None) -> None:
        target_id = message.message_id if message is not None else session.screen_message_id
        if target_id is None:
            return
        await self._safe_delete(bot, session.chat_id, target_id)
        if session.screen_message_id == target_id:
            session.screen_message_id = None
            session.screen_has_photo = False
            session.last_screen_type = None

    async def _send(self, bot: Bot, session: UserSession, payload: ScreenPayload) -> int:
        if payload.photo_url:
            message = await bot.send_photo(
                chat_id=session.chat_id,
                photo=payload.photo_url,
                caption=payload.text,
                parse_mode=ParseMode.HTML,
                reply_markup=payload.keyboard,
            )
            return message.message_id
        message = await bot.send_message(
            chat_id=session.chat_id,
            text=payload.text,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
            reply_markup=payload.keyboard,
        )
        return message.message_id

    async def _edit(
        self,
        bot: Bot,
        *,
        chat_id: int,
        message_id: int,
        had_photo: bool,
        payload: ScreenPayload,
    ) -> bool:
        if had_photo != bool(payload.photo_url):
            return False
        try:
            if payload.photo_url:
                media = InputMediaPhoto(media=payload.photo_url, caption=payload.text, parse_mode=ParseMode.HTML)
                await bot.edit_message_media(
                    chat_id=chat_id,
                    message_id=message_id,
                    media=media,
                    reply_markup=payload.keyboard,
                )
            else:
                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=payload.text,
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=True,
                    reply_markup=payload.keyboard,
                )
            return True
        except Exception:
            logger.debug("Failed to edit screen message %s", message_id, exc_info=True)
            return False

    async def _edit_caption_fallback(
        self,
        bot: Bot,
        *,
        chat_id: int,
        message_id: int,
        payload: ScreenPayload,
    ) -> bool:
        try:
            await bot.edit_message_caption(
                chat_id=chat_id,
                message_id=message_id,
                caption=payload.text,
                parse_mode=ParseMode.HTML,
                reply_markup=payload.keyboard,
            )
            return True
        except Exception:
            logger.debug("Failed to edit caption fallback for %s", message_id, exc_info=True)
            return False

    async def render(
        self,
        bot: Bot,
        session: UserSession,
        payload: ScreenPayload,
        *,
        screen_type: str,
        source_message: Message | None = None,
    ) -> None:
        target_id = session.screen_message_id
        had_photo = session.screen_has_photo

        if source_message is not None:
            target_id = source_message.message_id
            had_photo = bool(source_message.photo)

        if target_id is not None:
            edited = await self._edit(
                bot,
                chat_id=session.chat_id,
                message_id=target_id,
                had_photo=had_photo,
                payload=payload,
            )
            if edited:
                session.screen_message_id = target_id
                session.screen_has_photo = bool(payload.photo_url)
                session.last_screen_type = screen_type
                return

            deleted = await self._safe_delete(bot, session.chat_id, target_id)
            if deleted:
                if session.screen_message_id == target_id:
                    session.screen_message_id = None
                    session.screen_has_photo = False
            else:
                # Keep one-screen UX: if media/text mismatch cannot be deleted, rewrite caption in place.
                if had_photo and not payload.photo_url:
                    edited_caption = await self._edit_caption_fallback(
                        bot,
                        chat_id=session.chat_id,
                        message_id=target_id,
                        payload=payload,
                    )
                    if edited_caption:
                        session.screen_message_id = target_id
                        session.screen_has_photo = True
                        session.last_screen_type = screen_type
                        return

                if session.screen_message_id != target_id:
                    await self._deactivate(bot, session.chat_id, target_id)
                else:
                    await self._deactivate(bot, session.chat_id, target_id)
                    session.screen_message_id = None
                    session.screen_has_photo = False

        session.screen_message_id = await self._send(bot, session, payload)
        session.screen_has_photo = bool(payload.photo_url)
        session.last_screen_type = screen_type
