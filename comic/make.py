"""대기열(comic/queue.json)에서 다음 CC-BY 영상 1편을 골라 한국어 코믹 쇼츠로 만든다.
1) yt-dlp로 원본 받기  2) Gemini가 영상을 보고 웃음 포인트 3~5장면 + 반말 리액션 멘트(JSON)
3) Gemini TTS로 장면별 더빙  4) 1080x1920 세로 화면 + 큰 자막 + 효과음 + 출처 표기  → comic/work/final.mp4, comic/work/meta.json
사용법: GEMINI_API_KEY=... python comic/make.py      (GitHub Actions에서 실행)
"""
import base64, json, os, re, subprocess, sys, time, functools
import requests
from PIL import Image, ImageDraw, ImageFont
print = functools.partial(print, flush=True)

Q, WD = "comic/queue.json", "comic/work"
KEY = os.environ.get("GEMINI_API_KEY", "").strip()
G = "https://generativelanguage.googleapis.com"
FONT = next((p for p in ["/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc", "/usr/share/fonts/noto-cjk/NotoSansCJK-Bold.ttc"] if os.path.exists(p)), None)
W, H, TOP, VID = 1080, 1920, 420, 1150
YEL = (255, 214, 0)
VOICE = os.environ.get("COMIC_VOICE", "Puck")
ORIG_VOL = float(os.environ.get("ORIG_VOL", "0.2"))  # 원본 현장음(웃음소리 등) 작게 깔기


def sh(*a, **k): return subprocess.run(list(a), check=True, **k)
def dur(p): return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", p], capture_output=True, text=True).stdout.strip())
def font(s): return ImageFont.truetype(FONT, s, index=1)  # index 1 = 한국어


def save_q(q): json.dump(q, open(Q, "w", encoding="utf-8"), ensure_ascii=False, indent=0)


def fix_cookies(path="cookies.txt"):
    """깃허브 비밀값에 붙여넣으며 탭이 공백으로 바뀌거나 JSON 형식이어도 yt-dlp용(Netscape) 형식으로 고친다"""
    if not os.path.exists(path): return
    raw = open(path, encoding="utf-8", errors="ignore").read().strip()
    rows = []
    if raw.startswith("["):  # JSON 형식 쿠키
        for c in json.loads(raw):
            d = c.get("domain", ""); exp = int(c.get("expirationDate", c.get("expires", 0)) or 0)
            rows.append([d, "TRUE" if d.startswith(".") else "FALSE", c.get("path", "/"), "TRUE" if c.get("secure") else "FALSE", str(exp), c.get("name", ""), c.get("value", "")])
    else:
        for ln in raw.replace("\r", "").split("\n"):
            ln = ln.strip()
            if not ln or (ln.startswith("#") and not ln.startswith("#HttpOnly_")): continue
            f = ln.split("\t") if "\t" in ln else ln.split(None, 6)
            if len(f) == 6: f.append("")
            if len(f) == 7: rows.append(f)
    open(path, "w", encoding="utf-8").write("# Netscape HTTP Cookie File\n" + "".join("\t".join(r) + "\n" for r in rows))
    print(f"쿠키 {len(rows)}개 정리 완료")


def download_any(it):
    """Commons 등 직접 주소가 있으면 그대로 받고 mp4로 변환, 없으면 유튜브(yt-dlp)"""
    if not it.get("url"): return download(it["id"])
    raw, out = f"{WD}/raw", f"{WD}/src.mp4"
    base = it["url"].split("?")[0]; fn = base.rsplit("/", 1)[1]
    tr = base.replace("/wikipedia/commons/", "/wikipedia/commons/transcoded/", 1) + "/" + fn
    urls = [tr + ".720p.vp9.webm", tr + ".480p.vp9.webm", base]  # 가벼운 변환본부터 (원본은 마지막)
    ua = {"User-Agent": "ComicShortsBot/1.0 (https://github.com/MoneyInsight/insta-reels; reel-bot@users.noreply.github.com) python-requests"}
    try:
        ok = False
        for u in urls:
            for t in range(3):
                r = requests.get(u, stream=True, timeout=120, headers=ua)
                if r.status_code == 429: time.sleep(20 * (t + 1)); continue
                if r.status_code != 200: break
                with open(raw, "wb") as f:
                    for ch in r.iter_content(1 << 20): f.write(ch)
                ok = True; break
            if ok: break
        if not ok: raise RuntimeError(f"받기 실패 (마지막 상태 {r.status_code})")
        sh("ffmpeg", "-v", "error", "-y", "-i", raw, "-t", "600", "-vf", "scale=-2:'min(1080,ih)'", "-c:v", "libx264", "-preset", "veryfast",
           "-crf", "20", "-c:a", "aac", "-b:a", "128k", out)
        return out
    except Exception as e:
        print("::warning::다운로드 실패", it["id"], str(e)[:200]); return None


