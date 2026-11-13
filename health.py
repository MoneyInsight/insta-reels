"""건강 카드뉴스 자동 발행
대기열: coupang/cardnews/queue/<NAME>/spec.json  (Claude가 매일 작성, status=written)
  python health.py build   → 상품 찾기·카드·내레이션 영상 (Gemini 목소리만, 실패하면 다음 회차로 미룸) → status=ready
  python health.py next    → 가장 오래된 ready 영상을 site/ 로 꺼냄 (게시 준비)
  python health.py mark NAME threads|insta [ID]
spec 형식은 docs/health-cardnews-playbook.md 와 coupang/cardnews/s002/spec.json 참고."""
import io, json, os, shutil, subprocess, sys, urllib.parse
from datetime import datetime, timedelta, timezone
import requests

Q = "coupang/cardnews/queue"; LOG = "coupang/auto_log.json"
KST = timezone(timedelta(hours=9)); NOW = datetime.now(KST)
DISCLOSURE = "이 게시물은 쿠팡 파트너스 활동의 일환으로, 이에 따른 일정액의 수수료를 제공받습니다."
CAUTION = "질환이 있거나 약을 드시는 분은 섭취·사용 전 전문가와 상담하세요."


def jl(p, d=None):
    try: return json.load(open(p, encoding="utf-8"))
    except Exception: return d


