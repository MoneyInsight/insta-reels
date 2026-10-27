"""대본 JSON 하나로 세로 릴스 영상(음악 포함)을 만든다.
사용법: python make_reel.py queue/2026-10-27.json site
결과: site/reel-<date>.mp4, site/caption.txt
 
지침
- 배경과 배경음악은 매번 다르게: 게시된 릴스 수(posted/*.json 개수)로 테마·패턴·음악을 돌려 쓰고,
  날짜로 세부 값을 섞는다. 연속된 두 릴스는 절대 같은 테마/음악 조합이 나오지 않는다.
- 가독성 우선: 배경은 항상 어둡게, 글자 뒤에 어두운 막(scrim), 모든 글자에 외곽선,
  제목 최소 72px·설명 최소 42px, 강조색은 밝은 색만 사용.
"""
import json, os, subprocess, sys, glob, hashlib, shutil
import numpy as np, wave
from PIL import Image, ImageDraw, ImageFont, ImageFilter
 
src, outdir = sys.argv[1], sys.argv[2]
data = json.load(open(src, encoding="utf-8"))
date = data["date"]
os.makedirs(outdir, exist_ok=True)
tmp = os.path.join(outdir, "_tmp"); os.makedirs(tmp, exist_ok=True)
W, H = 1080, 1920
 
# ---------- 변형 번호 (매번 다르게) ----------
ROOT = os.path.dirname(os.path.abspath(__file__))
posted = len(glob.glob(os.path.join(ROOT, "posted", "*.json")))
VARIANT = int(os.environ.get("REEL_VARIANT", posted))
SALT = int(hashlib.md5(date.encode()).hexdigest()[:8], 16)
rng_v = np.random.default_rng(VARIANT * 7919 + SALT)
 
# ---------- 폰트 ----------
def find_font(weights):
    for w in weights:
        hits = glob.glob(f"/usr/share/fonts/**/NotoSansCJK-{w}.ttc", recursive=True)
        if hits: return hits[0]
    raise SystemExit("Noto Sans CJK 폰트를 찾을 수 없습니다")
FB = find_font(["Black", "Bold"]); FBold = find_font(["Bold"]); FM = find_font(["Medium", "Regular"])
def font(path, size): return ImageFont.truetype(path, size, index=1)  # index=1: 한국어
def fit(d, text, path, size, maxw=960, minsize=40):
    f = font(path, size)
    while d.textlength(text, font=f) > maxw and size > minsize:
        size -= 4; f = font(path, size)
    return f
 
# ---------- 테마 (모두 어두운 배경 + 밝은 강조색) ----------
THEMES = [
    dict(name="미드나잇 골드", top=(10, 14, 34), bot=(30, 12, 46), g1=(255, 176, 40), g2=(90, 70, 255), acc=(255, 204, 64)),
    dict(name="에메랄드", top=(4, 20, 20), bot=(6, 38, 34), g1=(30, 220, 150), g2=(0, 120, 255), acc=(90, 255, 190)),
    dict(name="딥 오션", top=(4, 12, 34), bot=(8, 30, 64), g1=(40, 160, 255), g2=(0, 220, 220), acc=(110, 210, 255)),
    dict(name="크림슨", top=(22, 6, 12), bot=(44, 8, 20), g1=(255, 60, 90), g2=(255, 150, 40), acc=(255, 120, 130)),
    dict(name="바이올렛", top=(16, 8, 36), bot=(38, 10, 58), g1=(190, 90, 255), g2=(255, 80, 180), acc=(215, 160, 255)),
    dict(name="선셋", top=(26, 10, 18), bot=(48, 18, 8), g1=(255, 120, 40), g2=(255, 60, 120), acc=(255, 180, 80)),
    dict(name="네온 시안", top=(6, 16, 26), bot=(26, 8, 38), g1=(0, 210, 230), g2=(255, 70, 190), acc=(80, 240, 250)),
    dict(name="블랙 옐로", top=(10, 10, 12), bot=(28, 28, 32), g1=(255, 230, 0), g2=(255, 255, 255), acc=(255, 228, 0)),
]
PATTERNS = ["dots", "grid", "diagonal", "rings", "waves"]
TRANSITIONS = ["slideleft", "slideup", "smoothleft", "wipeleft", "fade", "circleopen", "slidedown", "smoothup"]
th = THEMES[VARIANT % len(THEMES)]
pattern = PATTERNS[(VARIANT * 3 + SALT) % len(PATTERNS)]
trans = TRANSITIONS[(VARIANT * 5 + SALT) % len(TRANSITIONS)]
ACC = th["acc"]
print(f"테마={th['name']} 패턴={pattern} 전환={trans}")
 
