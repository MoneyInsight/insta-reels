"""쇼핑 커넥트 링크(naver.me/...)에서 상품명·가격·특징·사진 주소를 뽑는다.
깃허브 서버의 헤드리스 크롬으로 브랜드 커넥트 중간 페이지를 지나 실제 상품 페이지까지 따라간다.
사용법: python product_info.py <링크> <저장할 json>
"""
import json, re, sys
from playwright.sync_api import sync_playwright
url, out = sys.argv[1], sys.argv[2]
UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(user_agent=UA, locale="ko-KR", viewport={"width": 430, "height": 932})
    caught = []  # 중간 페이지가 주고받는 데이터(JSON)를 모아 둔다
    def on_resp(resp):
        try:
            if "json" in (resp.headers.get("content-type") or "") and "naver" in resp.url:
                caught.append({"url": resp.url.split("?")[0], "status": resp.status, "body": resp.json()})
        except Exception: pass
    pg.on("response", on_resp)
    pg.goto(url, wait_until="domcontentloaded", timeout=60000)
    for _ in range(30):  # 상품 페이지에 도착할 때까지 기다린다
        if re.search(r"smartstore|brand\.naver|shopping\.naver|/products/", pg.url) and "brandconnect" not in pg.url: break
        pg.wait_for_timeout(1000)
    pg.wait_for_timeout(4000)
    for _ in range(6): pg.mouse.wheel(0, 1500); pg.wait_for_timeout(700)  # 상세 이미지 불러오기
    print("최종 주소:", pg.url.split("?")[0])
    info = pg.evaluate("""() => {
      const m = p => (document.querySelector(`meta[property="${p}"]`)||{}).content || "";
      const imgs = [...new Set([...document.images].map(i => (i.currentSrc||i.src||"").split("?")[0])
                   .filter(s => /shop-phinf|shopping-phinf|shopping\\.pstatic/.test(s)))];
      return {title: m("og:title") || document.title, desc: m("og:description"), og_image: m("og:image"),
              images: imgs, text: document.body.innerText.slice(0, 4000)};
    }""")
    if not info["images"] and not info["title"]:
        pg.screenshot(path="page.png", full_page=False)
    b.close()
info["final_url"] = pg.url.split("?")[0]
info["api"] = caught
for c in caught: print("API:", c["url"], c["status"], json.dumps(c["body"], ensure_ascii=False)[:1500])
json.dump(info, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(json.dumps({k: v for k, v in info.items() if k != "text"}, ensure_ascii=False, indent=1)[:2500])
print("본문 일부:", info["text"][:1500])
