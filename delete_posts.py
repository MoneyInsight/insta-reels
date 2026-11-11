"""어색했던 게시물 삭제: python delete_posts.py NAME ... (스레드는 기록된 ID, 인스타는 캡션의 상품명으로 찾음)"""
import json, os, sys, requests
TH = os.environ["THREADS_ACCESS_TOKEN"]; IG = os.environ["IG_ACCESS_TOKEN"]
log = json.load(open("coupang/auto_log.json", encoding="utf-8"))
names = set(sys.argv[1:])
targets = [e for e in log if e["name"] in names]
ig_media = requests.get("https://graph.instagram.com/v21.0/me/media", params={"fields": "id,caption,timestamp", "limit": 60, "access_token": IG}).json().get("data", [])
th_media = requests.get("https://graph.threads.net/v1.0/me/threads", params={"fields": "id,text,timestamp", "limit": 60, "access_token": TH}).json().get("data", [])
keep_ig = set()
for e in targets:
    key = e["product"].replace("[로켓프레시] ", "")[:14]
    th_ids = {e.get("threads_id")} | {m["id"] for m in th_media if key in (m.get("text") or "")}
    for i in filter(None, th_ids):
        r = requests.delete(f"https://graph.threads.net/v1.0/{i}", params={"access_token": TH}).json()
        print("스레드 삭제", e["product"][:20], i, r)
    if e.get("insta"):
        ids = {e.get("insta_id")} | {m["id"] for m in ig_media if key in (m.get("caption") or "")}
        for i in filter(None, ids):
            r = requests.delete(f"https://graph.instagram.com/v21.0/{i}", params={"access_token": IG}).json()
            print("인스타 삭제", e["product"][:20], i, r)
    e["deleted"] = True
json.dump(log, open("coupang/auto_log.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
