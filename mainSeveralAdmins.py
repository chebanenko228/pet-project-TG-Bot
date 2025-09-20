import asyncio
import aiosqlite
from datetime import datetime, timedelta, timezone
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command, CommandStart
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.client.bot import DefaultBotProperties

API_TOKEN = ""
ADMIN_IDS = []  # ID администраторов
GROUP_ID = -100  # ID канала

bot = Bot(
    token=API_TOKEN,
    default=DefaultBotProperties(parse_mode="HTML")
)
dp = Dispatcher()

DB_PATH = "group_access_EG.db"


# ------------------- ИНИЦИАЛИЗАЦИЯ БД -------------------
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        # Таблица активных доступов
        await db.execute("""
        CREATE TABLE IF NOT EXISTS access (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            expires_at TEXT,
            posts_today INTEGER DEFAULT 0,
            last_post_date TEXT
        )
        """)

        # Таблица заявок
        await db.execute("""
        CREATE TABLE IF NOT EXISTS requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            requested_at TEXT,
            status TEXT,              -- pending / approved / denied
            FOREIGN KEY (user_id) REFERENCES access(user_id)
        )
        """)

        await db.commit()


# ------------------- КОМАНДА /start -------------------
@dp.message(CommandStart())
async def start_command(message: types.Message):
    # ⛔ Пропускаем, если сообщение от имени канала
    if message.sender_chat:
        return

    user_id = message.from_user.id
    username = message.from_user.username or f"id{user_id}"

    text = (
        f"Привет, @{username}! 👋\n\n"
        "Я бот для контроля доступа в группу.\n"
        "Чтобы получить доступ к отправке сообщений в группе, "
        "введи команду /request.\n\n"
        "После отправки заявки администратор рассмотрит её и либо "
        "одобрит, либо отклонит. Когда доступ будет предоставлен, "
        "ты сможешь писать до 3 сообщений в день.\n\n"
        "Если у тебя уже есть доступ, бот покажет твой текущий статус."
    )

    await message.answer(text)


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
            "SELECT expires_at, posts_today, last_post_date FROM access WHERE user_id=?",
            (user_id,)
        )
        access_row = await cursor.fetchone()

        if access_row:
            expires_at, posts_today, last_post_date = access_row
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
                        f"Сегодня {used_posts}/3 постов."
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
                "REPLACE INTO access (user_id, username, expires_at, posts_today, last_post_date) VALUES (?, ?, ?, ?, ?)",
                (user_id, username, expires.isoformat(), 0, None)
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


# ------------------- СБРОС ЛИМИТОВ -------------------
async def reset_daily():
    while True:
        now = datetime.now()
        tomorrow = datetime.combine(now.date() + timedelta(days=1), datetime.min.time())
        seconds_until_midnight = (tomorrow - now).total_seconds()
        await asyncio.sleep(seconds_until_midnight)
        try:
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute("UPDATE access SET posts_today=0")
                await db.commit()
            print("✅ Сброс дневных лимитов выполнен")
        except Exception as e:
            print(f"Ошибка при сбросе лимитов: {e}")


# ------------------- ПРОВЕРКА ИСТЕКШИХ ДОСТУПОВ -------------------
async def check_expired():
    while True:
        now = datetime.now(timezone.utc)
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute("SELECT user_id, username, expires_at FROM access WHERE expires_at IS NOT NULL")
            rows = await cursor.fetchall()
            for user_id, username, expires in rows:
                if expires and now > datetime.fromisoformat(expires):
                    await db.execute("DELETE FROM access WHERE user_id=?", (user_id,))
                    await db.commit()
                    await bot.send_message(user_id, "⛔ Срок вашего доступа истёк.")
                    for admin_id in ADMIN_IDS:
                        await bot.send_message(admin_id, f"⛔️ Доступ пользователя @{username or user_id} закончился и был снят.")
        await asyncio.sleep(60)


# ------------------- ЗАПУСК -------------------
async def main():
    await init_db()
    asyncio.create_task(reset_daily())
    asyncio.create_task(check_expired())
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
