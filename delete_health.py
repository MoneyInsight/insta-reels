"""글자가 깨진 건강 카드뉴스 삭제 후 다시 만들 대기열로 되돌림: python delete_health.py NAME ..."""
import json, os, sys, requests
TH = os.environ["THREADS_ACCESS_TOKEN"]; IG = os.environ["IG_ACCESS_TOKEN"]
Q = "coupang/cardnews/queue"; LOG = "coupang/auto_log.json"
log = json.load(open(LOG, encoding="utf-8"))
for n in sys.argv[1:]:
    p = f"{Q}/{n}/spec.json"; s = json.load(open(p, encoding="utf-8"))
    t = s.get("threads_id")
    if t:
        for r in requests.get(f"https://graph.threads.net/v1.0/{t}/replies", params={"fields": "id,username", "access_token": TH}).json().get("data", []):
            if r.get("username") == "durion0506":
                print("스레드 댓글 삭제", n, requests.delete(f"https://graph.threads.net/v1.0/{r['id']}", params={"access_token": TH}).json())
        print("스레드 삭제", n, requests.delete(f"https://graph.threads.net/v1.0/{t}", params={"access_token": TH}).json())
    i = s.get("insta_id")
    if i: print("인스타 삭제", n, requests.delete(f"https://graph.instagram.com/v21.0/{i}", params={"access_token": IG}).json())
    for k in ("threads", "insta", "threads_id", "insta_id", "posted_at"): s.pop(k, None)
    s["status"] = "written"
    json.dump(s, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    for f in ("video.mp4",): 
        if os.path.exists(f"{Q}/{n}/{f}"): os.remove(f"{Q}/{n}/{f}")
    log = [e for e in log if e.get("name") != n]
json.dump(log, open(LOG, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
