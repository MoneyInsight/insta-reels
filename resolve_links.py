"""쇼핑 커넥트 링크들을 스토어·상품번호로 풀어서 links.json 에 저장한다."""
import json, re, sys, requests
out = []
for u in sys.argv[1:]:
    r = requests.get(u, allow_redirects=False, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
    loc = r.headers.get("location", "")
    m = re.search(r"affiliates/(\d+)\?channelProductNo=(\d+)", loc)
    item = {"link": u, "affiliate": m.group(1) if m else None, "product_no": m.group(2) if m else None}
    if m:
        j = requests.get(f"https://gw-brandconnect.naver.com/affiliate/query/affiliate-urls/{m.group(1)}/redirect-url",
                         params={"channelProductNo": m.group(2)}, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
        try: item["target"] = j.json()
        except Exception: item["target"] = j.text[:300]
    print(json.dumps(item, ensure_ascii=False)); out.append(item)
json.dump(out, open("links.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
