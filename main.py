
import os
import json
import random
from datetime import datetime
from typing import Optional
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

# === STATE CONSTANTS ===
GENDER, AGE = range(2)

# === Data pengguna ===
users = {}
chat_logs = {}

# === Admin ===
ADMIN_IDS = [7894393728]

# === File backup ===
BACKUP_FILE = "backup_anon_semarang.json"

# ---------------------------
# Helper Functions
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


def auto_backup_users():
    try:
        with open(BACKUP_FILE, "w", encoding="utf-8") as f:
            json.dump({"users": users, "chat_logs": chat_logs}, f, indent=2, ensure_ascii=False)
        print(f"✅ Auto-backup berhasil ({len(users)} user tersimpan).")
    except Exception as e:
        print(f"⚠️ Gagal backup data: {e}")


# ---------------------------
# Restore dari file JSON
# ---------------------------
async def restore_from_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    admin_id = update.effective_user.id
    if admin_id not in ADMIN_IDS:
        await safe_reply(update, "❌ Kamu bukan admin.")
        return

    if not getattr(update.message, "document", None):
        await safe_reply(update, "⚠️ Kirim file JSON backup untuk di-restore.")
        return

    doc = update.message.document
    if not doc.file_name.lower().endswith(".json"):
        await safe_reply(update, "⚠️ File harus berekstensi .json")
        return

    path = "restore_temp.json"
    try:
        file = await doc.get_file()
        await file.download_to_drive(path)
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if "users" in data:
            users.clear()
            for k, v in data["users"].items():
                users[int(k)] = v
        if "chat_logs" in data:
            chat_logs.clear()
            for k, v in data["chat_logs"].items():
                chat_logs[int(k)] = v

        auto_backup_users()
        await safe_reply(update, f"♻️ Restore berhasil — {len(users)} user dipulihkan.")
    except Exception as e:
        await safe_reply(update, f"⚠️ Gagal restore: {e}")


# ---------------------------
# Menu Utama
# ---------------------------
async def show_main_menu(update: Optional[Update] = None, context: Optional[ContextTypes.DEFAULT_TYPE] = None):
    keyboard = [
        [InlineKeyboardButton("🔍 Cari Partner", callback_data="find")],
        [InlineKeyboardButton("👤 Profil", callback_data="profil")],
        [InlineKeyboardButton("💰 Dukung Operasional", url="https://saweria.co/operasional")],
    ]
    markup = InlineKeyboardMarkup(keyboard)
    text = "✅ Kamu sudah diverifikasi!\nPilih tombol di bawah untuk mulai percakapan:"

    if update and getattr(update, "message", None):
        await update.message.reply_text(text, reply_markup=markup)
    elif update and getattr(update, "callback_query", None):
        await update.callback_query.edit_message_text(text, reply_markup=markup)


# ---------------------------
# Start & Verifikasi
# ---------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    ensure_user(user_id)

    info_text = """👋 Hai! Selamat datang di *Anon Semarang Bot* 🎭

Bot ini dibuat untuk mahasiswa dan masyarakat di Kota Semarang agar dapat berbicara secara anonim dan aman.

⚠️ Mohon gunakan dengan bijak:
• Hormati sesama pengguna.
• Dilarang menyebarkan data pribadi sebelum saling mengenal lebih jauh.
• Dilarang mengirim konten negatif, SARA, atau pornografi.
• Pelanggaran akan menyebabkan pemblokiran permanen.

Silakan lanjutkan proses verifikasi singkat untuk mulai menggunakan bot. ✅"""

    await safe_reply(update, info_text, parse_mode="Markdown")

    if users[user_id].get("banned"):
        await safe_reply(update, "⚠️ Kamu telah diblokir admin.")
        return ConversationHandler.END

    if users[user_id].get("verified"):
        await show_main_menu(update, context)
        return ConversationHandler.END

    keyboard = [
        [InlineKeyboardButton("Laki-laki", callback_data="male")],
        [InlineKeyboardButton("Perempuan", callback_data="female")],
    ]
    await safe_reply(update, "🚻 Pilih gender kamu:", reply_markup=InlineKeyboardMarkup(keyboard))
    return GENDER


async def handle_gender(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    ensure_user(user_id)
    users[user_id]["gender"] = "Laki-laki" if query.data == "male" else "Perempuan"
    await query.edit_message_text("🎂 Masukkan usia kamu (contoh: 21):")
    return AGE


async def handle_age(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    ensure_user(user_id)
    age_text = update.message.text.strip()
    if not age_text.isdigit():
        await safe_reply(update, "⚠️ Usia harus berupa angka. Coba lagi:")
        return AGE

    age = int(age_text)
    if age < 17 or age > 30:
        await safe_reply(update, "Maaf, bot ini hanya untuk pengguna usia 17–30 tahun 😊")
        return AGE

    users[user_id]["age"] = age
    users[user_id]["verified"] = True
    auto_backup_users()

    await safe_reply(update, "✅ Verifikasi selesai! Kamu bisa mulai mencari partner anonim 🎭")
    await show_main_menu(update, context)
    return ConversationHandler.END


# ---------------------------
# Profil Pengguna
# ---------------------------
async def profil(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    ensure_user(user_id)
    profil = users[user_id]

    teks = f"""📝 **Profil Kamu**
🆔 User ID: `{user_id}`
🚻 Gender: {profil.get('gender') or '-'}
🎂 Usia: {profil.get('age') or '-'}
✅ Verifikasi: {'Sudah' if profil.get('verified') else 'Belum'}
"""
    await safe_reply(update, teks, parse_mode="Markdown")


# ---------------------------
# Fungsi Utama
# ---------------------------
def main():
    token = os.getenv("BOT_TOKEN")
    if not token:
        print("❌ BOT_TOKEN belum diatur.")
        return

    app = ApplicationBuilder().token(token).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            GENDER: [CallbackQueryHandler(handle_gender)],
            AGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_age)],
        },
        fallbacks=[CommandHandler("start", start)],
    )

    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("profil", profil))
    app.add_handler(MessageHandler(filters.Document.JSON, restore_from_file))

    print("🚀 Bot Anon Semarang aktif...")
    app.run_polling()


if __name__ == "__main__":
    main()
