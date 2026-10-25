"""대본 JSON 하나로 세로 릴스 영상(음악 포함)을 만든다.
사용법: python make_reel.py queue/2026-10-27.json site
결과: site/reel-<date>.mp4, site/caption.txt
"""
import json, os, subprocess, sys, glob
import numpy as np, wave
from PIL import Image, ImageDraw, ImageFont

src, outdir = sys.argv[1], sys.argv[2]
data = json.load(open(src, encoding="utf-8"))
date = data["date"]
os.makedirs(outdir, exist_ok=True)
tmp = os.path.join(outdir, "_tmp"); os.makedirs(tmp, exist_ok=True)

W, H = 1080, 1920
BG = (15, 18, 28); Y = (255, 214, 0); WH = (255, 255, 255); GR = (170, 176, 190)

def find_font(weights):
    for w in weights:
        hits = glob.glob(f"/usr/share/fonts/**/NotoSansCJK-{w}.ttc", recursive=True)
        if hits: return hits[0]
    raise SystemExit("Noto Sans CJK 폰트를 찾을 수 없습니다")
FB = find_font(["Black", "Bold"]); FBold = find_font(["Bold"]); FM = find_font(["Medium", "Regular"])
def font(path, size): return ImageFont.truetype(path, size, index=1)  # index=1: 한국어

def center(d, y, text, f, fill):
    d.text(((W - d.textlength(text, font=f)) / 2, y), text, font=f, fill=fill)

def fit(d, text, path, size, maxw=980):
    f = font(path, size)
    while d.textlength(text, font=f) > maxw and size > 30:
        size -= 4; f = font(path, size)
    return f

# ---------- 장면 이미지 ----------
clips = []
for i, s in enumerate(data["scenes"]):
    im = Image.new("RGB", (W, H), BG); d = ImageDraw.Draw(im)
    d.rectangle([0, 0, W, 14], fill=Y); d.rectangle([0, H - 14, W, H], fill=Y)
    badge = s.get("badge", "")
    if badge:
        if len(badge) > 2:
            bf = font(FB, 64); bw = d.textlength(badge, font=bf)
            d.rounded_rectangle([(W - bw) / 2 - 36, 470, (W + bw) / 2 + 36, 580], 55, fill=Y)
            d.text(((W - bw) / 2, 478), badge, font=bf, fill=BG)
        else:
            center(d, 420, badge, font(FB, 120), Y)
    y = 660
    for t in s["title"]:
        center(d, y, t, fit(d, t, FB, 104), WH); y += 140
    d.rectangle([W / 2 - 60, y + 30, W / 2 + 60, y + 38], fill=Y); y += 100
    for b in s.get("body", []):
        center(d, y, b, fit(d, b, FBold, 52), GR); y += 80
    if data.get("source"):
        center(d, H - 230, data["source"], fit(d, data["source"], FM, 36), (110, 116, 130))
    p = f"{tmp}/s{i}.png"; im.save(p)
    sec = float(s.get("sec", 4.0)); frames = int(sec * 30); c = f"{tmp}/c{i}.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-i", p, "-t", str(sec), "-vf",
        f"scale=1188:2112,zoompan=z='min(zoom+0.0006,1.06)':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={W}x{H}:fps=30,format=yuv420p",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", c], check=True)
    clips.append((c, sec))

T = 0.35; inputs, filt, last, off = [], [], "0:v", 0.0
for c, _ in clips: inputs += ["-i", c]
for i in range(1, len(clips)):
    off += clips[i - 1][1] - T
    filt.append(f"[{last}][{i}:v]xfade=transition=slideleft:duration={T}:offset={off:.2f}[v{i}]"); last = f"v{i}"
video = f"{tmp}/video.mp4"
subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *inputs, "-filter_complex", ";".join(filt), "-map", f"[{last}]",
    "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", video], check=True)
DUR = sum(s for _, s in clips) - T * (len(clips) - 1)

# ---------- 배경음악 (직접 합성, 저작권 없음) ----------
SR = 44100; beat = 60 / 124; N = int(SR * DUR); out = np.zeros(N); rng = np.random.default_rng(1)
def add(sig, start):
    s = int(start * SR)
    if s < N: n = min(len(sig), N - s); out[s:s+n] += sig[:n]
def midi(m): return 440 * 2 ** ((m - 69) / 12)
def saw(f, length, vol, decay):
    t = np.arange(int(length * SR)) / SR
    w = ((2 * ((t * f) % 1) - 1) + (2 * ((t * f * 1.006) % 1) - 1)) * 0.5
    return vol * w * np.minimum(1, t / 0.005) * np.exp(-t * decay)
def kick():
    t = np.arange(int(0.25 * SR)) / SR
    return 0.55 * np.sin(2*np.pi*(150*np.exp(-t*30)+42)*t) * np.exp(-t*12)
def snare():
    t = np.arange(int(0.18 * SR)) / SR
    return 0.22 * (rng.standard_normal(len(t))*np.exp(-t*22) + 0.6*np.sin(2*np.pi*190*t)*np.exp(-t*30))
def hat(v):
    t = np.arange(int(0.035 * SR)) / SR
    return v * rng.standard_normal(len(t)) * np.exp(-t*120)
prog = [[57,60,64],[53,57,60],[48,52,55],[55,59,62]]; bassn = [33,29,36,31]; arp = [0,1,2,1,0,2,1,2]
t = 0.0; i = 0; bar = beat * 4
while t < DUR:
    ch = prog[i % 4]; intro = i == 0
    for k in range(16): add(saw(midi(ch[arp[k % 8]] + 12), beat/4, 0.06, 18), t + k*beat/4)
    if not intro:
        for k in range(8): add(saw(midi(bassn[i % 4]), beat/2, 0.16 if k % 2 == 0 else 0.11, 6), t + k*beat/2)
    for b in range(4):
        if not intro or b >= 2: add(kick(), t + b*beat)
        if not intro and b in (1, 3): add(snare(), t + b*beat)
        for h in range(4): add(hat(0.06 if h == 2 else 0.03), t + b*beat + h*beat/4)
    for m in ch: add(saw(midi(m), 0.3, 0.05, 5), t)
    t += bar; i += 1
fi, fo = int(0.2*SR), int(1.2*SR)
out[:fi] *= np.linspace(0, 1, fi); out[-fo:] *= np.linspace(1, 0, fo)
out = np.convolve(out, np.ones(6)/6, mode="same"); out = np.tanh(out*1.4); out = out/np.max(np.abs(out))*0.85
pcm = (out * 32767).astype(np.int16); bgm = f"{tmp}/bgm.wav"
with wave.open(bgm, "wb") as w:
    w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR); w.writeframes(np.repeat(pcm[:, None], 2, axis=1).tobytes())

final = os.path.join(outdir, f"reel-{date}.mp4")
subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", video, "-i", bgm, "-map", "0:v", "-map", "1:a",
    "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", final], check=True)
open(os.path.join(outdir, "caption.txt"), "w", encoding="utf-8").write(data["caption"])
subprocess.run(["rm", "-rf", tmp])
print(final)
