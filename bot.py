import asyncio
from config import dp, bot
from database import init_db
from services.scheduler import reset_daily, check_expired

# Подключаем все handlers
import handlers.start
import handlers.request
import handlers.admin
import handlers.group


# ------------------- ЗАПУСК -------------------
async def main():
    await init_db()
    asyncio.create_task(reset_daily())
    asyncio.create_task(check_expired())
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
