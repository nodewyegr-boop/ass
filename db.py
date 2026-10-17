import aiosqlite

DB_PATH = "data.db"

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        # ตารางผู้ใช้และเงิน
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                balance INTEGER DEFAULT 0
            )
        """)
        # ตารางบัญชีที่ให้สิทธิ์ OAuth2
        await db.execute("""
            CREATE TABLE IF NOT EXISTS accounts (
                user_id INTEGER,
                token TEXT PRIMARY KEY,
                refresh_token TEXT,
                nitro_status INTEGER DEFAULT 0,
                boost_status INTEGER DEFAULT 0,
                claimed INTEGER DEFAULT 0
            )
        """)
        # ตารางรหัสบูส
        await db.execute("""
            CREATE TABLE IF NOT EXISTS boost_codes (
                code TEXT PRIMARY KEY,
                user_id INTEGER,
                amount INTEGER,
                used INTEGER DEFAULT 0
            )
        """)
        # ตารางสถิติระบบ
        await db.execute("""
            CREATE TABLE IF NOT EXISTS stats (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                available_accounts INTEGER DEFAULT 0,
                sold_boosts INTEGER DEFAULT 0
            )
        """)
        await db.execute("INSERT OR IGNORE INTO stats (id, available_accounts, sold_boosts) VALUES (1, 0, 0)")
        await db.commit()

async def get_balance(user_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0

async def update_balance(user_id: int, amount: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT INTO users (user_id, balance) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET balance = balance + ?", (user_id, amount, amount))
        await db.commit()

async def get_stats():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT available_accounts, sold_boosts FROM stats WHERE id = 1") as cursor:
            return await cursor.fetchone()

async def update_stats(available: int, sold: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE stats SET available_accounts = available_accounts + ?, sold_boosts = sold_boosts + ? WHERE id = 1", (available, sold))
        await db.commit()