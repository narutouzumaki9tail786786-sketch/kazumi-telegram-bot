import urllib.parse
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, MenuButtonWebApp, Update, WebAppInfo
from telegram.constants import ChatType, ParseMode
from telegram.ext import ContextTypes

from kazumi.config import DEFAULT_MAX_BET, WEBAPP_URL
from kazumi.database import users_collection
from kazumi.utils import Button, ensure_user_exists, format_display_text, format_money, parse_money, stylize_text, is_channel_sender


def get_game_webapp_url(game_name: str, bet: int = 1000, user_id: int = 0) -> str:
    base = WEBAPP_URL or "https://kazumi-mini-app.pages.dev"
    params = {
        "game": game_name,
        "bet": str(bet),
        "user": str(user_id),
    }
    return f"{base}?{urllib.parse.urlencode(params)}#{game_name}"


def make_game_button(text: str, webapp_link: str, chat=None):
    """Always use WebAppInfo to launch Telegram native Mini App without browser redirect modal."""
    return Button(text, web_app=WebAppInfo(url=webapp_link))


async def parse_game_bet(update: Update, context: ContextTypes.DEFAULT_TYPE, game_title: str, cmd_name: str, user: dict):
    """Parses bet argument, shows usage example if missing, and verifies real user balance."""
    if is_channel_sender(update):
        await update.effective_message.reply_text(
            "⚠️ <b>Channel Identity Not Supported!</b>\n"
            "Please switch from <i>Channel</i> mode to your <b>Personal Telegram Account</b> to play games.",
            parse_mode=ParseMode.HTML
        )
        return None

    user_coins = int(user.get("balance", 0))

    if not context.args:
        usage_text = (
            f"⚠️ <b>{stylize_text('Bet Amount Required')}!</b>\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"Please specify your coin wager to launch the game.\n\n"
            f"💡 <b>Usage Examples:</b>\n"
            f"• <code>/{cmd_name} 1000</code> ➔ Wager {format_money(1000)} Coins\n"
            f"• <code>/{cmd_name} 5000</code> ➔ Wager {format_money(5000)} Coins\n"
            f"• <code>/{cmd_name} all</code> ➔ Wager All Coins\n\n"
            f"💰 <b>Your Balance:</b> <code>{format_money(user_coins)}</code>"
        )
        await update.message.reply_text(format_display_text(usage_text, ParseMode.HTML), parse_mode=ParseMode.HTML)
        return None

    parsed = parse_money(context.args[0]) if context.args else None
    if parsed == "all":
        bet = min(user_coins, DEFAULT_MAX_BET)
    elif isinstance(parsed, int):
        bet = parsed
    else:
        await update.message.reply_text(
            format_display_text(
                f"⚠️ <b>{stylize_text('Invalid Bet')}!</b> Please enter a valid number (Example: <code>/{cmd_name} 1000</code>).",
                ParseMode.HTML
            ),
            parse_mode=ParseMode.HTML
        )
        return None

    if bet < 100:
        await update.message.reply_text(
            format_display_text(
                f"⚠️ <b>{stylize_text('Minimum Bet Limit')}!</b> <code>$100</code> Coins required to play!",
                ParseMode.HTML
            ),
            parse_mode=ParseMode.HTML
        )
        return None

    if bet > DEFAULT_MAX_BET:
        await update.message.reply_text(
            format_display_text(
                f"⚠️ <b>{stylize_text('Maximum Wager Limit')}!</b>\n━━━━━━━━━━━━━━━━━━━\nMaximum allowed bet for {game_title} is <code>{format_money(DEFAULT_MAX_BET)}</code> coins.",
                ParseMode.HTML
            ),
            parse_mode=ParseMode.HTML
        )
        return None

    if user_coins < bet:
        await update.message.reply_text(
            f"❌ <b>Insufficient Coins!</b>\n"
            f"Required: <code>{format_money(bet)}</code>\n"
            f"Your Balance: <code>{format_money(user_coins)}</code>",
            parse_mode=ParseMode.HTML
        )
        return None

    return bet


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🕹️ WEB ARCADE MINI APP COMMAND HANDLERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def wav_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = ensure_user_exists(update.effective_user)
    chat = update.effective_chat

    bet = await parse_game_bet(update, context, "Cyber Aviator", "wav", user)
    if bet is None:
        return

    webapp_link = get_game_webapp_url("aviator", bet, user["user_id"])

    text = (
        f"🚀 <b>{stylize_text('KAZUMI WEB AVIATOR')}</b> 🎮\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>Host:</b> {update.effective_user.mention_html()}\n"
        f"💰 <b>Target Stake:</b> <code>{format_money(bet)}</code>\n\n"
        "<i>Tap the button below to launch Full-Screen Aviator Crash Arcade inside Telegram Mini App!</i>"
    )

    markup = InlineKeyboardMarkup([
        [make_game_button("🚀 LAUNCH AVIATOR MINI APP 📱", webapp_link, chat)]
    ])

    await update.message.reply_text(
        format_display_text(text, ParseMode.HTML),
        parse_mode=ParseMode.HTML,
        reply_markup=markup,
    )