def download(vid):
    out = f"{WD}/src.mp4"
    cmd = ["yt-dlp", "-q", "--no-playlist", "--max-filesize", "400M", "-f", "bv*[height<=1080][ext=mp4]+ba[ext=m4a]/b[height<=1080]/b",
           "--merge-output-format", "mp4", "-o", out, f"https://www.youtube.com/watch?v={vid}"]
    if os.path.exists("cookies.txt"): fix_cookies(); cmd[1:1] = ["--cookies", "cookies.txt"]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode or not os.path.exists(out): print("::warning::다운로드 실패", vid, r.stderr[-300:]); return None
    return out


def gemini_upload(path):
    size = os.path.getsize(path)
    r = requests.post(f"{G}/upload/v1beta/files?key={KEY}", headers={"X-Goog-Upload-Protocol": "resumable", "X-Goog-Upload-Command": "start",
                      "X-Goog-Upload-Header-Content-Length": str(size), "X-Goog-Upload-Header-Content-Type": "video/mp4",
                      "Content-Type": "application/json"}, json={"file": {"display_name": os.path.basename(path)}}, timeout=60)
    url = r.headers["x-goog-upload-url"]
    f = requests.post(url, headers={"X-Goog-Upload-Offset": "0", "X-Goog-Upload-Command": "upload, finalize"}, data=open(path, "rb"), timeout=600).json()["file"]
    for _ in range(60):
        if f.get("state") == "ACTIVE": return f
        time.sleep(5); f = requests.get(f"{G}/v1beta/{f['name']}?key={KEY}", timeout=30).json()
    raise RuntimeError("Gemini 영상 처리 시간 초과")


PROMPT = """너는 조회수 수백만을 찍는 한국 유튜브 쇼츠 편집자야. 이 영상(원제: "{title}")을 보고 한국 시청자가 빵 터지거나 울컥할 장면만 골라 25~35초짜리 쇼츠 대본을 짜.
규칙:
- 영상에서 가장 웃기거나(사고·반전·표정) 감동적인 순간 3~5개. 첫 장면은 무조건 제일 강한 순간(첫 1초에 시선 강탈).
- 각 장면 길이 4~9초, start/end는 원본 영상의 초 단위(소수 1자리). 장면끼리 겹치지 않게, 시간 순서 상관없음.
- narration: 친구한테 말하듯 신난 반말 리액션("야 이거 봐 ㅋㅋㅋ", "잠깐만 표정 봐"), 장면 길이 1초당 한국어 6글자 이하. 사실과 다른 내용 금지.
- caption: 화면 자막 1~2줄(줄바꿈 \\n), 줄당 14자 이하, 핵심 단어 하나를 highlight로.
- 마지막 장면 narration은 "너도 이런 친구 있지? 태그해!"처럼 댓글·공유 유도로 끝내.
- 사람을 비하·조롱하거나 다치는 장면을 웃음거리로 삼지 마. 정치·폭력·선정·위험 행동이거나, 노래 공연/뮤직비디오 위주라 웃음·감동 포인트가 없으면 {{"skip": true, "reason": "..."}} 만 반환.
JSON만 반환:
{{"top1": "상단 제목 1줄(12자 이하)", "top2": "상단 제목 2줄(노란색, 12자 이하)", "yt_title": "유튜브 제목(후킹, 40자 이하, 이모지 1개까지)",
  "hashtags": ["...6개"], "mood": "funny 또는 touching",
  "sns_text": "스레드·인스타용 본문 3~4줄(반말 리액션 + 마지막 줄은 영상 속 상황과 자연스럽게 이어지는 상품 추천 한 줄)",
  "product_keyword": "영상과 자연스럽게 연결되는 쿠팡 검색어 1개(예: 고양이 장난감, 강아지 간식, 아기 턱받이, 캠핑 의자)",
  "product_must": "상품명에 꼭 들어가야 할 단어 1개", "product_label": "상품 짧은 이름(12자 이하)",
  "scenes": [{{"start": 0.0, "end": 0.0, "narration": "...", "caption": "...", "highlight": "..."}}]}}"""


