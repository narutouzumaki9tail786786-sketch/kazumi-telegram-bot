import uuid
import asyncio
import html
import time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from telegram.error import BadRequest
from kazumi.utils import ensure_user_exists, get_mention, stylize_text, add_xp
from kazumi.database import users_collection
from kazumi.config import XP_PER_GAME_WIN
from kazumi.ledger import adjust_user_balance
from kazumi.game_timeouts import GAME_EXPIRE_SECONDS, refund_locked_bet

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🔴🟡 CONNECT 4
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

ROWS = 6
COLS = 7
active_c4 = {}  # { game_id: { ... } }

DISC = {"p1": "🔴", "p2": "🟡", "empty": "⬜"}

def c4_player_mention(game, user_id):
    name = game["p1_name"] if user_id == game["p1"] else game["p2_name"]
    return f"<a href='tg://user?id={int(user_id)}'>{html.escape(name)}</a>"

def create_board():
    return [["empty"] * COLS for _ in range(ROWS)]

def drop_disc(board, col, player):
    """Drops disc in lowest available row of col. Returns row index or -1 if full."""
    for row in range(ROWS - 1, -1, -1):
        if board[row][col] == "empty":
            board[row][col] = player
            return row
    return -1

def check_winner(board, player):
    """Check all 4-in-a-row combinations."""
    # Horizontal
    for r in range(ROWS):
        for c in range(COLS - 3):
            if all(board[r][c+i] == player for i in range(4)):
                return True
    # Vertical
    for r in range(ROWS - 3):
        for c in range(COLS):
            if all(board[r+i][c] == player for i in range(4)):
                return True
    # Diagonal (down-right)
    for r in range(ROWS - 3):
        for c in range(COLS - 3):
            if all(board[r+i][c+i] == player for i in range(4)):
                return True
    # Diagonal (down-left)
    for r in range(ROWS - 3):
        for c in range(3, COLS):
            if all(board[r+i][c-i] == player for i in range(4)):
                return True
    return False

def check_draw(board):
    return all(board[0][c] != "empty" for c in range(COLS))

def build_c4_board(game_id, board, status="playing"):
    """Builds the inline keyboard representing the board."""
    keyboard = []
    # Board rows
    for row in board:
        keyboard.append([InlineKeyboardButton(DISC[cell], callback_data="c4_none") for cell in row])
    # Column selector buttons
    if status == "playing":
        keyboard.append([
            InlineKeyboardButton(str(c + 1), callback_data=f"c4_drop|{game_id}|{c}")
            for c in range(COLS)
        ])
    return InlineKeyboardMarkup(keyboard)

def touch_c4(game):
    game["updated_at"] = time.time()

def refund_c4_player(user_id, bet, *, idle, chat_id, game_id):
    return refund_locked_bet(
        user_id,
        bet,
        idle=idle,
        adjust_user_balance=adjust_user_balance,
        chat_id=chat_id,
        source="/c4 timeout",
        meta={"game_id": game_id},
    )

async def expire_c4_later(context, game_id):
    while True:
        game = active_c4.get(game_id)
        if not game or game.get("status") not in {"pending", "playing"}:
            return
        wait_for = GAME_EXPIRE_SECONDS - (time.time() - float(game.get("updated_at", game.get("created_at", time.time()))))
        if wait_for > 0:
            await asyncio.sleep(wait_for + 1)
            continue
        break
    game = active_c4.pop(game_id, None)
    if not game:
        return
    if game.get("status") == "pending":
        text = "⏳ <b>Connect Four challenge expired.</b>"
    else:
        bet = int(game.get("bet", 0))
        turn = game.get("turn")
        p1_refund = refund_c4_player(game["p1"], bet, idle=(turn == game["p1"]), chat_id=game.get("chat_id"), game_id=game_id)
        p2_refund = refund_c4_player(game["p2"], bet, idle=(turn == game["p2"]), chat_id=game.get("chat_id"), game_id=game_id)
        text = (
            "⏳ <b>Connect Four expired.</b>\n"
            f"🔴 refund: <code>{p1_refund['refund']:,}</code> | fee: <code>{p1_refund['fee']:,}</code>\n"
            f"🟡 refund: <code>{p2_refund['refund']:,}</code> | fee: <code>{p2_refund['fee']:,}</code>"
        )
    try:
        if game.get("message_id"):
            await context.bot.edit_message_text(chat_id=game["chat_id"], message_id=game["message_id"], text=text, parse_mode=ParseMode.HTML)
        else:
            await context.bot.send_message(chat_id=game["chat_id"], text=text, parse_mode=ParseMode.HTML)
    except BadRequest:
        pass

