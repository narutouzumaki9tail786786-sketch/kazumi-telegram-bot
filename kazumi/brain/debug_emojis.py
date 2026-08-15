import re
from kazumi.emojis import EMOJI_IDS

def apply_custom_emojis(text, remove_fallback=True):
    if not text: return text
    sorted_emojis = sorted(EMOJI_IDS.keys(), key=len, reverse=True)
    pattern = "|".join(f"{re.escape(e)}\uFE0F?" for e in sorted_emojis)
    
    print(f"Pattern length: {len(pattern)}")
    
    def replacer(match):
        raw_emoji = match.group(0)
        emoji = raw_emoji.replace("\uFE0F", "")
        emoji_id = EMOJI_IDS.get(emoji)
        print(f"Matched: {repr(raw_emoji)} -> ID: {emoji_id}")
        if emoji_id:
            fallback = "" if remove_fallback else emoji
            return f"<tg-emoji emoji-id='{emoji_id}'>{fallback}</tg-emoji>"
        return raw_emoji

    return re.sub(pattern, replacer, str(text))

test_text = "👋 Konichiwa! 🌸 Kazumi 💞"
result = apply_custom_emojis(test_text)
print(f"Result: {result}")

test_button = "➕ ADD ME"
result_btn = apply_custom_emojis(test_button)
print(f"Button Result: {result_btn}")
