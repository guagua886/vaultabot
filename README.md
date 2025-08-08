# Vaulta Telegram Points Bot

A production-ready Telegram bot that powers daily sign-ins, points, red packets, quizzes, link submissions, activity rankings, price tickers, RSS crypto news, feedback collection, user search, and more — with **multi-language (i18n)** support and **scheduled jobs**.

> Built on [pyTelegramBotAPI (`telebot`)](https://pypi.org/project/pyTelegramBotAPI/) and SQLite.

---

## ✨ Features

- **Daily Sign-in** with a rotating “sign-in word” posted to the group and soft pin (auto-unpin after 5 minutes).
- **Points System**: total points & unlocked points (transferable). 7-in-7 streak bonus (+2).
- **Red Pack (points red pack)**: group command to send a points red packet. Unclaimed remainder auto-refunds after 24h via a standalone script.
- **Quizzes**: admins post multiple-choice questions; correct answers +1.
- **Invites**: each user has a referral link; inviter gets +3 when invitee registers and joins.
- **Submissions**: users can submit Binance and Twitter(X) links; anti-duplicate storage.
- **Activity Ranking**: ranks message senders by month (only users above a minimum points threshold; admins excluded).
- **Price Ticker**: Binance spot prices, daily open cache, and periodic broadcasts.
- **RSS Crypto News**: fetch selected RSS feeds and post highlights (auto-translate unless language is `en`).
- **Feedback**: collects feedback into `feedback.csv` and supports export.
- **Sensitive Words**: delete matched messages and warn publicly; words are editable.
- **Exports**: CSV export for users, submissions, and feedback.
- **i18n**: all user-facing texts via `i18n.json`; switch language in `config.json`.
- **Admin Tooling**: batch add points from CSV, search users by fuzzy name/custom id, add points, etc.

---

## 🧱 Project Structure (key files)

```
vaulta_bot.py                    # Main bot with commands, schedulers, i18n
refund_expired_red_packets.py    # Standalone script to refund expired red packets
config.json                      # Main config (token, admins, group, language, etc.)
i18n.json                        # Translations for all texts
signin_words.txt                 # Candidate sign-in words (one per line)
rss_sources.json                 # RSS feed URLs list
watchlist.json                   # Symbols to watch for price broadcasts (e.g., ["BTCUSDT","ETHUSDT"])
quiz_bank.json                   # Quiz questions (optional)
sensitive_words.txt              # Sensitive words list (optional)
telegram_bot.db                  # SQLite database (auto-created)
group_messages.log               # Group message log for activity ranking
open_prices.json                 # Daily open price cache (auto-managed)
feedback.csv                     # Feedback storage (auto-created)
```

---

## 🚀 Quick Start

### 1) Requirements
- Python **3.9+** (3.10/3.11 recommended)
- A Telegram **Bot Token** via **@BotFather**
- Server/network that can reach Telegram
- SQLite (bundled with Python)

### 2) Install
```bash
# (optional) create venv
python3 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

pip install -U pytelegrambotapi feedparser schedule googletrans==4.0.0-rc1 requests
```

### 3) Prepare Configs
Create **`config.json`** at project root:

```jsonc
{
  "BOT_TOKEN": "YOUR_BOT_TOKEN",
  "ADMIN_IDS": [123456789, 222222222],
  "ALLOWED_GROUP_ID": -1001234567890,
  "MIN_ACTIVE_POINTS": 10,
  "LANGUAGE": "en"
}
```
- **BOT_TOKEN**: from @BotFather
- **ADMIN_IDS**: array of Telegram IDs with admin privileges
- **ALLOWED_GROUP_ID**: the **only** group where group-only features work (supergroup id is negative)
- **MIN_ACTIVE_POINTS**: users must have at least this much total points to appear in `/active`
- **LANGUAGE**: language key in `i18n.json` (e.g., `en`, `zh`, …)

Create **`i18n.json`** (minimal skeleton; extend as needed). The keys must match code calls like `get_text("...")`:
```jsonc
{
  "en": {
    "cmd_start": "Start",
    "cmd_me": "Profile",
    "cmd_bind": "Bind",
    "cmd_invites": "Invites",
    "cmd_submit": "Submit",
    "cmd_quiz": "Quiz",
    "cmd_price": "Price",
    "cmd_feedback": "Feedback",
    "cmd_unlock_points": "Unlock Points",
    "cmd_transfer": "Transfer",
    "cmd_transfers": "Transfers",
    "cmd_signinword": "Sign-in Word",
    "cmd_ranking": "Ranking",
    "cmd_active": "Active",
    "cmd_register": "Register",
    "cmd_help": "Help",

    "welcome_new_member": "👋 Welcome {name}! Use /signinword to see today's word and earn points.",
    "welcome_start": "Welcome to the points bot!\nJoin the group and send the daily sign-in word to earn points.\n\n🔗 Your invite link:\n{invite_link}",

    "redpack_usage": "Usage: /hongbao <total_points> <count> (or /redpack <total_points> <count>)",
    "redpack_positive_required": "Total points and count must be positive integers.",
    "redpack_insufficient_unlocked": "Not enough unlocked points to send a red packet.",
    "redpack_btn_claim": "🧧 Claim now",
    "redpack_announce": "🎁 Red packet! {name} (@{username} / {telegram_id}) sent {count} shares, total {total_points} pts.",
    "redpack_already_claimed": "You have already claimed this red packet.",
    "redpack_not_exist": "Red packet does not exist or was withdrawn.",
    "redpack_expired": "Red packet expired (24h).",
    "redpack_empty": "This red packet has been fully claimed.",
    "redpack_claim_broadcast": "🎉 {name} (@{username} / {telegram_id}) claimed {amount} pts!",

    "help_header": "*Available commands*",
    "help_user_section": "- /start, /me, /bind, /invites, /submit, /price, /feedback, /unlock_points, /transfer, /transfers, /signinword, /ranking, /active, /my_submissions",
    "help_admin_section": "\n*Admin*: /hongbao, /redpack, /quiz_send, /add_points, /export_users, /export_submissions, /export_feedback, /add_sensitive, /search_user, /get_group_id",
    "help_feedback_footer": "\nIf you need anything else, send /feedback <your message>."
  }
}
```

Create **`signin_words.txt`** (one word/phrase per line) and **`rss_sources.json`**:
```text
gm
good luck
hello world
```
```json
[
  "https://www.coindesk.com/arc/outboundfeeds/rss/",
  "https://cointelegraph.com/rss"
]
```

(Optional) **`watchlist.json`**:
```json
["BTCUSDT", "ETHUSDT"]
```

(Optional) **`quiz_bank.json`**:
```json
[
  {"question":"BTC max supply?","options":["21M","100M","Infinite"],"answer":0}
]
```

### 4) Run
```bash
python vaulta_bot.py
```

First run will create `telegram_bot.db` and tables automatically.

---

## 🧩 Commands

### For Everyone (mostly in **private** unless stated)
- `/start` — register, set name & username, and get your invite link
- `/me` — show profile (total, unlocked, month points, bindings, invite stats)
- `/bind` — get buttons to bind Binance UID / X handle / Vaulta account
  - `/bind_binance <UID>`
  - `/bind_twitter @handle`
  - `/bind_vaulta_account <account>`
- `/invites` — show how many users you invited (who also joined the group) and your invite link
- `/submit` — choose to submit **Binance** or **Twitter(X)** link
- `/my_submissions` — list your submitted links
- `/price <SYMBOL>` — e.g., `/price BTC`
- `/unlock_points <amount>` — move **total** → **unlocked** points
- `/transfer` — guided transfer (asks for recipient ID then amount)
- `/transfer_points <recipient_id> <amount>` — one-shot transfer
- `/transfers` — list recent incoming/outgoing transfers (with names/@custom_ids)
- `/signinword` — (group-only) show today’s word
- `/ranking` — monthly points leaderboard (current month delta)
- `/active` — activity leaderboard for this month (message count, users above `MIN_ACTIVE_POINTS` only)
- `/register` — get registration PDFs (wallet guides)
- `/feedback <message>` — send feedback (stored in CSV)

### Admin-only
- `/hongbao <total_points> <count>` or `/redpack ...` — send a red packet (deducts **unlocked** points)
- `/quiz_send` — post a quiz (or `/quiz_send {"question":"...","options":["A","B"],"answer":0}`)
- `/add_points <telegram_id> <amount>` — add points; user gets a DM notification
- `/export_users` — CSV
- `/export_submissions` — CSV
- `/export_feedback` — CSV
- `/add_sensitive <word>` — append to `sensitive_words.txt`
- `/search_user <keyword>` — fuzzy search by name/custom id (case-insensitive), lists top 20
- `/get_group_id` — print group id to server logs

> Many group features only respond in **ALLOWED_GROUP_ID** to avoid cross-group triggers.

---

## ⏱️ Schedules (inside `vaulta_bot.py`)

- **09:00** — fetch & post RSS crypto news
- **09:05** — select & post today’s sign-in word (pin for 5 minutes)
- **00:00** — cache daily open prices to `open_prices.json`
- **Every 2 hours** — broadcast price changes

> All `schedule` jobs run in a dedicated background thread.

---

## 🧧 Red Packet Auto-Refund

Unclaimed red packet remainder auto-refunds to sender’s **unlocked points** after **24 hours**.

Run manually:
```bash
python refund_expired_red_packets.py
```

Recommended **crontab** (every hour at minute 5):
```bash
5 * * * * /usr/bin/env bash -lc 'cd /path/to/project && . .venv/bin/activate && python refund_expired_red_packets.py >> refund.log 2>&1'
```

---

## 🗄️ Database (SQLite)

Tables created automatically (simplified list):
- `users(telegram_id, last_signin, points, unlocked_points, name, custom_id, invited_by, joined_group, ...)`
- `signin_history(telegram_id, date)`
- `quiz_answers(quiz_id, telegram_id)`
- `submissions(telegram_id, type, link)`
- `transfers(id, sender_id, recipient_id, amount, timestamp)`
- `red_packets(id, sender_id, total_points, count, created_at, remaining_points, claimed_count, expired)`
- `red_packet_claims(packet_id, telegram_id, claimed_points)`
- `monthly_snapshot(telegram_id, month, snapshot_points)`

---

## 🪵 Logs & Data Files

- `group_messages.log` — group message log for `/active`
- `admin_actions.log` — admin actions (add points, etc.)
- `feedback.csv` — feedback storage
- `open_prices.json` — daily open price cache
- `temp_signin_word.txt` — last posted sign-in word (for restarts)

---

## 🔒 Recommendations

- Keep `config.json` out of public repos.
- Limit `ADMIN_IDS` to trusted accounts.
- If you need proxies/webhooks, adjust networking accordingly (bot currently uses long polling).

---

## 🛠️ Deployment

### Option A: systemd (Linux)
Create `/etc/systemd/system/vaulta-bot.service`:
```ini
[Unit]
Description=Vaulta Telegram Points Bot
After=network.target

[Service]
WorkingDirectory=/path/to/project
ExecStart=/path/to/project/.venv/bin/python /path/to/project/vaulta_bot.py
Restart=always
RestartSec=5
User=ubuntu
Environment="PYTHONUNBUFFERED=1"

[Install]
WantedBy=multi-user.target
```
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now vaulta-bot
sudo systemctl status vaulta-bot -n 100
```

### Option B: PM2 (Node-based process manager)
```bash
npm i -g pm2
pm2 start "python vaulta_bot.py" --name vaulta-bot
pm2 logs vaulta-bot
pm2 save
pm2 startup
```

---

## 🧩 Troubleshooting

- **`database is locked`**: avoid heavy concurrent writes; stagger cron; or consider PostgreSQL if your workload grows.
- **Group commands not responding**: ensure the message is in **ALLOWED_GROUP_ID** and the bot has permission to delete/pin messages.
- **`LANGUAGE` not taking effect**: confirm keys exist in `i18n.json`. Missing keys will display `[your_key]` to help you spot gaps.
- **Price ticker empty**: check Binance connectivity and `watchlist.json`. `open_prices.json` is created at 00:00 and on first run.
- **RSS empty**: validate `rss_sources.json` feeds are reachable.
- **Sign-in word not set**: wait until 09:05 or restart to trigger an immediate selection (unless a cached `temp_signin_word.txt` exists).

---

## 🤝 Contributing

PRs welcome! Please avoid committing secrets. For new features, add corresponding i18n keys to `i18n.json` and reuse existing DB patterns.

---

## 📜 License

MIT
