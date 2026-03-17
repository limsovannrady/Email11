import os
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
from db import init_db, upsert_session, get_session, get_all_active_sessions, \
    update_last_mail_id, deactivate_session, log_mail, get_stats
import dropmail

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
POLL_INTERVAL = 15

BTN_NEW_EMAIL   = "📧 New Email"
BTN_MY_EMAIL    = "📋 My Email"
BTN_INBOX       = "📥 Check Inbox"
BTN_DELETE      = "🗑 Delete Session"
BTN_STATS       = "📊 Statistics"

MAIN_KEYBOARD = ReplyKeyboardMarkup(
    [
        [KeyboardButton(BTN_NEW_EMAIL), KeyboardButton(BTN_MY_EMAIL)],
        [KeyboardButton(BTN_INBOX),     KeyboardButton(BTN_DELETE)],
        [KeyboardButton(BTN_STATS)],
    ],
    resize_keyboard=True,
    is_persistent=True,
)


async def send_welcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    name = user.first_name or "there"
    text = (
        f"👋 Hello, <b>{name}</b>!\n\n"
        "I'm your <b>TempMail Bot</b> — I create disposable email addresses "
        "and forward any incoming emails directly to this chat.\n\n"
        "👇 Use the buttons below to get started!"
    )
    await update.message.reply_text(text, parse_mode="HTML", reply_markup=MAIN_KEYBOARD)


async def handle_new_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    msg = await update.message.reply_text(
        "⏳ Creating your temporary email address...",
        reply_markup=MAIN_KEYBOARD
    )

    try:
        result = dropmail.create_session()
    except Exception as e:
        await msg.edit_text(f"❌ Failed to create email: {e}")
        return

    if not result:
        await msg.edit_text("❌ Could not create a session. Please try again.")
        return

    upsert_session(
        telegram_user_id=user.id,
        telegram_username=user.username,
        telegram_first_name=user.first_name,
        dropmail_session_id=result["session_id"],
        email_address=result["email"]
    )

    text = (
        f"✅ <b>Your temporary email is ready!</b>\n\n"
        f"📧 <code>{result['email']}</code>\n\n"
        f"👆 Tap the address above to copy it.\n\n"
        f"📬 I'll automatically forward any incoming emails to this chat.\n"
        f"⚠️ <i>Active for ~10 minutes (extended on each access).</i>"
    )
    inline_kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📥 Check Inbox", callback_data="check_inbox"),
         InlineKeyboardButton("🔄 New Email",   callback_data="new_email")],
        [InlineKeyboardButton("🗑 Delete Session", callback_data="delete_session")],
    ])
    await msg.edit_text(text, parse_mode="HTML", reply_markup=inline_kb)


async def handle_my_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    session = get_session(user.id)

    if not session or not session.get("is_active") or not session.get("email_address"):
        await update.message.reply_text(
            "❌ You don't have an active email session.\n\n"
            "Tap <b>📧 New Email</b> to create one.",
            parse_mode="HTML",
            reply_markup=MAIN_KEYBOARD
        )
        return

    text = (
        f"📧 <b>Your current email address:</b>\n\n"
        f"<code>{session['email_address']}</code>\n\n"
        f"👆 Tap the address to copy it."
    )
    inline_kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📥 Check Inbox",    callback_data="check_inbox"),
         InlineKeyboardButton("🔄 New Email",      callback_data="new_email")],
        [InlineKeyboardButton("🗑 Delete Session", callback_data="delete_session")],
    ])
    await update.message.reply_text(
        text, parse_mode="HTML",
        reply_markup=inline_kb
    )


