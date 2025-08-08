import sqlite3

# 数据库文件路径
DB_FILE = 'telegram_bot.db'

def read_all_users():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT telegram_id, name, custom_id, last_signin, points, binance_uid, twitter_handle, a_account, invited_by, joined_group,unlocked_points 
        FROM users
        ORDER BY points DESC
    ''')
    rows = cursor.fetchall()
    conn.close()

    print("所有用户详细信息：\n")
    for idx, row in enumerate(rows, 1):
        print(f"用户 {idx}:")
        print(f"Telegram ID:    {row[0]}")
        print(f"昵称（name）:   {row[1] or '无'}")
        print(f"自定义ID:       {row[2] or '未设置'}")
        print(f"最后签到时间:   {row[3] or '无'}")
        print(f"积分:           {row[4]}")
        print(f"币安 UID:       {row[5] or '未绑定'}")
        print(f"X 账号:         {row[6] or '未绑定'}")
        print(f"A 账号:         {row[7] or '未绑定'}")
        print(f"邀请人 ID:      {row[8] or '无'}")
        print(f"是否进群:       {'是' if row[9] == 1 else '否'}")
        print(f"解锁积分:       {row[10]}")
        print("-" * 40)

if __name__ == "__main__":
    read_all_users()

