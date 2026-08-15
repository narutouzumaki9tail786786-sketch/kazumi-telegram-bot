# Copyright (c) 2025 Telegram:- @WTF_Phantom <DevixOP>
# Location: Supaul, Bihar 
#
# All rights reserved.
#
# This code is the intellectual property of @WTF_Phantom.
# You are not allowed to copy, modify, redistribute, or use this
# code for commercial or personal projects without explicit permission.
#
# Allowed:
# - Forking for personal learning
# - Submitting improvements via pull requests
#
# Not Allowed:
# - Claiming this code as your own
# - Re-uploading without credit or permission
# - Selling or using commercially
#
# Contact for permissions:
# Email: king25258069@gmail.com

import asyncio
import os
import random
import time
from io import BytesIO

import httpx
from datetime import datetime, timedelta
from telegram import Update
from telegram.error import BadRequest, TelegramError
from telegram.ext import ApplicationHandlerStop, ContextTypes
from telegram.constants import ParseMode
from kazumi.database import groups_collection, users_collection, waifu_drops_collection, gacha_messages_collection
from kazumi.ledger import adjust_user_balance
from kazumi.utils import ensure_user_exists, format_money, get_mention

# In-Memory Drop Storage
active_drops = {}
wrong_drop_answer_cooldowns = {}
DROP_MESSAGE_COUNT = int(os.getenv("WAIFU_DROP_MESSAGE_COUNT", 300))

DROP_FALLBACK_PHOTO = "https://i.waifu.pics/7p-Z9M-.png"
DROP_REWARD = 500
DROP_TTL_SECONDS = 600
DROP_DELETE_NOTICE = "<i>NSFW safety: this group image auto-deletes in 10 minutes.</i>"
DANBOORU_RANDOM_URL = "https://danbooru.donmai.us/posts/random.json"


def _cleanup_error_is_final(error: Exception) -> bool:
    text = str(error).lower()
    final_markers = (
        "message to delete not found",
        "message can't be deleted",
        "chat not found",
        "bot was kicked",
        "not enough rights",
        "forbidden",
    )
    return any(marker in text for marker in final_markers)
DANBOORU_TAG_PROFILES = ("rating:s 1girl", "rating:g 1girl")
DANBOORU_TRIES = 80
DROP_MIN_SCORE = 12
DROP_MIN_SIDE = 1000
DROP_REJECT_TAGS = {
    "1boy", "2boys", "multiple_boys", "male_focus", "solo_male", "old_man",
    "manly", "bara", "beard", "mustache", "facial_hair", "muscular_male",
    "shota", "trap", "crossdressing", "genderswap_(mtf)", "helmet", "mecha",
    "2girls", "3girls", "multiple_girls", "comic", "manga", "4koma", "cover",
    "magazine_cover", "book_cover", "scan", "text_focus", "speech_bubble",
    "english_text", "japanese_text", "watermark", "monochrome", "greyscale",
    "chibi", "child", "loli", "kindergarten_uniform", "elementary_school_uniform",
    "aged_down", "baby", "toddler", "flat_chest",
    "lowres", "cropped", "bad_anatomy", "bad_hands",
    "nude", "naked", "nipples", "areolae", "pussy", "penis", "sex", "cum",
    "spread_pussy", "explicit", "uncensored",
}
DROP_PREFERRED_TAGS = {
    "looking_at_viewer", "smile", "blush", "long_hair", "beautiful_detailed_eyes",
    "dress", "school_uniform", "sailor_collar", "thighhighs", "cleavage",
    "large_breasts", "medium_breasts", "portrait", "upper_body", "cowboy_shot",
    "solo_focus", "outdoors", "night", "flower", "hair_ornament", "bare_shoulders",
    "swimsuit", "bikini", "navel", "midriff", "short_shorts", "miniskirt",
    "off_shoulder", "collarbone", "sweater", "pantyhose", "zettai_ryouiki",
}
DROP_HOT_TAGS = {
    "cleavage", "large_breasts", "medium_breasts", "swimsuit", "bikini",
    "bare_shoulders", "navel", "midriff", "thighhighs", "short_shorts",
    "miniskirt", "off_shoulder", "collarbone", "pantyhose", "zettai_ryouiki",
}


