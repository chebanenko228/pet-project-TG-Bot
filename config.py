from aiogram.client.bot import DefaultBotProperties
from aiogram import Bot, Dispatcher


API_TOKEN = ""
ADMIN_IDS = []  # ID администраторов
GROUP_ID = -100  # ID канала
DB_PATH = ".db" # Название файла базы данных

bot = Bot(
    token=API_TOKEN,
    default=DefaultBotProperties(parse_mode="HTML")
)
dp = Dispatcher()