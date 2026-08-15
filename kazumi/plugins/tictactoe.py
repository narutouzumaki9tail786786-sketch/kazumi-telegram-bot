import html
import random
import asyncio
import uuid
import time

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ChatType, ParseMode
from telegram.error import BadRequest, TelegramError
from telegram.ext import ContextTypes

from kazumi.database import users_collection
from kazumi.emojis import EMOJI_IDS
from kazumi.utils import ensure_user_exists, format_money, get_mention, stylize_text
from kazumi.missions import track_many
from kazumi.ledger import adjust_user_balance
from kazumi.game_timeouts import GAME_EXPIRE_SECONDS, refund_locked_bet


active_ttt_games = {}
TTT_MAX_ACTIVE_PER_USER = 2
TTT_EXPIRE_SECONDS = GAME_EXPIRE_SECONDS

WIN_COMBINATIONS = [
    [0, 1, 2], [3, 4, 5], [6, 7, 8],
    [0, 3, 6], [1, 4, 7], [2, 5, 8],
    [0, 4, 8], [2, 4, 6],
]

ICON_X = EMOJI_IDS.get("\u274c")
ICON_O = EMOJI_IDS.get("\u2b55\ufe0f") or EMOJI_IDS.get("\u2b55")
ICON_EMPTY = EMOJI_IDS.get("\u2b1c\ufe0f") or EMOJI_IDS.get("\u2b1c")
ICON_ACCEPT = EMOJI_IDS.get("\u2705")
ICON_DECLINE = EMOJI_IDS.get("\u274c")
ICON_LABEL = "\u200b"


def _icon_button(text, callback_data, icon_id=None):
    kwargs = {"icon_custom_emoji_id": icon_id} if icon_id else {}
    return InlineKeyboardButton(text=text, callback_data=callback_data, **kwargs)


def _cell_text(mark, icon_id):
    if icon_id:
        return ICON_LABEL
    if mark == "X":
        return "\u274c"
    if mark == "O":
        return "\u2b55"
    return "\u2b1c"


def check_win(board):
    for combo in WIN_COMBINATIONS:
        first = board[combo[0]]
        if first != " " and first == board[combo[1]] == board[combo[2]]:
            return first
    return "DRAW" if " " not in board else None


def marker_icon(mark):
    if mark == "X":
        return ICON_X
    if mark == "O":
        return ICON_O
    return ICON_EMPTY


def player_mention(game, user_id):
    name = game["p1_name"] if user_id == game["p1"] else game["p2_name"]
    return f"<a href='tg://user?id={user_id}'>{html.escape(name)}</a>"


async def send_turn_ping(message, game):
    old_id = game.get("turn_ping_message_id")
    text = f"\U0001F449 <b>Your turn:</b> {player_mention(game, game['turn'])}"
    if old_id:
        try:
            await message.get_bot().edit_message_text(
                chat_id=message.chat_id,
                message_id=old_id,
                text=text,
                parse_mode=ParseMode.HTML,
            )
            return
        except TelegramError:
            game["turn_ping_message_id"] = None
    sent = await message.reply_text(
        text,
        parse_mode=ParseMode.HTML,
    )
    game["turn_ping_message_id"] = sent.message_id


async def close_turn_ping(message, game, text="\U0001F3C1 <b>Tic-Tac-Toe finished.</b>"):
    old_id = game.get("turn_ping_message_id")
    if not old_id:
        return
    try:
        await message.get_bot().edit_message_text(
            chat_id=message.chat_id,
            message_id=old_id,
            text=text,
            parse_mode=ParseMode.HTML,
        )
    except TelegramError:
        pass
    game["turn_ping_message_id"] = None


def _touch_game(game):
    game["updated_at"] = time.time()


def _refund_ttt_player(user_id, bet, *, idle, chat_id, game_id):
    return refund_locked_bet(
        user_id,
        bet,
        idle=idle,
        adjust_user_balance=adjust_user_balance,
        chat_id=chat_id,
        source="/ttt timeout",
        meta={"game_id": game_id},
    )


