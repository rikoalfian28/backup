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
# GANTI ADMIN_IDS DAN SAWERIA_LINK DENGAN MILIK ANDA.
# BOT_TOKEN diambil dari Railway Environment Variable (diset di fungsi main).
ADMIN_IDS = [7894393728]  # GANTI DENGAN USER ID ADMIN-MU
SAWERIA_LINK = "https://saweria.co/AnonBotFinal" 
SAWERIA_MESSAGE = (
    "Terima kasih sudah menggunakan Anonymous Chat! "
    "Semoga percakapanmu menyenangkan. 😊\n\n"
    "Jika bot ini bermanfaat, kamu bisa mendukung operasional server di link berikut:"
)

# === DATA PERSISTENCE CONFIG ===
DATA_FILE = "bot_data_final.json" 

# === STATES (Tanpa Universitas) ===
GENDER, AGE = range(2) 

# === In-memory storage ===
users = {} # user_id -> dict with keys: verified, partner, gender, age, searching, banned
chat_logs = {} # user_id -> list of (sender_label, message) up to last 20


# ---------------------------
# Data Persistence (Backup/Restore)
# ---------------------------
def save_data():
    """Save all data (users and chat_logs) to a JSON file."""
    data_to_save = {"users": users, "chat_logs": chat_logs}
    with open(DATA_FILE, "w") as f:
        json.dump(data_to_save, f, indent=4)
    print(f"🤖 Data saved to {DATA_FILE} at {datetime.now().strftime('%H:%M:%S')}")

def load_data():
    """Load data (users and chat_logs) from a JSON file on startup."""
    global users, chat_logs
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            try:
                data_loaded = json.load(f)
                users.update({int(k): v for k, v in data_loaded.get("users", {}).items()})
                chat_logs.update({int(k): v for k, v in data_loaded.get("chat_logs", {}).items()})
                print(f"🤖 Data loaded from {DATA_FILE}. Total users: {len(users)}")
            except json.JSONDecodeError as e:
                print(f"⚠️ Error loading data from {DATA_FILE}: {e}. Starting with empty data.")
    else:
        print("⚠️ Data file not found. Starting with empty data.")

async def auto_backup(context: ContextTypes.DEFAULT_TYPE):
    """Job to periodically save data and send backup file to admins."""
    save_data() 
    backup_file_path = DATA_FILE
    
    for admin_id in ADMIN_IDS:
        try:
            with open(backup_file_path, 'rb') as f:
                await context.bot.send_document(
                    chat_id=admin_id,
                    document=f, 
                    caption=f"🗄️ Auto Backup Data ({datetime.now().strftime('%d/%m %H:%M:%S')})\nFile ini berisi status users dan log chat."
                )
        except Exception as e:
            print(f"ERROR sending backup file to admin {admin_id}: {e}")

# ---------------------------
# Helper utilities
# ---------------------------
async def safe_reply(update: Update, text: str, parse_mode=None, reply_markup=None):
    if getattr(update, "message", None):
        return await update.message.reply_text(text, parse_mode=parse_mode, reply_markup=reply_markup)
    elif getattr(update, "callback_query", None):
        cq = update.callback_query
        if cq.message:
            return await cq.message.reply_text(text, parse_mode=parse_mode, reply_markup=reply_markup)
        else:
            return await cq.answer(text)

def ensure_user(user_id: int):
    if user_id not in users:
        users[user_id] = {
            "verified": False,
            "partner": None,
            "gender": None,
            "age": None,
            "searching": False,
            "banned": False,
        }

def save_chat(user_id: int, sender: str, message: str):
    if user_id not in chat_logs:
        chat_logs[user_id] = []
    chat_logs[user_id].append((sender, message))
    if len(chat_logs[user_id]) > 20:
        chat_logs[user_id] = chat_logs[user_id][-20:]

