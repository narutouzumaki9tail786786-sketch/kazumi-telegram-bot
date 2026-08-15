import os
import requests

BOT_TOKEN = "8541210855:AAH7k-O1hQ5S5a4MpGaHrxB192OlbRm5IiI"
CHANNEL = "@AbdulBotzOfficial"
PDF_PATH = "Kazumi_Official_Economy_Audit_Report.pdf"

# ─── Channel Post Caption ────────────────────────────────────────────────────
caption = (
    "🌸 <b>KAZUMI RPG BOT — OFFICIAL ECONOMY AUDIT REPORT</b>\n"
    "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    "📋 <b>Transparency Statement &amp; Game Economy Rebalance Audit</b>\n"
    "📅 <i>Date: July 24, 2026</i>\n\n"
    "🔍 <b>Key Actions Enforced:</b>\n"
    "✦ <b>Aviator Glitch Neutralized</b> — Max wager capped at <b>$10,000,000</b> per round\n"
    "✦ <b>Glitch Balances Rebalanced</b> — Extreme glitched wallets capped at <b>$50,000,000</b> baseline\n"
    "✦ <b>Gift Chain Audit</b> — All glitch currency gifted to others has been fully deducted\n"
    "✦ <b>Fair Players Protected</b> — All legitimate accounts remain <b>100% intact &amp; verified</b>\n\n"
    "🔒 <i>User IDs and handles are partially masked (blurred) to protect privacy.</i>\n\n"
    "━━━━━━━━━━━━━━━━━━━━━━━\n"
    "📄 Full details in the attached official audit PDF.\n"
    "🤖 <i>Issued by: Kazumi Administration &amp; Security Operations | @KazumiRpgBot</i>"
)

print(f"📤 Sending audit PDF to {CHANNEL}...")

with open(PDF_PATH, "rb") as pdf_file:
    resp = requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument",
        data={
            "chat_id": CHANNEL,
            "caption": caption,
            "parse_mode": "HTML",
        },
        files={"document": (os.path.basename(PDF_PATH), pdf_file, "application/pdf")},
        timeout=30,
    )

result = resp.json()
if result.get("ok"):
    msg_id = result["result"]["message_id"]
    print(f"✅ PDF posted successfully! Message ID: {msg_id}")
    print(f"🔗 https://t.me/AbdulBotzOfficial/{msg_id}")
else:
    print(f"❌ Failed to post PDF!")
    print(f"Error: {result.get('description', 'Unknown error')}")
    print(f"Full response: {result}")
