"""카드뉴스 → 내레이션 영상: python cardvideo.py coupang/cardnews/s001
spec.json의 cards[i].narration 을 읽어 카드마다 음성을 만들고, 9:16 세로 영상(video.mp4)으로 묶는다.
음성: Gemini(자연스러운 목소리) → 한 장이라도 실패하면 전체를 edge-tts로 (목소리 섞이지 않게)."""
import asyncio, base64, json, os, subprocess, sys
import requests
from PIL import Image, ImageFilter, ImageEnhance

W, H, FPS = 1080, 1920, 30
d = [a for a in sys.argv[1:] if not a.startswith("--")][0]; spec = json.load(open(f"{d}/spec.json", encoding="utf-8"))
tmp = f"/tmp/cv-{os.path.basename(d)}"; os.makedirs(tmp, exist_ok=True)
STYLE = ("Read the following Korean text aloud in a warm, calm, friendly female voice, like a kind health-information host "
         "explaining to a friend. Natural pace, clear pronunciation, gentle smile in the voice. Read only the text: ")


def gemini(text, out):
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key: return False
    for model in ["gemini-2.5-flash-preview-tts", "gemini-2.5-flash-tts", "gemini-2.5-pro-preview-tts"]:
        try:
            r = requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}", timeout=90,
                              json={"contents": [{"parts": [{"text": STYLE + text}]}],
                                    "generationConfig": {"responseModalities": ["AUDIO"],
                                                         "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": spec.get("voice", "Aoede")}}}}}).json()
            raw = base64.b64decode(r["candidates"][0]["content"]["parts"][0]["inlineData"]["data"])
            if len(raw) / 48000 > len(text) * 0.24 + 2: print("::notice::지시문까지 읽은 듯 → 다른 모델"); continue
            open(out + ".pcm", "wb").write(raw)
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "s16le", "-ar", "24000", "-ac", "1", "-i", out + ".pcm",
                            "-af", "silenceremove=start_periods=1:start_threshold=-45dB,areverse,silenceremove=start_periods=1:start_threshold=-45dB,areverse",
                            "-ar", "44100", "-ac", "2", out], check=True)
            return True
        except Exception:
            print("::notice::Gemini 음성 실패", model, str(r.get("error", ""))[:160] if isinstance(r, dict) else "")
    return False


def edge(text, out):
    if os.environ.get("CV_SILENT"):  # 시험용: 음성 대신 무음
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo", "-t", f"{len(text) * 0.17:.2f}", out], check=True); return
    import edge_tts
    mp3 = out + ".mp3"
    asyncio.run(edge_tts.Communicate(text, "ko-KR-SunHiNeural", rate="+12%").save(mp3))
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", mp3, "-ar", "44100", "-ac", "2", out], check=True)


def dur(p):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nk=1:nw=1", p], capture_output=True, text=True)
    return float(r.stdout.strip())


cards = spec["cards"]; wavs = [f"{tmp}/n{i}.wav" for i in range(len(cards))]
used = "gemini"
# 자연 음성은 영상 1편에 한 번만 부른다(무료 한도 절약). 카드별 길이는 글자 수 비율로 나눈다.
full = f"{tmp}/full.wav"
if gemini(" ... ".join(c["narration"] for c in cards), full):
    total = dur(full); lens = [len(c["narration"]) for c in cards]; t0 = 0.0
    for i, c in enumerate(cards):
        seg = total * lens[i] / sum(lens)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", full, "-ss", f"{t0:.3f}", "-t", f"{seg:.3f}", wavs[i]], check=True)
        t0 += seg
else:
    used = "edge"
if used == "edge" and "--gemini-only" in sys.argv:
    print("::notice::자연 음성 한도 초과 → 영상 만들지 않음"); sys.exit(2)
if used == "edge":
    print("::notice::자연 음성 한도 초과 → 전체 기본 음성으로")
    for i, c in enumerate(cards): edge(c["narration"], wavs[i])

# 화면: 움직이는 세로 영상 — 카드가 천천히 다가오고, 본문이 한 줄씩 나타나고, 자막이 목소리에 맞춰 바뀐다.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cardnews as CN
from PIL import ImageDraw
base = os.path.abspath(d); n = len(cards); acc = CN.hexc(spec.get("accent", "#B3261E"))
CY = (H - 1350) // 2  # 카드 위치(가운데)
fsub = CN.font("Black", 56); ftop = CN.font("Bold", 40); fsm = CN.font("Medium", 30)


def chunks(text):
    """자막을 12~16자 단위로 자른다 (어절 기준)"""
    out, cur = [], ""
    for w in text.replace("...", " ").split():
        if len(cur) + len(w) + 1 > 15 and cur: out.append(cur); cur = w
        else: cur = (cur + " " + w).strip()
    if cur: out.append(cur)
    return out


