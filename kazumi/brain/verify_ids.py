from kazumi.emojis import EMOJI_IDS
import re

print(f"Total keys: {len(EMOJI_IDS)}")
test_emoji = "👋"
normalized_test = test_emoji.replace("\uFE0F", "")

normalized_ids = {k.replace("\uFE0F", ""): v for k, v in EMOJI_IDS.items()}

print(f"Test emoji: {repr(test_emoji)}")
print(f"Found in normalized: {normalized_test in normalized_ids}")

if normalized_test in normalized_ids:
    print(f"ID: {normalized_ids[normalized_test]}")

test_text = "👋 Konichiwa"
sorted_emojis = sorted(normalized_ids.keys(), key=len, reverse=True)
pattern = "|".join(f"{re.escape(e)}\uFE0F?" for e in sorted_emojis)
match = re.search(pattern, test_text)
print(f"Regex Match: {match}")
if match:
    print(f"Match Group 0: {repr(match.group(0))}")
