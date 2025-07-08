import telebot
from telebot import types
from datetime import datetime, timedelta
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


current_quiz = {}

translator = Translator()
TEMP_SIGNIN_FILE = 'temp_signin_word.txt'

# 读取配置文件
with open('config.json', 'r', encoding='utf-8') as f:
    config = json.load(f)

BOT_TOKEN = config['BOT_TOKEN']
ADMIN_IDS = config['ADMIN_IDS']
ALLOWED_GROUP_ID = config['ALLOWED_GROUP_ID']

print(f"[CONFIG] BOT_TOKEN: {BOT_TOKEN}")
print(f"[CONFIG] ADMIN_IDS: {ADMIN_IDS}")
print(f"[CONFIG] ALLOWED_GROUP_ID: {ALLOWED_GROUP_ID}")

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
    last_bonus_date TEXT
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

def update_user_name_and_custom_id(telegram_id, name):
    conn = sqlite3.connect('telegram_bot.db')
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET name = ? WHERE telegram_id = ?', (name, telegram_id))
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

@bot.message_handler(commands=['export_submissions'])
def export_submissions_csv(message):
    if message.chat.type != 'private':
        return
    if message.from_user.id not in ADMIN_IDS:
        bot.reply_to(message, "❌ No permission. This command is only available to administrators.")
        return

    try:
        conn = sqlite3.connect('telegram_bot.db')
        cursor = conn.cursor()
        cursor.execute("SELECT telegram_id, type, link FROM submissions")
        rows = cursor.fetchall()
        conn.close()

        if not rows:
            bot.reply_to(message, "⚠️ No submission record yet.")
            return

        # 使用 StringIO 写入文本内容，再编码为字节
        string_io = StringIO()
        writer = csv.writer(string_io)
        writer.writerow(["Telegram ID", "Type", "Link"])
        for row in rows:
            writer.writerow(row)

        byte_io = BytesIO(string_io.getvalue().encode('utf-8'))
        byte_io.seek(0)

        file_name = f"submissions_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        bot.send_document(message.chat.id, byte_io, visible_file_name=file_name, caption="✅ Submit data export completed")
        byte_io.close()

    except Exception as e:
        bot.reply_to(message, f"❌ Export failed: {e}")

@bot.message_handler(commands=['export_users'])
def export_users_csv(message):
    if message.chat.type != 'private':
        return
    if message.from_user.id not in ADMIN_IDS:
        bot.reply_to(message, "❌ No permission. This command is only available to administrators.")
        return

    try:
        conn = sqlite3.connect('telegram_bot.db')
        cursor = conn.cursor()
        cursor.execute('''
            SELECT 
                telegram_id, last_signin, points, binance_uid, twitter_handle, 
                a_account, invited_by, joined_group, name, custom_id, last_bonus_date
            FROM users
        ''')
        rows = cursor.fetchall()
        conn.close()

        if not rows:
            bot.reply_to(message, "⚠️ There is currently no user data. ")
            return

        # 写入 CSV 格式
        string_io = StringIO()
        writer = csv.writer(string_io)
        writer.writerow([
            "Telegram ID", "Last check-in time", "Points", "Binance UID", "X account", 
"A account", "Inviter ID", "Join the group", "Name", "Custom ID", "Last extra points time"
        ])
        for row in rows:
            writer.writerow(row)

        byte_io = BytesIO(string_io.getvalue().encode("utf-8"))
        byte_io.seek(0)
        filename = f"users_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        bot.send_document(message.chat.id, byte_io, visible_file_name=filename, caption="✅ User data export completed.")
        byte_io.close()

    except Exception as e:
        bot.reply_to(message, f"❌ Export failed: {e}")


@bot.message_handler(commands=['quiz_send'])
def send_quiz(message):
    if message.from_user.id not in ADMIN_IDS:
        bot.reply_to(message, "❌ You do not have permission to send questions.")
        return

    try:
        if message.text.strip() == "/quiz_send":
            # 从题库文件中读取
            with open('quiz_bank.json', 'r', encoding='utf-8') as f:
                quiz_list = json.load(f)
            if not quiz_list:
                bot.reply_to(message, "⚠️ The question bank is empty.")
                return
            quiz_data = random.choice(quiz_list)

            # ✅ 打印选中的题目（调试用）
            print("[DEBUG] 选中题目：", json.dumps(quiz_data, ensure_ascii=False))

        else:
            quiz_data = json.loads(message.text.replace('/quiz_send', '').strip())

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

        sent_msg = bot.send_message(ALLOWED_GROUP_ID, f"🧩 Time-limited quick-answer questions, 1 point for a correct answer, questions expire after 30 minutes:\n\n{question}", reply_markup=markup)

        threading.Timer(1800, lambda: disable_quiz(quiz_id)).start()

    except Exception as e:
        bot.reply_to(message, f"❌ Format error:{e}\n JSON：\n/quiz_send {{\"question\": \"...\", \"options\": [\"A\", \"B\"], \"answer\": 0}}")

