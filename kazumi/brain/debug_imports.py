import os
import sys

# Add current dir to path
sys.path.append(os.getcwd())

plugins = [
    "kazumi.plugins.start", "kazumi.plugins.economy", "kazumi.plugins.game", 
    "kazumi.plugins.admin", "kazumi.plugins.broadcast", "kazumi.plugins.fun", 
    "kazumi.plugins.events", "kazumi.plugins.welcome", "kazumi.plugins.ping", 
    "kazumi.plugins.chatbot", "kazumi.plugins.riddle", "kazumi.plugins.social", 
    "kazumi.plugins.ai_media", "kazumi.plugins.waifu", "kazumi.plugins.collection", 
    "kazumi.plugins.shop", "kazumi.plugins.daily", "kazumi.plugins.games", 
    "kazumi.plugins.profile", "kazumi.plugins.achievements", "kazumi.plugins.search", 
    "kazumi.plugins.gift", "kazumi.plugins.heist", "kazumi.plugins.bounty", 
    "kazumi.plugins.tournament", "kazumi.plugins.gang", "kazumi.plugins.viral", 
    "kazumi.plugins.pets", "kazumi.plugins.extra_fun", "kazumi.plugins.harem", 
    "kazumi.plugins.tictactoe", "kazumi.plugins.war", "kazumi.plugins.connect4", 
    "kazumi.plugins.wordbomb", "kazumi.plugins.couples", "kazumi.plugins.premium"
]

for p in plugins:
    try:
        __import__(p)
        print(f"OK: {p}")
    except Exception as e:
        print(f"FAIL: {p}: {e}")
        import traceback
        traceback.print_exc()
        # sys.exit(1)