def build_board_markup(game_id, board, status="playing", revision=0):
    keyboard = []
    for i in range(0, 9, 3):
        row = []
        for j in range(3):
            idx = i + j
            mark = board[idx]
            cb_data = f"ttt_clk|{game_id}|{revision}|{idx}" if status == "playing" else "ttt_none"
            icon_id = marker_icon(mark)
            row.append(_icon_button(_cell_text(mark, icon_id), cb_data, icon_id))
        keyboard.append(row)
    return InlineKeyboardMarkup(keyboard)


def active_games_for_user(user_id):
    return sum(
        1 for game in active_ttt_games.values()
        if game.get("status") in {"pending", "playing"} and user_id in (game.get("p1"), game.get("p2"), game.get("challenger"), game.get("opponent"))
    )


async def safe_edit_or_announce(message, text, markup=None):
    try:
        await message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=markup)
        return message.message_id
    except (BadRequest, TelegramError):
        sent = await message.get_bot().send_message(
            chat_id=message.chat_id,
            text=text,
            parse_mode=ParseMode.HTML,
            reply_markup=markup,
        )
        return sent.message_id


async def expire_game_after(context: ContextTypes.DEFAULT_TYPE, chat_id: int, game_id: str, delay: int = TTT_EXPIRE_SECONDS):
    while True:
        game = active_ttt_games.get(game_id)
        if not game or game.get("status") not in {"pending", "playing"}:
            return
        wait_for = delay - (time.time() - float(game.get("updated_at", game.get("created_at", time.time()))))
        if wait_for > 0:
            await asyncio.sleep(wait_for + 1)
            continue
        break
    game = active_ttt_games.get(game_id)
    if not game or game.get("status") not in {"pending", "playing"}:
        return
    bet = int(game.get("bet", 0))
    p1_refund = {"refund": 0, "fee": 0}
    p2_refund = {"refund": 0, "fee": 0}
    if game.get("status") == "playing" and bet > 0:
        turn = game.get("turn")
        p1_refund = _refund_ttt_player(game["p1"], bet, idle=(turn == game["p1"]), chat_id=chat_id, game_id=game_id)
        p2_refund = _refund_ttt_player(game["p2"], bet, idle=(turn == game["p2"]), chat_id=chat_id, game_id=game_id)
    old_ping = game.get("turn_ping_message_id")
    if old_ping:
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=old_ping,
                text="\U000023F3 <b>Tic-Tac-Toe expired.</b>",
                parse_mode=ParseMode.HTML,
            )
        except TelegramError:
            pass
    active_ttt_games.pop(game_id, None)
    if game.get("status") == "pending":
        result_text = "Challenge timed out."
    else:
        result_text = (
            f"X refund: <code>{format_money(p1_refund['refund'])}</code> | fee: <code>{format_money(p1_refund['fee'])}</code>\n"
            f"O refund: <code>{format_money(p2_refund['refund'])}</code> | fee: <code>{format_money(p2_refund['fee'])}</code>"
        )
    try:
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"\U000023F3 <b>Tic-Tac-Toe expired.</b>\n{result_text}",
            parse_mode=ParseMode.HTML,
        )
    except TelegramError:
        pass


def game_header(game):
    pot = game["bet"] * 2
    bet_line = f"\n\U0001F4B0 <b>Pot:</b> <code>{format_money(pot)}</code>" if pot else ""
    return (
        f"\U0001F3AE <b>{stylize_text('Tic Tac Toe')}</b>\n"
        f"\u274C <b>X:</b> {player_mention(game, game['p1'])}\n"
        f"\u2B55 <b>O:</b> {player_mention(game, game['p2'])}"
        f"{bet_line}"
    )


def randomize_first_player(game):
    challenger = (game.get("challenger", game["p1"]), game.get("challenger_name", game["p1_name"]))
    opponent = (game.get("opponent", game["p2"]), game.get("opponent_name", game["p2_name"]))
    players = [
        challenger,
        opponent,
    ]
    if random.SystemRandom().randrange(2) == 1:
        players.reverse()
    game["p1"], game["p1_name"] = players[0]
    game["p2"], game["p2_name"] = players[1]
    game["turn"] = game["p1"]
    game["first_player"] = game["p1"]


