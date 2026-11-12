"""건강 카드뉴스 생성기: python cardnews.py spec.json 출력폴더 → 1080x1350 카드 PNG 여러 장
spec: {"accent":"#B3261E","cards":[{"type":"hook|text|tips|photo|end", ...}]}"""
import json, os, sys, glob
from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H = 1080, 1350
SAFE_T, SAFE_B = 130, 170  # 위아래는 인스타 버튼·이름에 가려지므로 비운다
BG, INK, SUB = (250, 245, 237), (34, 28, 24), (110, 98, 88)


FALLBACK = {"Black": ["Black", "Bold"], "Bold": ["Bold", "Black"], "Medium": ["Medium", "Regular", "DemiLight"], "Regular": ["Regular", "Medium", "DemiLight"]}


def font(w, size):
    """굵기 파일이 없으면 가까운 굵기로 대신 (기본 비트맵 글꼴로 떨어지면 글자가 깨져 보임)"""
    for x in FALLBACK.get(w, [w]) + ["Bold", "Regular"]:
        c = glob.glob(f"/usr/share/fonts/**/NotoSansCJK-{x}.ttc", recursive=True)
        if c: return ImageFont.truetype(c[0], size, index=1)
        c = glob.glob(os.path.expanduser(f"~/.fonts/NotoSansCJKkr-{x}.otf"))
        if c: return ImageFont.truetype(c[0], size)
    raise SystemExit("한글 글꼴 없음 — 카드 만들기 중단")


def hexc(h): h = h.lstrip("#"); return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def wrap(d, text, f, maxw):
    lines = []
    for para in text.split("\n"):
        cur = ""
        for word in para.split(" "):
            t = (cur + " " + word).strip()
            if d.textlength(clean(t), font=f) <= maxw: cur = t
            else:
                if cur: lines.append(cur)
                while d.textlength(clean(word), font=f) > maxw:  # 아주 긴 단어
                    k = len(word)
                    while d.textlength(word[:k], font=f) > maxw: k -= 1
                    lines.append(word[:k]); word = word[k:]
                cur = word
        lines.append(cur)
    return lines


def rich(d, xy, text, f, base, accent, lh):
    """[강조] 표시는 색을 바꿔 그린다. 한 줄씩."""
    x0, y = xy; on = False
    for line in text:
        x = x0; buf = ""
        for ch in line + "\0":
            if ch in "[]\0":
                if buf: d.text((x, y), buf, font=f, fill=accent if on else base); x += d.textlength(buf, font=f); buf = ""
                if ch == "[": on = True
                elif ch == "]": on = False
            else: buf += ch
        y += lh
    return y


def clean(s): return s.replace("[", "").replace("]", "")


