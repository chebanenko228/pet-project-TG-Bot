from aiogram import types
import asyncio
import aiosqlite
from datetime import datetime, timezone
from config import dp, ADMIN_IDS, GROUP_ID, DB_PATH, BOT_START_TIME


ADMIN_CONTACT = "@hrd_timur"  # username администратора


# ------------------- ОТСЛЕЖИВАНИЕ СООБЩЕНИЙ -------------------
@dp.message()
async def group_message(message: types.Message):
    if message.chat.id != GROUP_ID:
        return

    # ⛔ Пропускаем, если сообщение отправлено до запуска бота
    if message.date.replace(tzinfo=timezone.utc) < BOT_START_TIME:
        return

    # ⛔ Пропускаем, если сообщение от имени канала
    if message.sender_chat:
        return

    user_id = message.from_user.id
    if user_id in ADMIN_IDS:
        return  # админа не ограничиваем

    # username или "неизвестный"
    username = f"@{message.from_user.username}" if message.from_user.username else "неизвестный"
    now = datetime.now(timezone.utc)

    async def warn_and_delete(reason: str):
        """Удаляем сообщение и показываем предупреждение на 20 секунд"""
        await message.delete()
        warn_msg = await message.answer(
            f"❌ Публикация от {username} была удалена.\n"
            f"{reason}\n\n"
            f"📢 Разместить вакансию можно на правах рекламы.\n"
            f"Свяжитесь с администратором: {ADMIN_CONTACT}"
        )
        await asyncio.sleep(12)
        try:
            await warn_msg.delete()
        except:
            pass  # если сообщение уже удалено вручную/ботом

    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT expires_at, posts_today, last_post_date, max_posts FROM access WHERE user_id=?",
            (user_id,)
        )
        row = await cursor.fetchone()

        if not row:
            await warn_and_delete("У пользователя нет активной подписки.")
            return

        expires_at, posts_today, last_post_date, max_posts = row

        today = now.date()
        if not last_post_date or datetime.fromisoformat(last_post_date).date() != today:
            posts_today = 0

        if posts_today >= max_posts:
            await warn_and_delete("Превышен дневной лимит публикаций.")
        else:
            await db.execute(
                "UPDATE access SET posts_today=?, last_post_date=?, username=? WHERE user_id=?",
                (posts_today + 1, now.isoformat(), username, user_id)
            )
            await db.commit()
