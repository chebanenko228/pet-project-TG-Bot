import asyncio
import aiosqlite
from datetime import datetime, timedelta, timezone
from config import bot, ADMIN_IDS, DB_PATH
from aiogram.exceptions import TelegramBadRequest

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
from aiogram.exceptions import TelegramBadRequest

async def check_expired():
    while True:
        now = datetime.now(timezone.utc)
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                "SELECT user_id, username, expires_at FROM access WHERE expires_at IS NOT NULL"
            )
            rows = await cursor.fetchall()

            for user_id, username, expires in rows:
                if expires and now > datetime.fromisoformat(expires):
                    # пробуем уведомить пользователя
                    try:
                        await bot.send_message(user_id, "⛔ Срок вашего доступа истёк.")
                    except TelegramBadRequest:
                        print(f"[WARN] Не удалось отправить сообщение пользователю {user_id}")

                    # удаляем доступ
                    await db.execute("DELETE FROM access WHERE user_id=?", (user_id,))
                    await db.commit()

                    # уведомляем админов
                    for admin_id in ADMIN_IDS:
                        try:
                            await bot.send_message(
                                admin_id,
                                f"⛔️ Доступ пользователя @{username or user_id} закончился и был снят."
                            )
                        except TelegramBadRequest:
                            print(f"[WARN] Не удалось отправить сообщение админу {admin_id}")

        await asyncio.sleep(60)
