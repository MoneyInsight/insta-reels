"""위키미디어 공용(Commons)의 재사용 허락 영상(CC BY·CC0·퍼블릭 도메인)을 모아 웃긴·귀여운·감동 순으로 대기열을 만든다.
(유튜브는 깃허브 서버에서의 다운로드를 막아서 Commons로 전환. API 키 필요 없음)
사용법: python comic/rank.py   →  comic/queue.json
"""
import json, os, re, time, functools
import requests
print = functools.partial(print, flush=True)

Q = "comic/queue.json"
API = "https://commons.wikimedia.org/w/api.php"
H = {"User-Agent": "comic-shorts-bot/1.0 (github.com/MoneyInsight/insta-reels)"}
# (검색어, 가산점) — 웃김·귀여움·감동 위주
WORDS = [("funny", 30), ("funny animals", 30), ("funny cat", 30), ("funny dog", 30), ("compilation funny", 30), ("fail", 15),
         ("prank", 20), ("cute animals", 25), ("cute baby animals", 25), ("puppy playing", 20), ("kitten playing", 20),
         ("cat jumping", 20), ("dog playing", 15), ("parrot talking", 20), ("goat", 10), ("baby elephant", 20), ("panda playing", 25),
         ("otter", 15), ("penguin", 15), ("monkey", 10), ("raccoon", 15), ("hamster", 15), ("bear cub", 15), ("seal pup", 15),
         ("mascot", 20), ("slapstick", 25), ("comedy", 20), ("laughing", 20), ("reaction", 10), ("surprise", 10),
         ("rescue animal", 20), ("reunion", 20), ("heartwarming", 25), ("kindness", 15), ("dancing", 10), ("stop motion", 10)]
OK_LIC = re.compile(r"^(CC BY \d|CC BY$|CC0|Public domain)", re.I)  # BY-SA(동일조건) 제외
BAD = re.compile(r"\b(war|protest|shooting|riot|attack|surgery|medical|wound|death|dead|killed|hunt|slaughter|politic|speech|lecture|interview|news|trailer|music video|official video|nsfw|naked|HIV|cell|mouse model|ultrasound|microscop|cancer|disease)\b", re.I)
GOOD = re.compile(r"(funny|cute|lol|😂|hilarious|adorable|baby|puppy|kitten|fail|prank|compilation|laugh|playing|dance|reunion|rescue)", re.I)


def strip(h): return re.sub(r"<[^>]+>", "", h or "").replace("&amp;", "&").strip()


def search(q):
    out, cont = [], {}
    for _ in range(2):  # 검색어당 최대 100개
        p = {"action": "query", "format": "json", "generator": "search", "gsrnamespace": 6, "gsrlimit": 50,
             "gsrsearch": f"{q} filetype:video", "prop": "imageinfo", "iiprop": "url|size|extmetadata",
             "iiextmetadatafilter": "LicenseShortName|Artist|Credit|ImageDescription", **cont}
        try: j = requests.get(API, params=p, headers=H, timeout=40).json()
        except Exception as e: print("검색 실패", q, e); break
        out += list(j.get("query", {}).get("pages", {}).values())
        if "continue" not in j: break
        cont = {k: v for k, v in j["continue"].items()}
        time.sleep(0.5)
    return out


old = json.load(open(Q, encoding="utf-8")) if os.path.exists(Q) else {"items": []}
done = [x for x in old.get("items", []) if x.get("src") == "commons" and x["status"] != "todo"]
seen = {x["id"] for x in done}
cand = {}
for w, bonus in WORDS:
    for pg in search(w):
        ii = (pg.get("imageinfo") or [{}])[0]; m = ii.get("extmetadata", {})
        lic = strip(m.get("LicenseShortName", {}).get("value"))
        title = pg["title"][5:]; dur = float(ii.get("duration") or 0); hgt = int(ii.get("height") or 0)
        pid = "c" + str(pg["pageid"])
        if pid in seen or not OK_LIC.search(lic) or BAD.search(title) or not (8 <= dur <= 600) or hgt < 360: continue
        if ii.get("size", 0) > 400e6: continue
        credit = strip(m.get("Credit", {}).get("value")); artist = strip(m.get("Artist", {}).get("value"))[:60] or "Wikimedia Commons"
        score = bonus + (25 if GOOD.search(title) else 0) + (20 if "youtube" in credit.lower() else 0) + min(hgt, 1080) / 54 + (10 if 15 <= dur <= 240 else 0)
        c = cand.get(pid)
        if c: c["score"] += 8; continue  # 여러 검색어에 걸리면 가산
        cand[pid] = {"id": pid, "src": "commons", "title": title.rsplit(".", 1)[0][:120], "channel": artist, "license": lic,
                     "url": ii["url"], "page": ii.get("descriptionurl", ""), "sec": int(dur), "views": 0, "score": round(score, 1), "status": "todo"}
    print(w, "→ 후보", len(cand))
todo = sorted(cand.values(), key=lambda x: -x["score"])[:max(0, 1000 - len(done))]
items = done + todo
for n, x in enumerate(items, 1): x["rank"] = n
json.dump({"items": items, "source": "commons"}, open(Q, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
print(f"대기열 {len(items)}편 / 1위: {todo[0]['title'] if todo else '-'}")
