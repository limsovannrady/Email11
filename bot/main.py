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
from db import (
    init_db, upsert_session, get_session, get_all_active_sessions,
    update_last_mail_id, update_session_after_restore, deactivate_session,
    log_mail, get_stats,
)
import dropmail

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
POLL_INTERVAL = 15

# ── Button Labels (Khmer) ──────────────────────────────────────────────────────
BTN_NEW_EMAIL  = "📧 អ៊ីម៉ែលថ្មី"
BTN_MY_EMAIL   = "📋 អ៊ីម៉ែលរបស់ខ្ញុំ"
BTN_INBOX      = "📥 ពិនិត្យប្រអប់"
BTN_DELETE     = "🗑 លុបអ៊ីម៉ែល"
BTN_STATS      = "📊 ស្ថិតិ"

MAIN_KEYBOARD = ReplyKeyboardMarkup(
    [
        [KeyboardButton(BTN_NEW_EMAIL),  KeyboardButton(BTN_MY_EMAIL)],
        [KeyboardButton(BTN_INBOX),      KeyboardButton(BTN_DELETE)],
        [KeyboardButton(BTN_STATS)],
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
    text = (
        f"👋 សួស្តី, <b>{name}</b>!\n\n"
        "ខ្ញុំជា <b>TempMail Bot</b> — ខ្ញុំបង្កើតអ៊ីម៉ែលបណ្តោះអាសន្ន "
        "ហើយបញ្ជូនអ៊ីម៉ែលចូលដោយផ្ទាល់មកក្នុង chat នេះ។\n\n"
        "✨ <b>មុខងារ:</b>\n"
        "  • អ៊ីម៉ែលត្រូវបានស្តារឡើងវិញដោយស្វ័យប្រវត្តិ\n"
        "  • ទទួលអ៊ីម៉ែលភ្លាមៗ\n\n"
        "👇 ចុចប៊ូតុងខាងក្រោមដើម្បីចាប់ផ្តើម!"
    )
    await update.message.reply_text(text, parse_mode="HTML", reply_markup=MAIN_KEYBOARD)


# ── 📧 New Email ──────────────────────────────────────────────────────────────
async def handle_new_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    msg = await update.message.reply_text(
        "⏳ កំពុងបង្កើតអ៊ីម៉ែលបណ្តោះអាសន្ន...",
        reply_markup=MAIN_KEYBOARD
    )
    await _create_new_email(user, msg)


async def _create_new_email(user, msg):
    try:
        result = dropmail.create_session()
    except Exception as e:
        await msg.edit_text(f"❌ បង្កើតមិនបានទេ: {e}")
        return

    if not result:
        await msg.edit_text("❌ មិនអាចបង្កើត session បានទេ។ សូមព្យាយាមម្ដងទៀត។")
        return

    upsert_session(
        telegram_user_id=user.id,
        telegram_username=user.username,
        telegram_first_name=user.first_name,
        dropmail_session_id=result["session_id"],
        email_address=result["email"],
        address_id=result["address_id"],
        restore_key=result["restore_key"],
    )

    text = (
        f"✅ <b>អ៊ីម៉ែលបណ្តោះអាសន្នរបស់អ្នក:</b>\n\n"
        f"📧 <code>{result['email']}</code>\n\n"
        f"👆 ចុចលើអ៊ីម៉ែលខាងលើដើម្បីចម្លង។\n\n"
        f"📬 ខ្ញុំនឹងបញ្ជូនអ៊ីម៉ែលចូលមកជូនអ្នកភ្លាមៗ។\n"
        f"🔄 <i>ស្តារឡើងវិញដោយស្វ័យប្រវត្តិបើ session ផុតកំណត់។</i>"
    )
    await msg.edit_text(text, parse_mode="HTML", reply_markup=email_inline_kb())


# ── 📋 My Email ───────────────────────────────────────────────────────────────
async def handle_my_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    session = get_session(user.id)

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


# ── 📥 Check Inbox ────────────────────────────────────────────────────────────
async def handle_inbox(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await _show_inbox(user.id, reply_to=update.message)


# ── 🗑 Delete Email ───────────────────────────────────────────────────────────
async def handle_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    session = get_session(user.id)

    if not session or not session.get("is_active"):
        await update.message.reply_text(
            "❌ អ្នកមិនមាន session ដែលសកម្មទេ។",
            reply_markup=MAIN_KEYBOARD
        )
        return

    # Permanently delete the address from dropmail
    address_id = session.get("address_id")
    if address_id:
        dropmail.delete_address(address_id)

    deactivate_session(user.id)
    await update.message.reply_text(
        "🗑 <b>អ៊ីម៉ែលត្រូវបានលុបចោលហើយ។</b>\n\n"
        "ចុច <b>📧 អ៊ីម៉ែលថ្មី</b> ដើម្បីបង្កើតអ៊ីម៉ែលថ្មីម្ដងទៀត។",
        parse_mode="HTML",
        reply_markup=MAIN_KEYBOARD
    )


# ── 📊 Statistics ─────────────────────────────────────────────────────────────
async def handle_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    s = get_stats()
    text = (
        "📊 <b>ស្ថិតិ Bot</b>\n\n"
        f"👥 អ្នកប្រើប្រាស់សរុប: <b>{s['total_users']}</b>\n"
        f"📬 Session សកម្ម: <b>{s['active_sessions']}</b>\n"
        f"📧 អ៊ីម៉ែលបានបញ្ជូន: <b>{s['total_emails']}</b>\n"
    )
    await update.message.reply_text(text, parse_mode="HTML", reply_markup=MAIN_KEYBOARD)


# ── Show Inbox (shared helper) ────────────────────────────────────────────────
async def _show_inbox(user_id: int, reply_to=None, callback_query=None):
    session = get_session(user_id)

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
        mails = dropmail.get_new_mails(session["dropmail_session_id"], after_mail_id=None)
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
    await query.answer()
    user = query.from_user

    if query.data == "check_inbox":
        await _show_inbox(user.id, callback_query=query)

    elif query.data == "new_email":
        await query.edit_message_text("⏳ កំពុងបង្កើតអ៊ីម៉ែលបណ្តោះអាសន្ន...")
        try:
            result = dropmail.create_session()
        except Exception as e:
            await query.edit_message_text(f"❌ បង្កើតមិនបានទេ: {e}")
            return
        if not result:
            await query.edit_message_text("❌ មិនអាចបង្កើត session បានទេ។ សូមព្យាយាមម្ដងទៀត។")
            return
        upsert_session(
            telegram_user_id=user.id,
            telegram_username=user.username,
            telegram_first_name=user.first_name,
            dropmail_session_id=result["session_id"],
            email_address=result["email"],
            address_id=result["address_id"],
            restore_key=result["restore_key"],
        )
        text = (
            f"✅ <b>អ៊ីម៉ែលថ្មីបណ្តោះអាសន្ន:</b>\n\n"
            f"📧 <code>{result['email']}</code>\n\n"
            f"📬 ខ្ញុំនឹងបញ្ជូនអ៊ីម៉ែលចូលមកជូនអ្នកភ្លាមៗ។\n"
            f"🔄 <i>ស្តារឡើងវិញដោយស្វ័យប្រវត្តិ។</i>"
        )
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=email_inline_kb())

    elif query.data == "delete_email":
        session = get_session(user.id)
        address_id = session.get("address_id") if session else None
        if address_id:
            dropmail.delete_address(address_id)
        deactivate_session(user.id)
        await query.edit_message_text(
            "🗑 <b>អ៊ីម៉ែលត្រូវបានលុបចោលហើយ។</b>\n\n"
            "ចុច <b>📧 អ៊ីម៉ែលថ្មី</b> ដើម្បីបង្កើតថ្មី។",
            parse_mode="HTML"
        )


# ── Background email polling ──────────────────────────────────────────────────
async def poll_emails(context: ContextTypes.DEFAULT_TYPE):
    sessions = get_all_active_sessions()
    for session in sessions:
        user_id       = session["telegram_user_id"]
        session_id    = session["dropmail_session_id"]
        last_mail_id  = session.get("last_mail_id")
        email_address = session.get("email_address", "")
        restore_key   = session.get("restore_key")

        try:
            mails = dropmail.get_new_mails(session_id, after_mail_id=last_mail_id)
        except Exception as e:
            logger.warning(f"Poll error for user {user_id}: {e}")
            continue

        # ── Auto-restore if session expired ──────────────────────────────────
        if mails is None:
            if not restore_key or not email_address:
                deactivate_session(user_id)
                try:
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=(
                            "⚠️ <b>Session ផុតកំណត់ ហើយមិនអាចស្តារបានទេ។</b>\n\n"
                            "ចុច <b>📧 អ៊ីម៉ែលថ្មី</b> ដើម្បីបង្កើតថ្មី។"
                        ),
                        parse_mode="HTML"
                    )
                except Exception:
                    pass
                continue

            logger.info(f"Session expired for user {user_id}, auto-restoring...")
            try:
                restored = dropmail.restore_session(email_address, restore_key)
            except Exception as e:
                logger.warning(f"Restore failed for user {user_id}: {e}")
                restored = None

            if restored:
                update_session_after_restore(
                    telegram_user_id=user_id,
                    new_session_id=restored["session_id"],
                    new_address_id=restored.get("address_id"),
                    new_restore_key=restored.get("restore_key"),
                )
                logger.info(f"Restored session for user {user_id}: {restored['session_id']}")
                try:
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=(
                            f"🔄 <b>Session ត្រូវបានស្តារឡើងវិញដោយស្វ័យប្រវត្តិ!</b>\n\n"
                            f"📧 អ៊ីម៉ែលរបស់អ្នកនៅដដែល: <code>{email_address}</code>"
                        ),
                        parse_mode="HTML"
                    )
                except Exception:
                    pass
            else:
                deactivate_session(user_id)
                try:
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=(
                            "❌ <b>ស្តារ session មិនបានទេ។</b>\n\n"
                            "ចុច <b>📧 អ៊ីម៉ែលថ្មី</b> ដើម្បីបង្កើតថ្មី។"
                        ),
                        parse_mode="HTML"
                    )
                except Exception:
                    pass
            continue

        # ── Forward new emails ────────────────────────────────────────────────
        if not mails:
            continue

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
                log_mail(user_id, from_addr, to_addr, subject, body)
            except Exception as e:
                logger.warning(f"Failed to notify user {user_id}: {e}")

            newest_id = mail_id

        if newest_id:
            update_last_mail_id(user_id, newest_id)


# ── Bot entry point ───────────────────────────────────────────────────────────
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

    logger.info("Bot starting in Khmer mode...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
