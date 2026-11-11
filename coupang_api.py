"""쿠팡 파트너스 Open API로 숏츠 후보 상품을 모은다.
사용법: COUPANG_ACCESS_KEY=... COUPANG_SECRET_KEY=... python coupang_api.py pick [키워드 ...]
결과: coupang/candidates.json (이미 올린 상품 coupang/posted.json 은 제외)
"""
import hashlib, hmac, json, os, sys, time, urllib.parse
import requests

AK = os.environ.get("COUPANG_ACCESS_KEY", "").strip()
SK = os.environ.get("COUPANG_SECRET_KEY", "").strip()
HOST = "https://api-gateway.coupang.com"
BASE = "/v2/providers/affiliate_open_api/apis/openapi/v1"
SUB_ID = os.environ.get("COUPANG_SUB_ID", "shorts")
# 숏츠로 보여주기 좋은 생활 카테고리 위주 (식품·주방·생활·홈인테리어·가전·스포츠·자동차·반려동물·헬스)
CATEGORIES = {1012: "식품", 1013: "주방용품", 1014: "생활용품", 1015: "홈인테리어", 1016: "가전디지털",
              1017: "스포츠/레저", 1018: "자동차용품", 1029: "반려동물용품", 1024: "헬스/건강식품"}


def call(method, path, query="", body=None):
    if not AK or not SK:
        raise SystemExit("::error::COUPANG_ACCESS_KEY / COUPANG_SECRET_KEY 비밀값이 없습니다")
    dt = time.strftime("%y%m%dT%H%M%SZ", time.gmtime())
    msg = dt + method + path + query
    sig = hmac.new(SK.encode(), msg.encode(), hashlib.sha256).hexdigest()
    auth = f"CEA algorithm=HmacSHA256, access-key={AK}, signed-date={dt}, signature={sig}"
    url = HOST + path + (("?" + query) if query else "")
    r = requests.request(method, url, headers={"Authorization": auth, "Content-Type": "application/json;charset=UTF-8"},
                         data=json.dumps(body) if body is not None else None, timeout=30)
    try:
        j = r.json()
    except Exception:
        raise SystemExit(f"::error::쿠팡 API 응답 오류 {r.status_code}: {r.text[:300]}")
    if r.status_code != 200 or str(j.get("rCode", "0")) != "0":
        print(f"::warning::쿠팡 API {path} → {r.status_code} {str(j)[:300]}")
        return None
    return j.get("data")


def norm(p, source):
    return {"productId": p.get("productId"), "name": p.get("productName"), "price": p.get("productPrice"),
            "image": p.get("productImage"), "url": p.get("productUrl"), "category": p.get("categoryName", ""),
            "rocket": p.get("isRocket", False), "free_shipping": p.get("isFreeShipping", False),
            "rank": p.get("rank"), "source": source}


def short_links(urls):
    out = {}
    for i in range(0, len(urls), 20):
        d = call("POST", BASE + "/deeplink", body={"coupangUrls": urls[i:i + 20], "subId": SUB_ID}) or []
        for x in d:
            out[x.get("originalUrl")] = x.get("shortenUrl") or x.get("landingUrl")
    return out


def pick(keywords):
    posted = set()
    if os.path.exists("coupang/posted.json"):
        posted = {str(x) for x in json.load(open("coupang/posted.json", encoding="utf-8"))}
    found, seen = [], set()
    def add(items, source):
        for p in items or []:
            pid = str(p.get("productId"))
            if pid in seen or pid in posted or not p.get("productImage"): continue
            if "AFFTDP" in (p.get("productUrl") or ""): continue  # 여행·숙박·티켓 상품은 숏츠에 맞지 않아 제외
            seen.add(pid); found.append(norm(p, source))
    add(call("GET", BASE + "/products/goldbox", f"subId={SUB_ID}&imageSize=700x700"), "골드박스")
    for cid, cname in CATEGORIES.items():
        add(call("GET", BASE + f"/products/bestcategories/{cid}", f"limit=10&subId={SUB_ID}&imageSize=700x700"), f"베스트-{cname}")
        time.sleep(1)
    for kw in keywords:
        q = urllib.parse.urlencode({"keyword": kw, "limit": 10, "subId": SUB_ID, "imageSize": "700x700"})
        d = call("GET", BASE + "/products/search", q)
        add((d or {}).get("productData") if isinstance(d, dict) else d, f"검색-{kw}")
        time.sleep(1)
    # 짧은 제휴 링크(link.coupang.com/a/...)는 일반 상품 주소를 딥링크 API에 넣어야 만들어진다
    for p in found:
        p["product_page"] = f"https://www.coupang.com/vp/products/{p['productId']}"
    links = short_links([p["product_page"] for p in found[:40]])
    print(f"짧은 링크 {len(links)}개 생성")
    for p in found:
        p["short_url"] = links.get(p["product_page"]) or p["url"]
    os.makedirs("coupang", exist_ok=True)
    json.dump({"updated": time.strftime("%Y-%m-%d %H:%M", time.localtime()), "count": len(found), "items": found[:40]},
              open("coupang/candidates.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"후보 {len(found)}개 저장 (이미 올린 상품 {len(posted)}개 제외)")
    for p in found[:15]:
        print(f"- [{p['source']}] {p['name'][:50]} / {p['price']}원 / 로켓={p['rocket']}")


if __name__ == "__main__":
    if sys.argv[1:2] == ["pick"]:
        pick(sys.argv[2:])
