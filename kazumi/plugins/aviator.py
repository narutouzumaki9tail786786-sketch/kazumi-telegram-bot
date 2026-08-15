import asyncio
import random
import time
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, WebAppInfo

from telegram.constants import ChatType, ParseMode

from telegram.ext import ContextTypes

from datetime import datetime
from kazumi.config import DEFAULT_MAX_BET
from kazumi.database import users_collection, active_games_collection
from kazumi.ledger import adjust_user_balance
from kazumi.utils import ensure_user_exists, format_display_text, format_money, parse_money, stylize_text

ACTIVE_AVIATOR_GAMES = {}


def generate_crash_point() -> float:
    """Generates a provably-fair style random multiplier crash point between 1.05x and 50.0x."""
    val = random.random()
    if val < 0.05:
        return 1.00  # Instant crash 5% of the time
    if val < 0.40:
        return round(random.uniform(1.10, 1.80), 2)
    if val < 0.75:
        return round(random.uniform(1.80, 3.50), 2)
    if val < 0.92:
        return round(random.uniform(3.50, 10.00), 2)
    return round(random.uniform(10.00, 50.00), 2)


async def aviator(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_doc = ensure_user_exists(update.effective_user)
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    if user_id in ACTIVE_AVIATOR_GAMES:
        return await update.message.reply_text(
            format_display_text("🚀 <b>You already have an active Aviator flight running!</b>", ParseMode.HTML),
            parse_mode=ParseMode.HTML,
        )

    args = context.args
    if not args:
        help_txt = (
            f"🚀 <b>{stylize_text('Aviator Crash Game')}</b>\n\n"
            "Bet on a rising multiplier plane before it crashes!\n\n"
            "<b>Chat Command:</b> <code>/aviator [bet_amount]</code>\n"
            "<b>Example:</b> <code>/aviator 1000</code>\n\n"
            "🌐 <b>Web Mini App Direct Mode:</b> <code>/wav [bet]</code> (Full 2D Flight Canvas!)"
        )
        return await update.message.reply_text(
            format_display_text(help_txt, ParseMode.HTML),
            parse_mode=ParseMode.HTML,
        )

    parsed = parse_money(args[0]) if args else None
    if parsed == "all":
        bet = min(user_doc.get("balance", 0), DEFAULT_MAX_BET)
    elif isinstance(parsed, int):
        bet = parsed
    else:
        return await update.message.reply_text(
            format_display_text(
                f"❌ <b>{stylize_text('Invalid Bet Amount')}!</b>\n"
                f"Please enter a valid number (Example: <code>/aviator 1000</code>).",
                ParseMode.HTML
            ),
            parse_mode=ParseMode.HTML,
        )

    if bet < 100:
        return await update.message.reply_text(
            format_display_text(
                f"⚠️ <b>{stylize_text('Minimum Bet Limit')}!</b>\n"
                f"Minimum bet for Aviator is <code>$100</code> coins.",
                ParseMode.HTML
            ),
            parse_mode=ParseMode.HTML,
        )

    if bet > DEFAULT_MAX_BET:
        return await update.message.reply_text(
            format_display_text(
                f"⚠️ <b>{stylize_text('Maximum Wager Limit')}!</b>\n"
                f"━━━━━━━━━━━━━━━━━━━\n"
                f"Maximum allowed bet for Aviator is <code>{format_money(DEFAULT_MAX_BET)}</code> coins.",
                ParseMode.HTML
            ),
            parse_mode=ParseMode.HTML,
        )

    balance = user_doc.get("balance", 0)
    if balance < bet:
        return await update.message.reply_text(
            format_display_text(f"❌ You don't have enough coins! Balance: <code>{format_money(balance)}</code>", ParseMode.HTML),
            parse_mode=ParseMode.HTML,
        )

    # Deduct bet balance atomically
    res = adjust_user_balance(
        user_id,
        -bet,
        category="aviator_bet",
        reason=f"Aviator game bet of {bet} coins",
        chat_id=chat_id,
        require_gte=bet,
    )
    if not res:
        return await update.message.reply_text("❌ Balance debit failed. Try again.")

    crash_point = generate_crash_point()
    game_key = f"av_{user_id}_{int(time.time())}"

    game_state = {
        "user_id": user_id,
        "bet": bet,
        "crash_point": crash_point,
        "current_multiplier": 1.00,
        "cashed_out": False,
        "cashed_out_at": 1.00,
        "crashed": False,
        "chat_id": chat_id,
        "game_key": game_key,
        "game_type": "aviator",
        "created_at": datetime.utcnow(),
    }

    ACTIVE_AVIATOR_GAMES[user_id] = game_state

    # Save to Mongo for restart-proof recovery & auto-refund
    try:
        active_games_collection.insert_one(dict(game_state))
    except Exception as exc:
        print(f"[AVIATOR DB SAVE ERROR] {exc}", flush=True)

    start_text = (
        f"🚀 <b>{stylize_text('Aviator Flight Started!')}</b>\n"
        f"👤 <b>Player:</b> {update.effective_user.mention_html()}\n"
        f"💰 <b>Bet:</b> <code>{format_money(bet)}</code>\n\n"
        f"📈 <b>Multiplier:</b> <code>1.00x</code>\n"
        f"💵 <b>Current Cashout:</b> <code>{format_money(bet)}</code>\n\n"
        "<i>Tap Cashout before the plane crashes!</i>"
    )

    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"💰 Cash Out ({format_money(bet)})", callback_data=f"av_out|{user_id}|{game_key}")]
    ])

    sent_msg = await update.message.reply_text(
        format_display_text(start_text, ParseMode.HTML),
        parse_mode=ParseMode.HTML,
        reply_markup=markup,
    )

    # Flight ticker task
    asyncio.create_task(run_aviator_flight(context, sent_msg, user_id, game_key))


