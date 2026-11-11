"""쿠팡 파트너스 숏츠 완전 자동 엔진 (깃허브 액션 전용, Claude 사용량 0).

사용법
  python auto_coupang.py prepare threads   # 새 상품 1개 → 대본·영상·캡션 준비 (site/ 에 영상)
  python auto_coupang.py prepare insta     # 최근 스레드 영상 중 쿠팡 클릭 1위 → 인스타용 준비
  python auto_coupang.py mark threads|insta <NAME>   # 게시 성공 기록

- 스레드: 30분마다 새 상품. 상품마다 쿠팡 추적코드(subId)를 따로 달아 클릭 수를 잰다.
- 인스타: 3시간마다, 아직 인스타에 안 올린 최근 24시간 스레드 영상 중 클릭이 가장 많은 것.
- 후킹 대본: GEMINI_API_KEY 가 있으면 Gemini가 쓰고, 없거나 실패하면 내장 후킹 템플릿.
- 상품명에 없는 기능·수치·효능은 쓰지 않는다. 가격은 바뀌므로 쓰지 않는다.
"""
import hashlib, json, os, random, re, subprocess, sys, time
from datetime import datetime, timedelta, timezone

import requests

import coupang_api as cp

KST = timezone(timedelta(hours=9))
NOW = datetime.now(KST)
LOG = "coupang/auto_log.json"
SCRIPTS = "coupang/scripts"
DISCLOSURE = "이 게시물은 쿠팡 파트너스 활동의 일환으로, 이에 따른 일정액의 수수료를 제공받습니다."
OUT = os.environ.get("GITHUB_OUTPUT")


def out(k, v):
    print(f"{k}={v}")
    if OUT:
        open(OUT, "a", encoding="utf-8").write(f"{k}={v}\n")


def jload(p, default):
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return default


