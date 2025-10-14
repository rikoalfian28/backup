import os
import random
import json
from datetime import datetime
from typing import Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    CallbackQueryHandler,
    ConversationHandler,
    MessageHandler,
    filters,
)

# === KONFIGURASI BOT ===
# GANTI ADMIN_IDS DENGAN USER ID TELEGRAM ANDA
ADMIN_IDS = [123456789]
SAWERIA_LINK = "https://saweria.co/YourLink" # Ganti dengan link Saweria Anda
SAWERIA_MESSAGE = (
    "Terima kasih sudah menggunakan Anonymous Chat! 😊\n\n"
    "Jika bot ini bermanfaat, kamu bisa mendukung operasional server di link berikut:"
)

# === DATA PERSISTENCE ===
DATA_FILE = "bot_data.json"

# === STATES UNTUK CONVERSATION HANDLER ===
GENDER, AGE = range(2)

# === PENYIMPANAN DATA SEMENTARA (IN-MEMORY) ===
users = {}
chat_logs = {}
message_map = {} # Untuk fitur reply pesan

# ---------------------------
# Fungsi Persistence Data (Simpan & Muat)
# ---------------------------
def save_data():
    """Menyimpan data users dan chat_logs ke file JSON."""
    try:
        data_to_save = {"users": users, "chat_logs": chat_logs}
        with open(DATA_FILE, "w") as f:
            json.dump(data_to_save, f, indent=4)
        print(f"🤖 Data saved successfully at {datetime.now().strftime('%H:%M:%S')}")
    except Exception as e:
        print(f"🔥 ERROR saving data: {e}")

def load_data():
    """Memuat data dari file JSON saat bot dimulai."""
    global users, chat_logs
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r") as f:
                data_loaded = json.load(f)
                # Konversi key dari string ke integer
                users.update({int(k): v for k, v in data_loaded.get("users", {}).items()})
                chat_logs.update({int(k): v for k, v in data_loaded.get("chat_logs", {}).items()})
                print(f"🤖 Data loaded from {DATA_FILE}. Total users: {len(users)}")
        except (json.JSONDecodeError, IOError) as e:
            print(f"⚠️ Error loading data: {e}. Starting fresh.")
    else:
        print("⚠️ Data file not found. Starting fresh.")

async def auto_backup(context: ContextTypes.DEFAULT_TYPE):
    """Tugas backup otomatis yang mengirim file data ke admin."""
    save_data()
    for admin_id in ADMIN_IDS:
        try:
            with open(DATA_FILE, 'rb') as f:
                await context.bot.send_document(
                    chat_id=admin_id, document=f,
                    caption=f"🗄️ Auto Backup Data ({datetime.now().strftime('%d/%m %H:%M:%S')})"
                )
        except Exception as e:
            print(f"🔥 ERROR sending backup to admin {admin_id}: {e}")

# ---------------------------
# Fungsi Helper & Utility
# ---------------------------
def ensure_user(user_id: int):
    """Memastikan data user ada di dictionary, jika tidak maka dibuatkan."""
    if user_id not in users:
        users[user_id] = {
            "verified": False, "partner": None, "gender": None,
            "age": None, "searching": False, "banned": False,
            "last_search_mode": "find" # Mode pencarian default
        }

async def safe_reply(update: Update, text: str, **kwargs):
    """Mengirim balasan dengan aman, baik dari message atau callback query."""
    if update.callback_query:
        await update.callback_query.edit_message_text(text, **kwargs)
    elif update.message:
        await update.message.reply_text(text, **kwargs)

def find_partner_match(user_id: int) -> Optional[int]:
    """Mencari partner lawan jenis yang sedang mencari."""
    user_gender = users.get(user_id, {}).get("gender")
    if not user_gender: return None
    required_gender = "Perempuan" if user_gender == "Laki-laki" else "Laki-laki"
    
    candidates = [
        uid for uid, u in users.items()
        if u.get("searching") and uid != user_id and u.get("gender") == required_gender and not u.get("banned")
    ]
    return random.choice(candidates) if candidates else None

def find_friend_match(user_id: int) -> Optional[int]:
    """Mencari partner acak (semua gender) yang sedang mencari."""
    candidates = [
        uid for uid, u in users.items()
        if u.get("searching") and uid != user_id and not u.get("banned")
    ]
    return random.choice(candidates) if candidates else None