async def tictactoe_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    if not message:
        return
    user = update.effective_user
    chat = update.effective_chat
    ensure_user_exists(user)

    if chat.type == ChatType.PRIVATE:
        return await message.reply_text(
            "\U000026E9\ufe0f <b>Tic-Tac-Toe is made for groups.</b>\n"
            "<i>Reply to someone in a group with /ttt.</i>",
            parse_mode=ParseMode.HTML,
        )

    if not message.reply_to_message:
        return await message.reply_text(
            "\U000026A0\ufe0f <b>Reply to a player with /ttt.</b>\n"
            "<code>/ttt</code> or <code>/ttt 500</code>",
            parse_mode=ParseMode.HTML,
        )

    target_user = message.reply_to_message.from_user
    if target_user.is_bot or target_user.id == user.id:
        return await message.reply_text(
            "\U0000274C <b>Choose another human player.</b>",
            parse_mode=ParseMode.HTML,
        )

    ensure_user_exists(target_user)
    bet_amount = int(context.args[0]) if context.args and context.args[0].isdigit() else 0

    if active_games_for_user(user.id) >= TTT_MAX_ACTIVE_PER_USER:
        return await message.reply_text(
            "\U000023F3 <b>You already have active Tic-Tac-Toe games.</b> Finish them first.",
            parse_mode=ParseMode.HTML,
        )
    if active_games_for_user(target_user.id) >= TTT_MAX_ACTIVE_PER_USER:
        return await message.reply_text(
            f"\U000023F3 <b>{html.escape(target_user.first_name)} already has active Tic-Tac-Toe games.</b>",
            parse_mode=ParseMode.HTML,
        )

    if bet_amount > 0:
        p1_doc = users_collection.find_one({"user_id": user.id}) or {}
        p2_doc = users_collection.find_one({"user_id": target_user.id}) or {}
        if p1_doc.get("balance", 0) < bet_amount:
            return await message.reply_text(
                f"\U0001F4C9 You need <code>{format_money(bet_amount)}</code>.",
                parse_mode=ParseMode.HTML,
            )
        if p2_doc.get("balance", 0) < bet_amount:
            return await message.reply_text(
                f"\U0001F4C9 {target_user.first_name} cannot match <code>{format_money(bet_amount)}</code>.",
                parse_mode=ParseMode.HTML,
            )

    game_id = str(uuid.uuid4())[:8]
    now = time.time()
    active_ttt_games[game_id] = {
        "challenger": user.id,
        "challenger_name": user.first_name,
        "opponent": target_user.id,
        "opponent_name": target_user.first_name,
        "p1": user.id,
        "p1_name": user.first_name,
        "p2": target_user.id,
        "p2_name": target_user.first_name,
        "bet": bet_amount,
        "board": [" "] * 9,
        "turn": user.id,
        "status": "pending",
        "revision": 0,
        "chat_id": chat.id,
        "created_at": now,
        "updated_at": now,
        "stop_votes": [],
        "turn_ping_message_id": None,
    }

    keyboard = InlineKeyboardMarkup([
        [_icon_button("Accept", f"ttt_acc|{game_id}", ICON_ACCEPT)],
        [_icon_button("Decline", f"ttt_dec|{game_id}", ICON_DECLINE)],
    ])
    bet_text = f"\n\U0001F4B0 <b>Bet:</b> <code>{format_money(bet_amount)}</code>" if bet_amount else ""

    sent = await message.reply_text(
        f"\U00002694\ufe0f <b>{stylize_text('Tic Tac Toe Challenge')}</b>\n\n"
        f"{get_mention(user)} challenged {get_mention(target_user)}."
        f"{bet_text}\n\n"
        f"<i>{target_user.first_name}, accept to start.</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard,
    )
    active_ttt_games[game_id]["message_id"] = sent.message_id
    asyncio.create_task(expire_game_after(context, chat.id, game_id))
    track_many(user.id, ["group_challenge"])


