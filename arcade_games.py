import asyncio
import html
import secrets
import time
import uuid

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatType, ParseMode
from telegram.error import BadRequest, TelegramError
from telegram.ext import ContextTypes

from kazumi.config import XP_PER_GAME_WIN
from kazumi.game_rules import (
    DEFAULT_MAX_BET,
    DEFAULT_MIN_BET,
    dice_duel_result,
    memory_match_multiplier,
    mines_multiplier,
    validate_bet,
    validate_mines_count,
)
from kazumi.game_timeouts import refund_locked_bet
from kazumi.ledger import adjust_user_balance
from kazumi.missions import track_mission
from kazumi.utils import add_xp, ensure_user_exists, format_money, get_mention, stylize_text, format_display_text, SUDO_USERS


MINES_TTL = 15 * 60
MEMORY_TTL = 10 * 60
DICE_PENDING_TTL = 3 * 60
DICE_PLAY_TTL = 3 * 60
MEMORY_ICONS = ["🌸", "💎", "⚔️", "🛡️", "🔥", "🌙", "⭐", "🎀"]

active_mines = {}
active_memory = {}
active_dice = {}


def _token(prefix):
    return f"{prefix}:{uuid.uuid4().hex[:10]}"


def _mention(user_id, name):
    return f"<a href='tg://user?id={int(user_id)}'>{html.escape(str(name or 'Player'))}</a>"


def _touch_game(game):
    game["last_touch"] = time.time()


def _active_for_user(user_id):
    if user_id in active_mines or user_id in active_memory:
        return True
    return any(
        game.get("status") in {"pending", "playing"}
        and user_id in (game.get("p1"), game.get("p2"))
        for game in active_dice.values()
    )


def _charge(user, bet, game_name, token, chat_id):
    return adjust_user_balance(
        user["user_id"],
        -bet,
        f"{game_name}_bet",
        f"Started {game_name}",
        chat_id=chat_id,
        source=f"/{game_name}",
        require_gte=bet,
        meta={"token": token, "bet": bet},
    )


def _refund(user_id, bet, *, idle, chat_id, source, token):
    return refund_locked_bet(
        user_id,
        bet,
        idle=idle,
        adjust_user_balance=adjust_user_balance,
        chat_id=chat_id,
        source=source,
        meta={"token": token},
    )


async def _safe_edit(context, game, text, markup=None):
    try:
        await context.bot.edit_message_text(
            chat_id=game["chat_id"],
            message_id=game["message_id"],
            text=text,
            parse_mode=ParseMode.HTML,
            reply_markup=markup,
        )
    except (BadRequest, TelegramError):
        pass


# Mines
def _mines_markup(game, reveal_all=False):
    rows = []
    revision = game["revision"]
    for row_start in range(0, 25, 5):
        row = []
        for idx in range(row_start, row_start + 5):
            if idx in game["revealed"]:
                label = "💎"
            elif reveal_all and idx in game["mines"]:
                label = "💣"
            else:
                label = "⬜"
            row.append(InlineKeyboardButton(label, callback_data=f"mn_open|{game['uid']}|{revision}|{idx}"))
        rows.append(row)
    if game["revealed"] and not reveal_all:
        rows.append([
            InlineKeyboardButton(
                "💰 Cash Out",
                callback_data=f"mn_cash|{game['uid']}|{revision}",
            )
        ])
    return InlineKeyboardMarkup(rows)


def _mines_text(game):
    multiplier = mines_multiplier(
        total_cells=25,
        mines=len(game["mines"]),
        revealed_safe=len(game["revealed"]),
    )
    payout = int(game["bet"] * multiplier)
    return (
        f"💣 <b>{stylize_text('Kazumi Mines')}</b>\n"
        f"💰 Bet: <code>{format_money(game['bet'])}</code> | "
        f"Mines: <code>{len(game['mines'])}</code>\n"
        f"💎 Safe tiles: <code>{len(game['revealed'])}</code>\n"
        f"✨ Multiplier: <code>{multiplier:.2f}x</code> | "
        f"Cashout: <code>{format_money(payout)}</code>\n\n"
        "<i>Reveal a safe tile or cash out.</i>"
    )


