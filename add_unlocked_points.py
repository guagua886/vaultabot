import sqlite3

DB_FILE = 'telegram_bot.db'

def add_unlocked_points_column():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    # 检查字段是否已存在
    cursor.execute("PRAGMA table_info(users)")
    columns = [col[1] for col in cursor.fetchall()]
    if 'unlocked_points' not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN unlocked_points INTEGER DEFAULT 0")
        conn.commit()
        print("字段 unlocked_points 已成功添加。")
    else:
        print("字段 unlocked_points 已存在。无需添加。")

    conn.close()

if __name__ == '__main__':
    add_unlocked_points_column()