def make_background(i):
    yy, xx = np.mgrid[0:H, 0:W]
    ang = float(rng_v.uniform(0.15, 0.45))
    t = np.clip(yy / H * (1 - ang) + xx / W * ang, 0, 1)[..., None]
    base = Image.fromarray((np.array(th["top"]) * (1 - t) + np.array(th["bot"]) * t).astype(np.uint8)).convert("RGBA")
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0)); g = ImageDraw.Draw(glow)
    r = np.random.default_rng(VARIANT * 31 + i)
    # 빛 번짐은 가장자리 쪽에만 (가운데 글자 영역은 피함)
    ax, ay = int(r.choice([160, 920])), int(r.integers(220, 520))
    bx, by = W - ax, int(r.integers(1380, 1720))
    g.ellipse([ax - 430, ay - 430, ax + 430, ay + 430], fill=th["g1"] + (78,))
    g.ellipse([bx - 480, by - 480, bx + 480, by + 480], fill=th["g2"] + (64,))
    base = Image.alpha_composite(base, glow.filter(ImageFilter.GaussianBlur(170)))
    pat = Image.new("RGBA", (W, H), (0, 0, 0, 0)); p = ImageDraw.Draw(pat)
    if pattern == "dots":
        for x in range(24, W, 48):
            for y in range(24, H, 48): p.ellipse([x - 2, y - 2, x + 2, y + 2], fill=(255, 255, 255, 18))
    elif pattern == "grid":
        for x in range(0, W, 90): p.line([x, 0, x, H], fill=(255, 255, 255, 12), width=1)
        for y in range(0, H, 90): p.line([0, y, W, y], fill=(255, 255, 255, 12), width=1)
    elif pattern == "diagonal":
        for k in range(-H, W, 70): p.line([k, 0, k + H, H], fill=(255, 255, 255, 11), width=2)
    elif pattern == "rings":
        cx, cy = (ax, ay)
        for rad in range(120, 2200, 110): p.ellipse([cx - rad, cy - rad, cx + rad, cy + rad], outline=(255, 255, 255, 14), width=2)
    else:  # waves
        xs = np.arange(0, W + 10, 10)
        for row in range(0, H + 200, 120):
            pts = [(int(x), int(row + 26 * np.sin(x / 140 + row / 90))) for x in xs]
            p.line(pts, fill=(255, 255, 255, 13), width=2)
    base = Image.alpha_composite(base, pat)
    # 가독성용 어두운 막: 글자 영역 뒤를 차분하게
    scrim = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(scrim).ellipse([-120, 330, W + 120, 1460], fill=(0, 0, 0, 105))
    return Image.alpha_composite(base, scrim.filter(ImageFilter.GaussianBlur(90)))
 
STROKE = (8, 8, 14, 255)
def text_glow(im, xy, text, f, fill, stroke=4, blur=20, alpha=110):
    g = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(g).text(xy, text, font=f, fill=fill[:3] + (alpha,))
    im.alpha_composite(g.filter(ImageFilter.GaussianBlur(blur)))
    ImageDraw.Draw(im, "RGBA").text(xy, text, font=f, fill=fill, stroke_width=stroke, stroke_fill=STROKE)
 
BRAND = data.get("brand", "@soomndurion")  # 영상 왼쪽 위에 표시되는 인스타 계정
TOTAL = len(data["scenes"])
zoom_in = VARIANT % 2 == 0
 