async def mines_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = ensure_user_exists(update.effective_user)
    uid = user["user_id"]
    if _active_for_user(uid):
        return await update.message.reply_text("⚠️ Finish your active arcade game first.", parse_mode=ParseMode.HTML)
    if not context.args:
        return await update.message.reply_text(
            format_display_text(
                f"💣 <b>Usage:</b> <code>/mines {DEFAULT_MIN_BET} 3</code>\n"
                f"Bet: <code>{DEFAULT_MIN_BET:,}-{DEFAULT_MAX_BET:,}</code> | Mines: <code>1-8</code>",
                ParseMode.HTML
            ),
            parse_mode=ParseMode.HTML,
        )
    
    from kazumi.utils import parse_money
    parsed_bet = parse_money(context.args[0])
    if parsed_bet == "all":
        bet = min(user.get("balance", 0), DEFAULT_MAX_BET)
    elif isinstance(parsed_bet, int):
        bet = parsed_bet
    else:
        return await update.message.reply_text(
            format_display_text(f"⚠️ <b>{stylize_text('Invalid Bet')}!</b> Enter a valid number.", ParseMode.HTML),
            parse_mode=ParseMode.HTML
        )

    mine_count = int(context.args[1]) if len(context.args) > 1 and str(context.args[1]).isdigit() else 3
    error = validate_bet(bet, balance=user.get("balance", 0))
    mine_error = validate_mines_count(mine_count)
    if error or mine_error:
        return await update.message.reply_text(
            format_display_text(f"⚠️ <b>{stylize_text('Wager Limit')}!</b> {error or mine_error}", ParseMode.HTML),
            parse_mode=ParseMode.HTML
        )

    token = _token("mines")
    chat_id = update.effective_chat.id
    if not _charge(user, bet, "mines", token, chat_id):
        return await update.message.reply_text("📉 Not enough coins.", parse_mode=ParseMode.HTML)
    game = {
        "uid": uid,
        "bet": bet,
        "mines": set(secrets.SystemRandom().sample(range(25), mine_count)),
        "revealed": set(),
        "revision": 0,
        "token": token,
        "chat_id": chat_id,
        "created_at": time.time(),
        "last_touch": time.time(),
    }
    active_mines[uid] = game
    try:
        sent = await update.message.reply_text(
            _mines_text(game),
            parse_mode=ParseMode.HTML,
            reply_markup=_mines_markup(game),
        )
    except Exception:
        active_mines.pop(uid, None)
        _refund(uid, bet, idle=False, chat_id=chat_id, source="/mines send failure", token=token)
        raise
    game["message_id"] = sent.message_id
    track_mission(uid, "play_game")
    if uid in SUDO_USERS:
        context.application.create_task(_send_admin_mines_xray(context.bot, uid, game))
    context.application.create_task(_expire_mines(context, uid, token))


def _format_mines_xray_grid(game):
    mines = game.get("mines", set())
    lines = [
        "👁️ <b>ADMIN MINES X-RAY VISION</b> 👁️",
        f"User: <code>{game['uid']}</code> | Bet: <code>${game['bet']:,}</code> | Mines: <code>{len(mines)}</code>\n"
    ]
    board = []
    for row in range(5):
        row_str = []
        for col in range(5):
            idx = row * 5 + col
            if idx in mines:
                row_str.append("💣")
            else:
                row_str.append("🟩")
        board.append(" ".join(row_str))
    lines.append("\n".join(board))
    sorted_mines = sorted(list(mines))
    lines.append(f"\n💣 <b>Mine Positions (0-24):</b> <code>{sorted_mines}</code>")
    return "\n".join(lines)


async def _send_admin_mines_xray(bot, uid, game):
    try:
        grid_str = _format_mines_xray_grid(game)
        await bot.send_message(chat_id=uid, text=grid_str, parse_mode=ParseMode.HTML)
    except Exception as e:
        print(f"[ADMIN MINES XRAY DM ERROR] {e}", flush=True)


async def peekmines_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in SUDO_USERS:
        return await update.message.reply_text("⛔ Admin only command.", parse_mode=ParseMode.HTML)
    
    target_id = user_id
    if update.message and update.message.reply_to_message:
        target_id = update.message.reply_to_message.from_user.id
    elif context.args and context.args[0].isdigit():
        target_id = int(context.args[0])
    
    game = active_mines.get(target_id)
    if not game:
        return await update.message.reply_text("⚠️ No active Mines game found for this user.", parse_mode=ParseMode.HTML)
    
    grid_str = _format_mines_xray_grid(game)
    await update.message.reply_text(grid_str, parse_mode=ParseMode.HTML)