def _drop_record(chat_id: int, message_id: int, drop: dict, ttl_seconds: int = DROP_TTL_SECONDS):
    display_name = drop.get("display_name") or drop.get("name")
    aliases = set(drop.get("aliases") or [])
    aliases.update(_answer_variants(display_name))
    aliases.update(_answer_variants(drop.get("name")))
    return {
        "chat_id": chat_id,
        "message_id": message_id,
        "name": normalize_guess(display_name),
        "aliases": sorted(alias for alias in aliases if alias),
        "display_name": display_name,
        "image": drop.get("image_url") or drop.get("image"),
        "source": drop.get("source"),
        "telegram_file_id": drop.get("telegram_file_id"),
        "created_at": datetime.utcnow(),
        "expires_at": datetime.utcnow() + timedelta(seconds=ttl_seconds),
    }


def _remember_drop(chat_id: int, message_id: int, drop: dict):
    record = _drop_record(chat_id, message_id, drop)
    active_drops[chat_id] = record
    waifu_drops_collection.update_one(
        {"chat_id": chat_id, "message_id": message_id},
        {"$set": record},
        upsert=True,
    )
    gacha_messages_collection.update_one(
        {"chat_id": chat_id, "message_id": message_id},
        {
            "$set": {
                "chat_id": chat_id,
                "message_id": message_id,
                "user_id": 0,
                "is_nsfw": False,
                "kind": "waifu_drop",
                "created_at": record["created_at"],
                "expires_at": record["expires_at"],
            }
        },
        upsert=True,
    )
    return record


def _load_drop(chat_id: int, message_id: int):
    drop = active_drops.get(chat_id)
    if isinstance(drop, dict) and drop.get("message_id") == message_id:
        return drop

    drop = waifu_drops_collection.find_one({"chat_id": chat_id, "message_id": message_id})
    if not drop:
        return None
    if drop.get("expires_at") and drop["expires_at"] < datetime.utcnow():
        waifu_drops_collection.delete_one({"_id": drop["_id"]})
        return None
    active_drops[chat_id] = drop
    return drop


def _load_latest_drop(chat_id: int):
    drop = waifu_drops_collection.find_one(
        {"chat_id": chat_id, "expires_at": {"$gt": datetime.utcnow()}},
        sort=[("created_at", -1)],
    )
    if drop:
        active_drops[chat_id] = drop
    return drop


def _find_replied_drop(chat_id: int, reply_message):
    if not reply_message:
        return None, None

    message_id = reply_message.message_id
    drop = _load_drop(chat_id, message_id)
    if drop:
        return drop, int(drop.get("message_id") or message_id)

    if _is_waifu_drop_message(reply_message):
        drop = _load_latest_drop(chat_id)
        if drop:
            return drop, int(drop.get("message_id") or message_id)
    return None, message_id


def _clear_drop(chat_id: int, message_id: int):
    current = active_drops.get(chat_id)
    if isinstance(current, dict) and current.get("message_id") == message_id:
        active_drops.pop(chat_id, None)
    waifu_drops_collection.delete_one({"chat_id": chat_id, "message_id": message_id})
    gacha_messages_collection.delete_one({"chat_id": chat_id, "message_id": message_id})


async def _image_file_from_url(client: httpx.AsyncClient, url: str):
    if not url or "catbox" in str(url):
        return None
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
            "Referer": "https://danbooru.donmai.us/",
        }
        response = await client.get(url, headers=headers, follow_redirects=True, timeout=8.0)
        response.raise_for_status()
        content_type = response.headers.get("content-type", "").lower()
        content = response.content
        if not content or len(content) < 500:
            return None
        if not content_type.startswith("image/") and not content.startswith(b"\xff\xd8") and not content.startswith(b"\x89PNG") and not content.startswith(b"RIFF") and not content.startswith(b"GIF"):
            return None
        image = BytesIO(content)
        image.name = "kazumi_drop.jpg"
        return image
    except Exception as exc:
        print(f"[IMAGE FETCH ERROR] url={url}: {exc}", flush=True)
        return None


def normalize_guess(value):
    value = str(value or "").lower()
    value = value.replace("_", " ")
    value = (
        value.replace("ō", "ou")
        .replace("ū", "uu")
        .replace("ā", "aa")
        .replace("ī", "ii")
        .replace("ē", "ee")
    )
    for ch in "()[]{}.,!?:;\"'`/\\|":
        value = value.replace(ch, " ")
    return " ".join(value.strip().split())