def disable_quiz(qid):
    if current_quiz.get("id") == qid:
        current_quiz.clear()
        print("🛑 The quiz is over.")
        bot.send_message(ALLOWED_GROUP_ID, "⏰ The time for this question is over, thank you for participating!")


@bot.message_handler(commands=['submit'])
def handle_submit(message):
    if message.chat.type != 'private':
        return

    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton("📤 Submit Binance article link:", callback_data="submit_binance"),
        types.InlineKeyboardButton("🧵 Submit Twitter X link:", callback_data="submit_twitter")
    )
    bot.send_message(message.chat.id, "Please select the type of article you wish to submit:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("submit_"))
def handle_submit_callback(call):
    type_map = {
        "submit_binance": "binance",
        "submit_twitter": "twitter"
    }
    submit_type = type_map[call.data]
    bot.send_message(call.message.chat.id, f"Please enter the { 'Binance' if submit_type == 'binance' else 'X' } article link:")
    
    # 设置下一条消息为链接输入
    bot.register_next_step_handler(call.message, process_submission, submit_type, call.from_user.id)
    bot.answer_callback_query(call.id)

def process_submission(message, submit_type, telegram_id):
    link = message.text.strip()
    if not link.startswith("http"):
        bot.reply_to(message, "❌ Please enter a valid URL (must start with http)")
        return

    conn = sqlite3.connect('telegram_bot.db')
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM submissions WHERE telegram_id = ? AND type = ? AND link = ?", (telegram_id, submit_type, link))
    exists = cursor.fetchone()
    if exists:
        bot.reply_to(message, "⚠️ You have already submitted this link and cannot submit it again.")
    else:
        cursor.execute("INSERT INTO submissions (telegram_id, type, link) VALUES (?, ?, ?)", (telegram_id, submit_type, link))
        conn.commit()
        bot.reply_to(message, f"✅ { 'Binance' if submit_type == 'binance' else 'X' } link submitted successfully!")

    conn.close()


@bot.message_handler(commands=['add_sensitive'])
def handle_add_sensitive(message):
    if message.from_user.id not in ADMIN_IDS:
        bot.reply_to(message, "❌ You do not have permission to add sensitive words.")
        return

    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        bot.reply_to(message, "⚠️ Please use the format: /add_sensitive WORD")
        return

    new_word = args[1].strip().lower()
    if not new_word:
        bot.reply_to(message, "⚠️ Sensitive words cannot be empty.")
        return

    try:
        with open('sensitive_words.txt', 'a+', encoding='utf-8') as f:
            f.seek(0)
            existing_words = [line.strip().lower() for line in f.readlines()]
            if new_word in existing_words:
                bot.reply_to(message, f"⚠️ Sensitive words “{new_word}” already exists.")
                return
            f.write(new_word + '\n')
        bot.reply_to(message, f"✅ Sensitive words “{new_word}” Added.")
    except Exception as e:
        bot.reply_to(message, f"❌ Add failed: {e}")


@bot.callback_query_handler(func=lambda call: call.data.startswith("quiz_"))
def handle_quiz_answer(call):
    parts = call.data.split("_")
    quiz_id, choice = parts[1], int(parts[2])
    telegram_id = call.from_user.id

    # 无进行中题目或不匹配
    if current_quiz.get("id") != quiz_id:
        bot.answer_callback_query(call.id, "❌ The answer has ended or is invalid.")
        return

    # 检查数据库是否答过
    conn = sqlite3.connect('telegram_bot.db')
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM quiz_answers WHERE quiz_id = ? AND telegram_id = ?", (quiz_id, telegram_id))
    if cursor.fetchone():
        conn.close()
        #bot.answer_callback_query(call.id, "⚠️ 您已答过本题")
        bot.send_message(call.message.chat.id, f"⚠️ {call.from_user.first_name} ⚠️ You have answered this question.")
        return

    # 插入答题记录
    cursor.execute("INSERT INTO quiz_answers (quiz_id, telegram_id) VALUES (?, ?)", (quiz_id, telegram_id))
    conn.commit()

    # 判断正误
    if choice == current_quiz.get("answer"):
        user = get_user(telegram_id)
        update_user(telegram_id, 'points', user[2] + 1)
       # bot.answer_callback_query(call.id, "✅ 回答正确！积分 +1")
        bot.send_message(call.message.chat.id, f"✅ {call.from_user.first_name} Correct answer! Points +1")
    else:
        # bot.answer_callback_query(call.id, "❌ 回答错误")
        bot.send_message(call.message.chat.id, f"❌ {call.from_user.first_name} Wrong answer")
    conn.close()

@bot.message_handler(commands=['ranking'])
def handle_ranking(message):
    if message.chat.id != ALLOWED_GROUP_ID:
        return

    conn = sqlite3.connect('telegram_bot.db')
    cursor = conn.cursor()

    cursor.execute('''
        SELECT 
            u.telegram_id,
            u.name,
            u.points,
            COALESCE(s.snapshot_points, 0) as snapshot
        FROM users u
        LEFT JOIN monthly_snapshot s ON u.telegram_id = s.telegram_id
    ''')

    rows = cursor.fetchall()
    conn.close()

    # 计算当月积分
    ranking = []
    for row in rows:
        telegram_id, name, points, snapshot = row
        monthly_score = points - snapshot
        ranking.append((telegram_id, name or 'unkown', monthly_score))

    # 排序
    ranking.sort(key=lambda x: x[2], reverse=True)

    # 组装消息
    msg = "🏆 This month's ranking list (top 20):\n\n"
    for idx, (tid, name, score) in enumerate(ranking[:20], 1):
        msg += f"{idx}. {name}（Telegram id:{tid}）| {score} 分\n"

    bot.reply_to(message, msg)

# /quiz 答题活动（暂未开启）
@bot.message_handler(commands=['quiz'])
def handle_quiz(message):
    if message.chat.type == 'private':
        bot.reply_to(message, '🎯 The one-on-one question-answering activity has not yet started, so stay tuned!')

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

    # 如果是被邀请用户首次注册并加入群，则奖励邀请人3积分
    if invited_by:
        inviter = get_user(int(invited_by))
        if inviter:
            update_user(int(invited_by), 'points', inviter[2] + 3)

    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=False)
    markup.add('/start','/quiz', '/bind', '/me', '/invites','/submit')
    invite_link = f"https://t.me/{bot.get_me().username}?start={telegram_id}"
    bot.send_message(message.chat.id, f"Welcome to the Points Robot, join\nhttps://t.me/vaulta_cn\n and send sign word in group (Use /signinword in the group to view) Sign in to complete the invitation\n\n🔗 Your exclusive invitation link: \n{invite_link}", reply_markup=markup)

