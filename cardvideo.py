"""카드뉴스 → 내레이션 영상: python cardvideo.py coupang/cardnews/s001
spec.json의 cards[i].narration 을 읽어 카드마다 음성을 만들고, 9:16 세로 영상(video.mp4)으로 묶는다.
음성: Gemini(자연스러운 목소리) → 한 장이라도 실패하면 전체를 edge-tts로 (목소리 섞이지 않게)."""
import asyncio, base64, json, os, subprocess, sys
import requests
from PIL import Image, ImageFilter, ImageEnhance

W, H, FPS = 1080, 1920, 30
d = sys.argv[1]; spec = json.load(open(f"{d}/spec.json", encoding="utf-8"))
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
    import edge_tts
    mp3 = out + ".mp3"
    asyncio.run(edge_tts.Communicate(text, "ko-KR-SunHiNeural", rate="+4%").save(mp3))
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", mp3, "-ar", "44100", "-ac", "2", out], check=True)


def dur(p):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nk=1:nw=1", p], capture_output=True, text=True)
    return float(r.stdout.strip())


cards = spec["cards"]; wavs = [f"{tmp}/n{i}.wav" for i in range(len(cards))]
used = "gemini"
for i, c in enumerate(cards):
    if not gemini(c["narration"], wavs[i]): used = "edge"; break
if used == "edge":
    print("::notice::자연 음성 한도 초과 → 전체 기본 음성으로")
    for i, c in enumerate(cards): edge(c["narration"], wavs[i])

# 화면: 흐린 배경 + 가운데 카드(4:5), 카드마다 살짝 줌
clips = []
for i, c in enumerate(cards):
    card = Image.open(f"{d}/cards/{i + 1:02d}.jpg").convert("RGB")
    bg = card.resize((W, int(card.height * W / card.width))).resize((W, H)).filter(ImageFilter.GaussianBlur(40))
    bg = ImageEnhance.Brightness(bg).enhance(0.55); bg.save(f"{tmp}/bg{i}.jpg")
    card.save(f"{tmp}/c{i}.png")
    sec = dur(wavs[i]) + (0.9 if i == 0 else 0.6)
    n = int(sec * FPS); out = f"{tmp}/v{i}.mp4"
    z = f"min(1+on*0.00025,1.04)" if i % 2 == 0 else f"max(1.04-on*0.00025,1)"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-i", f"{tmp}/bg{i}.jpg", "-loop", "1", "-i", f"{tmp}/c{i}.png",
                    "-filter_complex",
                    f"[1:v]scale=2160:-1,zoompan=z='{z}':d={n}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1080x1350:fps={FPS}[cz];"
                    f"[0:v]fps={FPS}[b];[b][cz]overlay=0:{(H - 1350) // 2}:shortest=1,format=yuv420p[v]",
                    "-map", "[v]", "-t", f"{sec:.2f}", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-r", str(FPS), out], check=True)
    clips.append((out, sec))

# 화면 이어 붙이기(0.3초 페이드) + 음성 이어 붙이기
T = 0.3; inputs = []; fc = []; off = 0; prev = "0:v"
for k, (p, s) in enumerate(clips): inputs += ["-i", p]
for k in range(1, len(clips)):
    off += clips[k - 1][1] - T
    fc.append(f"[{prev}][{k}:v]xfade=transition=fade:duration={T}:offset={off:.2f}[x{k}]"); prev = f"x{k}"
subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *inputs, "-filter_complex", ";".join(fc), "-map", f"[{prev}]",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", f"{tmp}/video.mp4"], check=True)
alist = []; t = 0.0
for k, (p, s) in enumerate(clips):
    start = t + (0.5 if k == 0 else 0.25); alist.append((wavs[k], start)); t += s - T
ain = []; af = []
for k, (w, st) in enumerate(alist):
    ain += ["-i", w]; af.append(f"[{k}:a]adelay={int(st * 1000)}|{int(st * 1000)}[a{k}]")
af.append("".join(f"[a{k}]" for k in range(len(alist))) + f"amix=inputs={len(alist)}:normalize=0,loudnorm=I=-15:TP=-1.5[a]")
subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", f"{tmp}/video.mp4", *ain, "-filter_complex",
                ";".join(f.replace(f"[{k}:a]", f"[{k + 1}:a]") for k, f in enumerate(af[:-1])) + ";" +
                "".join(f"[a{k}]" for k in range(len(alist))) + f"amix=inputs={len(alist)}:normalize=0,loudnorm=I=-15:TP=-1.5[a]",
                "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-shortest", f"{d}/video.mp4"], check=True)
print(f"완성: {d}/video.mp4 ({dur(f'{d}/video.mp4'):.1f}초, 음성: {used})")