def _romanized_name_variants(value):
    base = normalize_guess(value)
    if not base:
        return set()

    variants = {base}
    replacements = (
        ("ou", "o"),
        ("uu", "u"),
        ("oo", "o"),
        ("aa", "a"),
        ("ii", "i"),
        ("ee", "e"),
    )
    changed = True
    while changed and len(variants) < 64:
        changed = False
        for item in list(variants):
            for src, dst in replacements:
                if src in item:
                    new_item = item.replace(src, dst)
                    if new_item not in variants:
                        variants.add(new_item)
                        changed = True
    return variants


def _answer_variants(value):
    normalized = normalize_guess(value)
    if not normalized:
        return set()

    variants = set(_romanized_name_variants(normalized))
    words = normalized.split()
    if words:
        variants.add("".join(words))
        for word in words:
            if len(word) >= 4:
                variants.update(_romanized_name_variants(word))
    if len(words) >= 2:
        variants.update(_romanized_name_variants(" ".join(reversed(words))))
        for idx in range(1, len(words)):
            variants.update(_romanized_name_variants(" ".join(words[idx:] + words[:idx])))

    stripped = []
    skip = False
    for word in words:
        if word.startswith("("):
            skip = True
        if not skip:
            stripped.append(word)
        if word.endswith(")"):
            skip = False
    if stripped and stripped != words:
        base = " ".join(stripped)
        variants.update(_romanized_name_variants(base))
        base_words = base.split()
        if len(base_words) >= 2:
            variants.update(_romanized_name_variants(" ".join(reversed(base_words))))
            for idx in range(1, len(base_words)):
                variants.update(_romanized_name_variants(" ".join(base_words[idx:] + base_words[:idx])))
        if base_words:
            variants.add("".join(base_words))
            for word in base_words:
                if len(word) >= 4:
                    variants.update(_romanized_name_variants(word))
    return variants


def _wrong_answer_allowed(chat_id: int, message_id: int, user_id: int, cooldown_seconds: int = 7):
    key = (chat_id, message_id, user_id)
    now = datetime.utcnow()
    last = wrong_drop_answer_cooldowns.get(key)
    if last and (now - last).total_seconds() < cooldown_seconds:
        return False
    wrong_drop_answer_cooldowns[key] = now
    return True


def _character_names(raw_tag):
    raw_tags = str(raw_tag or "").split()
    if len(raw_tags) != 1:
        return None, []
    raw = raw_tags[0].strip()
    if not raw:
        return None, []

    base = raw.split("_(")[0]

    def pretty(value):
        value = str(value or "").replace("_", " ").strip()
        return " ".join(part.capitalize() for part in value.split())

    def reversed_words(value):
        words = pretty(value).split()
        if len(words) < 2:
            return None
        return " ".join(reversed(words))

    display = pretty(base)
    base_display = pretty(base)
    full_display = pretty(raw)
    aliases = {
        raw,
        raw.replace("_", " "),
        raw.replace("_", " ").replace("(", "").replace(")", ""),
        full_display,
        base,
        base.replace("_", " "),
        base_display,
        reversed_words(raw),
        reversed_words(base),
    }
    expanded_aliases = set()
    for alias in aliases:
        expanded_aliases.update(_answer_variants(alias))
    return display, [alias for alias in expanded_aliases if alias]


def _tag_set(*values):
    tags = set()
    for value in values:
        tags.update(str(value or "").split())
    return tags


def _good_drop_post(item):
    tags = _tag_set(
        item.get("tag_string_general"),
        item.get("tag_string_meta"),
        item.get("tag_string_character"),
    )
    if tags & DROP_REJECT_TAGS:
        return False
    if "solo" not in tags:
        return False
    if int(item.get("score") or 0) < DROP_MIN_SCORE:
        return False
    width = int(item.get("image_width") or 0)
    height = int(item.get("image_height") or 0)
    if width < DROP_MIN_SIDE or height < DROP_MIN_SIDE:
        return False
    if not (tags & DROP_PREFERRED_TAGS) and int(item.get("score") or 0) < 70:
        return False
    if item.get("rating") == "s" and not (tags & DROP_HOT_TAGS) and int(item.get("score") or 0) < 100:
        return False
    return bool(item.get("large_file_url") or item.get("file_url"))