def plan(src, title):
    f = gemini_upload(src)
    for model in ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.0-flash"]:
        r = requests.post(f"{G}/v1beta/models/{model}:generateContent?key={KEY}", timeout=300, json={
            "contents": [{"parts": [{"file_data": {"mime_type": "video/mp4", "file_uri": f["uri"]}}, {"text": PROMPT.format(title=title)}]}],
            "generationConfig": {"responseMimeType": "application/json", "temperature": 0.9}}).json()
        try:
            txt = r["candidates"][0]["content"]["parts"][0]["text"]
            return json.loads(re.sub(r"^```json|```$", "", txt.strip()))
        except Exception:
            print("::notice::대본 생성 실패", model, str(r.get("error", ""))[:200])
    return None


TTS_STYLE = ("Read this Korean line as a fast, high-energy young Korean guy reacting to a hilarious viral video with his best friend: "
             "casual, laughing, exaggerated surprise, great comic timing. If the mood is touching, be warm and moved instead. Read only the text: ")


def tts(text, out, mood):
    style = TTS_STYLE if mood != "touching" else "Read this Korean line warmly and softly, genuinely moved, like telling a friend a touching story. Read only the text: "
    for model in ["gemini-2.5-flash-preview-tts", "gemini-2.5-flash-tts", "gemini-2.5-pro-preview-tts"]:
        try:
            r = requests.post(f"{G}/v1beta/models/{model}:generateContent?key={KEY}", timeout=120, json={
                "contents": [{"parts": [{"text": style + text}]}],
                "generationConfig": {"responseModalities": ["AUDIO"], "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": VOICE}}}}}).json()
            raw = base64.b64decode(r["candidates"][0]["content"]["parts"][0]["inlineData"]["data"])
            if len(raw) / 48000 > len(text) * 0.3 + 2: continue  # 지시문까지 읽은 경우
            open(out + ".pcm", "wb").write(raw)
            sh("ffmpeg", "-y", "-v", "error", "-f", "s16le", "-ar", "24000", "-ac", "1", "-i", out + ".pcm", "-af",
               "silenceremove=start_periods=1:start_threshold=-45dB,areverse,silenceremove=start_periods=1:start_threshold=-45dB,areverse",
               "-ar", "44100", "-ac", "1", out)
            return True
        except Exception:
            print("::notice::음성 실패", model, str(r.get("error", ""))[:160] if isinstance(r, dict) else "")
            time.sleep(8)
    return False


def overlay(i, top1, top2, cap, hl, credit):
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    d.rectangle([0, 0, W, TOP], fill="black"); d.rectangle([0, TOP + VID, W, H], fill="black")
    d.text((W / 2, 170), top1, font=font(88), fill="white", anchor="mm")
    d.text((W / 2, 295), top2, font=font(100), fill=YEL, anchor="mm")
    f = font(80); lines = [l for l in cap.split("\n") if l.strip()][:2]; y = 1330 - (len(lines) - 1) * 52
    for ln in lines:
        while d.textlength(ln, font=f) > W - 60 and f.size > 50: f = font(f.size - 4)
        segs = [(ln, "white")]
        if hl and hl in ln: a, b = ln.split(hl, 1); segs = [(a, "white"), (hl, YEL), (b, "white")]
        x = W / 2 - d.textlength(ln, font=f) / 2
        for t, c in segs:
            if t: d.text((x, y), t, font=f, fill=c, anchor="lm", stroke_width=9, stroke_fill="black"); x += d.textlength(t, font=f)
        y += 104
    d.text((W / 2, 1700), "끝까지 보면 웃음 보장" if i == 0 else "", font=font(46), fill=(200, 200, 200), anchor="mm")
    cf = font(30)
    while d.textlength(credit, font=cf) > W - 40 and cf.size > 18: cf = font(cf.size - 2)
    d.text((W / 2, 1860), credit, font=cf, fill=(150, 150, 150), anchor="mm")
    p = f"{WD}/ov{i}.png"; im.save(p); return p


