🤖 Vaulta Points Bot – User Guide
Vaulta Bot is a Telegram-based points management bot designed to support daily check-ins, referral tracking, article submissions, account binding, quiz activities, and more.

🧾 Feature Overview
Feature	Description
✅ Daily Check-in	Send the daily check-in word in the group to earn 1 point (once per 24 hours). If you check in 5 out of 7 consecutive days, you'll earn an extra 2 points.
🧩 Quiz Activities	Admins can post multiple-choice quizzes. Each user can answer only once per quiz. Correct answers earn +1 point.
📨 Referral System	Use your personal invite link to bring new members into the group. Earn 3 points per successful invite.
🔗 Account Binding	Bind your Binance UID, X (Twitter) handle, and Vaulta account for task participation.
📤 Submit Tasks	Submit Binance or X (Twitter) article links in private chat to earn points.
📊 Points Inquiry	View your current score, this month’s points, bound accounts, invite data, and more.
🏆 Ranking	Use /ranking in the group to see the current top 20 leaderboard.

📌 How to Use
🔰 Start the Bot
Send /start in a private chat to register and receive your personal invite link.
An interactive menu will appear with available commands.

✅ Daily Check-in (Group Only)
The bot will post the daily check-in word each morning

Send the word in the group chat to successfully check-in

Use /signinword to view the current word if you missed it

🔗 Bind Accounts (Private Chat Only)
/bind_binance 12345678 – bind your Binance UID

/bind_twitter @yourhandle – bind your X (Twitter) handle

/bind_vaulta_account vaultaname – bind your Vaulta account

Or use the /bind command for buttons

🧩 Quiz Activity (Group Only)
Admins post questions using /quiz_send.
Answer using the provided buttons – one attempt per user per quiz.
Correct answer earns 1 point.

📤 Submit Tasks (Private Chat Only)
Send /submit and choose between Binance or X submission

Enter your article link as prompted

Each user may only submit each link once

Use /my_submissions to view your submitted links

🧮 Query Your Info
/me – view your current and monthly points, account bindings, referral count

/invites – view your total successful invites and personal invite link

/ranking – group command to show top 20 monthly leaderboard

🔐 Admin Commands (Restricted to Whitelist)
Command	Description
/quiz_send {...}	Manually send a quiz (in JSON format) or randomly pull from the quiz bank
/export_submissions	Export all submitted Binance and Twitter links
/export_users	Export all user info and points
/add_sensitive word	Add a keyword to the sensitive word list (automatically deletes messages that contain it)

🧠 Technical Notes
All data is stored in a local SQLite database (telegram_bot.db)

Monthly snapshots are automatically saved to calculate monthly points

Task system, quiz bank, and check-in words are configured via local files

Button-based UI improves user interaction experience
