from aiogram import types
from aiogram.filters import CommandStart
from config import dp


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