def cover(im, w, h):
    r = max(w / im.width, h / im.height); im = im.resize((int(im.width * r) + 1, int(im.height * r) + 1))
    return im.crop(((im.width - w) // 2, (im.height - h) // 2, (im.width - w) // 2 + w, (im.height - h) // 2 + h))


def page_no(d, i, n, color):
    f = font("Medium", 26); t = f"{i}/{n}"; d.text((W - 60 - d.textlength(t, font=f), SAFE_T - 60), t, font=f, fill=color)


def brand(d, name, color):
    if name: d.text((60, SAFE_T - 60), name, font=font("Bold", 26), fill=color)


def card(c, i, n, spec, base_dir):
    acc = hexc(spec.get("accent", "#B3261E")); handle = spec.get("brand", "")
    t = c["type"]
    if t == "hook":
        im = Image.open(os.path.join(base_dir, c["image"])).convert("RGB")
        img = cover(im, W, H).filter(ImageFilter.GaussianBlur(1))
        shade = Image.new("RGBA", (W, H), (0, 0, 0, 0)); sd = ImageDraw.Draw(shade)
        for y in range(H):  # 아래로 갈수록 어둡게
            a = int(40 + 190 * max(0, (y - H * 0.25) / (H * 0.75)))
            sd.line([(0, y), (W, y)], fill=(15, 10, 8, min(a, 225)))
        img = Image.alpha_composite(img.convert("RGBA"), shade).convert("RGB"); d = ImageDraw.Draw(img)
        brand(d, handle, (255, 255, 255)); page_no(d, i, n, (230, 230, 230))
        if c.get("tag"):
            f = font("Bold", 34); tw = d.textlength(c["tag"], font=f)
            d.rounded_rectangle([60, 700, 60 + tw + 44, 700 + 64], 32, fill=acc); d.text((82, 709), c["tag"], font=f, fill=(255, 255, 255))
        f = font("Black", 92); lines = wrap(d, clean(c["title"]), f, W - 120)
        lines = [l for l in c["title"].split("\n")] if all(d.textlength(clean(l), font=f) <= W - 120 for l in c["title"].split("\n")) else lines
        y = rich(d, (60, 800), lines, f, (255, 255, 255), (255, 214, 102), 118)
        if c.get("sub"):
            d.text((60, y + 20), c["sub"], font=font("Medium", 38), fill=(235, 228, 220))
        if c.get("swipe"):
            f2 = font("Bold", 32); s = c["swipe"] + "  →"; d.text((W - 60 - d.textlength(s, font=f2), H - SAFE_B - 10), s, font=f2, fill=(255, 255, 255))
        return img
    img = Image.new("RGB", (W, H), BG); d = ImageDraw.Draw(img)
    brand(d, handle, SUB); page_no(d, i, n, SUB)
    y = SAFE_T + 40
    if c.get("label"):
        f = font("Bold", 32); tw = d.textlength(c["label"], font=f)
        d.rounded_rectangle([60, y, 60 + tw + 40, y + 58], 29, fill=acc); d.text((80, y + 7), c["label"], font=f, fill=(255, 255, 255)); y += 100
    if c.get("title"):
        f = font("Black", 68); lines = c["title"].split("\n")
        y = rich(d, (60, y), lines, f, INK, acc, 90) + 30
    if t == "text":
        f = font("Medium", 42)
        for para in c["body"]:
            y = rich(d, (60, y), wrap(d, para, f, W - 120), f, INK, acc, 62) + 28
        if c.get("source"):
            sl = wrap(d, c["source"], font("Regular", 28), W - 120); sy = H - SAFE_B - 40 * len(sl)
            d.line([(60, sy - 24), (W - 60, sy - 24)], fill=(214, 204, 192), width=2)
            for l in sl: d.text((60, sy), l, font=font("Regular", 28), fill=SUB); sy += 40
    elif t == "tips":
        for k, tip in enumerate(c["items"], 1):
            d.rounded_rectangle([60, y, W - 60, y + 170], 28, fill=(255, 255, 255), outline=(230, 220, 208), width=2)
            d.ellipse([90, y + 45, 170, y + 125], fill=acc); f = font("Black", 44); s = str(k)
            d.text((130 - d.textlength(s, font=f) / 2, y + 55), s, font=f, fill=(255, 255, 255))
            d.text((200, y + 30), tip[0], font=font("Bold", 42), fill=INK)
            lines = wrap(d, tip[1], font("Regular", 32), W - 300)[:2]
            for j, l in enumerate(lines): d.text((200, y + 88 + j * 40), l, font=font("Regular", 32), fill=SUB)
            y += 195
    elif t == "photo":
        im = Image.open(os.path.join(base_dir, c["image"])).convert("RGB")
        box = 700; ph = cover(im, box, box)
        mask = Image.new("L", (box, box), 0); ImageDraw.Draw(mask).rounded_rectangle([0, 0, box, box], 36, fill=255)
        img.paste(ph, ((W - box) // 2, y), mask); y += box + 34
        f = font("Bold", 42)
        for l in wrap(d, c["name"], f, W - 120)[:2]:
            d.text(((W - d.textlength(l, font=f)) / 2, y), l, font=f, fill=INK); y += 56
        if c.get("facts"):
            f = font("Medium", 34); s = "  ·  ".join(c["facts"])
            d.text(((W - d.textlength(s, font=f)) / 2, y + 6), s, font=f, fill=SUB); y += 60
        if c.get("cta"):
            f = font("Bold", 38); tw = d.textlength(c["cta"], font=f)
            d.rounded_rectangle([(W - tw) / 2 - 40, y + 14, (W + tw) / 2 + 40, y + 92], 39, fill=acc)
            d.text(((W - tw) / 2, y + 28), c["cta"], font=f, fill=(255, 255, 255))
        if c.get("notes"):
            f = font("Regular", 26); ny = H - SAFE_B - 36 * len(c["notes"]) + 20
            for nline in c["notes"]:
                for l in wrap(d, nline, f, W - 120): d.text(((W - d.textlength(l, font=f)) / 2, ny), l, font=f, fill=SUB); ny += 36
    elif t == "end":
        f = font("Medium", 40)
        for k, para in enumerate(c["body"]):
            d.ellipse([60, y + 14, 80, y + 34], fill=acc)
            for l in wrap(d, para, f, W - 160): d.text((100, y), l, font=f, fill=INK); y += 58
            y += 24
        f = font("Regular", 28); y = H - SAFE_B - 40 - 40 * len(c.get("notes", []))
        for nline in c.get("notes", []):
            for l in wrap(d, nline, f, W - 120): d.text((60, y), l, font=f, fill=SUB); y += 40
    return img


if __name__ == "__main__":
    spec_path, out = sys.argv[1], sys.argv[2]
    spec = json.load(open(spec_path, encoding="utf-8")); base = os.path.dirname(os.path.abspath(spec_path))
    os.makedirs(out, exist_ok=True); n = len(spec["cards"])
    for i, c in enumerate(spec["cards"], 1):
        card(c, i, n, spec, base).save(os.path.join(out, f"{i:02d}.jpg"), quality=92)
    print("카드", n, "장 →", out)
