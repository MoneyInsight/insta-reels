"""인기 영상 쇼츠 1편 — Pixabay 인기 영상을 고르고, 제미나이가 실제 화면을 보고 화면에 딱 맞는 나레이션·자막을 쓴다.
1) Pixabay 인기순(order=popular) 영상 중 같은 테마 4개 선택  2) 각 영상 장면 사진을 제미나이에 보여주고 대본 작성
3) 더빙·자막·효과음 → comic/work/final.mp4, meta.json (+ 대기열에 게시용 항목)
사용법: GEMINI_API_KEY=... PIXABAY_API_KEY=... python comic/trend_make.py
"""
import html, json, os, random, re, subprocess, sys, time, functools
import xml.etree.ElementTree as ET
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import make as m
import requests
print = functools.partial(print, flush=True)

PIX = os.environ.get("PIXABAY_API_KEY", "").strip()
YTK = os.environ.get("YT_API_KEY", "").strip()
LOG = "comic/trends_log.json"
UA = {"User-Agent": "Mozilla/5.0 (trend-shorts bot; github.com/MoneyInsight/insta-reels)"}


def google_trends():
    out = []
    try:
        x = ET.fromstring(requests.get("https://trends.google.com/trending/rss?geo=KR", headers=UA, timeout=30).content)
        ns = {"ht": "https://trends.google.com/trending/rss"}
        for it in x.iter("item"):
            news = [html.unescape(n.findtext("ht:news_item_title", "", ns)) for n in it.findall("ht:news_item", ns)][:2]
            out.append({"kw": it.findtext("title", ""), "traffic": it.findtext("ht:approx_traffic", "", ns), "news": news, "from": "구글트렌드"})
    except Exception as e: print("::warning::구글 트렌드 실패", e)
    return out


def youtube_popular():
    if not YTK: return []
    try:
        j = requests.get("https://www.googleapis.com/youtube/v3/videos", params={"part": "snippet,statistics", "chart": "mostPopular", "regionCode": "KR",
                         "maxResults": 30, "key": YTK}, timeout=30).json()
        return [{"kw": v["snippet"]["title"][:80], "traffic": v["statistics"].get("viewCount", ""), "news": [], "from": "유튜브인기"} for v in j.get("items", [])]
    except Exception as e: print("::warning::유튜브 인기 실패", e); return []


PROMPT = """너는 조회수 수백만 한국 유튜브 쇼츠 작가야. 아래 사진들은 Pixabay 인기 영상 {n}개에서 뽑은 장면이야(영상마다 3장, 순서대로).
{clips}
이 영상들을 순서대로 이어 붙여 30초 안팎 쇼츠 1편을 만든다. 규칙:
1) 나레이션·자막은 반드시 **그 영상 화면에 실제로 보이는 것**을 말해. 화면에 없는 사람·사건·장소를 지어내지 마.
2) 친구한테 말하듯 신나는 반말. 첫 장면은 강한 후킹("잠깐, 이거 진짜야?", "끝까지 보면 소름"), 장면마다 웃긴 드립이나 신기한 사실 하나.
3) 장면 i의 narration은 (그 영상 길이 × 5)자 이내, 최대 40자. caption 2줄 이내(줄당 14자, 줄바꿈 \\n), highlight는 caption 속 핵심 단어.
4) 마지막 장면은 "너는 어떤 게 제일 좋아? 댓글로!" 같은 참여 유도.
5) 이 테마와 자연스럽게 이어지는 쿠팡 상품 검색어 하나.
최근 다룬 주제(겹치면 안 됨): {used}
JSON만 출력(코드블록 없이), scenes는 정확히 {n}개, 영상 순서대로:
{{"topic": "한 줄 주제", "facts": ["영상 속 재미 포인트1", "포인트2"], "top1": "상단 제목 12자 이내", "top2": "노란 부제 12자 이내",
 "yt_title": "후킹 제목 40자 이내", "hashtags": ["6개"], "scenes": [{{"narration": "...", "caption": "...", "highlight": "..."}}],
 "product_keyword": "...", "product_must": "상품명에 꼭 들어갈 단어", "product_label": "12자 이내", "sns_text": "스레드·인스타 본문 3~4줄, 마지막 줄은 상품과 자연스럽게 연결"}}"""

