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

master_url = create_tele_page('Kazumi Cyber Web Arcade - A to Z Master Guide Index', [
    {'tag': 'h2', 'children': ['Kazumi Cyber Web Arcade - A to Z Master Guide Index']},
    {'tag': 'p', 'children': ['Welcome to the official Master Guide Index for Kazumi Cyber Web Arcade mini games and system features! Select any game below to read its complete rules and strategy guide.']},
    {'tag': 'hr'},
    {'tag': 'h3', 'children': ['1. Cyber Spin Wheel (/wspin)']},
    {'tag': 'p', 'children': ['3D HTML5 Canvas wheel with up to 10x Jackpot multipliers!']},
    {'tag': 'p', 'children': [{'tag': 'a', 'attrs': {'href': 'https://telegra.ph/How-Cyber-Spin-Wheel-Works---Kazumi-Guide-07-24-2'}, 'children': ['Click Here to Read Spin Wheel Guide']}]},
    {'tag': 'h3', 'children': ['2. Cyber Aviator Crash (/wav)']},
    {'tag': 'p', 'children': ['Real-time flight multiplier with live cashout mechanics!']},
    {'tag': 'p', 'children': [{'tag': 'a', 'attrs': {'href': 'https://telegra.ph/How-Cyber-Aviator-Crash-Works---Kazumi-Guide-07-24-2'}, 'children': ['Click Here to Read Aviator Crash Guide']}]},
    {'tag': 'h3', 'children': ['3. Cyber Mines 5x5 (/wmines)']},
    {'tag': 'p', 'children': ['High-stakes 5x5 grid strategy with custom mine selection!']},
    {'tag': 'p', 'children': [{'tag': 'a', 'attrs': {'href': 'https://telegra.ph/How-Cyber-Mines-5x5-Works---Kazumi-Guide-07-24-2'}, 'children': ['Click Here to Read Mines 5x5 Guide']}]},
    {'tag': 'h3', 'children': ['4. Cyber Color Bet (/wcolor)']},
    {'tag': 'p', 'children': ['Card color predictions with up to 4.5x instant payouts!']},
    {'tag': 'p', 'children': [{'tag': 'a', 'attrs': {'href': 'https://telegra.ph/How-Cyber-Color-Bet-Works---Kazumi-Guide-07-24-2'}, 'children': ['Click Here to Read Color Bet Guide']}]},
    {'tag': 'h3', 'children': ['5. Cyber Ludo Duel (/wludo) & System Updates']},
    {'tag': 'p', 'children': ['3D Ludo board duels, Telegram Bot API 9.4 native colored buttons, and anti-spam boss raids!']},
    {'tag': 'p', 'children': [{'tag': 'a', 'attrs': {'href': 'https://telegra.ph/How-Cyber-Ludo--Mega-Updates-Work---Kazumi-Guide-07-24-2'}, 'children': ['Click Here to Read Ludo & System Updates Guide']}]}
])

print('MASTER_INDEX_URL:', master_url)