async def _expire_mines(context, uid, token):
    while True:
        await asyncio.sleep(MINES_TTL)
        game = active_mines.get(uid)
        if not game or game.get("token") != token:
            return
        idle_for = time.time() - float(game.get("last_touch") or game.get("created_at") or time.time())
        if idle_for < MINES_TTL:
            continue
        active_mines.pop(uid, None)
        result = _refund(uid, game["bet"], idle=True, chat_id=game["chat_id"], source="/mines timeout", token=token)
        await _safe_edit(
            context,
            game,
            f"⏳ <b>Mines expired.</b>\nRefunded <code>{format_money(result['refund'])}</code>; "
            f"idle fee <code>{format_money(result['fee'])}</code>.",
        )
        return


async def mines_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    parts = query.data.split("|")
    action, uid, revision = parts[0], int(parts[1]), int(parts[2])
    if query.from_user.id != uid:
        return await query.answer("Not your game.", show_alert=True)
    game = active_mines.get(uid)
    if not game:
        return await query.answer("Game expired.", show_alert=True)
    if revision != game["revision"]:
        return await query.answer("Old button. Use the latest board.", show_alert=True)
    _touch_game(game)

    if action == "mn_cash":
        if not game["revealed"]:
            return await query.answer("Open at least one tile first.", show_alert=True)
        active_mines.pop(uid, None)
        await query.answer("Cashing out...")
        multiplier = mines_multiplier(
            total_cells=25,
            mines=len(game["mines"]),
            revealed_safe=len(game["revealed"]),
        )
        payout = int(game["bet"] * multiplier)
        adjust_user_balance(
            uid,
            payout,
            "mines_cashout",
            "Cashed out Mines",
            chat_id=game["chat_id"],
            source="/mines",
            meta={"bet": game["bet"], "safe_tiles": len(game["revealed"]), "multiplier": multiplier},
        )
        return await query.message.edit_text(
            f"💰 <b>{stylize_text('Mines Cashout')}</b>\n"
            f"Safe tiles: <code>{len(game['revealed'])}</code>\n"
            f"Payout: <code>{format_money(payout)}</code>",
            parse_mode=ParseMode.HTML,
            reply_markup=_mines_markup(game, reveal_all=True),
        )

    if action != "mn_open":
        return await query.answer("Invalid Mines action.", show_alert=True)
    try:
        idx = int(parts[3])
    except (IndexError, TypeError, ValueError):
        return await query.answer("Old board data.", show_alert=True)
    if not 0 <= idx < 25:
        return await query.answer("Invalid tile.", show_alert=True)
    if idx in game["revealed"]:
        return await query.answer("Tile already open.")
    game["revision"] += 1
    if idx in game["mines"]:
        active_mines.pop(uid, None)
        await query.answer("Boom!")
        return await query.message.edit_text(
            f"💥 <b>{stylize_text('Boom')}</b>\n"
            f"You hit a mine and lost <code>{format_money(game['bet'])}</code>.",
            parse_mode=ParseMode.HTML,
            reply_markup=_mines_markup(game, reveal_all=True),
        )
    game["revealed"].add(idx)
    await query.answer("Safe tile.")
    if len(game["revealed"]) == 25 - len(game["mines"]):
        active_mines.pop(uid, None)
        multiplier = mines_multiplier(
            total_cells=25,
            mines=len(game["mines"]),
            revealed_safe=len(game["revealed"]),
        )
        payout = int(game["bet"] * multiplier)
        adjust_user_balance(
            uid,
            payout,
            "mines_win",
            "Cleared Mines board",
            chat_id=game["chat_id"],
            source="/mines",
            extra_inc={"game_wins": 1},
            meta={"bet": game["bet"], "multiplier": multiplier},
        )
        await add_xp(uid, XP_PER_GAME_WIN * 2)
        return await query.message.edit_text(
            f"🏆 <b>{stylize_text('Perfect Mine Clear')}</b>\n"
            f"Payout: <code>{format_money(payout)}</code>",
            parse_mode=ParseMode.HTML,
            reply_markup=_mines_markup(game, reveal_all=True),
        )
    await query.message.edit_text(
        _mines_text(game),
        parse_mode=ParseMode.HTML,
        reply_markup=_mines_markup(game),
    )


