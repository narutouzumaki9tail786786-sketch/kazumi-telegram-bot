# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🌸 Kazumi — SaaS-Level Viral Telegram Bot (2026)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Kazumi private Telegram RPG bot
# Original Credits: @WTF_Phantom <DevixOP>

import os
import sys
import asyncio
import time
import traceback
from telegram.error import BadRequest, ChatMigrated, Forbidden, RetryAfter, TimedOut, NetworkError
# --- CRITICAL FIX: MUST BE AT THE VERY TOP ---
os.environ["GIT_PYTHON_REFRESH"] = "quiet"
# ---------------------------------------------

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

# Load .env file (industry standard)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # Will fall back to OS env vars

from telegram import MenuButtonWebApp, Update, WebAppInfo
from telegram.ext import (
    AIORateLimiter, ApplicationBuilder, CommandHandler, CallbackQueryHandler, 
    ChatMemberHandler, MessageHandler, PreCheckoutQueryHandler, filters
)
from telegram.request import HTTPXRequest

# --- INTERNAL IMPORTS ---
from kazumi.config import TOKEN, WEBAPP_URL
from kazumi.database import ensure_indexes

from kazumi.utils import log_to_channel, BOT_NAME
from kazumi import missions
# Import all plugins
from kazumi.plugins import (
    start, economy, game, admin, broadcast, fun, events, 
    welcome, ping, chatbot, riddle, social, ai_media, 
    waifu, collection, shop, daily,
    games, profile, achievements, search, gift, heist, bounty, tournament,
    gang, viral, pets, extra_fun, harem, tictactoe,
    war, connect4, wordbomb, arcade_games, couples, premium, loan, memory, cooldowns,
    season, settings, afk, engagement, support,
    aviator, ludo, bomb, colorbet, airdrop, boss_raid, referral, web_games
)
_NETWORK_ERROR_STATE = {"last": 0.0, "count": 0}
_FLOOD_ERROR_STATE = {"last": 0.0, "count": 0}

async def error_handler(update, context):
    error = context.error
    if isinstance(error, RetryAfter):
        _FLOOD_ERROR_STATE["count"] += 1
        now = time.monotonic()
        if now - _FLOOD_ERROR_STATE["last"] >= 15:
            print(f"[BOT FLOOD] Telegram rate-limit reached ({error.retry_after}s retry wait, x{_FLOOD_ERROR_STATE['count']} in window)", flush=True)
            _FLOOD_ERROR_STATE.update({"last": now, "count": 0})
        await asyncio.sleep(error.retry_after + 0.5)
        return
    if isinstance(error, (TimedOut, NetworkError)):
        _NETWORK_ERROR_STATE["count"] += 1
        now = time.monotonic()
        if now - _NETWORK_ERROR_STATE["last"] >= 30:
            print(
                f"[BOT NETWORK] {type(error).__name__}: {error} (x{_NETWORK_ERROR_STATE['count']} in last window)",
                flush=True,
            )
            _NETWORK_ERROR_STATE.update({"last": now, "count": 0})
        return
    if isinstance(error, BadRequest):
        message = str(error).lower()
        if any(
            marker in message
            for marker in (
                "message to be replied not found",
                "message is not modified",
                "there is no text in the message to edit",
                "query is too old",
                "wrong type of the web page content",
            )
        ):
            return
        print(f"[BOT BADREQUEST] {error}", flush=True)
        return
    if isinstance(error, ChatMigrated):
        print(f"[BOT MIGRATED] New chat id: {error.new_chat_id}", flush=True)
        return
    if isinstance(error, Forbidden):
        print(f"[BOT FORBIDDEN] {error}", flush=True)
        return

    update_id = getattr(update, "update_id", None)
    chat_id = getattr(getattr(update, "effective_chat", None), "id", None)
    user_id = getattr(getattr(update, "effective_user", None), "id", None)
    text = getattr(getattr(update, "effective_message", None), "text", None)
    print(f"[BOT ERROR] update={update_id} chat={chat_id} user={user_id} text={text!r}", flush=True)
    traceback.print_exception(type(context.error), context.error, context.error.__traceback__)

