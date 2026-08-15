import random
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from kazumi.database import users_collection
from kazumi.ledger import adjust_user_balance
from kazumi.utils import ensure_user_exists, format_display_text, format_money, get_mention, resolve_target, stylize_text

ACTIVE_LUDO_GAMES = {}


async def ludo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    ensure_user_exists(user)

    target_doc, err = await resolve_target(update, context)

    # Parse bet from args
    bet = 1000
    if context.args:
        for arg in context.args:
            if arg.isdigit():
                bet = max(100, int(arg))
                break

    user_doc = users_collection.find_one({"user_id": user.id})
    if (user_doc.get("balance", 0)) < bet:
        return await update.message.reply_text(
            format_display_text(f"❌ You need at least <code>{format_money(bet)}</code> coins to start Ludo.", ParseMode.HTML),
            parse_mode=ParseMode.HTML,
        )

    is_vs_bot = False
    target_id = None
    target_name = "Kazumi Bot 🤖"

    if target_doc and isinstance(target_doc, dict):
        target_id = target_doc.get("user_id")
        target_name = target_doc.get("name") or "Player 2"

    if not target_id or target_id == user.id:
        is_vs_bot = True
        target_id = 0
        target_name = "Kazumi Bot 🤖"

    game_id = f"ludo_{chat.id}_{user.id}"
    if game_id in ACTIVE_LUDO_GAMES:
        return await update.message.reply_text(
            format_display_text("🎲 A Ludo match is already active in this chat!", ParseMode.HTML),
            parse_mode=ParseMode.HTML,
        )

    game_state = {
        "game_id": game_id,
        "player1": user.id,
        "player1_name": user.first_name,
        "player2": target_id,
        "player2_name": target_name,
        "is_vs_bot": is_vs_bot,
        "bet": bet,
        "turn": user.id,
        "p1_pawns": [0, 0, 0, 0],  # 0 to 57 (57 = HOME)
        "p2_pawns": [0, 0, 0, 0],
        "last_dice": 0,
        "status": "playing",
    }
    ACTIVE_LUDO_GAMES[game_id] = game_state

    # Deduct P1 bet
    adjust_user_balance(user.id, -bet, category="ludo_bet", reason="Ludo match entry fee", chat_id=chat.id)

    target_mention = target_name if is_vs_bot else get_mention(target_doc)

    text = (
        f"🎲 <b>{stylize_text('Ludo Championship')}</b>\n"
        f"🔴 <b>Player 1:</b> {get_mention(user)} (Score: 0/4 Home)\n"
        f"🟡 <b>Player 2:</b> {target_mention} (Score: 0/4 Home)\n"
        f"💰 <b>Stake:</b> <code>{format_money(bet)}</code>\n\n"
        f"<b>Current Turn:</b> {get_mention(user)}\n"
        "<i>Roll the dice to move your pawns to HOME!</i>"
    )

    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎲 Roll Dice", callback_data=f"ld_roll|{game_id}|{user.id}")]
    ])

    await update.message.reply_text(format_display_text(text, ParseMode.HTML), parse_mode=ParseMode.HTML, reply_markup=markup)


async def ludo_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return
    await query.answer()

    data = (query.data or "").split("|")
    if len(data) < 3 or data[0] != "ld_roll":
        return

    game_id = data[1]
    expected_user = int(data[2])

    if query.from_user.id != expected_user:
        return await query.answer("❌ It is not your turn!", show_alert=True)

    game = ACTIVE_LUDO_GAMES.get(game_id)
    if not game or game["status"] != "playing":
        return await query.answer("❌ Game ended or expired.", show_alert=True)

    dice = random.randint(1, 6)
    game["last_dice"] = dice

    is_p1 = (query.from_user.id == game["player1"])
    pawns = game["p1_pawns"] if is_p1 else game["p2_pawns"]

    # Auto-move first available pawn
    moved = False
    for i in range(4):
        if pawns[i] + dice <= 57:
            pawns[i] += dice
            moved = True
            break

    # Check win condition (all 4 pawns reach 57 HOME or 2 pawns reach HOME for fast game)
    home_count = sum(1 for pos in pawns if pos >= 25)
    opp_name = game["player2_name"] if is_p1 else game["player1_name"]

    if home_count >= 2:
        # Player Wins!
        game["status"] = "finished"
        ACTIVE_LUDO_GAMES.pop(game_id, None)

        win_amount = game["bet"] * 2
        adjust_user_balance(query.from_user.id, win_amount, category="ludo_win", reason="Ludo match winner", chat_id=query.message.chat_id)

        win_text = (
            f"🏆 <b>{stylize_text('LUDO CHAMPION!')}</b>\n\n"
            f"🎉 {query.from_user.mention_html()} defeated {opp_name} in Ludo!\n"
            f"🎲 Final Roll: <code>{dice}</code>\n"
            f"💰 <b>Prize Won:</b> <code>{format_money(win_amount)}</code>!"
        )
        return await query.message.edit_text(format_display_text(win_text, ParseMode.HTML), parse_mode=ParseMode.HTML)

    # Switch turns
    if game["is_vs_bot"]:
        # Bot auto-moves
        bot_dice = random.randint(1, 6)
        for i in range(4):
            if game["p2_pawns"][i] + bot_dice <= 57:
                game["p2_pawns"][i] += bot_dice
                break
        next_turn = game["player1"]
        next_turn_name = game["player1_name"]
    else:
        next_turn = game["player2"] if is_p1 else game["player1"]
        next_turn_name = game["player2_name"] if is_p1 else game["player1_name"]

    game["turn"] = next_turn

    p1_score = sum(1 for pos in game["p1_pawns"] if pos >= 25)
    p2_score = sum(1 for pos in game["p2_pawns"] if pos >= 25)

    turn_text = (
        f"🎲 <b>{stylize_text('Ludo Match')}</b>\n\n"
        f"🎲 <b>Last Roll:</b> <code>{dice}</code>\n\n"
        f"🔴 <b>{game['player1_name']}:</b> {p1_score}/2 Home\n"
        f"🟡 <b>{game['player2_name']}:</b> {p2_score}/2 Home\n\n"
        f"👉 <b>Next Turn:</b> {next_turn_name}"
    )
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎲 Roll Dice", callback_data=f"ld_roll|{game_id}|{next_turn}")]
    ])
    await query.message.edit_text(format_display_text(turn_text, ParseMode.HTML), parse_mode=ParseMode.HTML, reply_markup=markup)
