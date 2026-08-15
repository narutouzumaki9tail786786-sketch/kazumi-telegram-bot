import textwrap
import unicodedata
from io import BytesIO

from PIL import Image, ImageDraw, ImageFont
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from kazumi.utils import get_mention
from kazumi.missions import track_mission


QUOTE_PANEL = (3, 4, 8, 242)
QUOTE_ACCENT = (45, 212, 191, 255)
QUOTE_TEXT = (255, 255, 255, 255)
QUOTE_MUTED = (180, 190, 205, 235)


def _font(size, bold=False):
    candidates = [
        "C:/Windows/Fonts/seguisb.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _emoji_font(size):
    for path in [
        "C:/Windows/Fonts/seguiemj.ttf",
        "C:/Windows/Fonts/seguisym.ttf",
        "C:/Windows/Fonts/segoeui.ttf",
    ]:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return _font(size)


def _plain(text):
    return unicodedata.normalize("NFKC", str(text or "")).strip()


def _safe_quote_text(text, limit=900):
    text = _plain(text)
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "..."


def _is_emojiish(ch):
    cp = ord(ch)
    return (
        cp >= 0x1F000
        or 0x2300 <= cp <= 0x23FF
        or 0x2600 <= cp <= 0x27BF
        or cp in (0xFE0F, 0x200D)
    )


def _char_font(ch, normal_font, emoji_font):
    return emoji_font if _is_emojiish(ch) else normal_font


def _emoji_size(font):
    return getattr(font, "size", 36)


def _heart_points(size):
    s = size / 64
    return [
        (32 * s, 57 * s), (8 * s, 34 * s), (5 * s, 18 * s), (16 * s, 8 * s),
        (28 * s, 13 * s), (32 * s, 21 * s), (36 * s, 13 * s), (48 * s, 8 * s),
        (59 * s, 18 * s), (56 * s, 34 * s),
    ]


def _draw_fallback_emoji(draw, x, y, ch, size):
    box = (x, y + max(0, size * 0.05), x + size, y + size * 1.05)
    if ch in ("\U0001F62D", "\U0001F622"):
        draw.ellipse(box, fill=(255, 207, 64, 255))
        draw.ellipse((x + size * 0.24, y + size * 0.34, x + size * 0.34, y + size * 0.44), fill=(30, 30, 34, 255))
        draw.ellipse((x + size * 0.66, y + size * 0.34, x + size * 0.76, y + size * 0.44), fill=(30, 30, 34, 255))
        draw.ellipse((x + size * 0.39, y + size * 0.58, x + size * 0.61, y + size * 0.77), fill=(45, 45, 52, 255))
        draw.rounded_rectangle((x + size * 0.17, y + size * 0.47, x + size * 0.29, y + size * 0.88), radius=int(size * 0.07), fill=(80, 190, 255, 255))
        draw.rounded_rectangle((x + size * 0.71, y + size * 0.47, x + size * 0.83, y + size * 0.88), radius=int(size * 0.07), fill=(80, 190, 255, 255))
        return True
    if ch in ("\U0001F600", "\U0001F602", "\U0001F60A", "\U0001F970", "\U0001F60D"):
        draw.ellipse(box, fill=(255, 207, 64, 255))
        draw.arc((x + size * 0.25, y + size * 0.42, x + size * 0.42, y + size * 0.58), 200, 340, fill=(30, 30, 34, 255), width=max(2, int(size * 0.05)))
        draw.arc((x + size * 0.58, y + size * 0.42, x + size * 0.75, y + size * 0.58), 200, 340, fill=(30, 30, 34, 255), width=max(2, int(size * 0.05)))
        draw.arc((x + size * 0.29, y + size * 0.54, x + size * 0.72, y + size * 0.84), 5, 175, fill=(30, 30, 34, 255), width=max(2, int(size * 0.06)))
        return True
    if ch in ("\u2764", "\U0001F495", "\U0001F496", "\U0001F497", "\U0001F498", "\U0001F49E"):
        points = [(x + px, y + py) for px, py in _heart_points(size)]
        draw.polygon(points, fill=(244, 63, 94, 255))
        return True
    if ch in ("\u2705", "\u274c"):
        draw.rounded_rectangle((x + size * 0.1, y + size * 0.18, x + size * 0.9, y + size * 0.98), radius=int(size * 0.16), outline=(245, 245, 245, 255), width=max(2, int(size * 0.08)))
        if ch == "\u2705":
            draw.line((x + size * 0.25, y + size * 0.6, x + size * 0.43, y + size * 0.78, x + size * 0.78, y + size * 0.36), fill=(74, 222, 128, 255), width=max(3, int(size * 0.1)))
        else:
            draw.line((x + size * 0.28, y + size * 0.36, x + size * 0.74, y + size * 0.82), fill=(248, 113, 113, 255), width=max(3, int(size * 0.1)))
            draw.line((x + size * 0.74, y + size * 0.36, x + size * 0.28, y + size * 0.82), fill=(248, 113, 113, 255), width=max(3, int(size * 0.1)))
        return True
    if ch == "\U0001F4CB":
        draw.rounded_rectangle((x + size * 0.18, y + size * 0.18, x + size * 0.82, y + size), radius=int(size * 0.08), outline=(245, 245, 245, 255), width=max(2, int(size * 0.06)))
        draw.rectangle((x + size * 0.34, y + size * 0.08, x + size * 0.66, y + size * 0.26), fill=(245, 245, 245, 255))
        for idx in range(3):
            yy = y + size * (0.42 + idx * 0.17)
            draw.line((x + size * 0.3, yy, x + size * 0.7, yy), fill=(245, 245, 245, 255), width=max(1, int(size * 0.04)))
        return True
    if ch == "\u23F3":
        draw.line((x + size * 0.24, y + size * 0.18, x + size * 0.78, y + size * 0.18), fill=(245, 245, 245, 255), width=max(2, int(size * 0.07)))
        draw.line((x + size * 0.24, y + size * 0.96, x + size * 0.78, y + size * 0.96), fill=(245, 245, 245, 255), width=max(2, int(size * 0.07)))
        draw.polygon([(x + size * 0.3, y + size * 0.22), (x + size * 0.72, y + size * 0.22), (x + size * 0.5, y + size * 0.54)], outline=(245, 245, 245, 255), fill=None)
        draw.polygon([(x + size * 0.3, y + size * 0.92), (x + size * 0.72, y + size * 0.92), (x + size * 0.5, y + size * 0.6)], fill=(245, 185, 66, 255))
        return True
    if ch == "\U0001F480":
        draw.ellipse(box, fill=(245, 245, 245, 255))
        draw.ellipse((x + size * 0.23, y + size * 0.37, x + size * 0.41, y + size * 0.55), fill=(20, 20, 24, 255))
        draw.ellipse((x + size * 0.59, y + size * 0.37, x + size * 0.77, y + size * 0.55), fill=(20, 20, 24, 255))
        draw.rectangle((x + size * 0.37, y + size * 0.74, x + size * 0.63, y + size * 0.9), fill=(20, 20, 24, 255))
        return True
    if ch == "\U0001F525":
        draw.polygon([(x + size * 0.48, y), (x + size * 0.78, y + size * 0.48), (x + size * 0.55, y + size), (x + size * 0.18, y + size * 0.62)], fill=(249, 115, 22, 255))
        draw.polygon([(x + size * 0.52, y + size * 0.26), (x + size * 0.68, y + size * 0.64), (x + size * 0.48, y + size), (x + size * 0.32, y + size * 0.66)], fill=(253, 224, 71, 255))
        return True
    return False


def _text_length(draw, text, normal_font, emoji_font):
    total = 0
    for ch in text:
        if ch in ("\ufe0f", "\u200d"):
            continue
        if _is_emojiish(ch):
            total += _emoji_size(emoji_font)
        else:
            total += draw.textlength(ch, font=normal_font)
    return total


def _draw_mixed_text(draw, xy, text, normal_font, emoji_font, fill):
    x, y = xy
    for ch in text:
        if ch in ("\ufe0f", "\u200d"):
            continue
        if _is_emojiish(ch):
            size = _emoji_size(emoji_font)
            if not _draw_fallback_emoji(draw, x, y, ch, size):
                draw.text((x, y), ch, font=emoji_font, fill=fill)
            x += size
            continue
        draw.text((x, y), ch, font=normal_font, fill=fill)
        x += draw.textlength(ch, font=normal_font)


def _message_text(message):
    text = _plain(message.text or message.caption or "")
    if text:
        return text.strip()
    if message.photo:
        return "Photo"
    if message.sticker:
        return "Sticker"
    if message.animation:
        return "Animation"
    if message.video:
        return "Video"
    if message.document:
        return "Document"
    return "Message"


async def _download_reply_photo(message, context):
    if not message.photo:
        return None
    try:
        file = await context.bot.get_file(message.photo[-1].file_id)
        data = BytesIO()
        await file.download_to_memory(out=data)
        data.seek(0)
        return Image.open(data).convert("RGB")
    except Exception as exc:
        print(f"[QUOTE PHOTO ERROR] {exc}", flush=True)
        return None


async def _download_avatar(user, context):
    if not user:
        return None
    try:
        photos = await context.bot.get_user_profile_photos(user.id, limit=1)
        if not photos.total_count:
            return None
        file = await context.bot.get_file(photos.photos[0][-1].file_id)
        data = BytesIO()
        await file.download_to_memory(out=data)
        data.seek(0)
        return Image.open(data).convert("RGBA")
    except Exception as exc:
        print(f"[QUOTE AVATAR ERROR] {exc}", flush=True)
        return None


def _cover(image, size):
    target_w, target_h = size
    src_w, src_h = image.size
    scale = max(target_w / src_w, target_h / src_h)
    new_size = (int(src_w * scale), int(src_h * scale))
    resized = image.resize(new_size, Image.Resampling.LANCZOS)
    left = (resized.width - target_w) // 2
    top = (resized.height - target_h) // 2
    return resized.crop((left, top, left + target_w, top + target_h))


def _draw_rounded(draw, box, radius, fill, outline=None, width=1):
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def _wrap_text(draw, text, font, emoji_font, max_width):
    lines = []
    for paragraph in str(text).splitlines():
        if not paragraph.strip():
            lines.append("")
            continue
        words = paragraph.split()
        current = ""
        for word in words:
            trial = word if not current else f"{current} {word}"
            if _text_length(draw, trial, font, emoji_font) <= max_width:
                current = trial
            else:
                if current:
                    lines.append(current)
                if _text_length(draw, word, font, emoji_font) <= max_width:
                    current = word
                else:
                    chunks = textwrap.wrap(word, width=14)
                    lines.extend(chunks[:-1])
                    current = chunks[-1] if chunks else ""
        if current:
            lines.append(current)
    while lines and lines[-1] == "":
        lines.pop()
    return lines


def _fit_quote_lines(draw, text, max_width, max_height, start_size=40, min_size=15):
    text = _safe_quote_text(text)
    for size in range(start_size, min_size - 1, -2):
        font = _font(size, bold=True)
        emoji_font = _emoji_font(size)
        line_gap = max(18, int(size * 1.22))
        lines = _wrap_text(draw, text, font, emoji_font, max_width)
        if len(lines) * line_gap <= max_height:
            return font, emoji_font, lines, line_gap, False

    font = _font(min_size, bold=True)
    emoji_font = _emoji_font(min_size)
    line_gap = max(18, int(min_size * 1.22))
    lines = _wrap_text(draw, text, font, emoji_font, max_width)
    max_lines = max(1, max_height // line_gap)
    clipped = len(lines) > max_lines
    if clipped:
        lines = lines[:max_lines]
        lines[-1] = lines[-1].rstrip(". ") + "..."
    return font, emoji_font, lines, line_gap, clipped


def _initials(name):
    parts = [p for p in name.split() if p]
    if not parts:
        return "?"
    return "".join(p[0] for p in parts[:2]).upper()


def _paste_circle(base, source, box):
    size = (box[2] - box[0], box[3] - box[1])
    source = _cover(source.convert("RGBA"), size)
    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse((0, 0, size[0], size[1]), fill=255)
    base.paste(source, box[:2], mask)


def render_quote_sticker(author_name, author_tag, quote_text, photo=None, avatar=None):
    width, height = 512, 512
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    title_font = _font(27, bold=True)
    handle_font = _font(14)
    small_font = _font(13)
    title_emoji = _emoji_font(31)

    author_name = _plain(author_name) or "Unknown"
    author_tag = _plain(author_tag)
    quote_text = _safe_quote_text(quote_text)

    bubble = (86, 76, 500, 474)
    draw.rounded_rectangle(bubble, radius=34, fill=QUOTE_PANEL)
    draw.polygon([(102, 386), (52, 434), (120, 420)], fill=QUOTE_PANEL)

    avatar_box = (22, 350, 112, 440)
    draw.ellipse((avatar_box[0] - 4, avatar_box[1] - 4, avatar_box[2] + 4, avatar_box[3] + 4), fill=(255, 255, 255, 235))
    if avatar:
        _paste_circle(image, avatar, avatar_box)
    else:
        draw.ellipse(avatar_box, fill=(236, 72, 153, 255))
        initials = _initials(author_name)
        initials_font = _font(30, bold=True)
        tw = draw.textlength(initials, font=initials_font)
        draw.text((67 - tw / 2, 378), initials, fill=QUOTE_TEXT, font=initials_font)

    x = 112
    y = 98
    _draw_mixed_text(draw, (x, y), author_name[:24], title_font, title_emoji, QUOTE_ACCENT)
    if author_tag:
        draw.text((x + 2, y + 31), author_tag[:30], fill=QUOTE_MUTED, font=handle_font)

    has_photo = bool(photo)
    photo_box = (366, 100, 486, 220) if has_photo else None
    text_y = 154
    max_text_width = 238 if has_photo else 350
    max_text_height = 284
    body_font, body_emoji, lines, line_gap, clipped = _fit_quote_lines(
        draw,
        quote_text,
        max_text_width,
        max_text_height,
        start_size=38 if len(quote_text) < 120 else 32,
        min_size=14,
    )

    for line in lines:
        _draw_mixed_text(draw, (x, text_y), line, body_font, body_emoji, QUOTE_TEXT)
        text_y += line_gap

    if photo and photo_box:
        preview = _cover(photo, (photo_box[2] - photo_box[0], photo_box[3] - photo_box[1])).convert("RGBA")
        mask = Image.new("L", preview.size, 0)
        mask_draw = ImageDraw.Draw(mask)
        mask_draw.rounded_rectangle((0, 0, preview.width, preview.height), radius=24, fill=255)
        image.paste(preview, photo_box[:2], mask)
        draw.rounded_rectangle(photo_box, radius=24, outline=(255, 255, 255, 70), width=2)

    footer = "/q by Kazumi" + (" · trimmed" if clipped else "")
    draw.text((112, 448), footer, fill=QUOTE_MUTED, font=small_font)

    output = BytesIO()
    image.save(output, format="WEBP", quality=90, method=6)
    output.seek(0)
    output.name = "quote.webp"
    return output


async def quote_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    reply = message.reply_to_message if message else None

    if not reply:
        return await message.reply_text(
            "\U000026A0\ufe0f <b>Reply to any text or photo message with /q.</b>",
            parse_mode=ParseMode.HTML,
        )

    user = reply.from_user
    author_name = user.full_name if user else (reply.sender_chat.title if reply.sender_chat else "Unknown")
    author_tag = f"@{user.username}" if user and user.username else ""
    quote_text = _message_text(reply)
    photo = await _download_reply_photo(reply, context)
    avatar = await _download_avatar(user, context)

    sticker = render_quote_sticker(author_name, author_tag, quote_text, photo=photo, avatar=avatar)
    try:
        await message.reply_sticker(sticker=sticker)
    except Exception as exc:
        print(f"[QUOTE STICKER ERROR] {exc}", flush=True)
        sticker.seek(0)
        await message.reply_document(document=sticker, filename="quote.webp")
    if update.effective_user:
        track_mission(update.effective_user.id, "quote")
