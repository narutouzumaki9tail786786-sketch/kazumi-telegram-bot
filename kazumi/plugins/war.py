import random
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
# ⚔️ BATTLEFIELD WAR
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

active_wars = {}
# Structure: { game_id: {p1, p2, p1_name, p2_name, p1_hp, p2_hp, p1_max_hp, p2_max_hp,
#                        p1_shield, p2_shield, turn, bet, status, chat_id} }

BASE_HP = 500
ATTACK_NORMAL = (80, 120)
ATTACK_HEAVY = (150, 250)
HEAVY_ACCURACY = 0.65
SHIELD_REDUCTION = 0.60

def get_hp_bar(current, maximum):
    """Generates a visual HP bar."""
    filled = round((current / maximum) * 10)
    bar = "❤️" * filled + "🖤" * (10 - filled)
    return f"{bar} ({current}/{maximum})"

def get_weapon_buff(user_doc):
    """Gets weapon damage buff from inventory."""
    return sum(i.get('buff', 0) for i in user_doc.get('inventory', []) if i.get('type') == 'weapon')

def get_armor_buff(user_doc):
    """Gets armor defense buff from inventory."""
    return sum(i.get('buff', 0) for i in user_doc.get('inventory', []) if i.get('type') == 'armor')

def war_player_mention(game, user_id):
    name = game["p1_name"] if user_id == game["p1"] else game["p2_name"]
    return f"<a href='tg://user?id={int(user_id)}'>{html.escape(name)}</a>"

def build_war_text(game):
    p1_bar = get_hp_bar(max(0, game['p1_hp']), game['p1_max_hp'])
    p2_bar = get_hp_bar(max(0, game['p2_hp']), game['p2_max_hp'])
    turn_name = war_player_mention(game, game['turn'])

    text = (
        f"⚔️ <b>{stylize_text('BATTLEFIELD WAR')}</b> ⚔️\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🗡️ <b>{war_player_mention(game, game['p1'])}</b>\n{p1_bar}\n\n"
        f"🛡️ <b>{war_player_mention(game, game['p2'])}</b>\n{p2_bar}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"⏳ <b>{turn_name}'s Turn!</b> Choose your move:"
    )
    return text

def build_war_buttons(game_id):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⚔️ Attack", callback_data=f"war_atk|{game_id}"),
            InlineKeyboardButton("💥 Heavy Strike", callback_data=f"war_heavy|{game_id}"),
        ],
        [
            InlineKeyboardButton("🛡️ Shield Up", callback_data=f"war_shield|{game_id}"),
        ]
    ])

def touch_war(game):
    game["updated_at"] = time.time()

def refund_war_player(user_id, bet, *, idle, chat_id, game_id):
    return refund_locked_bet(
        user_id,
        bet,
        idle=idle,
        adjust_user_balance=adjust_user_balance,
        chat_id=chat_id,
        source="/war timeout",
        meta={"game_id": game_id},
    )

async def expire_war_later(context, game_id):
    while True:
        game = active_wars.get(game_id)
        if not game or game.get("status") not in {"pending", "playing"}:
            return
        wait_for = GAME_EXPIRE_SECONDS - (time.time() - float(game.get("updated_at", game.get("created_at", time.time()))))
        if wait_for > 0:
            await asyncio.sleep(wait_for + 1)
            continue
        break
    game = active_wars.pop(game_id, None)
    if not game:
        return
    if game.get("status") == "pending":
        text = "⏳ <b>War challenge expired.</b>"
    else:
        bet = int(game.get("bet", 0))
        turn = game.get("turn")
        p1_refund = refund_war_player(game["p1"], bet, idle=(turn == game["p1"]), chat_id=game.get("chat_id"), game_id=game_id)
        p2_refund = refund_war_player(game["p2"], bet, idle=(turn == game["p2"]), chat_id=game.get("chat_id"), game_id=game_id)
        text = (
            f"⏳ <b>{stylize_text('War Expired')}</b>\n\n"
            f"{war_player_mention(game, game['p1'])}: refund <code>{p1_refund['refund']:,}</code> | fee <code>{p1_refund['fee']:,}</code>\n"
            f"{war_player_mention(game, game['p2'])}: refund <code>{p2_refund['refund']:,}</code> | fee <code>{p2_refund['fee']:,}</code>"
        )
    try:
        if game.get("message_id"):
            await context.bot.edit_message_text(chat_id=game["chat_id"], message_id=game["message_id"], text=text, parse_mode=ParseMode.HTML)
        else:
            await context.bot.send_message(chat_id=game["chat_id"], text=text, parse_mode=ParseMode.HTML)
    except BadRequest:
        pass