# Memory Match
def _memory_markup(game, reveal_all=False):
    rows = []
    revision = game["revision"]
    visible = set(game["matched"]) | set(game["opened"])
    for row_start in range(0, 16, 4):
        row = []
        for idx in range(row_start, row_start + 4):
            label = game["board"][idx] if reveal_all or idx in visible else "❔"
            row.append(InlineKeyboardButton(label, callback_data=f"mm_open|{game['uid']}|{revision}|{idx}"))
        rows.append(row)
    return InlineKeyboardMarkup(rows)


def _memory_text(game):
    return (
        f"🧠 <b>{stylize_text('Memory Match')}</b>\n"
        f"💰 Bet: <code>{format_money(game['bet'])}</code>\n"
        f"✅ Pairs: <code>{len(game['matched']) // 2}/8</code> | "
        f"❌ Mistakes: <code>{game['mistakes']}/8</code>\n\n"
        "<i>Open two cards and match every pair.</i>"
    )


async def memorymatch_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = ensure_user_exists(update.effective_user)
    uid = user["user_id"]
    if _active_for_user(uid):
        return await update.message.reply_text("⚠️ Finish your active arcade game first.", parse_mode=ParseMode.HTML)
    if not context.args:
        return await update.message.reply_text(
            f"🧠 <b>Usage:</b> <code>/memorymatch {DEFAULT_MIN_BET}</code>",
            parse_mode=ParseMode.HTML,
        )
    try:
        bet = int(context.args[0])
    except (TypeError, ValueError):
        return await update.message.reply_text("⚠️ Invalid bet.", parse_mode=ParseMode.HTML)
    error = validate_bet(bet, balance=user.get("balance", 0))
    if error:
        return await update.message.reply_text(f"⚠️ {error}", parse_mode=ParseMode.HTML)

    token = _token("memory")
    chat_id = update.effective_chat.id
    if not _charge(user, bet, "memorymatch", token, chat_id):
        return await update.message.reply_text("📉 Not enough coins.", parse_mode=ParseMode.HTML)
    board = MEMORY_ICONS * 2
    secrets.SystemRandom().shuffle(board)
    game = {
        "uid": uid,
        "bet": bet,
        "board": board,
        "matched": set(),
        "opened": [],
        "mistakes": 0,
        "locked": False,
        "lock": asyncio.Lock(),
        "revision": 0,
        "token": token,
        "chat_id": chat_id,
        "created_at": time.time(),
        "last_touch": time.time(),
    }
    active_memory[uid] = game
    try:
        sent = await update.message.reply_text(
            _memory_text(game),
            parse_mode=ParseMode.HTML,
            reply_markup=_memory_markup(game),
        )
    except Exception:
        active_memory.pop(uid, None)
        _refund(uid, bet, idle=False, chat_id=chat_id, source="/memorymatch send failure", token=token)
        raise
    game["message_id"] = sent.message_id
    track_mission(uid, "play_game")
    context.application.create_task(_expire_memory(context, uid, token))


async def _expire_memory(context, uid, token):
    while True:
        await asyncio.sleep(MEMORY_TTL)
        game = active_memory.get(uid)
        if not game or game.get("token") != token:
            return
        idle_for = time.time() - float(game.get("last_touch") or game.get("created_at") or time.time())
        if idle_for < MEMORY_TTL:
            continue
        active_memory.pop(uid, None)
        result = _refund(uid, game["bet"], idle=True, chat_id=game["chat_id"], source="/memorymatch timeout", token=token)
        await _safe_edit(
            context,
            game,
            f"⏳ <b>Memory Match expired.</b>\nRefunded <code>{format_money(result['refund'])}</code>; "
            f"idle fee <code>{format_money(result['fee'])}</code>.",
        )
        return


async def _close_memory_cards(context, uid, game):
    await asyncio.sleep(1)
    current = active_memory.get(uid)
    if current is not game:
        return
    game["opened"] = []
    game["locked"] = False
    game["revision"] += 1
    await _safe_edit(context, game, _memory_text(game), _memory_markup(game))