segs = []  # 카드별: 상태 이미지들, 각 상태 시작시각(비율), 배경, 자막(시작비율, 글)
for i, c in enumerate(cards):
    states = []
    if c["type"] == "text" and c.get("body"):
        for k in range(len(c["body"]) + 1):
            cc = dict(c, body=c["body"][:k]);
            if k < len(c["body"]): cc.pop("source", None)
            states.append(CN.card(cc, i + 1, n, spec, base))
        starts = [0] + [0.18 + 0.75 * k / len(c["body"]) for k in range(len(c["body"]))]
    else:
        states = [CN.card(c, i + 1, n, spec, base)]; starts = [0]
    bg = states[-1].resize((W, int(1350 * W / 1080))).resize((W, H)).filter(ImageFilter.GaussianBlur(45))
    bg = ImageEnhance.Brightness(bg).enhance(0.42)
    ch = chunks(c["narration"]); tot = sum(len(x) for x in ch); acc_t = 0; subs = []
    for x in ch: subs.append((acc_t / tot, x)); acc_t += len(x)
    segs.append({"states": states, "starts": starts, "bg": bg, "subs": subs, "sec": dur(wavs[i]) + (0.7 if i == 0 else 0.45)})
total_sec = sum(g["sec"] for g in segs)


def card_at(g, tl):
    """tl초 시점의 카드(줄 나타남은 0.25초 페이드) + 천천히 확대"""
    r = tl / g["sec"]; k = max(j for j, s0 in enumerate(g["starts"]) if r >= s0)
    im = g["states"][k]
    if k > 0:
        a = min(1, (r - g["starts"][k]) * g["sec"] / 0.25)
        if a < 1: im = Image.blend(g["states"][k - 1], im, a)
    z = 1 + 0.05 * r
    big = im.resize((int(1080 * z), int(1350 * z)), Image.BILINEAR)
    ox, oy = (big.width - 1080) // 2, (big.height - 1350) // 2
    return big.crop((ox, oy, ox + 1080, oy + 1350))


def frame(gi, tl, t_all):
    g = segs[gi]; fr = g["bg"].copy()
    cd = card_at(g, tl)
    if gi > 0 and tl < 0.35:  # 다음 카드가 오른쪽에서 밀고 들어옴
        e = 1 - (1 - tl / 0.35) ** 3; prev = card_at(segs[gi - 1], segs[gi - 1]["sec"] - 0.01)
        fr.paste(prev, (int(-W * e), CY)); fr.paste(cd, (int(W * (1 - e)), CY))
    else: fr.paste(cd, (0, CY))
    dr = ImageDraw.Draw(fr)
    # 위: 주제 + 진행 막대
    topic = spec.get("topic", "")
    dr.text(((W - dr.textlength(topic, font=ftop)) / 2, CY - 120), topic, font=ftop, fill=(255, 255, 255))
    dr.rounded_rectangle([60, CY - 40, W - 60, CY - 30], 5, fill=(255, 255, 255, 60) if False else (90, 80, 74))
    dr.rounded_rectangle([60, CY - 40, 60 + int((W - 120) * t_all / total_sec), CY - 30], 5, fill=acc)
    # 아래: 목소리 자막 (말 시작 0.25초 뒤부터)
    r = max(0, tl - (0.5 if gi == 0 else 0.25)) / max(0.1, g["sec"] - 0.6)
    cur = [x for s0, x in g["subs"] if r >= s0][-1]
    tw = dr.textlength(cur, font=fsub); y = CY + 1350 + 70
    dr.rounded_rectangle([(W - tw) / 2 - 30, y - 18, (W + tw) / 2 + 30, y + 80], 22, fill=(0, 0, 0))
    dr.text(((W - tw) / 2, y), cur, font=fsub, fill=(255, 225, 90))
    return fr


enc = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
                        "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-pix_fmt", "yuv420p", f"{tmp}/video.mp4"], stdin=subprocess.PIPE)
t_all = 0.0
for gi, g in enumerate(segs):
    for f in range(int(g["sec"] * FPS)):
        tl = f / FPS; enc.stdin.write(frame(gi, tl, t_all + tl).tobytes())
    t_all += g["sec"]
enc.stdin.close(); enc.wait()

# 음성: 카드 시작 + 0.25초(첫 카드 0.5초)
ain, af, t = [], [], 0.0
for k, g in enumerate(segs):
    st = t + (0.5 if k == 0 else 0.25); ain += ["-i", wavs[k]]
    af.append(f"[{k + 1}:a]adelay={int(st * 1000)}|{int(st * 1000)}[a{k}]"); t += g["sec"]
af.append("".join(f"[a{k}]" for k in range(len(segs))) + f"amix=inputs={len(segs)}:normalize=0,loudnorm=I=-15:TP=-1.5[a]")
subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", f"{tmp}/video.mp4", *ain, "-filter_complex", ";".join(af),
                "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-shortest", f"{d}/video.mp4"], check=True)
print(f"완성: {d}/video.mp4 ({dur(f'{d}/video.mp4'):.1f}초, 음성: {used})")
