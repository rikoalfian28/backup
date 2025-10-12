import os
import json
import random
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

# === CONFIG ===
TOKEN = os.getenv("BOT_TOKEN")  # set your bot token in environment
ADMIN_ID = 7894393728
BACKUP_FILE = "backup_anon_semarang.json"
SAWERIA_LINK = "https://saweria.co/operasional"

# === STATES ===
GENDER, AGE = range(2)

# === In-memory storage ===
users = {}
chat_logs = {}

# ---------------------------
# Helpers
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

def ensure_user(uid: int):
    if uid not in users:
        users[uid] = {
            "verified": False,
            "partner": None,
            "gender": None,
            "age": None,
            "searching": False,
            "banned": False,
        }

def save_profile_backup():
    # Save only profile info for verified users
    data = {}
    for uid, u in users.items():
        if u.get("verified"):
            data[str(uid)] = {
                "id": uid,
                "name": u.get("name"),
                "gender": u.get("gender"),
                "age": u.get("age"),
                "verified_at": u.get("verified_at"),
            }
    with open(BACKUP_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

async def send_backup_to_admin(context: ContextTypes.DEFAULT_TYPE):
    # send backup file (JSON only) to admin
    try:
        if os.path.exists(BACKUP_FILE):
            await context.bot.send_document(chat_id=ADMIN_ID, document=InputFile(BACKUP_FILE))
    except Exception as e:
        print("Failed to send backup to admin:", e)

# ---------------------------
# Start / registration
# ---------------------------
async def show_main_menu(update: Optional[Update] = None, context: Optional[ContextTypes.DEFAULT_TYPE] = None, chat_id: Optional[int] = None):
    keyboard = [
        [InlineKeyboardButton("🔍 Find", callback_data="find")],
        [InlineKeyboardButton("✏️ Ubah Profil", callback_data="ubah_profil")],
        [InlineKeyboardButton("👤 Profil", callback_data="profil")],
        [InlineKeyboardButton("💰 Dukung Operasional", url=SAWERIA_LINK)],
    ]
    text = "Anon Semarang Bot\nTempat berbagi cerita dan bertemu teman baru secara anonim.\nPilih tombol untuk memulai percakapan:"
    markup = InlineKeyboardMarkup(keyboard)
    if update and getattr(update, "message", None):
        await update.message.reply_text(text, reply_markup=markup, parse_mode="Markdown")
    elif update and getattr(update, "callback_query", None):
        await update.callback_query.edit_message_text(text, reply_markup=markup, parse_mode="Markdown")
    elif chat_id and context:
        await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=markup, parse_mode="Markdown")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    uid = user.id
    ensure_user(uid)
    users[uid].setdefault("name", user.first_name)

    info = (
        "👋 Hai! Selamat datang di *Anon Semarang Bot* 🎭\n\n"
        "Sebelum mulai, silakan verifikasi singkat (gender + umur).\n"
        "Gunakan bot dengan bijak dan jangan sebarkan data pribadi."
    )
    await safe_reply(update, info.format(bot_title="Anon Semarang Bot"), parse_mode="Markdown")

    if users[uid].get("banned"):
        await safe_reply(update, "⚠️ Kamu telah diblokir admin dan tidak bisa menggunakan bot ini.")
        return ConversationHandler.END

    if users[uid].get("verified"):
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
    uid = query.from_user.id
    ensure_user(uid)
    users[uid]["gender"] = "Laki-laki" if query.data == "male" else "Perempuan"
    try:
        await query.edit_message_text("🎂 Masukkan usia kamu (contoh: 21):")
    except Exception:
        await safe_reply(update, "🎂 Masukkan usia kamu (contoh: 21):")
    return AGE

