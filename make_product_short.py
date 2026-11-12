"""상품 대본 JSON 하나로 세로 숏츠(1080x1920, 30fps)를 만든다. 판다랭크 없이 자체 생성.
사용법: python make_product_short.py shorts/src/<이름>.json shorts/<이름>.mp4

대본 JSON 형식
{
  "name": "2026-11-11-soomn-pillow",       # 파일 이름
  "product": "숨엔 실리콘폼 경추베개",        # 위쪽에 계속 보이는 상품명
  "images": ["https://...jpg", "local.jpg"],  # 상품 사진 (URL 또는 shorts/src/<이름>/ 안의 파일)
  "voice": "female" | "male",              # AI 내레이션 목소리 (기본 female)
  "scenes": [
    {"img": 0, "say": "읽어줄 문장", "cap": ["자막 첫 줄", "[강조] 둘째 줄"], "badge": "선택"}
  ],
  "cta": ["구매 링크는", "[프로필]에 있어요"]   # 마지막 화면 문구
}
- cap 안의 [대괄호] 부분은 강조색으로 칠해진다.
- 장면 길이는 내레이션 길이에 맞춰 자동으로 정해진다.
- 대가성 문구는 마지막 화면 아래에 항상 들어간다.
"""
import asyncio, glob, hashlib, json, os, re, shutil, subprocess, sys, wave
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

src, final = sys.argv[1], sys.argv[2]
data = json.load(open(src, encoding="utf-8"))
NAME = data["name"]
SRC_DIR = os.path.join(os.path.dirname(src), NAME)
tmp = os.path.join(os.path.dirname(os.path.abspath(final)) or ".", f"_tmp_{NAME}")
os.makedirs(tmp, exist_ok=True)
W, H, FPS = 1080, 1920, 30
SALT = int(hashlib.md5(NAME.encode()).hexdigest()[:8], 16)
rng = np.random.default_rng(SALT)
DISCLOSURE = data.get("disclosure") or "이 콘텐츠는 네이버 쇼핑 커넥트 활동의 일환으로, 판매 시 수수료를 제공받습니다."

# ---------- 폰트 ----------
def find_font(weights):
    for w in weights:
        hits = glob.glob(f"/usr/share/fonts/**/NotoSansCJK-{w}.ttc", recursive=True)
        if hits: return hits[0]
        hits = glob.glob(os.path.expanduser(f"~/.fonts/NotoSansCJKkr-{w}.otf")) + glob.glob(f"fonts/NotoSansCJKkr-{w}.otf")
        if hits: return hits[0]
    raise SystemExit("Noto Sans CJK 폰트를 찾을 수 없습니다")
FB = find_font(["Black", "Bold"]); FBold = find_font(["Bold"]); FM = find_font(["Medium", "Regular", "Bold"])
def font(path, size): return ImageFont.truetype(path, size, index=1 if path.endswith(".ttc") else 0)  # ttc는 index=1이 한국어

# ---------- 강조색 (상품마다 다르게, 모두 밝은 색) ----------
ACCENTS = [(255, 214, 0), (0, 230, 180), (255, 120, 150), (110, 200, 255), (255, 160, 60), (190, 150, 255)]
ACC = ACCENTS[SALT % len(ACCENTS)]
STROKE = (0, 0, 0)

