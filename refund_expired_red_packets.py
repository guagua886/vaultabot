import sqlite3
from datetime import datetime, timedelta

def refund_expired_red_packets():
    conn = sqlite3.connect("telegram_bot.db")
    cursor = conn.cursor()

    cursor.execute('''
        SELECT id, sender_id, remaining_points, created_at
        FROM red_packets
        WHERE expired = 0 AND remaining_points > 0
    ''')
    packets = cursor.fetchall()

    refunded = 0
    for pid, sender_id, remaining, created_at_str in packets:
        created_at = datetime.strptime(created_at_str, "%Y-%m-%d %H:%M:%S")
        if datetime.now() - created_at > timedelta(hours=24):
            # 退回解锁积分
            cursor.execute("UPDATE users SET unlocked_points = unlocked_points + ? WHERE telegram_id = ?", (remaining, sender_id))
            cursor.execute("UPDATE red_packets SET expired = 1 WHERE id = ?", (pid,))
            refunded += 1

    conn.commit()
    conn.close()
    print(f"✅ 已退回 {refunded} 个过期红包的剩余积分。")

if __name__ == '__main__':
    refund_expired_red_packets()
