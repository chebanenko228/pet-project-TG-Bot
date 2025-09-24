from aiogram import types
import aiosqlite
from datetime import datetime, timezone
from config import dp, ADMIN_IDS, GROUP_ID, DB_PATH


# ------------------- ОТСЛЕЖИВАНИЕ СООБЩЕНИЙ -------------------
@dp.message()
async def group_message(message: types.Message):
    if message.chat.id != GROUP_ID:
        return

    # ⛔ Пропускаем, если сообщение от имени канала
    if message.sender_chat:
        return

    user_id = message.from_user.id
    if user_id in ADMIN_IDS:
        return  # админа не ограничиваем

    username = message.from_user.username or f"id{user_id}"
    now = datetime.now(timezone.utc)

    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT expires_at, posts_today, last_post_date FROM access WHERE user_id=?",
            (user_id,)
        )
        row = await cursor.fetchone()

        if not row:
            await message.delete()
            return

        expires_at, posts_today, last_post_date = row

        if expires_at and now > datetime.fromisoformat(expires_at):
            await db.execute("DELETE FROM access WHERE user_id=?", (user_id,))
            await db.commit()
            await message.delete()
            return

        today = now.date()
        if not last_post_date or datetime.fromisoformat(last_post_date).date() != today:
            posts_today = 0

        if posts_today >= 3:
            await message.delete()
        else:
            await db.execute(
                "UPDATE access SET posts_today=?, last_post_date=?, username=? WHERE user_id=?",
                (posts_today + 1, now.isoformat(), username, user_id)
            )
            await db.commit()