"""카드뉴스 → 내레이션 영상: python cardvideo.py coupang/cardnews/s001
spec.json의 cards[i].narration 을 읽어 카드마다 음성을 만들고, 9:16 세로 영상(video.mp4)으로 묶는다.
음성: Gemini(자연스러운 목소리) → 한 장이라도 실패하면 전체를 edge-tts로 (목소리 섞이지 않게)."""
import asyncio, base64, json, os, subprocess, sys
import requests
from PIL import Image, ImageFilter, ImageEnhance

W, H, FPS = 1080, 1920, 30
d = [a for a in sys.argv[1:] if not a.startswith("--")][0]; spec = json.load(open(f"{d}/spec.json", encoding="utf-8"))
tmp = f"/tmp/cv-{os.path.basename(d)}"; os.makedirs(tmp, exist_ok=True)
STYLE = ("Read the following Korean text aloud as a bright, high-pitched, energetic young Korean woman hosting a live shopping show. "
         "Excited, upbeat and persuasive, like recommending a must-have item to a close friend; lively fast pace, rising intonation on questions, "
         "strong emphasis on the final call to action. Read only the text: ")


def gemini(text, out):
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key: return False
    for model in ["gemini-2.5-flash-preview-tts", "gemini-2.5-flash-tts", "gemini-2.5-pro-preview-tts"]:
        try:
            r = requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}", timeout=90,
                              json={"contents": [{"parts": [{"text": STYLE + text}]}],
                                    "generationConfig": {"responseModalities": ["AUDIO"],
                                                         "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": spec.get("voice", "Zephyr")}}}}}).json()
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
    asyncio.run(edge_tts.Communicate(text, "ko-KR-SunHiNeural", rate="+18%", pitch="+18Hz").save(mp3))
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", mp3, "-ar", "44100", "-ac", "2", out], check=True)


def dur(p):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nk=1:nw=1", p], capture_output=True, text=True)
    return float(r.stdout.strip())


cards = spec["cards"]; wavs = [f"{tmp}/n{i}.wav" for i in range(len(cards))]
used = "gemini"
# 자연 음성은 영상 1편에 한 번만 부른다(무료 한도 절약). 카드별 길이는 글자 수 비율로 나눈다.
full = f"{tmp}/full.wav"
def silences(p, db=-38, mind=0.25):
    r = subprocess.run(["ffmpeg", "-i", p, "-af", f"silencedetect=n={db}dB:d={mind}", "-f", "null", "-"], capture_output=True, text=True).stderr
    st = [float(x.split("silence_start: ")[1].split()[0]) for x in r.splitlines() if "silence_start" in x]
    en = [float(x.split("silence_end: ")[1].split()[0]) for x in r.splitlines() if "silence_end" in x]
    if len(st) > len(en): en.append(dur(p))  # 끝까지 무음이면 끝 표시가 없다
    return list(zip(st, en))


def split_at_pauses(full, n, lens):
    """카드 경계를 문장 사이 쉼(무음) 한가운데에서 자른다 → 말이 중간에 잘리지 않는다"""
    total = dur(full)
    for mind in (0.25, 0.12):
        r = _split(full, n, lens, total, mind)
        if r: return r
    return None


def _split(full, n, lens, total, mind):
    sil = [(a, b) for a, b in silences(full, -38, mind) if 0.3 < a and b < total - 0.2]
    cuts, used_ = [], set(); acc = 0
    for k in range(n - 1):
        acc += lens[k]; exp = total * acc / sum(lens)
        cand = [(abs((a + b) / 2 - exp) - 1.5 * (b - a), j) for j, (a, b) in enumerate(sil) if j not in used_ and abs((a + b) / 2 - exp) < total * 0.22]
        if not cand: return None
        j = min(cand)[1]; used_.add(j); cuts.append((sil[j][0] + sil[j][1]) / 2)
    cuts = sorted(cuts)
    return [0.0] + cuts + [total]


ok_split = False
if gemini(" ... ".join(c["narration"] for c in cards), full):
    b = split_at_pauses(full, len(cards), [len(c["narration"]) for c in cards])
    if b:
        for i in range(len(cards)):
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", full, "-ss", f"{b[i]:.3f}", "-to", f"{b[i + 1]:.3f}",
                            "-af", "silenceremove=start_periods=1:start_threshold=-45dB,areverse,silenceremove=start_periods=1:start_threshold=-45dB,areverse,apad=pad_dur=0.05", wavs[i]], check=True)
        ok_split = True
    else: print("::notice::문장 쉼을 못 찾음 → 카드별 기본 음성")
if not ok_split:
    used = "edge"
