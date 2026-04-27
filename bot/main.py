import os
import asyncio
import logging
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
from db import (
    init_db, upsert_session, get_session, get_all_active_sessions,
    update_last_mail_id, update_session_after_restore, deactivate_session,
    log_mail, get_stats, add_email_to_history, get_email_history,
    get_all_history_entries, update_history_session, update_history_last_mail_id,
    get_history_entry_by_email, get_user_history_entries, remove_email_from_history,
)
import dropmail

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

BOT_TOKEN    = os.environ.get("TELEGRAM_BOT_TOKEN", "")
POLL_INTERVAL    = 3
RESTORE_INTERVAL = 600  # 10 minutes

ADMIN_ID          = int(os.environ.get("ADMIN_ID", 5002402843))
TARGET_CHANNEL_ID = int(os.environ.get("CHANNEL_ID", 0)) or None
ALLOWED           = filters.Chat(chat_id=[ADMIN_ID])

# ── Button Labels ──────────────────────────────────────────────────────────────
BTN_NEW_EMAIL  = "✉️ New address"
BTN_MY_EMAIL   = "📓 List"
BTN_DELETE     = "🗑️ Delete"

MAIN_KEYBOARD = ReplyKeyboardMarkup(
    [
        [KeyboardButton(BTN_NEW_EMAIL), KeyboardButton(BTN_MY_EMAIL)],
        [KeyboardButton(BTN_DELETE)],
    ],
    resize_keyboard=True,
    is_persistent=True,
)


# ── Inline keyboard shown under each email card ────────────────────────────────
def email_inline_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📥 ពិនិត្យប្រអប់", callback_data="check_inbox"),
         InlineKeyboardButton("🔄 អ៊ីម៉ែលថ្មី",   callback_data="new_email")],
        [InlineKeyboardButton("🗑 លុបអ៊ីម៉ែល",    callback_data="delete_email")],
    ])


# ── /start ────────────────────────────────────────────────────────────────────
async def send_welcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    name = user.first_name or "អ្នក"
    text = f"សួស្តី {name}"
    await update.message.reply_text(text, parse_mode="HTML", reply_markup=MAIN_KEYBOARD)


# ── 📧 New Email ──────────────────────────────────────────────────────────────
async def handle_new_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    try:
        result = await asyncio.to_thread(dropmail.create_session)
    except Exception as e:
        await update.message.reply_text(f"❌ បង្កើតមិនបានទេ: {e}", reply_markup=MAIN_KEYBOARD)
        return

    if not result:
        await update.message.reply_text(
            "❌ មិនអាចបង្កើត session បានទេ។ សូមព្យាយាមម្ដងទៀត។",
            reply_markup=MAIN_KEYBOARD
        )
        return

    def _persist():
        upsert_session(
            telegram_user_id=user.id,
            telegram_username=user.username,
            telegram_first_name=user.first_name,
            dropmail_session_id=result["session_id"],
            email_address=result["email"],
            address_id=result["address_id"],
            restore_key=result["restore_key"],
        )
        add_email_to_history(user.id, result["email"],
                             dropmail_session_id=result["session_id"],
                             address_id=result["address_id"],
                             restore_key=result["restore_key"])

    await asyncio.to_thread(_persist)
    await update.message.reply_text(f"<code>{result['email']}</code>", parse_mode="HTML")


# ── 📋 My Email ───────────────────────────────────────────────────────────────
async def handle_my_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    session = await asyncio.to_thread(get_session, user.id)

    if not session or not session.get("is_active") or not session.get("email_address"):
        await update.message.reply_text(
            "❌ អ្នកមិនទាន់មាន session ដែលសកម្មនៅឡើយ។\n\n"
            "ចុច <b>📧 អ៊ីម៉ែលថ្មី</b> ដើម្បីបង្កើត។",
            parse_mode="HTML",
            reply_markup=MAIN_KEYBOARD
        )
        return

    text = (
        f"📧 <b>អ៊ីម៉ែលបច្ចុប្បន្នរបស់អ្នក:</b>\n\n"
        f"<code>{session['email_address']}</code>\n\n"
        f"👆 ចុចលើអ៊ីម៉ែលដើម្បីចម្លង។"
    )
    await update.message.reply_text(
        text, parse_mode="HTML", reply_markup=email_inline_kb()
    )


