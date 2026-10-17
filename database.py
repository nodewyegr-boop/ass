import sqlite3

DB_NAME = "bot_database.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    # ตารางเก็บข้อมูลผู้ใช้และยอดเงิน
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            balance INTEGER DEFAULT 0
        )
    ''')
    # ตารางเก็บ Token OAuth2 และสถานะ Nitro
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS oauth_accounts (
            account_id TEXT PRIMARY KEY,
            access_token TEXT,
            refresh_token TEXT,
            nitro_status INTEGER DEFAULT 0,
            boost_count INTEGER DEFAULT 0
        )
    ''')
    # ตารางเก็บบัญชีรหัสผ่านซื้อบูสแบบ 222.xxx
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS boost_codes (
            code TEXT PRIMARY KEY,
            account_ids TEXT, -- เก็บไอดีบัญชีที่ผูกกับรหัสนี้ (คั่นด้วยคอมมา)
            used INTEGER DEFAULT 0
        )
    ''')
    conn.commit()
    conn.close()

def get_user_balance(user_id: str) -> int:
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT balance FROM users WHERE user_id = ?", (str(user_id),))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else 0

def update_user_balance(user_id: str, amount: int):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO users (user_id, balance) VALUES (?, 0)", (str(user_id),))
    cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, str(user_id)))
    conn.commit()
    conn.close()
