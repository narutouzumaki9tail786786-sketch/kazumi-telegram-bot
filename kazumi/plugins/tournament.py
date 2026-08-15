# 🌸 Kazumi — Tournament System

import random
import asyncio
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes
from telegram.constants import ParseMode, ChatType
from kazumi.utils import ensure_user_exists, get_mention, format_money, stylize_text, add_xp
from kazumi.database import users_collection
from kazumi.config import TOURNAMENT_ENTRY_FEE, TOURNAMENT_MIN_PLAYERS, XP_PER_GAME_WIN

active_tournaments = {}  # {chat_id: {players: [], phase, bracket}}

async def tournament_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat.type == ChatType.PRIVATE:
        return await update.message.reply_text("❌ Group Only!", parse_mode=ParseMode.HTML)
    
    user = ensure_user_exists(update.effective_user)
    uid = user['user_id']
    
    if chat.id in active_tournaments:
        t = active_tournaments[chat.id]
        if t['phase'] != 'joining':
            return await update.message.reply_text("⚠️ Tournament in progress!", parse_mode=ParseMode.HTML)
        if uid in t['players']:
            return await update.message.reply_text("⚠️ Already joined!", parse_mode=ParseMode.HTML)
        
        if user['balance'] < TOURNAMENT_ENTRY_FEE:
            return await update.message.reply_text(f"📉 Need {format_money(TOURNAMENT_ENTRY_FEE)}!", parse_mode=ParseMode.HTML)
        
        users_collection.update_one({"user_id": uid}, {"$inc": {"balance": -TOURNAMENT_ENTRY_FEE}})
        t['players'].append(uid)
        
        await update.message.reply_text(
            f"⚔️ {get_mention(user)} entered!\n👥 <b>{len(t['players'])} players</b>",
            parse_mode=ParseMode.HTML
        )
        return
    
    # Start new tournament
    if user['balance'] < TOURNAMENT_ENTRY_FEE:
        return await update.message.reply_text(f"📉 Entry: {format_money(TOURNAMENT_ENTRY_FEE)}", parse_mode=ParseMode.HTML)
    
    users_collection.update_one({"user_id": uid}, {"$inc": {"balance": -TOURNAMENT_ENTRY_FEE}})
    active_tournaments[chat.id] = {"players": [uid], "phase": "joining"}
    
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"⚔️ {stylize_text('Join')}", callback_data=f"tourney_join|{chat.id}")],
        [InlineKeyboardButton(f"🏁 {stylize_text('Start Now')}", callback_data=f"tourney_start|{chat.id}")]
    ])
    
    await update.message.reply_text(
        f"🏆 <b>{stylize_text('TOURNAMENT')}</b>\n\n"
        f"⚔️ {get_mention(user)} started a tournament!\n"
        f"💰 Entry: <code>{format_money(TOURNAMENT_ENTRY_FEE)}</code>\n"
        f"👥 Need {TOURNAMENT_MIN_PLAYERS}+ players\n\n"
        f"<i>Type /tournament or click to join!</i>",
        parse_mode=ParseMode.HTML, reply_markup=kb
    )

async def tournament_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data.split("|")
    action = data[0]
    chat_id = int(data[1])
    uid = query.from_user.id
    
    if chat_id not in active_tournaments:
        return await query.answer("❌ No tournament!", show_alert=True)
    
    t = active_tournaments[chat_id]
    
    if action == "tourney_join":
        if t['phase'] != 'joining':
            return await query.answer("⚠️ Already started!", show_alert=True)
        if uid in t['players']:
            return await query.answer("⚠️ Already in!", show_alert=True)
        
        user = ensure_user_exists(query.from_user)
        if user['balance'] < TOURNAMENT_ENTRY_FEE:
            return await query.answer(f"📉 Need {format_money(TOURNAMENT_ENTRY_FEE)}!", show_alert=True)
        
        users_collection.update_one({"user_id": uid}, {"$inc": {"balance": -TOURNAMENT_ENTRY_FEE}})
        t['players'].append(uid)
        await query.answer(f"✅ Joined! {len(t['players'])} players.", show_alert=True)
    
    elif action == "tourney_start":
        if len(t['players']) < TOURNAMENT_MIN_PLAYERS:
            return await query.answer(f"Need {TOURNAMENT_MIN_PLAYERS}+ players!", show_alert=True)
        
        t['phase'] = 'fighting'
        players = t['players'].copy()
        random.shuffle(players)
        prize = TOURNAMENT_ENTRY_FEE * len(players)
        
        # Simple bracket — random elimination
        round_num = 1
        results = []
        
        while len(players) > 1:
            round_results = f"⚔️ <b>Round {round_num}</b>\n"
            next_round = []
            
            for i in range(0, len(players) - 1, 2):
                p1, p2 = players[i], players[i + 1]
                winner = random.choice([p1, p2])
                loser = p2 if winner == p1 else p1
                next_round.append(winner)
                round_results += f"<a href='tg://user?id={winner}'>W</a> 🗡️ <a href='tg://user?id={loser}'>L</a>\n"
            
            if len(players) % 2 == 1:
                next_round.append(players[-1])
                round_results += f"<a href='tg://user?id={players[-1]}'>Bye</a> ✨\n"
            
            results.append(round_results)
            players = next_round
            round_num += 1
        
        champion = players[0]
        users_collection.update_one({"user_id": champion}, {"$inc": {"balance": prize, "game_wins": 1}})
        await add_xp(champion, XP_PER_GAME_WIN * 3)
        
        del active_tournaments[chat_id]
        
        msg = f"🏆 <b>{stylize_text('TOURNAMENT RESULTS')}</b>\n━━━━━━━━━━━━━━━━━━\n\n"
        msg += "\n".join(results)
        msg += f"\n🥇 <b>Champion:</b> <a href='tg://user?id={champion}'>Winner</a>\n"
        msg += f"💰 <b>Prize:</b> <code>{format_money(prize)}</code>"
        
        await query.message.edit_text(msg, parse_mode=ParseMode.HTML)