async def connect4_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start a Connect 4 game by replying to a user."""
    user = update.effective_user
    user_doc = ensure_user_exists(user)

    if not update.message.reply_to_message:
        return await update.message.reply_text(
            "🔴🟡 <b>Connect 4 — Usage:</b>\nReply to someone and type:\n"
            "<code>/c4</code> or <code>/c4 2000</code> (with bet)",
            parse_mode=ParseMode.HTML
        )

    target_user = update.message.reply_to_message.from_user
    if target_user.is_bot or target_user.id == user.id:
        return await update.message.reply_text("❌ Invalid target!")

    target_doc = ensure_user_exists(target_user)

    bet = 0
    if context.args and context.args[0].isdigit():
        bet = int(context.args[0])
        if user_doc.get('balance', 0) < bet:
            return await update.message.reply_text("❌ Not enough coins!")
        if target_doc.get('balance', 0) < bet:
            return await update.message.reply_text(f"❌ {get_mention(target_user)} doesn't have enough coins!", parse_mode=ParseMode.HTML)

    game_id = str(uuid.uuid4())[:8]
    now = time.time()
    active_c4[game_id] = {
        "p1": user.id, "p1_name": user.first_name,
        "p2": target_user.id, "p2_name": target_user.first_name,
        "board": create_board(),
        "turn": user.id,
        "bet": bet,
        "status": "pending",
        "chat_id": update.effective_chat.id if update.effective_chat else None,
        "created_at": now,
        "updated_at": now,
    }

    bet_text = f" for <b>${bet:,}</b>" if bet > 0 else ""
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Accept!", callback_data=f"c4_acc|{game_id}")],
        [InlineKeyboardButton("❌ Decline", callback_data=f"c4_dec|{game_id}")]
    ])

    sent = await update.message.reply_text(
        f"🔴🟡 <b>{stylize_text('CONNECT 4 CHALLENGE')}</b>\n\n"
        f"{get_mention(user)} vs {get_mention(target_user)}{bet_text}\n\n"
        f"🔴 {get_mention(user)} — Challenger\n"
        f"🟡 {get_mention(target_user)} — Waiting for acceptance...",
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard
    )
    active_c4[game_id]["message_id"] = sent.message_id
    context.application.create_task(expire_c4_later(context, game_id))

async def connect4_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    data = query.data.split("|")
    action = data[0]

    if action == "c4_none":
        return await query.answer()
    if len(data) < 2:
        return await query.answer("Game expired.", show_alert=True)

    game_id = data[1]

    game = active_c4.get(game_id)
    if not game:
        return await query.answer("❌ Game expired!", show_alert=True)

    if action == "c4_acc":
        if user.id != game['p2']:
            return await query.answer("❌ Not your challenge!", show_alert=True)
        if game['status'] != "pending":
            return await query.answer("❌ Challenge already handled!", show_alert=True)
        game['status'] = "accepting"
        if game['bet'] > 0:
            p1_charge = adjust_user_balance(
                game['p1'],
                -game['bet'],
                "connect4_bet",
                "Connect Four wager locked",
                chat_id=game.get("chat_id"),
                target_user_id=game['p2'],
                source="/connect4",
                require_gte=game['bet'],
                meta={"game_id": game_id},
            )
            if not p1_charge:
                active_c4.pop(game_id, None)
                await query.answer("Challenge cancelled.", show_alert=True)
                await query.message.edit_text(
                    "❌ <b>Challenge cancelled.</b>\nThe challenger no longer has enough coins.",
                    parse_mode=ParseMode.HTML,
                )
                return

            p2_charge = adjust_user_balance(
                game['p2'],
                -game['bet'],
                "connect4_bet",
                "Connect Four wager locked",
                chat_id=game.get("chat_id"),
                target_user_id=game['p1'],
                source="/connect4",
                require_gte=game['bet'],
                meta={"game_id": game_id},
            )
            if not p2_charge:
                adjust_user_balance(
                    game['p1'],
                    game['bet'],
                    "connect4_refund",
                    "Connect Four acceptance rollback",
                    chat_id=game.get("chat_id"),
                    target_user_id=game['p2'],
                    source="/connect4",
                    meta={"game_id": game_id},
                )
                active_c4.pop(game_id, None)
                await query.answer("Challenge cancelled. Challenger refunded.", show_alert=True)
                await query.message.edit_text(
                    "❌ <b>Challenge cancelled.</b>\nThe opponent no longer has enough coins. Challenger refunded.",
                    parse_mode=ParseMode.HTML,
                )
                return
        game['status'] = "playing"
        touch_c4(game)
        await query.answer("🎮 Game Started!")

        await query.message.edit_text(
            f"🔴🟡 <b>Connect Four!</b>\n"
            f"🔴 {c4_player_mention(game, game['p1'])}  vs  🟡 {c4_player_mention(game, game['p2'])}\n\n"
            f"⏳ <b>{c4_player_mention(game, game['turn'])}'s Turn (🔴)</b>\nClick a column number to drop your disc!",
            parse_mode=ParseMode.HTML,
            reply_markup=build_c4_board(game_id, game['board'])
        )
        return

    if action == "c4_dec":
        if user.id not in [game['p1'], game['p2']]:
            return await query.answer("Not your game!", show_alert=True)
        del active_c4[game_id]
        return await query.message.edit_text("❌ <b>Challenge Declined.</b>", parse_mode=ParseMode.HTML)

    if action == "c4_drop":
        if game['status'] != "playing":
            return await query.answer("Game not active.", show_alert=True)
        if user.id != game['turn']:
            return await query.answer("⏳ It's not your turn!", show_alert=True)

        try:
            col = int(data[2])
        except (IndexError, TypeError, ValueError):
            return await query.answer("❌ Old board data. Start a new game.", show_alert=True)
        if not 0 <= col < COLS:
            return await query.answer("❌ Invalid column.", show_alert=True)
        if game['board'][0][col] != "empty":
            return await query.answer("❌ That column is full! Pick another.", show_alert=True)

        is_p1 = (user.id == game['p1'])
        player_key = "p1" if is_p1 else "p2"
        disc_emoji = DISC[player_key]
        player_name = game['p1_name'] if is_p1 else game['p2_name']
        player_link = c4_player_mention(game, user.id)

        row = drop_disc(game['board'], col, player_key)
        if row == -1:
            return await query.answer("❌ That column is full! Pick another.", show_alert=True)
        touch_c4(game)

        # Check win
        if check_winner(game['board'], player_key):
            game['status'] = "finished"
            prize = game['bet'] * 2 if game['bet'] > 0 else 0
            coin_reward = 500
            winner_id = user.id
            loser_id = game['p2'] if is_p1 else game['p1']

            users_collection.update_one({"user_id": winner_id}, {"$inc": {"balance": prize + coin_reward, "game_wins": 1}})
            await add_xp(winner_id, XP_PER_GAME_WIN)
            del active_c4[game_id]
            await query.answer(f"🏆 {player_name} Wins!")

            prize_text = f"\n💰 <code>${prize + coin_reward:,}</code> won!" if prize + coin_reward > 0 else f"\n💰 +<code>${coin_reward:,}</code> bonus!"
            await query.message.edit_text(
                f"🔴🟡 <b>Connect Four — Game Over!</b>\n\n"
                f"🏆 <b>{player_link} ({disc_emoji}) WINS!</b>{prize_text}",
                parse_mode=ParseMode.HTML,
                reply_markup=build_c4_board(game_id, game['board'], status="done")
            )
            return

        # Check draw
        if check_draw(game['board']):
            game['status'] = "finished"
            if game['bet'] > 0:
                users_collection.update_one({"user_id": game['p1']}, {"$inc": {"balance": game['bet']}})
                users_collection.update_one({"user_id": game['p2']}, {"$inc": {"balance": game['bet']}})
            del active_c4[game_id]
            await query.answer("🤝 Draw!")
            await query.message.edit_text(
                f"🔴🟡 <b>Connect Four — DRAW!</b>\nBoard is full! Bets refunded.",
                parse_mode=ParseMode.HTML,
                reply_markup=build_c4_board(game_id, game['board'], status="done")
            )
            return

        # Switch turn
        game['turn'] = game['p2'] if is_p1 else game['p1']
        next_disc = "🟡" if is_p1 else "🔴"
        await query.answer("Disc dropped.")

        await query.message.edit_text(
            f"🔴🟡 <b>Connect Four!</b>\n"
            f"🔴 {c4_player_mention(game, game['p1'])}  vs  🟡 {c4_player_mention(game, game['p2'])}\n\n"
            f"⏳ <b>{c4_player_mention(game, game['turn'])}'s Turn ({next_disc})</b>\nClick a column number!",
            parse_mode=ParseMode.HTML,
            reply_markup=build_c4_board(game_id, game['board'])
        )
        return
