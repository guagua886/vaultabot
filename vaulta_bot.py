import telebot
from telebot import types
from telebot.types import ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime, timedelta
from collections import defaultdict
import sqlite3
import feedparser
import schedule
import time
import threading
import json
import os
import random
import re
from googletrans import Translator
from uuid import uuid4
import csv
from io import StringIO, BytesIO
import requests

current_quiz = {}

translator = Translator()
TEMP_SIGNIN_FILE = 'temp_signin_word.txt'
LOG_FILE = 'admin_actions.log'
MESSAGE_LOG_FILE = 'group_messages.log'

# 读取配置文件
with open('config.json', 'r', encoding='utf-8') as f:
    config = json.load(f)

BOT_TOKEN = config['BOT_TOKEN']
ADMIN_IDS = config['ADMIN_IDS']
ALLOWED_GROUP_ID = config['ALLOWED_GROUP_ID']
MIN_ACTIVE_POINTS = config.get('MIN_ACTIVE_POINTS', 10)
LANG = config.get("LANGUAGE", "zh")

print(f"[CONFIG] BOT_TOKEN: {BOT_TOKEN}")
print(f"[CONFIG]] ADMIN_IDS: {ADMIN_IDS}")
print(f"[CONFIG] ALLOWED_GROUP_ID: {ALLOWED_GROUP_ID}")
print(f"[CONFIG] MIN_ACTIVE_POINTS: {MIN_ACTIVE_POINTS}")
print(f"[CONFIG] LANG: {LANG}")

with open("i18n.json", "r", encoding="utf-8") as f:
    TEXTS = json.load(f)

def get_text(key: str) -> str:
    return TEXTS.get(LANG, {}).get(key, f"[{key}]")

bot = telebot.TeleBot(BOT_TOKEN)

# 有效签到词配置文件路径
SIGNIN_WORDS_FILE = 'signin_words.txt'
current_signin_word = ""

# 初始化数据库字段
conn = sqlite3.connect('telegram_bot.db')
cursor = conn.cursor()
cursor.execute('''
CREATE TABLE IF NOT EXISTS users (
    telegram_id INTEGER PRIMARY KEY,
    last_signin TEXT,
    points INTEGER DEFAULT 0,
    binance_uid TEXT,
    twitter_handle TEXT,
    a_account TEXT,
    invited_by TEXT,
    joined_group INTEGER DEFAULT 0,
    name TEXT,
    custom_id TEXT,
    last_bonus_date TEXT,
    unlocked_points INTEGER DEFAULT 0
)
''')
conn.commit()

cursor.execute('''CREATE TABLE IF NOT EXISTS quiz_answers (
    quiz_id TEXT,
    telegram_id INTEGER,
    PRIMARY KEY (quiz_id, telegram_id)
)''')
conn.commit()

cursor.execute('''
CREATE TABLE IF NOT EXISTS signin_history (
    telegram_id INTEGER,
    date TEXT
)
''')
conn.commit()

cursor.execute('''
CREATE TABLE IF NOT EXISTS submissions (
    telegram_id INTEGER,
    type TEXT, 
    link TEXT,
    PRIMARY KEY (telegram_id, type, link)
)
''')

conn.commit()

cursor.execute('''
        CREATE TABLE IF NOT EXISTS transfers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender_id INTEGER,
            recipient_id INTEGER,
            amount INTEGER,
            timestamp TEXT
        )
    ''')
conn.commit()

cursor.execute('''
CREATE TABLE IF NOT EXISTS red_packets (
    id TEXT PRIMARY KEY,
    sender_id INTEGER,
    total_points INTEGER,
    count INTEGER,
    created_at TEXT,
    remaining_points INTEGER,
    claimed_count INTEGER DEFAULT 0,
    expired INTEGER DEFAULT 0
)

    ''')
conn.commit()

cursor.execute('''
CREATE TABLE IF NOT EXISTS red_packet_claims (
    packet_id TEXT,
    telegram_id INTEGER,
    claimed_points INTEGER,
    PRIMARY KEY (packet_id, telegram_id)
)

    ''')
conn.commit()

cursor.execute('''
CREATE TABLE IF NOT EXISTS monthly_snapshot (
    telegram_id INTEGER,
    month TEXT,
    snapshot_points INTEGER,
    PRIMARY KEY (telegram_id, month)
)

    ''')
conn.commit()

cursor.execute('''
        CREATE TABLE IF NOT EXISTS monthly_points (
            telegram_id INTEGER,
            month TEXT,                 -- 形如 '2025-08'
            earned INTEGER DEFAULT 0,
            PRIMARY KEY (telegram_id, month)
        )
    ''')

conn.commit()

conn.close()

def add_monthly_points(telegram_id: int, delta: int):
    if delta <= 0:
        return  # 不记录负数

    month_str = datetime.now().strftime('%Y-%m')
    conn = sqlite3.connect('telegram_bot.db')
    cur = conn.cursor()

    cur.execute('''
        INSERT INTO monthly_points (telegram_id, month, earned)
        VALUES (?, ?, ?)
        ON CONFLICT(telegram_id, month)
        DO UPDATE SET earned = earned + excluded.earned
    ''', (telegram_id, month_str, delta))

    conn.commit()
    conn.close()

def log_transfer(sender_id, recipient_id, amount):
    conn = sqlite3.connect('telegram_bot.db')
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO transfers (sender_id, recipient_id, amount, timestamp)
        VALUES (?, ?, ?, ?)
    ''', (sender_id, recipient_id, amount, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()


def record_signin_history(telegram_id, date_str):
    conn = sqlite3.connect('telegram_bot.db')
    cursor = conn.cursor()
    cursor.execute("INSERT INTO signin_history (telegram_id, date) VALUES (?, ?)", (telegram_id, date_str))
    conn.commit()
    conn.close()

def count_signins_last_7_days(telegram_id):
    conn = sqlite3.connect('telegram_bot.db')
    cursor = conn.cursor()
    seven_days_ago = (datetime.now() - timedelta(days=6)).strftime('%Y-%m-%d')  # 包含今天，共7天
    cursor.execute('''
        SELECT COUNT(DISTINCT date)
        FROM signin_history
        WHERE telegram_id = ? AND date >= ?
    ''', (telegram_id, seven_days_ago))
    count = cursor.fetchone()[0]
    conn.close()
    return count

#敏感词过滤
def load_sensitive_words(file_path='sensitive_words.txt'):
    if not os.path.exists(file_path):
        return []
    with open(file_path, 'r', encoding='utf-8') as f:
        return [line.strip().lower() for line in f if line.strip()]

# 数据库操作函数
def get_user(telegram_id):
    conn = sqlite3.connect('telegram_bot.db')
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE telegram_id = ?', (telegram_id,))
    user = cursor.fetchone()
    conn.close()
    return user

def update_user(telegram_id, field, value):
    conn = sqlite3.connect('telegram_bot.db')
    cursor = conn.cursor()
    cursor.execute(f'UPDATE users SET {field} = ? WHERE telegram_id = ?', (value, telegram_id))
    conn.commit()
    conn.close()

def update_user_name_and_custom_id(telegram_id, name, custom_id=None):
    conn = sqlite3.connect('telegram_bot.db')
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET name = ?, custom_id = ? WHERE telegram_id = ?', (name, custom_id, telegram_id))
    conn.commit()
    conn.close()

def create_user_if_not_exist(telegram_id, invited_by=None, name=None):
    user = get_user(telegram_id)
    if not user:
        conn = sqlite3.connect('telegram_bot.db')
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO users (telegram_id, points, invited_by, name, custom_id)
            VALUES (?, ?, ?, ?, ?)
        ''', (telegram_id, 0, invited_by, name, None))
        conn.commit()
        conn.close()

@bot.message_handler(content_types=['new_chat_members'])
def welcome_new_members(message):
    if message.chat.id != ALLOWED_GROUP_ID:
        return  # 只在指定群内发送欢迎消息

    for new_member in message.new_chat_members:
        name = new_member.first_name or ""
        if new_member.last_name:
            name += " " + new_member.last_name
            
        try:
            bot.send_message(message.chat.id, get_text("welcome_new_member").format(name=name))
        except Exception as e:
            print(f"❌ ERROR: {e}")