@bot.message_handler(commands=['signinword'])
def handle_sign_in_word(message):
    if message.chat.id != ALLOWED_GROUP_ID:
        return
    if current_signin_word:
        bot.reply_to(message, f"📌 Today's sign-in words are: \n\n`{current_signin_word}`\n\n/ranking View the current top 20 points ranking \n\nSign in five times in a row within seven days and you will get 2 extra points", parse_mode="Markdown")
    else:
        bot.reply_to(message, "⚠️ No sign-in words have been set for today. Please try again later.")

# /invites 查看邀请人数（仅限私聊）
@bot.message_handler(commands=['invites'])
def handle_invites(message):
    if message.chat.type != 'private':
        return
    telegram_id = str(message.from_user.id)
    conn = sqlite3.connect('telegram_bot.db')
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM users WHERE invited_by = ? AND joined_group = 1", (telegram_id,))
    count = cursor.fetchone()[0]
    conn.close()
    invite_link = f"https://t.me/{bot.get_me().username}?start={telegram_id}"

    bot.reply_to(message, f"You have successfully invited {count} people to join the group! \n\n🔗 Your exclusive invitation link:\n\n{invite_link}")
    #bot.send_message(message.chat.id, f"🔗 您的专属邀请链接：\n{invite_link}", reply_markup=markup)


