import os
import asyncio
import random
from flask import Flask, request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    CallbackQueryHandler,
    ConversationHandler,
    MessageHandler,
    filters,
)

app = Flask(__name__)

# === KONFIGURASI ===
TOKEN = os.getenv("BOT_TOKEN")
PUBLIC_URL = os.getenv("PUBLIC_URL")

# === RAM STORAGE (HILANG SAAT RESTART) ===
users = {}
queues = {
    "male": set(),
    "female": set(),
    "random": set()
}

GENDER, AGE = range(2)

# === LOGIC ===
def create_user_if_not_exists(user_id):
    if user_id not in users:
        users[user_id] = {
            "verified": False, "partner": None, "gender": None, 
            "age": None, "searching": False
        }

def find_partner(user_id, mode):
    user_data = users.get(user_id)
    my_gender = user_data.get("gender")
    
    target_q = "random"
    if mode == "cari_doi":
        target_q = "female" if my_gender == "Laki-laki" else "male"
    
    candidates = list(queues[target_q])
    if user_id in candidates: candidates.remove(user_id)
    
    if not candidates: return None
    
    partner_id = random.choice(candidates)
    queues[target_q].remove(partner_id)
    return partner_id

def add_to_queue(user_id, mode):
    user_data = users.get(user_id)
    if mode == "find":
        queues["random"].add(user_id)
    elif mode == "cari_doi":
        q = "male" if user_data.get("gender") == "Laki-laki" else "female"
        queues[q].add(user_id)

def remove_from_queues(user_id):
    if user_id in queues["random"]: queues["random"].discard(user_id)
    if user_id in queues["male"]: queues["male"].discard(user_id)
    if user_id in queues["female"]: queues["female"].discard(user_id)

# === HANDLERS ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    create_user_if_not_exists(user_id)
    if users[user_id].get("verified"):
        await show_menu(update)
        return ConversationHandler.END
    
    kb = [[InlineKeyboardButton("Laki-laki", callback_data="male")],
          [InlineKeyboardButton("Perempuan", callback_data="female")]]
    await update.message.reply_text("👋 Pilih gender:", reply_markup=InlineKeyboardMarkup(kb))
    return GENDER

async def show_menu(update: Update):
    kb = [
        [InlineKeyboardButton("🔍 Cari Teman", callback_data="find")],
        [InlineKeyboardButton("💘 Cari Doi", callback_data="cari_doi")],
        [InlineKeyboardButton("✏️ Ubah Profil", callback_data="ubah_profil")]
    ]
    if update.callback_query:
        await update.callback_query.message.reply_text("✅ Menu Utama:", reply_markup=InlineKeyboardMarkup(kb))
    else:
        await update.message.reply_text("✅ Menu Utama:", reply_markup=InlineKeyboardMarkup(kb))

async def handle_gender(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    create_user_if_not_exists(uid)
    users[uid]["gender"] = "Laki-laki" if q.data == "male" else "Perempuan"
    await q.edit_message_text("🎂 Masukkan usia (angka):")
    return AGE

async def handle_age(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    text = update.message.text.strip()
    if not text.isdigit():
        await update.message.reply_text("⚠️ Angka saja.")
        return AGE
    users[uid]["age"] = int(text)
    users[uid]["verified"] = True
    await update.message.reply_text("✅ Disimpan!")
    await show_menu(update)
    return ConversationHandler.END

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    create_user_if_not_exists(uid)
    
    mode = q.data
    if mode == "ubah_profil": return

    pid = find_partner(uid, mode)
    if pid:
        users[uid]["partner"], users[uid]["searching"] = pid, False
        users[pid]["partner"], users[pid]["searching"] = uid, False
        remove_from_queues(uid)
        remove_from_queues(pid)
        
        msg = "💬 Partner Found! /stop to end."
        await q.edit_message_text(msg)
        try: await context.bot.send_message(pid, msg)
        except: pass
    else:
        add_to_queue(uid, mode)
        users[uid]["searching"] = True
        await q.edit_message_text("⏳ Searching...")

async def relay(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    create_user_if_not_exists(uid)
    pid = users[uid].get("partner")
    
    if pid:
        try: await context.bot.send_message(pid, update.message.text)
        except: 
            await update.message.reply_text("❌ Partner lost.")
            await stop_chat(update, context)
    elif users[uid].get("searching"):
        await update.message.reply_text("⏳ Searching...")
    else:
        await update.message.reply_text("⚠️ Klik /start")

async def stop_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    create_user_if_not_exists(uid)
    pid = users[uid].get("partner")
    
    users[uid]["partner"], users[uid]["searching"] = None, False
    remove_from_queues(uid)
    
    if pid and pid in users:
        users[pid]["partner"], users[pid]["searching"] = None, False
        try: await context.bot.send_message(pid, "❌ Chat ended.")
        except: pass
            
    await update.message.reply_text("🔴 Stopped.")
    await show_menu(update)

# === APP SETUP ===
bot_app = ApplicationBuilder().token(TOKEN).build()
conv = ConversationHandler(
    entry_points=[CommandHandler("start", start), CallbackQueryHandler(handle_gender, pattern="^ubah_profil$")],
    states={GENDER:[CallbackQueryHandler(handle_gender)], AGE:[MessageHandler(filters.TEXT, handle_age)]},
    fallbacks=[CommandHandler("start", start)]
)
bot_app.add_handler(conv)
bot_app.add_handler(CommandHandler("stop", stop_chat))
bot_app.add_handler(CallbackQueryHandler(button_handler, pattern="^(find|cari_doi)$"))
bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, relay))

@app.route('/webhook', methods=['POST'])
def webhook():
    if request.method == "POST":
        update = Update.de_json(request.get_json(force=True), bot_app.bot)
        asyncio.run(bot_app.process_update(update))
        return "OK"
    return "Bot Running"

@app.route('/')
def index():
    if not PUBLIC_URL: return "❌ No PUBLIC_URL found."
    wh = f"{PUBLIC_URL}/webhook"
    asyncio.run(bot_app.bot.set_webhook(wh))
    return f"✅ Webhook Set: {wh}"

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
