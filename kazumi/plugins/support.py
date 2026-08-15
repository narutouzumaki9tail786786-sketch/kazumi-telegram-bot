import uuid

from telegram import LabeledPrice, Update
from telegram.error import BadRequest
from telegram.constants import ChatType, ParseMode
from telegram.ext import ContextTypes

import kazumi.config as cfg
from kazumi.utils import Button, ensure_user_exists, get_mention, log_to_channel, stylize_text


SUPPORT_AMOUNTS = (10, 25, 50, 100)
SUPPORT_PAYLOAD_PREFIX = "kazumi_support"
SUPPORT_CURRENCY = "XTR"


def support_payload(user_id: int, amount: int) -> str:
    return f"{SUPPORT_PAYLOAD_PREFIX}|{int(user_id)}|{int(amount)}|{uuid.uuid4().hex[:8]}"


def parse_support_payload(payload: str):
    parts = str(payload or "").split("|")
    if len(parts) != 4 or parts[0] != SUPPORT_PAYLOAD_PREFIX:
        return None
    try:
        return {
            "user_id": int(parts[1]),
            "amount": int(parts[2]),
            "token": parts[3],
        }
    except (TypeError, ValueError):
        return None


def support_text() -> str:
    return (
        f"🌸 <b>{stylize_text('Kazumi Support')}</b>\n"
        "━━━━━━━━━━━━\n\n"
        "Enjoying Kazumi?\n"
        "Send a small Star boost to support:\n"
        "• faster updates\n"
        "• new games\n"
        "• smoother service\n"
        "• better features\n\n"
        "Every bit helps. 🤍"
    )


def support_keyboard(bot_username: str):
    dm_link = f"https://t.me/{bot_username}?start=support"
    rows = [
        [Button(f"⭐ {amount}", callback_data=f"support_buy|{amount}") for amount in SUPPORT_AMOUNTS[:2]],
        [Button(f"⭐ {amount}", callback_data=f"support_buy|{amount}") for amount in SUPPORT_AMOUNTS[2:]],
        [
            Button("📣 Updates", url=cfg.SUPPORT_CHANNEL, style="primary"),
            Button("💬 Community", url=cfg.SUPPORT_GROUP, style="success"),
        ],
        [
            Button("🔄 Refresh", callback_data="support_open", style="primary"),
            Button("👤 Owner", url=cfg.OWNER_LINK, style="primary"),
        ],
    ]
    # Group-safe open in DM shortcut
    rows.append([Button("🌸 Open In DM", url=dm_link, style="success")])
    from telegram import InlineKeyboardMarkup

    return InlineKeyboardMarkup(rows)


async def _send_support_invoice(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_id: int, amount: int):
    await context.bot.send_invoice(
        chat_id=chat_id,
        title="Kazumi Support",
        description=f"Support Kazumi with {amount} Telegram Stars.",
        payload=support_payload(user_id, amount),
        currency=SUPPORT_CURRENCY,
        prices=[LabeledPrice(label=f"Kazumi Support {amount} Stars", amount=amount)],
        provider_token="",
    )


async def support_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    if not user or not chat or not update.effective_message:
        return

    ensure_user_exists(user)
    bot_username = context.bot.username or "KazumiRpgBot"

    if chat.type != ChatType.PRIVATE:
        return await update.effective_message.reply_text(
            "🌸 <b>Open support in DM.</b>\nSend Stars safely from private chat.",
            parse_mode=ParseMode.HTML,
            reply_markup=support_keyboard(bot_username),
        )

    await update.effective_message.reply_text(
        support_text(),
        parse_mode=ParseMode.HTML,
        reply_markup=support_keyboard(bot_username),
        do_quote=False,
    )


async def support_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    try:
        await query.answer()
    except Exception:
        pass
    data = (query.data or "").split("|")
    action = data[0]
    bot_username = context.bot.username or "KazumiRpgBot"

    if action == "support_open":
        try:
            edit_kwargs = {
                "parse_mode": ParseMode.HTML,
                "reply_markup": support_keyboard(bot_username),
            }
            if query.message.photo:
                await query.message.edit_caption(support_text(), **edit_kwargs)
            else:
                await query.message.edit_text(support_text(), **edit_kwargs)
        except Exception as exc:
            if isinstance(exc, BadRequest) and "message is not modified" in str(exc).lower():
                return
            print(f"[SUPPORT OPEN ERROR] {exc}", flush=True)
        return

    if action != "support_buy" or len(data) != 2:
        return

    try:
        amount = int(data[1])
    except (TypeError, ValueError):
        return await query.answer("Invalid amount.", show_alert=True)
    if amount not in SUPPORT_AMOUNTS:
        return await query.answer("Choose a valid amount.", show_alert=True)

    if query.message.chat.type != ChatType.PRIVATE:
        return await query.answer("Open Kazumi in DM to send Stars.", show_alert=True)

    try:
        await _send_support_invoice(context, query.from_user.id, query.from_user.id, amount)
    except Exception as exc:
        print(f"[SUPPORT INVOICE ERROR] {exc}", flush=True)
        return await query.answer("Stars panel failed. Try again in a moment.", show_alert=True)


async def precheckout_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.pre_checkout_query
    if not query:
        return
    payload = parse_support_payload(query.invoice_payload if query else "")
    if not payload:
        # Not a support invoice, answer ok=True so Telegram checkout never gets stuck
        try:
            return await query.answer(ok=True)
        except Exception:
            return
    if payload["user_id"] != query.from_user.id:
        return await query.answer(ok=False, error_message="This support invoice belongs to another user.")
    await query.answer(ok=True)


async def successful_payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    user = update.effective_user
    if not message or not user or not message.successful_payment:
        return

    payment = message.successful_payment
    payload = parse_support_payload(payment.invoice_payload)
    if not payload:
        return

    amount = int(payment.total_amount or payload["amount"])
    await message.reply_text(
        (
            f"🌸 <b>{stylize_text('Thank You')}</b>\n"
            f"Your support of <code>{amount} Stars</code> reached Kazumi.\n\n"
            "It will help fund future updates, smoother service, and more features. 🤍"
        ),
        parse_mode=ParseMode.HTML,
    )
    await log_to_channel(
        context.bot,
        "transfer",
        {
            "user": f"{get_mention(user)} (<code>{user.id}</code>)",
            "chat": "Private",
            "action": f"Supported Kazumi with {amount} Stars",
        },
    )
