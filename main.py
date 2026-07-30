import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
import sqlite3
import threading
import time
import requests
import json
import flask

# ----------------- CONFIGURATION -----------------
TOKEN = "8069167650:AAGyWefpp8zfjDFufyaPnbc6rUrs-erTlfc"
ADMIN_IDS = [8053042225]  # Apna Telegram Admin User ID yahan daalein
MINI_APP_URL = "https://rkg26176.github.io/gbx_learning_bot/"

bot = telebot.TeleBot(TOKEN)
app = flask.Flask(__name__)

DB_NAME = "bot_panel_database.db"
db_lock = threading.Lock()

# Global state for broadcasting
broadcast_state = {
    "active": False,
    "type": None,
    "content": None,
    "caption": None,
    "reply_markup": None
}

# ----------------- DATABASE SETUP -----------------
def init_db():
    with db_lock:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                is_vip INTEGER DEFAULT 0,
                referred_by INTEGER,
                referral_count INTEGER DEFAULT 0
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        ''')
        conn.commit()
        conn.close()

init_db()

def get_db_connection():
    conn = sqlite3.connect(DB_NAME, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

# ----------------- DATABASE HELPERS -----------------
def add_user(user_id, username, first_name, referred_by=None):
    with db_lock:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        user = cursor.fetchone()
        
        if not user:
            cursor.execute("""
                INSERT INTO users (user_id, username, first_name, referred_by, is_vip, referral_count)
                VALUES (?, ?, ?, 0, 0, 0)
            """, (user_id, username, first_name))
            
            if referred_by and referred_by != user_id:
                cursor.execute("SELECT * FROM users WHERE user_id = ?", (referred_by,))
                ref_user = cursor.fetchone()
                if ref_user:
                    cursor.execute("UPDATE users SET referral_count = referral_count + 1 WHERE user_id = ?", (referred_by,))
                    cursor.execute("UPDATE users SET referred_by = ? WHERE user_id = ?", (referred_by, user_id))
                    
                    # Check if referrer reached 5 referrals to unlock VIP automatically
                    cursor.execute("SELECT referral_count FROM users WHERE user_id = ?", (referred_by,))
                    new_count = cursor.fetchone()["referral_count"]
                    if new_count >= 5:
                        cursor.execute("UPDATE users SET is_vip = 1 WHERE user_id = ?", (referred_by,))
                        try:
                            bot.send_message(referred_by, "🎉 **Congratulations!** You have successfully completed 5 referrals and your VIP Access has been unlocked automatically!")
                        except:
                            pass
        conn.commit()
        conn.close()

def is_user_vip(user_id):
    if user_id in ADMIN_IDS:
        return True
    with db_lock:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT is_vip FROM users WHERE user_id = ?", (user_id,))
        res = cursor.fetchone()
        conn.close()
        return res['is_vip'] == 1 if res else False

def set_vip_status(user_id, status: int):
    with db_lock:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET is_vip = ? WHERE user_id = ?", (status, user_id))
        conn.commit()
        conn.close()

def get_all_users():
    with db_lock:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM users")
        users = [row['user_id'] for row in cursor.fetchall()]
        conn.close()
        return users

def get_user_stats(user_id):
    with db_lock:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        user = cursor.fetchone()
        conn.close()
        return user

# ----------------- KEYBOARDS -----------------
def main_menu_keyboard(user_id):
    markup = InlineKeyboardMarkup(row_width=1)
    
    if is_user_vip(user_id):
        web_app = WebAppInfo(url=MINI_APP_URL)
        markup.add(InlineKeyboardButton("🚀 Open VIP Mini App", web_app=web_app))
    else:
        markup.add(InlineKeyboardButton("🔒 Open VIP Mini App (Locked)", callback_data="locked_panel"))
        
    markup.add(
        InlineKeyboardButton("👤 My Profile & Referrals", callback_data="my_profile"),
        InlineKeyboardButton("💎 Unlock VIP Access (₹79 / 5 Referrals)", callback_data="unlock_info")
    )
    return markup

def admin_menu_keyboard():
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("👥 User List & Management", callback_data="admin_userlist"),
        InlineKeyboardButton("📢 Broadcast Message", callback_data="admin_broadcast"),
        InlineKeyboardButton("➕ Direct Add VIP", callback_data="admin_add_vip"),
        InlineKeyboardButton("➖ Direct Remove VIP", callback_data="admin_remove_vip"),
        InlineKeyboardButton("📊 Bot Stats", callback_data="admin_stats"),
        InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu")
    )
    return markup

# ----------------- BOT HANDLERS -----------------
@bot.message_handler(commands=['start'])
def handle_start(message):
    user_id = message.from_user.id
    username = message.from_user.username or ""
    first_name = message.from_user.first_name or ""
    
    args = message.text.split()
    ref_id = None
    if len(args) > 1 and args[1].isdigit():
        ref_id = int(args[1])
        
    add_user(user_id, username, first_name, ref_id)
    
    welcome_text = (
        f"👋 Hello **{first_name}**!\n\n"
        f"Welcome to **GBX Learning Hub** Bot 🚀\n"
        f"Access premium educational resources and high-speed tools instantly.\n\n"
        f"👇 Choose an option below:"
    )
    
    bot.send_message(message.chat.id, welcome_text, parse_mode="Markdown", reply_markup=main_menu_keyboard(user_id))

@bot.message_handler(commands=['admin'])
def handle_admin(message):
    if message.from_user.id not in ADMIN_IDS:
        bot.send_message(message.chat.id, "❌ You are not authorized to use this command.")
        return
    bot.send_message(message.chat.id, "👑 **Admin Control Panel**", parse_mode="Markdown", reply_markup=admin_menu_keyboard())

@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    user_id = call.from_user.id
    data = call.data
    
    if data == "main_menu":
        try:
            bot.edit_message_text("👋 Welcome back to Main Menu:", call.message.chat.id, call.message.message_id, reply_markup=main_menu_keyboard(user_id))
        except:
            bot.send_message(call.message.chat.id, "👋 Welcome back to Main Menu:", reply_markup=main_menu_keyboard(user_id))
            
    elif data == "locked_panel":
        bot.answer_callback_query(call.id, "❌ VIP Mini App is locked! Complete 5 referrals or pay ₹79 to unlock.", show_alert=True)
        
    elif data == "unlock_info":
        bot_info = bot.get_me()
        bot_username = bot_info.username
        ref_link = f"https://t.me/{bot_username}?start={user_id}"
        
        info_text = (
            f"💎 **How to Unlock VIP Access:**\n\n"
            f"You have two simple ways to unlock the VIP Mini App:\n\n"
            f"1️⃣ **Referral Program:** Share your referral link with friends. When **5 users** start the bot using your link, VIP unlocks automatically!\n"
            f"🔗 Your Invite Link:\n`{ref_link}`\n\n"
            f"2️⃣ **Instant Purchase:** Pay a fixed price of **₹79** and get instant lifetime VIP access.\n"
            f"💳 Contact Admin to complete your payment!"
        )
        
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🔙 Back", callback_data="main_menu"))
        try:
            bot.edit_message_text(info_text, call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)
        except:
            bot.send_message(call.message.chat.id, info_text, parse_mode="Markdown", reply_markup=markup)
            
    elif data == "my_profile":
        user = get_user_stats(user_id)
        if user:
            is_vip_status = "✅ Active (VIP)" if is_user_vip(user_id) else "❌ Inactive (Free)"
            ref_count = user['referral_count']
            bot_info = bot.get_me()
            ref_link = f"https://t.me/{bot_info.username}?start={user_id}"
            
            profile_text = (
                f"👤 **Your Profile Details:**\n\n"
                f"🆔 **User ID:** `{user_id}`\n"
                f"👤 **Name:** {user['first_name']}\n"
                f"⚡ **VIP Status:** {is_vip_status}\n"
                f"👥 **Total Referrals:** {ref_count} / 5\n\n"
                f"🔗 **Your Referral Link:**\n`{ref_link}`"
            )
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("🔙 Back", callback_data="main_menu"))
            try:
                bot.edit_message_text(profile_text, call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)
            except:
                bot.send_message(call.message.chat.id, profile_text, parse_mode="Markdown", reply_markup=markup)

    # ADMIN CALLBACKS
    elif data.startswith("admin_"):
        if user_id not in ADMIN_IDS:
            bot.answer_callback_query(call.id, "❌ Access Denied!", show_alert=True)
            return
            
        if data == "admin_stats":
            users = get_all_users()
            total_users = len(users)
            vip_users = sum(1 for u in users if is_user_vip(u))
            
            stats_text = (
                f"📊 **Bot Statistics:**\n\n"
                f"👥 Total Users: `{total_users}`\n"
                f"💎 VIP Users: `{vip_users}`\n"
                f"👤 Free Users: `{total_users - vip_users}`"
            )
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("🔙 Back to Admin", callback_data="admin_back"))
            bot.edit_message_text(stats_text, call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)
            
        elif data == "admin_userlist":
            users = get_all_users()
            vip_list = [str(u) for u in users if is_user_vip(u) and u not in ADMIN_IDS]
            normal_list = [str(u) for u in users if not is_user_vip(u)]
            
            list_text = (
                f"📋 **All Registered Users List**\n\n"
                f"🟢 **1. Normal / Active Users ({len(normal_list)}):**\n"
                f"{', '.join(normal_list[:20]) if normal_list else 'Koi normal user nahi hai.'}\n\n"
                f"⭐ **2. VIP / Mini Web Unlocked Users ({len(vip_list)}):**\n"
                f"{', '.join(vip_list) if vip_list else 'Koi extra VIP user nahi hai.'}"
            )
            markup = InlineKeyboardMarkup()
            markup.add(
                InlineKeyboardButton("➕ Direct Add VIP", callback_data="admin_add_vip"),
                InlineKeyboardButton("➖ Direct Remove VIP", callback_data="admin_remove_vip"),
                InlineKeyboardButton("🔙 Back to Admin", callback_data="admin_back")
            )
            bot.edit_message_text(list_text, call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)
            
        elif data == "admin_add_vip":
            msg = bot.send_message(call.message.chat.id, "✍️ Please send the **User ID** whom you want to make VIP:\n(Cancel karne ke liye `/cancel` likhein)")
            bot.register_next_step_handler(msg, process_add_vip)
            
        elif data == "admin_remove_vip":
            msg = bot.send_message(call.message.chat.id, "✍️ Please send the **User ID** from whom you want to remove VIP:\n(Cancel karne ke liye `/cancel` likhein)")
            bot.register_next_step_handler(msg, process_remove_vip)
            
        elif data == "admin_broadcast":
            msg = bot.send_message(call.message.chat.id, "📢 Ab aap jo bhi message (Text, Photo, Video, Sticker, Link, Forward) bhejenge, vah sabhi active users ke paas chala jayega.\n\n❌ Radd karne ke liye `/cancel` likhein.")
            bot.register_next_step_handler(msg, process_broadcast_input)
            
        elif data == "admin_back":
            bot.edit_message_text(call.message.chat.id, "👑 **Admin Control Panel**", call.message.message_id, parse_mode="Markdown", reply_markup=admin_menu_keyboard())

# ----------------- ADMIN ACTIONS PROCESSORS -----------------
def process_add_vip(message):
    if message.text and message.text.strip() == "/cancel":
        bot.send_message(message.chat.id, "❌ Action cancelled.", reply_markup=admin_menu_keyboard())
        return
        
    try:
        target_id = int(message.text.strip())
        set_vip_status(target_id, 1)
        bot.send_message(message.chat.id, f"✅ User `{target_id}` has been successfully upgraded to **VIP**!", parse_mode="Markdown", reply_markup=admin_menu_keyboard())
        try:
            bot.send_message(target_id, "🎉 **Good News!** Admin has directly unlocked your VIP Access for the Mini App!")
        except:
            pass
    except ValueError:
        bot.send_message(message.chat.id, "❌ Invalid User ID! Please send a valid numeric ID.", reply_markup=admin_menu_keyboard())

def process_remove_vip(message):
    if message.text and message.text.strip() == "/cancel":
        bot.send_message(message.chat.id, "❌ Action cancelled.", reply_markup=admin_menu_keyboard())
        return
        
    try:
        target_id = int(message.text.strip())
        set_vip_status(target_id, 0)
        bot.send_message(message.chat.id, f"✅ User `{target_id}` VIP Access has been removed.", parse_mode="Markdown", reply_markup=admin_menu_keyboard())
        try:
            bot.send_message(target_id, "⚠️ Your VIP Access has been revoked by the admin.")
        except:
            pass
    except ValueError:
        bot.send_message(message.chat.id, "❌ Invalid User ID! Please send a valid numeric ID.", reply_markup=admin_menu_keyboard())

def process_broadcast_input(message):
    if message.text and message.text.strip() == "/cancel":
        bot.send_message(message.chat.id, "❌ Broadcast cancelled.", reply_markup=admin_menu_keyboard())
        return
        
    users = get_all_users()
    success = 0
    failed = 0
    
    status_msg = bot.send_message(message.chat.id, "🚀 Broadcasting started...")
    
    for uid in users:
        try:
            bot.copy_message(chat_id=uid, from_chat_id=message.chat.id, message_id=message.message_id)
            success += 1
        except:
            failed += 1
            
    bot.edit_message_text(f"✅ **Broadcast Completed!**\n\nSuccess: {success} users\nFailed: {failed} users", message.chat.id, status_msg.message_id, parse_mode="Markdown")

# ----------------- FLASK WEB SERVER FOR RAILWAY -----------------
@app.route('/')
def index():
    return "GBX Learning Hub Bot is running live!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

# ----------------- MAIN RUNNER -----------------
if __name__ == "__main__":
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()
    
    print("Bot is starting polling...")
    bot.infinity_polling(skip_pending=True)
  