def js(p, o): json.dump(o, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def out(k, v):
    if os.environ.get("GITHUB_OUTPUT"): open(os.environ["GITHUB_OUTPUT"], "a").write(f"{k}={v}\n")


def items(status):
    if not os.path.isdir(Q): return []
    r = []
    for n in sorted(os.listdir(Q)):
        s = jl(f"{Q}/{n}/spec.json", {})
        if s.get("status") == status: r.append((n, s))
    return r


def find_product(spec, d):
    import coupang_api as cp
    from PIL import Image
    kw = spec["product_keyword"]; must = spec.get("product_must", "")
    q = urllib.parse.urlencode({"keyword": kw, "limit": 10, "subId": "health", "imageSize": "700x700"})
    data = cp.call("GET", cp.BASE + "/products/search", q) or {}
    rows = data.get("productData") if isinstance(data, dict) else data
    for p in rows or []:
        name = p.get("productName", "")
        if must and must not in name: continue
        if not all(w in name for w in spec.get("product_require", [])): continue
        if spec.get("product_require_any") and not any(w in name for w in spec["product_require_any"]): continue
        if any(w in name for w in spec.get("product_exclude", [])): continue
        if any(w in name for w in ["중고", "리퍼", "렌탈"]): continue
        try:
            im = Image.open(io.BytesIO(requests.get(p["productImage"], timeout=20).content)).convert("RGB")
        except Exception:
            continue
        if min(im.size) < 400: continue
        im.save(f"{d}/product.jpg", quality=92)
        sub = "h" + NOW.strftime("%y%m%d%H%M")
        dl = cp.call("POST", cp.BASE + "/deeplink", body={"coupangUrls": [f"https://www.coupang.com/vp/products/{p['productId']}"], "subId": sub}) or []
        link = (dl[0].get("shortenUrl") if dl else "") or p.get("productUrl")
        return {"id": str(p["productId"]), "name": name, "link": link, "subId": sub, "image": p["productImage"]}
    return None


def build():
    todo = items("written")[:2]  # 한 번에 2편까지 (매시간 돌면서 조금씩)
    if not todo: print("만들 카드뉴스 없음"); return
    for n, spec in todo:
        d = f"{Q}/{n}"
        if not spec.get("product") or not os.path.exists(f"{d}/product.jpg"):
            p = find_product(spec, d)
            if not p: spec["status"] = "failed"; spec["error"] = "맞는 상품 없음"; js(f"{d}/spec.json", spec); print("상품 못 찾음", n); continue
            spec["product"] = p
        for c in spec["cards"]:
            if c["type"] in ("hook", "photo") and not c.get("image"): c["image"] = "product.jpg"
            if c["type"] == "photo":
                c["name"] = spec.get("product_label") or spec["product"]["name"][:30]
                c.setdefault("cta", "프로필 링크에서 확인")
                if spec.get("product_facts"): c["facts"] = spec["product_facts"]
                c["notes"] = spec.get("extra_notes", []) + [CAUTION, DISCLOSURE]
        js(f"{d}/spec.json", spec)
        subprocess.run([sys.executable, "cardnews.py", f"{d}/spec.json", f"{d}/cards"], check=True)
        r = subprocess.run([sys.executable, "cardvideo.py", d, "--gemini-only"], capture_output=True, text=True)
        print(r.stdout[-600:], r.stderr[-600:])
        if (r.returncode != 0 or not os.path.exists(f"{d}/video.mp4")) and not items("ready"):
            # 자연 음성 한도 + 올릴 것이 없으면 → 무료 대체 음성으로 만들어 빈 시간 없이 게시
            r = subprocess.run([sys.executable, "cardvideo.py", d], capture_output=True, text=True)
            print("대체 음성", r.stdout[-300:], r.stderr[-300:])
        if r.returncode != 0 or not os.path.exists(f"{d}/video.mp4"):
            if r.returncode == 3:  # 영상 검수 실패
                spec["qa_fail"] = spec.get("qa_fail", 0) + 1
                if spec["qa_fail"] >= 3: spec["status"] = "failed"; spec["error"] = "영상 검수 3번 실패"
                js(f"{d}/spec.json", spec)
            print("::notice::영상 못 만듦(음성 한도 또는 검수 실패) → 다음 회차에 다시", n); continue
        link = spec["product"]["link"]
        spec["threads_caption"] = spec["threads_text"].strip() + f"\n\n👉 바로가기: {link}\n\n{CAUTION}\n{DISCLOSURE}"
        spec["threads_reply"] = f"📌 {spec.get('product_label') or spec['product']['name'][:30]} 바로가기 👉 {link}\n저장해 두면 필요할 때 다시 보기 편해요.\n{DISCLOSURE}"
        spec["insta_caption"] = (spec["insta_text"].strip() + f"\n\n소개한 상품은 프로필 링크에서 볼 수 있어요.\n\n{CAUTION}\n{DISCLOSURE}\n\n"
                                 + " ".join("#" + h.lstrip("#") for h in spec.get("hashtags", [])[:12]))
        spec["status"] = "ready"; js(f"{d}/spec.json", spec); print("준비 완료", n)


def links_page():
    """인스타 프로필에 걸 '오늘 소개한 상품' 모음 페이지"""
    rows = []
    for n in sorted(os.listdir(Q), reverse=True)[:30] if os.path.isdir(Q) else []:
        s = jl(f"{Q}/{n}/spec.json", {})
        if s.get("status") not in ("posted", "ready") or not s.get("product"): continue
        p = s["product"]
        rows.append(f'<a class="i" href="{p["link"]}" rel="sponsored nofollow"><img src="{p["image"]}" alt=""><div><b>{s.get("topic","")}</b><span>{p["name"]}</span><em>쿠팡에서 보기 ›</em></div></a>')
    if os.path.exists("comic/queue.json"):
        cq = sorted([x for x in jl("comic/queue.json", {"items": []})["items"] if x.get("product")], key=lambda x: x.get("made_at", ""), reverse=True)[:15]
        for x in cq:
            p = x["product"]; lab = (x.get("plan") or {}).get("product_label") or "영상 속 그 상품"
            rows.append(f'<a class="i" href="{p["link"]}" rel="sponsored nofollow"><img src="{p["image"]}" alt=""><div><b>{lab}</b><span>{p["name"]}</span><em>쿠팡에서 보기 ›</em></div></a>')
    html = ("<!DOCTYPE html><html lang='ko'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
            "<title>오늘 소개한 상품</title><style>body{margin:0;font-family:system-ui,sans-serif;background:#faf5ed;color:#221c18}"
            "h1{font-size:20px;padding:18px 16px 4px}p.n{font-size:12px;color:#6e6258;padding:0 16px}"
            ".i{display:flex;gap:12px;align-items:center;margin:10px 12px;padding:10px;background:#fff;border-radius:14px;text-decoration:none;color:inherit}"
            ".i img{width:72px;height:72px;object-fit:cover;border-radius:10px}.i b{display:block;font-size:15px;color:#b3261e}.i span{display:block;font-size:13px}.i em{display:inline-block;margin-top:6px;font-style:normal;font-size:13px;font-weight:700;color:#fff;background:#b3261e;padding:5px 12px;border-radius:20px}</style></head><body>"
            "<h1>오늘 소개한 상품</h1><p class='n'>" + DISCLOSURE + "</p>" + "".join(rows) + "</body></html>")
    os.makedirs("site", exist_ok=True); open("site/links.html", "w", encoding="utf-8").write(html)
    open("site/privacy.html", "w", encoding="utf-8").write(
        "<!DOCTYPE html><html lang='ko'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>개인정보처리방침</title></head>"
        "<body style='font-family:system-ui,sans-serif;max-width:720px;margin:24px auto;padding:0 16px;line-height:1.7'>"
        "<h1>개인정보처리방침</h1><p>이 서비스(comic-shorts-uploader)는 운영자 본인의 유튜브 채널에 직접 만든 영상을 업로드하기 위해서만 YouTube Data API를 사용합니다.</p>"
        "<ul><li>수집 정보: 없음. 다른 사용자의 개인정보나 유튜브 데이터를 수집·저장·공유하지 않습니다.</li>"
        "<li>사용 권한: 운영자 채널에 영상 업로드(youtube.upload)만 사용합니다.</li>"
        "<li>권한 철회: Google 계정 → 보안 → 타사 액세스에서 언제든 철회할 수 있습니다.</li></ul>"
        "<p>문의: 이 페이지를 게시한 운영자에게 연락해 주세요.</p></body></html>")


def nxt():
    r = items("ready")
    links_page()
    if not r: print("올릴 카드뉴스 없음"); out("skip", "true"); return
    n, s = r[0]
    os.makedirs("site", exist_ok=True); shutil.copy(f"{Q}/{n}/video.mp4", f"site/health-{n}.mp4")
    open(f"{Q}/{n}/threads.txt", "w", encoding="utf-8").write(s["threads_caption"])
    if s.get("threads_reply"): open(f"{Q}/{n}/threads_reply.txt", "w", encoding="utf-8").write(s["threads_reply"])
    open(f"{Q}/{n}/insta.txt", "w", encoding="utf-8").write(s["insta_caption"])
    out("name", n); out("caption", f"{Q}/{n}/threads.txt"); out("insta_caption", f"{Q}/{n}/insta.txt")
    print("게시:", s.get("topic"), "/", s["product"]["name"][:30])


def mark(n, kind, pid=""):
    d = f"{Q}/{n}"; s = jl(f"{d}/spec.json", {})
    s[kind] = True; s.setdefault("posted_at", NOW.strftime("%Y-%m-%d %H:%M"))
    if pid.strip(): s[f"{kind}_id"] = pid.strip()
    s["status"] = "posted"; js(f"{d}/spec.json", s)
    log = jl(LOG, [])
    e = next((x for x in log if x.get("name") == n), None)
    if not e:
        e = {"name": n, "productId": s["product"]["id"], "product": "[건강] " + s.get("topic", "") + " · " + s["product"]["name"][:20],
             "subId": s["product"]["subId"], "link": s["product"]["link"], "time": NOW.strftime("%Y-%m-%d %H:%M"), "threads": False, "insta": False}
        log.append(e)
    e[kind] = True
    if pid.strip(): e[f"{kind}_id"] = pid.strip()
    js(LOG, log[-400:])
    if os.path.exists(f"{d}/video.mp4") and kind == "insta":  # 네이버 클립용 보관
        os.makedirs("naver-clip", exist_ok=True); shutil.copy(f"{d}/video.mp4", f"naver-clip/{n}.mp4")


if __name__ == "__main__":
    c = sys.argv[1]
    if c == "build": build()
    elif c == "next": nxt()
    elif c == "mark": mark(sys.argv[2], sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else "")
