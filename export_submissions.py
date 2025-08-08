# export_submissions_csv.py
import sqlite3
import csv
from datetime import datetime

def export_to_csv():
    db_file = 'telegram_bot.db'
    output_file = f'submissions_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'

    try:
        conn = sqlite3.connect(db_file)
        cursor = conn.cursor()
        cursor.execute("SELECT telegram_id, type, link FROM submissions")
        rows = cursor.fetchall()
        conn.close()

        if not rows:
            print("❗ 没有找到任何提交记录。")
            return

        with open(output_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(["Telegram ID", "类型", "链接"])  # 表头
            for row in rows:
                writer.writerow(row)

        print(f"✅ 导出成功，共 {len(rows)} 条记录，保存为：{output_file}")

    except Exception as e:
        print("❌ 导出失败：", e)

if __name__ == "__main__":
    export_to_csv()

