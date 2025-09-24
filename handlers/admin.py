from aiogram import types
from aiogram.filters import Command
import aiosqlite
from datetime import datetime, timedelta, timezone
from config import dp, bot, ADMIN_IDS, DB_PATH


# ------------------- КОМАНДА /list -------------------
@dp.message(Command("list"))
async def list_access(message: types.Message):
    # Проверка админа
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("⛔️ Команда доступна только администратору.")
        return

    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT user_id, username, expires_at, posts_today, max_posts FROM access"
        )
        rows = await cursor.fetchall()

    if not rows:
        await message.answer("📋 Нет активных пользователей.")
        return

    text = "📋 Активные пользователи:\n"
    for uid, username, expires, posts, max_posts in rows:
        expires_dt = datetime.fromisoformat(expires)
        expires_str = expires_dt.strftime("%d.%m.%Y %H:%M")
        text += f"ID {uid}, @{username or 'без username'} — до {expires_str}, {posts}/{max_posts} постов сегодня\n"

    await message.answer(text)


# ------------------- КОМАНДА /revoke -------------------
@dp.message(Command("revoke"))
async def revoke_access(message: types.Message):
    # Проверка админа
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("⛔️ Команда доступна только администратору.")
        return

    args = message.text.split()
    if len(args) < 2:
        await message.answer("❗️ Использование: /revoke <user_id>")
        return

    try:
        user_id_to_revoke = int(args[1])
    except ValueError:
        await message.answer("❗️ Укажите правильный ID пользователя.")
        return

    async with aiosqlite.connect(DB_PATH) as db:
        # Проверяем, есть ли доступ у пользователя
        cursor = await db.execute("SELECT username FROM access WHERE user_id=?", (user_id_to_revoke,))
        row = await cursor.fetchone()

        if not row:
            await message.answer(f"⚠️ У пользователя с ID {user_id_to_revoke} нет активного доступа.")
            return

        username = row[0] or f"id{user_id_to_revoke}"
        # Удаляем доступ
        await db.execute("DELETE FROM access WHERE user_id=?", (user_id_to_revoke,))
        await db.commit()

    # Уведомляем пользователя и администратора
    await bot.send_message(user_id_to_revoke, "⛔️ Ваш доступ был досрочно удалён администратором.")
    await message.answer(f"✅ Доступ пользователя @{username} (ID {user_id_to_revoke}) был удалён.")


# ------------------- СБРОС У КОНКРЕТНОГО ПОЛЬЗОВАТЕЛЯ -------------------
@dp.message(Command("reset_user"))
async def reset_user(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("❌ У вас нет прав для этой команды.")
        return

    args = message.text.split()
    if len(args) < 2:
        await message.answer("⚠️ Использование: /reset_user <user_id>")
        return

    try:
        user_id = int(args[1])
    except ValueError:
        await message.answer("⚠️ user_id должен быть числом.")
        return

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE access SET posts_today = 0 WHERE user_id = ?", (user_id,))
        await db.commit()

        cursor = await db.execute("SELECT user_id, username FROM access WHERE user_id = ?", (user_id,))
        row = await cursor.fetchone()

    if row:
        await message.answer(f"✅ Счётчик для пользователя {row[1]} (ID: {row[0]}) сброшен.")
    else:
        await message.answer("⚠️ Пользователь с таким ID не найден в базе.")


# ------------------- СБРОС У ВСЕХ -------------------
@dp.message(Command("reset_all"))
async def reset_all(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("❌ У вас нет прав для этой команды.")
        return

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE access SET posts_today = 0")
        await db.commit()

    await message.answer("✅ Счётчики у всех пользователей сброшены.")


# ------------------- Добавление дней к крайней дате -------------------
@dp.message(Command("extend"))
async def extend_access(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("❌ У вас нет прав для этой команды.")
        return

    args = message.text.split()
    if len(args) < 3:
        await message.answer("⚠️ Использование: /extend <user_id> <days>")
        return

    try:
        user_id = int(args[1])
        days = int(args[2])
        if days <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❗️ user_id и days должны быть положительными числами.")
        return

    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT expires_at, username FROM access WHERE user_id=?", (user_id,))
        row = await cursor.fetchone()

        if not row:
            await message.answer(f"⚠️ Пользователь с ID {user_id} не найден в базе.")
            return

        expires_at, username = row
        now = datetime.now(timezone.utc)
        if expires_at:
            expires_dt = datetime.fromisoformat(expires_at)
            if expires_dt < now:
                expires_dt = now
        else:
            expires_dt = now

        new_expires = expires_dt + timedelta(days=days)

        await db.execute("UPDATE access SET expires_at=? WHERE user_id=?", (new_expires.isoformat(), user_id))
        await db.commit()

    await message.answer(f"✅ Доступ пользователя @{username or user_id} продлён до {new_expires.strftime('%d.%m.%Y %H:%M')}")
    await bot.send_message(user_id, f"⏳ Ваш доступ был продлён до {new_expires.strftime('%d.%m.%Y %H:%M')}")


# ------------------- Изменение лимита сообщений в день -------------------
@dp.message(Command("setlimit"))
async def set_limit(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("❌ У вас нет прав для этой команды.")
        return

    args = message.text.split()
    if len(args) < 3:
        await message.answer("⚠️ Использование: /setlimit <user_id> <limit>")
        return

    try:
        user_id = int(args[1])
        new_limit = int(args[2])
        if new_limit <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❗ user_id и limit должны быть положительными числами.")
        return

    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT username FROM access WHERE user_id=?", (user_id,))
        row = await cursor.fetchone()
        if not row:
            await message.answer(f"⚠️ Пользователь {user_id} не найден.")
            return

        await db.execute("UPDATE access SET max_posts=? WHERE user_id=?", (new_limit, user_id))
        await db.commit()

    await message.answer(f"✅ Лимит постов для @{row[0] or user_id} изменён на {new_limit}")
    await bot.send_message(user_id, f"📢 Ваш лимит постов изменён: теперь {new_limit}.")


# ------------------- Информационная команда для админов -------------------
@dp.message(Command("help_admin"))
async def help_admin(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("⛔ Команда доступна только администраторам.")
        return

    help_text = (
        "📌 Доступные админские команды:\n\n"
        "/list — Показать всех активных пользователей и их лимиты\n"
        "/revoke <user_id> — Лишить пользователя доступа\n"
        "/reset_user <user_id> — Сбросить дневной лимит постов конкретного пользователя\n"
        "/reset_all — Сбросить дневной лимит постов у всех пользователей\n"
        "/extend <user_id> <days> — Продлить доступ пользователю на указанное количество дней\n"
        "/setlimit <user_id> <limit> — Изменить максимальный лимит постов пользователя\n"
        "\nИспользуйте команды внимательно!"
    )

    await message.answer(help_text)