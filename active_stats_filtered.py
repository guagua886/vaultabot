import sqlite3
import re
from datetime import datetime
from collections import defaultdict
import csv

def parse_filtered_group_activity(log_file='group_messages.log', db_path='telegram_bot.db', target_month=None):
    if target_month is None:
        target_month = datetime.now().strftime('%Y-%m')

    # 读取当前积分 ≥ 10 的用户信息
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT telegram_id, name, custom_id FROM users WHERE points >= 10")
    user_info = {str(row[0]): {'name': row[1] or '', 'custom_id': row[2] or ''} for row in cursor.fetchall()}
    conn.close()

    pattern = re.compile(
        r'\[(\d{4}-\d{2}-\d{2}) \d{2}:\d{2}:\d{2}\] .*?\[用户: (.*?) \((\d+)\)\]'
    )

    activity = defaultdict(int)

    with open(log_file, 'r', encoding='utf-8') as f:
        for line in f:
            match = pattern.search(line)
            if not match:
                continue

            date_str, _, tid = match.groups()
            if not date_str.startswith(target_month):
                continue
            if tid not in user_info:
                continue

            activity[tid] += 1

    # 排序输出
    print(f"📊 {target_month} 积分≥10用户活跃度排行：")
    sorted_activity = sorted(activity.items(), key=lambda x: x[1], reverse=True)

    for idx, (tid, count) in enumerate(sorted_activity, 1):
        info = user_info.get(tid, {})
        print(f"{idx}. {info.get('name', '')} (@{info.get('custom_id', '')}) - {count} 条")

    # 保存 CSV
    output_file = f"active_{target_month}_points10.csv"
    with open(output_file, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        writer.writerow(["序号", "Telegram ID", "姓名", "自定义ID", "当月消息数"])
        for idx, (tid, count) in enumerate(sorted_activity, 1):
            info = user_info.get(tid, {})
            writer.writerow([idx, tid, info.get('name', ''), info.get('custom_id', ''), count])

    print(f"✅ 已保存至 {output_file}")

if __name__ == '__main__':
    parse_filtered_group_activity()