# --- STARTUP LOGIC ---
async def post_init(application):
    application.bot_data["mongo_index_task"] = asyncio.create_task(_create_indexes_in_background())
    print("✅ ᴋᴀᴢᴜᴍɪ ᴄᴏɴɴᴇᴄᴛᴇᴅ! sᴇᴛᴛɪɴɢ ᴜᴘ ᴍᴇɴᴜ ᴄᴏᴍᴍᴀɴᴅs...🌸")
    application.bot_data["gacha_cleanup_task"] = asyncio.create_task(harem.gacha_cleanup_loop(application.bot))
    application.bot_data["protection_reminder_task"] = asyncio.create_task(game.protection_reminder_loop(application.bot))
    
    # --- PUBLIC MENU (Admin commands hidden) ---
    await application.bot.set_my_commands([
        ("start", "🌸 ᴍᴀɪɴ ᴍᴇɴᴜ"), 
        ("help", "📖 ᴄᴏᴍᴍᴀɴᴅ ʟɪsᴛ"),
        ("profile", "📊 ᴘʀᴏғɪʟᴇ ᴄᴀʀᴅ"),
        ("bal", "👛 ᴡᴀʟʟᴇᴛ"), 
        ("ledger", "📒 ᴡᴀʟʟᴇᴛ ʜɪsᴛᴏʀʏ"),
        ("loan", "💳 ʟᴏᴀɴs"),
        ("shop", "🛒 sʜᴏᴘ"),
        ("kill", "🔪 ᴋɪʟʟ"), 
        ("rob", "💰 sᴛᴇᴀʟ"), 
        ("protect", "\U0001F6E1 sʜɪᴇʟᴅ / ᴘʀɪᴠᴀᴛᴇ ᴛɪᴍᴇʀ"),
        ("blackjack", "🃏 ʙʟᴀᴄᴋᴊᴀᴄᴋ"),
        ("highlow", "🃏 ʜɪɢʜ-ʟᴏᴡ"),
        ("taprace", "🔥 ᴛᴀᴘ ʀᴀᴄᴇ"),
        ("rps", "✊ ʀᴏᴄᴋ-ᴘᴀᴘᴇʀ-sᴄɪssᴏʀs"),
        ("spin", "🎰 sᴘɪɴ ᴡʜᴇᴇʟ"),
        ("crate", "📦 ʟᴏᴏᴛ ᴄʀᴀᴛᴇ"),
        ("gang", "👑 ɢᴀɴɢ"),
        ("pet", "🏠 ᴘᴇᴛ"),
        ("raid", "⚔️ ʀᴀɪᴅ"),
        ("bank", "🏦 ʙᴀɴᴋ"),
        ("heist", "⚡ ʜᴇɪsᴛ"),
        ("bounty", "🎯 ʙᴏᴜɴᴛʏ"),
        ("daily", "📅 ᴅᴀɪʟʏ"), 
        ("weekly", "📆 ᴡᴇᴇᴋʟʏ"),
        ("support", "⭐ ꜱᴜᴘᴘᴏʀᴛ ᴋᴀᴢᴜᴍɪ"),
        ("claim", "\U0001F381 ɢʀᴏᴜᴘ ʙᴏɴᴜs"),
        ("missions", "📋 ᴛᴏᴅᴀʏ ᴘʟᴀɴ"),
        ("cooldowns", "⏱ ᴄᴏᴏʟᴅᴏᴡɴs"),
        ("season", "\U0001F3C6 sᴇᴀsᴏɴ"),
        ("settings", "\U00002699\ufe0f sᴇᴛᴛɪɴɢs"),
        ("plan", "💎 ᴘʀᴇᴍɪᴜᴍ ᴘʟᴀɴs"),
        ("fortune", "🔮 ғᴏʀᴛᴜɴᴇ"),
        ("invest", "📈 sᴛᴏᴄᴋs"),
        ("p2p", "\U0001F91D ᴘ2ᴘ ᴅᴇsᴋ"),
        ("confess", "💌 ᴄᴏɴғᴇss"),
        ("title", "🏷️ ᴛɪᴛʟᴇ"),
        ("propose", "💍 ᴍᴀʀʀʏ"), 
        ("draw", "🎨 ᴀʀᴛ"),
        ("chatbot", "🧠 ᴀɪ"),
        ("memory", "🧠 ᴍᴇᴍᴏʀʏ"),
        ("ping", "📶 sᴛᴀᴛᴜs"),
        ("gacha", "🎰 ɢᴀᴄʜᴀ ᴘᴜʟʟ"),
        ("harem", "💕 ᴍʏ ʜᴀʀᴇᴍ"),
        ("afk", "🌙 ᴀᴡᴀʏ"),
        ("karma", "🌟 ᴋᴀʀᴍᴀ"),
        ("ttt", "❌ ᴛɪᴄ-ᴛᴀᴄ-ᴛᴏᴇ"),
        ("trivia", "🧠 ᴛʀɪᴠɪᴀ"),
        ("bet", "🎲 ʙᴇᴛ"),
        ("dart", "🎯 ᴅᴀʀᴛ"),
        ("basket", "🏀 ʙᴀsᴋᴇᴛ"),
        ("bowl", "🎳 ʙᴏᴡʟ"),
        ("war", "⚔️ ʙᴀᴛᴛʟᴇғɪᴇʟᴅ"),
        ("c4", "🔴🟡 ᴄᴏɴɴᴇᴄᴛ 4"),
        ("wordbomb", "💣 ᴡᴏʀᴅ ʙᴏᴍʙ"),
        ("aviator", "🚀 ᴀᴠɪᴀᴛᴏʀ ᴄʀᴀsʜ"),
        ("ludo", "🎲 ʟᴜᴅᴏ ᴅᴜᴇʟ"),
        ("wav", "🚀 ᴡᴇʙ ᴀᴠɪᴀᴛᴏʀ"),
        ("wludo", "🎲 ᴡᴇʙ ʟᴜᴅᴏ"),
        ("wmines", "💎 ᴡᴇʙ ᴍɪɴᴇs"),
        ("wspin", "🎰 ᴡᴇʙ sᴘɪɴ"),
        ("wcolor", "🔴🟢 ᴡᴇʙ ᴄᴏʟᴏʀ"),
        ("bomb", "💣 ʜᴏᴛ ʙᴏᴍb ᴛᴀɢ"),
        ("colorbet", "🔴🟢 ᴄᴏʟᴏʀ ʙᴇᴛ"),
        ("boss", "👹 ʙᴏss ʀᴀɪᴅ"),
        ("refer", "📣 ɢʀᴏᴜᴘ ʀᴇғᴇʀʀᴀʟ"),
        ("premium", "🌟 ᴘʀᴇᴍɪᴜᴍ ʙᴇɴᴇғɪᴛs")
    ])


    
    try:
        bot_info = await application.bot.get_me()
        if WEBAPP_URL:
            await application.bot.set_chat_menu_button(
                menu_button=MenuButtonWebApp(text="Kazumi", web_app=WebAppInfo(url=WEBAPP_URL))
            )
        print(f"✅ Logged in as {bot_info.username} — Kazumi v2.0 🌸")
        asyncio.create_task(log_to_channel(application.bot, "start", {
            "user": "System", 
            "chat": "Cloud Server",
            "action": f"{BOT_NAME} (@{bot_info.username}) is now Online! 🚀"
        }))
    except Exception as e:
        print(f"⚠️ Startup Log Failed: {e}")


