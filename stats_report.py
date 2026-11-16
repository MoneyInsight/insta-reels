"""구독자·조회수 현황 (인스타·스레드·유튜브) + 지난 기록 대비 증가"""
import os, json, requests, datetime
H = "coupang/followers_history.json"
hist = json.load(open(H)) if os.path.exists(H) else []
now = (datetime.datetime.utcnow() + datetime.timedelta(hours=9)).strftime("%Y-%m-%d %H:%M")
r = {"t": now}
IG = os.environ["IG_ACCESS_TOKEN"]; TH = os.environ["THREADS_ACCESS_TOKEN"]
r["ig_followers"] = requests.get("https://graph.instagram.com/v21.0/me", params={"fields": "followers_count,media_count", "access_token": IG}).json().get("followers_count")
d = requests.get("https://graph.threads.net/v1.0/me/threads_insights", params={"metric": "followers_count", "access_token": TH}).json()
try: r["th_followers"] = d["data"][0]["total_value"]["value"]
except Exception: r["th_followers"] = None
K = os.environ["YT_API_KEY"]; Y = "https://www.googleapis.com/youtube/v3"
ids = []
for f in ("comic/youtube_log.json", "coupang/youtube_log.json"):
    if os.path.exists(f):
        for x in json.load(open(f, encoding="utf-8")):
            v = x.get("id") or x.get("video_id") or x.get("yt_id")
            if v and v not in ids: ids.append(v)
vids = []
for i in range(0, len(ids), 50):
    vs = requests.get(f"{Y}/videos", params={"part": "snippet,statistics", "id": ",".join(ids[i:i + 50]), "key": K}).json()
    for v in vs.get("items", []):
        vids.append({"id": v["id"], "ch": v["snippet"]["channelId"], "t": v["snippet"]["publishedAt"][5:16].replace("T", " "), "title": v["snippet"]["title"][:40],
                     "views": int(v["statistics"].get("viewCount", 0)), "likes": int(v["statistics"].get("likeCount", 0))})
vids.sort(key=lambda x: x["t"], reverse=True)
r["yt_recent"] = vids; r["yt_tracked"] = len(ids)
if vids:
    c = requests.get(f"{Y}/channels", params={"part": "snippet,statistics", "id": vids[0]["ch"], "key": K}).json()["items"][0]
    st = c["statistics"]; r["yt_channel"] = c["snippet"]["title"]
    r["yt_subs"] = int(st.get("subscriberCount", 0)); r["yt_views"] = int(st.get("viewCount", 0)); r["yt_videos"] = int(st.get("videoCount", 0))
else:
    r["yt_channel"] = None; r["yt_subs"] = r["yt_views"] = r["yt_videos"] = None
hist.append({k: r[k] for k in ("t", "ig_followers", "th_followers", "yt_subs", "yt_views", "yt_videos")})
json.dump(hist, open(H, "w"), ensure_ascii=False, indent=1)
json.dump(r, open("coupang/stats_now.json", "w"), ensure_ascii=False, indent=1)
print(json.dumps(r, ensure_ascii=False, indent=1)[:4000])
