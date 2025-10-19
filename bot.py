import asyncio
from config import dp, bot
from database import init_db
from services.scheduler import reset_daily, check_expired, cleanup_requests

# Подключаем все handlers
import handlers.start
import handlers.request
import handlers.admin
import handlers.group


# ------------------- ЗАПУСК -------------------
async def main():
    await init_db()
    tacks = [
        asyncio.create_task(reset_daily()),
        asyncio.create_task(check_expired()),
        asyncio.create_task(cleanup_requests()),
    ]
    try:
        await dp.start_polling(bot)
    finally:
        # Останавливаем фоновые задачи
        for task in tacks:
            task.cancel()
        await asyncio.gather(*tacks, return_exceptions=True)
        # Закрываем сессию бота
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
