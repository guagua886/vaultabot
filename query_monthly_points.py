import sqlite3
import argparse

DB_PATH = "telegram_bot.db"

def query_user_and_monthly_points(telegram_id: int):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 查询用户完整信息
    cursor.execute("PRAGMA table_info(users)")
    user_columns = [col[1] for col in cursor.fetchall()]
    
    cursor.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
    user_row = cursor.fetchone()

    print(f"📄 查询用户: Telegram ID = {telegram_id}\n")

    if not user_row:
        print("❌ 未找到该用户。\n")
        conn.close()
        return

    print("👤 用户信息:")
    for key, val in zip(user_columns, user_row):
        print(f" - {key}: {val}")

    print("\n📊 月度积分记录:")
    cursor.execute("""
        SELECT month, earned FROM monthly_points
        WHERE telegram_id = ?
        ORDER BY month DESC
    """, (telegram_id,))
    rows = cursor.fetchall()

    if not rows:
        print("暂无记录。")
    else:
        for month, earned in rows:
            print(f" - {month}: {earned} 分")

    conn.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="查询用户的完整信息和月积分记录")
    parser.add_argument("telegram_id", type=int, help="要查询的 Telegram ID")
    args = parser.parse_args()

    query_user_and_monthly_points(args.telegram_id)
