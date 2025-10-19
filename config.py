from aiogram.client.bot import DefaultBotProperties
from aiogram import Bot, Dispatcher
from datetime import datetime, timezone
from environs import Env

BOT_START_TIME = datetime.now(timezone.utc)

env = Env()
env.read_env()  # подгрузит .env

API_TOKEN = env.str("API_TOKEN", "")
ADMIN_IDS = env.list("ADMIN_IDS", subcast=int)
GROUP_ID = env.int("GROUP_ID", 0)
DB_PATH = env.str("DB_PATH", "group_access.db")

bot = Bot(
    token=API_TOKEN,
    default=DefaultBotProperties(parse_mode="HTML")
)
dp = Dispatcher()
