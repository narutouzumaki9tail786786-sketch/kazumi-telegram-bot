import kazumi.emojis as emojis

def to_hex(s):
    return " ".join(f"U+{ord(c):04X}" for c in s)

print("Emojis from emojis.py keys:")
for e in list(emojis.EMOJI_IDS.keys())[:5]:
    print(f"{e}: {to_hex(e)}")

# Read start.py
with open("kazumi/plugins/start.py", "r", encoding="utf-8") as f:
    content = f.read()

# Find the caption part
if "👋" in content:
    print("\n👋 found in start.py")
    print(f"👋 Hex in start.py: {to_hex('👋')}")
else:
    print("\n👋 NOT found in start.py")

# Check ➕
if "➕" in content:
    print("\n➕ found in start.py")
    print(f"➕ Hex in start.py: {to_hex('➕')}")
