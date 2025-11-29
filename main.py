import os
import json
import asyncio
import redis
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
from telegram.error import Forbidden

# === KONFIGURASI RAILWAY ===
app = Flask(__name__)

# Ambil Variabel dari Railway
TOKEN = os.getenv("BOT_TOKEN")
REDIS_URL = os.getenv("REDIS_URL")
PUBLIC_URL = os.getenv("PUBLIC_URL") # Domain dari Railway (https://xxx.railway.app)

# Cek koneksi Redis
if not REDIS_URL:
    print("⚠️ WARNING: REDIS_URL tidak ditemukan. Bot mungkin error.")
    r = None
else:
    r = redis.from_url(REDIS_URL, decode_responses=True)

# States Conversation
GENDER, AGE = range(2)

# === DATABASE FUNCTIONS (REDIS) ===
# Kita pakai Redis agar data aman walaupun server restart

def get_user(user_id):
    if not r: return {}
    data = r.get(f"user:{user_id}")
    return json.loads(data) if data else None

def save_user(user_id, data):
    if r: r.set(f"user:{user_id}", json.dumps(data))

def create_user_if_not_exists(user_id):
    if r and not r.exists(f"user:{user_id}"):
        default_data = {
            "verified": False, "partner": None, "gender": None, 
            "age": None, "searching": False
        }
        save_user(user_id, default_data)

# === LOGIKA MATCHMAKING ===

def find_partner(user_id, mode):
    if not r: return None
    user_data = get_user(user_id)
    my_gender = user_data.get("gender")
    
    target_queue = "queue:random"
    if mode == "cari_doi":
        target_queue = "queue:female" if my_gender == "Laki-laki" else "queue:male"
    
    # Ambil user dari antrean (SPOP = Set Pop / Ambil Acak)
    partner_id = r.spop(target_queue)
    
    # Cegah match dengan diri sendiri
    if partner_id and int(partner_id) == user_id:
        partner_id = r.spop(target_queue)
        
    return int(partner_id) if partner_id else None

def add_to_queue(user_id, mode):
    if not r: return
    user_data = get_user(user_id)
    if mode == "find":
        r.sadd("queue:random", user_id)
    elif mode == "cari_doi":
        q = "queue:male" if user_data.get("gender") == "Laki-laki" else "queue:female"
        r.sadd(q, user_id)

def remove_from_queues(user_id):
    if not r: return
    r.srem("queue:random", user_id)
    r.srem("queue:male", user_id)
    r.srem("queue:female", user_id)

# === HANDLERS ===

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    create_user_if_not_exists(user_id)
    user = get_user(user_id)
    
    if user and user.get("verified"):
        await show_menu(update)
        return ConversationHandler.END
        
    keyboard = [[InlineKeyboardButton("Laki-laki", callback_data="male")],
                [InlineKeyboardButton("Perempuan", callback_data="female")]]
    await update.message.reply_text("👋 Selamat datang! Pilih gender:", reply_markup=InlineKeyboardMarkup(keyboard))
    return GENDER

async def show_menu(update: Update):
    keyboard = [
        [InlineKeyboardButton("🔍 Cari Teman", callback_data="find")],
        [InlineKeyboardButton("💘 Cari Doi", callback_data="cari_doi")],
        [InlineKeyboardButton("✏️ Ubah Profil", callback_data="ubah_profil")]
    ]
    text = "✅ Menu Utama:"
    if update.callback_query:
        await update.callback_query.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def handle_gender(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    create_user_if_not_exists(user_id)
    user = get_user(user_id)
    user["gender"] = "Laki-laki" if query.data == "male" else "Perempuan"
    save_user(user_id, user)
    await query.edit_message_text("🎂 Masukkan usia (angka):")
    return AGE

async def handle_age(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()
    if not text.isdigit():
        await update.message.reply_text("⚠️ Harus angka.")
        return AGE
    user = get_user(user_id)
    user["age"] = int(text)
    user["verified"] = True
    save_user(user_id, user)
    await update.message.reply_text("✅ Profil disimpan!")
    await show_menu(update)
    return ConversationHandler.END

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    create_user_if_not_exists(user_id)
    
    mode = query.data
    if mode == "ubah_profil": return

    partner_id = find_partner(user_id, mode)
    if partner_id:
        u1, u2 = get_user(user_id), get_user(partner_id)
        u1["partner"], u1["searching"] = partner_id, False
        u2["partner"], u2["searching"] = user_id, False
        save_user(user_id, u1)
        save_user(partner_id, u2)
        remove_from_queues(user_id)
        remove_from_queues(partner_id)
        
        msg = "💬 Partner ditemukan! /stop untuk berhenti."
        await query.edit_message_text(msg)
        try: await context.bot.send_message(partner_id, msg)
        except: pass
    else:
        add_to_queue(user_id, mode)
        u = get_user(user_id)
        u["searching"] = True
        save_user(user_id, u)
        await query.edit_message_text("⏳ Sedang mencari partner...")

async def relay_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    create_user_if_not_exists(user_id)
    user = get_user(user_id)
    partner_id = user.get("partner")
    
    if partner_id:
        try:
            await context.bot.send_message(partner_id, update.message.text)
        except:
            await update.message.reply_text("❌ Partner hilang.")
            await stop_chat(update, context)
    elif user.get("searching"):
        await update.message.reply_text("⏳ Masih mencari...")
    else:
        await update.message.reply_text("⚠️ Belum ada partner. Klik /start.")

async def stop_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    create_user_if_not_exists(user_id)
    user = get_user(user_id)
    partner_id = user.get("partner")
    
    user["partner"], user["searching"] = None, False
    save_user(user_id, user)
    remove_from_queues(user_id)
    
    if partner_id:
        p = get_user(partner_id)
        if p:
            p["partner"], p["searching"] = None, False
            save_user(partner_id, p)
            try: await context.bot.send_message(partner_id, "❌ Chat berakhir.")
            except: pass
            
    await update.message.reply_text("🔴 Sesi berhenti.")
    await show_menu(update)

# === SETUP GLOBAL BOT ===
bot_app = ApplicationBuilder().token(TOKEN).build()

conv_handler = ConversationHandler(
    entry_points=[CommandHandler("start", start), CallbackQueryHandler(handle_gender, pattern="^ubah_profil$")],
    states={GENDER:[CallbackQueryHandler(handle_gender)], AGE:[MessageHandler(filters.TEXT, handle_age)]},
    fallbacks=[CommandHandler("start", start)]
)
bot_app.add_handler(conv_handler)
bot_app.add_handler(CommandHandler("stop", stop_chat))
bot_app.add_handler(CallbackQueryHandler(button_handler, pattern="^(find|cari_doi)$"))
bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, relay_message))

# === FLASK ROUTES ===

@app.route('/webhook', methods=['POST'])
def webhook():
    if request.method == "POST":
        update = Update.de_json(request.get_json(force=True), bot_app.bot)
        asyncio.run(bot_app.process_update(update))
        return "OK"
    return "Webhook Active"

@app.route('/', methods=['GET'])
def index():
    # Fitur Auto-Set Webhook saat halaman utama dibuka
    if not PUBLIC_URL:
        return "❌ Error: Variable PUBLIC_URL belum di-set di Railway!"
        
    webhook_url = f"{PUBLIC_URL}/webhook"
    try:
        # Set Webhook ke Telegram
        asyncio.run(bot_app.bot.set_webhook(webhook_url))
        return f"✅ Berhasil! Webhook terpasang di: {webhook_url}"
    except Exception as e:
        return f"❌ Gagal set webhook: {e}"

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
