import sqlite3
from datetime import datetime

def create_test_monthly_snapshot(db_path="telegram_bot.db", month="2025-06", snapshot_value=0):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 创建表（如果尚未存在）
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS monthly_snapshot (
        telegram_id INTEGER,
        month TEXT,
        snapshot_points INTEGER,
        PRIMARY KEY (telegram_id, month)
    )
    ''')

    # 获取所有用户 ID
    cursor.execute("SELECT telegram_id FROM users")
    users = cursor.fetchall()

    if not users:
        print("⚠️ 没有用户数据，跳过快照创建。")
        conn.close()
        return

    # 插入或更新快照数据
    for (telegram_id,) in users:
        cursor.execute('''
        INSERT OR REPLACE INTO monthly_snapshot (telegram_id, month, snapshot_points)
        VALUES (?, ?, ?)
        ''', (telegram_id, month, snapshot_value))

    conn.commit()
    conn.close()
    print(f"✅ 已为 {len(users)} 位用户创建 {month} 快照积分为 {snapshot_value}。")

if __name__ == '__main__':
    create_test_monthly_snapshot()