# 发送红包指令
@bot.message_handler(commands=['hongbao','redpack'])
def send_red_packet(message):
    if message.chat.type not in ['group', 'supergroup']:
        return

    try:
        parts = message.text.split()
        if len(parts) != 3:
            bot.reply_to(message, get_text("redpack_usage"))
            return

        total_points = int(parts[1])
        count = int(parts[2])
        if total_points <= 0 or count <= 0:
            bot.reply_to(message, get_text("redpack_positive_required"))
            return

        telegram_id = message.from_user.id
        conn = sqlite3.connect('telegram_bot.db')
        cursor = conn.cursor()

        cursor.execute("SELECT unlocked_points FROM users WHERE telegram_id = ?", (telegram_id,))
        result = cursor.fetchone()
        if not result or result[0] < total_points:
            bot.reply_to(message, get_text("redpack_insufficient_unlocked"))
            conn.close()
            return

        # 扣除解锁积分
        cursor.execute('''
            UPDATE users
            SET unlocked_points = unlocked_points - ?
            WHERE telegram_id = ?
        ''', (total_points, telegram_id))

        packet_id = str(uuid4())
        cursor.execute('''
            INSERT INTO red_packets (id, sender_id, total_points, count, created_at, remaining_points)
            VALUES (?, ?, ?, ?, datetime('now'), ?)
        ''', (packet_id, telegram_id, total_points, count, total_points))

        conn.commit()
        conn.close()

        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton(get_text("redpack_btn_claim"), callback_data=f"claim_{packet_id}"))

        name = message.from_user.first_name or ""
        if message.from_user.last_name:
            name += " " + message.from_user.last_name

        username = message.from_user.username or get_text("unknown_username")

        bot.send_message(
            message.chat.id,
            get_text("redpack_announce").format(
                name=name, username=username, telegram_id=telegram_id, count=count, total_points=total_points
            ),
            reply_markup=markup
        )

    except Exception as e:
        # 日志里用英文/原样也可，这里也给成可读的统一风格
        print(message, f"❌ ERROR: {str(e)}")


# 领取红包
@bot.callback_query_handler(func=lambda call: call.data.startswith("claim_"))
def claim_red_packet(call):
    telegram_id = call.from_user.id
    packet_id = call.data.replace("claim_", "")

    conn = sqlite3.connect("telegram_bot.db")
    cursor = conn.cursor()

    # 判断是否已领取
    cursor.execute("SELECT 1 FROM red_packet_claims WHERE packet_id = ? AND telegram_id = ?", (packet_id, telegram_id))
    if cursor.fetchone():
        bot.answer_callback_query(call.id, get_text("redpack_already_claimed"))
        conn.close()
        return

    # 查看红包信息
    cursor.execute(
        "SELECT created_at, remaining_points, count, claimed_count, sender_id, expired FROM red_packets WHERE id = ?",
        (packet_id,)
    )
    row = cursor.fetchone()
    if not row:
        bot.answer_callback_query(call.id, get_text("redpack_not_exist"))
        conn.close()
        return

    created_at_str, remaining_points, total_count, claimed_count, sender_id, expired = row
    created_at = datetime.strptime(created_at_str, "%Y-%m-%d %H:%M:%S")

    # 过期判断（24h）
    if expired or (datetime.now() - created_at > timedelta(hours=24)):
        bot.answer_callback_query(call.id, get_text("redpack_expired"))
        conn.close()
        return

    if claimed_count >= total_count or remaining_points <= 0:
        bot.answer_callback_query(call.id, get_text("redpack_empty"))
        conn.close()
        return

    remaining_count = total_count - claimed_count

    if remaining_count == 1:
        claim_amount = remaining_points
    else:
        avg = remaining_points / remaining_count
        max_possible = int(avg * 2)
        claim_amount = random.randint(1, min(max_possible, remaining_points - (remaining_count - 1)))

    # 更新红包表
    cursor.execute(
        "UPDATE red_packets SET claimed_count = claimed_count + 1, remaining_points = remaining_points - ? WHERE id = ?",
        (claim_amount, packet_id)
    )
    # 记录领取者
    cursor.execute(
        "INSERT INTO red_packet_claims (packet_id, telegram_id, claimed_points) VALUES (?, ?, ?)",
        (packet_id, telegram_id, claim_amount)
    )
    # 增加解锁积分
    cursor.execute(
        "UPDATE users SET unlocked_points = unlocked_points + ? WHERE telegram_id = ?",
        (claim_amount, telegram_id)
    )

    conn.commit()
    conn.close()

    bot.answer_callback_query(call.id)

    name = call.from_user.first_name or ""
    if call.from_user.last_name:
        name += " " + call.from_user.last_name
    username = call.from_user.username or get_text("unknown_username")

    bot.send_message(
        call.message.chat.id,
        get_text("redpack_claim_broadcast").format(
            name=name, username=username, telegram_id=telegram_id, amount=claim_amount
        )
    )


@bot.message_handler(commands=['search_user'])
def handle_search_user(message):
    if message.chat.type != 'private':
        return
    if message.from_user.id not in ADMIN_IDS:
        bot.reply_to(message, get_text("search_user_no_permission"))
        return

    args = message.text.strip().split(maxsplit=1)
    if len(args) < 2:
        bot.reply_to(message, get_text("search_user_usage"))
        return

    keyword = args[1].strip().lower()

    conn = sqlite3.connect('telegram_bot.db')
    cursor = conn.cursor()

    cursor.execute('''
        SELECT telegram_id, name, custom_id, points, unlocked_points
        FROM users
        WHERE LOWER(name) LIKE ? OR LOWER(custom_id) LIKE ?
        ORDER BY points DESC
        LIMIT 20
    ''', (f'%{keyword}%', f'%{keyword}%'))

    rows = cursor.fetchall()
    conn.close()

    if not rows:
        bot.reply_to(message, get_text("search_user_not_found").format(keyword=keyword))
        return

    header = get_text("search_user_header").format(keyword=keyword)
    lines = [header, ""]
    for tid, name, cid, pts, unlocked in rows:
        display_name = name or get_text("search_user_name_unknown")
        cid_display = f"@{cid}" if cid else get_text("search_user_cid_none")
        lines.append(
            get_text("search_user_line").format(
                name=display_name,
                cid_display=cid_display,
                tid=tid,
                points=pts,
                unlocked=unlocked
            )
        )
        lines.append("")  # 空行

    msg = "\n".join(lines)
    bot.reply_to(message, msg, parse_mode="Markdown")


@bot.message_handler(commands=['help'])
def handle_help(message):
    if message.chat.type != 'private':
        return  # 仅限私聊使用

    is_admin = message.from_user.id in ADMIN_IDS

    help_text = get_text("help_header") + "\n" + get_text("help_user_section")

    if is_admin:
        help_text += "\n" + get_text("help_admin_section")

    help_text += "\n" + get_text("help_feedback_footer")
    bot.reply_to(message, help_text, parse_mode="Markdown")


@bot.message_handler(commands=['export_feedback'])
def export_feedback_csv(message):
    if message.chat.type != 'private':
        return
    if message.from_user.id not in ADMIN_IDS:
        bot.reply_to(message, get_text("admin_no_permission"))
        return

    file_path = "feedback.csv"
    if not os.path.exists(file_path):
        bot.reply_to(message, get_text("feedback_no_records"))
        return

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        # 添加 UTF-8 BOM 头以避免 Excel 乱码
        byte_content = '\ufeff' + content
        byte_io = BytesIO(byte_content.encode("utf-8"))
        byte_io.seek(0)

        file_name = f"feedback_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        bot.send_document(
            message.chat.id,
            byte_io,
            visible_file_name=file_name,
            caption=get_text("feedback_export_success_caption")
        )
        byte_io.close()

    except Exception as e:
        bot.reply_to(message, get_text("feedback_export_failed").format(error=str(e)))