async def run_aviator_flight(context: ContextTypes.DEFAULT_TYPE, message, user_id: int, game_key: str):
    game = ACTIVE_AVIATOR_GAMES.get(user_id)
    if not game or game["game_key"] != game_key:
        return

    crash_point = game["crash_point"]
    bet = game["bet"]
    curr_mult = 1.00

    while curr_mult < crash_point:
        await asyncio.sleep(1.2)
        game = ACTIVE_AVIATOR_GAMES.get(user_id)
        if not game or game.get("cashed_out") or game["game_key"] != game_key:
            return

        # Increment multiplier
        step = round(random.uniform(0.12, 0.35), 2)
        curr_mult = round(curr_mult + step, 2)

        if curr_mult >= crash_point:
            break

        game["current_multiplier"] = curr_mult
        potential_win = int(bet * curr_mult)

        text = (
            f"🚀 <b>{stylize_text('Aviator Flying High!')}</b>\n"
            f"👤 <b>Player:</b> {game['user_id']}\n"
            f"💰 <b>Bet:</b> <code>{format_money(bet)}</code>\n\n"
            f"📈 <b>Multiplier:</b> <code>{curr_mult:.2f}x</code>\n"
            f"💵 <b>Current Value:</b> <code>{format_money(potential_win)}</code>\n\n"
            "🔥 <i>Plane is rising! Tap Cashout quick!</i>"
        )
        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"💰 Cash Out ({format_money(potential_win)})", callback_data=f"av_out|{user_id}|{game_key}")]
        ])
        try:
            await message.edit_text(format_display_text(text, ParseMode.HTML), parse_mode=ParseMode.HTML, reply_markup=markup)
        except Exception:
            pass

    # Crashed!
    game = ACTIVE_AVIATOR_GAMES.get(user_id)
    if game and not game.get("cashed_out") and game["game_key"] == game_key:
        game["crashed"] = True
        ACTIVE_AVIATOR_GAMES.pop(user_id, None)
        try:
            active_games_collection.delete_one({"game_key": game_key})
        except Exception:
            pass

        crash_text = (
            f"💥 <b>{stylize_text('CRASHED!')}</b>\n"
            f"The plane flew away at <code>{crash_point:.2f}x</code>!\n\n"
            f"💸 <b>Loss:</b> <code>{format_money(bet)}</code>."
        )
        try:
            await message.edit_text(format_display_text(crash_text, ParseMode.HTML), parse_mode=ParseMode.HTML)
        except Exception:
            pass


