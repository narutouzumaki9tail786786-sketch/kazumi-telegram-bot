import urllib.request
import json

def create_tele_page(title, content_list):
    req = urllib.request.urlopen('https://api.telegra.ph/createAccount?short_name=KazumiBot&author_name=Kazumi+RPG+Bot')
    acc = json.loads(req.read().decode('utf-8'))
    token = acc['result']['access_token']

    data = json.dumps({
        'access_token': token,
        'title': title,
        'author_name': 'Kazumi RPG Bot',
        'content': content_list,
        'return_content': True
    }).encode('utf-8')

    req2 = urllib.request.Request('https://api.telegra.ph/createPage', data=data, headers={'Content-Type': 'application/json'})
    res = urllib.request.urlopen(req2)
    page = json.loads(res.read().decode('utf-8'))
    return page['result']['url']

# 1. Spin Wheel
spin_url = create_tele_page('How Cyber Spin Wheel Works - Kazumi Guide', [
    {'tag': 'h2', 'children': ['🎡 Cyber Spin Wheel (/wspin)']},
    {'tag': 'p', 'children': ['Cyber Spin Wheel is Kazumi flagship 3D radial wheel game built on HTML5 Canvas. Players can wager coins and watch the high-speed neon wheel spin to hit massive prize multipliers!']},
    {'tag': 'h3', 'children': ['🎮 How to Play A to Z:']},
    {'tag': 'p', 'children': ['1. Open DM or Group chat with @KazumiRpgBot.']},
    {'tag': 'p', 'children': ['2. Type /wspin <amount> (Example: /wspin 2000).']},
    {'tag': 'p', 'children': ['3. Tap the Play Spin Wheel button to launch the Cyber Web Mini App.']},
    {'tag': 'p', 'children': ['4. Tap SPIN WHEEL on the interactive neon board.']},
    {'tag': 'p', 'children': ['5. Watch the metallic hub and LED ring spin!']},
    {'tag': 'h3', 'children': ['💰 Multiplier & Payout Structure:']},
    {'tag': 'p', 'children': ['• 🎯 2x Multiplier — Double your bet amount!']},
    {'tag': 'p', 'children': ['• 🎯 3x Multiplier — Triple your bet amount!']},
    {'tag': 'p', 'children': ['• 🎯 5x Multiplier — 5x mega payout!']},
    {'tag': 'p', 'children': ['• 🎯 10x JACKPOT — Massive 10x jackpot payout!']},
    {'tag': 'p', 'children': ['• ⚡ Real-Time Wallet Sync — All winnings are automatically credited to your Kazumi balance instantly!']}
])

# 2. Aviator Crash
aviator_url = create_tele_page('How Cyber Aviator Crash Works - Kazumi Guide', [
    {'tag': 'h2', 'children': ['🚀 Cyber Aviator Crash (/wav)']},
    {'tag': 'p', 'children': ['Cyber Aviator Crash is an intense real-time flight multiplier game where timing is everything. Watch the rocket ascend and multiplier skyrocket before it crashes!']},
    {'tag': 'h3', 'children': ['🎮 How to Play A to Z:']},
    {'tag': 'p', 'children': ['1. Type /wav <amount> (Example: /wav 1000) in chat.']},
    {'tag': 'p', 'children': ['2. Launch the Web Mini App via the button.']},
    {'tag': 'p', 'children': ['3. Tap LAUNCH ROCKET to start the flight.']},
    {'tag': 'p', 'children': ['4. As the rocket climbs, the multiplier increases from 1.00x up to 100.00x+!']},
    {'tag': 'p', 'children': ['5. Tap CASHOUT BEFORE the rocket crashes to secure your multiplied winnings!']},
    {'tag': 'h3', 'children': ['⚠️ Risk vs Reward:']},
    {'tag': 'p', 'children': ['• If you cash out at 2.50x on a 1,000 bet, you instantly win 2,500 coins!']},
    {'tag': 'p', 'children': ['• If the rocket crashes before you cash out, the bet is lost. Strategy & fast reflexes win big!']}
])

