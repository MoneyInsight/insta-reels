"""카드뉴스용 상품 찾기: python card_search.py 키워드 → coupang/cardnews/search.json + 상품 사진"""
import io, json, os, sys, urllib.parse, requests
import coupang_api as cp
from PIL import Image
kw = sys.argv[1]; os.makedirs("coupang/cardnews", exist_ok=True)
q = urllib.parse.urlencode({"keyword": kw, "limit": 10, "subId": "card", "imageSize": "700x700"})
d = cp.call("GET", cp.BASE + "/products/search", q) or {}
items = [cp.norm(p, kw) for p in (d.get("productData") if isinstance(d, dict) else d) or []]
links = cp.short_links([f"https://www.coupang.com/vp/products/{p['productId']}" for p in items]) if items else {}
for p in items:
    p["link"] = links.get(f"https://www.coupang.com/vp/products/{p['productId']}", "")
    try:
        im = Image.open(io.BytesIO(requests.get(p["image"], timeout=20).content)).convert("RGB")
        im.save(f"coupang/cardnews/p{p['productId']}.jpg", quality=90)
    except Exception as e:
        print("사진 실패", p["productId"], e)
json.dump(items, open("coupang/cardnews/search.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
for p in items: print(p["productId"], p["name"][:40], p["price"], p["rocket"], p["link"])