async def handle_inbox(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await _show_inbox(user.id, reply_to=update.message)


async def handle_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    session = get_session(user.id)

    if not session or not session.get("is_active"):
        await update.message.reply_text(
            "❌ You don't have an active session to delete.",
            reply_markup=MAIN_KEYBOARD
        )
        return

    deactivate_session(user.id)
    await update.message.reply_text(
        "🗑 <b>Session deleted.</b>\n\n"
        "Your temporary email has been deactivated.\n"
        "Tap <b>📧 New Email</b> to create a new one.",
        parse_mode="HTML",
        reply_markup=MAIN_KEYBOARD
    )


async def handle_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    s = get_stats()
    text = (
        "📊 <b>Bot Statistics</b>\n\n"
        f"👥 Total users: <b>{s['total_users']}</b>\n"
        f"📬 Active sessions: <b>{s['active_sessions']}</b>\n"
        f"📧 Emails forwarded: <b>{s['total_emails']}</b>\n"
    )
    await update.message.reply_text(text, parse_mode="HTML", reply_markup=MAIN_KEYBOARD)


async def _show_inbox(user_id: int, reply_to=None, callback_query=None):
    session = get_session(user_id)

    if not session or not session.get("is_active") or not session.get("dropmail_session_id"):
        text = (
            "❌ You don't have an active email session.\n\n"
            "Tap <b>📧 New Email</b> to create one."
        )
        if callback_query:
            await callback_query.edit_message_text(text, parse_mode="HTML")
        elif reply_to:
            await reply_to.reply_text(text, parse_mode="HTML", reply_markup=MAIN_KEYBOARD)
        return

    try:
        mails = dropmail.get_new_mails(session["dropmail_session_id"], after_mail_id=None)
    except Exception as e:
        text = f"❌ Error checking inbox: {e}"
        if callback_query:
            await callback_query.edit_message_text(text)
        elif reply_to:
            await reply_to.reply_text(text, reply_markup=MAIN_KEYBOARD)
        return

    if not mails:
        text = (
            f"📭 <b>Inbox is empty</b>\n\n"
            f"📧 Address: <code>{session['email_address']}</code>\n\n"
            f"No emails yet. I'll notify you automatically when one arrives."
        )
    else:
        text = f"📬 <b>Inbox — {len(mails)} email(s)</b>\n"
        text += f"📧 <code>{session['email_address']}</code>\n\n"
        for i, mail in enumerate(mails[-5:], 1):
            subject  = mail.get("headerSubject") or "(no subject)"
            from_addr = mail.get("fromAddr") or "unknown"
            body     = (mail.get("text") or "").strip()
            preview  = body[:200] + "…" if len(body) > 200 else body
            text += (
                f"━━━━━━━━━━━━━━━━━━\n"
                f"<b>#{i} {subject}</b>\n"
                f"From: <code>{from_addr}</code>\n"
                f"{preview or '<i>(empty)</i>'}\n\n"
            )

    inline_kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Refresh",        callback_data="check_inbox"),
         InlineKeyboardButton("🔄 New Email",      callback_data="new_email")],
        [InlineKeyboardButton("🗑 Delete Session", callback_data="delete_session")],
    ])

    if callback_query:
        await callback_query.edit_message_text(text, parse_mode="HTML", reply_markup=inline_kb)
    elif reply_to:
        await reply_to.reply_text(text, parse_mode="HTML", reply_markup=inline_kb)


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user

    if query.data == "check_inbox":
        await _show_inbox(user.id, callback_query=query)

    elif query.data == "delete_session":
        deactivate_session(user.id)
        await query.edit_message_text(
            "🗑 <b>Session deleted.</b>\n\n"
            "Tap <b>📧 New Email</b> to create a new one.",
            parse_mode="HTML"
        )

    elif query.data == "new_email":
        await query.edit_message_text("⏳ Creating your temporary email address...")
        try:
            result = dropmail.create_session()
        except Exception as e:
            await query.edit_message_text(f"❌ Failed to create email: {e}")
            return

        if not result:
            await query.edit_message_text("❌ Could not create a session. Please try again.")
            return

        upsert_session(
            telegram_user_id=user.id,
            telegram_username=user.username,
            telegram_first_name=user.first_name,
            dropmail_session_id=result["session_id"],
            email_address=result["email"]
        )
        text = (
            f"✅ <b>New temporary email ready!</b>\n\n"
            f"📧 <code>{result['email']}</code>\n\n"
            f"📬 I'll automatically forward any incoming emails to this chat.\n"
            f"⚠️ <i>Active for ~10 min (extended on each access).</i>"
        )
        inline_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📥 Check Inbox",    callback_data="check_inbox"),
             InlineKeyboardButton("🔄 New Email",      callback_data="new_email")],
            [InlineKeyboardButton("🗑 Delete Session", callback_data="delete_session")],
        ])
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=inline_kb)


async def poll_emails(context: ContextTypes.DEFAULT_TYPE):
    sessions = get_all_active_sessions()
    for session in sessions:
        user_id      = session["telegram_user_id"]
        session_id   = session["dropmail_session_id"]
        last_mail_id = session.get("last_mail_id")
        email_address = session.get("email_address", "")

        try:
            mails = dropmail.get_new_mails(session_id, after_mail_id=last_mail_id)
        except Exception as e:
            logger.warning(f"Poll error for user {user_id}: {e}")
            continue

        if not mails:
            continue

        newest_id = None
        for mail in mails:
            mail_id = mail.get("id")
            if last_mail_id and mail_id == last_mail_id:
                continue

            subject   = mail.get("headerSubject") or "(no subject)"
            from_addr = mail.get("fromAddr") or "unknown"
            to_addr   = mail.get("toAddr") or email_address
            body      = (mail.get("text") or "").strip()
            preview   = body[:800] + "\n…" if len(body) > 800 else body

            text = (
                f"📬 <b>New Email Received!</b>\n\n"
                f"📧 To: <code>{to_addr}</code>\n"
                f"👤 From: <code>{from_addr}</code>\n"
                f"📝 Subject: <b>{subject}</b>\n\n"
                f"{'─' * 28}\n"
                f"{preview if preview else '<i>(empty body)</i>'}"
            )

            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=text,
                    parse_mode="HTML"
                )
                log_mail(user_id, from_addr, to_addr, subject, body)
            except Exception as e:
                logger.warning(f"Failed to notify user {user_id}: {e}")

            newest_id = mail_id

        if newest_id:
            update_last_mail_id(user_id, newest_id)


def main():
    init_db()
    logger.info("Database initialized.")

    if not BOT_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN is not set!")
    if not dropmail.DROPMAIL_TOKEN:
        raise ValueError("DROPMAIL_API_TOKEN is not set!")

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", send_welcome))

    app.add_handler(MessageHandler(filters.Regex(f"^{BTN_NEW_EMAIL}$"),  handle_new_email))
    app.add_handler(MessageHandler(filters.Regex(f"^{BTN_MY_EMAIL}$"),   handle_my_email))
    app.add_handler(MessageHandler(filters.Regex(f"^{BTN_INBOX}$"),      handle_inbox))
    app.add_handler(MessageHandler(filters.Regex(f"^{BTN_DELETE}$"),     handle_delete))
    app.add_handler(MessageHandler(filters.Regex(f"^{BTN_STATS}$"),      handle_stats))

    app.add_handler(CallbackQueryHandler(button_callback))

    app.job_queue.run_repeating(poll_emails, interval=POLL_INTERVAL, first=5)

    logger.info("Bot is starting with reply keyboard...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