@bot.message_handler(commands=['feedback'])
def handle_feedback(message):
    text = message.text.strip()
    parts = text.split(maxsplit=1)

    if len(parts) < 2:
        bot.reply_to(message, get_text("feedback_usage"))
        return

    content = parts[1].strip()
    if not content:
        bot.reply_to(message, get_text("feedback_empty"))
        return

    telegram_id = message.from_user.id
    name = message.from_user.first_name or ""
    if message.from_user.last_name:
        name += " " + message.from_user.last_name
    name = name.strip()

    custom_id = ""
    user = get_user(telegram_id)
    if user and len(user) >= 10 and user[9]:  # custom_id 字段
        custom_id = user[9]

    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    try:
        with open("feedback.csv", "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            if f.tell() == 0:
                writer.writerow(["Telegram ID", "Custom ID", "Name", "Content", "Time"])
            writer.writerow([telegram_id, custom_id, name, content, timestamp])

        bot.reply_to(message, get_text("feedback_thanks"))
    except Exception as e:
        bot.reply_to(message, get_text("feedback_save_failed").format(error=str(e)))


@bot.message_handler(commands=['add_points'])
def handle_add_points(message):
    if message.from_user.id not in ADMIN_IDS:
        bot.reply_to(message, get_text("admin_no_permission"))
        return

    try:
        args = message.text.strip().split()
        if len(args) != 3:
            bot.reply_to(message, get_text("add_points_usage"), parse_mode="Markdown")
            return

        target_id = int(args[1])
        points_to_add = int(args[2])

        user = get_user(target_id)
        if not user:
            bot.reply_to(message, get_text("add_points_user_not_found").format(target_id=target_id))
            return

        new_points = user[2] + points_to_add
        update_user(target_id, 'points', new_points)
        add_monthly_points(target_id, points_to_add)

        # 管理日志
        with open(LOG_FILE, 'a', encoding='utf-8') as log_file:
            log_file.write(
                get_text("add_points_admin_log").format(
                    time=datetime.now(), admin_id=message.from_user.id,
                    target_id=target_id, points=points_to_add
                ) + "\n"
            )

        # 私聊通知用户
        try:
            bot.send_message(
                target_id,
                get_text("add_points_dm_user_notify").format(points=points_to_add, new_points=new_points)
            )
        except Exception as e:
            bot.reply_to(message, get_text("add_points_added_but_dm_failed").format(error=str(e)))
            return

        bot.reply_to(
            message,
            get_text("add_points_success_reply").format(
                target_id=target_id, points=points_to_add, new_points=new_points
            )
        )

    except Exception as e:
        bot.reply_to(
            message,
            get_text("add_points_format_error").format(error=str(e)),
            parse_mode="Markdown"
        )


@bot.message_handler(content_types=['document'])
def handle_uploaded_csv(message):
    if message.chat.type != 'private':
        return

    if message.from_user.id not in ADMIN_IDS:
        bot.reply_to(message, get_text("upload_no_permission"))
        return

    if message.document.file_name != 'batch_points.csv':
        # 不用 parse_mode，这样反引号会原样显示
        bot.reply_to(message, get_text("upload_wrong_filename"))
        return

    try:
        # 下载文件
        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)

        # 保存本地文件
        with open('batch_points.csv', 'wb') as f:
            f.write(downloaded_file)

        # 执行批量加分
        success = 0
        failed = 0
        log_lines = []

        decoded = downloaded_file.decode('utf-8')
        reader = csv.reader(StringIO(decoded))
        for row in reader:
            try:
                telegram_id = int(row[0])
                points = int(row[1])
                user = get_user(telegram_id)
                if user:
                    new_points = user[2] + points
                    update_user(telegram_id, 'points', new_points)
                    add_monthly_points(telegram_id, points)

                    bot.send_message(
                        telegram_id,
                        get_text("batch_points_awarded_dm").format(points=points, new_points=new_points)
                    )
                    time.sleep(2)
                    log_lines.append(
                        get_text("batch_admin_log").format(
                            time=datetime.now(),
                            admin_id=message.from_user.id,
                            user_id=telegram_id,
                            points=points
                        )
                    )
                    success += 1
                else:
                    log_lines.append(
                        get_text("batch_user_not_exist_log").format(
                            time=datetime.now(),
                            user_id=telegram_id
                        )
                    )
                    failed += 1
            except Exception as e:
                failed += 1
                log_lines.append(
                    get_text("batch_row_error_log").format(
                        time=datetime.now(),
                        row=row,
                        error=str(e)
                    )
                )

        with open('add_points_log.txt', 'a', encoding='utf-8') as log_file:
            log_file.write("\n".join(log_lines) + "\n")

        bot.reply_to(
            message,
            get_text("batch_process_result").format(success=success, failed=failed)
        )

    except Exception as e:
        bot.reply_to(message, get_text("batch_process_failed").format(error=str(e)))


@bot.message_handler(commands=['price'])
def handle_price(message):
    try:
        parts = message.text.strip().split()
        if len(parts) != 2:
            bot.reply_to(message, get_text("price_usage_error"))
            return

        symbol = parts[1].upper()
        url = f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}USDT"

        resp = requests.get(url, timeout=5)
        data = resp.json() if resp.ok else {}

        if 'price' in data:
            price = float(data['price'])
            bot.reply_to(
                message,
                get_text("price_current").format(symbol=symbol, price=price),
                parse_mode='Markdown'
            )
        else:
            bot.reply_to(
                message,
                get_text("price_invalid_symbol").format(symbol=symbol),
                parse_mode='Markdown'
            )

    except Exception as e:
        bot.reply_to(message, get_text("price_failed").format(error=str(e)))


@bot.message_handler(commands=['export_submissions'])
def export_submissions_csv(message):
    if message.chat.type != 'private':
        return
    if message.from_user.id not in ADMIN_IDS:
        bot.reply_to(message, get_text("error_no_permission"))
        return

    try:
        conn = sqlite3.connect('telegram_bot.db')
        cursor = conn.cursor()
        cursor.execute("SELECT telegram_id, type, link FROM submissions")
        rows = cursor.fetchall()
        conn.close()

        if not rows:
            bot.reply_to(message, get_text("submission_no_records"))
            return

        # 写入 CSV
        string_io = StringIO()
        writer = csv.writer(string_io)
        writer.writerow([
            get_text("csv_col_telegram_id"),
            get_text("csv_col_type"),
            get_text("csv_col_link")
        ])
        for row in rows:
            writer.writerow(row)

        byte_io = BytesIO(string_io.getvalue().encode('utf-8'))
        byte_io.seek(0)

        file_name = f"submissions_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        bot.send_document(
            message.chat.id,
            byte_io,
            visible_file_name=file_name,
            caption=get_text("export_submissions_success")
        )
        byte_io.close()

    except Exception as e:
        bot.reply_to(message, get_text("export_submissions_fail").format(error=str(e)))

@bot.message_handler(commands=['export_users'])
def export_users_csv(message):
    if message.chat.type != 'private':
        return
    if message.from_user.id not in ADMIN_IDS:
        bot.reply_to(message, get_text("error_no_permission"))
        return

    try:
        conn = sqlite3.connect('telegram_bot.db')
        cursor = conn.cursor()
        cursor.execute('''
            SELECT 
                telegram_id, last_signin, points, binance_uid, twitter_handle, 
                a_account, invited_by, joined_group, name, custom_id, last_bonus_date, unlocked_points
            FROM users
        ''')
        rows = cursor.fetchall()
        conn.close()

        if not rows:
            bot.reply_to(message, get_text("error_no_user_data"))
            return

        # 写入 CSV
        string_io = StringIO()
        writer = csv.writer(string_io)
        writer.writerow([
            "Telegram ID", "Last Sign-in", "Points", "Binance UID", "X Handle", 
            "A Account", "Invited By", "Joined Group", "Name", "Custom ID", "Last Bonus Date", "Unlocked Points"
        ])
        for row in rows:
            writer.writerow(row)

        byte_io = BytesIO(string_io.getvalue().encode("utf-8"))
        byte_io.seek(0)
        filename = f"users_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        bot.send_document(message.chat.id, byte_io, visible_file_name=filename, caption=get_text("export_users_success"))
        byte_io.close()

    except Exception as e:
        bot.reply_to(message, get_text("export_users_fail").format(error=str(e)))