# ── 📓 List — show all emails ever created ───────────────────────────────────
async def handle_inbox(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user    = update.effective_user
    history = await asyncio.to_thread(get_email_history, user.id)

    if not history:
        await update.message.reply_text(
            "📭 គ្មាន email ណាទេ។\n\nចុច ✉️ New address ដើម្បីបង្កើត។",
            reply_markup=MAIN_KEYBOARD
        )
        return

    lines = "\n".join(f"{i+1}- <code>{email}</code>" for i, email in enumerate(history))
    text  = f"📧 Email {len(history)}\n\n{lines}"
    await update.message.reply_text(text, parse_mode="HTML", reply_markup=MAIN_KEYBOARD)


# ── 🗑️ Delete — show email picker ─────────────────────────────────────────────
async def handle_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user    = update.effective_user
    entries = await asyncio.to_thread(get_user_history_entries, user.id)

    if not entries:
        await update.message.reply_text(
            "📭 គ្មាន email ណាទេ។",
            reply_markup=MAIN_KEYBOARD
        )
        return

    buttons = [
        [InlineKeyboardButton(e["email_address"], callback_data=f"del_email:{e['email_address']}")]
        for e in entries
    ]
    kb = InlineKeyboardMarkup(buttons)

    await update.message.reply_text(
        "ជ្រើសរើស Email ដែលអ្នកចង់លុប៖",
        reply_markup=kb
    )


# ── 📊 Statistics ─────────────────────────────────────────────────────────────
async def handle_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    s = await asyncio.to_thread(get_stats)
    text = (
        "📊 <b>ស្ថិតិ Bot</b>\n\n"
        f"👥 អ្នកប្រើប្រាស់សរុប: <b>{s['total_users']}</b>\n"
        f"📬 Session សកម្ម: <b>{s['active_sessions']}</b>\n"
        f"📧 អ៊ីម៉ែលបានបញ្ជូន: <b>{s['total_emails']}</b>\n"
    )
    await update.message.reply_text(text, parse_mode="HTML", reply_markup=MAIN_KEYBOARD)


# ── Show Inbox (shared helper) ────────────────────────────────────────────────
async def _show_inbox(user_id: int, reply_to=None, callback_query=None):
    session = await asyncio.to_thread(get_session, user_id)

    if not session or not session.get("is_active") or not session.get("dropmail_session_id"):
        text = (
            "❌ អ្នកមិនមាន session ដែលសកម្មទេ។\n\n"
            "ចុច <b>📧 អ៊ីម៉ែលថ្មី</b> ដើម្បីបង្កើត។"
        )
        if callback_query:
            await callback_query.edit_message_text(text, parse_mode="HTML")
        elif reply_to:
            await reply_to.reply_text(text, parse_mode="HTML", reply_markup=MAIN_KEYBOARD)
        return

    try:
        mails = await asyncio.to_thread(
            dropmail.get_new_mails, session["dropmail_session_id"], None
        )
    except Exception as e:
        text = f"❌ កំហុសក្នុងការពិនិត្យ: {e}"
        if callback_query:
            await callback_query.edit_message_text(text)
        elif reply_to:
            await reply_to.reply_text(text, reply_markup=MAIN_KEYBOARD)
        return

    if mails is None:
        # Session expired but we have restore key — show restore notice
        text = (
            f"⚠️ Session ផុតកំណត់។ កំពុងស្តារឡើងវិញ...\n"
            f"📧 <code>{session['email_address']}</code>"
        )
        if callback_query:
            await callback_query.edit_message_text(text, parse_mode="HTML")
        elif reply_to:
            await reply_to.reply_text(text, parse_mode="HTML", reply_markup=MAIN_KEYBOARD)
        return

    if not mails:
        text = (
            f"📭 <b>ប្រអប់ទទេ</b>\n\n"
            f"📧 <code>{session['email_address']}</code>\n\n"
            f"មិនទាន់មានអ៊ីម៉ែលចូលទេ។ ខ្ញុំនឹងជូនដំណឹងអ្នកភ្លាមៗ។"
        )
    else:
        text = f"📬 <b>ប្រអប់ — {len(mails)} សំបុត្រ</b>\n"
        text += f"📧 <code>{session['email_address']}</code>\n\n"
        for i, mail in enumerate(mails[-5:], 1):
            subject   = mail.get("headerSubject") or "(គ្មានប្រធានបទ)"
            from_addr = mail.get("fromAddr") or "unknown"
            body      = (mail.get("text") or "").strip()
            preview   = body[:200] + "…" if len(body) > 200 else body
            text += (
                f"━━━━━━━━━━━━━━━━━━\n"
                f"<b>#{i} {subject}</b>\n"
                f"From: <code>{from_addr}</code>\n"
                f"{preview or '<i>(ទទេ)</i>'}\n\n"
            )

    refresh_kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 ផ្ទុកឡើងវិញ",    callback_data="check_inbox"),
         InlineKeyboardButton("🔄 អ៊ីម៉ែលថ្មី",   callback_data="new_email")],
        [InlineKeyboardButton("🗑 លុបអ៊ីម៉ែល",    callback_data="delete_email")],
    ])

    if callback_query:
        await callback_query.edit_message_text(text, parse_mode="HTML", reply_markup=refresh_kb)
    elif reply_to:
        await reply_to.reply_text(text, parse_mode="HTML", reply_markup=refresh_kb)