# /bind_binance UID（仅限私聊）
@bot.message_handler(commands=['bind_binance'])
def handle_bind_binance(message):
    if message.chat.type != 'private':
        return
    telegram_id = message.from_user.id
    create_user_if_not_exist(telegram_id)
    try:
        uid = message.text.split()[1]
        if not uid.isdigit():
            raise ValueError
        update_user(telegram_id, 'binance_uid', uid)
        bot.reply_to(message, f"Successfully bound Binance UID: {uid}。")
    except:
        bot.reply_to(message, "Please enter a valid Binance UID, for example: /bind_binance 12345678")

# /bind_twitter handle（仅限私聊）
@bot.message_handler(commands=['bind_twitter'])
def handle_bind_twitter(message):
    if message.chat.type != 'private':
        return
    telegram_id = message.from_user.id
    create_user_if_not_exist(telegram_id)
    try:
        handle = message.text.split()[1]
        if not handle.startswith('@'):
            raise ValueError
        update_user(telegram_id, 'twitter_handle', handle)
        bot.reply_to(message, f"Successfully bound X account:{handle}。")
    except:
        bot.reply_to(message, "Please enter a valid Twitter handle, for example: /bind_twitter @yourhandle")

# /bind_vaulta_account A名（仅限私聊）
@bot.message_handler(commands=['bind_vaulta_account'])
def handle_bind_vaulta_account(message):
    if message.chat.type != 'private':
        return
    telegram_id = message.from_user.id
    create_user_if_not_exist(telegram_id)
    try:
        a_account = message.text.split()[1]
        update_user(telegram_id, 'a_account', a_account)
        bot.reply_to(message, f"Successfully bound account A: {a_account}。")
    except:
        bot.reply_to(message, "Please enter the correct A account, for example: /bind_vaulta_account yourAname")

# /me 查看当前信息（仅限私聊）
@bot.message_handler(commands=['me'])
def handle_me(message):
    if message.chat.type != 'private':
        return
    telegram_id = message.from_user.id
    user = get_user(telegram_id)
    if user:
        conn = sqlite3.connect('telegram_bot.db')
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users WHERE invited_by = ? AND joined_group = 1", (str(telegram_id),))
        invite_count = cursor.fetchone()[0]
        
        cursor.execute('SELECT snapshot_points FROM monthly_snapshot WHERE telegram_id = ?', (telegram_id,))
        row = cursor.fetchone()
        snapshot_points = row[0] if row else 0
        month_points = user[2] - snapshot_points

        conn.close()
        msg = (
           f"Current points: {user[2]}\n"
           f"New points added this month: {month_points}\n"
           f"Biance UID：{user[3] or 'Unbound'}\n"
           f"X account：{user[4] or 'Unbound'}\n"
           f"A account：{user[5] or 'Unbound'}\n"
           f"Number of people successfully invited to join the group: {invite_count}\n"
           f"Invite link: https://t.me/{bot.get_me().username}?start={telegram_id}"
        )

        bot.reply_to(message, msg)
    else:
        bot.reply_to(message, "User information not found, please register using /start first.")

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
        bot.reply_to(message, "📭 You haven't submitted any links yet.")
        return

    binance_links = [link for typ, link in results if typ == "binance"]
    twitter_links = [link for typ, link in results if typ == "twitter"]

    msg = "📑 *The link you submitted is as follows:*\n\n"

    if binance_links:
        msg += "🔗 *Biance Link：*\n" + "\n".join(f"• {l}" for l in binance_links) + "\n\n"
    else:
        msg += "🔗 *Biance Link：*\n（None）\n\n"

    if twitter_links:
        msg += "🧵 *X Link：*\n" + "\n".join(f"• {l}" for l in twitter_links)
    else:
        msg += "🧵 *X Link：*\n（None）"

    bot.reply_to(message, msg, parse_mode="Markdown", disable_web_page_preview=True)

@bot.message_handler(commands=['bind'])
def handle_bind(message):
    if message.chat.type != 'private':
        return
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🔗 Bind Binance UID", callback_data="bind_binance"))
    markup.add(types.InlineKeyboardButton("🧵 Bind X Account", callback_data="bind_x"))
    markup.add(types.InlineKeyboardButton("🅰️ Bind Vaulta Account", callback_data="bind_vaulta"))
    bot.send_message(message.chat.id, "Please select the account type you want to bind: ", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("bind_"))