def find_user_game(chat_id, user_id):
    for game_id, game in active_ttt_games.items():
        if game.get("chat_id") == chat_id and game.get("status") in {"pending", "playing"} and user_id in (game.get("p1"), game.get("p2")):
            return game_id, game
    return None, None


async def edit_or_send_board(context: ContextTypes.DEFAULT_TYPE, chat_id: int, game_id: str, game, text: str):
    markup = build_board_markup(game_id, game["board"], revision=game.get("revision", 0))
    message_id = game.get("message_id")
    if message_id:
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                parse_mode=ParseMode.HTML,
                reply_markup=markup,
            )
            return message_id
        except TelegramError:
            pass
    sent = await context.bot.send_message(chat_id=chat_id, text=text, parse_mode=ParseMode.HTML, reply_markup=markup)
    game["message_id"] = sent.message_id
    return sent.message_id


async def tttboard_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type == ChatType.PRIVATE:
        return await update.message.reply_text("\U000026E9\ufe0f Group only.", parse_mode=ParseMode.HTML)
    game_id, game = find_user_game(update.effective_chat.id, update.effective_user.id)
    if not game:
        return await update.message.reply_text("\U0000274C No active Tic-Tac-Toe game for you here.", parse_mode=ParseMode.HTML)
    mark = "X" if game["turn"] == game["p1"] else "O"
    text = f"{game_header(game)}\n\n\U0001F449 <b>Turn:</b> {mark} - {player_mention(game, game['turn'])}"
    await edit_or_send_board(context, update.effective_chat.id, game_id, game, text)
    await update.message.reply_text("\U0001F6E0 <b>Board recovered.</b> Keep playing.", parse_mode=ParseMode.HTML)


async def tttstop_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type == ChatType.PRIVATE:
        return await update.message.reply_text("\U000026E9\ufe0f Group only.", parse_mode=ParseMode.HTML)
    game_id, game = find_user_game(update.effective_chat.id, update.effective_user.id)
    if not game:
        return await update.message.reply_text("\U0000274C No active Tic-Tac-Toe game for you here.", parse_mode=ParseMode.HTML)

    votes = set(game.get("stop_votes") or [])
    votes.add(update.effective_user.id)
    game["stop_votes"] = list(votes)
    players = {game["p1"], game["p2"]}
    if not players.issubset(votes):
        other_id = game["p2"] if update.effective_user.id == game["p1"] else game["p1"]
        return await update.message.reply_text(
            f"\U000023F3 <b>Stop vote saved.</b>\nNeed agreement from {player_mention(game, other_id)}. They can send <code>/tttstop</code>.",
            parse_mode=ParseMode.HTML,
        )

    if game.get("status") == "playing" and game.get("bet", 0) > 0:
        adjust_user_balance(
            game["p1"],
            game["bet"],
            "ttt_refund",
            "Tic-Tac-Toe stopped by agreement",
            chat_id=game.get("chat_id"),
            source="/tttstop",
            meta={"game_id": game_id, "reason": "mutual_stop"},
        )
        adjust_user_balance(
            game["p2"],
            game["bet"],
            "ttt_refund",
            "Tic-Tac-Toe stopped by agreement",
            chat_id=game.get("chat_id"),
            source="/tttstop",
            meta={"game_id": game_id, "reason": "mutual_stop"},
        )
    await close_turn_ping(update.message, game, "\U0001F6D1 <b>Tic-Tac-Toe stopped by both players.</b>")
    active_ttt_games.pop(game_id, None)
    await update.message.reply_text(
        "\U0001F6D1 <b>Tic-Tac-Toe stopped.</b>\nBoth players agreed, active bet refunded.",
        parse_mode=ParseMode.HTML,
    )


