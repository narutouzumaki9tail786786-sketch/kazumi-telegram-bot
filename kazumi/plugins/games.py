# 🌸 Kazumi — New Games Module (Blackjack, RPS, Guess, Russian Roulette, CoinFlip)

import random
import time
import asyncio
from datetime import datetime
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.error import BadRequest
from telegram.ext import ApplicationHandlerStop, ContextTypes
from telegram.constants import ParseMode, ChatType
from kazumi.utils import ensure_user_exists, get_mention, format_money, parse_money, format_display_text, stylize_text, add_xp, Button, pick_rotating_media
from kazumi.database import users_collection
from kazumi.ledger import adjust_user_balance
from kazumi.missions import track_many, track_mission
from kazumi.game_timeouts import GAME_EXPIRE_SECONDS, expire_minutes, refund_locked_bet
from kazumi.game_rules import highlow_profile
from kazumi.plugins.profile import get_level
from kazumi.config import (
    BLACKJACK_MIN_BET, BLACKJACK_MAX_BET, RPS_MIN_BET, RPS_MAX_BET,
    COINFLIP_MIN_BET, COINFLIP_MAX_BET, GUESS_REWARD, GUESS_MAX_TRIES,
    RUSSIAN_ROULETTE_BET, XP_PER_GAME_WIN
)

def game_is_expired(game, ttl=GAME_EXPIRE_SECONDS):
    return (time.time() - float(game.get("updated_at", game.get("created_at", 0)))) >= ttl

def touch_game(game):
    game["updated_at"] = time.time()

def locked_refund(uid, bet, *, idle=False, chat_id=None, source="game_expire", meta=None):
    return refund_locked_bet(
        uid,
        bet,
        idle=idle,
        adjust_user_balance=adjust_user_balance,
        chat_id=chat_id,
        source=source,
        meta=meta,
    )

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🃏 BLACKJACK
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

active_bj = {}  # {user_id: {deck, player, dealer, bet, msg_id}}

CARD_VALUES = {'2':2,'3':3,'4':4,'5':5,'6':6,'7':7,'8':8,'9':9,'10':10,'J':10,'Q':10,'K':10,'A':11}
SUITS = ['♠️','♥️','♦️','♣️']
RANKS = list(CARD_VALUES.keys())

def new_deck():
    deck = [(r, s) for r in RANKS for s in SUITS]
    random.shuffle(deck)
    return deck

def card_str(cards):
    return " ".join(f"[{r}{s}]" for r, s in cards)

def hand_value(cards):
    total = sum(CARD_VALUES[r] for r, _ in cards)
    aces = sum(1 for r, _ in cards if r == 'A')
    while total > 21 and aces:
        total -= 10
        aces -= 1
    return total

def bj_display(game, show_dealer=False):
    pv = hand_value(game['player'])
    if show_dealer:
        dv = hand_value(game['dealer'])
        dealer_text = f"{card_str(game['dealer'])} = <b>{dv}</b>"
    else:
        dealer_text = f"[{game['dealer'][0][0]}{game['dealer'][0][1]}] [❓]"
    
    return (
        f"🃏 <b>{stylize_text('BLACKJACK')}</b>\n"
        f"💰 Bet: <code>{format_money(game['bet'])}</code>\n\n"
        f"🏠 <b>Dealer:</b> {dealer_text}\n"
        f"👤 <b>You:</b> {card_str(game['player'])} = <b>{pv}</b>"
    )

async def expire_blackjack_later(context, uid, token):
    while True:
        game = active_bj.get(uid)
        if not game or game.get("token") != token:
            return
        wait_for = GAME_EXPIRE_SECONDS - (time.time() - float(game.get("updated_at", game.get("created_at", time.time()))))
        if wait_for > 0:
            await asyncio.sleep(wait_for + 1)
            continue
        break
    game = active_bj.pop(uid, None)
    if not game:
        return
    result = locked_refund(
        uid,
        game.get("bet", 0),
        idle=True,
        chat_id=game.get("chat_id"),
        source="/blackjack timeout",
        meta={"message_id": game.get("message_id")},
    )
    if game.get("chat_id") and game.get("message_id"):
        try:
            await context.bot.edit_message_text(
                chat_id=game["chat_id"],
                message_id=game["message_id"],
                text=(
                    f"{bj_display(game, True)}\n\n"
                    f"⏳ <b>Expired.</b> Idle fee: <code>{format_money(result['fee'])}</code>\n"
                    f"💵 Refunded: <code>{format_money(result['refund'])}</code>"
                ),
                parse_mode=ParseMode.HTML,
            )
        except BadRequest:
            pass