# 3. Mines 5x5
mines_url = create_tele_page('How Cyber Mines 5x5 Works - Kazumi Guide', [
    {'tag': 'h2', 'children': ['💣 Cyber Mines 5x5 (/wmines)']},
    {'tag': 'p', 'children': ['Cyber Mines 5x5 is a high-stakes grid strategy game. Uncover sparkling diamonds across a 5x5 grid while dodging hidden plasma mines!']},
    {'tag': 'h3', 'children': ['🎮 How to Play A to Z:']},
    {'tag': 'p', 'children': ['1. Type /wmines <amount> (Example: /wmines 1000).']},
    {'tag': 'p', 'children': ['2. Select how many mines to hide (1 to 24 mines). More mines = higher risk & bigger multipliers!']},
    {'tag': 'p', 'children': ['3. Tap tiles on the 5x5 grid one by one to reveal hidden diamonds.']},
    {'tag': 'p', 'children': ['4. Each diamond increases your current payout multiplier.']},
    {'tag': 'p', 'children': ['5. Tap CASHOUT at any time to claim your coins, or keep pushing for higher multipliers!']}
])

# 4. Color Bet
color_url = create_tele_page('How Cyber Color Bet Works - Kazumi Guide', [
    {'tag': 'h2', 'children': ['🔴🟢 Cyber Color Bet (/wcolor)']},
    {'tag': 'p', 'children': ['Cyber Color Bet is a fast-paced card prediction game with high multiplier payouts!']},
    {'tag': 'h3', 'children': ['🎮 How to Play A to Z:']},
    {'tag': 'p', 'children': ['1. Type /wcolor <amount> (Example: /wcolor 2000).']},
    {'tag': 'p', 'children': ['2. Select Red, Green, or Blue card prediction.']},
    {'tag': 'p', 'children': ['3. The cyber dealer draws the winning card.']},
    {'tag': 'p', 'children': ['4. Win up to 4.5x instant payouts automatically deposited into your wallet!']}
])

# 5. Ludo & Mega Updates
ludo_url = create_tele_page('How Cyber Ludo & Mega Updates Work - Kazumi Guide', [
    {'tag': 'h2', 'children': ['🎲 Cyber Ludo Duel (/wludo) & Full Mega Update Details']},
    {'tag': 'p', 'children': ['Challenge group members to live 3D Ludo board duels! Roll dice, knock out opponent tokens, and win the full prize pot!']},
    {'tag': 'hr'},
    {'tag': 'h3', 'children': ['🌟 COMPLETE A TO Z SYSTEM UPDATES IN KAZUMI 2.0:']},
    {'tag': 'p', 'children': ['🎨 1. Telegram Bot API 9.4 Native Colored Buttons — Buttons across all menus now feature official Green (success), Blue (primary), and Red (danger) color styling.']},
    {'tag': 'p', 'children': ['⚡ 2. 32-Worker Concurrency Boost — Server processing upgraded to 32 parallel threads & 128 HTTP sockets for instant response time and zero lag.']},
    {'tag': 'p', 'children': ['🛡️ 3. Anti-Spam Boss Raids (/boss) — 4-second attack cooldown & in-place card editing added to keep group chats clean and lag-free.']},
    {'tag': 'p', 'children': ['💳 4. Real-Time MongoDB Wallet Sync — All Web Arcade game bets, wins, and cashouts instantly sync with your Kazumi wallet (/bal).']},
    {'tag': 'p', 'children': ['✨ 5. Clean Custom Emoji Deduplication — Every inline button now displays exactly 1 single vibrant custom emoji icon without text duplication.']}
])

print('SPIN_URL:', spin_url)
print('AVIATOR_URL:', aviator_url)
print('MINES_URL:', mines_url)
print('COLOR_URL:', color_url)
print('LUDO_URL:', ludo_url)
