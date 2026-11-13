"""CC-BY(크리에이티브 커먼즈) 유튜브 영상을 조회수 순으로 모아 1~1000위 대기열을 만든다.
사용법: YT_API_KEY=... python comic/rank.py   →  comic/queue.json
- 검색 1회 = 100 단위(하루 10,000) → 키워드 40개 × 최대 5쪽까지 돌려도 한 번에 끝난다(이미 있으면 이어서 보충).
- 실제 라이선스(status.license == creativeCommon)를 영상마다 다시 확인한다.
"""
import json, os, re, sys, time
import requests

KEY = os.environ.get("YT_API_KEY", "").strip()
if not KEY: print("::error::YT_API_KEY 비밀값이 없습니다"); raise SystemExit(1)
Q = "comic/queue.json"
API = "https://www.googleapis.com/youtube/v3"
WORDS = ["funny", "funny animals", "funny cats", "funny dogs", "fail", "fails compilation", "prank", "try not to laugh",
         "funny baby", "cute animals", "funny moments", "comedy sketch", "hilarious", "epic fail", "funny kids",
         "wholesome", "heartwarming", "animal rescue", "surprise reaction", "dog reunion", "soldier coming home",
         "funny parrot", "funny goat", "funny monkey", "funny elephant", "cat vs", "dog vs", "funny mascot",
         "slapstick", "blooper", "funny dance", "funny pet", "unexpected", "satisfying", "lucky moments",
         "amazing animals", "kindness", "emotional", "funny grandma", "funny twins"]
BAD = re.compile(r"(music video|official video|lyrics|audio|full movie|episode|news|trailer|podcast|live stream|politic|war|shooting|accident|crash|death|dies|nsfw|sexy|asmr eating)", re.I)
# 허용 카테고리: 22 사람·블로그, 23 코미디, 24 엔터, 15 반려동물·동물, 17 스포츠, 19 여행
OK_CAT = {"22", "23", "24", "15", "17", "19"}


def get(path, **p):
    p["key"] = KEY
    for t in range(3):
        r = requests.get(f"{API}/{path}", params=p, timeout=30)
        if r.status_code == 200: return r.json()
        if r.status_code == 403 and "quota" in r.text: print("::warning::오늘 API 한도 끝 → 지금까지 모은 것으로 저장"); return None
        time.sleep(3 * (t + 1))
    print("::warning::API 실패", path, r.status_code, r.text[:200]); return {}


def iso_sec(d):
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", d or "")
    return sum(int(x or 0) * k for x, k in zip(m.groups(), (3600, 60, 1))) if m else 0


old = json.load(open(Q, encoding="utf-8")) if os.path.exists(Q) else {"items": [], "seen": []}
seen = set(old.get("seen", [])) | {x["id"] for x in old["items"]}
ids = set()
stop = False
for w in WORDS:
    tok = None
    for _ in range(5):
        j = get("search", part="id", q=w, type="video", videoLicense="creativeCommon", order="viewCount",
                maxResults=50, safeSearch="strict", **({"pageToken": tok} if tok else {}))
        if j is None: stop = True; break
        ids |= {x["id"]["videoId"] for x in j.get("items", [])}
        tok = j.get("nextPageToken")
        if not tok: break
    if stop: break
    print(w, "→ 누적", len(ids))

new = []
ids = [i for i in ids if i not in seen]
for k in range(0, len(ids), 50):
    j = get("videos", part="snippet,statistics,status,contentDetails", id=",".join(ids[k:k + 50]))
    if not j: continue
    for v in j.get("items", []):
        sn, st = v["snippet"], v["status"]
        sec = iso_sec(v["contentDetails"]["duration"])
        if st.get("license") != "creativeCommon" or not st.get("embeddable", True): continue
        if sn.get("categoryId") not in OK_CAT or BAD.search(sn["title"]): continue
        if not 8 <= sec <= 900: continue  # 너무 짧거나 너무 긴 영상 제외
        if v["contentDetails"].get("contentRating", {}).get("ytRating") == "ytAgeRestricted": continue
        new.append({"id": v["id"], "title": sn["title"], "channel": sn["channelTitle"], "views": int(v["statistics"].get("viewCount", 0)),
                    "sec": sec, "cat": sn.get("categoryId"), "status": "todo"})

items = old["items"] + new
done = [x for x in items if x["status"] != "todo"]
todo = sorted([x for x in items if x["status"] == "todo"], key=lambda x: -x["views"])
items = done + todo[:max(0, 1000 - len(done))]
for n, x in enumerate(sorted(items, key=lambda x: -x["views"]), 1): x["rank"] = n
json.dump({"items": items, "seen": sorted(seen | set(ids))}, open(Q, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
print(f"대기열 {len(items)}편 (새로 {len(new)}편) / 1위: {items and max(items, key=lambda x: x['views'])['title']}")
