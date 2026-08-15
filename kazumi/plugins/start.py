# Copyright (c) 2025 Telegram:- @WTF_Phantom <DevixOP>
# Location: Supaul, Bihar

from telegram import Update, InlineKeyboardMarkup, InputMediaPhoto
from telegram.constants import ChatType, ParseMode
from telegram.error import BadRequest, Forbidden
from telegram.ext import ContextTypes
import asyncio
import traceback

import kazumi.config as cfg
from kazumi.utils import (
    Button,
    SUDO_USERS,
    apply_custom_emojis,
    ensure_user_exists,
    format_display_text,
    get_mention,
    log_to_channel,
    stylize_text,
    track_group,
)

SUDO_IMG = None


async def _run_background(label: str, awaitable):
    """Contain best-effort side work so it cannot produce an unhandled task error."""
    try:
        await awaitable
    except Exception as exc:
        print(f"[START BACKGROUND ERROR] {label}: {exc}", flush=True)


def _schedule_background(label: str, awaitable):
    return asyncio.create_task(_run_background(label, awaitable))


def _is_unreachable_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return isinstance(exc, Forbidden) or any(
        marker in text
        for marker in (
            "bot was blocked",
            "bot was kicked",
            "chat not found",
            "not enough rights to send",
        )
    )


def _is_noop_edit_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return isinstance(exc, BadRequest) and (
        "message is not modified" in text
        or "there is no text in the message to edit" in text
        or "query is too old" in text
    )


def _is_remote_image_url(value) -> bool:
    return str(value or "").lower().startswith(("http://", "https://"))


def emojify(text: str) -> str:
    return apply_custom_emojis(text, remove_fallback=False)


def pretty(text: str) -> str:
    return format_display_text(text, ParseMode.HTML)


def get_start_keyboard(bot_username):
    return InlineKeyboardMarkup([
        [
            Button(f"\U00002795 {stylize_text('Add Me To Group')}", url=f"https://t.me/{bot_username}?startgroup=true", style="success"),
        ],
        [
            Button(f"\U0001F310 {stylize_text('Web Arcade')}", callback_data="help_webarcade", style="success"),
            Button(f"\U00002B50 {stylize_text('Stars & VIP')}", callback_data="help_stars", style="primary"),
        ],
        [
            Button(f"\U0001F4D6 {stylize_text('Menu')}", callback_data="help_main", style="primary"),
            Button(f"\U0001F4E3 {stylize_text('Updates')}", url=cfg.SUPPORT_CHANNEL, style="primary"),
            Button(f"\U00002601\ufe0f {stylize_text('Support')}", url=cfg.SUPPORT_GROUP, style="success"),
        ],
        [
            Button(f"\U00002b50 {stylize_text('Donate Kazumi')}", callback_data="support_open", style="success"),
        ],
    ])


def get_group_start_keyboard():
    return InlineKeyboardMarkup([
        [
            Button("\U0001F525 Tap Race", callback_data="help_multiplayer", style="success"),
            Button("\U0001F3AF Group Games", callback_data="help_multiplayer", style="primary"),
        ],
        [
            Button("\U0001F4D6 Commands", callback_data="help_main", style="primary"),
            Button("\U0001F4E3 Updates", url=cfg.SUPPORT_CHANNEL, style="primary"),
        ],
    ])


def get_help_keyboard():
    return InlineKeyboardMarkup([
        [
            Button(f"\U0001F3AE {stylize_text('Games')}", callback_data="help_games", style="success"),
            Button(f"\U00002694\ufe0f {stylize_text('RPG')}", callback_data="help_rpg", style="primary"),
        ],
        [
            Button(f"\U0001F310 {stylize_text('Web Arcade')}", callback_data="help_webarcade", style="success"),
            Button(f"\U00002B50 {stylize_text('Stars & VIP')}", callback_data="help_stars", style="primary"),
        ],
        [
            Button(
                f"\U0001F465 {stylize_text('Multiplayer')}",
                callback_data="help_multiplayer",
                style="primary",
            ),
        ],
        [
            Button(f"\U0001F49E {stylize_text('Social')}", callback_data="help_social", style="success"),
            Button(f"\U0001F45B {stylize_text('Economy')}", callback_data="help_economy", style="primary"),
        ],
        [
            Button(f"\U0001F365 {stylize_text('AI & Fun')}", callback_data="help_fun", style="success"),
            Button(f"\U000026E9\ufe0f {stylize_text('Group')}", callback_data="help_group", style="primary"),
        ],
        [
            Button(f"\U0001F4E3 {stylize_text('Updates')}", url=cfg.SUPPORT_CHANNEL, style="primary"),
            Button(f"\U00002601\ufe0f {stylize_text('Support')}", url=cfg.SUPPORT_GROUP, style="success"),
            Button(f"\U0001F451 {stylize_text('Owner')}", url=cfg.OWNER_LINK, style="primary"),
        ],
        [
            Button(f"\U0001F519 {stylize_text('Back')}", callback_data="return_start", style="danger"),
        ],
    ])