def render(src, p, item):
    total = dur(src); credit = f"원본: {item['channel']} / " + ("Wikimedia Commons (" + item.get("license", "CC BY") + ")" if item.get("src") == "commons" else "YouTube (CC BY)")
    vids, auds, cuts, t = [], [], [], 0.0
    for i, s in enumerate(p["scenes"][:5]):
        st = max(0.0, float(s["start"])); en = min(total, float(s["end"]))
        if en - st < 2: continue
        a = f"{WD}/n{i}.wav"
        if not tts(s["narration"], a, p.get("mood")): raise RuntimeError("음성 생성 실패")
        ad = dur(a); d = max(en - st, ad + 0.35)
        if st + d > total: st = max(0.0, total - d)
        d = min(d, total - st)
        tempo = min(1.3, (ad + 0.2) / d) if ad + 0.2 > d else 1.0
        ov = overlay(len(vids), p.get("top1", "")[:14], p.get("top2", "")[:14], s.get("caption", ""), s.get("highlight", ""), credit)
        out = f"{WD}/s{i}.mp4"
        zoom = "" if i % 2 else ",zoompan=z='min(1+on/450,1.12)':d=1:s=1080x1150:fps=30"  # 번갈아 살짝 줌인
        vf = (f"[0:v]fps=30,scale=1080:1150:force_original_aspect_ratio=increase,crop=1080:1150{zoom},setsar=1[v];"
              f"color=black:s={W}x{H}:r=30[bg];[bg][v]overlay=0:{TOP}:shortest=1[b];[b][1:v]overlay=0:0,format=yuv420p[vo];"
              f"[0:a]aformat=sample_rates=44100:channel_layouts=mono,volume={ORIG_VOL}[o];"
              f"[2:a]atempo={tempo:.3f},apad,aformat=sample_rates=44100:channel_layouts=mono,volume=1.2[n];"
              f"[o][n]amix=inputs=2:duration=first:normalize=0[ao]")
        has_a = "audio" in subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-of", "csv=p=0", "-show_entries", "stream=codec_type", src], capture_output=True, text=True).stdout
        inputs = ["-ss", f"{st:.2f}", "-t", f"{d:.2f}", "-i", src, "-i", ov, "-i", a]
        if not has_a:
            inputs = ["-ss", f"{st:.2f}", "-t", f"{d:.2f}", "-i", src, "-i", ov, "-i", a, "-f", "lavfi", "-t", f"{d:.2f}", "-i", "anullsrc=r=44100:cl=mono"]
            vf = vf.replace("[0:a]", "[3:a]")
        sh("ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", vf, "-map", "[vo]", "-map", "[ao]", "-t", f"{d:.2f}",
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-r", "30", "-c:a", "aac", "-ar", "44100", "-ac", "1", "-b:a", "128k", out + ".tmp.mp4")
        os.replace(out + ".tmp.mp4", out); vids.append(out); t += d; cuts.append(t)
    if len(vids) < 2 or t < 12: raise RuntimeError("쓸 장면이 부족함")
    open(f"{WD}/list.txt", "w").write("".join(f"file '{os.path.basename(v)}'\n" for v in vids))
    sh("ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", f"{WD}/list.txt", "-c", "copy", f"{WD}/joined.mp4")
    # 장면 전환마다 '뿅' 효과음
    cuts = cuts[:-1]
    sfx = "".join(f"aevalsrc='0.35*sin(2*PI*(600+2500*t)*t)*exp(-14*t)':d=0.25:s=44100,adelay={int(c*1000)},aformat=channel_layouts=mono[s{k}];" for k, c in enumerate(cuts))
    mix = "[0:a]aformat=channel_layouts=mono[m];" + sfx + "[m]" + "".join(f"[s{k}]" for k in range(len(cuts))) + f"amix=inputs={len(cuts)+1}:duration=first:normalize=0[a]"
    sh("ffmpeg", "-v", "error", "-y", "-i", f"{WD}/joined.mp4", "-filter_complex", mix, "-map", "0:v", "-map", "[a]", "-c:v", "copy",
       "-c:a", "aac", "-b:a", "160k", f"{WD}/final.tmp.mp4")
    os.replace(f"{WD}/final.tmp.mp4", f"{WD}/final.mp4")
    return t


def qa(path):
    """게시 전 자동 검수: 길이·해상도·소리 크기"""
    d = dur(path)
    info = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "csv=p=0", path], capture_output=True, text=True).stdout.strip()
    vol = subprocess.run(["ffmpeg", "-i", path, "-af", "volumedetect", "-f", "null", "-"], capture_output=True, text=True).stderr
    mean = float(re.search(r"mean_volume: (-?[\d.]+)", vol).group(1)) if "mean_volume" in vol else -99
    ok = 12 <= d <= 59 and info == "1080,1920" and mean > -35
    print(f"검수: {d:.1f}초, {info}, 평균음량 {mean}dB → {'통과' if ok else '실패'}")
    return ok