@bot.message_handler(commands=['quiz_send'])
def send_quiz(message):
    if message.from_user.id not in ADMIN_IDS:
        bot.reply_to(message, get_text("quiz_send_no_perm"))
        return

    try:
        if message.text.strip() == "/quiz_send":
            # 从题库文件中读取
            with open('quiz_bank.json', 'r', encoding='utf-8') as f:
                quiz_list = json.load(f)
            if not quiz_list:
                bot.reply_to(message, get_text("quiz_bank_empty"))
                return
            quiz_data = random.choice(quiz_list)

            # 打印选中的题目（调试）
            print(get_text("quiz_debug_selected") + json.dumps(quiz_data, ensure_ascii=False))
        else:
            payload = message.text.replace('/quiz_send', '', 1).strip()
            quiz_data = json.loads(payload)

        question = quiz_data['question']
        options = quiz_data['options']
        correct_index = quiz_data['answer']

        quiz_id = str(uuid4())
        current_quiz.clear()
        current_quiz.update({
            "id": quiz_id,
            "question": question,
            "options": options,
            "answer": correct_index,
            "answered": set()
        })

        markup = types.InlineKeyboardMarkup()
        for idx, option in enumerate(options):
            markup.add(types.InlineKeyboardButton(option, callback_data=f"quiz_{quiz_id}_{idx}"))

        sent_msg = bot.send_message(
            ALLOWED_GROUP_ID,
            get_text("quiz_send_announce").format(question=question),
            reply_markup=markup
        )

        threading.Timer(1800, lambda: disable_quiz(quiz_id)).start()

    except Exception as e:
        bot.reply_to(
            message,
            get_text("quiz_send_format_error").format(error=str(e))
        )


def disable_quiz(qid):
    if current_quiz.get("id") == qid:
        current_quiz.clear()
        print(get_text("quiz_end_log"))
        bot.send_message(ALLOWED_GROUP_ID, get_text("quiz_end_message"))


@bot.message_handler(commands=['submit'])
def handle_submit(message):
    if message.chat.type != 'private':
        return

    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton(get_text("submit_btn_binance"), callback_data="submit_binance"),
        types.InlineKeyboardButton(get_text("submit_btn_twitter"), callback_data="submit_twitter")
    )
    bot.send_message(message.chat.id, get_text("submit_choose_type"), reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("submit_"))
def handle_submit_callback(call):
    type_map = {
        "submit_binance": "binance",
        "submit_twitter": "twitter"
    }
    submit_type = type_map[call.data]
    platform_label = get_text("platform_binance") if submit_type == "binance" else get_text("platform_twitter")
    bot.send_message(call.message.chat.id, get_text("submit_prompt_link").format(platform=platform_label))
    
    # 设置下一条消息为链接输入
    bot.register_next_step_handler(call.message, process_submission, submit_type, call.from_user.id)
    bot.answer_callback_query(call.id)

def process_submission(message, submit_type, telegram_id):
    link = (message.text or "").strip()
    if not link.startswith("http"):
        bot.reply_to(message, get_text("submit_invalid_link"))
        return

    conn = sqlite3.connect('telegram_bot.db')
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM submissions WHERE telegram_id = ? AND type = ? AND link = ?", (telegram_id, submit_type, link))
    exists = cursor.fetchone()
    if exists:
        bot.reply_to(message, get_text("submit_already_exists"))
    else:
        cursor.execute("INSERT INTO submissions (telegram_id, type, link) VALUES (?, ?, ?)", (telegram_id, submit_type, link))
        conn.commit()
        platform_label = get_text("platform_binance") if submit_type == "binance" else get_text("platform_twitter")
        bot.reply_to(message, get_text("submit_success").format(platform=platform_label))

    conn.close()



@bot.message_handler(commands=['add_sensitive'])
def handle_add_sensitive(message):
    if message.from_user.id not in ADMIN_IDS:
        bot.reply_to(message, get_text("add_sensitive_no_perm"))
        return

    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        bot.reply_to(message, get_text("add_sensitive_usage"))
        return

    new_word = args[1].strip().lower()
    if not new_word:
        bot.reply_to(message, get_text("add_sensitive_empty"))
        return

    try:
        with open('sensitive_words.txt', 'a+', encoding='utf-8') as f:
            f.seek(0)
            existing_words = [line.strip().lower() for line in f.readlines()]
            if new_word in existing_words:
                bot.reply_to(message, get_text("add_sensitive_exists").format(word=new_word))
                return
            f.write(new_word + '\n')
        bot.reply_to(message, get_text("add_sensitive_added").format(word=new_word))
    except Exception as e:
        bot.reply_to(message, get_text("add_sensitive_failed").format(error=str(e)))

        
@bot.callback_query_handler(func=lambda call: call.data.startswith("quiz_"))
def handle_quiz_answer(call):
    parts = call.data.split("_")
    quiz_id, choice = parts[1], int(parts[2])
    telegram_id = call.from_user.id

    # 显示名
    name = call.from_user.first_name or ""
    if getattr(call.from_user, "last_name", None):
        name += " " + call.from_user.last_name

    # 无进行中题目或不匹配
    if current_quiz.get("id") != quiz_id:
        bot.answer_callback_query(call.id, get_text("quiz_ended_or_invalid"))
        return

    # 检查数据库是否答过
    conn = sqlite3.connect('telegram_bot.db')
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM quiz_answers WHERE quiz_id = ? AND telegram_id = ?", (quiz_id, telegram_id))
    if cursor.fetchone():
        conn.close()
        bot.send_message(call.message.chat.id, get_text("quiz_already_answered_public").format(name=name))
        return

    # 插入答题记录
    cursor.execute("INSERT INTO quiz_answers (quiz_id, telegram_id) VALUES (?, ?)", (quiz_id, telegram_id))
    conn.commit()

    # 判断正误
    if choice == current_quiz.get("answer"):
        user = get_user(telegram_id)
        update_user(telegram_id, 'points', user[2] + 1)
        add_monthly_points(telegram_id, 1)
        bot.send_message(call.message.chat.id, get_text("quiz_correct_public").format(name=name))
    else:
        bot.send_message(call.message.chat.id, get_text("quiz_wrong_public").format(name=name))

    conn.close()

@bot.message_handler(commands=['active'])
def handle_active_ranking(message):
    if message.chat.type == 'private':
        # 私聊使用时，要求已加入群
        user = get_user(message.from_user.id)
        if not user or user[7] != 1:
            bot.reply_to(message, get_text("active_need_join_group"))
            return
    else:
        # 群聊中，只允许指定群
        if message.chat.id != ALLOWED_GROUP_ID:
            return

    target_month = datetime.now().strftime('%Y-%m')

    # 获取当前积分 ≥ 配置值 的用户
    conn = sqlite3.connect('telegram_bot.db')
    cursor = conn.cursor()
    cursor.execute("SELECT telegram_id, name, custom_id FROM users WHERE points >= ?", (MIN_ACTIVE_POINTS,))
    user_info = {}
    for row in cursor.fetchall():
        tid = str(row[0])
        if int(tid) in ADMIN_IDS:
            continue  # 🚫 排除管理员
        user_info[tid] = {
            'name': (row[1] or get_text("unknown_name")),
            'custom_id': (row[2] or '')
        }
    conn.close()

    log_path = "group_messages.log"
    pattern = re.compile(r'\[(\d{4}-\d{2}-\d{2}) \d{2}:\d{2}:\d{2}\] .*?\[用户: (.*?) \((\d+)\)\]')
    activity = defaultdict(int)

    if not os.path.exists(log_path):
        bot.reply_to(message, get_text("active_log_missing"))
        return

    with open(log_path, 'r', encoding='utf-8') as f:
        for line in f:
            match = pattern.search(line)
            if not match:
                continue
            date_str, _, tid = match.groups()
            if not date_str.startswith(target_month):
                continue
            if tid not in user_info:
                continue
            activity[tid] += 1

    sorted_activity = sorted(activity.items(), key=lambda x: x[1], reverse=True)[:20]

    if not sorted_activity:
        bot.reply_to(message, get_text("active_empty").format(min_points=MIN_ACTIVE_POINTS))
        return

    msg = get_text("active_header").format(month=target_month, min_points=MIN_ACTIVE_POINTS)
    for idx, (tid, count) in enumerate(sorted_activity, 1):
        info = user_info.get(tid, {'name': get_text("unknown_name"), 'custom_id': ''})
        msg += get_text("active_line").format(idx=idx, name=info['name'], tid=tid, count=count)

    bot.reply_to(message, msg, parse_mode="Markdown")