def handle_bind_callback(call):
    if call.data == "bind_binance":
        bot.send_message(call.message.chat.id, "Please enter the command: /bind_binance Your Binance UID, for example: \n`/bind_binance 12345678`")
    elif call.data == "bind_x":
        bot.send_message(call.message.chat.id, "Please enter the command: /bind_twitter @your X account, for example: \n`/bind_twitter @vaulta_cn`")
    elif call.data == "bind_vaulta":
        bot.send_message(call.message.chat.id, "Please enter the command: /bind_vaulta_account your Vaulta account, for example: \n`/bind_vaulta_account vaultauser`")
    bot.answer_callback_query(call.id)


@bot.message_handler(commands=['get_group_id'])
def handle_get_group_id(message):
    print(f"Received message from group:{message.chat.title}, group ID：{message.chat.id}")
    if message.chat.type in ['group', 'supergroup']:
        bot.reply_to(message, "The group ID is printed in the server log.")
    else:
        bot.reply_to(message, "Please use this command in a group.")


# 每日选择有效签到词，并在群内发布并置顶

def select_daily_signin_word():
    global current_signin_word
    print("[Scheduled task] is executing select_daily_signin_word:", datetime.now())
    if not os.path.exists(SIGNIN_WORDS_FILE):
        print("Sign-in word configuration file not found signin_words.txt")
        return

    with open(SIGNIN_WORDS_FILE, 'r', encoding='utf-8') as f:
        lines = [line.strip() for line in f if line.strip()]

    if not lines:
        print("Sign-in word configuration file is empty")
        return

    current_signin_word = random.choice(lines)
    
    # ✅ 写入临时文件
    with open(TEMP_SIGNIN_FILE, 'w', encoding='utf-8') as f:
        f.write(current_signin_word)

    try:
        sent = bot.send_message(ALLOWED_GROUP_ID, f"📌 Today's sign-in word: \n\n`{current_signin_word}`\n\nPlease send this word in the group to complete the daily sign-in! \n\nUse /signinword to view the current sign-in word\n\nSign in five times in a row within seven days and you will receive 2 extra points", parse_mode="Markdown")
        bot.pin_chat_message(ALLOWED_GROUP_ID, sent.message_id, disable_notification=False)
        threading.Timer(300, lambda: bot.unpin_chat_message(ALLOWED_GROUP_ID, message_id=sent.message_id)).start()
    except Exception as e:
        print("Failed to send sign-in word:", e)

# 群内消息处理：检测是否为当前签到词
@bot.message_handler(func=lambda m: m.chat.type in ['group', 'supergroup'])
def handle_custom_signin_word(message):
    #先检查敏感词
    sensitive_words = load_sensitive_words()
    text = message.text.lower() if message.text else ""
    for word in sensitive_words:
        if word in text:
            try:
                bot.delete_message(message.chat.id, message.message_id)
                warn = bot.send_message(message.chat.id, f"⚠️ User @{message.from_user.username or message.from_user.id} The message has been deleted due to triggering sensitive words.")
                threading.Timer(15, lambda: bot.delete_message(message.chat.id, warn.message_id)).start()
                print(f"⚠️ Sensitive word trigger:{word}，Deleted message from {message.from_user.id} ")
            except Exception as e:
                print(f"❌ Failed to delete sensitive word message: {e}")
            break

    global current_signin_word
    if message.chat.id != ALLOWED_GROUP_ID:
        return
    if not current_signin_word:
        return

    if message.text and message.text.strip().lower() == current_signin_word.lower():
        telegram_id = message.from_user.id
        create_user_if_not_exist(telegram_id)
        update_user(telegram_id, 'joined_group', 1)
        user = get_user(telegram_id)
        now = datetime.now()
        last_signin = user[1]
        if last_signin:
            try:
                last_signin_time = datetime.strptime(last_signin, '%Y-%m-%d %H:%M:%S')
                if now - last_signin_time < timedelta(hours=24):
                    remaining = timedelta(hours=24) - (now - last_signin_time)
                    hours, remainder = divmod(remaining.seconds, 3600)
                    minutes = remainder // 60
                    msg = bot.reply_to(message, f"You have already signed in. Please try again in {hours} hours and {minutes} minutes.")
                    threading.Timer(30, lambda: bot.delete_message(message.chat.id, msg.message_id)).start()
                    return
            except:
                pass
    
        update_user(telegram_id, 'last_signin', now.strftime('%Y-%m-%d %H:%M:%S'))
        new_points = user[2] + 1

        # 记录签到历史（按日期）
        record_signin_history(telegram_id, now.strftime('%Y-%m-%d'))

        # 检查最近7天是否至少有5次
        bonus_text = ""
        today_str = now.strftime('%Y-%m-%d')
        last_bonus_date = user[10]  # last_bonus_date 是表的第11个字段

        if count_signins_last_7_days(telegram_id) >= 5:
            if not last_bonus_date or datetime.strptime(last_bonus_date, "%Y-%m-%d") <= now - timedelta(days=7):
              new_points += 2
              bonus_text = "🎉 Sign in for 5 consecutive days within 7 days and get an extra 2 points!"
              update_user(telegram_id, 'last_bonus_date', today_str)
            else:
              bonus_text = ""

        else:
          bonus_text = ""

        update_user(telegram_id, 'points', new_points)

        msg = bot.reply_to(
           message,
           f"✅ Sign in successfully! You have earned 1 point. Your current total points are {new_points} points\n{bonus_text}"
        )
        threading.Timer(30, lambda: bot.delete_message(message.chat.id, msg.message_id)).start()
        
        print(f"Received group message, group ID: {message.chat.id}, From user: {message.from_user.id}，Message content: {message.text}")
        
        name = message.from_user.first_name or ""
        if message.from_user.last_name:
          name += " " + message.from_user.last_name

        update_user_name_and_custom_id(telegram_id, name.strip())
        

