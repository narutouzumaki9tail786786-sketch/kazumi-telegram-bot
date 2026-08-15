from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatType, ParseMode
from telegram.ext import ContextTypes

from kazumi.database import chatbot_collection, groups_collection
from kazumi.plugins.memory import public_memory_payload
from kazumi.utils import ensure_user_exists, stylize_text


async def is_group_admin(chat, user_id):
    member = await chat.get_member(user_id)
    return member.status in ("administrator", "creator")


def status_text(value):
    return "ON" if value else "OFF"


def settings_keyboard(group_doc, ai_doc):
    welcome_on = bool(group_doc.get("welcome_enabled", False))
    ai_on = bool(ai_doc.get("enabled", True))
    waifu_on = bool(group_doc.get("waifu_drops_enabled", True))
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(f"Welcome: {status_text(welcome_on)}", callback_data="settings_toggle|welcome"),
            InlineKeyboardButton(f"AI Chat: {status_text(ai_on)}", callback_data="settings_toggle|ai"),
        ],
        [
            InlineKeyboardButton(f"Waifu Drops: {status_text(waifu_on)}", callback_data="settings_toggle|waifu"),
            InlineKeyboardButton("Refresh", callback_data="settings_refresh"),
        ],
    ])


def group_settings_text(chat, group_doc, ai_doc):
    claimed = bool(group_doc.get("claimed", False))
    ai_model = ai_doc.get("model", "groq")
    waifu_on = bool(group_doc.get("waifu_drops_enabled", True))
    return (
        f"⚙️ <b>{stylize_text('Group Settings')}</b>\n\n"
        f"<b>Group:</b> {chat.title or 'This group'}\n"
        f"<b>Welcome:</b> <code>{status_text(group_doc.get('welcome_enabled', False))}</code>\n"
        f"<b>AI Chat:</b> <code>{status_text(ai_doc.get('enabled', True))}</code>\n"
        f"<b>Waifu Drops:</b> <code>{status_text(waifu_on)}</code>\n"
        f"<b>AI Model:</b> <code>{ai_model}</code>\n"
        f"<b>Claim Bonus Used:</b> <code>{status_text(claimed)}</code>\n\n"
        "<b>Quick commands:</b>\n"
        "<code>/welcome on</code> | <code>/welcome off</code>\n"
        "<code>/waifudrop on</code> | <code>/waifudrop off</code>\n"
        "<code>/chatbot</code> for model and history controls"
    )


def private_settings_text(user_id):
    memory = public_memory_payload(user_id)
    return (
        f"\U00002699\ufe0f <b>{stylize_text('Kazumi Settings')}</b>\n\n"
        f"<b>Personal memory:</b> <code>{memory['count']}/{memory['limit']}</code>\n"
        "<b>AI Chat:</b> <code>ON in DM</code>\n"
        "<b>Mini App:</b> use Telegram Open button\n\n"
        "<b>Controls:</b>\n"
        "<code>/memory</code> - show saved facts\n"
        "<code>/forgetme</code> - clear personal memory\n"
        "<code>/chatbot</code> - AI model/history panel\n"
        "<code>/cooldowns</code> - daily timers"
    )


async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = ensure_user_exists(update.effective_user)
    chat = update.effective_chat

    if chat.type == ChatType.PRIVATE:
        return await update.message.reply_text(private_settings_text(user["user_id"]), parse_mode=ParseMode.HTML)

    if not await is_group_admin(chat, update.effective_user.id):
        return await update.message.reply_text("\U0000274C <b>Admin only.</b>", parse_mode=ParseMode.HTML)

    group_doc = groups_collection.find_one({"chat_id": chat.id}) or {}
    ai_doc = chatbot_collection.find_one({"chat_id": chat.id}) or {}
    await update.message.reply_text(
        group_settings_text(chat, group_doc, ai_doc),
        parse_mode=ParseMode.HTML,
        reply_markup=settings_keyboard(group_doc, ai_doc),
    )


async def settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    chat = query.message.chat
    if chat.type == ChatType.PRIVATE:
        await query.answer()
        return await query.message.edit_text(private_settings_text(query.from_user.id), parse_mode=ParseMode.HTML)

    if not await is_group_admin(chat, query.from_user.id):
        return await query.answer("Admin only.", show_alert=True)

    action = query.data.split("|", 1)[1] if "|" in query.data else query.data.replace("settings_", "")
    if action == "welcome":
        group_doc = groups_collection.find_one({"chat_id": chat.id}) or {}
        new_state = not bool(group_doc.get("welcome_enabled", False))
        groups_collection.update_one({"chat_id": chat.id}, {"$set": {"welcome_enabled": new_state, "title": chat.title}}, upsert=True)
        await query.answer(f"Welcome {status_text(new_state)}")
    elif action == "ai":
        ai_doc = chatbot_collection.find_one({"chat_id": chat.id}) or {}
        new_state = not bool(ai_doc.get("enabled", True))
        chatbot_collection.update_one({"chat_id": chat.id}, {"$set": {"enabled": new_state}}, upsert=True)
        await query.answer(f"AI chat {status_text(new_state)}")
    elif action == "waifu":
        group_doc = groups_collection.find_one({"chat_id": chat.id}) or {}
        new_state = not bool(group_doc.get("waifu_drops_enabled", True))
        groups_collection.update_one({"chat_id": chat.id}, {"$set": {"waifu_drops_enabled": new_state, "title": chat.title}}, upsert=True)
        await query.answer(f"Waifu Drops {status_text(new_state)}")
    elif action == "open_ai":
        return await query.answer("Use /chatbot for model controls.", show_alert=True)
    else:
        await query.answer("Refreshed.")

    group_doc = groups_collection.find_one({"chat_id": chat.id}) or {}
    ai_doc = chatbot_collection.find_one({"chat_id": chat.id}) or {}
    await query.message.edit_text(
        group_settings_text(chat, group_doc, ai_doc),
        parse_mode=ParseMode.HTML,
        reply_markup=settings_keyboard(group_doc, ai_doc),
    )
