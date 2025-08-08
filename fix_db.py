import sqlite3

def fix_monthly_snapshot_schema(db_path='telegram_bot.db'):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        cursor.execute("PRAGMA table_info(monthly_snapshot)")
        columns = [row[1] for row in cursor.fetchall()]
        if 'month' not in columns:
            cursor.execute("ALTER TABLE monthly_snapshot ADD COLUMN month TEXT")
            print("✅ 已添加 month 字段。")
        else:
            print("✅ 表结构已包含 month 字段。")
    except Exception as e:
        print("❌ 修改表结构失败：", e)
    finally:
        conn.commit()
        conn.close()

if __name__ == '__main__':
    fix_monthly_snapshot_schema()

