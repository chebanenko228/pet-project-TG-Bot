from aiogram import types
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
import aiosqlite
from datetime import datetime, timedelta, timezone
from config import dp, bot, ADMIN_IDS, DB_PATH


# ------------------- ЗАПРОС ДОСТУПА -------------------
@dp.message(Command("request"))
async def request_access(message: types.Message):
    # ⛔ Пропускаем, если сообщение от имени канала
    if message.sender_chat:
        return

    """
    Обработка команды /request:
    - Админ всегда имеет доступ.
    - Если у пользователя активный доступ → показываем статус.
    - Если заявка уже отправлена < часа назад → стопаем.
    - Если нет заявки → создаём новую и уведомляем админа.
    """
    user_id = message.from_user.id
    username = message.from_user.username or "неизвестный"
    now = datetime.now(timezone.utc)

    if user_id in ADMIN_IDS:
        # доступ без ограничений
        await message.answer("✅ Ты админ, у тебя всегда есть доступ без ограничений.")
        return

    async with aiosqlite.connect(DB_PATH) as db:
        # 🔹 Проверяем активный доступ
        cursor = await db.execute(
            "SELECT expires_at, posts_today, last_post_date, max_posts FROM access WHERE user_id=?",
            (user_id,)
        )
        access_row = await cursor.fetchone()

        if access_row:
            expires_at, posts_today, last_post_date, max_posts = access_row
            if expires_at and datetime.fromisoformat(expires_at) > now:
                days_left = (datetime.fromisoformat(expires_at).date() - now.date()).days
                used_posts = 0
                if last_post_date and datetime.fromisoformat(last_post_date).date() == now.date():
                    used_posts = posts_today
                await message.answer(
                    f"⚠️ У тебя уже есть доступ.\n"
                    f"Осталось {days_left} дн.\n"
                    f"Сегодня {used_posts}/{max_posts} постов."
                )
                return

        # 🔹 Проверяем последнюю заявку пользователя
        cursor = await db.execute(
            "SELECT requested_at FROM requests WHERE user_id=?",
            (user_id,)
        )
        row = await cursor.fetchone()

        if row:
            last_request = datetime.fromisoformat(row[0])
            if (now - last_request) < timedelta(hours=1):
                minutes_left = int((timedelta(hours=1) - (now - last_request)).total_seconds() // 60)
                await message.answer(
                    f"⏳ Ты можешь отправлять заявку только раз в час. Подожди {minutes_left} мин."
                )
                return
        else:
            # вставляем новую заявку, если её нет
            await db.execute(
                "INSERT INTO requests (user_id, username, requested_at) VALUES (?, ?, ?)",
                (user_id, username, now.isoformat())
            )
            await db.commit()

    # 🔹 Уведомление администратору
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Одобрить", callback_data=f"approve_{user_id}_{username}")
    kb.button(text="❌ Отказать", callback_data=f"deny_{user_id}_{username}")

    for admin_id in ADMIN_IDS:
        await bot.send_message(
            admin_id,
            f"🔔 Новый запрос от @{username} (ID {user_id})",
            reply_markup=kb.as_markup()
        )

    await message.answer("📩 Заявка отправлена администратору. Ожидайте решения.")


# ------------------- РЕШЕНИЕ АДМИНА -------------------
@dp.callback_query(lambda c: c.data.startswith("approve_") or c.data.startswith("deny_"))
async def decision(callback: types.CallbackQuery):
    # разбор callback_data
    try:
        action, user_id_str, username = callback.data.split("_", 2)
        user_id = int(user_id_str)
    except ValueError:
        await callback.answer("❌ Некорректные данные.")
        return

    async with aiosqlite.connect(DB_PATH) as db:
        if action == "approve":
            # выдаём доступ на 7 дней, 3 поста в день
            expires = datetime.now(timezone.utc) + timedelta(days=7)

            # обновляем таблицу access
            await db.execute(
                """
                REPLACE INTO access (user_id, username, expires_at, posts_today, last_post_date, max_posts)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (user_id, username, expires.isoformat(), 0, None, 3)
            )

            # удаляем заявку из requests (она больше не нужна)
            await db.execute("DELETE FROM requests WHERE user_id=?", (user_id,))
            await db.commit()

            await bot.send_message(
                user_id,
                "✅ Вам выдан доступ писать в группе на 7 дней (3 поста в день)."
            )
            await callback.message.edit_text(f"Одобрено ✅ (ID {user_id}, @{username})")

        elif action == "deny":
            # просто удаляем заявку
            await db.execute("DELETE FROM requests WHERE user_id=?", (user_id,))
            await db.commit()

            await bot.send_message(user_id, "❌ Ваша заявка отклонена.")
            await callback.message.edit_text(f"Отклонено ❌ (ID {user_id}, @{username})")

    await callback.answer()