# ---------------------------
# Helper functions for finding matches
# ---------------------------
def find_partner_match(user_id: int) -> Optional[int]:
    """Finds a verified, searching, non-banned partner of the opposite gender (Cari Doi)."""
    user_data = users.get(user_id)
    if not user_data: return None

    user_gender = user_data.get("gender")
    required_gender = "Perempuan" if user_gender == "Laki-laki" else "Laki-laki" if user_gender == "Perempuan" else None
    if not required_gender: return find_friend_match(user_id)
    
    candidates = [
        uid for uid, u in users.items()
        if u.get("searching") and uid != user_id and u.get("verified") and not u.get("banned") and u.get("gender") == required_gender
    ]
    if candidates: return random.choice(candidates)
    return None

def find_friend_match(user_id: int) -> Optional[int]:
    """Finds a verified, searching, non-banned partner of ANY gender (Find/Cari Teman)."""
    candidates = [
        uid for uid, u in users.items()
        if u.get("searching") and uid != user_id and u.get("verified") and not u.get("banned")
    ]
    if candidates: return random.choice(candidates)
    return None

# ---------------------------
# Menu / Start / Registration
# ---------------------------
async def show_main_menu(update: Optional[Update] = None, context: Optional[ContextTypes.DEFAULT_TYPE] = None, chat_id: Optional[int] = None):
    now = datetime.now()
    day = now.weekday()  # Monday=0, ..., Friday=4, Saturday=5, Sunday=6
    hour = now.hour

    keyboard = [
        [InlineKeyboardButton("🔍 Find (Cari Teman)", callback_data="find")], 
        [InlineKeyboardButton("✏️ Ubah Profil", callback_data="ubah_profil")],
    ]

    # Cari Doi: Jumat 18:00 -> Minggu 23:59
    if (day == 4 and hour >= 18) or (day == 5) or (day == 6): 
        keyboard.insert(1, [InlineKeyboardButton("💘 Cari Doi (Lawan Jenis)", callback_data="cari_doi")])

    text = "✅ Kamu sudah terverifikasi!\nPilih tombol untuk mulai anonim:"
    markup = InlineKeyboardMarkup(keyboard)

    if update and getattr(update, "message", None):
        await update.message.reply_text(text, reply_markup=markup)
    elif update and getattr(update, "callback_query", None):
        await update.callback_query.edit_message_text(text, reply_markup=markup)
    elif chat_id and context:
        await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=markup)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    ensure_user(user_id)

    if users[user_id].get("banned"):
        await safe_reply(update, "⚠️ Kamu telah diblokir admin dan tidak bisa menggunakan bot ini.")
        return ConversationHandler.END

    if users[user_id].get("verified"):
        if users[user_id].get("searching"):
            await safe_reply(update, "⏳ Kamu sedang mencari partner...\nGunakan /stop untuk membatalkan.")
        elif users[user_id].get("partner"):
            await safe_reply(update, "💬 Kamu sedang dalam percakapan anonim.\nGunakan /stop untuk mengakhiri.")
        else:
            await show_main_menu(update, context)
        return ConversationHandler.END

    # Registration starts (langsung ke GENDER)
    keyboard = [
        [InlineKeyboardButton("Laki-laki", callback_data="male")],
        [InlineKeyboardButton("Perempuan", callback_data="female")],
    ]
    await safe_reply(update, "👋 Selamat datang di Anonymous Chat!\nPilih gender kamu:", reply_markup=InlineKeyboardMarkup(keyboard))
    return GENDER 