# ---------- 상품 사진 준비 ----------
def load_images():
    out = []
    for k, ref in enumerate(data["images"]):
        p = os.path.join(tmp, f"img{k}")
        if re.match(r"https?://", ref):
            import requests
            r = requests.get(ref, timeout=30, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://smartstore.naver.com/"})
            r.raise_for_status(); open(p, "wb").write(r.content)
        else:
            shutil.copy(ref if os.path.exists(ref) else os.path.join(SRC_DIR, ref), p)
        im = ImageOps.exif_transpose(Image.open(p)).convert("RGB")
        out.append(im)
    if not out: raise SystemExit("상품 사진이 하나도 없습니다")
    return out
IMGS = load_images()

def cover(im, w, h):
    return ImageOps.fit(im, (w, h), Image.LANCZOS)

def make_intro_plate(im, scale=1.12):
    w, h = int(W * scale), int(H * scale)
    bg = cover(im, w, h).filter(ImageFilter.GaussianBlur(18))
    bg = Image.blend(bg, Image.new("RGB", (w, h), (0, 0, 0)), 0.35)
    ph = im.copy(); r = min(w * 0.96 / ph.width, h * 0.62 / ph.height)
    ph = ph.resize((int(ph.width * r), int(ph.height * r)), Image.LANCZOS)
    bg.paste(ph, ((w - ph.width) // 2, int(h * 0.30)))
    return bg


def make_plate(im, scale=1.12):
    """배경: 같은 사진을 크게 흐리고 어둡게 + 가운데에 상품 사진(둥근 카드, 그림자). 줌을 위해 크게 만든다."""
    w, h = int(W * scale), int(H * scale)
    bg = cover(im, w, h).filter(ImageFilter.GaussianBlur(40))
    bg = Image.blend(bg, Image.new("RGB", (w, h), (0, 0, 0)), 0.55).convert("RGBA")
    box_w, box_h = int(w * 0.84), int(h * 0.44)
    r = min(box_w / im.width, box_h / im.height)  # 작은 사진도 칸에 맞게 키운다
    ph = im.resize((int(im.width * r), int(im.height * r)), Image.LANCZOS)
    x, y = (w - ph.width) // 2, int(h * 0.15) + (box_h - ph.height) // 2
    sh = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle([x - 6, y + 18, x + ph.width + 6, y + ph.height + 30], 40, fill=(0, 0, 0, 170))
    bg.alpha_composite(sh.filter(ImageFilter.GaussianBlur(28)))
    mask = Image.new("L", ph.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, ph.width, ph.height], 36, fill=255)
    bg.paste(ph, (x, y), mask)
    return bg.convert("RGB")

# ---------- 판다랭크식 레이아웃: 검은 바탕 + 위 고정 제목(흰/빨강) + 가운데 사진 + 작은 자막 ----------
PANDA = data.get("style") == "panda"
BAND_Y0, BAND_Y1 = 420, 1500

def make_plate_panda(im, scale=1.12):
    w, h = int(W * scale), int(H * scale)
    bg = Image.new("RGB", (w, h), (0, 0, 0))
    side = int((BAND_Y1 - BAND_Y0) * scale)
    bg.paste(cover(im, w, side), (0, (h - side) // 2))
    return bg

def chunks(say):
    out = []
    for part in re.split(r"(?<=[,.!?…])\s+", say.strip()):
        while len(part) > 17:
            k = part.rfind(" ", 0, 17); k = k if k > 5 else 17
            out.append(part[:k].strip()); part = part[k:].strip()
        if part: out.append(part)
    m = []
    for x in out:  # 너무 짧은 조각은 앞 조각에 붙인다
        if m and (len(x) < 6 or len(m[-1]) < 6) and len(m[-1]) + len(x) <= 21: m[-1] += " " + x
        else: m.append(x)
    return m or [""]

def overlay_panda(text, last=False):
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    d.rectangle([0, 0, W, BAND_Y0], fill=(0, 0, 0, 255)); d.rectangle([0, BAND_Y1, W, H], fill=(0, 0, 0, 255))
    title = [t for t in (data.get("title") or [data["product"]]) if t][:2]
    y = 170 if len(title) == 2 else 230
    for k, line in enumerate(title):
        f = font(FB, 98)
        while d.textlength(line, font=f) > 1000: f = font(FB, f.size - 4)
        d.text(((W - d.textlength(line, font=f)) / 2, y + 118 * k), line, font=f,
               fill=(255, 255, 255) if k == 0 and len(title) == 2 else (255, 45, 45))
    if text:
        f = font(FBold, 54)
        while d.textlength(text, font=f) > 990: f = font(FBold, f.size - 2)
        tw = d.textlength(text, font=f); ty = BAND_Y1 - 130
        d.rectangle([(W - tw) / 2 - 20, ty - 6, (W + tw) / 2 + 20, ty + f.size + 22], fill=(0, 0, 0, 235))
        d.text(((W - tw) / 2, ty), text, font=f, fill=(255, 255, 255))
    if last:
        df = font(FM, 30); ws = DISCLOSURE.split(" "); k = len(ws) // 2
        lines = [DISCLOSURE] if d.textlength(DISCLOSURE, font=df) < 980 else [" ".join(ws[:k]), " ".join(ws[k:])]
        for k, t in enumerate(lines):
            d.text(((W - d.textlength(t, font=df)) / 2, 1570 + 44 * k), t, font=df, fill=(210, 210, 210))
    return im

# ---------- 자막 ----------
def parse(line):  # "[강조] 문장" → [(텍스트, 강조여부)]
    parts = re.split(r"(\[[^\]]+\])", line)
    return [(p[1:-1], True) if p.startswith("[") else (p, False) for p in parts if p]

def draw_rich(d, y, line, size, maxw=980):
    segs = parse(line)
    while True:
        f = font(FB, size); tw = sum(d.textlength(t, font=f) for t, _ in segs)
        if tw <= maxw or size <= 56: break
        size -= 4
    x = (W - tw) / 2
    for t, hi in segs:
        d.text((x, y), t, font=f, fill=ACC if hi else (255, 255, 255), stroke_width=9, stroke_fill=STROKE)
        x += d.textlength(t, font=f)
    return size

def overlay_intro(scene):
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    sc = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(sc).rectangle([0, 120, W, 560], fill=(0, 0, 0, 170))
    im.alpha_composite(sc.filter(ImageFilter.GaussianBlur(30))); d = ImageDraw.Draw(im)
    pf = font(FB, 64); t = "주목!!"; tw = d.textlength(t, font=pf)
    d.rounded_rectangle([(W - tw) / 2 - 30, 150, (W + tw) / 2 + 30, 240], 45, fill=(235, 30, 45))
    d.text(((W - tw) / 2, 158), t, font=pf, fill=(255, 255, 255))
    y = 280
    for k, line in enumerate(scene.get("cap", [])[:2]):
        segs = parse(line); size = 132
        while True:
            f = font(FB, size); tw = sum(d.textlength(x, font=f) for x, _ in segs)
            if tw <= 1000 or size <= 70: break
            size -= 4
        x0 = (W - tw) / 2
        for t2, hi in segs:
            d.text((x0, y), t2, font=f, fill=(255, 226, 0) if (hi or k == 1) else (255, 255, 255), stroke_width=10, stroke_fill=(0, 0, 0))
            x0 += d.textlength(t2, font=f)
        y += size + 30
    return im


def overlay(scene, idx, total, last=False):
    if scene.get("intro"): return overlay_intro(scene)
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    # 위: 상품명 띠 + 진행 막대
    pf = font(FBold, 40); prod = data["product"]
    while d.textlength(prod, font=pf) > 900: pf = font(FBold, pf.size - 2)
    pw = d.textlength(prod, font=pf)
    d.rounded_rectangle([(W - pw) / 2 - 34, 120, (W + pw) / 2 + 34, 196], 38, fill=(0, 0, 0, 170))
    d.text(((W - pw) / 2, 132), prod, font=pf, fill=(255, 255, 255))
    seg = (W - 160 - 8 * (total - 1)) / total
    for k in range(total):
        x0 = 80 + k * (seg + 8)
        d.rounded_rectangle([x0, 70, x0 + seg, 80], 5, fill=ACC + (255,) if k <= idx else (255, 255, 255, 70))
    # 배지
    badge = scene.get("badge")
    if badge:
        bf = font(FB, 54); bw = d.textlength(badge, font=bf)
        d.rounded_rectangle([(W - bw) / 2 - 36, 1150, (W + bw) / 2 + 36, 1242], 46, fill=ACC + (255,))
        d.text(((W - bw) / 2, 1160), badge, font=bf, fill=(15, 15, 20))
    # 아래: 큰 자막 (어두운 막 위)
    caps = scene.get("cap", [])
    if caps:
        y0 = 1300 if not last else 1180
        sc = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(sc).rectangle([0, y0 - 80, W, y0 + 150 * len(caps) + 60], fill=(0, 0, 0, 150))
        im.alpha_composite(sc.filter(ImageFilter.GaussianBlur(40))); d = ImageDraw.Draw(im)
        for k, line in enumerate(caps):
            draw_rich(d, y0 + 150 * k, line, 104)
    if last:
        df = font(FM, 30); txt = DISCLOSURE
        lines = [txt]
        if d.textlength(txt, font=df) >= 980:  # 띄어쓰기 기준으로 두 줄
            ws = txt.split(" "); k = len(ws) // 2
            lines = [" ".join(ws[:k]), " ".join(ws[k:])]
        for k, t in enumerate(lines):
            d.text(((W - d.textlength(t, font=df)) / 2, 1730 + 44 * k), t, font=df, fill=(235, 235, 235), stroke_width=3, stroke_fill=STROKE)
    return im

# ---------- AI 내레이션 (edge-tts, 실패하면 무음) ----------
VOICES = {"female": "ko-KR-SunHiNeural", "male": "ko-KR-InJoonNeural"}
GVOICE = {"female": ["Aoede", "Kore", "Leda"], "male": ["Puck", "Fenrir", "Orus"]}
_gtts_off = False
def gemini_tts(text, path):
    """Gemini 음성: 사람이 말하듯 자연스러운 톤. 실패하면 None (무료 한도 초과 등)."""
    global _gtts_off
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key or _gtts_off: return None
    import base64, requests
    voice = GVOICE.get(data.get("voice", "female"), GVOICE["female"])[SALT % 3]
    style = "Say this in Korean like an excited friend sharing a great find, casual and fast: "
    for model in ["gemini-2.5-flash-preview-tts", "gemini-2.5-flash-tts", "gemini-2.5-pro-preview-tts"]:
        r = {}
        try:
            r = requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}", timeout=60,
                              json={"contents": [{"parts": [{"text": style + text}]}],
                                    "generationConfig": {"responseModalities": ["AUDIO"],
                                                         "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}}}}}).json()
            b64 = r["candidates"][0]["content"]["parts"][0]["inlineData"]["data"]
            raw = path.replace(".mp3", ".pcm"); open(raw, "wb").write(base64.b64decode(b64))
            wav = path.replace(".mp3", ".wav")
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "s16le", "-ar", "24000", "-ac", "1", "-i", raw,
                            "-af", "silenceremove=start_periods=1:start_threshold=-45dB,areverse,silenceremove=start_periods=1:start_threshold=-45dB,areverse",
                            "-ar", "44100", "-ac", "2", wav], check=True)
            dur = os.path.getsize(raw) / 48000
            if dur > len(text) * 0.22 + 1.5:  # 지시문까지 읽어버린 경우 버림
                print(f"::notice::Gemini 음성이 너무 김({dur:.1f}s) → 다시 시도"); continue
            return wav
        except Exception as e:
            err = str(r.get("error", {}).get("code")) if isinstance(r, dict) and "error" in r else type(e).__name__
            last = f"{model}: " + (json.dumps(r.get("error", {}), ensure_ascii=False)[:160] if isinstance(r, dict) and r.get("error") else repr(e)[:160])
            if err in ("429", "403"): continue
    print("::notice::Gemini 음성 사용 불가 → 기본 음성으로 대체 / " + locals().get("last", "")); _gtts_off = True
    return None

def tts(text, path):
    g = gemini_tts(text, path)
    if g: return g
    try:
        import edge_tts
        async def run():
            await edge_tts.Communicate(text, VOICES.get(data.get("voice", "female"), "ko-KR-SunHiNeural"), rate="+15%", pitch="+3Hz").save(path)
        asyncio.run(run())
        wav = path.replace(".mp3", ".wav")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", path, "-ar", "44100", "-ac", "2", wav], check=True)
        return wav
    except Exception as e:
        print(f"::warning::내레이션 생성 실패({e.__class__.__name__}) - 무음으로 진행")
        return None
def dur(wav):
    with wave.open(wav) as w: return w.getnframes() / w.getframerate()

# ---------- 장면 만들기 ----------
scenes = list(data["scenes"])
if data.get("intro") and not PANDA:  # 첫 1~2초 후킹 인트로 (상품 크게 + 외침)
    scenes.insert(0, {"img": 0, "intro": True, "badge": "!", "say": data["intro"].get("say", "여러분! 이거 아시나요?!"),
                      "cap": data["intro"].get("cap", ["여러분!", "[이거 아시나요?!]"])})
cta = {"img": scenes[0].get("img", 0), "say": data.get("cta_say", "구매 링크는 프로필에서 확인하세요."), "crop": data.get("cta_crop"),
       "cap": data.get("cta", ["구매 링크는", "[프로필]에서 확인!"]), "last": True}
scenes.append(cta)
T = 0.3  # 장면 전환 겹침
clips, voices = [], []
for i, s in enumerate(scenes):
    v = tts(s["say"], f"{tmp}/v{i}.mp3") if s.get("say") else None
    sec = max(1.6 if s.get("intro") else 1.8, (dur(v) + (0.25 if s.get("intro") else 0.45)) if v else len(s.get("say", "")) * 0.13 + 0.8)
    sec = min(sec, 6.5) + T
    voices.append((v, sec))
    src_im = IMGS[s.get("img", i) % len(IMGS)]
    if s.get("crop"):  # [x0, y0, x1, y1] 비율(0~1)로 사진 일부를 확대해서 보여준다 (사진이 한 장뿐일 때 장면마다 다르게)
        x0, y0, x1, y1 = s["crop"]; w0, h0 = src_im.size
        src_im = src_im.crop((int(x0 * w0), int(y0 * h0), int(x1 * w0), int(y1 * h0)))
    if src_im.height > src_im.width * 1.6:  # 긴 상세페이지 통째로는 쓰지 않고 한 부분만
        w0, h0 = src_im.size; y0 = int(h0 * [0.05, 0.3, 0.55, 0.75][i % 4]); y0 = min(y0, h0 - int(w0 * 1.2))
        src_im = src_im.crop((0, max(0, y0), w0, max(0, y0) + int(w0 * 1.2)))
    c = f"{tmp}/c{i}.mp4"; frames = int(sec * FPS)
    if PANDA:
        pp = f"{tmp}/p{i}.png"; make_plate_panda(src_im).save(pp)
        cs = chunks(s.get("say", "")); tot = sum(len(x) for x in cs) or 1; talk = max(0.5, sec - T - 0.3); t0 = 0.0
        ins, fc, prev = ["-loop", "1", "-i", pp], [], "bg"
        z = "min(1.0+on*0.0007,1.10)" if i % 2 == 0 else "max(1.10-on*0.0007,1.0)"
        fc.append(f"[0:v]zoompan=z='{z}':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={W}x{H}:fps={FPS}[bg]")
        for k, tx in enumerate(cs):
            op = f"{tmp}/o{i}_{k}.png"; overlay_panda(tx, last=s.get("last", False)).save(op)
            t1 = sec if k == len(cs) - 1 else t0 + talk * len(tx) / tot
            ins += ["-loop", "1", "-i", op]
            fc.append(f"[{prev}][{k + 1}:v]overlay=0:0:enable='between(t,{t0:.2f},{t1:.2f})'[x{k}]"); prev = f"x{k}"; t0 = t1
        fc.append(f"[{prev}]format=yuv420p[out]")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *ins, "-t", f"{sec:.2f}", "-filter_complex", ";".join(fc), "-map", "[out]",
                        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-r", str(FPS), c], check=True)
        clips.append((c, sec)); continue
    plate = (make_intro_plate if s.get("intro") else make_plate)(src_im); pp = f"{tmp}/p{i}.png"; plate.save(pp)
    op = f"{tmp}/o{i}.png"; overlay(s, i, len(scenes), last=s.get("last", False)).save(op)
    frames = int(sec * FPS)
    mode = (SALT + i) % 3
    z = ["if(lt(on,6),1.16-on*0.02,min(zoom+0.0009,1.12))", "if(lt(on,6),1.20-on*0.013,max(zoom-0.0009,1.0))", "if(lt(on,6),1.14-on*0.013,1.06)"][mode]
    xexpr = "iw/2-(iw/zoom/2)" if mode != 2 else f"(iw-iw/zoom)*on/{frames}"
    c = f"{tmp}/c{i}.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-i", pp, "-loop", "1", "-i", op, "-t", f"{sec:.2f}",
        "-filter_complex",
        f"[0:v]zoompan=z='{z}':d={frames}:x='{xexpr}':y='ih/2-(ih/zoom/2)':s={W}x{H}:fps={FPS}[bg];[bg][1:v]overlay=0:0,format=yuv420p",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-r", str(FPS), c], check=True)
    clips.append((c, sec))

TRANS = ["slideleft", "smoothleft", "slideup", "fade", "wipeleft"]
tr = "fade" if PANDA else TRANS[SALT % len(TRANS)]
inputs, filt, last, off = [], [], "0:v", 0.0
for c, _ in clips: inputs += ["-i", c]
starts = [0.0]
for i in range(1, len(clips)):
    off += clips[i - 1][1] - T; starts.append(off)
    filt.append(f"[{last}][{i}:v]xfade=transition={tr}:duration={T}:offset={off:.2f}[v{i}]"); last = f"v{i}"
video = f"{tmp}/video.mp4"
subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *inputs, "-filter_complex", ";".join(filt), "-map", f"[{last}]",
    "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", video], check=True)
DUR = sum(s for _, s in clips) - T * (len(clips) - 1)

# ---------- 배경음악 (직접 합성, 저작권 없음) + 내레이션 섞기 ----------
SR = 44100; N = int(SR * DUR); out = np.zeros(N)
def add(sig, start, buf):
    st = int(start * SR)
    if 0 <= st < N: n = min(len(sig), N - st); buf[st:st + n] += sig[:n]
def hz(m): return 440 * 2 ** ((m - 69) / 12)
def tone(f, length, vol, decay, attack=0.01):
    t = np.arange(int(length * SR)) / SR
    env = np.minimum(1, t / attack) * np.exp(-t * decay)
    return vol * np.sin(2 * np.pi * f * t) * env
bpm = [96, 100, 104, 108][SALT % 4]; beat = 60 / bpm
scale = [0, 2, 4, 5, 7, 9, 11]; root = 48 + int(rng.integers(0, 8))
prog = [[0, 4, 5, 3], [0, 5, 3, 4], [5, 3, 0, 4]][SALT % 3]
t, i = 0.0, 0
while t < DUR:
    deg = prog[i % 4]; ch = [root + 12 + scale[(deg + k) % 7] + 12 * ((deg + k) // 7) for k in (0, 2, 4)]
    for k in range(8): add(tone(hz(ch[k % 3] + 12), beat * 0.6, 0.05, 6), t + k * beat / 2, out)
    for m in ch: add(tone(hz(m), beat * 4.2, 0.03, 0.5, attack=0.3), t, out)
    add(tone(hz(root - 12 + scale[deg]), beat * 3.8, 0.10, 0.9, attack=0.03), t, out)
    for b in range(4):
        tt = np.arange(int(0.25 * SR)) / SR
        add(0.2 * np.sin(2 * np.pi * (100 * np.exp(-tt * 25) + 45) * tt) * np.exp(-tt * 12), t + b * beat, out)
    t += beat * 4; i += 1
out = np.convolve(out, np.ones(8) / 8, mode="same"); out = out / (np.max(np.abs(out)) + 1e-9)
voice = np.zeros(N)
for (v, _), st in zip(voices, starts):
    if v:
        with wave.open(v) as w:
            a = np.frombuffer(w.readframes(w.getnframes()), np.int16).reshape(-1, 2).mean(axis=1) / 32768
        add(a, st + 0.15, voice)
sfx = np.zeros(N)
def whoosh():
    t = np.arange(int(0.35 * SR)) / SR
    noise = np.random.default_rng(SALT).standard_normal(len(t))
    env = np.sin(np.pi * t / t[-1]) ** 2
    return 0.25 * np.convolve(noise, np.ones(6) / 6, mode="same") * env
def pop():
    t = np.arange(int(0.18 * SR)) / SR
    return 0.5 * np.sin(2 * np.pi * (600 + 900 * t / t[-1]) * t) * np.exp(-t * 18)
def ding():
    t = np.arange(int(0.6 * SR)) / SR
    return 0.3 * (np.sin(2 * np.pi * 1318 * t) + 0.5 * np.sin(2 * np.pi * 1975 * t)) * np.exp(-t * 6)
for k, st in enumerate(starts):
    if scenes[k].get("badge"): add(pop(), st + 0.05, sfx)
add(ding(), starts[-1] + 0.1, sfx)
has_voice = np.max(np.abs(voice)) > 0
mix = out * (0.12 if has_voice else 0.4) + voice * 0.95 + sfx * 0.6
fi, fo = int(0.1 * SR), int(0.8 * SR)
mix[:fi] *= np.linspace(0, 1, fi); mix[-fo:] *= np.linspace(1, 0, fo)
mix = np.clip(mix / max(1.0, np.max(np.abs(mix)) / 0.95), -1, 1)
pcm = (mix * 32767).astype(np.int16); audio = f"{tmp}/audio.wav"
with wave.open(audio, "wb") as w:
    w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR); w.writeframes(np.repeat(pcm[:, None], 2, axis=1).tobytes())

os.makedirs(os.path.dirname(os.path.abspath(final)), exist_ok=True)
subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", video, "-i", audio, "-map", "0:v", "-map", "1:a",
    "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", final], check=True)
if not os.environ.get("KEEP_TMP"): shutil.rmtree(tmp)
print(f"완성: {final} ({DUR:.1f}초, 장면 {len(scenes)}개, 내레이션 {'있음' if has_voice else '없음'})")