# ── Inline button callbacks ───────────────────────────────────────────────────
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user  = query.from_user
    if user.id != ADMIN_ID:
        await query.answer("⛔ អ្នកមិនមានសិទ្ធិប្រើ bot នេះទេ។", show_alert=True)
        return
    await query.answer()

    if query.data == "check_inbox":
        await _show_inbox(user.id, callback_query=query)

    elif query.data == "new_email":
        try:
            result = await asyncio.to_thread(dropmail.create_session)
        except Exception as e:
            await query.edit_message_text(f"❌ បង្កើតមិនបានទេ: {e}")
            return
        if not result:
            await query.edit_message_text("❌ មិនអាចបង្កើត session បានទេ។ សូមព្យាយាមម្ដងទៀត។")
            return

        def _persist():
            upsert_session(
                telegram_user_id=user.id,
                telegram_username=user.username,
                telegram_first_name=user.first_name,
                dropmail_session_id=result["session_id"],
                email_address=result["email"],
                address_id=result["address_id"],
                restore_key=result["restore_key"],
            )
            add_email_to_history(user.id, result["email"],
                                 dropmail_session_id=result["session_id"],
                                 address_id=result["address_id"],
                                 restore_key=result["restore_key"])

        await asyncio.to_thread(_persist)
        await query.edit_message_text(f"<code>{result['email']}</code>", parse_mode="HTML")

    elif query.data == "delete_email":
        session = await asyncio.to_thread(get_session, user.id)
        address_id = session.get("address_id") if session else None
        if address_id:
            await asyncio.to_thread(dropmail.delete_address, address_id)
        await asyncio.to_thread(deactivate_session, user.id)
        await query.edit_message_text(
            "🗑 <b>អ៊ីម៉ែលត្រូវបានលុបចោលហើយ។</b>\n\n"
            "ចុច <b>📧 អ៊ីម៉ែលថ្មី</b> ដើម្បីបង្កើតថ្មី។",
            parse_mode="HTML"
        )

    elif query.data.startswith("del_email:"):
        email_to_delete = query.data[len("del_email:"):]
        entry = await asyncio.to_thread(get_history_entry_by_email, user.id, email_to_delete)
        if not entry:
            await query.edit_message_text(f"❌ រកមិនឃើញ <code>{email_to_delete}</code>", parse_mode="HTML")
            return
        if entry.get("address_id"):
            await asyncio.to_thread(dropmail.delete_address, entry["address_id"])
        await asyncio.to_thread(remove_email_from_history, entry["id"])
        session = await asyncio.to_thread(get_session, user.id)
        if session and session.get("email_address") == email_to_delete:
            await asyncio.to_thread(deactivate_session, user.id)
        await query.edit_message_text(
            f"🗑 លុប <code>{email_to_delete}</code> បានសម្រេច។",
            parse_mode="HTML"
        )


