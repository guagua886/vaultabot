import sqlite3

conn = sqlite3.connect("telegram_bot.db")
cursor = conn.cursor()

# 红包主表
cursor.execute('''
CREATE TABLE IF NOT EXISTS red_packets (
    id TEXT PRIMARY KEY,
    sender_id INTEGER,
    total_points INTEGER,
    count INTEGER,
    created_at TEXT,
    claimed_count INTEGER DEFAULT 0,
    remaining_points INTEGER,
    expired INTEGER DEFAULT 0
)
''')

# 领取记录表
cursor.execute('''
CREATE TABLE IF NOT EXISTS red_packet_claims (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    packet_id TEXT,
    telegram_id INTEGER,
    claimed_points INTEGER
)
''')

conn.commit()
conn.close()
print("✅ 红包相关数据表已创建")