async def handle_age(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    ensure_user(uid)
    age_text = update.message.text.strip()
    if not age_text.isdigit():
        await safe_reply(update, "⚠️ Usia harus berupa angka. Coba lagi:")
        return AGE
    age = int(age_text)
    if age < 17 or age > 30:
        await safe_reply(update, "Maaf, bot ini hanya untuk pengguna usia 17–30 tahun ya 😊")
        return AGE
    users[uid]["age"] = age
    users[uid]["verified"] = True
    users[uid]["searching"] = False
    users[uid]["verified_at"] = datetime.now().isoformat()
    users[uid].setdefault("name", context.application.bot.username if hasattr(context.application, 'bot') else None)

    # backup profile-only and send to admin (JSON only)
    try:
        save_profile_backup()
    except Exception as e:
        print("Backup save failed:", e)
    try:
        context.application.create_task(send_backup_to_admin(context))
    except Exception:
        pass

    await safe_reply(update, "✅ Data kamu sudah diverifikasi otomatis!\nSekarang kamu bisa mulai mencari partner anonim 🎭")
    await show_main_menu(update, context)
    return ConversationHandler.END

# ---------------------------
# Search / pairing / relay
# ---------------------------
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    ensure_user(uid)
    if users[uid].get("banned"):
        await query.edit_message_text("⚠️ Kamu diblokir admin.")
        return
    action = query.data
    if action == "find":
        if users[uid].get("partner"):
            await query.edit_message_text("⚠️ Kamu sedang dalam percakapan. Gunakan /stop untuk keluar.")
            return
        if users[uid].get("searching"):
            total_verified = sum(1 for u in users.values() if u.get("verified") and not u.get("banned"))
            total_searching = sum(1 for u in users.values() if u.get("searching") and u.get("verified") and not u.get("banned"))
            teks = f"⏳ Kamu sudah mencari partner.\n\n👥 User terverifikasi: {total_verified}\n🟢 Sedang online/mencari: {total_searching}\n\nGunakan /stop untuk membatalkan."
            await query.edit_message_text(teks)
            return
        candidates = [uid2 for uid2, u in users.items() if u.get("searching") and uid2 != uid and u.get("verified") and not u.get("banned")]
        if candidates:
            partner_id = random.choice(candidates)
            users[uid]["partner"] = partner_id
            users[partner_id]["partner"] = uid
            users[uid]["searching"] = False
            users[partner_id]["searching"] = False
            try:
                await context.bot.send_message(uid, "💬 Partner ditemukan! Sekarang kamu bisa ngobrol anonim.")
                await context.bot.send_message(partner_id, "💬 Partner ditemukan! Sekarang kamu bisa ngobrol anonim.")
            except Exception:
                pass
        else:
            users[uid]["searching"] = True
            total_verified = sum(1 for u in users.values() if u.get("verified") and not u.get("banned"))
            total_searching = sum(1 for u in users.values() if u.get("searching") and u.get("verified") and not u.get("banned"))
            teks = f"🔍 Sedang mencari partner...\n\n👥 User terverifikasi: {total_verified}\n🟢 Sedang online/mencari: {total_searching}\n\nGunakan /stop untuk membatalkan."
            await query.edit_message_text(teks)
    elif action == "ubah_profil":
        users[uid].update({"verified": False, "gender": None, "age": None})
        keyboard = [
            [InlineKeyboardButton("Laki-laki", callback_data="male")],
            [InlineKeyboardButton("Perempuan", callback_data="female")],
        ]
        await query.edit_message_text("✏️ Ubah profil kamu.\nPilih gender:", reply_markup=InlineKeyboardMarkup(keyboard))
        return GENDER
    elif action == "profil":
        await show_profile(update, context)

async def show_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    ensure_user(uid)
    u = users[uid]
    if u.get("banned"):
        status = "🚫 Diblokir Admin"
    elif u.get("partner"):
        status = f"💬 Sedang ngobrol dengan User {u['partner']}"
    elif u.get("searching"):
        status = "🔎 Sedang mencari partner"
    else:
        status = "⏸️ Idle"
    teks = "📝 **Profil Kamu**\n"
    teks += f"🆔 User ID: `{uid}`\n"
    teks += f"🚻 Gender: {u.get('gender') or '-'}\n"
    teks += f"🎂 Usia: {u.get('age') or '-'}\n"
    teks += f"📌 Status: {status}\n"
    teks += f"✅ Verifikasi: {'Sudah' if u.get('verified') else 'Belum'}\n"
    await safe_reply(update, teks, parse_mode="Markdown")

# ---------------------------
# Relay messages
# ---------------------------
async def relay_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    ensure_user(uid)
    partner = users[uid].get("partner")
    if not partner:
        await safe_reply(update, "⚠️ Kamu tidak sedang dalam percakapan anonim.")
        return
    if not update.message.text:
        return
    msg = update.message.text
    # save chat lightly
    if uid not in chat_logs:
        chat_logs[uid] = []
    chat_logs[uid].append(("user", msg))
    if len(chat_logs[uid]) > 20:
        chat_logs[uid] = chat_logs[uid][-20:]
    # also save for partner
    if partner not in chat_logs:
        chat_logs[partner] = []
    chat_logs[partner].append(("partner", msg))
    if len(chat_logs[partner]) > 20:
        chat_logs[partner] = chat_logs[partner][-20:]
    try:
        await context.bot.send_message(chat_id=partner, text=msg)
    except Exception as e:
        print("Relay error:", e)

# ---------------------------
# Stop command
# ---------------------------
async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    ensure_user(uid)
    partner = users[uid].get("partner")
    if partner:
        try:
            await context.bot.send_message(chat_id=partner, text="❌ Partner keluar dari percakapan.")
        except:
            pass
        users[partner]["partner"] = None
    users[uid]["partner"] = None
    users[uid]["searching"] = False
    await safe_reply(update, "❌ Kamu keluar dari percakapan / pencarian partner.")

# ---------------------------
# Admin commands (ban/unban/broadcast)
# ---------------------------
async def ban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    admin = update.effective_user.id
    if admin not in [ADMIN_ID]:
        await safe_reply(update, "❌ Kamu bukan admin.")
        return
    if not context.args:
        await safe_reply(update, "⚠️ Gunakan: /ban <user_id>")
        return
    try:
        target = int(context.args[0])
    except ValueError:
        await safe_reply(update, "⚠️ User ID harus angka.")
        return
    ensure_user(target)
    users[target]["banned"] = True
    await safe_reply(update, f"✅ User {target} dibanned.")
    try:
        await context.bot.send_message(target, "⚠️ Kamu telah diblokir oleh admin.")
    except:
        pass

async def unban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    admin = update.effective_user.id
    if admin not in [ADMIN_ID]:
        await safe_reply(update, "❌ Kamu bukan admin.")
        return
    if not context.args:
        await safe_reply(update, "⚠️ Gunakan: /unban <user_id>")
        return
    try:
        target = int(context.args[0])
    except ValueError:
        await safe_reply(update, "⚠️ User ID harus angka.")
        return
    ensure_user(target)
    users[target]["banned"] = False
    await safe_reply(update, f"✅ User {target} di-unban.")
    try:
        await context.bot.send_message(target, "✅ Kamu sudah di-unban oleh admin.")
    except:
        pass

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    admin = update.effective_user.id
    if admin not in [ADMIN_ID]:
        await safe_reply(update, "❌ Kamu bukan admin.")
        return
    if not context.args:
        await safe_reply(update, "⚠️ Gunakan: /broadcast <pesan>")
        return
    message = " ".join(context.args)
    sent = 0
    for uid, u in users.items():
        if u.get("verified") and not u.get("banned"):
            try:
                await context.bot.send_message(chat_id=uid, text=f"📢 Pesan dari Admin:\n\n{message}")
                sent += 1
            except:
                pass
    await safe_reply(update, f"✅ Broadcast dikirim ke {sent} user.")

# ---------------------------
# Restore handler (admin upload)
# ---------------------------
async def restore_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    admin = update.effective_user.id
    if admin not in [ADMIN_ID]:
        await safe_reply(update, "❌ Kamu bukan admin.")
        return
    if not getattr(update.message, "document", None):
        await safe_reply(update, "⚠️ Kirim file JSON backup untuk di-restore.")
        return
    doc = update.message.document
    if not doc.file_name.lower().endswith(".json"):
        await safe_reply(update, "⚠️ File harus berekstensi .json")
        return
    path = "restore_profiles.json"
    try:
        f = await doc.get_file()
        await f.download_to_drive(path)
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        for k, v in data.items():
            try:
                ik = int(k)
            except:
                ik = k
            users[ik] = {
                "verified": True,
                "partner": None,
                "gender": v.get("gender"),
                "age": v.get("age"),
                "searching": False,
                "banned": False,
                "name": v.get("name"),
                "verified_at": v.get("verified_at"),
            }
        save_profile_backup()
        try:
            await context.bot.send_document(chat_id=ADMIN_ID, document=InputFile(BACKUP_FILE))
        except:
            pass
        await safe_reply(update, f"✅ Restore selesai. {len(data)} profil dipulihkan.")
    except Exception as e:
        await safe_reply(update, f"⚠️ Gagal restore: {e}")

# ---------------------------
# Main
# ---------------------------
def main():
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise RuntimeError("BOT_TOKEN environment variable is not set.")
    app = ApplicationBuilder().token(token).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            GENDER: [CallbackQueryHandler(handle_gender, pattern="^(male|female)$")],
            AGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_age)],
        },
        fallbacks=[CommandHandler("start", start)],
        per_message=False,
    )

    app.add_handler(conv)
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(CommandHandler("profil", show_profile))
    app.add_handler(CommandHandler("stop", stop))
    app.add_handler(CommandHandler("ban", ban_command))
    app.add_handler(CommandHandler("unban", unban_command))
    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(MessageHandler(filters.Document.ALL, restore_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, relay_message))

    print("🤖 Anon Semarang Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
