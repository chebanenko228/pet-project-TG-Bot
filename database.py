import aiosqlite
from config import DB_PATH

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
            last_post_date TEXT,
            max_posts INTEGER DEFAULT 3
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