def load_rss_sources(file_path='rss_sources.json'):
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            sources = json.load(f)
            if not isinstance(sources, list):
                raise ValueError("The configuration file is malformed and should be a list.")
            return sources
    except Exception as e:
        print(f"❌ Unable to load RSS configuration file:{e}")
        return []

def fetch_rss_news():
    print("[Scheduled task] is executing fetch_rss_news:", datetime.now())
    feeds = load_rss_sources()
    news_items = []

    for feed_url in feeds:
        try:
            feed = feedparser.parse(feed_url)

            if not feed.entries or not all(hasattr(entry, 'title') and hasattr(entry, 'link') for entry in feed.entries):
                print(f"⚠️ RSS feed is invalid or has no content:{feed_url}")
                continue

            for entry in feed.entries[:5]:
                title = entry.title
                link = entry.link

                translated_title = title  # 如果翻译失败就保留原文

                news_items.append(f"• [{translated_title}]({link})")

        except Exception as e:
            print(f"❌ Fetch failed: {feed_url} Error: {e}")
            continue

    news_items = news_items[:8]

    if news_items:
        message = "📰 *Today’s crypto news highlights:*\n\n" + "\n".join(news_items)
        try:
            bot.send_message(ALLOWED_GROUP_ID, message, parse_mode='Markdown', disable_web_page_preview=True)
        except:
            print("Failed to send encrypted news")
    else:
        print("❌ Unable to fetch news, please try again later.")

schedule.every().day.at("09:00").do(fetch_rss_news)
schedule.every().day.at("09:05").do(select_daily_signin_word)

# 启动时执行一次
if not os.path.exists(TEMP_SIGNIN_FILE):
    fetch_rss_news()
    select_daily_signin_word()
else:
    with open(TEMP_SIGNIN_FILE, 'r', encoding='utf-8') as f:
        current_signin_word = f.read().strip()
        print(f"[Startup] Sign-in words loaded from temporary file:{current_signin_word}")


# ✅ 新增：独立线程运行定时任务
def run_schedule():
    while True:
        schedule.run_pending()
        time.sleep(5)

# 启动调度线程
threading.Thread(target=run_schedule, daemon=True).start()

bot.set_my_commands([
    telebot.types.BotCommand("start", "🔰"),
    telebot.types.BotCommand("me", "📊"),
    telebot.types.BotCommand("bind", "🔗"),
    telebot.types.BotCommand("invites", "📨"),
    telebot.types.BotCommand("submit", "✅"),
    telebot.types.BotCommand("quiz", "🧩"),
])


# 启动 Telegram Bot（主线程）
print("Bot is running...")
try:
    bot.polling(none_stop=True)
except Exception as e:
    print("Polling Error:", e)