async def wludo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = ensure_user_exists(update.effective_user)
    chat = update.effective_chat

    bet = await parse_game_bet(update, context, "Cyber Ludo", "wludo", user)
    if bet is None:
        return

    webapp_link = get_game_webapp_url("ludo", bet, user["user_id"])

    text = (
        f"🎲 <b>{stylize_text('KAZUMI WEB LUDO BOARD')}</b> 🎮\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>Host:</b> {update.effective_user.mention_html()}\n"
        f"💰 <b>Stake:</b> <code>{format_money(bet)}</code>\n\n"
        "<i>Tap below to launch 2D Animated Ludo Board inside Telegram Mini App!</i>"
    )

    markup = InlineKeyboardMarkup([
        [make_game_button("🎲 LAUNCH LUDO MINI APP 📱", webapp_link, chat)]
    ])

    await update.message.reply_text(
        format_display_text(text, ParseMode.HTML),
        parse_mode=ParseMode.HTML,
        reply_markup=markup,
    )


async def wmines_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = ensure_user_exists(update.effective_user)
    chat = update.effective_chat

    bet = await parse_game_bet(update, context, "Cyber Mines", "wmines", user)
    if bet is None:
        return

    webapp_link = get_game_webapp_url("mines", bet, user["user_id"])

    text = (
        f"💎 <b>{stylize_text('KAZUMI WEB MINES')}</b> 🎮\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>Player:</b> {update.effective_user.mention_html()}\n"
        f"💰 <b>Stake:</b> <code>{format_money(bet)}</code>\n\n"
        "<i>Tap below to launch 5x5 Minesweeper Grid inside Telegram Mini App!</i>"
    )

    markup = InlineKeyboardMarkup([
        [make_game_button("💎 LAUNCH MINES MINI APP 📱", webapp_link, chat)]
    ])

    await update.message.reply_text(
        format_display_text(text, ParseMode.HTML),
        parse_mode=ParseMode.HTML,
        reply_markup=markup,
    )


async def wspin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = ensure_user_exists(update.effective_user)
    chat = update.effective_chat

    bet = await parse_game_bet(update, context, "Cyber Spin Wheel", "wspin", user)
    if bet is None:
        return

    webapp_link = get_game_webapp_url("spin", bet, user["user_id"])

    text = (
        f"🎰 <b>{stylize_text('KAZUMI MEGA SPIN WHEEL')}</b> 🎮\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>Player:</b> {update.effective_user.mention_html()}\n"
        f"💰 <b>Stake:</b> <code>{format_money(bet)}</code>\n\n"
        "<i>Tap below to spin the 3D Lucky Wheel inside Telegram Mini App!</i>"
    )

    markup = InlineKeyboardMarkup([
        [make_game_button("🎰 LAUNCH SPIN WHEEL MINI APP 📱", webapp_link, chat)]
    ])

    await update.message.reply_text(
        format_display_text(text, ParseMode.HTML),
        parse_mode=ParseMode.HTML,
        reply_markup=markup,
    )


async def wcolor_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = ensure_user_exists(update.effective_user)
    chat = update.effective_chat

    bet = await parse_game_bet(update, context, "Cyber Color Bet", "wcolor", user)
    if bet is None:
        return

    webapp_link = get_game_webapp_url("color", bet, user["user_id"])

    text = (
        f"🔴🟢 <b>{stylize_text('KAZUMI WEB COLOR PREDICTION')}</b> 🎮\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>Player:</b> {update.effective_user.mention_html()}\n"
        f"💰 <b>Stake:</b> <code>{format_money(bet)}</code>\n\n"
        "<i>Tap below to open Color Prediction Wheel inside Telegram Mini App!</i>"
    )

    markup = InlineKeyboardMarkup([
        [make_game_button("🔴🟢 LAUNCH COLOR MINI APP 📱", webapp_link, chat)]
    ])

    await update.message.reply_text(
        format_display_text(text, ParseMode.HTML),
        parse_mode=ParseMode.HTML,
        reply_markup=markup,
    )