# ---------------------------
# Alur Registrasi & Menu Utama
# ---------------------------
async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menampilkan menu utama bot."""
    now = datetime.now()
    day, hour = now.weekday(), now.hour # Senin=0, ..., Minggu=6
    
    keyboard = [
        [InlineKeyboardButton("🔍 Cari Teman (Random)", callback_data="find")],
        [InlineKeyboardButton("✏️ Ubah Profil", callback_data="ubah_profil")],
    ]
    # Mode Cari Doi hanya aktif Jumat 18:00 - Minggu 23:59
    if (day == 4 and hour >= 18) or (day == 5) or (day == 6):
        keyboard.insert(1, [InlineKeyboardButton("💘 Cari Doi (Lawan Jenis)", callback_data="cari_doi")])
    
    await safe_reply(update, "✅ Kamu sudah terverifikasi!\nSilakan pilih menu:", reply_markup=InlineKeyboardMarkup(keyboard))

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk perintah /start."""
    user_id = update.effective_user.id
    ensure_user(user_id)
    if users[user_id].get("banned"):
        await update.message.reply_text("⚠️ Akun Anda telah diblokir oleh admin.")
        return ConversationHandler.END
    if users[user_id].get("verified"):
        await show_main_menu(update, context)
        return ConversationHandler.END
    return await start_registration_flow(update, context)