CATS = ["animals", "animals", "people", "food", "sports", "nature", "travel", "feelings", "science", "places"]


def px(params):
    try:
        return requests.get("https://pixabay.com/api/videos/", params={"key": PIX, "safesearch": "true", **params}, timeout=30).json().get("hits", [])
    except Exception as e:
        print("::warning::Pixabay 실패", e); return []


def pick_clips(used_ids, n=4):
    ok = lambda h: h["id"] not in used_ids and 5 <= h.get("duration", 0) <= 40
    for _ in range(6):
        cat = random.choice(CATS)
        pool = [h for h in px({"category": cat, "order": "popular", "per_page": 50, "page": random.randint(1, 6)}) if ok(h)]
        if not pool: continue
        seed = random.choice(pool[:15]); tag = seed.get("tags", "").split(",")[0].strip()
        rel = [h for h in px({"q": tag, "order": "popular", "per_page": 30}) if ok(h) and h["id"] != seed["id"]] if tag else []
        rel += [h for h in pool if h["id"] != seed["id"] and h not in rel]
        clips = [seed] + rel[:n - 1]
        if len(clips) >= n - 1: print("테마:", cat, tag, [h["id"] for h in clips]); return clips
    return []


def fetch(h, i):
    v = h["videos"].get("medium") or h["videos"].get("small") or h["videos"].get("large")
    out = f"{m.WD}/b{i}.mp4"
    with requests.get(v["url"], stream=True, timeout=120, headers=UA) as rr:
        rr.raise_for_status()
        with open(out, "wb") as f:
            for ch in rr.iter_content(1 << 20): f.write(ch)
    frames = []
    d = m.dur(out)
    for k, fr in enumerate((0.15, 0.5, 0.85)):
        jp = f"{m.WD}/f{i}_{k}.jpg"
        m.sh("ffmpeg", "-v", "error", "-y", "-ss", f"{d*fr:.2f}", "-i", out, "-frames:v", "1", "-vf", "scale=384:-2", "-q:v", "5", jp)
        frames.append(jp)
    return out, frames


GHT = os.environ.get("GITHUB_TOKEN", "").strip()