async def war_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Challenge someone to a Battlefield War."""
    user = update.effective_user
    chat = update.effective_chat
    user_doc = ensure_user_exists(user)

    if not update.message.reply_to_message:
        await update.message.reply_text(
            "⚔️ <b>Usage:</b> Reply to a user and type:\n"
            "<code>/war</code> — Free battle\n"
            "<code>/war 5000</code> — Bet 5000 coins!",
            parse_mode=ParseMode.HTML
        )
        return

    target_user = update.message.reply_to_message.from_user
    if target_user.is_bot or target_user.id == user.id:
        await update.message.reply_text("❌ Can't challenge bots or yourself!")
        return

    target_doc = ensure_user_exists(target_user)

    # Optional bet
    bet = 0
    if context.args and context.args[0].isdigit():
        bet = int(context.args[0])
        if user_doc.get('balance', 0) < bet:
            return await update.message.reply_text("❌ Not enough coins for the bet!")
        if target_doc.get('balance', 0) < bet:
            return await update.message.reply_text(f"❌ <b>{get_mention(target_user)}</b> doesn't have enough coins!", parse_mode=ParseMode.HTML)

    game_id = str(uuid.uuid4())[:8]
    now = time.time()

    # Calculate HP based on equipment
    p1_armor = get_armor_buff(user_doc)
    p2_armor = get_armor_buff(target_doc)

    p1_max_hp = int(BASE_HP * (1 + p1_armor * 0.5))
    p2_max_hp = int(BASE_HP * (1 + p2_armor * 0.5))

    active_wars[game_id] = {
        "p1": user.id, "p1_name": user.first_name,
        "p2": target_user.id, "p2_name": target_user.first_name,
        "p1_hp": p1_max_hp, "p2_hp": p2_max_hp,
        "p1_max_hp": p1_max_hp, "p2_max_hp": p2_max_hp,
        "p1_shield": False, "p2_shield": False,
        "p1_weapon": get_weapon_buff(user_doc),
        "p2_weapon": get_weapon_buff(target_doc),
        "turn": user.id,
        "bet": bet,
        "status": "pending",
        "chat_id": chat.id,
        "created_at": now,
        "updated_at": now,
    }

    bet_text = f" for <b>${bet:,}</b>!" if bet > 0 else "!"
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("⚔️ Accept Battle", callback_data=f"war_acc|{game_id}")],
        [InlineKeyboardButton("🏳️ Decline", callback_data=f"war_dec|{game_id}")]
    ])

    sent = await update.message.reply_text(
        f"⚔️ <b>{stylize_text('WAR CHALLENGE')}</b> ⚔️\n\n"
        f"{get_mention(user)} has challenged {get_mention(target_user)}{bet_text}\n\n"
        f"🗡️ <b>{get_mention(user)}</b> — HP: {p1_max_hp} | Weapon: +{int(get_weapon_buff(user_doc)*100)}%\n"
        f"🛡️ <b>{get_mention(target_user)}</b> — HP: {p2_max_hp} | Armor: +{int(get_armor_buff(target_doc)*100)}%\n\n"
        f"⏳ Waiting for <b>{get_mention(target_user)}</b> to accept...",
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard
    )
    active_wars[game_id]["message_id"] = sent.message_id
    context.application.create_task(expire_war_later(context, game_id))

async def war_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles all War game button callbacks."""
    query = update.callback_query
    user = query.from_user
    parts = query.data.split("|")
    action = parts[0]
    game_id = parts[1]

    game = active_wars.get(game_id)
    if not game:
        return await query.answer("❌ This battle has expired!", show_alert=True)

    # --- ACCEPT / DECLINE ---
    if action == "war_acc":
        if user.id != game['p2']:
            return await query.answer("❌ This challenge isn't for you!", show_alert=True)
        if game['status'] != "pending":
            return await query.answer("❌ Game already started!", show_alert=True)

        game['status'] = "accepting"
        if game['bet'] > 0:
            p1_charge = adjust_user_balance(
                game['p1'],
                -game['bet'],
                "war_bet",
                "War wager locked",
                chat_id=game.get("chat_id"),
                target_user_id=game['p2'],
                source="/war",
                require_gte=game['bet'],
                meta={"game_id": game_id},
            )
            if not p1_charge:
                active_wars.pop(game_id, None)
                await query.answer("Battle cancelled.", show_alert=True)
                await query.message.edit_text(
                    "❌ <b>Battle cancelled.</b>\nThe challenger no longer has enough coins.",
                    parse_mode=ParseMode.HTML,
                )
                return

            p2_charge = adjust_user_balance(
                game['p2'],
                -game['bet'],
                "war_bet",
                "War wager locked",
                chat_id=game.get("chat_id"),
                target_user_id=game['p1'],
                source="/war",
                require_gte=game['bet'],
                meta={"game_id": game_id},
            )
            if not p2_charge:
                adjust_user_balance(
                    game['p1'],
                    game['bet'],
                    "war_refund",
                    "War acceptance rollback",
                    chat_id=game.get("chat_id"),
                    target_user_id=game['p2'],
                    source="/war",
                    meta={"game_id": game_id},
                )
                active_wars.pop(game_id, None)
                await query.answer("Battle cancelled. Challenger refunded.", show_alert=True)
                await query.message.edit_text(
                    "❌ <b>Battle cancelled.</b>\nThe opponent no longer has enough coins. Challenger refunded.",
                    parse_mode=ParseMode.HTML,
                )
                return

        game['status'] = "playing"
        touch_war(game)
        await query.answer("⚔️ Battle begins!")
        await query.message.edit_text(
            build_war_text(game),
            parse_mode=ParseMode.HTML,
            reply_markup=build_war_buttons(game_id)
        )
        return

    if action == "war_dec":
        if user.id not in [game['p1'], game['p2']]:
            return await query.answer("Not your battle!", show_alert=True)
        del active_wars[game_id]
        return await query.message.edit_text("🏳️ <b>Battle Declined.</b>", parse_mode=ParseMode.HTML)

    # --- GAME MOVES ---
    if game['status'] != "playing":
        return await query.answer("Game not active.", show_alert=True)

    if user.id != game['turn']:
        return await query.answer("⏳ It's not your turn!", show_alert=True)
    if action not in {"war_shield", "war_atk", "war_heavy"}:
        return await query.answer("❌ Invalid battle move.", show_alert=True)

    is_p1 = (user.id == game['p1'])
    attacker_hp_key = 'p1_hp' if is_p1 else 'p2_hp'
    defender_hp_key = 'p2_hp' if is_p1 else 'p1_hp'
    attacker_shield_key = 'p1_shield' if is_p1 else 'p2_shield'
    defender_shield_key = 'p2_shield' if is_p1 else 'p1_shield'
    weapon_key = 'p1_weapon' if is_p1 else 'p2_weapon'
    attacker_name = war_player_mention(game, game['p1'] if is_p1 else game['p2'])
    defender_name = war_player_mention(game, game['p2'] if is_p1 else game['p1'])

    result_text = ""
    missed = False

    if action == "war_shield":
        game[attacker_shield_key] = True
        result_text = f"🛡️ <b>{attacker_name}</b> raises their shield! Next hit reduced by {int(SHIELD_REDUCTION*100)}%!"

    elif action in ("war_atk", "war_heavy"):
        # Determine damage
        if action == "war_atk":
            raw_dmg = random.randint(*ATTACK_NORMAL)
        else:
            if random.random() > HEAVY_ACCURACY:
                missed = True
                raw_dmg = 0
                result_text = f"💨 <b>{attacker_name}'s</b> Heavy Strike <b>MISSED!</b>"
            else:
                raw_dmg = random.randint(*ATTACK_HEAVY)

        if not missed:
            # Apply weapon buff
            weapon_buff = game[weapon_key]
            final_dmg = int(raw_dmg * (1 + weapon_buff))

            # Apply shield reduction if defender has shield
            if game[defender_shield_key]:
                final_dmg = int(final_dmg * (1 - SHIELD_REDUCTION))
                game[defender_shield_key] = False
                shield_note = f" <i>(Shield blocked {int(SHIELD_REDUCTION*100)}%!)</i>"
            else:
                shield_note = ""

            game[defender_hp_key] -= final_dmg
            move_emoji = "⚔️" if action == "war_atk" else "💥"
            result_text = f"{move_emoji} <b>{attacker_name}</b> hit <b>{defender_name}</b> for <code>{final_dmg}</code> damage!{shield_note}"

        # Reset attacker's shield after their move
        game[attacker_shield_key] = False

    # Switch turns
    game['turn'] = game['p2'] if is_p1 else game['p1']
    touch_war(game)

    # Check for winner
    p1_hp = max(0, game['p1_hp'])
    p2_hp = max(0, game['p2_hp'])
    game['p1_hp'] = p1_hp
    game['p2_hp'] = p2_hp

    if p1_hp <= 0 or p2_hp <= 0:
        # Game over
        game['status'] = 'finished'
        winner_id = game['p2'] if p1_hp <= 0 else game['p1']
        loser_id = game['p1'] if p1_hp <= 0 else game['p2']
        winner_name = war_player_mention(game, winner_id)
        loser_name = war_player_mention(game, loser_id)

        prize = game['bet'] * 2 if game['bet'] > 0 else 0
        coin_reward = random.randint(300, 600)

        users_collection.update_one({"user_id": winner_id}, {"$inc": {"balance": prize + coin_reward, "game_wins": 1, "kills": 1}})
        users_collection.update_one({"user_id": loser_id}, {"$set": {"status": "dead"}, "$inc": {"deaths": 1}})
        await add_xp(winner_id, XP_PER_GAME_WIN * 2)

        del active_wars[game_id]
        await query.answer("💥 Battle Over!")

        p1_bar = get_hp_bar(p1_hp, game['p1_max_hp'])
        p2_bar = get_hp_bar(p2_hp, game['p2_max_hp'])

        prize_text = f"\n💰 <b>Prize:</b> <code>${prize + coin_reward:,}</code>" if prize + coin_reward > 0 else f"\n💰 <b>Earned:</b> <code>${coin_reward:,}</code>"
        await query.message.edit_text(
            f"⚔️ <b>{stylize_text('BATTLE OVER')}</b> ⚔️\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🗡️ <b>{war_player_mention(game, game['p1'])}</b>\n{p1_bar}\n\n"
            f"🛡️ <b>{war_player_mention(game, game['p2'])}</b>\n{p2_bar}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📝 {result_text}\n\n"
            f"🏆 <b>{winner_name} WINS!</b>\n"
            f"💀 <b>{loser_name}</b> has been defeated!{prize_text}",
            parse_mode=ParseMode.HTML
        )
        return

    # Continue game
    await query.answer("Move locked.")
    await query.message.edit_text(
        f"{build_war_text(game)}\n\n📝 {result_text}",
        parse_mode=ParseMode.HTML,
        reply_markup=build_war_buttons(game_id)
    )
    return