async def blackjack(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = ensure_user_exists(update.effective_user)
    uid = user['user_id']
    
    if uid in active_bj:
        old = active_bj.get(uid)
        if old and game_is_expired(old):
            active_bj.pop(uid, None)
            result = locked_refund(
                uid,
                old.get("bet", 0),
                idle=True,
                chat_id=old.get("chat_id"),
                source="/blackjack timeout",
                meta={"message_id": old.get("message_id")},
            )
            return await update.message.reply_text(
                f"⏳ Old blackjack game expired. Refunded <code>{format_money(result['refund'])}</code>; idle fee <code>{format_money(result['fee'])}</code>.",
                parse_mode=ParseMode.HTML,
            )
        return await update.message.reply_text("⚠️ Finish your current game first!", parse_mode=ParseMode.HTML)
    
    if not context.args:
        return await update.message.reply_text(
            format_display_text(f"🃏 <b>Usage:</b> <code>/blackjack {BLACKJACK_MIN_BET}</code>", ParseMode.HTML),
            parse_mode=ParseMode.HTML
        )
    
    parsed = parse_money(context.args[0])
    if parsed == "all":
        bet = min(user.get("balance", 0), BLACKJACK_MAX_BET)
    elif isinstance(parsed, int):
        bet = parsed
    else:
        return await update.message.reply_text(
            format_display_text(f"⚠️ <b>{stylize_text('Invalid Bet')}!</b> Enter a valid number.", ParseMode.HTML),
            parse_mode=ParseMode.HTML
        )
    
    if bet < BLACKJACK_MIN_BET or bet > BLACKJACK_MAX_BET:
        return await update.message.reply_text(
            format_display_text(
                f"⚠️ <b>{stylize_text('Wager Limit')}!</b> Bet range: <code>{format_money(BLACKJACK_MIN_BET)}</code> - <code>{format_money(BLACKJACK_MAX_BET)}</code>",
                ParseMode.HTML
            ),
            parse_mode=ParseMode.HTML
        )
    if user['balance'] < bet:
        return await update.message.reply_text("📉 Not enough coins!", parse_mode=ParseMode.HTML)
    
    charged = adjust_user_balance(
        uid,
        -bet,
        "blackjack_bet",
        "Started blackjack",
        chat_id=update.effective_chat.id if update.effective_chat else None,
        source="/blackjack",
        require_gte=bet,
        meta={"bet": bet},
    )
    if not charged:
        return await update.message.reply_text("\U0001F4C9 Not enough coins!", parse_mode=ParseMode.HTML)
    track_mission(uid, "play_game")
    
    deck = new_deck()
    player = [deck.pop(), deck.pop()]
    dealer = [deck.pop(), deck.pop()]
    
    now = time.time()
    token = f"{uid}:{int(now)}:{random.randint(1000, 9999)}"
    game = {
        "deck": deck,
        "player": player,
        "dealer": dealer,
        "bet": bet,
        "created_at": now,
        "updated_at": now,
        "token": token,
        "chat_id": update.effective_chat.id if update.effective_chat else None,
    }
    active_bj[uid] = game
    
    pv = hand_value(player)
    if pv == 21:  # Natural Blackjack!
        del active_bj[uid]
        win = int(bet * 2.5)
        adjust_user_balance(uid, win, category="blackjack_win", reason=f"Natural Blackjack win +{format_money(win)}", chat_id=update.effective_chat.id, extra_inc={"game_wins": 1})
        await add_xp(uid, XP_PER_GAME_WIN * 2)
        return await update.message.reply_text(
            f"{bj_display(game, True)}\n\n🎉 <b>BLACKJACK!</b> You win <code>{format_money(win)}</code>!",
            parse_mode=ParseMode.HTML
        )
    
    kb = InlineKeyboardMarkup([
        [Button("🎴 Hit", callback_data=f"bj_hit|{uid}"),
         Button("🛑 Stand", callback_data=f"bj_stand|{uid}")]
    ])
    
    sent = await update.message.reply_text(bj_display(game), parse_mode=ParseMode.HTML, reply_markup=kb)
    game["message_id"] = sent.message_id
    context.application.create_task(expire_blackjack_later(context, uid, token))

async def bj_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data.split("|")
    action, uid = data[0], int(data[1])
    
    if query.from_user.id != uid:
        return await query.answer("❌ Not your game!", show_alert=True)
    
    if uid not in active_bj:
        return await query.answer("❌ Game expired!", show_alert=True)
    
    game = active_bj[uid]
    if game_is_expired(game):
        active_bj.pop(uid, None)
        result = locked_refund(
            uid,
            game.get("bet", 0),
            idle=True,
            chat_id=query.message.chat_id if query.message else None,
            source="/blackjack timeout",
            meta={"message_id": query.message.message_id if query.message else None},
        )
        await query.answer("⏳ Game expired. Idle fee applied.", show_alert=True)
        return await query.message.edit_text(
            f"{bj_display(game, True)}\n\n"
            f"⏳ <b>Expired.</b> Idle fee: <code>{format_money(result['fee'])}</code>\n"
            f"💵 Refunded: <code>{format_money(result['refund'])}</code>",
            parse_mode=ParseMode.HTML,
        )
    touch_game(game)
    
    if action == "bj_hit":
        game['player'].append(game['deck'].pop())
        pv = hand_value(game['player'])
        
        if pv > 21:  # Bust
            del active_bj[uid]
            await query.message.edit_text(
                f"{bj_display(game, True)}\n\n💥 <b>BUST!</b> You lost <code>{format_money(game['bet'])}</code>!",
                parse_mode=ParseMode.HTML
            )
            return
        elif pv == 21:
            action = "bj_stand"  # Auto-stand on 21
        else:
            kb = InlineKeyboardMarkup([
                [Button("🎴 Hit", callback_data=f"bj_hit|{uid}"),
                 Button("🛑 Stand", callback_data=f"bj_stand|{uid}")]
            ])
            await query.message.edit_text(bj_display(game), parse_mode=ParseMode.HTML, reply_markup=kb)
            return
    
    if action == "bj_stand":
        del active_bj[uid]
        # Dealer plays
        while hand_value(game['dealer']) < 17:
            game['dealer'].append(game['deck'].pop())
        
        pv = hand_value(game['player'])
        dv = hand_value(game['dealer'])
        
        if dv > 21 or pv > dv:
            win = game['bet'] * 2
            adjust_user_balance(uid, win, category="blackjack_win", reason=f"Won Blackjack hand +{format_money(win)}", chat_id=game.get("chat_id"), extra_inc={"game_wins": 1})
            await add_xp(uid, XP_PER_GAME_WIN)
            result = f"🎉 <b>YOU WIN!</b> +<code>{format_money(win)}</code>"
        elif pv == dv:
            adjust_user_balance(uid, game['bet'], category="blackjack_push", reason=f"Blackjack push bet returned", chat_id=game.get("chat_id"))
            result = f"🤝 <b>PUSH!</b> Bet returned."
        else:
            result = f"💀 <b>Dealer Wins!</b> Lost <code>{format_money(game['bet'])}</code>"
        
        await query.message.edit_text(f"{bj_display(game, True)}\n\n{result}", parse_mode=ParseMode.HTML)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ✊ ROCK-PAPER-SCISSORS (PvP + Bot)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

RPS_EMOJIS = {"rock": "\U0001faa8", "paper": "\U0001f4c4", "scissors": "\u2702\ufe0f"}
RPS_BUTTON_LABELS = {
    "rock": "\U0001faa8 ʀᴏᴄᴋ",
    "paper": "\U0001f4c4 ᴘᴀᴘᴇʀ",
    "scissors": "\u2702\ufe0f sᴄɪssᴏʀs",
}
RPS_WINS = {"rock": "scissors", "paper": "rock", "scissors": "paper"}

active_rps = {}  # {msg_id: {challenger, bet, challenger_choice, opponent, opponent_choice}}


def rps_button(choice: str, callback_data: str):
    return Button(RPS_BUTTON_LABELS[choice], callback_data=callback_data)

async def expire_rps_later(context, mid, token):
    while True:
        game = active_rps.get(mid)
        if not game or game.get("token") != token:
            return
        wait_for = GAME_EXPIRE_SECONDS - (time.time() - float(game.get("updated_at", game.get("created_at", time.time()))))
        if wait_for > 0:
            await asyncio.sleep(wait_for + 1)
            continue
        break
    game = active_rps.pop(mid, None)
    if not game:
        return
    bet = int(game.get("bet", 0))
    status = game.get("status", "pending")
    if status == "pending":
        challenger_refund = locked_refund(game["challenger"], bet, chat_id=game.get("chat_id"), source="/rps timeout", meta={"message_id": mid})
        text = (
            f"⏳ <b>{stylize_text('RPS Expired')}</b>\n\n"
            f"Challenge timed out. Refunded: <code>{format_money(challenger_refund['refund'])}</code>"
        )
    else:
        c_idle = not game.get("challenger_choice")
        o_idle = not game.get("opponent_choice")
        c_refund = locked_refund(game["challenger"], bet, idle=c_idle, chat_id=game.get("chat_id"), source="/rps timeout", meta={"message_id": mid})
        o_refund = {"refund": 0, "fee": 0}
        if game.get("opponent"):
            o_refund = locked_refund(game["opponent"], bet, idle=o_idle, chat_id=game.get("chat_id"), source="/rps timeout", meta={"message_id": mid})
        text = (
            f"⏳ <b>{stylize_text('RPS Expired')}</b>\n\n"
            f"Player 1 refund: <code>{format_money(c_refund['refund'])}</code> | fee: <code>{format_money(c_refund['fee'])}</code>\n"
            f"Player 2 refund: <code>{format_money(o_refund['refund'])}</code> | fee: <code>{format_money(o_refund['fee'])}</code>"
        )
    if game.get("chat_id"):
        try:
            await context.bot.edit_message_text(chat_id=game["chat_id"], message_id=mid, text=text, parse_mode=ParseMode.HTML)
        except BadRequest:
            pass

async def rps(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = ensure_user_exists(update.effective_user)
    uid = user['user_id']
    
    if not context.args:
        return await update.message.reply_text(
            f"✊ <b>{stylize_text('Rock Paper Scissors')}</b>\n━━━━━━━━━━━━\n\n"
            f"<b>ᴘᴠᴘ:</b> <code>/rps 500</code> — ᴄʜᴀʟʟᴇɴɢᴇ ᴘʟᴀʏᴇʀs\n"
            f"<b>ʙᴏᴛ:</b> <code>/rps bot 500</code> — ᴘʟᴀʏ ᴠs ʙᴏᴛ",
            parse_mode=ParseMode.HTML)
    
    # --- BOT MODE: /rps bot 500 ---
    if context.args[0].lower() == "bot":
        if len(context.args) < 2: return await update.message.reply_text("⚠️ <code>/rps bot 500</code>", parse_mode=ParseMode.HTML)
        try: bet = int(context.args[1])
        except: return
        if bet < RPS_MIN_BET or bet > RPS_MAX_BET:
            return await update.message.reply_text(f"⚠️ ʙᴇᴛ: {RPS_MIN_BET} - {RPS_MAX_BET}", parse_mode=ParseMode.HTML)
        if user['balance'] < bet:
            return await update.message.reply_text("📉 ɴᴏᴛ ᴇɴᴏᴜɢʜ!", parse_mode=ParseMode.HTML)
        track_mission(uid, "play_game")
        
        kb = InlineKeyboardMarkup([[
            rps_button("rock", f"rpsbot_rock|{uid}|{bet}"),
            rps_button("paper", f"rpsbot_paper|{uid}|{bet}"),
            rps_button("scissors", f"rpsbot_scissors|{uid}|{bet}")
        ]])
        return await update.message.reply_text(
            f"✊ <b>{stylize_text('RPS vs Bot')}</b>\n💰 ʙᴇᴛ: <code>{format_money(bet)}</code>\n\n<i>ᴄʜᴏᴏsᴇ ʏᴏᴜʀ ᴍᴏᴠᴇ!</i>",
            parse_mode=ParseMode.HTML, reply_markup=kb)
    
    # --- PVP MODE: /rps 500 ---
    try: bet = int(context.args[0])
    except: return await update.message.reply_text("⚠️ <code>/rps 500</code>", parse_mode=ParseMode.HTML)
    
    if bet < RPS_MIN_BET or bet > RPS_MAX_BET:
        return await update.message.reply_text(f"⚠️ ʙᴇᴛ: {RPS_MIN_BET} - {RPS_MAX_BET}", parse_mode=ParseMode.HTML)
    if user['balance'] < bet:
        return await update.message.reply_text("📉 ɴᴏᴛ ᴇɴᴏᴜɢʜ!", parse_mode=ParseMode.HTML)
    
    # Lock challenger's bet atomically so parallel commands cannot overspend.
    charged = adjust_user_balance(
        uid,
        -bet,
        "rps_bet",
        "RPS challenge wager locked",
        chat_id=update.effective_chat.id if update.effective_chat else None,
        source="/rps",
        require_gte=bet,
        meta={"mode": "pvp"},
    )
    if not charged:
        return await update.message.reply_text("📉 ɴᴏᴛ ᴇɴᴏᴜɢʜ!", parse_mode=ParseMode.HTML)
    track_mission(uid, "play_game")
    
    kb = InlineKeyboardMarkup([[
        Button("✅ ᴀᴄᴄᴇᴘᴛ", callback_data=f"rpspvp_accept|{uid}|{bet}"),
        Button("❌ ʀᴇᴊᴇᴄᴛ", callback_data=f"rpspvp_reject|{uid}|{bet}")
    ]])
    
    try:
        msg = await update.message.reply_text(
            f"✊ <b>{stylize_text('RPS Challenge')}</b>\n━━━━━━━━━━━━\n\n"
            f"⚔️ {get_mention(user)} ᴡᴀɴᴛs ᴛᴏ ғɪɢʜᴛ!\n"
            f"💰 ʙᴇᴛ: <code>{format_money(bet)}</code> ᴇᴀᴄʜ\n"
            f"🏆 ᴡɪɴɴᴇʀ ᴛᴀᴋᴇs: <code>{format_money(bet * 2)}</code>\n\n"
            f"<i>ᴀɴʏᴏɴᴇ ᴛᴀᴘ ᴀᴄᴄᴇᴘᴛ ᴛᴏ ᴘʟᴀʏ!</i>",
            parse_mode=ParseMode.HTML,
            reply_markup=kb,
        )
    except Exception:
        adjust_user_balance(
            uid,
            bet,
            "rps_refund",
            "RPS challenge send failed",
            chat_id=update.effective_chat.id if update.effective_chat else None,
            source="/rps",
            meta={"mode": "pvp"},
        )
        raise
    
    now = time.time()
    token = f"rps:{msg.message_id}:{int(now)}:{random.randint(1000, 9999)}"
    active_rps[msg.message_id] = {
        "challenger": uid,
        "bet": bet,
        "challenger_choice": None,
        "opponent": None,
        "opponent_choice": None,
        "status": "pending",
        "created_at": now,
        "updated_at": now,
        "token": token,
        "chat_id": update.effective_chat.id if update.effective_chat else None,
    }
    context.application.create_task(expire_rps_later(context, msg.message_id, token))

async def rps_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    
    # --- BOT MODE CALLBACK ---
    if data.startswith("rpsbot_"):
        parts = data.split("|")
        choice = parts[0].replace("rpsbot_", "")
        uid, bet = int(parts[1]), int(parts[2])
        if query.from_user.id != uid:
            return await query.answer("❌ ɴᴏᴛ ʏᴏᴜʀ ɢᴀᴍᴇ!", show_alert=True)
        
        user = ensure_user_exists(query.from_user)
        if user['balance'] < bet:
            return await query.answer("📉 ɴᴏᴛ ᴇɴᴏᴜɢʜ!", show_alert=True)
        
        bot_choice = random.choice(["rock", "paper", "scissors"])
        if choice == bot_choice:
            result = f"🤝 <b>ᴅʀᴀᴡ!</b> ʙᴏᴛʜ {RPS_EMOJIS[choice]}"
        elif RPS_WINS[choice] == bot_choice:
            users_collection.update_one({"user_id": uid}, {"$inc": {"balance": bet, "game_wins": 1}})
            await add_xp(uid, XP_PER_GAME_WIN)
            result = f"🎉 <b>ʏᴏᴜ ᴡɪɴ!</b> +<code>{format_money(bet)}</code>"
        else:
            users_collection.update_one({"user_id": uid}, {"$inc": {"balance": -bet}})
            result = f"💀 <b>ʏᴏᴜ ʟᴏsᴇ!</b> -{format_money(bet)}"
        
        return await query.message.edit_text(
            f"✊ <b>{stylize_text('RPS vs Bot')}</b>\n\n"
            f"👤 ʏᴏᴜ: {RPS_EMOJIS[choice]}  🆚  🤖 ʙᴏᴛ: {RPS_EMOJIS[bot_choice]}\n\n{result}",
            parse_mode=ParseMode.HTML)
    
    # --- PVP ACCEPT/REJECT ---
    if data.startswith("rpspvp_"):
        parts = data.split("|")
        action = parts[0].replace("rpspvp_", "")
        challenger_id, bet = int(parts[1]), int(parts[2])
        mid = query.message.message_id
        opp_id = query.from_user.id
        game = active_rps.get(mid)

        if (
            not game
            or game.get("status") != "pending"
            or game.get("challenger") != challenger_id
            or game.get("bet") != bet
        ):
            return await query.answer("❌ ɢᴀᴍᴇ ᴇxᴘɪʀᴇᴅ ᴏʀ ᴀʟʀᴇᴀᴅʏ sᴛᴀʀᴛᴇᴅ!", show_alert=True)
        
        if action == "reject":
            if opp_id != challenger_id:
                return await query.answer("❌ ᴏɴʟʏ ᴄʜᴀʟʟᴇɴɢᴇʀ ᴄᴀɴ ᴄᴀɴᴄᴇʟ!", show_alert=True)
            active_rps.pop(mid, None)
            locked_refund(challenger_id, bet, chat_id=query.message.chat_id if query.message else None, source="/rps cancel")
            await query.answer("Challenge cancelled.")
            return await query.message.edit_text("❌ ᴄʜᴀʟʟᴇɴɢᴇ ᴄᴀɴᴄᴇʟʟᴇᴅ! ᴄᴏɪɴs ʀᴇғᴜɴᴅᴇᴅ.", parse_mode=ParseMode.HTML)
        
        if action == "accept":
            if opp_id == challenger_id:
                return await query.answer("❌ ᴄᴀɴ'ᴛ ᴘʟᴀʏ ᴡɪᴛʜ ʏᴏᴜʀsᴇʟғ!", show_alert=True)
            
            opp = ensure_user_exists(query.from_user)
            if opp['balance'] < bet:
                return await query.answer("📉 ɴᴏᴛ ᴇɴᴏᴜɢʜ ᴄᴏɪɴs!", show_alert=True)

            game["status"] = "accepting"
            charged = adjust_user_balance(
                opp_id,
                -bet,
                "rps_bet",
                "RPS opponent wager locked",
                chat_id=query.message.chat_id if query.message else None,
                target_user_id=challenger_id,
                source="/rps",
                require_gte=bet,
                meta={"message_id": mid},
            )
            if not charged:
                game["status"] = "pending"
                return await query.answer("📉 ɴᴏᴛ ᴇɴᴏᴜɢʜ ᴄᴏɪɴs!", show_alert=True)
            game['opponent'] = opp_id
            game['status'] = "playing"
            touch_game(game)
            await query.answer("Challenge accepted.")
            track_mission(opp_id, "play_game")
            
            # Show move selection for BOTH
            kb = InlineKeyboardMarkup([[
                rps_button("rock", f"rpsmove_rock|{mid}"),
                rps_button("paper", f"rpsmove_paper|{mid}"),
                rps_button("scissors", f"rpsmove_scissors|{mid}")
            ]])
            
            return await query.message.edit_text(
                f"✊ <b>{stylize_text('RPS PvP')}</b>\n━━━━━━━━━━━━\n\n"
                f"⚔️ <a href='tg://user?id={challenger_id}'>ᴘʟᴀʏᴇʀ 1</a> 🆚 {get_mention(opp)}\n"
                f"💰 ᴘᴏᴛ: <code>{format_money(bet * 2)}</code>\n\n"
                f"<i>ʙᴏᴛʜ ᴘʟᴀʏᴇʀs ᴛᴀᴘ ʏᴏᴜʀ ᴍᴏᴠᴇ!</i>",
                parse_mode=ParseMode.HTML, reply_markup=kb)
    
    # --- PVP MOVE SELECTION ---
    if data.startswith("rpsmove_"):
        parts = data.split("|")
        choice = parts[0].replace("rpsmove_", "")
        mid = int(parts[1])
        uid = query.from_user.id
        
        if mid not in active_rps:
            return await query.answer("❌ ɢᴀᴍᴇ ᴇxᴘɪʀᴇᴅ!", show_alert=True)
        
        game = active_rps[mid]
        if game_is_expired(game):
            active_rps.pop(mid, None)
            bet = int(game.get("bet", 0))
            c_idle = not game.get("challenger_choice")
            o_idle = not game.get("opponent_choice")
            c_refund = locked_refund(game["challenger"], bet, idle=c_idle, chat_id=query.message.chat_id if query.message else None, source="/rps timeout", meta={"message_id": mid})
            o_refund = {"refund": 0, "fee": 0}
            if game.get("opponent"):
                o_refund = locked_refund(game["opponent"], bet, idle=o_idle, chat_id=query.message.chat_id if query.message else None, source="/rps timeout", meta={"message_id": mid})
            await query.answer("⏳ Game expired.", show_alert=True)
            return await query.message.edit_text(
                f"⏳ <b>{stylize_text('RPS Expired')}</b>\n\n"
                f"ᴘ1 refund: <code>{format_money(c_refund['refund'])}</code> | fee: <code>{format_money(c_refund['fee'])}</code>\n"
                f"ᴘ2 refund: <code>{format_money(o_refund['refund'])}</code> | fee: <code>{format_money(o_refund['fee'])}</code>",
                parse_mode=ParseMode.HTML,
            )
        if uid != game['challenger'] and uid != game['opponent']:
            return await query.answer("❌ ɴᴏᴛ ʏᴏᴜʀ ɢᴀᴍᴇ!", show_alert=True)
        
        # Record choice
        if uid == game['challenger']:
            if game['challenger_choice']:
                return await query.answer("✅ ᴀʟʀᴇᴀᴅʏ ᴄʜᴏsᴇɴ!", show_alert=True)
            game['challenger_choice'] = choice
            touch_game(game)
            await query.answer(f"✅ ʏᴏᴜ ᴄʜᴏsᴇ {RPS_EMOJIS[choice]}", show_alert=True)
        else:
            if game['opponent_choice']:
                return await query.answer("✅ ᴀʟʀᴇᴀᴅʏ ᴄʜᴏsᴇɴ!", show_alert=True)
            game['opponent_choice'] = choice
            touch_game(game)
            await query.answer(f"✅ ʏᴏᴜ ᴄʜᴏsᴇ {RPS_EMOJIS[choice]}", show_alert=True)
        
        # Check if both chose
        if game['challenger_choice'] and game['opponent_choice']:
            c1, c2 = game['challenger_choice'], game['opponent_choice']
            bet = game['bet']
            pot = bet * 2
            active_rps.pop(mid, None)
            
            if c1 == c2:
                # Draw — refund both
                users_collection.update_one({"user_id": game['challenger']}, {"$inc": {"balance": bet}})
                users_collection.update_one({"user_id": game['opponent']}, {"$inc": {"balance": bet}})
                result = "🤝 <b>ᴅʀᴀᴡ!</b> ᴄᴏɪɴs ʀᴇғᴜɴᴅᴇᴅ."
            elif RPS_WINS[c1] == c2:
                # Challenger wins
                users_collection.update_one({"user_id": game['challenger']}, {"$inc": {"balance": pot, "game_wins": 1}})
                await add_xp(game['challenger'], XP_PER_GAME_WIN)
                result = f"🎉 <a href='tg://user?id={game['challenger']}'>ᴘʟᴀʏᴇʀ 1</a> ᴡɪɴs <code>{format_money(pot)}</code>!"
            else:
                # Opponent wins
                users_collection.update_one({"user_id": game['opponent']}, {"$inc": {"balance": pot, "game_wins": 1}})
                await add_xp(game['opponent'], XP_PER_GAME_WIN)
                result = f"🎉 <a href='tg://user?id={game['opponent']}'>ᴘʟᴀʏᴇʀ 2</a> ᴡɪɴs <code>{format_money(pot)}</code>!"
            
            await query.message.edit_text(
                f"✊ <b>{stylize_text('RPS Result')}</b>\n━━━━━━━━━━━━\n\n"
                f"<a href='tg://user?id={game['challenger']}'>ᴘ1</a>: {RPS_EMOJIS[c1]}  🆚  "
                f"<a href='tg://user?id={game['opponent']}'>ᴘ2</a>: {RPS_EMOJIS[c2]}\n\n{result}",
                parse_mode=ParseMode.HTML)

# 👋 SLAP COMMAND
async def slap_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from kazumi.config import SLAP_GIFS
    if not update.message.reply_to_message:
        return await update.message.reply_text("👋 ʀᴇᴘʟʏ ᴛᴏ sᴏᴍᴇᴏɴᴇ!", parse_mode=ParseMode.HTML)
    
    user = ensure_user_exists(update.effective_user)
    target = update.message.reply_to_message.from_user
    if target.id == update.effective_user.id:
        return await update.message.reply_text("🤦 ᴄᴀɴ'ᴛ sʟᴀᴘ ʏᴏᴜʀsᴇʟғ!", parse_mode=ParseMode.HTML)
    
    t_mention = f"<a href='tg://user?id={target.id}'>{target.first_name}</a>"
    caption = f"👋 {get_mention(user)} sʟᴀᴘᴘᴇᴅ {t_mention}! 💥"
    
    try:
        gif = pick_rotating_media("action:slap", SLAP_GIFS)
        await update.message.reply_animation(animation=gif, caption=caption, parse_mode=ParseMode.HTML)
    except:
        await update.message.reply_text(caption, parse_mode=ParseMode.HTML)

# 🥊 PUNCH COMMAND
async def punch_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from kazumi.config import PUNCH_GIFS
    if not update.message.reply_to_message:
        return await update.message.reply_text("🥊 ʀᴇᴘʟʏ ᴛᴏ sᴏᴍᴇᴏɴᴇ!", parse_mode=ParseMode.HTML)
    
    user = ensure_user_exists(update.effective_user)
    target = update.message.reply_to_message.from_user
    if target.id == update.effective_user.id:
        return await update.message.reply_text("🤦 ᴄᴀɴ'ᴛ ᴘᴜɴᴄʜ ʏᴏᴜʀsᴇʟғ!", parse_mode=ParseMode.HTML)
    
    t_mention = f"<a href='tg://user?id={target.id}'>{target.first_name}</a>"
    caption = f"🥊 {get_mention(user)} ᴘᴜɴᴄʜᴇᴅ {t_mention}! 👊"
    
    try:
        gif = pick_rotating_media("action:punch", PUNCH_GIFS)
        await update.message.reply_animation(animation=gif, caption=caption, parse_mode=ParseMode.HTML)
    except:
        await update.message.reply_text(caption, parse_mode=ParseMode.HTML)

# 🤗 HUG COMMAND
async def hug_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from kazumi.config import HUG_GIFS
    if not update.message.reply_to_message:
        return await update.message.reply_text("🤗 ʀᴇᴘʟʏ ᴛᴏ sᴏᴍᴇᴏɴᴇ!", parse_mode=ParseMode.HTML)
    
    user = ensure_user_exists(update.effective_user)
    target = update.message.reply_to_message.from_user
    if target.id == update.effective_user.id:
        return await update.message.reply_text("🤦 ᴄᴀɴ'ᴛ ʜᴜɢ ʏᴏᴜʀsᴇʟғ!", parse_mode=ParseMode.HTML)
    
    t_mention = f"<a href='tg://user?id={target.id}'>{target.first_name}</a>"
    caption = f"🤗 {get_mention(user)} ʜᴜɢɢᴇᴅ {t_mention}! ❤️"
    
    try:
        gif = pick_rotating_media("action:hug", HUG_GIFS)
        await update.message.reply_animation(animation=gif, caption=caption, parse_mode=ParseMode.HTML)
    except:
        await update.message.reply_text(caption, parse_mode=ParseMode.HTML)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🔢 NUMBER GUESS GAME
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

active_guesses = {}  # {chat_id: {number, tries, user_id}}

def _guess_rate(wins, matches):
    if not matches:
        return 0.0
    return (wins / matches) * 100

def _guess_rank_score(user_doc):
    matches = int(user_doc.get("guess_matches", 0) or 0)
    wins = int(user_doc.get("guess_wins", 0) or 0)
    coins = int(user_doc.get("guess_coins_earned", 0) or 0)
    fast = int(user_doc.get("guess_fast_wins", 0) or 0)
    rate = _guess_rate(wins, matches)
    return (rate, wins, fast, coins, -int(user_doc.get("guess_best_attempts", 999) or 999))

async def guess_leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users = list(users_collection.find({"guess_matches": {"$gt": 0}}))
    if not users:
        return await update.message.reply_text(
            "🔢 <b>Guess Leaderboard</b>\n━━━━━━━━━━━━\n\nNo guess stats yet. Start one with <code>/guess</code>.",
            parse_mode=ParseMode.HTML
        )

    users.sort(key=_guess_rank_score, reverse=True)
    lines = []
    for idx, doc in enumerate(users[:10], 1):
        matches = int(doc.get("guess_matches", 0) or 0)
        wins = int(doc.get("guess_wins", 0) or 0)
        losses = int(doc.get("guess_losses", 0) or 0)
        coins = int(doc.get("guess_coins_earned", 0) or 0)
        fast = int(doc.get("guess_fast_wins", 0) or 0)
        best = doc.get("guess_best_attempts")
        rate = _guess_rate(wins, matches)
        best_text = f"{best}ᴛ" if best else "—"
        lines.append(
            f"{idx}. {get_mention(doc)} — <b>{rate:.1f}%</b>\n"
            f"   🏆 {wins}W/{losses}L · ⚡ {fast} fast · 💰 {format_money(coins)} · best {best_text}"
        )

    await update.message.reply_text(
        "🔢 <b>Guess Leaderboard</b>\n"
        "━━━━━━━━━━━━\n"
        "<i>Ranked by win rate, then wins, fast solves and coins.</i>\n\n"
        + "\n".join(lines),
        parse_mode=ParseMode.HTML
    )

async def guess_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat.type == ChatType.PRIVATE:
        return await update.message.reply_text("❌ Group Only!", parse_mode=ParseMode.HTML)

    if context.args and context.args[0].lower() in {"top", "leaderboard", "lb", "rank", "ranking"}:
        return await guess_leaderboard(update, context)
    
    if chat.id in active_guesses:
        g = active_guesses[chat.id]
        return await update.message.reply_text(f"⚠️ Game active! {g['tries_left']} tries left. Guess 1-100!", parse_mode=ParseMode.HTML)
    
    ensure_user_exists(update.effective_user)
    number = random.randint(1, 100)
    active_guesses[chat.id] = {
        "number": number,
        "tries_left": GUESS_MAX_TRIES,
        "user_id": update.effective_user.id,
        "players": {},
    }
    
    await update.message.reply_text(
        f"🔢 <b>{stylize_text('Number Guess')}</b>\n\n"
        f"I picked a number <b>1-100</b>!\n"
        f"🎯 You have <b>{GUESS_MAX_TRIES}</b> tries.\n"
        f"💰 Reward: <code>{format_money(GUESS_REWARD)}</code>\n\n"
        f"<i>Type your guess in chat!</i>\n"
        f"<code>/guess top</code> shows win-rate leaderboard.",
        parse_mode=ParseMode.HTML
    )

async def guess_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return
    chat = update.effective_chat
    if chat.id not in active_guesses: return
    
    text = update.message.text.strip()
    if not text.isdigit(): return
    
    guess = int(text)
    if guess < 1 or guess > 100: return
    
    game = active_guesses[chat.id]
    target = game['number']
    game['tries_left'] -= 1
    
    user = ensure_user_exists(update.effective_user)
    uid = user["user_id"]
    players = game.setdefault("players", {})
    player_key = str(uid)
    first_try_in_match = player_key not in players
    players[player_key] = int(players.get(player_key, 0)) + 1
    attempts_used = players[player_key]
    if first_try_in_match:
        users_collection.update_one({"user_id": uid}, {"$inc": {"guess_matches": 1}})
    
    if guess == target:
        del active_guesses[chat.id]
        bonus = (game['tries_left'] + 1) * 200  # More tries left = more bonus
        fast_bonus = 1000 if attempts_used <= 3 else 0
        total = GUESS_REWARD + bonus
        if fast_bonus:
            total += fast_bonus
        users_collection.update_one(
            {"user_id": uid},
            {
                "$inc": {
                    "balance": total,
                    "game_wins": 1,
                    "guess_wins": 1,
                    "guess_coins_earned": total,
                    "guess_fast_wins": 1 if fast_bonus else 0,
                },
                "$min": {"guess_best_attempts": attempts_used},
            },
        )
        await add_xp(uid, XP_PER_GAME_WIN)
        fast_text = f"\n⚡ Fast solve bonus: <code>{format_money(fast_bonus)}</code>" if fast_bonus else ""
        await update.message.reply_text(
            f"🎉 <b>{stylize_text('CORRECT')}!</b> The number was <b>{target}</b>!\n"
            f"👤 Winner: {get_mention(user)}\n"
            f"🎯 Solved in: <b>{attempts_used}</b> tries\n"
            f"💰 Won: <code>{format_money(total)}</code> (Bonus: +{format_money(bonus)})"
            f"{fast_text}",
            parse_mode=ParseMode.HTML
        )
        raise ApplicationHandlerStop
    elif game['tries_left'] <= 0:
        del active_guesses[chat.id]
        loser_ids = []
        for raw_uid in game.get("players", {}):
            try:
                loser_ids.append(int(raw_uid))
            except (TypeError, ValueError):
                pass
        if loser_ids:
            users_collection.update_many({"user_id": {"$in": loser_ids}}, {"$inc": {"guess_losses": 1}})
        await update.message.reply_text(f"💀 <b>Game Over!</b> The number was <b>{target}</b>.", parse_mode=ParseMode.HTML)
        raise ApplicationHandlerStop
    else:
        hint = "📈 <b>Higher!</b>" if target > guess else "📉 <b>Lower!</b>"
        await update.message.reply_text(f"{hint} ({game['tries_left']} tries left)", parse_mode=ParseMode.HTML)
        raise ApplicationHandlerStop

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 💣 RUSSIAN ROULETTE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

active_rr = {}  # {chat_id: {players: [uid1, uid2], chamber: int, current: int, bet: int}}

async def expire_rr_later(context, chat_id, token):
    while True:
        game = active_rr.get(chat_id)
        if not game or game.get("token") != token:
            return
        wait_for = GAME_EXPIRE_SECONDS - (time.time() - float(game.get("updated_at", game.get("created_at", time.time()))))
        if wait_for > 0:
            await asyncio.sleep(wait_for + 1)
            continue
        break
    game = active_rr.pop(chat_id, None)
    if not game:
        return
    bet = int(game.get("bet", 0))
    if len(game.get("players", [])) < 2:
        refund = locked_refund(game["players"][0], bet, chat_id=chat_id, source="/rr timeout")
        text = f"⏳ <b>{stylize_text('Russian Roulette Expired')}</b>\n\nChallenge timed out. Refunded: <code>{format_money(refund['refund'])}</code>"
    else:
        current_player = game["players"][game["turn"] % 2]
        lines = []
        for uid in game["players"]:
            result = locked_refund(uid, bet, idle=(uid == current_player), chat_id=chat_id, source="/rr timeout")
            lines.append(f"<a href='tg://user?id={uid}'>Player</a>: refund <code>{format_money(result['refund'])}</code> | fee <code>{format_money(result['fee'])}</code>")
        text = f"⏳ <b>{stylize_text('Russian Roulette Expired')}</b>\n\n" + "\n".join(lines)
    message_id = game.get("message_id")
    try:
        if message_id:
            await context.bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=text, parse_mode=ParseMode.HTML)
        else:
            await context.bot.send_message(chat_id=chat_id, text=text, parse_mode=ParseMode.HTML)
    except BadRequest:
        pass

async def russian_roulette(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat.type == ChatType.PRIVATE:
        return await update.message.reply_text("❌ Group Only!", parse_mode=ParseMode.HTML)
    
    user = ensure_user_exists(update.effective_user)
    bet = RUSSIAN_ROULETTE_BET
    
    if user['balance'] < bet:
        return await update.message.reply_text(f"📉 Need <code>{format_money(bet)}</code>!", parse_mode=ParseMode.HTML)
    
    if chat.id in active_rr:
        game = active_rr[chat.id]
        if game_is_expired(game):
            active_rr.pop(chat.id, None)
            for pid in game.get("players", []):
                locked_refund(pid, game.get("bet", 0), chat_id=chat.id, source="/rr timeout")
            return await update.message.reply_text("⏳ Old Russian Roulette game expired. Locked bets were returned.", parse_mode=ParseMode.HTML)
        if len(game['players']) >= 2:
            return await update.message.reply_text("⚠️ Game full!", parse_mode=ParseMode.HTML)
        if user['user_id'] in game['players']:
            return await update.message.reply_text("⚠️ Already joined!", parse_mode=ParseMode.HTML)
        
        game['players'].append(user['user_id'])
        game["status"] = "playing"
        game["turn"] = 1
        touch_game(game)
        users_collection.update_one({"user_id": user['user_id']}, {"$inc": {"balance": -bet}})
        
        kb = InlineKeyboardMarkup([[
            Button("🔫 Pull Trigger", callback_data=f"rr_pull|{chat.id}")
        ]])
        
        sent = await update.message.reply_text(
            f"💣 <b>{stylize_text('Russian Roulette')}</b>\n\n"
            f"🔫 Both players joined!\n💰 Pot: <code>{format_money(bet * 2)}</code>\n\n"
            f"<i>{get_mention(user)}'s turn — Pull the trigger!</i>",
            parse_mode=ParseMode.HTML, reply_markup=kb
        )
        game["message_id"] = sent.message_id
        return
    
    users_collection.update_one({"user_id": user['user_id']}, {"$inc": {"balance": -bet}})
    now = time.time()
    token = f"rr:{chat.id}:{int(now)}:{random.randint(1000, 9999)}"
    active_rr[chat.id] = {
        "players": [user['user_id']], 
        "chamber": random.randint(1, 6), 
        "current": 1, 
        "bet": bet,
        "turn": 0,
        "status": "pending",
        "created_at": now,
        "updated_at": now,
        "token": token,
    }
    
    await update.message.reply_text(
        f"💣 <b>{stylize_text('Russian Roulette')}</b>\n\n"
        f"🔫 {get_mention(user)} loaded the revolver!\n"
        f"💰 Entry: <code>{format_money(bet)}</code>\n\n"
        f"<i>Someone type /rr to accept the challenge!</i>",
        parse_mode=ParseMode.HTML
    )
    context.application.create_task(expire_rr_later(context, chat.id, token))

async def rr_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data.split("|")
    chat_id = int(data[1])
    
    if chat_id not in active_rr:
        return await query.answer("❌ Game ended!", show_alert=True)
    
    game = active_rr[chat_id]
    if game_is_expired(game):
        active_rr.pop(chat_id, None)
        bet = int(game.get("bet", 0))
        current_player = game["players"][game["turn"] % 2] if len(game.get("players", [])) >= 2 else None
        lines = []
        for pid in game.get("players", []):
            result = locked_refund(pid, bet, idle=(pid == current_player), chat_id=chat_id, source="/rr timeout")
            lines.append(f"<a href='tg://user?id={pid}'>Player</a>: refund <code>{format_money(result['refund'])}</code> | fee <code>{format_money(result['fee'])}</code>")
        await query.answer("⏳ Game expired.", show_alert=True)
        return await query.message.edit_text(
            f"⏳ <b>{stylize_text('Russian Roulette Expired')}</b>\n\n" + "\n".join(lines),
            parse_mode=ParseMode.HTML,
        )
    uid = query.from_user.id
    
    if uid not in game['players']:
        return await query.answer("❌ Not in this game!", show_alert=True)
    
    current_player = game['players'][game['turn'] % 2]
    if uid != current_player:
        return await query.answer("⏳ Not your turn!", show_alert=True)
    
    if game['current'] == game['chamber']:
        # BANG!
        other = game['players'][0] if game['players'][1] == uid else game['players'][1]
        prize = game['bet'] * 2
        users_collection.update_one({"user_id": other}, {"$inc": {"balance": prize, "rr_wins": 1, "game_wins": 1}})
        await add_xp(other, XP_PER_GAME_WIN)
        del active_rr[chat_id]
        
        await query.message.edit_text(
            f"💥 <b>BANG!</b>\n\n"
            f"💀 <a href='tg://user?id={uid}'>Player</a> is dead!\n"
            f"🎉 <a href='tg://user?id={other}'>Winner</a> takes <code>{format_money(prize)}</code>!",
            parse_mode=ParseMode.HTML
        )
    else:
        game['current'] += 1
        game['turn'] += 1
        touch_game(game)
        next_player = game['players'][game['turn'] % 2]
        
        kb = InlineKeyboardMarkup([[
            Button("🔫 Pull Trigger", callback_data=f"rr_pull|{chat_id}")
        ]])
        
        await query.message.edit_text(
            f"💣 <b>*click*</b> — Safe! ({game['current']-1}/6)\n\n"
            f"🔫 <a href='tg://user?id={next_player}'>Next player</a>'s turn!",
            parse_mode=ParseMode.HTML, reply_markup=kb
        )

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🪙 COINFLIP
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

HIGHLOW_MIN_BET = 100
HIGHLOW_MAX_BET = 500_000
HIGHLOW_TTL_SECONDS = 10 * 60
HIGHLOW_CARD_NAMES = {
    1: "A", 2: "2", 3: "3", 4: "4", 5: "5", 6: "6", 7: "7",
    8: "8", 9: "9", 10: "10", 11: "J", 12: "Q", 13: "K",
}
active_highlow = {}

def highlow_card(exclude=None):
    return random.choice([card for card in range(1, 14) if card != exclude])

def highlow_is_expired(game):
    return (time.time() - float(game.get("updated_at", game.get("created_at", 0)))) > HIGHLOW_TTL_SECONDS

def clear_expired_highlow(uid, *, force=False):
    game = active_highlow.get(uid)
    if not game or (not force and not highlow_is_expired(game)):
        return None
    refund_info = locked_refund(
        uid,
        int(game.get("bet", 0)),
        idle=True,
        chat_id=game.get("chat_id"),
        source="/hl timeout",
        meta={"message_id": game.get("message_id"), "round": int(game.get("round", 0))},
    )
    game["refund_info"] = refund_info
    del active_highlow[uid]
    return game

async def expire_highlow_later(context, uid, token):
    while True:
        game = active_highlow.get(uid)
        if not game or game.get("token") != token:
            return
        elapsed = time.time() - float(game.get("updated_at", game.get("created_at", time.time())))
        wait_for = HIGHLOW_TTL_SECONDS - elapsed
        if wait_for > 0:
            await asyncio.sleep(wait_for + 2)
            continue
        break
    expired = clear_expired_highlow(uid, force=True)
    if not expired:
        return
    chat_id = expired.get("chat_id")
    message_id = expired.get("message_id")
    if not chat_id or not message_id:
        return
    try:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=(
                f"\U000023F3 <b>{stylize_text('High Low Expired')}</b>\n\n"
                f"\U0001F4B5 Refunded: <code>{format_money(expired.get('refund_info', {}).get('refund', expired['bet']))}</code>\n"
                f"\U0001F4B8 Idle fee: <code>{format_money(expired.get('refund_info', {}).get('fee', 0))}</code>\n"
                f"<i>Start again with /hl {HIGHLOW_MIN_BET}</i>"
            ),
            parse_mode=ParseMode.HTML,
        )
    except BadRequest:
        pass

def highlow_card_text(card):
    return HIGHLOW_CARD_NAMES.get(card, str(card))

def highlow_payout(bet, round_no, profile):
    if round_no <= 0:
        return bet
    multipliers = profile["multipliers"]
    return int(bet * multipliers[min(round_no, profile["max_rounds"]) - 1])

def highlow_keyboard(uid, allow_cashout=True):
    keyboard = [[
        Button("\U0001F4C8 Higher", callback_data=f"hl_higher|{uid}"),
        Button("\U0001F4C9 Lower", callback_data=f"hl_lower|{uid}"),
    ]]
    if allow_cashout:
        keyboard.append([Button("\U0001F4B0 Cash Out", callback_data=f"hl_cash|{uid}")])
    return InlineKeyboardMarkup(keyboard)

def highlow_text(game, intro=False):
    round_no = game["round"]
    profile = game["profile"]
    max_rounds = profile["max_rounds"]
    next_payout = highlow_payout(game["bet"], min(round_no + 1, max_rounds), profile)
    safe_payout = highlow_payout(game["bet"], round_no, profile)
    lead = f"\U0001F0CF <b>{stylize_text('High Low')}</b>"
    if intro:
        lead += "\n<i>Guess if the next card is higher or lower.</i>"
    return (
        f"{lead}\n"
        f"\U0001F4B0 <b>Bet:</b> <code>{format_money(game['bet'])}</code>\n"
        f"\U0001F3AF <b>Tier:</b> <code>{profile['name']}</code>\n"
        f"\U0001F3AF <b>Round:</b> <code>{round_no}/{max_rounds}</code>\n"
        f"\U0001F4B5 <b>Cashout:</b> <code>{format_money(safe_payout)}</code>\n"
        f"\U00002728 <b>Next Win:</b> <code>{format_money(next_payout)}</code>\n\n"
        f"\U0001F0CF <b>Current Card:</b> <code>{highlow_card_text(game['card'])}</code>\n"
        f"<i>Will the next card be higher or lower?</i>"
    )

async def highlow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = ensure_user_exists(update.effective_user)
    uid = user["user_id"]

    if uid in active_highlow:
        expired = clear_expired_highlow(uid)
        if expired:
            await update.message.reply_text(
                f"\U000023F3 Old /highlow game expired. Refunded: <code>{format_money(expired.get('refund_info', {}).get('refund', expired['bet']))}</code> | Idle fee: <code>{format_money(expired.get('refund_info', {}).get('fee', 0))}</code>",
                parse_mode=ParseMode.HTML,
            )
        else:
            game = active_highlow[uid]
            age_left = max(1, int((HIGHLOW_TTL_SECONDS - (time.time() - float(game.get("updated_at", game.get("created_at", time.time()))))) // 60))
            return await update.message.reply_text(
                f"\U000026A0\ufe0f Finish your current /highlow game first.\n"
                f"\U000023F3 Auto-expire in about <code>{age_left}m</code>.",
                parse_mode=ParseMode.HTML,
            )

    if not context.args:
        return await update.message.reply_text(
            f"\U0001F0CF <b>{stylize_text('High Low')}</b>\n"
            f"<b>Usage:</b> <code>/highlow {HIGHLOW_MIN_BET}</code>\n"
            f"<b>Alias:</b> <code>/hl {HIGHLOW_MIN_BET}</code>",
            parse_mode=ParseMode.HTML,
        )

    try:
        bet = int(context.args[0])
    except Exception:
        return await update.message.reply_text("\U000026A0\ufe0f Invalid bet.", parse_mode=ParseMode.HTML)

    if bet < HIGHLOW_MIN_BET or bet > HIGHLOW_MAX_BET:
        return await update.message.reply_text(
            f"\U000026A0\ufe0f Bet range: <code>{format_money(HIGHLOW_MIN_BET)}</code> - <code>{format_money(HIGHLOW_MAX_BET)}</code>",
            parse_mode=ParseMode.HTML,
        )
    if user["balance"] < bet:
        return await update.message.reply_text("\U0001F4C9 Not enough coins!", parse_mode=ParseMode.HTML)

    charged = adjust_user_balance(
        uid,
        -bet,
        "highlow_bet",
        "Started high-low",
        chat_id=update.effective_chat.id if update.effective_chat else None,
        source="/hl",
        require_gte=bet,
        meta={"bet": bet},
    )
    if not charged:
        return await update.message.reply_text("\U0001F4C9 Not enough coins!", parse_mode=ParseMode.HTML)
    track_mission(uid, "play_game")
    level, _, _ = get_level(user.get("xp", 0))
    profile = highlow_profile(level)
    now = time.time()
    token = f"{uid}:{int(now)}:{random.randint(1000, 9999)}"
    game = {
        "uid": uid,
        "bet": bet,
        "card": highlow_card(),
        "profile": profile,
        "level": level,
        "round": 0,
        "created_at": now,
        "updated_at": now,
        "token": token,
        "chat_id": update.effective_chat.id if update.effective_chat else None,
    }
    sent = await update.message.reply_text(
        highlow_text(game, intro=True),
        parse_mode=ParseMode.HTML,
        reply_markup=highlow_keyboard(uid, allow_cashout=False),
    )
    game["message_id"] = sent.message_id
    active_highlow[uid] = game
    context.application.create_task(expire_highlow_later(context, uid, token))

async def highlow_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    action, uid_text = query.data.split("|", 1)
    uid = int(uid_text)

    if query.from_user.id != uid:
        return await query.answer("\U0000274C Not your game!", show_alert=True)
    if uid not in active_highlow:
        return await query.answer("\U0000274C Game expired!", show_alert=True)

    game = active_highlow[uid]
    if highlow_is_expired(game):
        expired = clear_expired_highlow(uid)
        if expired:
            await query.answer("\U000023F3 Game expired. Bet refunded.", show_alert=True)
            return await query.message.edit_text(
                f"\U000023F3 <b>{stylize_text('High Low Expired')}</b>\n\n"
                f"\U0001F4B5 Refunded: <code>{format_money(expired.get('refund_info', {}).get('refund', expired['bet']))}</code>\n"
                f"\U0001F4B8 Idle fee: <code>{format_money(expired.get('refund_info', {}).get('fee', 0))}</code>\n"
                f"<i>Start again with /hl {HIGHLOW_MIN_BET}</i>",
                parse_mode=ParseMode.HTML,
            )
        return await query.answer("\U0000274C Game expired!", show_alert=True)
    if game.get("processing"):
        return await query.answer("Previous move is still processing.", show_alert=True)
    if action not in {"hl_cash", "hl_higher", "hl_lower"}:
        return await query.answer("Invalid High-Low action.", show_alert=True)
    game["updated_at"] = time.time()

    if action == "hl_cash":
        if int(game.get("round", 0)) <= 0:
            return await query.answer("Win at least one round before cashing out.", show_alert=True)
        active_highlow.pop(uid, None)
        payout = highlow_payout(game["bet"], game["round"], game["profile"])
        adjust_user_balance(
            uid,
            payout,
            "highlow_cashout",
            "Cashed out high-low",
            chat_id=query.message.chat_id if query.message else None,
            source="/hl cashout",
            meta={"round": int(game.get("round", 0)), "bet": int(game.get("bet", 0))},
        )
        await query.answer("Cashing out...")
        return await query.message.edit_text(
            f"\U0001F4B0 <b>{stylize_text('Cashed Out')}!</b>\n\n"
            f"\U0001F464 {get_mention(query.from_user)}\n"
            f"\U00002728 Rounds cleared: <code>{game['round']}</code>\n"
            f"\U0001F4B5 Payout: <code>{format_money(payout)}</code>",
            parse_mode=ParseMode.HTML,
        )

    game["processing"] = True
    old_card = game["card"]
    new_card = highlow_card(exclude=old_card)
    game["card"] = new_card
    guessed_higher = action == "hl_higher"
    correct = new_card > old_card if guessed_higher else new_card < old_card

    if not correct:
        lost = game["bet"]
        active_highlow.pop(uid, None)
        direction = "higher" if guessed_higher else "lower"
        await query.answer("Lost.")
        return await query.message.edit_text(
            f"\U0001F4A5 <b>{stylize_text('High Low Lost')}!</b>\n\n"
            f"\U0001F0CF Old: <code>{highlow_card_text(old_card)}</code>\n"
            f"\U0001F0CF New: <code>{highlow_card_text(new_card)}</code>\n"
            f"\U0001F3AF Guess: <b>{direction}</b>\n"
            f"\U0001F4B8 Lost: <code>{format_money(lost)}</code>",
            parse_mode=ParseMode.HTML,
        )

    game["round"] += 1
    max_rounds = game["profile"]["max_rounds"]
    if game["round"] >= max_rounds:
        active_highlow.pop(uid, None)
        payout = highlow_payout(game["bet"], game["round"], game["profile"])
        adjust_user_balance(
            uid,
            payout,
            "highlow_win",
            "Perfect high-low run",
            chat_id=query.message.chat_id if query.message else None,
            source="/hl",
            extra_inc={"game_wins": 1},
            meta={"round": int(game.get("round", 0)), "bet": int(game.get("bet", 0))},
        )
        await add_xp(uid, XP_PER_GAME_WIN * 2)
        await query.answer("Perfect run!")
        return await query.message.edit_text(
            f"\U0001F3C6 <b>{stylize_text('Perfect Run')}!</b>\n\n"
            f"\U0001F0CF Final card: <code>{highlow_card_text(new_card)}</code>\n"
            f"\U00002728 Cleared: <code>{max_rounds}/{max_rounds}</code>\n"
            f"\U0001F4B5 Payout: <code>{format_money(payout)}</code>",
            parse_mode=ParseMode.HTML,
        )

    game["processing"] = False
    await query.answer("Correct.")
    await query.message.edit_text(
        f"\U00002705 <b>{stylize_text('Correct')}!</b>\n\n"
        f"\U0001F0CF Old: <code>{highlow_card_text(old_card)}</code>\n"
        f"\U0001F0CF New: <code>{highlow_card_text(new_card)}</code>\n\n"
        f"{highlow_text(game)}",
        parse_mode=ParseMode.HTML,
        reply_markup=highlow_keyboard(uid, allow_cashout=True),
    )

active_tapraces = {}
TAPRACE_TARGET = 15
TAPRACE_REWARD = 3500
TAPRACE_TTL = 90
TAPRACE_DAILY_WIN_LIMIT = 1
TAPRACE_MIN_TARGET = 5
TAPRACE_MAX_TARGET = 50
TAPRACE_MIN_REWARD = 500
TAPRACE_MAX_REWARD = 20000


def today_key():
    return datetime.utcnow().strftime("%Y-%m-%d")


def taprace_daily_wins(user):
    data = user.get("taprace_daily", {}) or {}
    return int(data.get("wins", 0)) if data.get("date") == today_key() else 0


def parse_taprace_args(args):
    target = TAPRACE_TARGET
    reward = TAPRACE_REWARD
    numbers = []
    for arg in args:
        cleaned = "".join(ch for ch in str(arg) if ch.isdigit())
        if cleaned:
            numbers.append(int(cleaned))
    if numbers:
        target = max(TAPRACE_MIN_TARGET, min(numbers[0], TAPRACE_MAX_TARGET))
    if len(numbers) >= 2:
        reward = max(TAPRACE_MIN_REWARD, min(numbers[1], TAPRACE_MAX_REWARD))
    return target, reward


def taprace_markup(chat_id):
    return InlineKeyboardMarkup([[
        Button("\U0001F525 Tap", callback_data=f"taprace_tap|{chat_id}")
    ]])


def taprace_scoreboard(game):
    scores = sorted(game["scores"].items(), key=lambda item: item[1], reverse=True)[:5]
    if not scores:
        return "<i>No taps yet. Be first.</i>"
    lines = []
    for idx, (uid, score) in enumerate(scores, 1):
        name = game["names"].get(uid, "Player")
        lines.append(f"<code>{idx}.</code> <a href='tg://user?id={uid}'>{name}</a> - <b>{score}</b>")
    return "\n".join(lines)


def taprace_text(game):
    left = max(0, int(game["expires_at"] - time.time()))
    return (
        f"\U0001F525 <b>{stylize_text('Tap Race')}</b>\n"
        f"\U0001F3AF <b>Goal:</b> <code>{game['target']}</code> taps\n"
        f"\U0001F4B0 <b>Reward:</b> <code>{format_money(game['reward'])}</code>\n"
        f"\u23F3 <b>Time:</b> <code>{left}s</code>\n\n"
        f"{taprace_scoreboard(game)}"
    )


async def taprace_answer(query, text=None, show_alert=False):
    try:
        await query.answer(text, show_alert=show_alert)
    except BadRequest:
        pass


async def taprace_edit(message, text, reply_markup=None):
    try:
        await message.edit_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=reply_markup,
        )
    except BadRequest as exc:
        if "Message is not modified" not in str(exc):
            raise

async def expire_taprace_later(context, chat_id, token):
    while True:
        game = active_tapraces.get(chat_id)
        if not game or game.get("token") != token:
            return
        wait_for = float(game.get("expires_at", time.time())) - time.time()
        if wait_for > 0:
            await asyncio.sleep(wait_for + 1)
            continue
        break
    game = active_tapraces.pop(chat_id, None)
    if not game:
        return
    message_id = game.get("message_id")
    try:
        if message_id:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text="\u23F3 <b>Tap Race expired.</b>\nNo winner this time.",
                parse_mode=ParseMode.HTML,
            )
        else:
            await context.bot.send_message(
                chat_id=chat_id,
                text="\u23F3 <b>Tap Race expired.</b>\nNo winner this time.",
                parse_mode=ParseMode.HTML,
            )
    except BadRequest:
        pass


async def taprace(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat.type == ChatType.PRIVATE:
        return await update.message.reply_text(
            "\U000026E9\ufe0f <b>Tap Race is for groups.</b>",
            parse_mode=ParseMode.HTML,
        )

    if chat.id in active_tapraces:
        return await update.message.reply_text(
            "\U000026A0\ufe0f <b>A Tap Race is already active.</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=taprace_markup(chat.id),
        )

    starter = ensure_user_exists(update.effective_user)
    if taprace_daily_wins(starter) >= TAPRACE_DAILY_WIN_LIMIT:
        await update.message.reply_text(
            "\u23F3 <b>Tap Race daily limit reached.</b>\n"
            "You can host the race, but you can not win another Tap Race reward today.",
            parse_mode=ParseMode.HTML,
        )
    target, reward = parse_taprace_args(context.args)
    track_many(update.effective_user.id, ["play_game", "group_challenge", "taprace"])
    token = f"taprace:{chat.id}:{int(time.time())}:{random.randint(1000, 9999)}"
    game = {
        "chat_id": chat.id,
        "scores": {},
        "names": {},
        "started_by": update.effective_user.id,
        "target": target,
        "reward": reward,
        "expires_at": time.time() + TAPRACE_TTL,
        "token": token,
    }
    active_tapraces[chat.id] = game

    sent = await update.message.reply_text(
        taprace_text(game),
        parse_mode=ParseMode.HTML,
        reply_markup=taprace_markup(chat.id),
    )
    game["message_id"] = sent.message_id
    context.application.create_task(expire_taprace_later(context, chat.id, token))


async def taprace_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    _, chat_id_text = query.data.split("|", 1)
    chat_id = int(chat_id_text)
    game = active_tapraces.get(chat_id)

    if not game:
        return await taprace_answer(query, "Race expired.", show_alert=True)
    if time.time() > game["expires_at"]:
        del active_tapraces[chat_id]
        await taprace_edit(
            query.message,
            "\u23F3 <b>Tap Race expired.</b>\nNo winner this time.",
        )
        return await taprace_answer(query, "Race expired.", show_alert=True)

    user = ensure_user_exists(query.from_user)
    uid = user["user_id"]
    if taprace_daily_wins(user) >= TAPRACE_DAILY_WIN_LIMIT:
        return await taprace_answer(query, "Daily Tap Race reward already claimed.", show_alert=True)

    track_many(uid, ["play_game", "taprace"])
    game["scores"][uid] = game["scores"].get(uid, 0) + 1
    game["names"][uid] = query.from_user.first_name

    if game["scores"][uid] >= game["target"]:
        adjust_user_balance(
            uid,
            game["reward"],
            "taprace_win",
            f"Won Tap Race in {query.message.chat.title if query.message and query.message.chat else 'group'}",
            chat_id=chat_id,
            source="/taprace",
            extra_inc={"game_wins": 1, "xp": XP_PER_GAME_WIN, "taprace_daily.wins": 1},
            extra_set={"taprace_daily.date": today_key()},
            meta={"target": game["target"]},
        )
        del active_tapraces[chat_id]
        await taprace_edit(
            query.message,
            f"\U0001F3C6 <b>{stylize_text('Tap Race Winner')}!</b>\n\n"
            f"{get_mention(query.from_user)} reached <code>{game['target']}</code> taps first.\n"
            f"\U0001F4B0 <b>Reward:</b> <code>{format_money(game['reward'])}</code>\n"
            f"<i>One Tap Race win per user per day.</i>",
        )
        return await taprace_answer(query, "You won!", show_alert=True)

    await taprace_answer(query, f"{game['scores'][uid]}/{game['target']}")
    if game["scores"][uid] % 3 == 0:
        await taprace_edit(
            query.message,
            taprace_text(game),
            reply_markup=taprace_markup(chat_id),
        )


async def coinflip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = ensure_user_exists(update.effective_user)
    if not context.args or len(context.args) < 2:
        return await update.message.reply_text("🪙 <b>Usage:</b> <code>/cf heads 500</code>", parse_mode=ParseMode.HTML)
    
    side = context.args[0].lower()
    if side not in ["heads", "tails", "h", "t"]:
        return await update.message.reply_text("⚠️ Choose <b>heads</b> or <b>tails</b>!", parse_mode=ParseMode.HTML)
    
    parsed = parse_money(context.args[1])
    if parsed == "all":
        bet = min(user.get("balance", 0), COINFLIP_MAX_BET)
    elif isinstance(parsed, int):
        bet = parsed
    else:
        return await update.message.reply_text(
            format_display_text(f"⚠️ <b>{stylize_text('Invalid Bet')}!</b> Enter a valid number.", ParseMode.HTML),
            parse_mode=ParseMode.HTML
        )
    
    if bet < COINFLIP_MIN_BET or bet > COINFLIP_MAX_BET:
        return await update.message.reply_text(
            format_display_text(
                f"⚠️ <b>{stylize_text('Wager Limit')}!</b> Bet range: <code>{format_money(COINFLIP_MIN_BET)}</code> - <code>{format_money(COINFLIP_MAX_BET)}</code>",
                ParseMode.HTML
            ),
            parse_mode=ParseMode.HTML
        )
    charged = adjust_user_balance(
        user["user_id"],
        -bet,
        category="coinflip_bet",
        reason=f"Coinflip bet of {format_money(bet)} on {side}",
        chat_id=update.effective_chat.id if update.effective_chat else None,
        source="/coinflip",
        require_gte=bet,
    )
    if not charged:
        return await update.message.reply_text("📉 Not enough coins!", parse_mode=ParseMode.HTML)
    
    side = "heads" if side in ["heads", "h"] else "tails"
    result = random.choice(["heads", "tails"])
    track_mission(user["user_id"], "play_game")
    
    if side == result:
        total_payout = bet * 2
        adjust_user_balance(
            user["user_id"],
            total_payout,
            category="coinflip_win",
            reason=f"Won Coinflip ({result}) +{format_money(bet)}",
            chat_id=update.effective_chat.id if update.effective_chat else None,
            source="/coinflip",
            extra_inc={"game_wins": 1},
        )
        await add_xp(user['user_id'], XP_PER_GAME_WIN)
        text = f"🪙 <b>{result.upper()}!</b>\n\n🎉 You won <code>{format_money(bet)}</code>!"
    else:
        text = f"🪙 <b>{result.upper()}!</b>\n\n💀 You lost <code>{format_money(bet)}</code>!"
    
    await update.message.reply_text(format_display_text(text, ParseMode.HTML), parse_mode=ParseMode.HTML)
