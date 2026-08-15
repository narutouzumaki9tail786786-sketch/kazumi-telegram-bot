import sys, requests
sys.stdout.reconfigure(encoding='utf-8')

BOT_TOKEN = "8541210855:AAH7k-O1hQ5S5a4MpGaHrxB192OlbRm5IiI"
ALPHA_ID = 8419685066

msg = (
    "<b>Notice from Kazumi Administration</b>\n\n"
    "Your account has been reviewed as part of the <b>July 24 Economy Audit</b>.\n\n"
    "<b>Action Taken:</b>\n"
    "Your wallet has been adjusted to reflect your pre-bug balance. "
    "All coins earned through the Aviator glitch today have been removed.\n\n"
    "<b>Your Returned Balance:</b>\n"
    "Wallet: <code>$9,682</code> (70% of your balance before the bug)\n\n"
    "<i>Fair players are protected. Thank you for your understanding.</i>\n"
    "<i>— Kazumi Admin Team</i>"
)

resp = requests.post(
    f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
    data={"chat_id": ALPHA_ID, "text": msg, "parse_mode": "HTML"},
    timeout=15
)
r = resp.json()
if r.get("ok"):
    print("DM sent to ALPHA successfully!")
else:
    print(f"DM failed: {r.get('description', str(r))}")
