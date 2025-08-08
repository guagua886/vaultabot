import sqlite3

conn = sqlite3.connect('telegram_bot.db')
cursor = conn.cursor()

# 添加新字段，忽略已存在的错误
try:
    cursor.execute('ALTER TABLE users ADD COLUMN name TEXT')
except:
    pass

try:
    cursor.execute('ALTER TABLE users ADD COLUMN custom_id TEXT')
except:
    pass

conn.commit()
conn.close()