def jsave(p, d):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    json.dump(d, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


# ---------------- 상품 고르기 ----------------
SKIP_WORDS = ["계란", "대란", "우유", "생수", "삼다수", "흰밥", "햇반", "바나나", "오이", "버섯", "국내산 무", "양파", "대파", "두부",
              "도서", "잡지", "동아", "문제집", "교재", "영양제", "오메가", "비타민", "유산균", "홍삼", "건강기능", "의약", "콘돔", "성인",
              "종일권", "입장권", "숙박", "여행", "체크인", "객실", "룸", "쿠폰", "상품권", "기프트"]
GOOD_CATS = ["주방", "생활", "홈인테리어", "가구", "가전", "디지털", "스포츠", "레저", "자동차", "반려", "완구", "취미", "문구", "뷰티"]


def usable(p):
    n = p.get("name") or ""
    if any(w in n for w in SKIP_WORDS):
        return False
    if len(n.split()) < 2 or len(n) < 8:
        return False
    return bool(p.get("image"))


def candidates():
    d = jload("coupang/candidates.json", {})
    used = {str(x) for x in jload("coupang/posted.json", [])} | {str(e["productId"]) for e in jload(LOG, [])}
    items = [p for p in d.get("items", []) if str(p["productId"]) not in used and usable(p)]
    fresh = d.get("updated", "") >= (NOW - timedelta(hours=6)).strftime("%Y-%m-%d %H:%M")
    if len(items) < 5 or not fresh:
        print("후보가 부족하거나 오래돼서 새로 받는다")
        try:
            cp.pick([])
        except SystemExit as e:
            print("::warning::후보 갱신 실패", e)
        d = jload("coupang/candidates.json", {})
        items = [p for p in d.get("items", []) if str(p["productId"]) not in used and usable(p)]
    return items


def choose(items):
    recent_cats = [e.get("category", "") for e in jload(LOG, [])[-3:]]
    def score(p):
        s = 0
        cat = p.get("category", "") + p.get("source", "")
        if any(c in cat for c in GOOD_CATS): s += 3
        if p.get("category", "") in recent_cats: s -= 3          # 같은 분야 연속 피하기
        if p.get("source") == "골드박스": s += 1
        if p.get("rocket"): s += 1
        s += min(len(feature_tokens(p["name"])), 4) * 0.5        # 특징이 많은 상품
        return s
    items = sorted(items, key=score, reverse=True)
    return items[0] if items else None


# ---------------- 상품명에서 특징 뽑기 ----------------
UNIT = r"(?:L|ml|mL|ML|리터|kg|g|cm|mm|m|개|매|롤|팩|p|P|입|구|단|W|w|mAh|인치|인용|인|겹|종|세트|장|컵|중)"


def feature_tokens(name):
    name = re.sub(r"\[[^\]]*\]|\([^)]*\)|★[^★]*★", " ", name)
    toks = [t.strip(",./·+") for t in name.split()]
    toks = [t for t in toks if len(t) >= 2]
    if toks and re.match(r"^[A-Za-z0-9가-힣]{2,}$", toks[0]) and len(toks) > 3:
        toks = toks[1:]                       # 맨 앞 브랜드명은 특징에서 뺀다
    nums = [t for t in toks if re.search(r"\d", t) and re.search(UNIT, t)]
    rest = [t for t in toks if t not in nums]
    seen, res = set(), []
    for t in nums + rest:
        if t not in seen:
            seen.add(t); res.append(t)
    return res[:5]


def short_name(name, n=18):
    name = re.sub(r"\[[^\]]*\]|\([^)]*\)|★[^★]*★", " ", name)
    name = re.sub(r"\s+", " ", name).strip()
    if len(name) <= n: return name
    cut = name[:n]
    return cut[:cut.rfind(" ")] if " " in cut else cut


def speakable(t):  # 숫자 단위를 읽기 좋게
    rep = {"L": "리터", "ml": "밀리리터", "mL": "밀리리터", "kg": "킬로그램", "cm": "센티", "mm": "밀리", "W": "와트", "mAh": "밀리암페어", "p": "개", "P": "개"}
    return re.sub(r"(\d+(?:\.\d+)?)\s*(mAh|ml|mL|kg|cm|mm|L|W|p|P)\b", lambda m: m.group(1) + rep.get(m.group(2), m.group(2)), t)


# ---------------- 후킹 대본: Gemini ----------------
def gemini_copy(p):
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        return None
    try:
        ms = requests.get(f"https://generativelanguage.googleapis.com/v1beta/models?key={key}&pageSize=200", timeout=20).json().get("models", [])
        avail = [m["name"] for m in ms if "generateContent" in m.get("supportedGenerationMethods", [])]
        flash = sorted([n for n in avail if re.match(r"models/gemini-[\d.]+-flash$", n)], reverse=True)
        order = [n for n in ["models/gemini-flash-latest", "models/gemini-2.5-flash"] if n in avail] + flash
        order = list(dict.fromkeys(order)) or ["models/gemini-2.5-flash"]
        prompt = f"""너는 쿠팡 살림템을 친구한테 추천하는 30대 유튜버다. 아래 상품으로 30초 세로 숏츠 대본과 캡션을 JSON으로만 써라.
상품명: {p['name']}
카테고리: {p.get('category','')}
말투: 광고 문구 말고 진짜 사람이 쓴 것처럼. 친한 사람한테 말하듯 구어체 존댓말("~더라고요", "~거든요", "솔직히", "아니 근데", "이거 진짜"), 살짝 웃긴 비유나 현실 공감 한 스푼. "제품", "탁월한", "최고의", "강력 추천", "혁신적인" 같은 딱딱한 광고 말은 쓰지 않는다.
규칙:
- 상품명에 실제로 들어 있는 특징만 쓴다. 상품명에 없는 기능·수치·효능·후기·가격은 절대 지어내지 않는다. 써 본 척하지 않는다. "샀어요", "담았어요", "써보니", "먹어보니", "우리 집", "제가 써보니" 같은 직접 구매·사용 경험 표현은 절대 쓰지 않는다(추천하는 사람 시점으로만).
- 1장면은 스크롤을 멈추게 하는 후킹: 대상 지목 + 공감되는 상황 질문(예: "자취생 여러분, 이거 아직 모르세요?", "매번 ○○ 때문에 짜증나셨죠?"). badge는 4~6자(예: 요즘 인기, 살림 필수템).
- 2~5장면은 상품명 속 특징을 하나씩, 생활 장면에 빗대서 재미있게. 마지막 장면은 가벼운 웃음 포인트로 마무리.
- say는 말하듯 짧은 한 문장(25자 이내, 숫자는 읽는 대로 '9리터').
- cap은 2줄, 한 줄 12자 이내, 가장 센 단어 하나를 [대괄호]로 감싼다.
- threads_text: 400자 이내. 친구한테 카톡 보내듯 자연스럽게. 첫 줄 후킹 → 왜 눈에 띄었는지 한두 줄 → 상품명 → 특징 2~3개를 문장 속에 자연스럽게 → 마지막 줄에 정확히 "{{LINK}}" 를 쓴다. 해시태그 2개. 이모지 1~2개.
- insta_hook: 인스타 캡션 첫 줄, 사람 말투 후킹 한 문장 + 이모지 1개. features: 상품명 속 특징 4개를 짧은 구어체로. hashtags: 해시태그 5개(# 포함).
JSON 형식: {{"badge":"","scenes":[{{"say":"","cap":["",""]}}x5],"threads_text":"","insta_hook":"","features":["",""],"hashtags":["#"]}}"""
        txt, errs = None, []
        for model in order[:4]:  # 무료 한도가 남은 모델을 차례로 시도
            r = requests.post(f"https://generativelanguage.googleapis.com/v1beta/{model}:generateContent?key={key}", timeout=60,
                              json={"contents": [{"parts": [{"text": prompt}]}],
                                    "generationConfig": {"responseMimeType": "application/json", "temperature": 0.9}})
            rj = r.json()
            if "candidates" in rj:
                txt = rj["candidates"][0]["content"]["parts"][0]["text"]; break
            errs.append(f"{model}:{rj.get('error', {}).get('code')}")
        if txt is None:
            raise RuntimeError("모든 모델 실패 " + ", ".join(errs))
        g = json.loads(txt)
        fake = re.compile(r"샀어|샀는데|담았|담아버|써보니|써 보니|먹어보니|마셔보니|우리 집|저희 집|제가 써|직접 써|사용해보니|써봤")
        if fake.search(json.dumps(g, ensure_ascii=False)):
            raise RuntimeError("직접 써 본 척 표현 포함 → 템플릿으로 대체")
        assert len(g["scenes"]) >= 4 and all(len(s["cap"]) == 2 for s in g["scenes"])
        assert "{LINK}" in g["threads_text"] and len(g["threads_text"]) < 480
        print("후킹 대본: Gemini", model)
        return g
    except Exception as e:
        print("::warning::Gemini 대본 실패 → 템플릿 사용:", str(e)[:200])
        return None


# ---------------- 후킹 대본: 템플릿 ----------------
HOOKS = [
    ("아니 근데 이거 아직 모르는 사람 있어요?", ["아니 근데 이거", "[아직 몰라요]?"]),
    ("요즘 쿠팡 장바구니에 다들 이거 있더라고요.", ["요즘 장바구니", "[필수 멤버]"]),
    ("솔직히 이거 보고 살짝 놀랐거든요.", ["솔직히 이거", "[살짝 놀람]"]),
    ("자취생 여러분, 잠깐만 보고 가세요.", ["자취생 여러분", "[잠깐만요]"]),
    ("살림 좀 해본 사람들은 다 아는 그거요.", ["살림러들은", "[다 아는 그거]"]),
    ("이거 하나로 잔소리 줄어든 집 있대요.", ["이거 하나로", "[잔소리 감소]?"]),
]
BADGES = ["요즘 인기", "살림 필수템", "베스트 상품", "장바구니 1순위", "오늘의 추천"]
FEAT_SAY = ["일단 {f}, 이게 제일 눈에 띄더라고요.", "거기다 {f}까지 챙겼어요.", "{f}, 이거 은근 중요하거든요.", "포인트는 바로 {f}예요.", "{f}라니, 이건 좀 반칙 아닌가요?"]
FEAT_CAP = [["[{f}]", "이게 핵심"], ["{f}까지", "[챙겼다]"], ["놓치면 아쉬운", "[{f}]"], ["포인트는", "[{f}]"], ["눈여겨볼 점", "[{f}]"]]


def template_copy(p, seed):
    rnd = random.Random(seed)
    s = short_name(p["name"], 14)
    feats = feature_tokens(p["name"]) or [s]
    while len(feats) < 4:
        feats.append(feats[len(feats) % max(1, len(feats))])
    say, cap = rnd.choice(HOOKS)
    scenes = [{"say": say.format(s=s), "cap": [c.format(s2=short_name(p["name"], 8)) for c in cap]}]
    idx = list(range(len(FEAT_SAY))); rnd.shuffle(idx)
    for i, f in enumerate(feats[:4]):
        k = idx[i % len(idx)]
        scenes.append({"say": speakable(FEAT_SAY[k].format(f=f)), "cap": [c.format(f=f[:10]) for c in FEAT_CAP[k]]})
    hook_line = scenes[0]["say"]
    th = f"{hook_line}\n\n{short_name(p['name'], 40)}\n" + "\n".join(f"- {f}" for f in feats[:3]) + "\n\n{LINK}\n\n#쿠팡추천 #살림템"
    tags = ["#쿠팡추천", "#살림템", "#꿀템추천", "#" + re.sub(r"\W", "", feats[0])[:12], "#생활용품"]
    return {"badge": rnd.choice(BADGES), "scenes": scenes, "threads_text": th, "insta_hook": hook_line + " 👀",
            "features": feats[:4], "hashtags": tags}


# ---------------- 준비 ----------------
def build_video(js_path, mp4):
    subprocess.run([sys.executable, "make_product_short.py", js_path, mp4], check=True)


def write_caps(name, p, g, link):
    th = g["threads_text"].replace("{LINK}", f"구매 링크 👉 {link}") + f"\n\n{DISCLOSURE}"
    ig = (f"{g['insta_hook']}\n\n{p['name']}\n" + "\n".join(f"✔ {f}" for f in g["features"][:5]) +
          f"\n\n👉 구매 링크: {link.replace('https://', '')}\n(주소를 복사해서 열어주세요)\n\n{DISCLOSURE}\n\n" + " ".join(g["hashtags"][:5]))
    open(f"{SCRIPTS}/{name}.threads.txt", "w", encoding="utf-8").write(th[:500])
    open(f"{SCRIPTS}/{name}.insta.txt", "w", encoding="utf-8").write(ig[:2200])


def prepare_threads():
    since = (NOW - timedelta(hours=6)).strftime("%Y-%m-%d %H:%M")
    retry = [e for e in jload(LOG, []) if not e.get("threads") and e.get("tries", 0) < 3 and e["time"] >= since
             and os.path.exists(f"{SCRIPTS}/{e['name']}.json")]
    if retry:
        e = retry[-1]; name = e["name"]
        print("지난번 실패한 글 재게시:", e["product"], "시도", e.get("tries", 0) + 1)
        os.makedirs("site", exist_ok=True)
        build_video(f"{SCRIPTS}/{name}.json", f"site/short-{name}.mp4")
        out("name", name); out("caption", f"{SCRIPTS}/{name}.threads.txt"); return
    items = candidates()
    p = choose(items)
    if not p:
        print("::error::올릴 상품 후보가 없습니다"); out("skip", "true"); return
    sub = "t" + NOW.strftime("%y%m%d%H%M")
    # 상품마다 다른 subId로 짧은 링크를 만들어 클릭을 따로 센다
    d = cp.call("POST", cp.BASE + "/deeplink", body={"coupangUrls": [f"https://www.coupang.com/vp/products/{p['productId']}"], "subId": sub}) or []
    link = (d[0].get("shortenUrl") if d else None) or p.get("short_url") or p["url"]
    name = NOW.strftime("%Y%m%d-%H%M") + "-" + hashlib.md5(str(p["productId"]).encode()).hexdigest()[:6]
    g = gemini_copy(p) or gemini_copy(p) or template_copy(p, name)  # 실패하면 Gemini 1번 더
    crops = [None, [0.1, 0.05, 0.9, 0.95], None, [0.15, 0.1, 0.85, 0.8], None]
    scenes = []
    for i, s in enumerate(g["scenes"][:5]):
        sc = {"img": 0, "say": speakable(s["say"])[:60], "cap": [c[:16] for c in s["cap"][:2]]}
        if i == 0: sc["badge"] = g.get("badge", "요즘 인기")[:8]
        if crops[i]: sc["crop"] = crops[i]
        scenes.append(sc)
    os.makedirs(SCRIPTS, exist_ok=True)
    js = {"name": name, "product": short_name(p["name"], 20), "coupang_product_id": p["productId"], "images": [p["image"]],
          "voice": random.Random(name).choice(["female", "female", "male"]), "disclosure": DISCLOSURE, "scenes": scenes,
          "cta": ["가격·구매는", "[링크]에서 확인!"], "cta_say": "가격과 구매는 링크에서 확인하세요."}
    jsave(f"{SCRIPTS}/{name}.json", js)
    write_caps(name, p, g, link)
    os.makedirs("site", exist_ok=True)
    build_video(f"{SCRIPTS}/{name}.json", f"site/short-{name}.mp4")
    log = jload(LOG, [])
    log.append({"name": name, "productId": p["productId"], "product": p["name"], "category": p.get("category", ""),
                "subId": sub, "link": link, "time": NOW.strftime("%Y-%m-%d %H:%M"), "threads": False, "insta": False})
    jsave(LOG, log)
    out("name", name); out("caption", f"{SCRIPTS}/{name}.threads.txt")
    print("상품:", p["name"], "/ 링크:", link)


def clicks_by_subid():
    res = {}
    start = (NOW - timedelta(days=1)).strftime("%Y%m%d"); end = NOW.strftime("%Y%m%d")
    try:
        d = cp.call("GET", cp.BASE + "/reports/clicks", f"startDate={start}&endDate={end}") or []
        for row in d if isinstance(d, list) else d.get("data", []):
            k = row.get("subId") or row.get("subid") or ""
            res[k] = res.get(k, 0) + int(row.get("click") or row.get("clicks") or row.get("clickCount") or 0)
    except SystemExit as e:
        print("::warning::클릭 리포트 조회 실패", e)
    return res


def prepare_insta():
    log = jload(LOG, [])
    since = (NOW - timedelta(hours=24)).strftime("%Y-%m-%d %H:%M")
    pool = [e for e in log if e.get("threads") and not e.get("insta") and e["time"] >= since]
    if not pool:
        print("인스타에 올릴 후보(최근 24시간 스레드 영상)가 없습니다"); out("skip", "true"); return
    clicks = clicks_by_subid()
    for e in pool: e["clicks"] = clicks.get(e["subId"], 0)
    # 쿠팡 클릭은 집계가 늦으므로 스레드 조회수·좋아요도 함께 본다 (클릭 > 조회수 순)
    tok = os.environ.get("THREADS_ACCESS_TOKEN", "").strip()
    for e in pool:
        e["views"] = 0
        if tok and e.get("threads_id"):
            try:
                j = requests.get(f"https://graph.threads.net/v1.0/{e['threads_id']}/insights",
                                 params={"metric": "views,likes,shares", "access_token": tok}, timeout=20).json()
                vals = {m["name"]: (m.get("values") or [{}])[0].get("value", 0) or (m.get("total_value") or {}).get("value", 0) for m in j.get("data", [])}
                e["views"] = vals.get("views", 0) + 20 * vals.get("likes", 0) + 50 * vals.get("shares", 0)
                if "error" in j: print("::notice::스레드 조회수 조회 불가:", j["error"].get("message", "")[:120])
            except Exception as ex:
                print("::notice::스레드 조회수 조회 실패", str(ex)[:100])
    best = sorted(pool, key=lambda e: (e["clicks"], e["views"], e["time"]), reverse=True)[0]
    print("순위(클릭, 조회점수):", [(e["product"][:20], e["clicks"], e["views"]) for e in sorted(pool, key=lambda e: (-e["clicks"], -e["views"]))[:5]])
    name = best["name"]
    os.makedirs("site", exist_ok=True)
    build_video(f"{SCRIPTS}/{name}.json", f"site/short-{name}.mp4")
    out("name", name); out("caption", f"{SCRIPTS}/{name}.insta.txt")
    print("인스타 선택:", best["product"], "클릭", best["clicks"])


def fail(kind, name, reason):
    log = jload(LOG, [])
    for e in log:
        if e["name"] == name:
            e["tries"] = e.get("tries", 0) + 1; e["last_error"] = reason[:200]
    jsave(LOG, log)


def mark(kind, name, post_id=""):
    if kind == "insta" and os.path.exists(f"site/short-{name}.mp4"):  # 인스타에 올린 영상은 네이버 클립용으로 보관
        os.makedirs("naver-clip", exist_ok=True)
        import shutil
        shutil.copy(f"site/short-{name}.mp4", f"naver-clip/{name}.mp4")
        shutil.copy(f"{SCRIPTS}/{name}.threads.txt", f"naver-clip/{name}_클립문구.txt")
        cut = (NOW - timedelta(days=14)).strftime("%Y%m%d")
        for f in os.listdir("naver-clip"):
            if f[:8].isdigit() and f[:8] < cut: os.remove(os.path.join("naver-clip", f))
    log = jload(LOG, [])
    for e in log:
        if e["name"] == name:
            e[kind] = True
            if post_id: e[f"{kind}_id"] = post_id
            if kind == "insta":
                ids = jload("coupang/posted.json", [])
                if e["productId"] not in ids: ids.append(e["productId"]); jsave("coupang/posted.json", ids)
    jsave(LOG, log[-400:])
    # 오래된 대본 정리 (14일)
    cutoff = (NOW - timedelta(days=14)).strftime("%Y%m%d")
    for f in os.listdir(SCRIPTS):
        if f[:8].isdigit() and f[:8] < cutoff:
            os.remove(os.path.join(SCRIPTS, f))


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "prepare":
        prepare_threads() if sys.argv[2] == "threads" else prepare_insta()
    elif cmd == "gemtest":
        d = jload("coupang/candidates.json", {}); g = gemini_copy(d["items"][0]); print(json.dumps(g, ensure_ascii=False)[:1500])
    elif cmd == "clicks":
        start = (NOW - timedelta(days=1)).strftime("%Y%m%d"); end = NOW.strftime("%Y%m%d")
        d = cp.call("GET", cp.BASE + "/reports/clicks", f"startDate={start}&endDate={end}")
        print("원본:", json.dumps(d, ensure_ascii=False)[:800])
        print(clicks_by_subid())
    elif cmd == "fail":
        fail(sys.argv[2], sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else "")
    elif cmd == "mark":
        mark(sys.argv[2], sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else "")
