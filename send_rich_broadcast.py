import asyncio, sys
from telegram import Bot
from telegram.constants import ParseMode
from kazumi.config import TOKEN
from kazumi.database import users_collection, groups_collection

BROADCAST_HTML = """🚀 <b>MEGA UPDATE — KAZUMI RPG BOT</b> 🌸✨

🎮 <b>5 NEW CYBER WEB ARCADE GAMES ARE LIVE!</b>
🎡 <a href="https://t.me/KazumiRpgBot?start=wspin">Cyber Spin Wheel</a> — Spin & win up to 10× rewards. 🔗
🚀 <a href="https://t.me/KazumiRpgBot?start=wav">Cyber Aviator Crash</a> — Cash out before the rocket crashes. 📈
🔮 <a href="https://t.me/KazumiRpgBot?start=wmines">Cyber Mines 5×5</a> — Find diamonds, avoid bombs & multiply rewards. 🔗
🔴🟢 <a href="https://t.me/KazumiRpgBot?start=wcolor">Cyber Color Bet</a> — Predict the color & win big. 🔗
🎲 <a href="https://t.me/KazumiRpgBot?start=wludo">Cyber Ludo Duel</a> — Real-time 3D Ludo battles. 🔗

⚡ <b>Arcade Commands:</b>
<code>/wspin 2000</code> ➔ 🎡 Web Spin Wheel
<code>/wav 1000</code> ➔ 🚀 Web Aviator Crash
<code>/wmines 1000</code> ➔ 🔮 Web 5x5 Mines
<code>/wcolor 500</code> ➔ 🔴🟢 Web Color Bet
<code>/wludo 1000</code> ➔ 🎲 Web Ludo Board
━━━━━━━━━━━━━━━━━━━━
🛠️ <b>System Updates & Performance Fixes:</b>
⚡ <b>2048-Connection Network Upgrade</b> (Ultra Fast Response & Zero Delay)
🛡️ <b>Unlimited Gang Bank Withdrawals</b> (Daily Cap Removed!)
📱 <b>Instant Mini App Sync & Auto-Balance Loader</b>
⚔️ <b>Enhanced Anti-Spam & Boss Protection</b>
✨ <b>Custom Emojis & Rich Display Support</b>

💬 <i>Note: Web Arcade Games sync seamlessly in both PM and Group Chats!</i>

🌸 <b>Play Now:</b> @KazumiRpgBot"""

async def main():
    bot = Bot(TOKEN)
    users = list(users_collection.find({"bot_blocked": {"$ne": True}}, {"user_id": 1}))
    groups = list(groups_collection.find({"bot_blocked": {"$ne": True}}, {"chat_id": 1}))

    print(f"Starting broadcast to {len(users)} users and {len(groups)} groups...")
    
    u_sent = 0
    for u in users:
        cid = u.get("user_id")
        if not cid: continue
        try:
            await bot.send_message(chat_id=cid, text=BROADCAST_HTML, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
            u_sent += 1
            await asyncio.sleep(0.05)
        except Exception as e:
            print(f"User {cid} failed: {e}")

    g_sent = 0
    for g in groups:
        cid = g.get("chat_id")
        if not cid: continue
        try:
            await bot.send_message(chat_id=cid, text=BROADCAST_HTML, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
            g_sent += 1
            await asyncio.sleep(0.05)
        except Exception as e:
            print(f"Group {cid} failed: {e}")

    print(f"DONE! Sent to {u_sent} users and {g_sent} groups.")

if __name__ == "__main__":
    asyncio.run(main())