@bot.message_handler(commands=['ranking'])
def handle_ranking(message):
    if message.chat.type == 'private':
        # 私聊使用时，要求已加入群
        user = get_user(message.from_user.id)
        if not user or user[7] != 1:
            bot.reply_to(message, get_text("ranking_need_join_group"))
            return
    else:
        # 群聊中，只允许指定群
        if message.chat.id != ALLOWED_GROUP_ID:
            return

    month_str = datetime.now().strftime('%Y-%m')

    conn = sqlite3.connect('telegram_bot.db')
    cur = conn.cursor()
    cur.execute('''
        SELECT u.telegram_id, u.name, COALESCE(m.earned, 0) AS earned
        FROM users u
        LEFT JOIN monthly_points m
          ON m.telegram_id = u.telegram_id AND m.month = ?
        WHERE COALESCE(m.earned, 0) > 0
        ORDER BY earned DESC
        LIMIT 20
    ''', (month_str,))
    rows = cur.fetchall()
    conn.close()

    title = get_text("monthly_ranking_title")
    item_tpl = get_text("monthly_ranking_item")
    unknown_name = get_text("unknown_name")

    msg = title + "\n\n"
    if not rows:
        msg += get_text("monthly_ranking_empty")  # 可选：当无数据时的提示
    else:
        for i, (tid, name, earned) in enumerate(rows, 1):
          display_name = name or unknown_name
          msg += item_tpl.format(rank=i, name=display_name, tid=tid, earned=earned) + "\n"

    bot.reply_to(message, msg)

# /quiz 答题活动（暂未开启）
@bot.message_handler(commands=['quiz'])
def handle_quiz(message):
    if message.chat.type == 'private':
        bot.reply_to(message, '🎯 一对一答题活动暂未开启，敬请期待！')

# /start 命令（仅限私聊）
@bot.message_handler(commands=['start'])
def handle_start(message):
    if message.chat.type != 'private':
        return

    telegram_id = message.from_user.id
    args = message.text.split()
    invited_by = None
    if len(args) > 1:
        try:
            inviter_id = int(args[1])
            if inviter_id != telegram_id:
                invited_by = str(inviter_id)
        except:
            pass

    create_user_if_not_exist(telegram_id, invited_by)
    
    name = message.from_user.first_name or ""
    if message.from_user.last_name:
       name += " " + message.from_user.last_name

    custom_id = message.from_user.username or None  # 用户名可能不存在
    update_user_name_and_custom_id(telegram_id, name.strip(), custom_id)

    # 如果是被邀请用户首次注册并加入群，则奖励邀请人3积分
    if invited_by:
        inviter = get_user(int(invited_by))
        if inviter:
            update_user(int(invited_by), 'points', inviter[2] + 3)
            add_monthly_points(int(invited_by), 3)

    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=False)
    markup.add('/start','/quiz', '/bind', '/me', '/invites','/submit')

    invite_link = f"https://t.me/{bot.get_me().username}?start={telegram_id}"
    bot.send_message(message.chat.id, get_text("welcome_start").format(invite_link=invite_link), reply_markup=ReplyKeyboardRemove())

@bot.message_handler(commands=['signinword'])
def handle_sign_in_word(message):
 if message.chat.id != ALLOWED_GROUP_ID:
    bot.reply_to(message, get_text("signinword_wrong_group"))
    return
 if current_signin_word:
    bot.reply_to(message, get_text("signinword_today").format(current_signin_word=current_signin_word), parse_mode="Markdown")
 else:
    bot.reply_to(message, get_text("signinword_not_set"))


@bot.message_handler(commands=['register'])
def handle_register(message):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton(get_text("register_btn_tokenpocket"), callback_data="register_tokenpocket"))
    markup.add(types.InlineKeyboardButton(get_text("register_btn_metamask"), callback_data="register_metamask"))
    markup.add(types.InlineKeyboardButton(get_text("register_btn_anchor_android"), callback_data="register_anchor_android"))
    markup.add(types.InlineKeyboardButton(get_text("register_btn_anchor_ios"), callback_data="register_anchor_ios"))
    markup.add(types.InlineKeyboardButton(get_text("register_btn_anchor_pc"), callback_data="register_anchor_pc"))

    bot.reply_to(message, get_text("register_prompt_select"), reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("register_"))
def handle_register_callback(call):
    file_map = {
        "register_tokenpocket": "TokenPocket.pdf",
        "register_metamask": "MetaMask.pdf",
        "register_anchor_android": "anchor_android.pdf",
        "register_anchor_ios": "anchor_ios.pdf",
        "register_anchor_pc": "anchor_pc.pdf"
    }

    file_key = call.data
    file_path = file_map.get(file_key)

    if not file_path or not os.path.exists(file_path):
        bot.answer_callback_query(call.id, get_text("register_file_missing"))
        return

    with open(file_path, "rb") as f:
        bot.send_document(
            chat_id=call.message.chat.id,
            document=f,
            visible_file_name=file_path,
            caption=get_text("register_doc_caption")
        )
    bot.answer_callback_query(call.id)


# /invites 查看邀请人数（仅限私聊）
@bot.message_handler(commands=['invites'])
def handle_invites(message):
    if message.chat.type != 'private':
        return

    telegram_id = str(message.from_user.id)
    conn = sqlite3.connect('telegram_bot.db')
    cursor = conn.cursor()
    cursor.execute(
        "SELECT COUNT(*) FROM users WHERE invited_by = ? AND joined_group = 1",
        (telegram_id,)
    )
    count = cursor.fetchone()[0]
    conn.close()

    invite_link = f"https://t.me/{bot.get_me().username}?start={telegram_id}"

    bot.reply_to(
        message,
        get_text("invites_result").format(count=count, invite_link=invite_link)
    )

# /bind_binance UID（仅限私聊）
@bot.message_handler(commands=['bind_binance'])
def handle_bind_binance(message):
    if message.chat.type != 'private':
        return
    telegram_id = message.from_user.id
    create_user_if_not_exist(telegram_id)

    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        bot.reply_to(message, get_text("bind_binance_usage"))
        return

    uid = parts[1].strip()
    if not uid.isdigit():
        bot.reply_to(message, get_text("bind_binance_usage"))
        return

    update_user(telegram_id, 'binance_uid', uid)
    bot.reply_to(message, get_text("bind_binance_success").format(uid=uid))


# /bind_twitter handle（仅限私聊）
@bot.message_handler(commands=['bind_twitter'])
def handle_bind_twitter(message):
    if message.chat.type != 'private':
        return
    telegram_id = message.from_user.id
    create_user_if_not_exist(telegram_id)

    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        bot.reply_to(message, get_text("bind_twitter_usage"))
        return

    handle = parts[1].strip()
    if not handle.startswith('@') or len(handle) < 2:
        bot.reply_to(message, get_text("bind_twitter_usage"))
        return

    update_user(telegram_id, 'twitter_handle', handle)
    bot.reply_to(message, get_text("bind_twitter_success").format(handle=handle))