async def handle_gender(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    ensure_user(user_id)
    users[user_id]["gender"] = "Laki-laki" if query.data == "male" else "Perempuan"

    await query.edit_message_text("🎂 Masukkan usia kamu (18–25 tahun):")
    return AGE


async def handle_age(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    ensure_user(user_id)
    age_text = update.message.text.strip()
    if not age_text.isdigit():
        await safe_reply(update, "⚠️ Usia harus berupa angka. Coba lagi:")
        return AGE

    age = int(age_text)
    if age < 18 or age > 25:
        await safe_reply(update, "⚠️ Usia hanya diperbolehkan 18–25 tahun. Coba lagi:")
        return AGE

    users[user_id]["age"] = age
    
    # VERIFIKASI OTOMATIS
    users[user_id]["verified"] = True
    users[user_id].setdefault("name", update.effective_user.first_name)
    
    # Instant backup (menggantikan admin verification request)
    try:
        # Menjadwalkan tugas backup secara instan
        context.application.create_task(auto_backup(context)) 
    except Exception as e:
        # Ini akan gagal jika JobQueue tidak disiapkan, tapi logic tetap berjalan.
        # JobQueue warning ditangani di main().
        print(f"Error creating instant auto_backup task: {e}")
    
    await safe_reply(update, "✅ Profil kamu sudah diverifikasi secara otomatis!")
    await show_main_menu(update, context)
    return ConversationHandler.END

# ---------------------------
# Stop command (termasuk Saweria Link)
# ---------------------------
async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    ensure_user(user_id)
    partner_id = users[user_id].get("partner")

    if partner_id:
        try:
            await context.bot.send_message(chat_id=partner_id, text="❌ Partner keluar dari percakapan.")
        except: pass
        users[partner_id]["partner"] = None

    users[user_id]["partner"] = None
    users[user_id]["searching"] = False
    
    await safe_reply(update, "❌ Kamu keluar dari percakapan / pencarian partner.")

    keyboard = [
        [InlineKeyboardButton("💰 Dukung Kami di Saweria", url=SAWERIA_LINK)]
    ]
    markup = InlineKeyboardMarkup(keyboard)
    
    await safe_reply(update, SAWERIA_MESSAGE, reply_markup=markup)

# ---------------------------
# Report command
# ---------------------------
async def report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    ensure_user(user_id)
    partner_id = users[user_id].get("partner")
    if not partner_id:
        await safe_reply(update, "⚠️ Kamu tidak sedang dalam percakapan anonim.")
        return

    log_text = "📑 Riwayat Chat Terakhir:\n\n"
    for sender, msg in chat_logs.get(user_id, []):
        prefix = "🟢 Kamu" if sender == "user" else "🔵 Partner"
        log_text += f"{prefix}: {msg}\n"

    for admin_id in ADMIN_IDS:
        keyboard = [[InlineKeyboardButton("🚫 Ban User", callback_data=f"ban_{partner_id}"), InlineKeyboardButton("✅ Unban User", callback_data=f"unban_{partner_id}")]]
        try:
            await context.bot.send_message(
                chat_id=admin_id,
                text=f"🚨 LAPORAN USER!\n\nPelapor: {user_id}\nTerlapor: {partner_id}\n\n{log_text}",
                reply_markup=InlineKeyboardMarkup(keyboard),
            )
        except Exception as e: print(f"ERROR send report to {admin_id}: {e}")

    await safe_reply(update, "📩 Laporan sudah dikirim ke admin. Terima kasih!")

# ---------------------------
# Admin commands
# ---------------------------
async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    admin_id = update.effective_user.id
    if admin_id not in ADMIN_IDS: await safe_reply(update, "❌ Kamu bukan admin."); return
    if not context.args: await safe_reply(update, "⚠️ Gunakan format: /broadcast <pesan>"); return

    message = " ".join(context.args)
    target_users = [uid for uid, u in users.items() if not u.get("banned") and uid != admin_id]
    success_count, fail_count = 0, 0
    broadcast_message = f"📢 **Pesan Admin**\n\n{message}"
    
    for uid in target_users:
        try:
            await context.bot.send_message(uid, broadcast_message, parse_mode="Markdown"); success_count += 1
        except Exception as e: print(f"ERROR broadcasting to {uid}: {e}"); fail_count += 1

    await safe_reply(update, f"✅ Pesan berhasil dikirim ke {success_count} user.\n❌ Gagal dikirim ke {fail_count} user.")

async def ban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    admin_id = update.effective_user.id
    if admin_id not in ADMIN_IDS: await safe_reply(update, "❌ Kamu bukan admin."); return
    if not context.args: await safe_reply(update, "⚠️ Gunakan format: /ban <user_id>"); return
    try: target_id = int(context.args[0])
    except ValueError: await safe_reply(update, "⚠️ User ID harus berupa angka."); return

    ensure_user(target_id)
    users[target_id]["banned"] = True
    await safe_reply(update, f"✅ User {target_id} berhasil diblokir.");
    try: await context.bot.send_message(target_id, "⚠️ Kamu telah diblokir oleh admin.");
    except: pass

async def unban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    admin_id = update.effective_user.id
    if admin_id not in ADMIN_IDS: await safe_reply(update, "❌ Kamu bukan admin."); return
    if not context.args: await safe_reply(update, "⚠️ Gunakan format: /unban <user_id>"); return
    try: target_id = int(context.args[0])
    except ValueError: await safe_reply(update, "⚠️ User ID harus berupa angka."); return

    ensure_user(target_id)
    users[target_id]["banned"] = False
    await safe_reply(update, f"✅ User {target_id} sudah di-unban.");
    try: await context.bot.send_message(target_id, "✅ Kamu sudah di-unban oleh admin.");
    except: pass

# ---------------------------
# Admin Panel & Recovery
# ---------------------------
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    admin_id = update.effective_user.id
    if admin_id not in ADMIN_IDS: await safe_reply(update, "❌ Kamu bukan admin."); return

    keyboard = [[InlineKeyboardButton("📋 Semua User", callback_data="list_users")], [InlineKeyboardButton("✅ Terverifikasi", callback_data="list_verified")], [InlineKeyboardButton("🚫 Banned", callback_data="list_banned")]]
    await safe_reply(update, "⚙️ Panel Admin:", reply_markup=InlineKeyboardMarkup(keyboard))

async def admin_panel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    action = query.data; admin_id = query.from_user.id
    if admin_id not in ADMIN_IDS: await query.edit_message_text("❌ Kamu bukan admin."); return

    filter_map = {"list_users": list(users.keys()), "list_verified": [uid for uid, u in users.items() if u.get("verified")], "list_banned": [uid for uid, u in users.items() if u.get("banned")]}
    
    if action in filter_map:
        target_list = filter_map[action]
        if not target_list:
            await query.edit_message_text(f"📋 Tidak ada user di kategori ini."); return
        
        keyboard = [[InlineKeyboardButton(f"User {uid}", callback_data=f"detail_{uid}")] for uid in target_list]
        await query.edit_message_text(f"📋 User di Kategori {action.split('_')[1]}:", reply_markup=InlineKeyboardMarkup(keyboard))

async def admin_detail_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    admin_id = query.from_user.id
    if admin_id not in ADMIN_IDS: await query.edit_message_text("❌ Kamu bukan admin."); return
    
    parts = query.data.split("_", 1)
    if len(parts) != 2: await query.edit_message_text("⚠️ Data tidak valid."); return
    try: target_id = int(parts[1])
    except ValueError: await query.edit_message_text("⚠️ ID user tidak valid."); return

    ensure_user(target_id)
    profil = users[target_id]
    status_text = "🚫 Diblokir Admin" if profil.get("banned") else f"💬 Ngobrol ({profil['partner']})" if profil.get("partner") else "🔎 Mencari" if profil.get("searching") else "⏸️ Idle"

    teks = f"📝 **Profil User (Detail)**\n🆔 User ID: `{target_id}`\n🚻 Gender: {profil.get('gender') or '-'}\n🎂 Usia: {profil.get('age') or '-'}\n📌 Status: {status_text}\n✅ Verifikasi: {'Sudah' if profil.get('verified') else 'Belum'}\n🚫 Banned: {'Ya' if profil.get('banned') else 'Tidak'}"
    keyboard = [[InlineKeyboardButton("🚫 Ban", callback_data=f"ban_{target_id}"), InlineKeyboardButton("✅ Unban", callback_data=f"unban_{target_id}")]]
    await context.bot.send_message(admin_id, teks, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def restore_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    admin_id = update.effective_user.id
    if admin_id not in ADMIN_IDS: await safe_reply(update, "❌ Kamu bukan admin."); return

    if not getattr(update.message, "document", None): await safe_reply(update, "⚠️ Kirim file JSON backup untuk di-restore."); return
    doc = update.message.document
    if doc.file_name != DATA_FILE: await safe_reply(update, f"⚠️ Nama file harus '{DATA_FILE}'."); return

    temp_path = f"temp_recover_{admin_id}.json"
    try:
        f = await doc.get_file(); await f.download_to_drive(temp_path)
        global users, chat_logs
        with open(temp_path, "r", encoding="utf-8") as fh: recovered_data = json.load(fh)
        
        users.clear(); chat_logs.clear()
        users.update({int(k): v for k, v in recovered_data.get("users", {}).items()})
        chat_logs.update({int(k): v for k, v in recovered_data.get("chat_logs", {}).items()})
        os.remove(temp_path)
        save_data() # Save locally immediately
        
        await safe_reply(update, f"✅ Data berhasil di-RECOVER! Total user: {len(users)}.");
    except json.JSONDecodeError:
        await safe_reply(update, "❌ Gagal memproses file. Pastikan file JSON valid.")
    except Exception as e:
        await safe_reply(update, f"⚠️ Gagal restore: {e}")

# ---------------------------
# Button handler for menu (DIPERBAIKI)
# ---------------------------
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    ensure_user(user_id)

    # blocked check
    if users[user_id].get("banned"):
        await query.edit_message_text("⚠️ Kamu diblokir admin.")
        return

    action = query.data

    if action in ["find", "cari_doi"]:
        if users[user_id].get("partner"):
            await query.edit_message_text("⚠️ Kamu sedang dalam percakapan. Gunakan /stop untuk keluar.")
            return
        if users[user_id].get("searching"):
            total_verified = sum(1 for u in users.values() if u.get("verified") and not u.get("banned"))
            total_searching = sum(1 for u in users.values() if u.get("searching") and u.get("verified") and not u.get("banned"))
            teks = (f"⏳ Kamu sudah mencari partner.\n\n👥 User terverifikasi: {total_verified}\n🟢 Sedang online/mencari: {total_searching}\n\nGunakan /stop untuk membatalkan.")
            await query.edit_message_text(teks)
            return

        # Logika Pencarian
        partner_id = None
        if action == "cari_doi":
            partner_id = find_partner_match(user_id)
            search_type_text = "Cari Doi (Lawan Jenis)"
        elif action == "find":
            partner_id = find_friend_match(user_id)
            search_type_text = "Cari Teman (Random)"
            
        if partner_id:
            users[user_id]["partner"] = partner_id; users[partner_id]["partner"] = user_id
            users[user_id]["searching"] = False; users[partner_id]["searching"] = False
            
            await context.bot.send_message(user_id, f"💬 Partner {search_type_text} ditemukan! Sekarang kamu bisa ngobrol anonim.")
            await context.bot.send_message(partner_id, f"💬 Partner {search_type_text} ditemukan! Sekarang kamu bisa ngobrol anonim.")
        else:
            users[user_id]["searching"] = True
            total_verified = sum(1 for u in users.values() if u.get("verified") and not u.get("banned"))
            total_searching = sum(1 for u in users.values() if u.get("searching") and u.get("verified") and not u.get("banned"))
            teks = (f"🔍 Sedang mencari {search_type_text}...\n\n👥 User terverifikasi: {total_verified}\n🟢 Sedang online/mencari: {total_searching}\n\nGunakan /stop untuk membatalkan.")
            await query.edit_message_text(teks)

    elif action == "ubah_profil":
        users[user_id].update({"verified": False, "gender": None, "age": None})
        keyboard = [
            [InlineKeyboardButton("Laki-laki", callback_data="male")],
            [InlineKeyboardButton("Perempuan", callback_data="female")],
        ]
        await query.edit_message_text("✏️ Ubah profil kamu.\nPilih gender:", reply_markup=InlineKeyboardMarkup(keyboard))
        return GENDER


# ---------------------------
# Relay messages
# ---------------------------
async def relay_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id; ensure_user(user_id)
    partner_id = users[user_id].get("partner")

    if partner_id:
        msg = update.message.text
        if not msg: await safe_reply(update, "⚠️ Maaf, bot hanya mendukung pesan teks saat ngobrol."); return
        save_chat(user_id, "user", msg); save_chat(partner_id, "partner", msg)
        try: await context.bot.send_message(chat_id=partner_id, text=msg)
        except Exception as e: print(f"ERROR sending relayed message: {e}")
    else:
        await safe_reply(update, "⚠️ Kamu tidak sedang dalam percakapan anonim.")


# ---------------------------
# Utility commands
# ---------------------------
async def myid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await safe_reply(update, f"🆔 User ID kamu: `{user_id}`", parse_mode="Markdown")

async def online_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    total_verified = sum(1 for u in users.values() if u.get("verified") and not u.get("banned"))
    searching_verified = [uid for uid, u in users.items() if u.get("searching") and u.get("verified") and not u.get("banned")]

    if user_id in ADMIN_IDS:
        if not searching_verified:
            await safe_reply(update, "📭 Tidak ada user terverifikasi yang sedang mencari partner.")
            return
        teks = "🟢 User terverifikasi yang sedang mencari:\n\n"
        for uid in searching_verified:
            u = users[uid]
            teks += f"- `{uid}` | {u.get('gender') or '?'} | {u.get('age') or '?'} tahun\n"
        teks += f"\n👥 Total verified: {total_verified}\n🟢 Sedang mencari: {len(searching_verified)}"
        await safe_reply(update, teks, parse_mode="Markdown")
    else:
        teks = f"👥 User terverifikasi: {total_verified}\n🟢 Sedang online/mencari: {len(searching_verified)}"
        await safe_reply(update, teks)


# ---------------------------
# Main
# ---------------------------
def main():
    token = os.getenv("BOT_TOKEN")
    if not token: raise RuntimeError("BOT_TOKEN environment variable is not set.")

    load_data() 
    app = ApplicationBuilder().token(token).build()

    # 2. ADD AUTO-BACKUP JOB (Run every 12 hours, and instantly on verification)
    BACKUP_INTERVAL_SECONDS = 12 * 60 * 60 
    
    if app.job_queue:
        app.job_queue.run_repeating(auto_backup, interval=BACKUP_INTERVAL_SECONDS, first=5) 
        print(f"🤖 Auto backup scheduled every {BACKUP_INTERVAL_SECONDS / 3600} hours.")
    else:
        print("⚠️ WARNING: JobQueue failed to set up. Auto-backup will not run.")

    # Conversation handler (start -> gender -> age)
    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            GENDER: [CallbackQueryHandler(handle_gender, pattern="^(male|female)$")],
            AGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_age)],
        },
        fallbacks=[CommandHandler("start", start)],
        per_message=False,
    )

    # Add handlers
    app.add_handler(conv)
    app.add_handler(CommandHandler("stop", stop))
    app.add_handler(CommandHandler("report", report))
    app.add_handler(CommandHandler("ban", ban_command))
    app.add_handler(CommandHandler("unban", unban_command))
    app.add_handler(CommandHandler("broadcast", broadcast_command))
    app.add_handler(CommandHandler("adminpanel", admin_panel))
    app.add_handler(CommandHandler("myid", myid))
    app.add_handler(CommandHandler("online", online_cmd))

    # Callback Query Handlers
    app.add_handler(CallbackQueryHandler(admin_panel_handler, pattern="^(list_users|list_verified|list_banned)$"))
    app.add_handler(CallbackQueryHandler(admin_detail_handler, pattern="^detail_"))
    
    # Perbaikan NameError: button_handler sekarang terdaftar dengan benar
    app.add_handler(CallbackQueryHandler(button_handler)) 

    # Handler for Admin Data Recovery
    app.add_handler(
        MessageHandler(filters.Document.ALL & filters.User(user_id=ADMIN_IDS), restore_handler)
    )
    # Handler for generic text messages (relay)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, relay_message))

    print("🤖 Anonymous Chat Final Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