if used == "edge" and "--gemini-only" in sys.argv and not os.path.exists(full):
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
    segs.append({"states": states, "starts": starts, "bg": bg, "subs": subs, "sec": dur(wavs[i]) + (0.7 if i == 0 else 0.45) + (1.2 if i == len(cards) - 1 else 0)})
total_sec = sum(g["sec"] for g in segs)


def card_at(g, tl):
    """tl초 시점의 카드(줄 나타남은 0.25초 페이드) + 천천히 확대"""
    r = tl / g["sec"]; k = max(j for j, s0 in enumerate(g["starts"]) if r >= s0)
    im = g["states"][k]
    if k > 0:
        a = min(1, (r - g["starts"][k]) * g["sec"] / 0.25)
        if a < 1: im = Image.blend(g["states"][k - 1], im, a)
    z = 1 + 0.045 * (r * r * (3 - 2 * r))  # 부드러운 가속·감속 확대(소수점 단위라 떨림 없음)
    return im.transform((1080, 1350), Image.AFFINE, (1 / z, 0, 540 - 540 / z, 0, 1 / z, 675 - 675 / z), Image.BICUBIC)


def frame(gi, tl, t_all):
    g = segs[gi]; fr = g["bg"].copy()
    cd = card_at(g, tl)
    if gi > 0 and tl < 0.35:  # 다음 카드가 오른쪽에서 밀고 들어옴
        e = 1 - (1 - tl / 0.35) ** 3; prev = card_at(segs[gi - 1], segs[gi - 1]["sec"] - 0.01)
        fr.paste(prev, (int(-W * e), CY)); fr.paste(cd, (int(W * (1 - e)), CY))
    else: fr.paste(cd, (0, CY))
    dr = ImageDraw.Draw(fr)
    if gi == len(segs) - 1 and tl > 0.6:  # 마지막 장: 링크 누르라는 깜빡이는 버튼
        import math
        sc = 1 + 0.06 * math.sin(tl * 7); txt = "지금 링크 눌러서 확인 ›"; fb = CN.font("Black", int(50 * sc))
        tw = dr.textlength(txt, font=fb); bh = 50 * sc + 44; y0 = CY + 1100 - bh / 2
        dr.rounded_rectangle([(W - tw) / 2 - 44, y0, (W + tw) / 2 + 44, y0 + bh], int(bh / 2), fill=(255, 214, 0))
        dr.text(((W - tw) / 2, y0 + 16), txt, font=fb, fill=(20, 20, 20))
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
# 배경음악: 부드러운 곡을 영상마다 돌아가며 (목소리가 나올 땐 자동으로 작아짐)
import glob as _g, bgm as _bgm
qdir = os.path.dirname(os.path.abspath(d).rstrip("/"))
idx = spec.get("bgm_idx")
if idx is None:
    idx = sum(1 for f in _g.glob(f"{qdir}/*/spec.json") if json.load(open(f)).get("status") in ("posted", "ready"))
song = _bgm.make(f"{tmp}/bgm.wav", t, idx); ain += ["-i", f"{tmp}/bgm.wav"]; nb = len(segs) + 1
af.append("".join(f"[a{k}]" for k in range(len(segs))) + f"amix=inputs={len(segs)}:normalize=0,asplit=2[v1][v2]")
af.append(f"[{nb}:a]volume=0.20[bg]")
af.append("[bg][v2]sidechaincompress=threshold=0.02:ratio=5:attack=30:release=500[bgd]")
af.append("[v1][bgd]amix=inputs=2:normalize=0,loudnorm=I=-15:TP=-1.5,apad[a]")
print("배경음악:", song)
subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", f"{tmp}/video.mp4", *ain, "-filter_complex", ";".join(af),
                "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-t", f"{t:.3f}", f"{d}/video.mp4"], check=True)
# 검수: 음성이 끝까지 들어갔는지, 영상 길이·프레임이 맞는지
need = sum(dur(w) for w in wavs); vd = dur(f"{d}/video.mp4")
fr = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries", "stream=nb_read_frames", "-of", "csv=p=0", f"{d}/video.mp4"], capture_output=True, text=True).stdout.strip()
last_start = sum(g["sec"] for g in segs[:-1]) + (0.5 if len(segs) == 1 else 0.25)
end_silent = vd - (last_start + dur(wavs[-1])) >= 0.5  # 마지막 말이 끝나고 0.5초 이상 여유
if vd < need + 0.5 or not end_silent or abs(int(fr or 0) - vd * FPS) > FPS:
    print(f"::error::영상 검수 실패: 길이 {vd:.1f}s / 음성 {need:.1f}s / 끝 무음 {end_silent} / 프레임 {fr}"); os.remove(f"{d}/video.mp4"); sys.exit(3)
print(f"완성: {d}/video.mp4 ({dur(f'{d}/video.mp4'):.1f}초, 음성: {used})")