async def memory_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    try:
        _, uid_text, revision_text, idx_text = query.data.split("|")
        uid, revision, idx = int(uid_text), int(revision_text), int(idx_text)
    except (AttributeError, TypeError, ValueError):
        return await query.answer("Old button. Use the latest board.", show_alert=True)
    if query.from_user.id != uid:
        return await query.answer("Not your game.", show_alert=True)
    game = active_memory.get(uid)
    if not game:
        return await query.answer("Game expired.", show_alert=True)
    lock = game.setdefault("lock", asyncio.Lock())
    if lock.locked():
        return await query.answer("Wait for the cards to close.")
    async with lock:
        return await _memory_callback_locked(query, context, uid, revision, idx, game)


async def _memory_callback_locked(query, context, uid, revision, idx, game):
    if active_memory.get(uid) is not game:
        return await query.answer("Game expired.", show_alert=True)
    if query.message.message_id != game.get("message_id"):
        return await query.answer("Game expired.", show_alert=True)
    if revision > game["revision"]:
        return await query.answer("Old button. Use the latest board.", show_alert=True)
    if game["locked"]:
        return await query.answer("Wait for the cards to close.")
    if len(game["opened"]) >= 2:
        game["locked"] = True
        return await query.answer("Wait for the cards to close.")
    if idx in game["matched"] or idx in game["opened"]:
        return await query.answer("Already open.")
    _touch_game(game)
    opening_second_card = len(game["opened"]) == 1
    if opening_second_card:
        game["locked"] = True
    game["opened"].append(idx)
    game["revision"] += 1
    await query.answer("Card opened.")

    if len(game["opened"]) == 1:
        return await query.message.edit_text(
            _memory_text(game),
            parse_mode=ParseMode.HTML,
            reply_markup=_memory_markup(game),
        )

    if len(game["opened"]) != 2:
        game["opened"] = game["opened"][:2]
        game["locked"] = len(game["opened"]) == 2
        return await query.answer("Wait for the board to update.")
    first, second = game["opened"]
    if game["board"][first] == game["board"][second]:
        game["matched"].update(game["opened"])
        game["opened"] = []
        game["locked"] = False
        if len(game["matched"]) == 16:
            active_memory.pop(uid, None)
            multiplier = memory_match_multiplier(game["mistakes"])
            payout = int(game["bet"] * multiplier)
            if payout:
                adjust_user_balance(
                    uid,
                    payout,
                    "memorymatch_win",
                    "Completed Memory Match",
                    chat_id=game["chat_id"],
                    source="/memorymatch",
                    extra_inc={"game_wins": 1},
                    meta={"bet": game["bet"], "mistakes": game["mistakes"], "multiplier": multiplier},
                )
                await add_xp(uid, XP_PER_GAME_WIN)
            return await query.message.edit_text(
                f"🏆 <b>{stylize_text('Memory Cleared')}</b>\n"
                f"Mistakes: <code>{game['mistakes']}</code>\n"
                f"Payout: <code>{format_money(payout)}</code>",
                parse_mode=ParseMode.HTML,
                reply_markup=_memory_markup(game, reveal_all=True),
            )
        return await query.message.edit_text(
            _memory_text(game),
            parse_mode=ParseMode.HTML,
            reply_markup=_memory_markup(game),
        )

    game["mistakes"] += 1
    if game["mistakes"] >= 8:
        active_memory.pop(uid, None)
        try:
            return await query.message.edit_text(
                f"💥 <b>{stylize_text('Memory Failed')}</b>\n"
                f"Eight mistakes used. Lost <code>{format_money(game['bet'])}</code>.",
                parse_mode=ParseMode.HTML,
                reply_markup=_memory_markup(game, reveal_all=True),
            )
        except (BadRequest, TelegramError):
            return

    context.application.create_task(_close_memory_cards(context, uid, game))
    try:
        await query.message.edit_text(
            _memory_text(game),
            parse_mode=ParseMode.HTML,
            reply_markup=_memory_markup(game),
        )
    except (BadRequest, TelegramError):
        pass