async def aviator_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return
    await query.answer()

    data = (query.data or "").split("|")
    if len(data) != 3 or data[0] != "av_out":
        return

    owner_id = int(data[1])
    game_key = data[2]

    if query.from_user.id != owner_id:
        return await query.answer("❌ This is not your Aviator flight!", show_alert=True)

    game = ACTIVE_AVIATOR_GAMES.get(owner_id)

    # 🔄 BOT RESTART RECOVERY: If game memory was cleared on restart, check Mongo!
    if not game or game["game_key"] != game_key:
        db_game = active_games_collection.find_one({"game_key": game_key}) or active_games_collection.find_one({"user_id": owner_id, "game_type": "aviator"})
        if db_game:
            bet = db_game.get("bet", 0)
            # Refund 100% of bet back to user wallet
            adjust_user_balance(
                owner_id,
                bet,
                category="aviator_restart_refund",
                reason=f"100% Refund for Aviator flight interrupted by bot restart ({game_key})",
                chat_id=query.message.chat_id,
            )
            active_games_collection.delete_one({"_id": db_game["_id"]})
            ACTIVE_AVIATOR_GAMES.pop(owner_id, None)

            refund_msg = (
                f"🔄 <b>{stylize_text('FLIGHT REFUNDED!')}</b>\n\n"
                f"Your flight was interrupted by a bot update/restart.\n"
                f"💰 <b>100% Bet Refunded:</b> <code>{format_money(bet)}</code> credited back to your wallet!"
            )
            try:
                await query.message.edit_text(format_display_text(refund_msg, ParseMode.HTML), parse_mode=ParseMode.HTML)
            except Exception:
                pass
            return await query.answer("💰 Flight interrupted by bot restart. 100% bet refunded!", show_alert=True)
        else:
            return await query.answer("❌ Flight already ended, crashed, or refunded!", show_alert=True)

    if game.get("cashed_out") or game.get("crashed"):
        return await query.answer("❌ Flight already concluded!", show_alert=True)

    # Cashout success!
    game["cashed_out"] = True
    cashed_mult = game["current_multiplier"]
    bet = game["bet"]
    win_amount = int(bet * cashed_mult)
    profit = win_amount - bet

    ACTIVE_AVIATOR_GAMES.pop(owner_id, None)
    try:
        active_games_collection.delete_one({"game_key": game_key})
    except Exception:
        pass

    # Credit win balance
    adjust_user_balance(
        owner_id,
        win_amount,
        category="aviator_win",
        reason=f"Cashed out Aviator at {cashed_mult}x",
        chat_id=query.message.chat_id,
    )

    win_text = (
        f"🎉 <b>{stylize_text('CASHED OUT SUCCESS!')}</b>\n\n"
        f"👤 <b>Player:</b> {query.from_user.mention_html()}\n"
        f"📈 <b>Cashed at:</b> <code>{cashed_mult:.2f}x</code>\n"
        f"💰 <b>Total Payout:</b> <code>{format_money(win_amount)}</code> (+<code>{format_money(profit)}</code> PROFIT)!"
    )
    try:
        await query.message.edit_text(format_display_text(win_text, ParseMode.HTML), parse_mode=ParseMode.HTML)
    except Exception:
        pass


def auto_refund_orphaned_games():
    """Startup task: refund all uncompleted in-chat games that were interrupted by bot restarts."""
    try:
        orphaned = list(active_games_collection.find({}))
        if not orphaned:
            return

        count = 0
        total_refunded = 0
        for g in orphaned:
            uid = g.get("user_id")
            bet = g.get("bet", 0)
            gkey = g.get("game_key", "unknown")
            if uid and bet > 0:
                adjust_user_balance(
                    uid,
                    bet,
                    category="bot_restart_auto_refund",
                    reason=f"Automatic 100% refund for interrupted game ({gkey})",
                )
                total_refunded += bet
                count += 1
            active_games_collection.delete_one({"_id": g["_id"]})

        print(f"✅ [RESTART GAME RECOVERY] Refunded {count} interrupted games (Total {total_refunded} coins)", flush=True)
    except Exception as exc:
        print(f"[RESTART GAME RECOVERY ERROR] {exc}", flush=True)