def gpt_plan(parts, n):
    """GitHub Models(무료, GITHUB_TOKEN)로 OpenAI GPT가 장면 사진을 보고 대본 작성"""
    if not GHT: print("::notice::GITHUB_TOKEN 없음 → GPT 건너뜀"); return None
    content = []
    for x in parts:
        if "text" in x: content.append({"type": "text", "text": x["text"]})
        else: content.append({"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + x["inline_data"]["data"], "detail": "low"}})
    eps = [("https://models.github.ai/inference/chat/completions", ["openai/gpt-4.1", "openai/gpt-4o", "openai/gpt-4.1-mini"]),
           ("https://models.inference.ai.azure.com/chat/completions", ["gpt-4o", "gpt-4o-mini"])]
    for rnd in range(2):
        for url, models in eps:
            for model in models:
                txt = ""
                try:
                    rr = requests.post(url, timeout=180, headers={"Authorization": f"Bearer {GHT}", "Content-Type": "application/json",
                                                                  "Accept": "application/json", "X-GitHub-Api-Version": "2022-11-28"},
                                       json={"model": model, "temperature": 0.9, "messages": [{"role": "user", "content": content}]})
                    txt = f"{rr.status_code} {rr.text[:250]}"
                    t = rr.json()["choices"][0]["message"]["content"]
                    p = json.loads(re.search(r"\{.*\}", t, re.S).group(0))
                    if len(p.get("scenes", [])) >= n - 1: print("대본 작성:", model); return p
                except Exception as e:
                    print("::notice::GPT 실패", model, txt or e); time.sleep(5)
    return None


def voice(text, out):
    """마이크로소프트 음성(edge-tts)으로 바로 더빙"""
    try:
        import asyncio, edge_tts
        asyncio.run(edge_tts.Communicate(text, "ko-KR-InJoonNeural", rate="+15%", pitch="+0Hz").save(out + ".mp3"))
        m.sh("ffmpeg", "-y", "-v", "error", "-i", out + ".mp3", "-ar", "44100", "-ac", "1", out)
        return True
    except Exception as e:
        print("::warning::edge-tts 실패 → 기존 방식", e); return m.tts(text, out, "funny")


def plan(clips, used):
    import base64
    desc = "\n".join(f"- 영상{i+1}: {c['dur']:.0f}초, 태그: {c['tags']}" for i, c in enumerate(clips))
    parts = [{"text": PROMPT.format(n=len(clips), clips=desc, used=", ".join(used[-30:]) or "없음")}]
    for i, c in enumerate(clips):
        parts.append({"text": f"[영상{i+1}]"})
        for f in c["frames"]:
            parts.append({"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(open(f, "rb").read()).decode()}})
    p = gpt_plan(parts, len(clips))
    if p: return p
    print("::notice::GPT 실패 → 제미나이로 대체")
    try:
        ms = requests.get(f"{m.G}/v1beta/models?key={m.KEY}&pageSize=200", timeout=30).json().get("models", [])
        names = [x["name"].split("/")[-1] for x in ms if "generateContent" in x.get("supportedGenerationMethods", [])
                 and not re.search(r"tts|image|live|audio|embed|robotics|computer|learnlm|gemma", x["name"])]
    except Exception: names = []
    flash = sorted([n for n in names if "flash" in n], key=lambda n: ("lite" in n, "preview" in n or "exp" in n))
    order = list(dict.fromkeys(["gemini-3.8-flash"] + flash[:4]))
    print("모델 후보:", order)
    for model in order * 3:
        r = {}
        try:
            r = requests.post(f"{m.G}/v1beta/models/{model}:generateContent?key={m.KEY}", timeout=240,
                              json={"contents": [{"parts": parts}], "generationConfig": {"temperature": 0.9}}).json()
            t = "".join(p.get("text", "") for p in r["candidates"][0]["content"]["parts"])
            p = json.loads(re.search(r"\{.*\}", t, re.S).group(0))
            if len(p.get("scenes", [])) >= len(clips) - 1: return p
        except Exception:
            e = r.get("error", {}) if isinstance(r, dict) else {}
            print("::notice::대본 실패", model, str(e.get("message", e))[:300]); time.sleep(45 if "demand" in str(e) else 5)
    return None


def seg(src, d, ov, aud, out, tempo):
    total = m.dur(src); loop = ["-stream_loop", "-1"] if total < d + 0.2 else []
    st = 0.0
    vf = (f"[0:v]fps=30,scale=1080:1150:force_original_aspect_ratio=increase,crop=1080:1150,setsar=1,"
          f"zoompan=z='min(1+on/600,1.08)':d=1:s=1080x1150:fps=30[v];color=black:s={m.W}x{m.H}:r=30[bg];[bg][v]overlay=0:{m.TOP}:shortest=1[b];"
          f"[b][1:v]overlay=0:0,format=yuv420p[vo];[2:a]atempo={tempo:.3f},apad,aformat=sample_rates=44100:channel_layouts=mono,volume=1.25[ao]")
    m.sh("ffmpeg", "-v", "error", "-y", *loop, "-ss", f"{st:.2f}", "-t", f"{d:.2f}", "-i", src, "-i", ov, "-i", aud, "-filter_complex", vf,
         "-map", "[vo]", "-map", "[ao]", "-t", f"{d:.2f}", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-r", "30",
         "-c:a", "aac", "-ar", "44100", "-ac", "1", "-b:a", "128k", out + ".tmp.mp4")
    os.replace(out + ".tmp.mp4", out)


def main():
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "edge-tts"], check=False)
    if not PIX: print("::error::PIXABAY_API_KEY 필요"); raise SystemExit(1)
    os.makedirs(m.WD, exist_ok=True)
    for f in os.listdir(m.WD): os.remove(os.path.join(m.WD, f))
    log = json.load(open(LOG, encoding="utf-8")) if os.path.exists(LOG) else []
    used_ids = {i for x in log for i in x.get("pix", [])}
    hits = pick_clips(used_ids)
    if not hits: raise SystemExit("Pixabay 인기 영상을 못 가져옴")
    clips = []
    for i, h in enumerate(hits):
        try:
            src, frames = fetch(h, i)
            clips.append({"src": src, "frames": frames, "dur": m.dur(src), "tags": h.get("tags", ""), "id": h["id"],
                          "owner": h.get("user", "Pixabay"), "page": h.get("pageURL", "")})
        except Exception as e: print("::warning::영상 받기 실패", h["id"], e)
    if len(clips) < 3: raise SystemExit("영상이 부족함")
    p = plan(clips, [x["topic"] for x in log])
    if not p: print("::error::제미나이 대본 생성 불가 → 다음 회차에"); raise SystemExit(1)
    print("주제:", p["topic"])
    credit = "영상: Pixabay 인기 영상 · 무료 라이선스"
    parts, cuts, t, owners = [], [], 0.0, []
    for i, (s, c) in enumerate(zip(p["scenes"], clips)):
        a = f"{m.WD}/n{i}.wav"
        if not voice(s["narration"], a): raise SystemExit("음성 실패")
        owners.append(c["owner"])
        ad = m.dur(a); d = max(4.0, ad + 0.4); tempo = 1.0
        ov = m.overlay(i, p.get("top1", "")[:14], p.get("top2", "")[:14], s.get("caption", ""), s.get("highlight", ""), credit)
        out = f"{m.WD}/s{i}.mp4"; seg(c["src"], d, ov, a, out, tempo); parts.append(out); t += d; cuts.append(t)
    open(f"{m.WD}/list.txt", "w").write("".join(f"file '{os.path.basename(x)}'\n" for x in parts))
    m.sh("ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", f"{m.WD}/list.txt", "-c", "copy", f"{m.WD}/joined.mp4")
    cuts = cuts[:-1]
    sfx = "".join(f"aevalsrc='0.3*sin(2*PI*(600+2500*t)*t)*exp(-14*t)':d=0.25:s=44100,adelay={int(x*1000)},aformat=channel_layouts=mono[s{k}];" for k, x in enumerate(cuts))
    mix = "[0:a]aformat=channel_layouts=mono[m];" + sfx + "[m]" + "".join(f"[s{k}]" for k in range(len(cuts))) + f"amix=inputs={len(cuts)+1}:duration=first:normalize=0[a]"
    m.sh("ffmpeg", "-v", "error", "-y", "-i", f"{m.WD}/joined.mp4", "-filter_complex", mix, "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", f"{m.WD}/final.tmp.mp4")
    os.replace(f"{m.WD}/final.tmp.mp4", f"{m.WD}/final.mp4")
    if not m.qa(f"{m.WD}/final.mp4"): raise SystemExit("검수 실패")
    tags = [h.lstrip("#") for h in p.get("hashtags", [])][:8]
    meta = {"yt_title": (p.get("yt_title") or p["topic"])[:85] + " #Shorts",
            "yt_description": (f"{p.get('top1','')} {p.get('top2','')}\n\n📌 재미 포인트\n" + "\n".join("· " + f for f in p.get("facts", [])[:5]) +
                               "\n\n너는 어떻게 생각해? 댓글로 알려줘!\n\n🎬 화면 영상: Pixabay(무료 라이선스) — " + ", ".join(o.split(" ")[0] for o in owners) +
                               "\n\n" + " ".join("#" + h for h in tags + ["쇼츠", "인기영상", "Shorts"])),
            "yt_tags": tags + ["쇼츠", "인기영상", "웃긴영상", "Shorts"], "yt_category": "24"}
    json.dump(meta, open(f"{m.WD}/meta.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    rid = "trend" + time.strftime("%Y%m%d%H%M")
    q = json.load(open(m.Q, encoding="utf-8")) if os.path.exists(m.Q) else {"items": []}
    q["items"].append({"id": rid, "src": "trend", "title": p["topic"], "channel": "Pixabay", "license": "무료 라이선스", "status": "made", "rank": 0,
                       "made_at": time.strftime("%Y-%m-%d %H:%M"), "kind": "trend", "plan": {k: p.get(k) for k in
                       ("top1", "top2", "hashtags", "product_keyword", "product_must", "product_label", "sns_text", "yt_title")}})
    m.save_q(q)
    log.append({"topic": p["topic"], "time": time.strftime("%Y-%m-%d %H:%M"), "id": rid, "pix": [c["id"] for c in clips]})
    json.dump(log[-300:], open(LOG, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    with open(os.environ.get("GITHUB_OUTPUT", "/dev/null"), "a") as o: o.write(f"vid={rid}\n")
    print(f"완성: {t:.1f}초 → {meta['yt_title']}")


if __name__ == "__main__":
    main()