# ── Background email polling — keeps EVERY history email alive ────────────────
async def _poll_one(entry: dict, context: ContextTypes.DEFAULT_TYPE):
    history_id    = entry["id"]
    user_id       = entry["telegram_user_id"]
    session_id    = entry["dropmail_session_id"]
    email_address = entry["email_address"]
    restore_key   = entry["restore_key"]
    last_mail_id  = entry.get("last_mail_id")

    if not session_id:
        return

    try:
        mails = await asyncio.to_thread(
            dropmail.get_new_mails, session_id, last_mail_id
        )
    except Exception as e:
        logger.warning(f"Poll error [{email_address}]: {e}")
        return

    # ── Auto-restore silently when session expires ────────────────────────
    if mails is None:
        logger.info(f"Restoring [{email_address}] for user {user_id}...")
        try:
            restored = await asyncio.to_thread(
                dropmail.restore_session, email_address, restore_key
            )
        except Exception as e:
            logger.warning(f"Restore failed [{email_address}]: {e}")
            return

        if restored:
            def _persist_restore():
                update_history_session(
                    history_id,
                    new_session_id=restored["session_id"],
                    new_address_id=restored.get("address_id"),
                    new_restore_key=restored.get("restore_key"),
                )
                cur_sess = get_session(user_id)
                if cur_sess and cur_sess.get("email_address") == email_address:
                    update_session_after_restore(
                        telegram_user_id=user_id,
                        new_session_id=restored["session_id"],
                        new_address_id=restored.get("address_id"),
                        new_restore_key=restored.get("restore_key"),
                    )
            await asyncio.to_thread(_persist_restore)
            logger.info(f"Restored [{email_address}] → new session {restored['session_id']}")
        return

    # ── Forward new emails ────────────────────────────────────────────────
    if not mails:
        return

    newest_id = None
    for mail in mails:
        mail_id = mail.get("id")
        if last_mail_id and mail_id == last_mail_id:
            continue

        subject   = mail.get("headerSubject") or "(គ្មានប្រធានបទ)"
        from_addr = mail.get("fromAddr") or "unknown"
        to_addr   = mail.get("toAddr") or email_address
        body      = (mail.get("text") or "").strip()
        preview   = body[:800] + "\n…" if len(body) > 800 else body

        text = (
            f"📬 <b>អ៊ីម៉ែលថ្មីចូលមកដល់!</b>\n\n"
            f"📧 ទៅ: <code>{to_addr}</code>\n"
            f"👤 ពី: <code>{from_addr}</code>\n"
            f"📝 ប្រធានបទ: <b>{subject}</b>\n\n"
            f"{'─' * 28}\n"
            f"{preview if preview else '<i>(ទទេ)</i>'}"
        )

        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=text,
                parse_mode="HTML"
            )
            await asyncio.to_thread(log_mail, user_id, from_addr, to_addr, subject, body)
        except Exception as e:
            logger.warning(f"Failed to notify user {user_id}: {e}")

        if TARGET_CHANNEL_ID and TARGET_CHANNEL_ID != user_id:
            try:
                await context.bot.send_message(
                    chat_id=TARGET_CHANNEL_ID,
                    text=text,
                    parse_mode="HTML"
                )
            except Exception as e:
                logger.warning(f"Failed to forward to channel {TARGET_CHANNEL_ID}: {e}")

        newest_id = mail_id

    if newest_id:
        await asyncio.to_thread(update_history_last_mail_id, history_id, newest_id)


async def poll_emails(context: ContextTypes.DEFAULT_TYPE):
    entries = await asyncio.to_thread(get_all_history_entries)
    if not entries:
        return
    await asyncio.gather(
        *[_poll_one(entry, context) for entry in entries],
        return_exceptions=True,
    )


# ── Proactive restore — keeps ALL history emails active every 10 min ──────────
async def _restore_one(entry: dict):
    history_id    = entry["id"]
    user_id       = entry["telegram_user_id"]
    email_address = entry["email_address"]
    restore_key   = entry["restore_key"]

    if not restore_key:
        return

    try:
        restored = await asyncio.to_thread(
            dropmail.restore_session, email_address, restore_key
        )
    except Exception as e:
        logger.warning(f"Proactive restore failed [{email_address}]: {e}")
        return

    if restored:
        def _persist():
            update_history_session(
                history_id,
                new_session_id=restored["session_id"],
                new_address_id=restored.get("address_id"),
                new_restore_key=restored.get("restore_key"),
            )
            cur_sess = get_session(user_id)
            if cur_sess and cur_sess.get("email_address") == email_address:
                update_session_after_restore(
                    telegram_user_id=user_id,
                    new_session_id=restored["session_id"],
                    new_address_id=restored.get("address_id"),
                    new_restore_key=restored.get("restore_key"),
                )
        await asyncio.to_thread(_persist)
        logger.info(f"Proactively restored [{email_address}] → session {restored['session_id']}")


async def proactive_restore_all(context: ContextTypes.DEFAULT_TYPE):
    """Every 10 minutes, restore every session in email_history so all emails stay active."""
    entries = await asyncio.to_thread(get_all_history_entries)
    if not entries:
        return
    await asyncio.gather(
        *[_restore_one(entry) for entry in entries],
        return_exceptions=True,
    )


# ── Bot entry point ───────────────────────────────────────────────────────────
def main():
    init_db()
    logger.info("Database initialized.")

    if not BOT_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN is not set!")
    if not dropmail.DROPMAIL_TOKEN:
        raise ValueError("DROPMAIL_API_TOKEN is not set!")

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", send_welcome, filters=ALLOWED))

    app.add_handler(MessageHandler(ALLOWED & filters.Regex(f"^{BTN_NEW_EMAIL}$"), handle_new_email))
    app.add_handler(MessageHandler(ALLOWED & filters.Regex(f"^{BTN_MY_EMAIL}$"),  handle_inbox))
    app.add_handler(MessageHandler(ALLOWED & filters.Regex(f"^{BTN_DELETE}$"),    handle_delete))

    app.add_handler(CallbackQueryHandler(button_callback))

    app.job_queue.run_repeating(poll_emails, interval=POLL_INTERVAL, first=5)
    app.job_queue.run_repeating(proactive_restore_all, interval=RESTORE_INTERVAL, first=30)

    logger.info("Bot starting in Khmer mode...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