async def _create_indexes_in_background():
    """Build Mongo indexes without delaying bot or WebApp startup."""
    try:
        await asyncio.to_thread(ensure_indexes)
        print("✅ Mongo indexes verified in background.", flush=True)
    except Exception as exc:
        print(f"[DB INDEX ERROR] {exc}", flush=True)


async def post_shutdown(application):
    """Cancel long-lived background work cleanly before the event loop closes."""
    tasks = [
        application.bot_data.get("gacha_cleanup_task"),
        application.bot_data.get("protection_reminder_task"),
        application.bot_data.get("mongo_index_task"),
    ]
    tasks = [task for task in tasks if task and not task.done()]
    for task in tasks:
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)

# --- MAIN EXECUTION ---
if __name__ == '__main__':
    if not TOKEN:
        print("CRITICAL: BOT_TOKEN is missing.")
    else:
        # This deployment is intentionally polling-only; the Mini App runs in
        # its separate WSGI process (webapp_server.py).
        if False:
            # ── WEBHOOK MODE ──────────────────────────────────────────
            # Flask handles everything (webhook updates come in via HTTP)
            # Bot runs inside Flask using ApplicationBuilder + webhook
            print(f"✅ Flask Server Started (Webhook Mode).")
            print(f"🔗 Webhook URL: {WEBHOOK_URL}{WEBHOOK_PATH}")
        else:
            # ── POLLING MODE ──────────────────────────────────────────
            print("✅ Running in Polling Mode.")

        print("DEBUG: Building Application...")
        bot_request = HTTPXRequest(
            connection_pool_size=128,
            connect_timeout=15.0,
            read_timeout=30.0,
            write_timeout=30.0,
            pool_timeout=60.0,
        )
        updates_request = HTTPXRequest(
            connection_pool_size=64,
            connect_timeout=15.0,
            read_timeout=45.0,
            write_timeout=30.0,
            pool_timeout=60.0,
        )
        # Keep headroom below Telegram's global limit so ordinary commands are
        # not starved by bursts from games, drops, and group activity. A single
        # controlled retry handles a transient flood response without turning
        # it into an application error.
        rate_limiter = AIORateLimiter(
            overall_max_rate=25,
            overall_time_period=1,
            group_max_rate=18,
            group_time_period=60,
            max_retries=1,
        )
        app_bot = (
            ApplicationBuilder()
            .token(TOKEN)
            .post_init(post_init)
            .post_shutdown(post_shutdown)
            .request(bot_request)
            .get_updates_request(updates_request)
            .rate_limiter(rate_limiter)
            .concurrent_updates(64)
            .build()
        )

        print("DEBUG: Application Built.")
        app_bot.add_error_handler(error_handler)

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 📌 REGISTER HANDLERS
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        # ── Basics ──
        app_bot.add_handler(CommandHandler("start", start.start))
        app_bot.add_handler(CommandHandler("setstart", start.setstart_command))
        app_bot.add_handler(CommandHandler("help", start.help_command))
        app_bot.add_handler(CommandHandler("ping", ping.ping))
        app_bot.add_handler(CommandHandler("settings", settings.settings_command))
        app_bot.add_handler(CallbackQueryHandler(settings.settings_callback, pattern="^settings_"))
        app_bot.add_handler(CommandHandler(["waifudrop", "waifudrops"], collection.toggle_waifu_drops_command))
        app_bot.add_handler(CommandHandler("season", season.season_command))
        app_bot.add_handler(CallbackQueryHandler(season.season_callback, pattern="^season_"))
        app_bot.add_handler(CallbackQueryHandler(ping.ping_callback, pattern="^sys_stats$"))
        app_bot.add_handler(CallbackQueryHandler(start.help_callback, pattern="^help_"))
        app_bot.add_handler(CallbackQueryHandler(start.help_callback, pattern="^return_start$"))
        
        # ── Profile & Achievements ──
        app_bot.add_handler(CommandHandler("profile", profile.profile_command))
        app_bot.add_handler(CommandHandler("achievements", achievements.achievements_command))
        app_bot.add_handler(CommandHandler("search", search.search_command))
        
        # ── Economy ──
        app_bot.add_handler(CommandHandler("register", economy.register))
        app_bot.add_handler(CommandHandler("bal", economy.balance))
        app_bot.add_handler(CommandHandler(["ledger", "history", "walletlog"], economy.ledger))
        app_bot.add_handler(CallbackQueryHandler(economy.inventory_callback, pattern="^inv_"))
        app_bot.add_handler(CommandHandler(["ranking", "top"], economy.ranking))
        app_bot.add_handler(CommandHandler("toprich", economy.ranking))
        app_bot.add_handler(CommandHandler("leaders", economy.ranking))
        app_bot.add_handler(CommandHandler("give", economy.give))
        app_bot.add_handler(CommandHandler("loan", loan.loan_command))
        app_bot.add_handler(CallbackQueryHandler(loan.loan_callback, pattern="^loan_"))
        app_bot.add_handler(CommandHandler("claim", economy.claim))
        app_bot.add_handler(CommandHandler("daily", daily.daily))
        app_bot.add_handler(CommandHandler("weekly", engagement.weekly))
        app_bot.add_handler(CommandHandler(["missions", "dailyplan"], missions.missions_command))
        app_bot.add_handler(CommandHandler(["cooldowns", "cd"], cooldowns.cooldowns_command))
        app_bot.add_handler(CommandHandler("gift", gift.gift_command))
        app_bot.add_handler(CommandHandler("support", support.support_command))
        app_bot.add_handler(CallbackQueryHandler(support.support_callback, pattern="^support_"))
        
        # ── Premium & Telegram Stars (XTR) ──
        app_bot.add_handler(CommandHandler("addpremium", premium.add_premium))
        app_bot.add_handler(CommandHandler("rmpremium", premium.remove_premium))
        app_bot.add_handler(CommandHandler("setemoji", premium.set_emoji))
        app_bot.add_handler(CommandHandler("check", premium.check_protection))
        app_bot.add_handler(CommandHandler(["premium", "plan", "vip"], premium.premium_info))
        app_bot.add_handler(CommandHandler(["stars", "buycoins"], premium.stars_command))
        app_bot.add_handler(CommandHandler("bless", premium.bless_command))
        app_bot.add_handler(CommandHandler("shield", premium.shield_command))
        app_bot.add_handler(CommandHandler("gangboost", premium.gangboost_command))
        app_bot.add_handler(CallbackQueryHandler(premium.buy_stars_callback, pattern="^(stars_|buy_invoice_)"))
        app_bot.add_handler(PreCheckoutQueryHandler(premium.precheckout_handler))
        app_bot.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, premium.successful_payment_handler))

        
        # ── Shop ──
        app_bot.add_handler(CommandHandler("shop", shop.shop_menu))
        app_bot.add_handler(CommandHandler("buy", shop.buy))
        app_bot.add_handler(CommandHandler("sell", shop.sell))
        app_bot.add_handler(CommandHandler("flex", shop.flex))
        app_bot.add_handler(CallbackQueryHandler(shop.shop_callback, pattern="^shop_"))
        
        # ── RPG / Game ──
        app_bot.add_handler(CommandHandler("kill", game.kill))
        app_bot.add_handler(CommandHandler("rob", game.rob))
        app_bot.add_handler(CommandHandler("protect", game.protect))
        app_bot.add_handler(CommandHandler("revive", game.revive))
        
        # ── NEW Games ──
        app_bot.add_handler(CommandHandler("blackjack", games.blackjack))
        app_bot.add_handler(CommandHandler("bj", games.blackjack))
        app_bot.add_handler(CallbackQueryHandler(games.bj_callback, pattern="^bj_"))
        app_bot.add_handler(CommandHandler("rps", games.rps))
        app_bot.add_handler(CallbackQueryHandler(games.rps_callback, pattern="^rps"))
        app_bot.add_handler(CommandHandler("slap", games.slap_command))
        app_bot.add_handler(CommandHandler("punch", games.punch_command))
        app_bot.add_handler(CommandHandler("hug", games.hug_command))
        app_bot.add_handler(CommandHandler("guess", games.guess_start))
        app_bot.add_handler(CommandHandler(["guesstop", "guesslb"], games.guess_leaderboard))
        app_bot.add_handler(CommandHandler("rr", games.russian_roulette))
        app_bot.add_handler(CallbackQueryHandler(games.rr_callback, pattern="^rr_"))
        app_bot.add_handler(CommandHandler("cf", games.coinflip))
        app_bot.add_handler(CommandHandler(["highlow", "hl"], games.highlow))
        app_bot.add_handler(CallbackQueryHandler(games.highlow_callback, pattern="^hl_"))
        app_bot.add_handler(CommandHandler(["taprace", "tr"], games.taprace))
        app_bot.add_handler(CallbackQueryHandler(games.taprace_callback, pattern="^taprace_"))
        app_bot.add_handler(CommandHandler("mines", arcade_games.mines_command))
        app_bot.add_handler(CommandHandler(["peekmines", "peekmine", "minesxray"], arcade_games.peekmines_command))
        app_bot.add_handler(CallbackQueryHandler(arcade_games.mines_callback, pattern="^mn_"))
        app_bot.add_handler(CommandHandler(["memorymatch", "memorygame", "mm"], arcade_games.memorymatch_command))
        app_bot.add_handler(CallbackQueryHandler(arcade_games.memory_callback, pattern="^mm_"))
        app_bot.add_handler(CommandHandler(["diceduel", "dd"], arcade_games.diceduel_command))
        app_bot.add_handler(CallbackQueryHandler(arcade_games.diceduel_callback, pattern="^dd_"))
        
        # ── Tic-Tac-Toe ──
        app_bot.add_handler(CommandHandler("ttt", tictactoe.tictactoe_command))
        app_bot.add_handler(CommandHandler(["tttboard", "tttfix"], tictactoe.tttboard_command))
        app_bot.add_handler(CommandHandler("tttstop", tictactoe.tttstop_command))
        app_bot.add_handler(CallbackQueryHandler(tictactoe.tictactoe_callback, pattern="^ttt_"))

        # ── Battlefield War ──
        app_bot.add_handler(CommandHandler("war", war.war_command))
        app_bot.add_handler(CallbackQueryHandler(war.war_callback, pattern="^war_"))

        # ── Connect 4 ──
        app_bot.add_handler(CommandHandler("c4", connect4.connect4_command))
        app_bot.add_handler(CallbackQueryHandler(connect4.connect4_callback, pattern="^c4_"))

        # ── Word Bomb ──
        app_bot.add_handler(CommandHandler("wordbomb", wordbomb.wordbomb_command))
        app_bot.add_handler(CommandHandler("wbjoin", wordbomb.wbjoin_command))
        app_bot.add_handler(CallbackQueryHandler(wordbomb.wb_callback, pattern="^wb_"))

        # ── Aviator ──
        app_bot.add_handler(CommandHandler("aviator", aviator.aviator))
        app_bot.add_handler(CallbackQueryHandler(aviator.aviator_callback, pattern="^av_out\\|"))

        # ── Ludo ──
        app_bot.add_handler(CommandHandler("ludo", ludo.ludo_command))
        app_bot.add_handler(CallbackQueryHandler(ludo.ludo_callback, pattern="^ld_roll\\|"))

        # ── Hot Bomb Tag ──
        app_bot.add_handler(CommandHandler("bomb", bomb.bomb_command))
        app_bot.add_handler(CommandHandler("pass", bomb.pass_command))

        # ── Color Bet ──
        app_bot.add_handler(CommandHandler(["colorbet", "cb"], colorbet.colorbet_command))

        # ── Boss Raid ──
        app_bot.add_handler(CommandHandler(["boss", "raidboss"], boss_raid.boss_command))
        app_bot.add_handler(CommandHandler("attack", boss_raid.attack_command))
        app_bot.add_handler(CallbackQueryHandler(boss_raid.boss_callback, pattern="^raid_atk\\|"))

        # ── Group Referral ──
        app_bot.add_handler(CommandHandler("refer", referral.refer_command))
        app_bot.add_handler(CommandHandler("addbonus", referral.addbonus_command))

        # ── Web-Direct Arcade Launchers ──
        app_bot.add_handler(CommandHandler(["wav", "avweb"], web_games.wav_command))
        app_bot.add_handler(CommandHandler(["wludo", "ludoweb"], web_games.wludo_command))
        app_bot.add_handler(CommandHandler(["wmines", "minesweb"], web_games.wmines_command))
        app_bot.add_handler(CommandHandler(["wspin", "spinweb"], web_games.wspin_command))
        app_bot.add_handler(CommandHandler(["wcolor", "colorweb"], web_games.wcolor_command))

        # ── AirDrop Listener ──
        app_bot.add_handler(CallbackQueryHandler(airdrop.airdrop_callback, pattern="^claim_ad\\|"))


        
        # ── Heist, Bounty, Tournament ──
        app_bot.add_handler(CommandHandler("heist", heist.heist_command))
        app_bot.add_handler(CallbackQueryHandler(heist.heist_callback, pattern="^heist_"))
        app_bot.add_handler(CommandHandler("bounty", bounty.bounty_command))
        app_bot.add_handler(CommandHandler("claimbounty", bounty.claim_bounty))
        app_bot.add_handler(CommandHandler("tournament", tournament.tournament_command))
        app_bot.add_handler(CallbackQueryHandler(tournament.tournament_callback, pattern="^tourney_"))
        
        # ── Web Mini App Direct Launchers ──
        app_bot.add_handler(CommandHandler("wav", web_games.wav_command))
        app_bot.add_handler(CommandHandler("wludo", web_games.wludo_command))
        app_bot.add_handler(CommandHandler("wmines", web_games.wmines_command))
        app_bot.add_handler(CommandHandler("wspin", web_games.wspin_command))
        app_bot.add_handler(CommandHandler("wcolor", web_games.wcolor_command))

        
        # ── Viral Features ──
        app_bot.add_handler(CommandHandler("gang", gang.gang_command))
        app_bot.add_handler(CommandHandler("spin", viral.spin_command))
        app_bot.add_handler(CommandHandler("crate", viral.crate_command))
        app_bot.add_handler(CommandHandler("bank", viral.bank_command))
        app_bot.add_handler(CommandHandler("fortune", viral.fortune_command))
        app_bot.add_handler(CommandHandler("confess", viral.confess_command))
        app_bot.add_handler(CommandHandler("wanted", viral.wanted_command))
        app_bot.add_handler(CommandHandler("title", viral.title_command))
        app_bot.add_handler(CommandHandler("funpoll", viral.funpoll_command))
        app_bot.add_handler(CommandHandler("invest", viral.invest_command))
        app_bot.add_handler(CommandHandler("p2p", viral.p2p_command))
        app_bot.add_handler(CommandHandler("pet", pets.pet_command))
        app_bot.add_handler(CommandHandler("raid", pets.raid_command))
        
        # ── Social / Waifu ──
        app_bot.add_handler(CommandHandler("propose", social.propose))
        app_bot.add_handler(CommandHandler("marry", social.marry_status))
        app_bot.add_handler(CommandHandler("divorce", social.divorce))
        app_bot.add_handler(CommandHandler("couple", social.couple_game))
        app_bot.add_handler(CommandHandler("couples", couples.couples_command))
        app_bot.add_handler(CommandHandler("ship", couples.ship_command))
        app_bot.add_handler(CallbackQueryHandler(social.proposal_callback, pattern="^marry_"))
        
        app_bot.add_handler(CommandHandler("wpropose", waifu.wpropose))
        app_bot.add_handler(CommandHandler("wmarry", waifu.wmarry))
        for a in waifu.SFW_ACTIONS: app_bot.add_handler(CommandHandler(a, waifu.waifu_action))
        
        # ── Harem / Gacha (NEW) ──
        app_bot.add_handler(CommandHandler("gacha", harem.gacha_command))
        app_bot.add_handler(CommandHandler("harem", harem.harem_command))
        app_bot.add_handler(CommandHandler("card", harem.card_command))
        app_bot.add_handler(CommandHandler("date", harem.date_command))
        app_bot.add_handler(CommandHandler("special", harem.special_command))

        # ── Fun / AI ──
        app_bot.add_handler(CommandHandler("dice", fun.dice))
        app_bot.add_handler(CommandHandler("slots", fun.slots))
        app_bot.add_handler(CommandHandler("trivia", engagement.trivia))
        app_bot.add_handler(CommandHandler("bet", engagement.bet))
        app_bot.add_handler(CommandHandler("dart", engagement.dart))
        app_bot.add_handler(CommandHandler("basket", engagement.basket))
        app_bot.add_handler(CommandHandler("bowl", engagement.bowl))
        app_bot.add_handler(CommandHandler("karma", engagement.karma))
        app_bot.add_handler(CommandHandler("topkarma", engagement.topkarma))
        
        # ── Extra Fun / Competitor Parity ──
        app_bot.add_handler(CommandHandler("truth", extra_fun.truth_command))
        app_bot.add_handler(CommandHandler("dare", extra_fun.dare_command))
        app_bot.add_handler(CommandHandler("crush", extra_fun.crush_command))
        app_bot.add_handler(CommandHandler("love", extra_fun.love_command))
        app_bot.add_handler(CommandHandler("look", extra_fun.look_command))
        app_bot.add_handler(CommandHandler("brain", extra_fun.brain_command))
        app_bot.add_handler(CommandHandler("stupid_meter", extra_fun.stupid_command))
        app_bot.add_handler(CommandHandler("murder", extra_fun.murder_command))
        app_bot.add_handler(CommandHandler("bite", extra_fun.bite_command))
        app_bot.add_handler(CommandHandler("kiss", extra_fun.kiss_command))
        app_bot.add_handler(CommandHandler("puzzle", extra_fun.puzzle_command))
        app_bot.add_handler(CommandHandler("owner", extra_fun.owner_command))
        app_bot.add_handler(CommandHandler("admins", extra_fun.admins_command))
        app_bot.add_handler(CommandHandler(["wordgame", "word"], extra_fun.wordgame_command))
        app_bot.add_handler(CommandHandler("riddle", riddle.riddle_command))
        app_bot.add_handler(CommandHandler("draw", ai_media.draw_command))
        app_bot.add_handler(CommandHandler("speak", ai_media.speak_command))
        app_bot.add_handler(CommandHandler("chatbot", chatbot.chatbot_menu)) 
        app_bot.add_handler(CommandHandler("ask", chatbot.ask_ai))           
        app_bot.add_handler(CallbackQueryHandler(chatbot.chatbot_callback, pattern="^ai_")) 
        app_bot.add_handler(CommandHandler("remember", memory.remember_command))
        app_bot.add_handler(CommandHandler("memory", memory.memory_command))
        app_bot.add_handler(CommandHandler("forgetme", memory.forgetme_command))
        app_bot.add_handler(CommandHandler(["afk", "brb"], afk.afk_command))
        
        # ── Admin & System ──
        app_bot.add_handler(CommandHandler("welcome", welcome.welcome_command))
        app_bot.add_handler(CommandHandler("broadcast", broadcast.broadcast))
        app_bot.add_handler(CommandHandler("pinall", broadcast.pinall))
        app_bot.add_handler(CommandHandler("unpinall", broadcast.unpinall))
        app_bot.add_handler(CommandHandler(["sudo", "admin"], admin.sudo_help))
        app_bot.add_handler(CommandHandler("adminstats", admin.admin_stats))
        app_bot.add_handler(CommandHandler("adminhealth", admin.admin_health))
        app_bot.add_handler(CommandHandler("admingames", admin.admin_games))
        app_bot.add_handler(CommandHandler("admineconomy", admin.admin_economy))
        app_bot.add_handler(CommandHandler("admingroups", admin.admin_groups))
        app_bot.add_handler(CommandHandler("adminusers", admin.admin_users))
        app_bot.add_handler(CommandHandler("adminpromo", admin.admin_promo))
        app_bot.add_handler(CallbackQueryHandler(admin.admin_panel_callback, pattern="^admin_panel_"))
        app_bot.add_handler(CommandHandler("sudolist", admin.sudolist))
        app_bot.add_handler(CommandHandler("addsudo", admin.addsudo))
        app_bot.add_handler(CommandHandler("rmsudo", admin.rmsudo))
        app_bot.add_handler(CommandHandler("addcoins", admin.addcoins))
        app_bot.add_handler(CommandHandler("rmcoins", admin.rmcoins))
        app_bot.add_handler(CommandHandler("freerevive", admin.freerevive))
        app_bot.add_handler(CommandHandler("unprotect", admin.unprotect))
        app_bot.add_handler(CommandHandler("cleandb", admin.cleandb))
        app_bot.add_handler(CommandHandler("update", admin.update_bot))
        app_bot.add_handler(CommandHandler("getid", admin.getid))
        app_bot.add_handler(CommandHandler("adminpurchases", admin.admin_purchases))
        app_bot.add_handler(CallbackQueryHandler(admin.confirm_handler, pattern="^cnf\\|"))
        
        # ── Events & Messages (ORDER IS CRITICAL) ──
        app_bot.add_handler(ChatMemberHandler(events.chat_member_update, ChatMemberHandler.MY_CHAT_MEMBER))
        app_bot.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome.new_member))
        # 0. AFK notices and welcome-back messages
        afk_activity_filter = filters.ALL & ~filters.COMMAND & ~filters.StatusUpdate.ALL
        app_bot.add_handler(MessageHandler(afk_activity_filter, afk.afk_message_handler), group=0)
        
        # 1. Collection (Waifu Guessing)
        app_bot.add_handler(MessageHandler(filters.TEXT & filters.ChatType.GROUPS & ~filters.COMMAND, collection.collect_waifu), group=1)
        # 2. Drop Check (Message Counting)
        app_bot.add_handler(MessageHandler(filters.ChatType.GROUPS, collection.check_drops), group=2)
        # 3. Riddle Answer
        app_bot.add_handler(MessageHandler(filters.TEXT & filters.ChatType.GROUPS & ~filters.COMMAND, riddle.check_riddle_answer), group=3)
        # 4. Number Guess Answer
        app_bot.add_handler(MessageHandler(filters.TEXT & filters.ChatType.GROUPS & ~filters.COMMAND, games.guess_check), group=4)
        # 5. Trivia answers
        app_bot.add_handler(MessageHandler(filters.TEXT & filters.ChatType.GROUPS & ~filters.COMMAND, engagement.trivia_answer_handler), group=5)
        # 6. Karma shortcuts
        app_bot.add_handler(MessageHandler(filters.TEXT & filters.ChatType.GROUPS & ~filters.COMMAND, engagement.karma_message_handler), group=6)
        # 7. Extra Minigames (Puzzles / Wordgame)
        app_bot.add_handler(MessageHandler(filters.TEXT & filters.ChatType.GROUPS & ~filters.COMMAND, extra_fun.check_minigames), group=7)

        # 8. Word Bomb Answer Listener
        app_bot.add_handler(MessageHandler(filters.TEXT & filters.ChatType.GROUPS & ~filters.COMMAND, wordbomb.check_word_answer), group=8)

        # 9. AI Chat
        app_bot.add_handler(MessageHandler((filters.TEXT | filters.Sticker.ALL) & ~filters.COMMAND, chatbot.ai_message_handler), group=9)
        
        # 10. Group Tracking + XP System
        app_bot.add_handler(MessageHandler(filters.ChatType.GROUPS, events.group_tracker), group=10)

        # 11. AirDrop Supply Spawner
        app_bot.add_handler(MessageHandler(filters.ChatType.GROUPS, airdrop.check_airdrop_spawns), group=11)


        # Automatically refund any in-chat games that were interrupted by previous bot restarts
        try:
            aviator.auto_refund_orphaned_games()
        except Exception as exc:
            print(f"[STARTUP RECOVERY ERROR] {exc}", flush=True)

        # Keep the polling queue restricted to update types with registered
        # handlers. Reactions, boosts, broad chat-member updates and inline
        # queries are intentionally excluded.
        allowed_updates = ["message", "callback_query", "my_chat_member", "pre_checkout_query"]

        # Kazumi production uses polling in its own PM2 process. Webhook code
        # is retired here; the Mini App is served by webapp_server.py.
        if False:
            # ── WEBHOOK MODE (Flask-Native Integration) ─────────────────────
            import requests
            full_webhook_url = f"{WEBHOOK_URL}{WEBHOOK_PATH}"
            print(f"⚡ Starting Webhook Mode: {full_webhook_url}...🌸", flush=True)
            try:
                r = requests.post(
                    f"https://api.telegram.org/bot{TOKEN}/setWebhook",
                    data={"url": full_webhook_url, "drop_pending_updates": False},
                    timeout=10
                ).json()
                print(f"✅ Telegram setWebhook response: {r.get('description', r)}", flush=True)
            except Exception as exc:
                print(f"⚠️ Webhook registration error: {exc}", flush=True)

            async def start_ptb_webhook():
                global _APP_BOT_INSTANCE, _MAIN_EVENT_LOOP
                _MAIN_EVENT_LOOP = asyncio.get_running_loop()
                await app_bot.initialize()
                await app_bot.post_init(app_bot)
                await app_bot.start()
                _APP_BOT_INSTANCE = app_bot
                print("✅ PTB Application initialized & listening for Webhook updates! 🌸", flush=True)
                while True:
                    await asyncio.sleep(3600)

            def run_ptb_async():
                asyncio.run(start_ptb_webhook())

            ptb_thread = Thread(target=run_ptb_async)
            ptb_thread.daemon = True
            ptb_thread.start()

            # Run Flask on main thread
            run_flask()
        else:
            # ── POLLING MODE ──────────────────────────────────────────────────
            import requests
            try:
                r = requests.post(
                    f"https://api.telegram.org/bot{TOKEN}/deleteWebhook",
                    data={"drop_pending_updates": False},
                    timeout=10
                ).json()
                print(f"✅ Cleared Webhook for Polling: {r.get('description', r)}", flush=True)
            except Exception as exc:
                print(f"⚠️ Clear Webhook error: {exc}", flush=True)

            print("🌸 Kazumi Bot starting Polling Mode... 🌸", flush=True)
            app_bot.run_polling(
                allowed_updates=allowed_updates,
                drop_pending_updates=False,
                bootstrap_retries=5,
            )