# /bind_vaulta_account A名（仅限私聊）
@bot.message_handler(commands=['bind_vaulta_account'])
def handle_bind_vaulta_account(message):
    if message.chat.type != 'private':
        return
    telegram_id = message.from_user.id
    create_user_if_not_exist(telegram_id)

    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        bot.reply_to(message, get_text("bind_vaulta_usage"))
        return

    a_account = parts[1].strip()
    if not a_account:
        bot.reply_to(message, get_text("bind_vaulta_usage"))
        return

    update_user(telegram_id, 'a_account', a_account)
    bot.reply_to(message, get_text("bind_vaulta_success").format(a_account=a_account))

# /me 查看当前信息（仅限私聊）
@bot.message_handler(commands=['me'])
def handle_me(message):
    if message.chat.type != 'private':
        return

    telegram_id = message.from_user.id
    user = get_user(telegram_id)
    if not user:
        bot.reply_to(message, get_text("me_not_found"))
        return

    conn = sqlite3.connect('telegram_bot.db')
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM users WHERE invited_by = ? AND joined_group = 1", (str(telegram_id),))
    invite_count = cursor.fetchone()[0]

    month_str = datetime.now().strftime('%Y-%m')
    cur.execute("SELECT COALESCE(earned,0) FROM monthly_points WHERE telegram_id = ? AND month = ?", (telegram_id, month_str))
    row = cur.fetchone()
    month_points = row[0] if row else 0
    conn.close()

    binance = user[3] if user[3] else get_text("me_unbound")
    twitter = user[4] if user[4] else get_text("me_unbound")
    a_account = user[5] if user[5] else get_text("me_unbound")

    invite_link = f"https://t.me/{bot.get_me().username}?start={telegram_id}"

    msg = get_text("me_profile").format(
        telegram_id=telegram_id,
        points=user[2],
        unlocked=user[11],
        month_points=month_points,
        binance=binance,
        twitter=twitter,
        a_account=a_account,
        invite_count=invite_count,
        invite_link=invite_link
    )

    bot.reply_to(message, msg)

@bot.message_handler(commands=['my_submissions'])
def handle_my_submissions(message):
    if message.chat.type != 'private':
        return

    telegram_id = message.from_user.id
    conn = sqlite3.connect('telegram_bot.db')
    cursor = conn.cursor()
    cursor.execute("SELECT type, link FROM submissions WHERE telegram_id = ?", (telegram_id,))
    results = cursor.fetchall()
    conn.close()

    if not results:
        bot.reply_to(message, get_text("my_submissions_none"))
        return

    binance_links = [link for typ, link in results if typ == "binance"]
    twitter_links = [link for typ, link in results if typ == "twitter"]

    lines = [get_text("my_submissions_header")]

    # Binance
    if binance_links:
        lines.append(get_text("my_submissions_binance_title") + "\n".join(f"• {l}" for l in binance_links) + "\n\n")
    else:
        lines.append(get_text("my_submissions_binance_title") + get_text("my_submissions_none_item") + "\n\n")

    # Twitter/X
    if twitter_links:
        lines.append(get_text("my_submissions_twitter_title") + "\n".join(f"• {l}" for l in twitter_links))
    else:
        lines.append(get_text("my_submissions_twitter_title") + get_text("my_submissions_none_item"))

    msg = "".join(lines)
    bot.reply_to(message, msg, parse_mode="Markdown", disable_web_page_preview=True)

@bot.message_handler(commands=['bind'])
def handle_bind(message):
    if message.chat.type != 'private':
        return
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton(get_text("bind_btn_binance"), callback_data="bind_binance"))
    markup.add(types.InlineKeyboardButton(get_text("bind_btn_x"), callback_data="bind_x"))
    markup.add(types.InlineKeyboardButton(get_text("bind_btn_vaulta"), callback_data="bind_vaulta"))
    bot.send_message(message.chat.id, get_text("bind_prompt_select_type"), reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("bind_"))
def handle_bind_callback(call):
    try:
        if call.data == "bind_binance":
            bot.send_message(call.message.chat.id, get_text("bind_binance_hint"), parse_mode="HTML")
        elif call.data == "bind_x":
            bot.send_message(call.message.chat.id, get_text("bind_x_hint"), parse_mode="HTML")
        elif call.data == "bind_vaulta":
            bot.send_message(call.message.chat.id, get_text("bind_vaulta_hint"), parse_mode="HTML")
    finally:
        bot.answer_callback_query(call.id)

@bot.message_handler(commands=['transfer_points'])
def handle_transfer_points(message):
    if message.chat.type != 'private':
        return

    args = message.text.split()

    if len(args) != 3:
        bot.reply_to(message, get_text("transfer_points_usage"), parse_mode="Markdown")
        return

    try:
        sender_id = message.from_user.id
        recipient_id = int(args[1])
        amount = int(args[2])

        if sender_id == recipient_id:
            bot.reply_to(message, get_text("transfer_self_forbidden_1"))
            return
        if amount <= 0:
            bot.reply_to(message, get_text("transfer_amount_positive_1"))
            return

        sender = get_user(sender_id)
        recipient = get_user(recipient_id)

        if not sender:
            bot.reply_to(message, get_text("transfer_sender_not_registered_1"))
            return
        if not recipient:
            bot.reply_to(message, get_text("transfer_recipient_not_exist_1"))
            return

        # 统一以“已解锁积分”校验与转账
        sender_unlocked = sender[11]
        recipient_unlocked = recipient[11]

        if sender_unlocked < amount:
            bot.reply_to(message, get_text("transfer_not_enough_unlocked").format(points=sender_unlocked))
            return

        # 更新数据库
        update_user(sender_id, 'unlocked_points', sender_unlocked - amount)
        update_user(recipient_id, 'unlocked_points', recipient_unlocked + amount)

        log_transfer(sender_id, recipient_id, amount)

        bot.reply_to(
            message,
            get_text("transfer_success_with_remaining").format(
                amount=amount,
                recipient_id=recipient_id,
                remaining=sender_unlocked - amount
            )
        )
    except ValueError:
        bot.reply_to(message, get_text("transfer_invalid_values"))
    except Exception as e:
        bot.reply_to(message, get_text("transfer_failed_generic").format(error=str(e)))