# ---------- 장면 이미지 ----------
clips = []
for i, s in enumerate(data["scenes"]):
    im = make_background(i); d = ImageDraw.Draw(im, "RGBA")
    sm = font(FBold, 32)
    d.text((64, 102), BRAND if BRAND.startswith("@") else " ".join(BRAND), font=sm, fill=(255, 255, 255, 200), stroke_width=2, stroke_fill=STROKE)
    cnt = f"{i + 1:02d} / {TOTAL:02d}"
    d.text((W - 64 - d.textlength(cnt, font=sm), 102), cnt, font=sm, fill=(255, 255, 255, 180), stroke_width=2, stroke_fill=STROKE)
    seg = (W - 128 - 10 * (TOTAL - 1)) / TOTAL
    for k in range(TOTAL):
        x0 = 64 + k * (seg + 10)
        d.rounded_rectangle([x0, 168, x0 + seg, 177], 4, fill=ACC + (255,) if k <= i else (255, 255, 255, 24))
 
    badge = s.get("badge", "")
    if badge:
        if len(badge) > 2:
            bfont = font(FB, 60); bw = d.textlength(badge, font=bfont)
            pill = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            ImageDraw.Draw(pill).rounded_rectangle([(W - bw) / 2 - 42, 466, (W + bw) / 2 + 42, 578], 56, fill=ACC + (255,))
            im.alpha_composite(pill.filter(ImageFilter.GaussianBlur(30))); im.alpha_composite(pill)
            ImageDraw.Draw(im, "RGBA").text(((W - bw) / 2, 476), badge, font=bfont, fill=(12, 10, 20))
        else:
            nf = font(FB, 160); nw = d.textlength(badge, font=nf)
            text_glow(im, ((W - nw) / 2, 370), badge, nf, ACC + (255,), stroke=5, blur=32, alpha=170)
 
    d = ImageDraw.Draw(im, "RGBA")
    y = 660
    titles = s["title"]
    for k, t in enumerate(titles):
        f = fit(d, t, FB, 112, maxw=960, minsize=72)
        col = ACC + (255,) if (k == len(titles) - 1 and len(titles) > 1) else (255, 255, 255, 255)
        text_glow(im, ((W - d.textlength(t, font=f)) / 2, y), t, f, col, stroke=5, blur=22, alpha=120 if col[:3] != (255, 255, 255) else 70)
        d = ImageDraw.Draw(im, "RGBA"); y += 150
 
    body = s.get("body", [])
    if body:
        y += 46; bh = 84 * len(body) + 70
        card = Image.new("RGBA", (W, H), (0, 0, 0, 0)); cd = ImageDraw.Draw(card)
        cd.rounded_rectangle([84, y, W - 84, y + bh], 42, fill=(10, 10, 18, 150), outline=ACC + (90,), width=3)
        cd.rounded_rectangle([84, y + 30, 93, y + bh - 30], 4, fill=ACC + (255,))
        im.alpha_composite(card); d = ImageDraw.Draw(im, "RGBA")
        ty = y + 35
        for b in body:
            f = fit(d, b, FBold, 52, maxw=820, minsize=42)
            d.text(((W - d.textlength(b, font=f)) / 2, ty), b, font=f, fill=(244, 246, 252, 255), stroke_width=2, stroke_fill=STROKE); ty += 84
 
    if data.get("source"):
        sf = fit(d, data["source"], FM, 34, minsize=28)
        d.text(((W - d.textlength(data["source"], font=sf)) / 2, H - 214), data["source"], font=sf,
               fill=(255, 255, 255, 170), stroke_width=2, stroke_fill=STROKE)
    p = f"{tmp}/s{i}.png"; im.convert("RGB").save(p)
    sec = float(s.get("sec", 4.0)); frames = int(sec * 30); c = f"{tmp}/c{i}.mp4"
    z = "min(zoom+0.0006,1.06)" if zoom_in else "if(eq(on,0),1.06,max(zoom-0.0006,1.0))"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-i", p, "-t", str(sec), "-vf",
        f"scale=1188:2112,zoompan=z='{z}':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={W}x{H}:fps=30,format=yuv420p",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", c], check=True)
    clips.append((c, sec))
 
T = 0.35; inputs, filt, last, off = [], [], "0:v", 0.0
for c, _ in clips: inputs += ["-i", c]
for i in range(1, len(clips)):
    off += clips[i - 1][1] - T
    filt.append(f"[{last}][{i}:v]xfade=transition={trans}:duration={T}:offset={off:.2f}[v{i}]"); last = f"v{i}"
video = f"{tmp}/video.mp4"
subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *inputs, "-filter_complex", ";".join(filt), "-map", f"[{last}]",
    "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", video], check=True)
DUR = sum(s for _, s in clips) - T * (len(clips) - 1)
 