async def start_registration_flow(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Memulai alur registrasi atau ubah profil."""
    if update.callback_query:
        await update.callback_query.answer()
    user_id = update.effective_user.id
    users[user_id].update({"verified": False, "gender": None, "age": None})
    keyboard = [
        [InlineKeyboardButton("Laki-laki", callback_data="male")],
        [InlineKeyboardButton("Perempuan", callback_data="female")],
    ]
    await safe_reply(update, "👋 Selamat datang!\nUntuk memulai, pilih gender kamu:", reply_markup=InlineKeyboardMarkup(keyboard))
    return GENDER

async def handle_gender(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menangani pilihan gender dan meminta usia."""
    query = update.callback_query
    await query.answer()
    users[query.from_user.id]["gender"] = "Laki-laki" if query.data == "male" else "Perempuan"
    await query.edit_message_text("🎂 Sekarang, masukkan usiamu (hanya angka, 18-25):")
    return AGE

async def handle_age(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menangani masukan usia dan menyelesaikan registrasi."""
    user_id = update.effective_user.id
    age_text = update.message.text.strip()
    if not age_text.isdigit() or not (18 <= int(age_text) <= 25):
        await update.message.reply_text("⚠️ Usia tidak valid. Masukkan angka antara 18-25:")
        return AGE

    users[user_id]["age"] = int(age_text)
    users[user_id]["verified"] = True
    save_data() # Langsung simpan data setelah registrasi berhasil
    await update.message.reply_text("✅ Profil berhasil disimpan!")
    await show_main_menu(update, context)
    return ConversationHandler.END

# ---------------------------
# Handler Tombol dan Perintah Chat
# ---------------------------
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menangani tombol 'Cari Teman' dan 'Cari Doi'."""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    ensure_user(user_id)

    if users[user_id].get("partner") or users[user_id].get("searching"):
        await query.edit_message_text("⚠️ Kamu sudah dalam sesi. Gunakan /stop untuk keluar.")
        return

    action = query.data
    users[user_id]['last_search_mode'] = action
    partner_finder = find_friend_match if action == "find" else find_partner_match
    search_type_text = "Cari Teman" if action == "find" else "Cari Doi"

    partner_id = partner_finder(user_id)
    if partner_id:
        users[partner_id]['last_search_mode'] = action
        users[user_id].update({"partner": partner_id, "searching": False})
        users[partner_id].update({"partner": user_id, "searching": False})
        
        chat_msg = f"💬 Partner {search_type_text} ditemukan! Selamat mengobrol.\n\nGunakan /next untuk cari lagi, atau /stop untuk berhenti."
        await query.edit_message_text(chat_msg)
        await context.bot.send_message(partner_id, chat_msg)
    else:
        users[user_id]["searching"] = True
        total_searching = sum(1 for u in users.values() if u.get("searching"))
        await query.edit_message_text(f"⏳ Sedang mencari {search_type_text}...\nTotal user mencari: {total_searching}\nGunakan /stop untuk batal.")

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menghentikan sesi chat atau pencarian."""
    user_id = update.effective_user.id
    partner_id = users.get(user_id, {}).get("partner")

    if partner_id:
        try:
            await context.bot.send_message(partner_id, "❌ Partner telah mengakhiri obrolan.")
        except Exception as e:
            print(f"🔥 Could not notify partner {partner_id}: {e}")
        users[partner_id]["partner"] = None
    
    users[user_id].update({"partner": None, "searching": False})
    
    await update.message.reply_text("❌ Sesi dihentikan.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("💰 Dukung Kami", url=SAWERIA_LINK)]]))

async def next_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menghentikan chat saat ini dan langsung mencari partner baru."""
    user_id = update.effective_user.id
    if not users.get(user_id, {}).get("partner"):
        await update.message.reply_text("⚠️ Kamu tidak sedang dalam obrolan. Gunakan menu untuk mencari.")
        return

    # Hentikan chat lama
    await stop(update, context)
    
    # Cari chat baru
    await update.message.reply_text("🔄 Mencari partner baru...")
    last_mode = users[user_id].get("last_search_mode", "find")
    
    # Buat callback query palsu untuk memanggil button_handler
    class FakeCallbackQuery:
        def __init__(self, user_id, data):
            self.from_user = type('user', (), {'id': user_id})()
            self.data = data
        async def answer(self): pass
        async def edit_message_text(self, text, **kwargs):
            await context.bot.send_message(user_id, text, **kwargs)

    fake_update = type('update', (), {'callback_query': FakeCallbackQuery(user_id, last_mode)})()
    await button_handler(fake_update, context)

async def relay_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Meneruskan pesan teks antar partner."""
    user_id = update.effective_user.id
    partner_id = users.get(user_id, {}).get("partner")
    if not partner_id:
        await update.message.reply_text("⚠️ Kamu tidak sedang dalam obrolan.")
        return

    original_message = update.message
    if not original_message.text: return # Hanya teruskan pesan teks

    # Cek apakah ini balasan
    target_reply_id = None
    if original_message.reply_to_message:
        target_reply_id = message_map.get(original_message.reply_to_message.message_id)

    try:
        sent_message = await context.bot.send_message(
            chat_id=partner_id,
            text=original_message.text,
            reply_to_message_id=target_reply_id
        )
        # Petakan ID pesan untuk fitur reply
        message_map[sent_message.message_id] = original_message.message_id
    except Exception as e:
        print(f"🔥 Failed to relay message to {partner_id}: {e}")
        await update.message.reply_text("❌ Gagal mengirim pesan. Partner mungkin memblokir bot. Sesi diakhiri.")
        await stop(update, context)

# ---------------------------
# Perintah Tambahan
# ---------------------------
async def myid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menampilkan User ID pengguna."""
    await update.message.reply_text(f"🆔 ID Telegram kamu: `{update.effective_user.id}`", parse_mode='Markdown')

async def report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Melaporkan partner saat ini ke admin."""
    # (Fungsi ini sengaja disederhanakan, Anda bisa menambahkan logika log chat jika perlu)
    user_id = update.effective_user.id
    partner_id = users.get(user_id, {}).get("partner")
    if not partner_id:
        await update.message.reply_text("⚠️ Kamu tidak sedang dalam obrolan untuk dilaporkan.")
        return

    report_text = f"🚨 **Laporan Pengguna** 🚨\n\n- **Pelapor:** `{user_id}`\n- **Terlapor:** `{partner_id}`"
    keyboard = [
        [InlineKeyboardButton(f"Blokir User {partner_id}", callback_data=f"admin_ban_{partner_id}")],
    ]
    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(admin_id, report_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        except Exception as e:
            print(f"🔥 Failed to send report to admin {admin_id}: {e}")
    await update.message.reply_text("✅ Laporan telah dikirim ke admin. Terima kasih.")


# ---------------------------
# Fitur Khusus Admin
# ---------------------------
# (Letakkan semua fungsi admin di sini: broadcast, ban, unban, adminpanel, restore_handler, dll.)
# ... (Kode fungsi admin dari versi sebelumnya bisa disalin di sini) ...

# ---------------------------
# Fungsi Main
# ---------------------------
def main():
    """Fungsi utama untuk menjalankan bot."""
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise RuntimeError("Error: BOT_TOKEN environment variable is not set.")

    load_data()
    app = ApplicationBuilder().token(token).build()

    # Jadwalkan backup otomatis setiap 6 jam
    if app.job_queue:
        app.job_queue.run_repeating(auto_backup, interval=6 * 3600, first=10)
        print("🤖 Auto backup job scheduled.")

    # Conversation Handler untuk registrasi dan ubah profil
    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            CallbackQueryHandler(start_registration_flow, pattern="^ubah_profil$")
        ],
        states={
            GENDER: [CallbackQueryHandler(handle_gender, pattern="^(male|female)$")],
            AGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_age)],
        },
        fallbacks=[CommandHandler("start", start)],
    )
    
    app.add_handler(conv_handler)
    
    # Handler untuk perintah
    app.add_handler(CommandHandler("stop", stop))
    app.add_handler(CommandHandler("next", next_chat))
    app.add_handler(CommandHandler("myid", myid))
    app.add_handler(CommandHandler("report", report))

    # Handler untuk tombol menu utama
    app.add_handler(CallbackQueryHandler(button_handler, pattern="^(find|cari_doi)$"))
    
    # Handler untuk meneruskan pesan (harus terakhir)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, relay_message))

    print("🚀 Bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()