@bot.message_handler(commands=['unlock_points'])
def handle_unlock_points(message):
    if message.chat.type != 'private':
        return

    telegram_id = message.from_user.id
    user = get_user(telegram_id)
    if not user:
        bot.reply_to(message, get_text("unlock_not_registered"))
        return

    try:
        amount = int(message.text.split()[1])
        if amount <= 0:
            raise ValueError
    except Exception:
        bot.reply_to(message, get_text("unlock_format_error"))
        return

    total_points = user[2]
    unlocked = user[11]  # unlocked_points

    if total_points < amount:
        bot.reply_to(
            message,
            get_text("unlock_points_not_enough").format(total=total_points, amount=amount)
        )
        return

    # 更新数据库
    conn = sqlite3.connect('telegram_bot.db')
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE users
        SET points = points - ?, unlocked_points = unlocked_points + ?
        WHERE telegram_id = ?
    ''', (amount, amount, telegram_id))
    conn.commit()
    conn.close()

    bot.reply_to(
        message,
        get_text("unlock_success").format(amount=amount, unlocked_after=unlocked + amount)
    )


@bot.message_handler(commands=['transfers'])
def handle_all_transfers(message):
    if message.chat.type != 'private':
        return

    telegram_id = message.from_user.id
    conn = sqlite3.connect('telegram_bot.db')
    cursor = conn.cursor()

    cursor.execute('''
        SELECT sender_id, recipient_id, amount, timestamp
        FROM transfers
        WHERE sender_id = ? OR recipient_id = ?
        ORDER BY timestamp DESC
    ''', (telegram_id, telegram_id))
    records = cursor.fetchall()

    if not records:
        bot.reply_to(message, get_text("transfers_none"))
        conn.close()
        return

    # 查询所有相关用户的 name 和 custom_id（避免重复查）
    user_ids = set()
    for sid, rid, _, _ in records:
        user_ids.add(sid)
        user_ids.add(rid)

    placeholders = ",".join("?" for _ in user_ids)
    cursor.execute(f'''
        SELECT telegram_id, name, custom_id FROM users
        WHERE telegram_id IN ({placeholders})
    ''', tuple(user_ids))
    rows = cursor.fetchall()
    conn.close()

    # 缓存：uid -> (name, cid)
    user_info = {row[0]: (row[1] or get_text("unknown_name"), row[2] or "") for row in rows}

    def format_user(uid: int) -> str:
        name, cid = user_info.get(uid, (get_text("unknown_name"), ""))
        if cid:
            return get_text("user_display_with_cid").format(name=name, cid=cid)
        return get_text("user_display_name_only").format(name=name)

    msg = get_text("transfers_header")
    for sid, rid, amt, ts in records:
        if sid == telegram_id:
            msg += get_text("transfers_line_out").format(amount=amt, rid=rid, user_display=format_user(rid), ts=ts)
        else:
            msg += get_text("transfers_line_in").format(amount=amt, sid=sid, user_display=format_user(sid), ts=ts)

    bot.reply_to(message, msg, parse_mode="Markdown")
    
@bot.message_handler(commands=['transfer'])
def handle_transfer_button(message):
    if message.chat.type != 'private':
        return
    bot.send_message(message.chat.id, get_text("transfer_prompt_recipient"))
    bot.register_next_step_handler(message, get_recipient_id)

def get_recipient_id(message):
    try:
        recipient_id = int(message.text.strip())
        if recipient_id == message.from_user.id:
            bot.reply_to(message, get_text("transfer_self_forbidden"))
            return
        bot.send_message(message.chat.id, get_text("transfer_prompt_amount"))
        bot.register_next_step_handler(message, process_transfer_amount, recipient_id)
    except Exception:
        bot.reply_to(message, get_text("transfer_invalid_telegram_id"))

def process_transfer_amount(message, recipient_id):
    try:
        amount = int(message.text.strip())
        sender_id = message.from_user.id

        if amount <= 0:
            bot.reply_to(message, get_text("transfer_amount_positive"))
            return

        sender = get_user(sender_id)
        recipient = get_user(recipient_id)

        if not sender:
            bot.reply_to(message, get_text("transfer_sender_not_registered"))
            return
        if not recipient:
            bot.reply_to(message, get_text("transfer_recipient_not_exist"))
            return
        if sender[11] < amount:
            bot.reply_to(message, get_text("transfer_not_enough_points").format(points=sender[11]))
            return

        # 执行转账
        update_user(sender_id, 'unlocked_points', sender[11] - amount)
        update_user(recipient_id, 'unlocked_points', recipient[11] + amount)

        log_transfer(sender_id, recipient_id, amount)

        bot.reply_to(message, get_text("transfer_success").format(amount=amount, recipient_id=recipient_id))
    except:
        bot.reply_to(message, get_text("transfer_invalid_input"))


@bot.message_handler(commands=['get_group_id'])
def handle_get_group_id(message):
    print(get_text("get_group_id_log").format(title=message.chat.title, id=message.chat.id))
    if message.chat.type in ['group', 'supergroup']:
        bot.reply_to(message, get_text("get_group_id_reply_group"))
    else:
        bot.reply_to(message, get_text("get_group_id_reply_private"))

# 每日选择有效签到词，并在群内发布并置顶

def select_daily_signin_word():
    global current_signin_word
    print(get_text("select_signin_task_log").format(time=datetime.now()))

    if not os.path.exists(SIGNIN_WORDS_FILE):
        print(get_text("signin_file_missing"))
        return

    with open(SIGNIN_WORDS_FILE, 'r', encoding='utf-8') as f:
        lines = [line.strip() for line in f if line.strip()]

    if not lines:
        print(get_text("signin_file_empty"))
        return

    current_signin_word = random.choice(lines)

    # 写入临时文件
    with open(TEMP_SIGNIN_FILE, 'w', encoding='utf-8') as f:
        f.write(current_signin_word)

    try:
        sent = bot.send_message(
            ALLOWED_GROUP_ID,
            get_text("signin_announce").format(current_signin_word=current_signin_word),
            parse_mode="Markdown"
        )
        bot.pin_chat_message(ALLOWED_GROUP_ID, sent.message_id, disable_notification=False)
        threading.Timer(300, lambda: bot.unpin_chat_message(ALLOWED_GROUP_ID, message_id=sent.message_id)).start()
    except Exception as e:
        print(get_text("signin_send_failed").format(error=str(e)))

# 群内消息处理：检测是否为当前签到词
@bot.message_handler(func=lambda m: m.chat.type in ['group', 'supergroup'])
def handle_custom_signin_word(message):
    try:
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        user_name = (message.from_user.first_name or "")
        if message.from_user.last_name:
            user_name += " " + message.from_user.last_name
        text_or_mark = message.text.strip() if message.text else get_text("log_non_text")

        line = get_text("log_line_group_msg").format(
            timestamp=timestamp,
            chat_title=message.chat.title,
            chat_id=message.chat.id,
            user_name=user_name,
            user_id=message.from_user.id,
            text=text_or_mark
        )

        with open(MESSAGE_LOG_FILE, 'a', encoding='utf-8') as log_file:
            log_file.write(line)
    except Exception as e:
        print(get_text("log_group_write_failed").format(error=str(e)))

    # 先检查敏感词
    sensitive_words = load_sensitive_words()
    text = message.text.lower() if message.text else ""
    for word in sensitive_words:
        if word and word in text:
            try:
                bot.delete_message(message.chat.id, message.message_id)

                name = message.from_user.first_name or ""
                if message.from_user.last_name:
                    name += " " + message.from_user.last_name
                username = message.from_user.username or ""

                warn = bot.send_message(
                    message.chat.id,
                    get_text("sensitive_warn_public").format(
                        username=username,
                        name=name,
                        user_id=message.from_user.id
                    )
                )
                threading.Timer(15, lambda: bot.delete_message(message.chat.id, warn.message_id)).start()

                print(get_text("sensitive_trigger_log").format(
                    word=word,
                    username=username,
                    name=name,
                    user_id=message.from_user.id
                ))
            except Exception as e:
                print(get_text("sensitive_delete_failed").format(error=str(e)))
            break

    telegram_id = message.from_user.id
    create_user_if_not_exist(telegram_id)

    name = message.from_user.first_name or ""
    if message.from_user.last_name:
        name += " " + message.from_user.last_name

    custom_id = message.from_user.username or None
    update_user_name_and_custom_id(telegram_id, name.strip(), custom_id)

    global current_signin_word
    if message.chat.id != ALLOWED_GROUP_ID:
        return
    if not current_signin_word:
        return

    if message.text and message.text.strip().lower() == current_signin_word.lower():
        update_user(telegram_id, 'joined_group', 1)

        user = get_user(telegram_id)
        now = datetime.now()
        today_str = now.strftime('%Y-%m-%d')
        last_signin = user[1]          # last_signin
        last_bonus_date = user[10]     # last_bonus_date

        # 判断是否已经签到
        if last_signin:
            try:
                last_signin_date = datetime.strptime(last_signin, '%Y-%m-%d %H:%M:%S').date()
                if last_signin_date == now.date():
                    msg = bot.reply_to(message, get_text("already_signed_today"))
                    threading.Timer(30, lambda: bot.delete_message(message.chat.id, msg.message_id)).start()
                    return
            except Exception as e:
                print(get_text("date_parse_failed").format(error=str(e)))

        update_user(telegram_id, 'last_signin', now.strftime('%Y-%m-%d %H:%M:%S'))
        new_points = user[2] + 1
        monthly_points_add = 1

        # 记录签到历史（按日期）
        record_signin_history(telegram_id, now.strftime('%Y-%m-%d'))

        # 检查最近7天是否至少有7次
        bonus_text = ""
        if count_signins_last_7_days(telegram_id) >= 7:
            if (not last_bonus_date) or (datetime.strptime(last_bonus_date, "%Y-%m-%d") <= now - timedelta(days=7)):
                new_points += 2
                monthly_points_add += 2
                bonus_text = get_text("bonus_7in7")
                update_user(telegram_id, 'last_bonus_date', today_str)

        update_user(telegram_id, 'points', new_points)
        add_monthly_points(telegram_id, monthly_points_add)

        msg = bot.reply_to(
            message,
            get_text("signin_success").format(new_points=new_points, bonus_text=bonus_text)
        )
        threading.Timer(30, lambda: bot.delete_message(message.chat.id, msg.message_id)).start()

        print(get_text("recv_group_log").format(
            chat_id=message.chat.id,
            user_id=message.from_user.id,
            content=(message.text or "")
        ))

        # 再次确保用户信息最新
        name = message.from_user.first_name or ""
        if message.from_user.last_name:
          name += " " + message.from_user.last_name

        custom_id = message.from_user.username or None  # 自定义用户名可能不存在

        update_user_name_and_custom_id(telegram_id, name.strip(), custom_id)


def safe_delete(chat_id, msg_id, label=""):
    try:
        bot.delete_message(chat_id, msg_id)
    except Exception as e:
        print(get_text("safe_delete_failed").format(label=label, msg_id=msg_id, error=str(e)))

def load_rss_sources(file_path='rss_sources.json'):
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            sources = json.load(f)
            if not isinstance(sources, list):
                raise ValueError("配置文件格式错误，应为列表。")
            return sources
    except Exception as e:
        print(f"❌ Unable to load RSS configuration file: {e}")
        return []

def fetch_rss_news():
    print(get_text("rss_task_log").format(time=datetime.now()))
    feeds = load_rss_sources()
    news_items = []

    for feed_url in feeds:
        try:
            feed = feedparser.parse(feed_url)

            if (not getattr(feed, "entries", None)) or (not all(hasattr(entry, "title") and hasattr(entry, "link") for entry in feed.entries)):
                print(get_text("rss_invalid_feed").format(url=feed_url))
                continue

            for entry in feed.entries[:5]:
                title = entry.title
                link = entry.link

                # 仅非英文模式才翻译到中文
                if LANG != "en":
                    try:
                        translated_title = translator.translate(title, dest="zh-cn").text
                    except Exception:
                        translated_title = title
                else:
                    translated_title = title

                news_items.append(f"• [{translated_title}]({link})")

        except Exception as e:
            print(get_text("rss_fetch_failed").format(url=feed_url, error=str(e)))
            continue

    news_items = news_items[:8]

    if news_items:
        message = get_text("rss_header") + "\n".join(news_items)
        try:
            bot.send_message(ALLOWED_GROUP_ID, message, parse_mode="Markdown", disable_web_page_preview=True)
        except Exception:
            print(get_text("rss_send_failed"))
    else:
        print(get_text("rss_none"))
       

price_cache = {}  # 存储每日 00:00 价格

def load_watchlist():
    try:
        with open('watchlist.json', 'r') as f:
            return json.load(f)
    except:
        return ["BTCUSDT"]

def fetch_price(symbol):
    url = f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}"
    try:
        response = requests.get(url, timeout=5)
        data = response.json()
        return float(data['price']) if 'price' in data else None
    except Exception as e:
        print(get_text("fetch_price_failed").format(symbol=symbol, error=str(e)))
        return None

def update_daily_open_prices():
    global price_cache
    watchlist = load_watchlist()

    print(get_text("open_price_task_log").format(time=datetime.now()))

    for symbol in watchlist:
        price = fetch_price(symbol)
        if price:
            price_cache[symbol] = price
            print(get_text("open_price_log").format(symbol=symbol, price=price))
        else:
            print(get_text("open_price_fail").format(symbol=symbol))

    # ✅ 写入文件持久化
    try:
        with open("open_prices.json", "w", encoding="utf-8") as f:
            json.dump(price_cache, f)
            print(get_text("open_price_save_success"))
    except Exception as e:
        print(get_text("open_price_save_fail").format(error=str(e)))


def broadcast_price_changes():
    watchlist = load_watchlist()
    messages = []

    print(get_text("broadcast_task_log").format(time=datetime.now()))

    for symbol in watchlist:
        current_price = fetch_price(symbol)
        if current_price is None:
            continue

        open_price = price_cache.get(symbol)
        if open_price:
            diff = current_price - open_price
            percent = (diff / open_price) * 100
            arrow = "📈" if percent >= 0 else "📉"
            change_str = f"{arrow} {percent:.4f}%"
        else:
            change_str = get_text("broadcast_no_open_price")

        display_symbol = f"{symbol[:-4]}/USDT" if symbol.endswith("USDT") else symbol
        messages.append(
            get_text("broadcast_line").format(
                symbol=display_symbol,
                price=f"{current_price:.4f}",
                change=change_str
            )
        )

    if messages:
        full_msg = "\n".join(messages) + get_text("broadcast_footer")
        try:
            bot.send_message(ALLOWED_GROUP_ID, full_msg)
        except Exception as e:
            print(get_text("broadcast_send_failed").format(error=str(e)))


schedule.every().day.at("09:00").do(fetch_rss_news)
schedule.every().day.at("09:05").do(select_daily_signin_word)
schedule.every().day.at("00:00").do(update_daily_open_prices)

# 每两小时播报一次价格
schedule.every(2).hours.do(broadcast_price_changes)

# 启动时初始化开盘价一次
# 启动时加载价格缓存
try:
    with open("open_prices.json", "r", encoding="utf-8") as f:
        price_cache = json.load(f)
        print(f"[Startup] Loaded open_prices.json cache: {price_cache}")
except Exception as e:
    print(f"[Startup] Unable to load open_prices.json, using empty cache: {e}")
    update_daily_open_prices()


#broadcast_price_changes()

# 启动时执行一次
if not os.path.exists(TEMP_SIGNIN_FILE):
    fetch_rss_news()
    select_daily_signin_word()
else:
    with open(TEMP_SIGNIN_FILE, 'r', encoding='utf-8') as f:
        current_signin_word = f.read().strip()
        print(f"[Startup] Sign-in words loaded from temporary file: {current_signin_word}")


# ✅ 新增：独立线程运行定时任务
def run_schedule():
    while True:
        schedule.run_pending()
        time.sleep(5)

# 启动调度线程
threading.Thread(target=run_schedule, daemon=True).start()

bot.set_my_commands([
    telebot.types.BotCommand("start", get_text("cmd_start")),
    telebot.types.BotCommand("me", get_text("cmd_me")),
    telebot.types.BotCommand("bind", get_text("cmd_bind")),
    telebot.types.BotCommand("invites", get_text("cmd_invites")),
    telebot.types.BotCommand("submit", get_text("cmd_submit")),
    telebot.types.BotCommand("quiz", get_text("cmd_quiz")),
    telebot.types.BotCommand("price", get_text("cmd_price")),
    telebot.types.BotCommand("feedback", get_text("cmd_feedback")),
    telebot.types.BotCommand("unlock_points", get_text("cmd_unlock_points")),
    telebot.types.BotCommand("transfer", get_text("cmd_transfer")),
    telebot.types.BotCommand("transfers", get_text("cmd_transfers")),
    telebot.types.BotCommand("signinword", get_text("cmd_signinword")),
    telebot.types.BotCommand("ranking", get_text("cmd_ranking")),
    telebot.types.BotCommand("active", get_text("cmd_active")),
    telebot.types.BotCommand("register", get_text("cmd_register")),
    telebot.types.BotCommand("help", get_text("cmd_help"))
])

# 启动 Telegram Bot（主线程）
print("Bot is running...")

while True:
    try:
        bot.polling(none_stop=True, timeout=60, long_polling_timeout=60)
    except telebot.apihelper.ApiTelegramException as e:
        if e.error_code == 502:
            print(f"[WARN]] Telegram 502 Bad Gateway，Skip restart, wait 5 seconds to reconnect...")
            time.sleep(5)
            continue  # 直接继续循环，不退出
        else:
            print(f"[ERROR] Telegram API error: {e}")
            time.sleep(5)
    except Exception as e:
        print(f"[ERROR] An unknown exception occurred: {e}")
        time.sleep(5)