import sqlite3

DB_PATH = 'telegram_bot.db'

def add_last_bonus_date_column():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 检查列是否已经存在
    cursor.execute("PRAGMA table_info(users)")
    columns = [row[1] for row in cursor.fetchall()]
    if 'last_bonus_date' not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN last_bonus_date TEXT")
        print("✅ 字段 last_bonus_date 添加成功。")
    else:
        print("ℹ️ 字段 last_bonus_date 已存在，无需重复添加。")

    conn.commit()
    conn.close()

if __name__ == "__main__":
    add_last_bonus_date_column()

