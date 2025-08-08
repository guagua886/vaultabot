import sqlite3
import os

DB_FILE = 'telegram_bot.db'

def initialize_snapshot_zeros():
    if not os.path.exists(DB_FILE):
        print(f"❌ 数据库文件不存在: {DB_FILE}")
        return

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    # 创建快照表（如果尚未存在）
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS monthly_snapshot (
            telegram_id INTEGER PRIMARY KEY,
            snapshot_points INTEGER
        )
    ''')

    # 读取所有 telegram_id
    cursor.execute('SELECT telegram_id FROM users')
    all_ids = cursor.fetchall()

    added = 0
    for row in all_ids:
        telegram_id = row[0]

        # 仅在该用户还没有记录时插入 0
        cursor.execute('SELECT 1 FROM monthly_snapshot WHERE telegram_id = ?', (telegram_id,))
        if not cursor.fetchone():
            cursor.execute('INSERT INTO monthly_snapshot (telegram_id, snapshot_points) VALUES (?, ?)', (telegram_id, 0))
            added += 1

    conn.commit()
    conn.close()

    print(f"✅ 已初始化 {added} 条 snapshot 记录为 0")

if __name__ == '__main__':
    initialize_snapshot_zeros()

