"""쇼핑 커넥트 링크(naver.me/...)에서 상품명·가격·사진 주소를 뽑는다.
사용법: python product_info.py <링크> <저장할 json>
"""
import json, re, sys, requests
url, out = sys.argv[1], sys.argv[2]
H = {"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
     "Accept-Language": "ko-KR,ko;q=0.9"}
s = requests.Session(); r = s.get(url, headers=H, timeout=30, allow_redirects=True)
print("최종 주소:", r.url.split("?")[0], "응답:", r.status_code, "길이:", len(r.text))
html = r.text
def meta(p):
    m = re.search(rf'<meta[^>]+property="{p}"[^>]+content="([^"]*)"', html) or re.search(rf'<meta[^>]+content="([^"]*)"[^>]+property="{p}"', html)
    return m.group(1) if m else ""
imgs = []
for u in re.findall(r'https://shop-phinf\.pstatic\.net/[^"\'\\\s?]+\.(?:jpg|jpeg|png|webp|gif)', html, re.I):
    if u not in imgs: imgs.append(u)
info = {"final_url": r.url.split("?")[0], "status": r.status_code, "title": meta("og:title"), "desc": meta("og:description"),
        "og_image": meta("og:image"), "images": imgs[:20]}
m = re.search(r'"salePrice"\s*:\s*(\d+)', html); info["price"] = int(m.group(1)) if m else None
m = re.search(r'"discountedSalePrice"\s*:\s*(\d+)', html); info["discounted_price"] = int(m.group(1)) if m else None
json.dump(info, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(json.dumps(info, ensure_ascii=False, indent=1)[:3000])
