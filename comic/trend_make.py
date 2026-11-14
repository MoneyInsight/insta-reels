"""실시간 트렌드 쇼츠 1편 — 지금 한국에서 뜨는 주제를 골라 최신 정보로 30초 정리 영상을 만든다.
1) 구글 트렌드(한국) + 유튜브 한국 인기 영상 제목 → 후보  2) 제미나이(구글 검색 연동)가 안전한 주제 선택·사실 확인·대본
3) Pixabay 무료 영상으로 화면 구성  4) 더빙·자막·효과음 → comic/work/final.mp4, meta.json (+ 대기열에 게시용 항목)
사용법: GEMINI_API_KEY=... PIXABAY_API_KEY=... [YT_API_KEY=...] python comic/trend_make.py
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


PROMPT = """너는 조회수 수백만 한국 유튜브 쇼츠 기획자야. 아래는 '지금 이 순간' 한국에서 뜨는 검색어·인기 영상 목록이야.
{cands}
최근 다룬 주제(겹치면 안 됨): {used}

1) 이 중 **쇼츠로 만들면 가장 클릭될 주제 하나**를 골라. 단, 정치·선거·범죄·사건사고·사망·재난·특정인 비방·선정적·연예인 사생활 루머 주제는 절대 고르지 마.
   좋은 예: 새 제품·IT 이슈, 스포츠 경기 결과, 여행지·축제, 생활 꿀팁, 화제의 음식·유행, 날씨·계절 이슈.
2) 구글 검색으로 그 주제의 **오늘 기준 최신 사실**을 확인하고, 확인된 사실만 써.
3) 25~35초 쇼츠 대본: 친구한테 말하듯 신난 반말. 첫 장면은 강한 후킹("이거 모르면 손해야", "요즘 난리 난 ○○ 알아?").
   장면 5~6개, 장면당 narration 25자 이내, caption 2줄 이내(줄당 14자, 줄바꿈 \\n), highlight는 caption 속 핵심 단어,
   broll은 그 장면에 깔 무료 영상 검색어(영어 1~3단어, 사람 얼굴·로고 없는 일반 장면. 예: "smartphone closeup", "soccer stadium", "autumn leaves").
   마지막 장면은 "너는 어떻게 생각해? 댓글로!"처럼 참여 유도.