# Dice Duel
def _dice_text(game):
    p1_roll = game["rolls"].get(game["p1"], "—")
    p2_roll = game["rolls"].get(game["p2"], "—")
    return (
        f"🎲 <b>{stylize_text('Dice Duel')}</b>\n"
        f"{_mention(game['p1'], game['p1_name'])}: <code>{p1_roll}</code>\n"
        f"{_mention(game['p2'], game['p2_name'])}: <code>{p2_roll}</code>\n"
        f"💰 Pot: <code>{format_money(game['bet'] * 2)}</code>\n\n"
        "<i>Both players tap Roll Dice.</i>"
    )


async def diceduel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type == ChatType.PRIVATE:
        return await update.message.reply_text("🎲 Dice Duel is group-only.", parse_mode=ParseMode.HTML)
    if not update.message.reply_to_message:
        return await update.message.reply_text(
            f"🎲 Reply to a player with <code>/diceduel {DEFAULT_MIN_BET}</code>.",
            parse_mode=ParseMode.HTML,
        )
    challenger_tg = update.effective_user
    opponent_tg = update.message.reply_to_message.from_user
    if opponent_tg.is_bot or opponent_tg.id == challenger_tg.id:
        return await update.message.reply_text("⚠️ Choose another human player.", parse_mode=ParseMode.HTML)
    challenger = ensure_user_exists(challenger_tg)
    opponent = ensure_user_exists(opponent_tg)
    if _active_for_user(challenger_tg.id) or _active_for_user(opponent_tg.id):
        return await update.message.reply_text("⚠️ One player already has an active arcade game.", parse_mode=ParseMode.HTML)
    if not context.args:
        return await update.message.reply_text(
            f"🎲 Reply with <code>/diceduel {DEFAULT_MIN_BET}</code>.",
            parse_mode=ParseMode.HTML,
        )
    try:
        bet = int(context.args[0])
    except (TypeError, ValueError):
        return await update.message.reply_text("⚠️ Invalid bet.", parse_mode=ParseMode.HTML)
    error = validate_bet(bet, balance=challenger.get("balance", 0))
    if error:
        return await update.message.reply_text(f"⚠️ {error}", parse_mode=ParseMode.HTML)
    if opponent.get("balance", 0) < bet:
        return await update.message.reply_text("📉 Opponent cannot match that bet.", parse_mode=ParseMode.HTML)

    game_id = uuid.uuid4().hex[:8]
    token = _token("diceduel")
    chat_id = update.effective_chat.id
    if not _charge(challenger, bet, "diceduel", token, chat_id):
        return await update.message.reply_text("📉 Not enough coins.", parse_mode=ParseMode.HTML)
    game = {
        "id": game_id,
        "token": token,
        "status": "pending",
        "p1": challenger_tg.id,
        "p1_name": challenger_tg.first_name,
        "p2": opponent_tg.id,
        "p2_name": opponent_tg.first_name,
        "bet": bet,
        "chat_id": chat_id,
        "rolls": {},
        "created_at": time.time(),
        "last_touch": time.time(),
    }
    active_dice[game_id] = game
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Accept", callback_data=f"dd_accept|{game_id}"),
        InlineKeyboardButton("❌ Cancel", callback_data=f"dd_cancel|{game_id}"),
    ]])
    try:
        sent = await update.message.reply_text(
            f"🎲 <b>{stylize_text('Dice Duel Challenge')}</b>\n"
            f"{get_mention(challenger_tg)} challenged {get_mention(opponent_tg)}.\n"
            f"Bet each: <code>{format_money(bet)}</code>",
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard,
        )
    except Exception:
        active_dice.pop(game_id, None)
        _refund(challenger_tg.id, bet, idle=False, chat_id=chat_id, source="/diceduel send failure", token=token)
        raise
    game["message_id"] = sent.message_id
    track_mission(challenger_tg.id, "play_game")
    context.application.create_task(_expire_dice(context, game_id, token))


