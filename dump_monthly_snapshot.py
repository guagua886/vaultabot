import sqlite3
import csv
import os

DB_PATH = "telegram_bot.db"

def dump_monthly_snapshot_with_userinfo_sorted():
    """Query monthly_snapshot table with user info, sort by points (DESC) within each month,
    print results, and export to CSV.
    """
    if not os.path.exists(DB_PATH):
        print("❌ Database file does not exist.")
        return
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT 
            s.telegram_id,
            u.name,
            u.custom_id,
            u.binance_uid,
            s.month,
            s.snapshot_points
        FROM monthly_snapshot s
        LEFT JOIN users u ON s.telegram_id = u.telegram_id
        ORDER BY s.month, s.snapshot_points DESC
    """)
    rows = cursor.fetchall()
    conn.close()
    
    if not rows:
        print("⚠️ No data found in table monthly_snapshot.")
        return
    
    print(f"📌 Total {len(rows)} records in monthly_snapshot (sorted by month & points DESC):")
    for tid, name, custom_id, binance_uid, month, points in rows:
        print(
            f"Month: {month} | Points: {points} | Telegram ID: {tid} | "
            f"Name: {name or 'Unknown'} | Custom ID: @{custom_id or 'None'} | Binance UID: {binance_uid or 'None'}"
        )
    
    # Save to CSV
    csv_file = "monthly_snapshot_userinfo_sorted.csv"
    with open(csv_file, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["Month", "Snapshot Points", "Telegram ID", "Name", "Custom ID", "Binance UID"])
        for tid, name, custom_id, binance_uid, month, points in rows:
            writer.writerow([
                month,
                points,
                tid,
                name or '',
                custom_id or '',
                binance_uid or ''
            ])
    
    print(f"✅ Exported to {csv_file}")

if __name__ == "__main__":
    dump_monthly_snapshot_with_userinfo_sorted()