4) 이 주제와 자연스럽게 이어지는 쿠팡 상품 검색어 하나.
JSON만 출력(코드블록 없이):
{{"topic": "...", "why": "고른 이유 한 줄", "facts": ["확인한 사실1", "사실2"], "top1": "상단 제목 12자 이내", "top2": "노란 부제 12자 이내",
 "yt_title": "후킹 제목 40자 이내", "hashtags": ["6개"], "scenes": [{{"narration": "...", "caption": "...", "highlight": "...", "broll": "..."}}],
 "product_keyword": "...", "product_must": "상품명에 꼭 들어갈 단어", "product_label": "12자 이내", "sns_text": "스레드·인스타 본문 3~4줄, 마지막 줄은 상품과 자연스럽게 연결"}}"""


def plan(cands, used):
    txt = "\n".join(f"- [{c['from']}] {c['kw']} (관심도 {c['traffic']}) {' / '.join(c['news'])}" for c in cands[:40])
    tries = [("gemini-3.8-flash", True), ("gemini-3.8-flash", False), ("gemini-3.8-flash-lite", False),
             ("gemini-3.8-flash", False), ("gemini-3.1-flash", False), ("gemini-3.1-pro-preview", False), ("gemini-3.8-flash", False)]
    for model, ground in tries:
        r = {}
        try:
            body = {"contents": [{"parts": [{"text": PROMPT.format(cands=txt, used=", ".join(used[-30:]) or "없음")}]}],
                    "generationConfig": {"temperature": 0.9}}
            if ground: body["tools"] = [{"google_search": {}}]
            r = requests.post(f"{m.G}/v1beta/models/{model}:generateContent?key={m.KEY}", timeout=240, json=body).json()
            t = "".join(p.get("text", "") for p in r["candidates"][0]["content"]["parts"])
            p = json.loads(re.search(r"\{.*\}", t, re.S).group(0))
            if p.get("scenes"): return p
        except Exception:
            e = r.get("error", {}) if isinstance(r, dict) else {}
            print("::notice::대본 실패", model, "검색" if ground else "", str(e.get("message", e))[:400]); time.sleep(20)
    return None


def broll(q, i, used_ids):
    for qq in [q, " ".join(q.split()[:1]), "city life"]:
        try:
            j = requests.get("https://pixabay.com/api/videos/", params={"key": PIX, "q": qq, "safesearch": "true", "per_page": 12, "video_type": "film"}, timeout=30).json()
        except Exception: continue
        hits = [h for h in j.get("hits", []) if h["id"] not in used_ids and h.get("duration", 0) >= 4]
        if not hits: continue
        h = random.choice(hits[:6]); used_ids.add(h["id"])
        v = h["videos"].get("medium") or h["videos"].get("small") or h["videos"].get("large")
        out = f"{m.WD}/b{i}.mp4"
        with requests.get(v["url"], stream=True, timeout=120, headers=UA) as rr:
            rr.raise_for_status()
            with open(out, "wb") as f:
                for ch in rr.iter_content(1 << 20): f.write(ch)
        return out, h.get("user", "Pixabay"), h.get("pageURL", "")
    return None, None, None


def seg(src, d, ov, aud, out, tempo):
    total = m.dur(src); loop = ["-stream_loop", "-1"] if total < d + 0.2 else []
    st = 0.0 if loop else max(0.0, min(total - d, (total - d) / 3))
    vf = (f"[0:v]fps=30,scale=1080:1150:force_original_aspect_ratio=increase,crop=1080:1150,setsar=1,"
          f"zoompan=z='min(1+on/600,1.08)':d=1:s=1080x1150:fps=30[v];color=black:s={m.W}x{m.H}:r=30[bg];[bg][v]overlay=0:{m.TOP}:shortest=1[b];"
          f"[b][1:v]overlay=0:0,format=yuv420p[vo];[2:a]atempo={tempo:.3f},apad,aformat=sample_rates=44100:channel_layouts=mono,volume=1.25[ao]")
    m.sh("ffmpeg", "-v", "error", "-y", *loop, "-ss", f"{st:.2f}", "-t", f"{d:.2f}", "-i", src, "-i", ov, "-i", aud, "-filter_complex", vf,
         "-map", "[vo]", "-map", "[ao]", "-t", f"{d:.2f}", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-r", "30",
         "-c:a", "aac", "-ar", "44100", "-ac", "1", "-b:a", "128k", out + ".tmp.mp4")
    os.replace(out + ".tmp.mp4", out)


def main():
    if not (m.KEY and PIX): print("::error::GEMINI_API_KEY / PIXABAY_API_KEY 필요"); raise SystemExit(1)
    os.makedirs(m.WD, exist_ok=True)
    for f in os.listdir(m.WD): os.remove(os.path.join(m.WD, f))
    log = json.load(open(LOG, encoding="utf-8")) if os.path.exists(LOG) else []
    cands = google_trends() + youtube_popular()
    print("트렌드 후보", len(cands))
    if not cands: raise SystemExit("트렌드를 못 가져옴")
    p = plan(cands, [x["topic"] for x in log])
    if not p: print("::error::제미나이 대본 생성 불가 → 다음 회차에"); raise SystemExit(1)
    print("주제:", p["topic"], "|", p.get("why", ""))
    credit = "영상: Pixabay 무료 라이선스 · 정보: 최신 보도 종합"
    parts, cuts, t, used_ids, owners = [], [], 0.0, set(), []
    for i, s in enumerate(p["scenes"][:6]):
        a = f"{m.WD}/n{i}.wav"
        if not m.tts(s["narration"], a, "funny"): raise SystemExit("음성 실패")
        src, owner, page = broll(s.get("broll") or p["topic"], i, used_ids)
        if not src: raise SystemExit("화면 영상을 못 찾음")
        owners.append(f"{owner} {page}")
        ad = m.dur(a); d = max(2.8, ad + 0.35); tempo = 1.0
        ov = m.overlay(i, p.get("top1", "")[:14], p.get("top2", "")[:14], s.get("caption", ""), s.get("highlight", ""), credit)
        out = f"{m.WD}/s{i}.mp4"; seg(src, d, ov, a, out, tempo); parts.append(out); t += d; cuts.append(t)
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
            "yt_description": (f"{p.get('top1','')} {p.get('top2','')}\n\n📌 핵심 정리\n" + "\n".join("· " + f for f in p.get("facts", [])[:5]) +
                               "\n\n너는 어떻게 생각해? 댓글로 알려줘!\n\n🎬 화면 영상: Pixabay(무료 라이선스) — " + ", ".join(o.split(" ")[0] for o in owners) +
                               "\n\n" + " ".join("#" + h for h in tags + ["쇼츠", "이슈", "Shorts"])),
            "yt_tags": tags + ["쇼츠", "이슈", "트렌드", "Shorts"], "yt_category": "24"}
    json.dump(meta, open(f"{m.WD}/meta.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    rid = "trend" + time.strftime("%Y%m%d%H%M")
    q = json.load(open(m.Q, encoding="utf-8")) if os.path.exists(m.Q) else {"items": []}
    q["items"].append({"id": rid, "src": "trend", "title": p["topic"], "channel": "Pixabay", "license": "무료 라이선스", "status": "made", "rank": 0,
                       "made_at": time.strftime("%Y-%m-%d %H:%M"), "kind": "trend", "plan": {k: p.get(k) for k in
                       ("top1", "top2", "hashtags", "product_keyword", "product_must", "product_label", "sns_text", "yt_title")}})
    m.save_q(q)
    log.append({"topic": p["topic"], "time": time.strftime("%Y-%m-%d %H:%M"), "id": rid})
    json.dump(log[-300:], open(LOG, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    with open(os.environ.get("GITHUB_OUTPUT", "/dev/null"), "a") as o: o.write(f"vid={rid}\n")
    print(f"완성: {t:.1f}초 → {meta['yt_title']}")


if __name__ == "__main__":
    main()