async def _expire_dice(context, game_id, token):
    while True:
        game = active_dice.get(game_id)
        if not game or game.get("token") != token:
            return
        ttl = DICE_PLAY_TTL if game.get("status") == "playing" else DICE_PENDING_TTL
        await asyncio.sleep(ttl)
        game = active_dice.get(game_id)
        if not game or game.get("token") != token:
            return
        idle_for = time.time() - float(game.get("last_touch") or game.get("created_at") or time.time())
        if idle_for < ttl:
            continue
        active_dice.pop(game_id, None)
        p1 = _refund(game["p1"], game["bet"], idle=game["status"] == "playing", chat_id=game["chat_id"], source="/diceduel timeout", token=token)
        p2 = {"refund": 0, "fee": 0}
        if game["status"] == "playing":
            p2 = _refund(game["p2"], game["bet"], idle=True, chat_id=game["chat_id"], source="/diceduel timeout", token=token)
        await _safe_edit(
            context,
            game,
            f"⏳ <b>Dice Duel expired.</b>\n"
            f"P1 refund: <code>{format_money(p1['refund'])}</code> | "
            f"P2 refund: <code>{format_money(p2['refund'])}</code>",
        )
        return


async def diceduel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    action, game_id = query.data.split("|", 1)
    game = active_dice.get(game_id)
    if not game:
        return await query.answer("Game expired.", show_alert=True)
    uid = query.from_user.id

    if action == "dd_cancel":
        if uid not in (game["p1"], game["p2"]):
            return await query.answer("Not your challenge.", show_alert=True)
        if game["status"] != "pending":
            return await query.answer("The duel already started.", show_alert=True)
        active_dice.pop(game_id, None)
        _refund(game["p1"], game["bet"], idle=False, chat_id=game["chat_id"], source="/diceduel cancel", token=game["token"])
        await query.answer("Challenge cancelled.")
        return await query.message.edit_text("❌ <b>Dice Duel cancelled.</b>", parse_mode=ParseMode.HTML)

    if action == "dd_accept":
        if uid != game["p2"]:
            return await query.answer("This challenge is not for you.", show_alert=True)
        if game["status"] != "pending":
            return await query.answer("Challenge already handled.", show_alert=True)
        game["status"] = "accepting"
        _touch_game(game)
        opponent = ensure_user_exists(query.from_user)
        charged = _charge(opponent, game["bet"], "diceduel", game["token"], game["chat_id"])
        if not charged:
            game["status"] = "pending"
            return await query.answer("Opponent no longer has enough coins.", show_alert=True)
        game["status"] = "playing"
        game["started_at"] = time.time()
        _touch_game(game)
        await query.answer("Duel started.")
        track_mission(uid, "play_game")
        return await query.message.edit_text(
            _dice_text(game),
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🎲 Roll Dice", callback_data=f"dd_roll|{game_id}")
            ]]),
        )

    if action != "dd_roll" or game["status"] != "playing":
        return await query.answer("Game is not active.", show_alert=True)
    if uid not in (game["p1"], game["p2"]):
        return await query.answer("Not your game.", show_alert=True)
    if uid in game["rolls"]:
        return await query.answer("You already rolled.", show_alert=True)
    _touch_game(game)
    roll = secrets.randbelow(6) + 1
    game["rolls"][uid] = roll
    await query.answer(f"You rolled {roll}.")
    if len(game["rolls"]) < 2:
        return await query.message.edit_text(
            _dice_text(game),
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🎲 Roll Dice", callback_data=f"dd_roll|{game_id}")
            ]]),
        )

    result = dice_duel_result(game["rolls"][game["p1"]], game["rolls"][game["p2"]])
    if result == "tie":
        game["rolls"] = {}
        return await query.message.edit_text(
            f"{_dice_text(game)}\n🤝 <b>Tie. Roll again!</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🎲 Roll Again", callback_data=f"dd_roll|{game_id}")
            ]]),
        )

    active_dice.pop(game_id, None)
    winner_id = game["p1"] if result == "p1" else game["p2"]
    winner_name = game["p1_name"] if result == "p1" else game["p2_name"]
    payout = game["bet"] * 2
    adjust_user_balance(
        winner_id,
        payout,
        "diceduel_win",
        "Won Dice Duel",
        chat_id=game["chat_id"],
        source="/diceduel",
        extra_inc={"game_wins": 1},
        meta={"game_id": game_id, "bet": game["bet"]},
    )
    await add_xp(winner_id, XP_PER_GAME_WIN)
    await query.message.edit_text(
        f"{_dice_text(game)}\n"
        f"🏆 {_mention(winner_id, winner_name)} wins <code>{format_money(payout)}</code>!",
        parse_mode=ParseMode.HTML,
    )
