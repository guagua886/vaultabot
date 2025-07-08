import sqlite3
from datetime import datetime

def snapshot_monthly_points():
    db = 'telegram_bot.db'
    conn = sqlite3.connect(db)
    cursor = conn.cursor()

    month_str = datetime.now().strftime('%Y-%m')

    # 读取所有用户当前积分
    cursor.execute('SELECT telegram_id, points FROM users')
    users = cursor.fetchall()

    for telegram_id, points in users:
        cursor.execute('''
            INSERT OR REPLACE INTO monthly_snapshot (telegram_id, month, snapshot_points)
            VALUES (?, ?, ?)
        ''', (telegram_id, month_str, points))

    conn.commit()
    conn.close()
    print(f"[{month_str}] 所有用户积分快照已保存。")

if __name__ == '__main__':
    snapshot_monthly_points()