def get_back_keyboard():
    return InlineKeyboardMarkup([[Button(f"\U0001F519 {stylize_text('Back')}", callback_data="help_main", style="danger")]])


def start_caption(user) -> str:
    user_link = get_mention(user)
    return pretty(
        f"\U0001F44B Konichiwa {user_link}! (&gt;=▽=&lt;)\n"
        f"\U0001F338 {cfg.BOT_NAME} - The Ultimate RPG Bot! \U0001F49E\n\n"
        f"* Games: Blackjack, RPS, Heist, Roulette\n"
        f"* Group Games: TTT, C4, Tap Race, Word Bomb\n"
        f"* RPG: Kill, Rob, Bounty, Tournament, Gang War\n"
        f"* Economy: Level, XP, Shop, Daily, Loans, Missions\n"
        f"* AI: Chatbot, Memory, TTS & Art\n\n"
        f"\U00002728 New: /season, /settings, /cooldowns\n"
        f"Click the buttons below!"
    )


def group_start_caption(chat, user) -> str:
    return pretty(
        f"\U0001F338 <b>{cfg.BOT_NAME}</b>\n"
        f"\U000026E9\ufe0f Group: <b>{chat.title or 'This Group'}</b>\n\n"
        f"\U0001F525 Keep chat active with /taprace\n"
        f"\U0000274C Reply /ttt to challenge someone\n"
        f"\U0001F3AF Try /ttt, /c4, /wordbomb, /taprace\n"
        f"\U0001F3C6 Use /season and /missions for daily activity\n"
        f"\U00002699\ufe0f Admins can use /settings\n\n"
        f"<i>Daily rewards are DM only. Games are made for groups.</i>"
    )


