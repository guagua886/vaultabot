# backfill_monthly_points.py
# 功能：
# 1) 创建 monthly_points 表（若不存在）
# 2) 以“原来口径”把指定月份（默认当前月）的月积分回填到 monthly_points
#
# 原来口径：earned = users.points - snapshot_points（取该用户最近一次 <= 指定月 的快照）
# 备注：若没有快照，snapshot_points 视为 0；若 earned < 0，则写入 0

import argparse
import sqlite3
from datetime import datetime

DB_PATH = "telegram_bot.db"

CREATE_SQL = """
CREATE TABLE IF NOT EXISTS monthly_points (
  telegram_id INTEGER,
  month TEXT,                -- 例如 '2025-08'
  earned INTEGER DEFAULT 0,
  PRIMARY KEY (telegram_id, month)
);
"""

def get_month_str(arg_month: str | None) -> str:
    if arg_month:
        # 简单校验 YYYY-MM
        try:
            datetime.strptime(arg_month, "%Y-%m")
        except ValueError:
            raise SystemExit("❌ --month 参数格式应为 YYYY-MM，例如 2025-08")
        return arg_month
    return datetime.now().strftime("%Y-%m")

def main(month_str: str):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA busy_timeout=5000")
    cur = conn.cursor()

    # 1) 建表
    cur.execute(CREATE_SQL)
    conn.commit()

    # 2) 读取用户当前 points
    cur.execute("SELECT telegram_id, COALESCE(points, 0) FROM users")
    users = cur.fetchall()

    updated = 0
    for telegram_id, points in users:
        # 3) 查该用户最近一次 <= 指定月 的快照 snapshot_points
        cur.execute("""
            SELECT snapshot_points
            FROM monthly_snapshot
            WHERE telegram_id = ?
              AND month = (
                  SELECT MAX(month)
                  FROM monthly_snapshot
                  WHERE telegram_id = ?
                    AND month <= ?
              )
        """, (telegram_id, telegram_id, month_str))
        row = cur.fetchone()
        snapshot_points = row[0] if row and row[0] is not None else 0

        earned = points - snapshot_points
        if earned < 0:
            earned = 0

        # 4) 回填/覆盖当月 earned
        cur.execute("""
            INSERT INTO monthly_points (telegram_id, month, earned)
            VALUES (?, ?, ?)
            ON CONFLICT(telegram_id, month) DO UPDATE SET earned=excluded.earned
        """, (telegram_id, month_str, int(earned)))
        updated += 1

    conn.commit()

    # 打印前 20 名检查
    cur.execute("""
        SELECT u.name, m.telegram_id, m.earned
        FROM monthly_points m
        LEFT JOIN users u ON u.telegram_id = m.telegram_id
        WHERE m.month = ?
        ORDER BY m.earned DESC
        LIMIT 20
    """, (month_str,))
    top20 = cur.fetchall()

    conn.close()

    print(f"✅ 回填完成：月份={month_str}，更新 {updated} 条。前 20 预览：")
    for i, (name, tid, earned) in enumerate(top20, 1):
        print(f"{i}. {name or '未知'}(ID:{tid})  本月积分={earned}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backfill monthly_points using original logic.")
    parser.add_argument("--month", help="指定月份（YYYY-MM），默认当前月", default=None)
    args = parser.parse_args()
    month_str = get_month_str(args.month)
    main(month_str)
