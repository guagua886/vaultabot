import sqlite3
import csv
import os
from datetime import datetime

def read_snapshot(month_str=None):
    db_path = "telegram_bot.db"
    if not os.path.exists(db_path):
        print("❌ 数据库文件不存在。")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 如果未指定月份，则使用当前月
    if not month_str:
        month_str = datetime.now().strftime('%Y-%m')

    # 查询快照 + 用户信息
    cursor.execute('''
        SELECT 
            s.telegram_id,
            u.custom_id,
            u.name,
            s.snapshot_points
        FROM monthly_snapshot s
        LEFT JOIN users u ON s.telegram_id = u.telegram_id
        WHERE s.month = ?
    ''', (month_str,))

    rows = cursor.fetchall()
    conn.close()

    if not rows:
        print(f"⚠️ 没有找到 {month_str} 的快照数据。")
        return

    print(f"📌 [{month_str}] 快照数据，共 {len(rows)} 条：")
    for row in rows:
        tid, custom_id, name, points = row
        print(f"Telegram ID: {tid} | 自定义ID: @{custom_id or '无'} | 姓名: {name or '未知'} | 快照积分: {points}")

    # 保存为 CSV
    csv_file = f"snapshot_{month_str}.csv"
    with open(csv_file, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["Telegram ID", "Custom ID", "Name", "Month", "Snapshot Points"])
        for row in rows:
            writer.writerow([row[0], row[1] or '', row[2] or '', month_str, row[3]])

    print(f"✅ 快照数据已保存为 {csv_file}")

if __name__ == '__main__':
    read_snapshot()  # 默认读取当前月份