async def send_or_edit_start(update: Update, context: ContextTypes.DEFAULT_TYPE, caption: str, reply_markup):
    query = update.callback_query

    if query:
        await query.answer()
        try:
            if cfg.START_IMG_URL:
                await query.message.edit_media(
                    media=InputMediaPhoto(media=cfg.START_IMG_URL, caption=caption, parse_mode=ParseMode.HTML),
                    reply_markup=reply_markup,
                )
                return True
        except Exception as exc:
            if _is_noop_edit_error(exc):
                return True
            if _is_unreachable_error(exc):
                return False
            print(f"[START CALLBACK PHOTO ERROR] {exc}", flush=True)
            try:
                await query.message.edit_caption(caption=caption, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
            except Exception as caption_exc:
                if _is_noop_edit_error(caption_exc):
                    return True
                if _is_unreachable_error(caption_exc):
                    return False
                try:
                    await query.message.edit_text(caption, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
                except Exception as text_exc:
                    if _is_noop_edit_error(text_exc):
                        return True
                    if _is_unreachable_error(text_exc):
                        return False
                    raise
            return True

    # A remote image URL makes Telegram download the media before the user sees
    # the menu. Preserve fast Telegram file_ids, but send the initial menu as
    # text when the configured artwork is external.
    if cfg.START_IMG_URL and not _is_remote_image_url(cfg.START_IMG_URL):
        try:
            await update.effective_message.reply_photo(
                photo=cfg.START_IMG_URL,
                caption=caption,
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup,
                do_quote=False,
            )
            return True
        except Exception as exc:
            if _is_unreachable_error(exc):
                return False
            print(f"[START PHOTO ERROR] {exc}", flush=True)

    try:
        await update.effective_message.reply_text(
            caption,
            parse_mode=ParseMode.HTML,
            reply_markup=reply_markup,
            do_quote=False,
        )
        return True
    except Exception as exc:
        if _is_unreachable_error(exc):
            return False
        print(f"[START TEXT ERROR] {exc}", flush=True)
        plain_caption = (
            f"Konichiwa {update.effective_user.first_name}!\n"
            f"{cfg.BOT_NAME} - The Ultimate RPG Bot!\n\n"
            "Games: Blackjack, RPS, Heist, Roulette\n"
            "RPG: Kill, Rob, Bounty, Tournament\n"
            "Social: Marry, Couple, Waifu, Gift\n"
            "Economy: Level, XP, Shop, Daily\n"
            "AI: Sassy Chatbot & Art\n\n"
            "New: /profile for your stats card!\n"
            "Click the buttons below!"
        )
        try:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=plain_caption,
                reply_markup=reply_markup,
            )
            return True
        except Exception as fallback_exc:
            if _is_unreachable_error(fallback_exc):
                return False
            raise


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat

    if not user or not chat:
        return

    try:
        _schedule_background("ensure user", asyncio.to_thread(ensure_user_exists, user))
        _schedule_background("track group", asyncio.to_thread(track_group, chat, user))

        if chat.type == ChatType.PRIVATE and context.args and context.args[0].lower() == "support":
            from kazumi.plugins import support as support_plugin
            return await support_plugin.support_command(update, context)

        bot_username = context.bot.username or "KazumiRpgBot"
        caption = group_start_caption(chat, user) if chat.type in (ChatType.GROUP, ChatType.SUPERGROUP) else start_caption(user)
        reply_markup = get_group_start_keyboard() if chat.type in (ChatType.GROUP, ChatType.SUPERGROUP) else get_start_keyboard(bot_username)
        delivered = await send_or_edit_start(
            update=update,
            context=context,
            caption=caption,
            reply_markup=reply_markup,
        )

        if delivered and chat.type == ChatType.PRIVATE and not update.callback_query:
            _schedule_background("command log", log_to_channel(
                context.bot,
                "command",
                {
                    "user": f"{get_mention(user)} (<code>{user.id}</code>)",
                    "action": "Started Bot",
                    "chat": "Private",
                },
            ))
    except Exception as exc:
        if _is_unreachable_error(exc):
            return
        print(f"Start Error: {exc}", flush=True)
        traceback.print_exc()
        if update.effective_message:
            try:
                await update.effective_message.reply_text(
                    "Start failed. Please try again in a moment.",
                    parse_mode=ParseMode.HTML,
                )
            except Exception as reply_exc:
                if not _is_unreachable_error(reply_exc):
                    raise


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    caption = pretty(f"\U0001F4D6 <b>{cfg.BOT_NAME} Diary</b> \U0001F338\n\n<i>Select a category below:</i>")
    try:
        await update.effective_message.reply_photo(
            photo=cfg.HELP_IMG_URL,
            caption=caption,
            parse_mode=ParseMode.HTML,
            reply_markup=get_help_keyboard(),
        )
    except Exception as exc:
        print(f"[HELP PHOTO ERROR] {exc}")
        await update.effective_message.reply_text(caption, parse_mode=ParseMode.HTML, reply_markup=get_help_keyboard())


HELP_SECTIONS = {
    "help_games": (
        "\U0001F3AE <b>Casino & Mini Games</b>\n\n"
        "<b>/blackjack [bet]</b>\n- Classic Blackjack card game (hit/stand)\n\n"
        "<b>/highlow [bet]</b>\n- Risky card streak prediction game\n\n"
        "<b>/wordgame [bet]</b>\n- Unscramble a word for prize coins\n\n"
        "<b>/mines [bet] [1-8]</b>\n- Reveal safe tiles and cash out\n\n"
        "<b>/memorymatch [bet]</b>\n- Match all hidden emoji pairs\n\n"
        "<b>/guess</b>\n- Guess the hidden number (1-100)\n"
        "<b>/guess top</b>\n- Win-rate leaderboard\n\n"
        "<b>/aviator [bet]</b>\n- Text-based crash multiplier\n\n"
        "<b>/colorbet [red/green/violet] [bet]</b>\n- Color prediction wheel\n\n"
        "<b>/rr</b>\n- Russian roulette\n\n"
        "<b>/cf [side] [bet]</b>\n- Coinflip duel\n\n"
        "<b>/dice [bet]</b> | <b>/slots</b>\n- Classic Casino\n\n"
        "<b>/dart</b> | <b>/basket</b> | <b>/bowl</b>\n- Native Telegram dice games"
    ),


    "help_multiplayer": (
        "\U0001F465 <b>Multiplayer Games</b>\n\n"
        "<b>/ludo [bet]</b>\n- Interactive 2P/4P Ludo duel\n\n"
        "<b>/bomb</b> | <b>/pass @user</b>\n- Hot potato ticking bomb tag\n\n"
        "<b>/boss</b> | <b>/attack</b>\n- Co-op World Boss Raids\n\n"
        "<b>/rps [bet]</b>\n- Challenge a player to rock-paper-scissors\n\n"
        "<b>/ttt</b>\n- Reply to a player for Tic Tac Toe\n\n"
        "<b>/c4</b>\n- Reply to challenge Connect 4\n\n"
        "<b>/taprace</b>\n- Fast group tapping race\n\n"
        "<b>/wordbomb</b>\n- Group word survival game\n\n"
        "<b>/diceduel [bet]</b>\n- Reply to a player; both roll for the pot\n\n"
        "<b>/war [bet]</b>\n- Battlefield duel against another player\n\n"
        "<b>/trivia</b>\n- Group quiz for coins"
    ),
    "help_social": (
        "\U0001F48D <b>Social & Love</b>\n\n"
        "<b>/refer</b> | <b>/addbonus</b>\n- Earn 50,000 coins + Mythic pull per group\n\n"
        "<b>/slap</b> | <b>/hug</b> | <b>/kiss</b> | <b>/bite</b> | <b>/pat</b>\n- Anime roleplay actions\n\n"
        "<b>/propose @user</b>\n- Marry someone\n\n"
        "<b>/marry</b>\n- Check status\n\n"
        "<b>/divorce</b>\n- Break up\n\n"
        "<b>/couple</b>\n- Matchmaking fun\n\n"
        "<b>/couples</b> | <b>/ship</b>\n- Daily couple and ship score\n\n"
        "<b>/afk [reason]</b> | <b>/brb [reason]</b>\n- Away status with mention alerts\n\n"
        "<b>/karma</b> | <b>/topkarma</b>\n- Reply reputation system\n\n"
        "<b>/wpropose</b> | <b>/gacha</b>\n- Waifu and harem systems\n\n"
        "<b>/gift [item] @user</b>\n- Gift items/coins"
    ),
    "help_economy": (
        "\U0001F45B <b>Economy & Shop</b>\n\n"
        "<b>/profile</b>\n- Stats card + level\n\n"
        "<b>/bal</b>\n- Wallet & rank\n\n"
        "<b>/support</b>\n- Send Telegram Stars to support Kazumi\n\n"
        "<b>/season</b>\n- Monthly rank and leaderboard\n\n"
        "<b>/missions</b>\n- Today's activity plan\n\n"
        "<b>/cooldowns</b>\n- Daily timers and limits\n\n"
        "<b>/loan</b>\n- Ask, give, repay loans\n\n"
        "<b>/claim</b>\n- One-time group add bonus\n\n"
        "<b>/shop</b>\n- Buy weapons and armor\n\n"
        "<b>/give [amt] [user]</b>\n- Transfer coins\n\n"
        "<b>/daily</b>\n- Streak rewards\n\n"
        "<b>/weekly</b>\n- Weekly reward\n\n"
        "<b>/bet [amt]</b>\n- Quick chance bet\n\n"
        "<b>/spin</b> | <b>/fortune</b>\n- Daily bonus actions\n\n"
        "<b>/bank</b>\n- Deposit, withdraw, interest\n\n"
        "<b>/search @user</b>\n- Find players\n\n"
        "<b>/achievements</b>\n- Badges"
    ),
    "help_rpg": (
        "\U00002694\ufe0f <b>RPG & War</b>\n\n"
        "<b>/boss</b> | <b>/attack</b>\n- Team up to defeat World Bosses\n\n"
        "<b>/kill [user]</b>\n- Murder and loot\n\n"
        "<b>/rob [amt] [user]</b>\n- Steal coins\n\n"
        "<b>/bounty [amt] @user</b>\n- Place bounty\n\n"
        "<b>/heist</b>\n- Bank heist team\n\n"
        "<b>/tournament</b>\n- PvP tournament\n\n"
        "<b>/gang</b>\n- Create, join, status, top\n\n"
        "<b>/gang war [name] [stake]</b>\n- Strategic gang wars\n\n"
        "<b>/war [bet]</b>\n- Battlefield duel\n\n"
        "<b>/raid</b>\n- Pet raid action\n\n"
        "<b>/protect 1d</b>\n- Buy shield\n\n"
        "<b>/revive</b>\n- Instant revive"
    ),
    "help_fun": (
        "\U0001F9E0 <b>AI & Media</b>\n\n"
        "<b>/draw [prompt]</b>\n- Generate anime art\n\n"
        "<b>/speak [text]</b>\n- Cute anime TTS\n\n"
        "<b>/chatbot</b>\n- AI settings\n\n"
        "<b>/memory</b> | <b>/remember</b>\n- Personal memory controls\n\n"
        "<b>/forgetme</b>\n- Clear saved personal memory\n\n"
        "<b>/riddle</b>\n- AI quiz"
    ),
    "help_group": (
        "\U000026E9\ufe0f <b>Group Settings</b>\n\n"
        "<b>/settings</b>\n- Admin control panel\n\n"
        "<b>/welcome on/off</b>\n- Welcome images\n\n"
        "<b>/chatbot</b>\n- Group AI enable/model\n\n"
        "<b>/setstart</b>\n- Owner: update start image\n\n"
        "<b>/ping</b>\n- System status"
    ),
}



async def edit_help_message(query, text, photo, reply_markup):
    caption = pretty(text)
    if not photo:
        try:
            await query.message.edit_text(caption, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
        except Exception:
            await query.message.edit_caption(caption=caption, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
        return
    try:
        await query.message.edit_media(
            InputMediaPhoto(media=photo, caption=caption, parse_mode=ParseMode.HTML),
            reply_markup=reply_markup,
        )
    except Exception as exc:
        print(f"[HELP EDIT PHOTO ERROR] {exc}")
        try:
            await query.message.edit_caption(caption=caption, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
        except Exception:
            await query.message.edit_text(caption, parse_mode=ParseMode.HTML, reply_markup=reply_markup)


async def help_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return

    try:
        await query.answer()
    except Exception:
        pass
    data = query.data

    if data == "return_start":
        await start(update, context)
        return

    if data == "help_main":
        await edit_help_message(
            query,
            f"\U0001F4D6 <b>{cfg.BOT_NAME} Diary</b> \U0001F338\n\n<i>Select a category below:</i>",
            cfg.HELP_IMG_URL,
            get_help_keyboard(),
        )
        return

    if data == "help_webarcade":
        from kazumi.plugins.premium import help_webarcade_callback
        await help_webarcade_callback(update, context)
        return

    if data == "help_stars":
        from kazumi.plugins.premium import help_stars_callback
        await help_stars_callback(update, context)
        return


    if data == "help_sudo":
        if query.from_user.id not in SUDO_USERS:
            await query.answer("\U0000274C Kazumi says owner only!", show_alert=True)
            return
        await edit_help_message(
            query,
            "\U0001F510 <b>Sudo Panel</b>\n\n"
            "<b>/addcoins</b>, <b>/rmcoins</b>\n"
            "<b>/freerevive</b>, <b>/unprotect</b>\n"
            "<b>/broadcast</b>, <b>/cleandb</b>\n"
            "<b>/update</b>, <b>/addsudo</b>",
            SUDO_IMG,
            get_back_keyboard(),
        )
        return

    text = HELP_SECTIONS.get(data)
    if text:
        await edit_help_message(query, text, cfg.HELP_IMG_URL, get_back_keyboard())


async def setstart_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin: reply to a photo to set it as the start image for this process."""
    uid = update.effective_user.id
    if uid != cfg.OWNER_ID and uid not in SUDO_USERS:
        return

    reply = update.effective_message.reply_to_message
    if not reply or not reply.photo:
        await update.effective_message.reply_text(
            pretty("\U000026A0\ufe0f Reply to a photo first."),
            parse_mode=ParseMode.HTML,
        )
        return

    file_id = reply.photo[-1].file_id
    cfg.START_IMG_URL = file_id

    await update.effective_message.reply_photo(
        photo=file_id,
        caption=pretty(f"\U00002705 <b>Start image updated!</b>\n\n<code>{file_id}</code>"),
        parse_mode=ParseMode.HTML,
    )
