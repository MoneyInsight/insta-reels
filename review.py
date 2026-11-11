"""게시 전 자동 검수: 규칙 검사 + Gemini가 영상을 직접 보고 듣고 확인.
사용: python3 review.py NAME  (coupang/scripts/NAME.* 와 site/short-NAME.mp4 검사)
반환: (통과 여부, 문제 목록)"""
import base64, json, os, re, subprocess, sys
import requests

SCRIPTS = "coupang/scripts"
BAD_WORDS = ["아나운서", "또박또박", "말해", "지시", "Say this", "excited friend", "{LINK}", "None", "undefined", "샀어", "써보니"]


def ffmpeg():
    try:
        import imageio_ffmpeg; return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


def media_info(mp4):
    r = subprocess.run([ffmpeg(), "-i", mp4, "-af", "volumedetect", "-f", "null", "-"], capture_output=True, text=True).stderr
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", r)
    dur = int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3]) if m else 0
    v = re.search(r"mean_volume: (-?[\d.]+) dB", r)
    return dur, float(v[1]) if v else -99.0


def rule_check(name):
    js = json.load(open(f"{SCRIPTS}/{name}.json", encoding="utf-8"))
    th = open(f"{SCRIPTS}/{name}.threads.txt", encoding="utf-8").read()
    ig = open(f"{SCRIPTS}/{name}.insta.txt", encoding="utf-8").read()
    mp4 = f"site/short-{name}.mp4"
    probs = []
    if not os.path.exists(mp4) or os.path.getsize(mp4) < 200_000: probs.append("영상 파일이 없거나 너무 작음")
    else:
        dur, vol = media_info(mp4)
        if not 12 <= dur <= 60: probs.append(f"영상 길이 이상 ({dur:.0f}초)")
        if vol < -40: probs.append("소리가 거의 없음")
    if "coupang" not in th and "coupa.ng" not in th: probs.append("스레드 글에 구매 링크 없음")
    if "coupang" not in ig and "coupa.ng" not in ig: probs.append("인스타 글에 구매 링크 없음")
    if "수수료" not in th or "수수료" not in ig: probs.append("대가성 문구 없음")
    if len(th) > 500: probs.append("스레드 글 500자 초과")
    say = " ".join([js.get("intro", {}).get("say", "")] + [s["say"] for s in js["scenes"]])
    for w in BAD_WORDS:
        if w in th or w in ig or w in say: probs.append(f"금지 표현 포함: {w}")
    return probs, js, th, mp4


def detail_parts(js):
    """상세페이지 이미지를 줄여서 Gemini에 같이 보낸다 (내용 대조용)."""
    import io
    try:
        from PIL import Image
        d = json.load(open(f"coupang/details/{js.get('coupang_product_id')}.json", encoding="utf-8"))
    except Exception:
        return []
    parts = []
    for x in d.get("images", [])[:4]:
        try:
            u = x["url"] if isinstance(x, dict) else x
            im = Image.open(io.BytesIO(requests.get(u, timeout=20).content)).convert("RGB")
            im = im.resize((500, max(1, int(im.height * 500 / im.width))))
            if im.height > 6000: im = im.crop((0, 0, 500, 6000))
            b = io.BytesIO(); im.save(b, "JPEG", quality=75)
            parts.append({"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(b.getvalue()).decode()}})
        except Exception:
            continue
    return parts


def gemini_check(js, th, mp4, ig=""):
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key or os.path.getsize(mp4) > 18_000_000: return None
    script = "\n".join([js.get("intro", {}).get("say", "")] + [s["say"] for s in js["scenes"]] + [js.get("cta_say", "")])
    det = detail_parts(js)
    prompt = (f"너는 쇼츠 검수자야. 이 영상은 쿠팡 상품 '{js['product']}' 홍보 쇼츠고, 원래 내레이션 대본은 아래와 같아.\n{script}\n\n"
              "영상을 직접 보고 들은 뒤 JSON으로만 답해: "
              '{"transcript": "실제로 들린 내레이션", "extra_speech": "대본에 없는데 읽힌 말(지시문 등), 없으면 빈칸", '
              '"problems": ["심각한 문제만: 대본에 없는 말 읽음, 소리 끊김/잡음, 상품과 무관한 이미지, 자막 잘림/겹침, 깨진 이미지, 오타, 어색한 문장"], '
              '"hook_score": 1~10 (첫 3초가 시선을 끄는 정도), "ok": true/false}\n'
              "사소한 취향 문제는 problems에 넣지 마.\n"
              + (f"\n함께 보낸 이미지들은 이 상품의 실제 쿠팡 상세페이지야. 영상 내레이션·자막과 아래 게시글에 나온 수치·기능·효과·구성이 "
                 f"상세페이지와 다르거나 상세페이지에 없는 과장이면 '내용 불일치: ~' 형식으로 problems에 넣어. 상품명이 다르면 그것도.\n"
                 f"[스레드 글]\n{th}\n[인스타 글]\n{ig}" if det else ""))
    body = {"contents": [{"parts": [{"inline_data": {"mime_type": "video/mp4", "data": base64.b64encode(open(mp4, "rb").read()).decode()}},
                                    {"text": prompt}] + det}],
            "generationConfig": {"responseMimeType": "application/json"}}
    last = ""
    try:
        ms = requests.get(f"https://generativelanguage.googleapis.com/v1beta/models?key={key}&pageSize=200", timeout=20).json().get("models", [])
        names = [m["name"].split("/")[1] for m in ms if "generateContent" in m.get("supportedGenerationMethods", [])]
    except Exception:
        names = []
    flash = sorted([n for n in names if re.match(r"gemini-[\d.]+-flash(-lite)?$", n)], reverse=True)
    for model in (["gemini-flash-latest", "gemini-flash-lite-latest"] + flash)[:6]:
        r = {}
        try:
            r = requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}",
                              json=body, timeout=180).json()
            t = r["candidates"][0]["content"]["parts"][0]["text"]
            return json.loads(t[t.find("{"): t.rfind("}") + 1])
        except Exception as e:
            last += f" | {model}: " + (json.dumps(r.get("error", {}), ensure_ascii=False)[:200] if isinstance(r, dict) and r.get("error") else repr(e)[:200])
            continue
    print("::notice::AI 검수 오류 " + last)
    return None


def review(name):
    probs, js, th, mp4 = rule_check(name)
    g = None
    if not any("영상 파일" in p for p in probs):
        ig = open(f"{SCRIPTS}/{name}.insta.txt", encoding="utf-8").read()
        g = gemini_check(js, th, mp4, ig)
    if g:
        if g.get("extra_speech", "").strip(): probs.append("대본에 없는 말 읽음: " + g["extra_speech"][:60])
        for p in g.get("problems", [])[:6]:
            if p: probs.append(p if p.startswith("내용 불일치") else f"AI 검수: {p}")
        for w in ["아나운서", "또박또박", "Say this", "friend"]:
            if w in g.get("transcript", ""): probs.append(f"내레이션에 지시문 포함: {w}")
    else:
        print("::notice::AI 검수 사용 불가 → 규칙 검사만 진행")
    os.makedirs("coupang/reviews", exist_ok=True)
    json.dump({"name": name, "problems": probs, "gemini": g}, open(f"coupang/reviews/{name}.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("검수:", "통과" if not probs else "문제 " + str(len(probs)) + "개", "| 후킹 점수:", (g or {}).get("hook_score", "-"))
    for p in probs: print("  -", p)
    return not probs, probs


if __name__ == "__main__":
    ok, _ = review(sys.argv[1])
    sys.exit(0 if ok else 1)
