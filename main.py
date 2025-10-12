import json
import os
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler

# ===== Konstanta =====
GENDER, AGE = range(2)
DATA_FILE = "backup_data.json"

# ===== Data Pengguna =====
users = {}

# ===== Fungsi Backup & Restore =====
def save_data():
    with open(DATA_FILE, "w") as f:
        json.dump(users, f, indent=4)

def load_data():
    global users
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            users = json.load(f)

# ===== Start Command =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)

    # Jika user sudah terverifikasi
    if user_id in users and users[user_id].get("verified", False):
        await update.message.reply_text(
            "👋 Kamu sudah terverifikasi!\nGunakan /menu untuk mulai berbicara anonim 🎭"
        )
        return ConversationHandler.END

    # Pesan pembuka
    info_text = (
        "👋 Hai! Selamat datang di *Anon Semarang Bot* 🎭\n"
        "Bot ini dibuat untuk mahasiswa di Semarang agar bisa berbicara secara anonim.\n"
        "Gunakan dengan bijak dan jangan membagikan informasi pribadi sebelum saling mengenal lebih jauh."
    )
    await update.message.reply_text(info_text, parse_mode="Markdown")

    # Langsung mulai verifikasi gender
    reply_keyboard = [["Laki-laki", "Perempuan"]]
    await update.message.reply_text(
        "Silakan pilih jenis kelamin kamu:",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True),
    )
    return GENDER

# ===== Verifikasi Gender =====
async def set_gender(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    gender = update.message.text

    users[user_id] = {"gender": gender}
    await update.message.reply_text("Sekarang, masukkan usia kamu (17–30 tahun):")
    return AGE

# ===== Verifikasi Umur =====
async def set_age(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    try:
        age = int(update.message.text)
        if 17 <= age <= 30:
            users[user_id]["age"] = age
            users[user_id]["verified"] = True
            save_data()
            await update.message.reply_text(
                "✅ Data kamu sudah diverifikasi otomatis!\n"
                "Sekarang kamu bisa mulai mencari partner anonim 🎭"
            )
            return ConversationHandler.END
        else:
            await update.message.reply_text(
                "Maaf, bot ini hanya untuk pengguna usia 17–30 tahun ya 😊\nSilakan ketik /start untuk mencoba lagi."
            )
            return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("Masukkan angka yang valid untuk usia kamu.")
        return AGE

# ===== Command Menu =====
async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📋 Menu:\n"
        "/start - Mulai ulang bot\n"
        "/menu - Tampilkan menu\n"
        "/profile - Lihat profil kamu\n"
        "/saweria - Dukung pengembangan bot 💰"
    )

# ===== Profile =====
async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if user_id not in users:
        await update.message.reply_text("Kamu belum terdaftar. Ketik /start untuk mulai.")
        return

    data = users[user_id]
    profile_text = (
        f"👤 Profil Kamu\n"
        f"Gender: {data.get('gender', 'Tidak diketahui')}\n"
        f"Usia: {data.get('age', 'Tidak diketahui')}\n"
        f"Status: {'Terverifikasi ✅' if data.get('verified') else 'Belum Verifikasi ❌'}"
    )
    await update.message.reply_text(profile_text)

# ===== Saweria =====
async def saweria(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "💰 Dukung pengembangan bot ini di Saweria:\nhttps://saweria.co/anonsemarang"
    )

# ===== Main =====
def main():
    load_data()
    token = os.getenv("BOT_TOKEN")
    if not token:
        print("❌ BOT_TOKEN belum diset di environment variable.")
        return

    app = ApplicationBuilder().token(token).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            GENDER: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_gender)],
            AGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_age)],
        },
        fallbacks=[],
    )

    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("menu", menu))
    app.add_handler(CommandHandler("profile", profile))
    app.add_handler(CommandHandler("saweria", saweria))

    print("🤖 Bot Anon Semarang sedang berjalan...")
    app.run_polling()

if __name__ == "__main__":
    main()
