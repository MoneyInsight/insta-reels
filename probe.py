import requests, re, time, json
PNO = "4926418912"
UAs = {"pc": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36",
       "bot": "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
       "kakao": "facebookexternalhit/1.1"}
s = requests.Session()
r = s.get("https://gw-brandconnect.naver.com/affiliate/query/redirect/1016150437336672?channelProductNo=" + PNO, allow_redirects=False, timeout=20, headers={"User-Agent": UAs["pc"]})
store_url = r.headers.get("location", "").split("?")[0]; print("STORE URL:", store_url)
store = (re.search(r"naver\.com/([^/]+)/products", store_url) or [None, "main"])[1]
urls = [store_url, f"https://m.smartstore.naver.com/{store}/products/{PNO}", f"https://smartstore.naver.com/main/products/{PNO}",
        f"https://smartstore.naver.com/i/v2/channels/x/products/{PNO}?withWindow=false",
        f"https://search.shopping.naver.com/search/all?query={PNO}",
        f"https://msearch.shopping.naver.com/search/all?query={PNO}",
        f"https://shopping.naver.com/window-products/{PNO}"]
for u in urls:
    for k, ua in UAs.items():
        try:
            x = s.get(u, timeout=20, headers={"User-Agent": ua, "Accept-Language": "ko-KR"})
            t = x.text
            title = (re.search(r'og:title"\s*content="([^"]*)', t) or re.search(r"<title>([^<]*)", t) or [None, ""])[1]
            imgs = len(set(re.findall(r'shop-phinf\.pstatic\.net/[^"\'\\?\s]+', t)))
            print(f"{x.status_code} {k:5} len={len(t):7} imgs={imgs:3} title={title[:60]!r} {u[:90]}")
        except Exception as e: print("ERR", k, u[:80], e)
        time.sleep(1)
