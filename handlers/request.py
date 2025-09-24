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
    username = message.from_user.username or f"id{user_id}"
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
            if expires_at:
                expires_dt = datetime.fromisoformat(expires_at)
                if expires_dt > now:
                    days_left = (expires_dt.date() - now.date()).days
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
            "SELECT requested_at, status FROM requests WHERE user_id=? ORDER BY id DESC LIMIT 1",
            (user_id,)
        )
        request_row = await cursor.fetchone()

        if request_row:
            requested_at, status = request_row
            if requested_at:
                last_request = datetime.fromisoformat(requested_at)
                delta = now - last_request
                if delta < timedelta(hours=1):
                    minutes_left = int((timedelta(hours=1) - delta).total_seconds() // 60)
                    await message.answer(
                        f"⏳ Ты можешь отправлять заявку только раз в час. Подожди {minutes_left} мин."
                    )
                    return

        # 🔹 Создаём новую заявку
        await db.execute(
            "INSERT INTO requests (user_id, username, requested_at, status) VALUES (?, ?, ?, ?)",
            (user_id, username, now.isoformat(), "pending")
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
@dp.callback_query()
async def decision(callback: types.CallbackQuery):
    action, user_id_str, username = callback.data.split("_", 2)
    user_id = int(user_id_str)
    if username == "":
        username = f"id{user_id}"

    async with aiosqlite.connect(DB_PATH) as db:
        if action == "approve":
            expires = datetime.now(timezone.utc) + timedelta(days=7)

            # Обновляем заявку
            await db.execute(
                "UPDATE requests SET status=? WHERE user_id=? AND status='pending'",
                ("approved", user_id)
            )

            # Добавляем доступ
            await db.execute(
                "REPLACE INTO access (user_id, username, expires_at, posts_today, last_post_date, max_posts) VALUES (?, ?, ?, ?, ?, ?)",
                (user_id, username, expires.isoformat(), 0, None, 3)
            )
            await db.commit()

            await bot.send_message(
                user_id,
                "✅ Вам выдан доступ писать в группе на 7 дней (3 поста в день)."
            )
            await callback.message.edit_text(f"Одобрено ✅ (ID {user_id}, @{username})")

        elif action == "deny":
            # Обновляем заявку
            await db.execute(
                "UPDATE requests SET status=? WHERE user_id=? AND status='pending'",
                ("denied", user_id)
            )
            await db.commit()

            await bot.send_message(user_id, "❌ Ваша заявка отклонена.")
            await callback.message.edit_text(f"Отклонено ❌ (ID {user_id}, @{username})")

    await callback.answer()