async def tictactoe_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    data = query.data.split("|")
    action = data[0]

    if action == "ttt_none":
        return await query.answer("Game is already over.", show_alert=True)

    game_id = data[1]
    game = active_ttt_games.get(game_id)
    if not game:
        return await query.answer("Game expired.", show_alert=True)

    if action == "ttt_acc":
        if user.id != game["p2"]:
            return await query.answer("This challenge is not for you.", show_alert=True)
        if game["status"] != "pending":
            return await query.answer("This challenge was already handled.", show_alert=True)
        game["status"] = "accepting"
        if game["bet"] > 0:
            p1_charge = adjust_user_balance(
                game["p1"],
                -game["bet"],
                "ttt_bet",
                "Tic-Tac-Toe wager locked",
                chat_id=game.get("chat_id"),
                target_user_id=game["p2"],
                source="/ttt",
                require_gte=game["bet"],
                meta={"game_id": game_id},
            )
            if not p1_charge:
                active_ttt_games.pop(game_id, None)
                await query.answer("Challenge cancelled.", show_alert=True)
                await safe_edit_or_announce(
                    query.message,
                    "\U0000274C <b>Challenge cancelled.</b>\nThe challenger no longer has enough coins.",
                )
                return

            p2_charge = adjust_user_balance(
                game["p2"],
                -game["bet"],
                "ttt_bet",
                "Tic-Tac-Toe wager locked",
                chat_id=game.get("chat_id"),
                target_user_id=game["p1"],
                source="/ttt",
                require_gte=game["bet"],
                meta={"game_id": game_id},
            )
            if not p2_charge:
                adjust_user_balance(
                    game["p1"],
                    game["bet"],
                    "ttt_refund",
                    "Tic-Tac-Toe acceptance rollback",
                    chat_id=game.get("chat_id"),
                    target_user_id=game["p2"],
                    source="/ttt",
                    meta={"game_id": game_id},
                )
                active_ttt_games.pop(game_id, None)
                await query.answer("Challenge cancelled. Challenger refunded.", show_alert=True)
                await safe_edit_or_announce(
                    query.message,
                    "\U0000274C <b>Challenge cancelled.</b>\nThe opponent no longer has enough coins. Challenger refunded.",
                )
                return
        game["status"] = "playing"
        _touch_game(game)
        randomize_first_player(game)
        await query.answer("Challenge accepted.")
        game["message_id"] = await safe_edit_or_announce(
            query.message,
            f"{game_header(game)}\n\n"
            f"\U0001F449 <b>Turn:</b> X - {player_mention(game, game['p1'])}",
            build_board_markup(game_id, game["board"], revision=game.get("revision", 0)),
        )
        asyncio.create_task(asyncio.to_thread(track_many, game["p1"], ["play_game", "group_challenge"]))
        asyncio.create_task(asyncio.to_thread(track_many, game["p2"], ["play_game", "group_challenge"]))
        await send_turn_ping(query.message, game)
        return

    if action == "ttt_dec":
        if user.id not in (game["p1"], game["p2"]):
            return await query.answer("Not your game.", show_alert=True)
        game["status"] = "cancelled"
        await query.answer("Challenge cancelled.")
        game["message_id"] = await safe_edit_or_announce(
            query.message,
            "\U0000274C <b>Tic-Tac-Toe challenge cancelled.</b>",
        )
        active_ttt_games.pop(game_id, None)
        return

    if action != "ttt_clk":
        return

    if game["status"] != "playing":
        return await query.answer("Game is not active.", show_alert=True)

    try:
        if len(data) >= 4:
            clicked_revision = int(data[2])
            idx = int(data[3])
        else:
            clicked_revision = int(game.get("revision", 0))
            idx = int(data[2])
    except (TypeError, ValueError, IndexError):
        return await query.answer("Board data is old. Use /tttboard.", show_alert=True)

    current_message_id = game.get("message_id")
    if current_message_id and getattr(query.message, "message_id", None) != current_message_id:
        return await query.answer("Board updated. Use the latest board.", show_alert=True)
    if clicked_revision != int(game.get("revision", 0)):
        return await query.answer("Board updated. Use the latest board.", show_alert=True)
    if not 0 <= idx < len(game["board"]):
        return await query.answer("Board data is invalid. Use /tttboard.", show_alert=True)

    if user.id != game["turn"]:
        print(
            "[TTT TURN MISMATCH] "
            f"game={game_id} chat={game.get('chat_id')} clicker={user.id} "
            f"turn={game.get('turn')} p1={game.get('p1')} p2={game.get('p2')} "
            f"rev={game.get('revision')} msg={getattr(query.message, 'message_id', None)}",
            flush=True,
        )
        return await query.answer("Not your turn.", show_alert=True)

    if game["board"][idx] != " ":
        return await query.answer("That spot is taken.", show_alert=True)

    is_p1 = user.id == game["p1"]
    mark = "X" if is_p1 else "O"
    game["board"][idx] = mark
    _touch_game(game)
    result = check_win(game["board"])

    if result:
        game["status"] = "finished"
        game["revision"] = int(game.get("revision", 0)) + 1
        markup = build_board_markup(game_id, game["board"], status="finished")
        await query.answer("Game over.")
        if result == "DRAW":
            if game["bet"] > 0:
                adjust_user_balance(
                    game["p1"],
                    game["bet"],
                    "ttt_refund",
                    "Tic-Tac-Toe draw refund",
                    chat_id=game.get("chat_id"),
                    source="/ttt",
                    meta={"game_id": game_id, "result": "draw"},
                )
                adjust_user_balance(
                    game["p2"],
                    game["bet"],
                    "ttt_refund",
                    "Tic-Tac-Toe draw refund",
                    chat_id=game.get("chat_id"),
                    source="/ttt",
                    meta={"game_id": game_id, "result": "draw"},
                )
            text = f"{game_header(game)}\n\n\U0001F91D <b>Draw!</b> Bets returned."
        else:
            winner_id = game["p1"] if result == "X" else game["p2"]
            loser_id = game["p2"] if result == "X" else game["p1"]
            winner_name = game["p1_name"] if result == "X" else game["p2_name"]
            loser_name = game["p2_name"] if result == "X" else game["p1_name"]
            winnings = game["bet"] * 2
            if winnings > 0:
                adjust_user_balance(
                    winner_id,
                    winnings,
                    "ttt_win",
                    "Tic-Tac-Toe win payout",
                    chat_id=game.get("chat_id"),
                    source="/ttt",
                    target_user_id=loser_id,
                    meta={"game_id": game_id, "bet": game["bet"], "mark": result},
                )
            users_collection.update_one({"user_id": winner_id}, {"$inc": {"xp": 40, "game_wins": 1}})
            users_collection.update_one({"user_id": loser_id}, {"$inc": {"game_losses": 1}})
            prize = f"\n\U0001F4B0 <b>Won:</b> <code>{format_money(winnings)}</code>" if winnings else ""
            text = (
                f"{game_header(game)}\n\n"
                f"\U0001F3C6 <b>{html.escape(winner_name)} wins as {result}!</b>{prize}\n"
                f"\U0001F4C9 <b>Loss:</b> {html.escape(loser_name)}"
            )
        await safe_edit_or_announce(query.message, text, markup)
        await close_turn_ping(query.message, game, "\U0001F3C1 <b>Tic-Tac-Toe finished.</b>")
        await query.message.get_bot().send_message(
            chat_id=query.message.chat_id,
            text=f"\U0001F4CC <b>TTT Result Locked</b>\n{text}",
            parse_mode=ParseMode.HTML,
        )
        active_ttt_games.pop(game_id, None)
        return

    game["turn"] = game["p2"] if is_p1 else game["p1"]
    game["revision"] = int(game.get("revision", 0)) + 1
    next_mark = "O" if is_p1 else "X"
    await query.answer("Move saved.")
    game["message_id"] = await safe_edit_or_announce(
        query.message,
        f"{game_header(game)}\n\n"
        f"\U0001F449 <b>Turn:</b> {next_mark} - {player_mention(game, game['turn'])}",
        build_board_markup(game_id, game["board"], revision=game.get("revision", 0)),
    )
    await send_turn_ping(query.message, game)
    return
