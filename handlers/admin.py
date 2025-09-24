from aiogram import types
from aiogram.filters import Command
import aiosqlite
from datetime import datetime
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
            "SELECT user_id, username, expires_at, posts_today FROM access"
        )
        rows = await cursor.fetchall()

    if not rows:
        await message.answer("📋 Нет активных пользователей.")
        return

    text = "📋 Активные пользователи:\n"
    for uid, username, expires, posts in rows:
        expires_dt = datetime.fromisoformat(expires)
        expires_str = expires_dt.strftime("%d.%m.%Y %H:%M")
        text += f"ID {uid}, @{username or 'без username'} — до {expires_str}, {posts}/3 постов сегодня\n"

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