ICONIC_ANIME_WAIFUS = [
    {
        "name": "Zero Two",
        "aliases": ["zero two", "002", "zerotwo", "darling"],
        "url": "https://i.waifu.pics/7p-Z9M-.png",
    },
    {
        "name": "Rem",
        "aliases": ["rem", "rem-chan", "rem rin"],
        "url": "https://i.waifu.pics/U~eR33M.png",
    },
    {
        "name": "Yor Forger",
        "aliases": ["yor forger", "yor", "thorn princess", "yor briar"],
        "url": "https://i.waifu.pics/5j1E4vM.jpg",
    },
    {
        "name": "Makima",
        "aliases": ["makima", "control devil"],
        "url": "https://i.waifu.pics/XmJp~8g.jpg",
    },
    {
        "name": "Marin Kitagawa",
        "aliases": ["marin kitagawa", "marin", "kitagawa"],
        "url": "https://i.waifu.pics/b-J7v5e.png",
    },
    {
        "name": "Megumin",
        "aliases": ["megumin", "explosion girl"],
        "url": "https://i.waifu.pics/50a-4lM.png",
    },
    {
        "name": "Kurumi Tokisaki",
        "aliases": ["kurumi tokisaki", "kurumi", "tokisaki kurumi"],
        "url": "https://i.waifu.pics/e1Vd3h9.jpg",
    },
    {
        "name": "Nezuko Kamado",
        "aliases": ["nezuko kamado", "nezuko", "kamado nezuko"],
        "url": "https://i.waifu.pics/N9u-1k2.jpg",
    },
    {
        "name": "Kaguya Shinomiya",
        "aliases": ["kaguya shinomiya", "kaguya", "shinomiya kaguya"],
        "url": "https://i.waifu.pics/3~W1~kL.png",
    },
    {
        "name": "Mikasa Ackerman",
        "aliases": ["mikasa ackerman", "mikasa", "ackerman mikasa"],
        "url": "https://i.waifu.pics/c6d2-kM.jpg",
    },
    {
        "name": "Boa Hancock",
        "aliases": ["boa hancock", "hancock", "pirate empress"],
        "url": "https://i.waifu.pics/x~N9x~M.jpg",
    },
    {
        "name": "Mai Sakurajima",
        "aliases": ["mai sakurajima", "mai", "bunny girl mai"],
        "url": "https://i.waifu.pics/w-Y6v7M.png",
    },
    {
        "name": "Rias Gremory",
        "aliases": ["rias gremory", "rias", "gremory rias"],
        "url": "https://i.waifu.pics/k5n~7~M.jpg",
    },
    {
        "name": "Emilia",
        "aliases": ["emilia", "lia", "emilia-tan"],
        "url": "https://i.waifu.pics/m-0j8~M.png",
    },
    {
        "name": "Chika Fujiwara",
        "aliases": ["chika fujiwara", "chika", "fujiwara chika"],
        "url": "https://i.waifu.pics/b~Z4w-M.png",
    },
    {
        "name": "Power",
        "aliases": ["power", "blood devil"],
        "url": "https://i.waifu.pics/y9z-8~M.jpg",
    },
    {
        "name": "Shinobu Kocho",
        "aliases": ["shinobu kocho", "shinobu", "kocho shinobu", "insect hashira"],
        "url": "https://i.waifu.pics/h-X7y-M.jpg",
    },
    {
        "name": "Mitsuri Kanroji",
        "aliases": ["mitsuri kanroji", "mitsuri", "love hashira"],
        "url": "https://i.waifu.pics/e6-Z9~M.jpg",
    },
    {
        "name": "Violet Evergarden",
        "aliases": ["violet evergarden", "violet"],
        "url": "https://i.waifu.pics/d~m9v~M.jpg",
    },
    {
        "name": "C.C.",
        "aliases": ["c.c.", "cc", "c2"],
        "url": "https://i.waifu.pics/4~q-8~M.png",
    },
]