# ---------- 배경음악: 매번 다른 곡 (직접 합성, 저작권 없음) ----------
SR = 44100; mr = np.random.default_rng(VARIANT * 104729 + SALT)
BPMS = [72, 76, 80, 84, 88, 92]  # 조용하고 차분한 템포
bpm = BPMS[(VARIANT + SALT) % len(BPMS)]; beat = 60 / bpm
minor = (VARIANT + SALT // 7) % 2 == 0
scale = [0, 2, 3, 5, 7, 8, 10] if minor else [0, 2, 4, 5, 7, 9, 11]
PROGS = ([[0, 5, 2, 6], [0, 3, 4, 0], [0, 6, 5, 4], [0, 5, 3, 4]] if minor
         else [[0, 4, 5, 3], [5, 3, 0, 4], [0, 3, 5, 4], [0, 5, 3, 4]])
prog = PROGS[int(mr.integers(len(PROGS)))]
root = 45 + int(mr.integers(0, 12))
LEADS = ["sine", "tri", "bell"]; lead = LEADS[(VARIANT + SALT // 3) % len(LEADS)]  # 부드러운 음색만
DRUMS = ["none", "soft"]; drum = DRUMS[(VARIANT * 2 + SALT) % len(DRUMS)]  # 드럼 없음 또는 아주 약하게
ARPS = [[0, 1, 2, 1, 0, 2, 1, 2], [0, 2, 1, 2, 0, 2, 1, 2], [0, 1, 2, 3, 2, 1, 0, 1], [2, 1, 0, 1, 2, 3, 2, 1]]
arp = ARPS[int(mr.integers(len(ARPS)))]
print(f"음악={bpm}BPM {'단조' if minor else '장조'} 리드={lead} 드럼={drum} (잔잔한 버전)")
 
N = int(SR * DUR); out = np.zeros(N); nz = np.random.default_rng(VARIANT)
def add(sig, start):
    s = int(start * SR)
    if 0 <= s < N: n = min(len(sig), N - s); out[s:s+n] += sig[:n]
def hz(m): return 440 * 2 ** ((m - 69) / 12)
def tone(f, length, vol, decay, kind, attack=0.01):
    t = np.arange(int(length * SR)) / SR; ph = t * f
    if kind == "tri": w = 2 * np.abs(2 * (ph % 1) - 1) - 1
    elif kind == "bell": w = np.sin(2 * np.pi * ph) + 0.25 * np.sin(2 * np.pi * ph * 2.01) * np.exp(-t * 6)
    else: w = np.sin(2 * np.pi * ph)
    env = np.minimum(1, t / attack) * np.exp(-t * decay)
    rel = min(len(t), int(0.03 * SR))
    if rel: env[-rel:] *= np.linspace(1, 0, rel)
    return vol * w * env
def chord(deg):
    return [root + 12 + scale[(deg + k) % 7] + 12 * ((deg + k) // 7) for k in (0, 2, 4, 6)]
def kick():
    t = np.arange(int(0.3 * SR)) / SR
    return 0.18 * np.sin(2 * np.pi * (90 * np.exp(-t * 25) + 45) * t) * np.exp(-t * 10)
def shaker():
    t = np.arange(int(0.05 * SR)) / SR
    return 0.012 * nz.standard_normal(len(t)) * np.exp(-t * 60)
 
bar = beat * 4; t = 0.0; i = 0
while t < DUR:
    deg = prog[i % 4]; ch = chord(deg); intro = i == 0
    for k in range(8):  # 8분음표로 느긋하게
        add(tone(hz(ch[arp[k % 8] % 4] + 12), beat * 0.9, 0.04, 3.5, lead), t + k * beat / 2)
    for m in ch[:4]: add(tone(hz(m), bar * 1.1, 0.03, 0.4, "sine", attack=0.4), t)  # 부드러운 패드
    if not intro:
        add(tone(hz(root - 12 + scale[deg]), bar * 0.95, 0.09, 0.8, "sine", attack=0.05), t)  # 낮은 베이스 한 음
    if drum == "soft" and not intro:
        for b in (0, 2): add(kick(), t + b * beat)
        for h in range(8): add(shaker(), t + h * beat / 2)
    t += bar; i += 1
fi, fo = int(0.2 * SR), int(1.2 * SR)
out[:fi] *= np.linspace(0, 1, fi); out[-fo:] *= np.linspace(1, 0, fo)
out = np.convolve(out, np.ones(12) / 12, mode="same"); out = out / np.max(np.abs(out)) * 0.45  # 전체 볼륨 낮춤
pcm = (out * 32767).astype(np.int16); bgm = f"{tmp}/bgm.wav"
with wave.open(bgm, "wb") as w:
    w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR); w.writeframes(np.repeat(pcm[:, None], 2, axis=1).tobytes())
 
final = os.path.join(outdir, f"reel-{date}.mp4")
subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", video, "-i", bgm, "-map", "0:v", "-map", "1:a",
    "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", final], check=True)
open(os.path.join(outdir, "caption.txt"), "w", encoding="utf-8").write(data["caption"])
if not os.environ.get("KEEP_TMP"): shutil.rmtree(tmp)
print(final)
