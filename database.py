import aiosqlite
import asyncio
from datetime import date, datetime
from typing import Optional, List, Dict


DB_PATH = "bot.db"


async def init_db():
    """Инициализация базы данных"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                full_name TEXT,
                is_banned INTEGER DEFAULT 0,
                daily_limit INTEGER DEFAULT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                date TEXT,
                count INTEGER DEFAULT 0,
                UNIQUE(user_id, date)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS gallery (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                file_path TEXT,
                prompt TEXT,
                negative_prompt TEXT,
                model TEXT,
                lora TEXT,
                steps INTEGER,
                cfg REAL,
                sampler TEXT,
                seed INTEGER,
                width INTEGER,
                height INTEGER,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_settings (
                user_id INTEGER PRIMARY KEY,
                steps INTEGER DEFAULT 25,
                cfg_scale REAL DEFAULT 7.0,
                width INTEGER DEFAULT 512,
                height INTEGER DEFAULT 768,
                sampler TEXT DEFAULT 'Euler a',
                scheduler TEXT DEFAULT 'Karras',
                negative_prompt TEXT DEFAULT 'worst quality, low quality, bad anatomy',
                selected_lora TEXT DEFAULT NULL,
                lora_weight REAL DEFAULT 0.8
            )
        """)
        await db.commit()


async def register_user(user_id: int, username: str, full_name: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT OR IGNORE INTO users (user_id, username, full_name)
            VALUES (?, ?, ?)
        """, (user_id, username, full_name))
        await db.execute("""
            INSERT OR IGNORE INTO user_settings (user_id) VALUES (?)
        """, (user_id,))
        await db.commit()


async def get_user_request_count(user_id: int) -> int:
    today = date.today().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
            SELECT count FROM requests WHERE user_id = ? AND date = ?
        """, (user_id, today)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0


async def increment_user_requests(user_id: int):
    today = date.today().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO requests (user_id, date, count) VALUES (?, ?, 1)
            ON CONFLICT(user_id, date) DO UPDATE SET count = count + 1
        """, (user_id, today))
        await db.commit()


async def is_user_banned(user_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
            SELECT is_banned FROM users WHERE user_id = ?
        """, (user_id,)) as cursor:
            row = await cursor.fetchone()
            return bool(row[0]) if row else False


async def ban_user(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET is_banned = 1 WHERE user_id = ?", (user_id,))
        await db.commit()


async def unban_user(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET is_banned = 0 WHERE user_id = ?", (user_id,))
        await db.commit()


async def set_user_limit(user_id: int, limit: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET daily_limit = ? WHERE user_id = ?", (limit, user_id))
        await db.commit()


async def get_user_limit(user_id: int, default_limit: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT daily_limit FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            if row and row[0] is not None:
                return row[0]
            return default_limit


async def get_all_users() -> List[Dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users") as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


async def get_user_settings(user_id: int) -> Dict:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM user_settings WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                return dict(row)
            return {}


async def update_user_setting(user_id: int, key: str, value):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(f"""
            INSERT INTO user_settings (user_id, {key}) VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET {key} = ?
        """, (user_id, value, value))
        await db.commit()


async def save_to_gallery(user_id: int, file_path: str, params: Dict):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO gallery 
            (user_id, file_path, prompt, negative_prompt, model, lora, steps, cfg, sampler, seed, width, height)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            user_id, file_path,
            params.get("prompt", ""),
            params.get("negative_prompt", ""),
            params.get("model", ""),
            params.get("lora", ""),
            params.get("steps", 25),
            params.get("cfg_scale", 7.0),
            params.get("sampler", ""),
            params.get("seed", -1),
            params.get("width", 512),
            params.get("height", 768),
        ))
        await db.commit()


async def get_user_gallery(user_id: int, limit: int = 20) -> List[Dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT * FROM gallery WHERE user_id = ? ORDER BY created_at DESC LIMIT ?
        """, (user_id, limit)) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


async def get_total_stats() -> Dict:
    async with aiosqlite.connect(DB_PATH) as db:
        today = date.today().isoformat()
        async with db.execute("SELECT COUNT(*) FROM users") as c:
            total_users = (await c.fetchone())[0]
        async with db.execute("SELECT SUM(count) FROM requests WHERE date = ?", (today,)) as c:
            today_requests = (await c.fetchone())[0] or 0
        async with db.execute("SELECT COUNT(*) FROM gallery") as c:
            total_images = (await c.fetchone())[0]
        return {
            "total_users": total_users,
            "today_requests": today_requests,
            "total_images": total_images,
        }