async def fetch_drop_character():
    """Return a high-quality waifu-style image with a real searchable character tag."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    }

    # 1. Iconic Famous Anime Waifus Pool (50% random chance for famous guessable waifus!)
    if random.random() < 0.5 and ICONIC_ANIME_WAIFUS:
        try:
            choice = random.choice(ICONIC_ANIME_WAIFUS)
            async with httpx.AsyncClient(timeout=6, follow_redirects=True, headers=headers) as client:
                image_file = await _image_file_from_url(client, choice["url"])
                if image_file:
                    name = choice["name"]
                    aliases = [normalize_guess(a) for a in choice["aliases"]] + [normalize_guess(name)]
                    return {
                        "name": name,
                        "aliases": list(set(aliases)),
                        "photo": image_file,
                        "image_url": choice["url"],
                        "source": "Kazumi Iconic Waifu Database",
                    }
        except Exception as exc:
            print(f"[ICONIC WAIFU DROP ERROR] {exc}", flush=True)

    # 2. Danbooru (with image bytes download)
    try:
        async with httpx.AsyncClient(timeout=6, follow_redirects=True, headers=headers) as client:
            for _ in range(15):
                tags = random.choice(DANBOORU_TAG_PROFILES)
                r = await client.get(
                    DANBOORU_RANDOM_URL,
                    params={"tags": tags},
                )
                if r.status_code != 200:
                    continue
                item = r.json() or {}
                if not _good_drop_post(item):
                    continue
                name, aliases = _character_names(item.get("tag_string_character"))
                url = item.get("large_file_url") or item.get("file_url")
                if not name or not aliases or not url:
                    continue
                image_file = await _image_file_from_url(client, url)
                if image_file:
                    return {
                        "name": name,
                        "aliases": aliases,
                        "photo": image_file,
                        "image_url": url,
                        "source": f"https://danbooru.donmai.us/posts/{item.get('id')}",
                    }
    except Exception as exc:
        print(f"[DANBOORU DROP ERROR] {exc}", flush=True)

    # 3. Safebooru API (with image bytes download)
    try:
        async with httpx.AsyncClient(timeout=6, follow_redirects=True, headers=headers) as client:
            r = await client.get("https://safebooru.org/index.php?page=dapi&s=post&q=index&json=1&tags=rating:safe+solo+1girl&limit=50")
            if r.status_code == 200:
                posts = r.json() or []
                random.shuffle(posts)
                for item in posts[:10]:
                    tags = item.get("tags", "")
                    if "1boy" in tags or "multiple_girls" in tags:
                        continue
                    dir_name = item.get("directory")
                    img_name = item.get("image")
                    if dir_name and img_name:
                        url = f"https://safebooru.org/images/{dir_name}/{img_name}"
                        image_file = await _image_file_from_url(client, url)
                        if image_file:
                            return {
                                "name": "Safebooru Waifu",
                                "aliases": [normalize_guess("Safebooru Waifu"), normalize_guess("Waifu")],
                                "photo": image_file,
                                "image_url": url,
                                "source": f"https://safebooru.org/index.php?page=post&s=view&id={item.get('id')}",
                            }
    except Exception as exc:
        print(f"[SAFEBOORU DROP ERROR] {exc}", flush=True)

    # 4. Waifu.im API (with image bytes download)
    try:
        async with httpx.AsyncClient(timeout=6, follow_redirects=True, headers=headers) as client:
            r = await client.get("https://api.waifu.im/search?is_nsfw=false&included_tags=waifu&limit=10")
            if r.status_code == 200:
                images = r.json().get("images", [])
                if images:
                    item = random.choice(images)
                    url = item.get("url")
                    if url:
                        image_file = await _image_file_from_url(client, url)
                        if image_file:
                            return {
                                "name": "Anime Waifu",
                                "aliases": [normalize_guess("Anime Waifu"), normalize_guess("Waifu")],
                                "photo": image_file,
                                "image_url": url,
                                "source": "https://waifu.im",
                            }
    except Exception as exc:
        print(f"[WAIFU.IM DROP ERROR] {exc}", flush=True)

    # 5. Nekos.best API (with image bytes download)
    try:
        async with httpx.AsyncClient(timeout=6, follow_redirects=True, headers=headers) as client:
            r = await client.get("https://nekos.best/api/v2/waifu")
            if r.status_code == 200:
                data = r.json().get("results", [{}])[0]
                url = data.get("url")
                artist = data.get("artist_name") or "Anime Waifu"
                if url:
                    image_file = await _image_file_from_url(client, url)
                    if image_file:
                        return {
                            "name": artist,
                            "aliases": [normalize_guess(artist)],
                            "photo": image_file,
                            "image_url": url,
                        }
    except Exception as exc:
        print(f"[NEKOS BEST DROP ERROR] {exc}", flush=True)

    # 6. Waifu.pics API (with image bytes download)
    try:
        async with httpx.AsyncClient(timeout=6, follow_redirects=True, headers=headers) as client:
            r = await client.get("https://api.waifu.pics/sfw/waifu")
            if r.status_code == 200:
                url = r.json().get("url")
                if url:
                    image_file = await _image_file_from_url(client, url)
                    if image_file:
                        return {
                            "name": "Kazumi Waifu",
                            "aliases": [normalize_guess("Kazumi Waifu"), normalize_guess("Kazumi")],
                            "photo": image_file,
                            "image_url": url,
                        }
    except Exception as exc:
        print(f"[WAIFU PICS DROP ERROR] {exc}", flush=True)

    # 7. Fallback: Download fallback photo bytes
    try:
        async with httpx.AsyncClient(timeout=6, follow_redirects=True, headers=headers) as client:
            image_file = await _image_file_from_url(client, DROP_FALLBACK_PHOTO)
            if image_file:
                return {"name": "Kazumi", "aliases": [normalize_guess("Kazumi")], "photo": image_file, "image_url": DROP_FALLBACK_PHOTO}
    except Exception:
        pass

    return {"name": "Kazumi", "aliases": [normalize_guess("Kazumi")], "photo": DROP_FALLBACK_PHOTO, "image_url": DROP_FALLBACK_PHOTO}


async def _expire_drop_after(context: ContextTypes.DEFAULT_TYPE, chat_id: int, message_id: int, delay: int = DROP_TTL_SECONDS):
    try:
        await asyncio.sleep(delay)
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
        except BadRequest as exc:
            if _cleanup_error_is_final(exc):
                _clear_drop(chat_id, message_id)
                return
            now = datetime.utcnow()
            gacha_messages_collection.update_one(
                {"chat_id": chat_id, "message_id": message_id},
                {
                    "$inc": {"delete_attempts": 1},
                    "$set": {
                        "last_delete_error": str(exc)[:300],
                        "last_delete_attempt_at": now,
                        "next_delete_attempt_at": now + timedelta(minutes=5),
                    },
                },
            )
            print(f"[WAIFU DROP CLEANUP ERROR] chat={chat_id} message={message_id}: {exc}", flush=True)
            return
        except TelegramError as exc:
            if _cleanup_error_is_final(exc):
                _clear_drop(chat_id, message_id)
                return
            now = datetime.utcnow()
            gacha_messages_collection.update_one(
                {"chat_id": chat_id, "message_id": message_id},
                {
                    "$inc": {"delete_attempts": 1},
                    "$set": {
                        "last_delete_error": str(exc)[:300],
                        "last_delete_attempt_at": now,
                        "next_delete_attempt_at": now + timedelta(minutes=5),
                    },
                },
            )
            print(f"[WAIFU DROP CLEANUP ERROR] chat={chat_id} message={message_id}: {exc}", flush=True)
            return
        _clear_drop(chat_id, message_id)
    except asyncio.CancelledError:
        return


def _schedule_drop_expiry(context: ContextTypes.DEFAULT_TYPE, chat_id: int, message_id: int):
    task = _expire_drop_after(context, chat_id, message_id)
    application = getattr(context, "application", None)
    if application:
        application.create_task(task)
    else:
        asyncio.create_task(task)


def _is_waifu_drop_message(message):
    text = (getattr(message, "caption", None) or getattr(message, "text", None) or "").lower()
    return "waifu appeared" in text and "reply to this" in text

_GROUP_MSG_COUNT = {}
_GROUP_DROPS_ENABLED = {}
_GROUP_DROPS_TTL = {}


async def _refresh_drop_settings(chat_id: int):
    """Refresh a group setting outside the Telegram update path."""
    try:
        group_doc = await asyncio.to_thread(groups_collection.find_one, {"chat_id": chat_id}) or {}
        _GROUP_DROPS_ENABLED[chat_id] = group_doc.get("waifu_drops_enabled", True)
    except Exception as exc:
        print(f"[WAIFU DROP SETTINGS ERROR] chat={chat_id}: {exc}", flush=True)


async def _spawn_drop(update: Update, context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    """Run the infrequent database, media, and send work after the update is released."""
    chat = update.effective_chat
    message = update.effective_message
    if not chat or not message:
        return

    try:
        await asyncio.to_thread(
            groups_collection.update_one,
            {"chat_id": chat_id},
            {"$inc": {"msg_count": DROP_MESSAGE_COUNT}},
            upsert=True,
        )
        drop = await fetch_drop_character()
        name = drop["name"]
        photo = drop.get("photo") or DROP_FALLBACK_PHOTO

        hint = " ".join(part[:1] + ("•" * max(0, len(part) - 1)) for part in name.split())
        caption = (
            f"👩 <b>A Waifu Appeared!</b>\n\n"
            f"Guess her real character name to collect her.\n"
            f"<b>Hint:</b> <code>{hint}</code>\n"
            f"<b>Reward:</b> <code>{format_money(DROP_REWARD)}</code>\n"
            f"<i>Reply to this image.</i>\n"
            f"{DROP_DELETE_NOTICE}"
        )
        photo_list = []
        if photo and "catbox" not in str(photo):
            photo_list.append(photo)
        if DROP_FALLBACK_PHOTO and DROP_FALLBACK_PHOTO not in photo_list:
            photo_list.append(DROP_FALLBACK_PHOTO)

        sent = None
        for photo_obj in photo_list:
            try:
                if hasattr(photo_obj, "seek"):
                    photo_obj.seek(0)
                sent = await message.reply_photo(
                    photo=photo_obj,
                    caption=caption,
                    parse_mode=ParseMode.HTML,
                )
                if sent:
                    drop_for_store = dict(drop)
                    drop_for_store["telegram_file_id"] = sent.photo[-1].file_id if sent.photo else None
                    _remember_drop(chat.id, sent.message_id, drop_for_store)
                    _schedule_drop_expiry(context, chat.id, sent.message_id)
                    break
            except Exception as exc:
                print(f"[WAIFU DROP PHOTO ERROR] chat={chat.id} photo={photo_obj}: {exc}", flush=True)
                if "flood" in str(exc).lower() or "retry after" in str(exc).lower():
                    break

        if not sent:
            try:
                sent = await message.reply_text(caption.replace("image", "message"), parse_mode=ParseMode.HTML)
                _remember_drop(chat.id, sent.message_id, drop)
                _schedule_drop_expiry(context, chat.id, sent.message_id)
            except Exception as exc:
                print(f"[WAIFU DROP SEND ERROR] chat={chat.id}: {exc}", flush=True)
    except Exception as exc:
        print(f"[WAIFU DROP SPAWN ERROR] chat={chat_id}: {exc}", flush=True)

async def check_drops(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update or not update.message or not update.effective_chat: return
    chat = update.effective_chat
    if chat.type == "private": return

    now_ts = time.time()
    chat_id = chat.id
    refresh_settings = chat_id not in _GROUP_DROPS_TTL or (now_ts - _GROUP_DROPS_TTL[chat_id] > 120)
    if refresh_settings:
        _GROUP_DROPS_TTL[chat_id] = now_ts

    if not _GROUP_DROPS_ENABLED.get(chat_id, True):
        return

    _GROUP_MSG_COUNT[chat_id] = _GROUP_MSG_COUNT.get(chat_id, 0) + 1
    count = _GROUP_MSG_COUNT[chat_id]
    
    if count % DROP_MESSAGE_COUNT == 0:
        context.application.create_task(_spawn_drop(update, context, chat_id), update=update)

    if refresh_settings:
        context.application.create_task(_refresh_drop_settings(chat_id), update=update)


async def toggle_waifu_drops_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    if chat.type == "private":
        return await update.message.reply_text("❌ <b>Group command only.</b>", parse_mode=ParseMode.HTML)
    
    member = await chat.get_member(user.id)
    if member.status not in ("administrator", "creator"):
        return await update.message.reply_text("❌ <b>Admin only.</b>", parse_mode=ParseMode.HTML)

    if not context.args:
        group_doc = await asyncio.to_thread(groups_collection.find_one, {"chat_id": chat.id}) or {}
        state = "ON 🟢" if group_doc.get("waifu_drops_enabled", True) else "OFF 🔴"
        return await update.message.reply_text(
            f"🌸 <b>Waifu Drops:</b> <code>{state}</code>\n"
            f"Usage: <code>/waifudrop on</code> or <code>/waifudrop off</code>",
            parse_mode=ParseMode.HTML,
        )

    arg = context.args[0].lower()
    if arg in ("on", "enable", "true", "1"):
        new_state = True
    elif arg in ("off", "disable", "false", "0"):
        new_state = False
    else:
        return await update.message.reply_text("❌ <b>Usage:</b> <code>/waifudrop on</code> or <code>/waifudrop off</code>", parse_mode=ParseMode.HTML)

    await asyncio.to_thread(
        groups_collection.update_one,
        {"chat_id": chat.id},
        {"$set": {"waifu_drops_enabled": new_state, "title": chat.title}},
        upsert=True,
    )
    state_str = "ENABLED 🟢" if new_state else "DISABLED 🔴"
    await update.message.reply_text(
        f"🌸 <b>Waifu drops are now {state_str} in this group.</b>",
        parse_mode=ParseMode.HTML,
    )

async def collect_waifu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    msg = update.message
    
    if not msg or not msg.text:
        return
    reply_message = msg.reply_to_message
    if not reply_message:
        return

    drop, drop_message_id = _find_replied_drop(chat.id, reply_message)
    if not drop:
        if reply_message and _is_waifu_drop_message(reply_message):
            await msg.reply_text(
                "\u23f3 <b>This waifu drop is no longer claimable.</b>\nWait for the next drop and reply to it fast.",
                parse_mode=ParseMode.HTML,
            )
            raise ApplicationHandlerStop
        return

    guess = normalize_guess(msg.text)
    correct = drop.get("name") if isinstance(drop, dict) else drop
    aliases = set(drop.get("aliases") or [correct]) if isinstance(drop, dict) else {correct}
    aliases.update(_answer_variants(correct))
    aliases.update(_answer_variants(drop.get("display_name") if isinstance(drop, dict) else correct))
    aliases = {normalize_guess(alias) for alias in aliases if alias}
    
    if guess == correct or guess in aliases:
        user = ensure_user_exists(msg.from_user)
        rarity = random.choice(["Common", "Rare", "Epic", "Legendary"])
        display_name = drop.get("display_name", correct.title()) if isinstance(drop, dict) else correct.title()
        waifu = {
            "name": display_name,
            "rarity": rarity,
            "date": datetime.utcnow(),
            "image": drop.get("image") if isinstance(drop, dict) else None,
            "telegram_file_id": drop.get("telegram_file_id") if isinstance(drop, dict) else None,
            "drop_message_id": drop_message_id,
        }
        collected = adjust_user_balance(
            user["user_id"],
            DROP_REWARD,
            "waifu_collect",
            f"Collected {display_name}",
            chat_id=chat.id,
            source="waifu_drop",
            extra_push={"waifus": waifu},
            meta={"name": display_name, "rarity": rarity, "drop_message_id": drop_message_id},
        )
        if not collected:
            await msg.reply_text(
                "\u26a0\ufe0f <b>Collection could not be saved.</b> Please reply again.",
                parse_mode=ParseMode.HTML,
            )
            raise ApplicationHandlerStop

        _clear_drop(chat.id, drop_message_id)
        wrong_drop_answer_cooldowns.pop((chat.id, drop_message_id, msg.from_user.id), None)
        
        await msg.reply_text(
            f"\U0001F389 <b>Collected!</b>\n\n"
            f"\U0001F464 {get_mention(user)} caught <b>{display_name}</b>!\n"
            f"\U0001F31F <b>Rarity:</b> {rarity}\n"
            f"\U0001F4B0 <b>Reward:</b> <code>{format_money(DROP_REWARD)}</code>",
            parse_mode=ParseMode.HTML
        )
    else:
        if _wrong_answer_allowed(chat.id, drop_message_id, msg.from_user.id):
            hint_name = drop.get("display_name") or str(correct).title() if isinstance(drop, dict) else str(correct).title()
            hint = " ".join(part[:1] + ("\u2022" * max(0, len(part) - 1)) for part in str(hint_name).split())
            await msg.reply_text(
                "\u274c <b>Wrong name.</b>\n"
                f"<b>Hint:</b> <code>{hint}</code>\n"
                "<i>Reply with the real character name.</i>",
                parse_mode=ParseMode.HTML,
            )
    raise ApplicationHandlerStop