def main():
    if not KEY: print("::error::GEMINI_API_KEY 없음"); raise SystemExit(1)
    os.makedirs(WD, exist_ok=True)
    q = json.load(open(Q, encoding="utf-8"))
    dl_streak = 0; tried = set()
    for _ in range(4):  # 실패하면 다음 순위로 최대 4번
        todo = sorted([x for x in q["items"] if x["status"] == "todo" and x["id"] not in tried], key=lambda x: x["rank"])
        if not todo: print("::warning::대기열이 비었습니다 → rank.py로 보충 필요"); return
        it = todo[0]; tried.add(it["id"]); print(f"{it['rank']}위 {it['title']} ({it['views']:,}회) / {it['channel']}")
        for f in os.listdir(WD): os.remove(os.path.join(WD, f))
        try:
            src = download_any(it)
            if not src:
                it["dl_fail"] = it.get("dl_fail", 0) + 1
                if it["dl_fail"] >= 3: it["status"] = "fail_download"
                save_q(q); dl_streak += 1
                if dl_streak >= 2: print("::error::연속 다운로드 실패 → 쿠키 만료 또는 유튜브 차단 의심, 이번 회차 중단"); raise SystemExit(1)
                continue
            p = plan(src, it["title"])
            if not p or p.get("skip") or not p.get("scenes"):
                it["status"] = "skip"; it["reason"] = (p or {}).get("reason", "대본 실패"); save_q(q); print("건너뜀:", it["reason"]); continue
            secs = render(src, p, it)
            if not qa(f"{WD}/final.mp4"): it["status"] = "fail_qa"; save_q(q); continue
        except Exception as e:
            print("::warning::제작 실패", e); it["status"] = "fail"; it["reason"] = str(e)[:200]; save_q(q); continue
        tags = [h.lstrip("#") for h in p.get("hashtags", [])][:8]
        meta = {"yt_title": (p.get("yt_title") or p.get("top1", ""))[:85] + " #Shorts",
                "yt_description": (f"{p.get('top1','')} {p.get('top2','')}\n\n"
                                   f"🎬 원본 영상: \"{it['title']}\" — {it['channel']}\n{it.get('page') or 'https://www.youtube.com/watch?v=' + it['id']}\n"
                                   f"원본 라이선스: {it.get('license', 'CC BY')} — 재사용이 허락된 영상에 한국어 더빙·자막·편집을 더했습니다.\n\n"
                                   + " ".join("#" + h for h in tags + ["쇼츠", "웃긴영상", "Shorts"])),
                "yt_tags": tags + ["웃긴영상", "쇼츠", "Shorts", "해외반응"], "yt_category": "23" if p.get("mood") != "touching" else "24"}
        json.dump(meta, open(f"{WD}/meta.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        it["status"] = "made"; it["made_at"] = time.strftime("%Y-%m-%d %H:%M"); it["plan"] = p; save_q(q)
        with open(os.environ.get("GITHUB_OUTPUT", "/dev/null"), "a") as o: o.write(f"vid={it['id']}\n")
        print(f"완성: {secs:.1f}초 → {meta['yt_title']}"); return
    raise SystemExit(1)


if __name__ == "__main__":
    main()
