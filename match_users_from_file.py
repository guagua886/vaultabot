import sqlite3
import csv

INPUT_FILE = "name_or_customid.txt"
OUTPUT_FILE = "matched_users.csv"
DB_FILE = "telegram_bot.db"

def load_keywords(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        # 去掉 @，统一小写
        return [line.strip().lstrip('@').lower() for line in f if line.strip()]

def search_users(keywords):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    results = []
    seen_ids = set()  # 避免重复用户

    for keyword in keywords:
        # 模糊匹配姓名
        cursor.execute('''
            SELECT telegram_id, name, custom_id, points, unlocked_points
            FROM users
            WHERE LOWER(name) LIKE ?
        ''', (f"%{keyword}%",))
        for row in cursor.fetchall():
            if row[0] not in seen_ids:
                results.append(row)
                seen_ids.add(row[0])

        # 精确匹配 custom_id（不区分大小写）
        cursor.execute('''
            SELECT telegram_id, name, custom_id, points, unlocked_points
            FROM users
            WHERE LOWER(custom_id) = ?
        ''', (keyword,))
        for row in cursor.fetchall():
            if row[0] not in seen_ids:
                results.append(row)
                seen_ids.add(row[0])

    conn.close()
    return results

def write_results(results, output_path):
    with open(output_path, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        writer.writerow(["Telegram ID", "Name", "Custom ID", "Points", "Unlocked Points"])
        for tid, name, custom_id, points, unlocked in results:
            name = name or ""
            custom_id = (custom_id or "").lower()  # ✅ 统一小写
            writer.writerow([tid, name, custom_id, points, unlocked])

def main():
    keywords = load_keywords(INPUT_FILE)
    print(f"读取关键词 {len(keywords)} 个")

    results = search_users(keywords)
    print(f"✅ 匹配到用户 {len(results)} 条")

    write_results(results, OUTPUT_FILE)
    print(f" 已写入结果到 {OUTPUT_FILE}")

if __name__ == '__main__':
    main()

