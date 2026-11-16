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
tok = requests.post("https://oauth2.googleapis.com/token", data={"client_id": os.environ["YTC_CLIENT_ID"], "client_secret": os.environ["YTC_CLIENT_SECRET"],
                    "refresh_token": os.environ["YTC_REFRESH_TOKEN"], "grant_type": "refresh_token"}).json().get("access_token")
A = {"Authorization": f"Bearer {tok}"}
ch = requests.get("https://www.googleapis.com/youtube/v3/channels", params={"part": "snippet,statistics,contentDetails", "mine": "true"}, headers=A).json()
it = ch.get("items", [{}])[0]; st = it.get("statistics", {})
r["yt_channel"] = it.get("snippet", {}).get("title"); r["yt_subs"] = int(st.get("subscriberCount", 0)); r["yt_views"] = int(st.get("viewCount", 0)); r["yt_videos"] = int(st.get("videoCount", 0))
up = it.get("contentDetails", {}).get("relatedPlaylists", {}).get("uploads")
vids = []
if up:
    pl = requests.get("https://www.googleapis.com/youtube/v3/playlistItems", params={"part": "contentDetails", "playlistId": up, "maxResults": 30}, headers=A).json()
    ids = ",".join(x["contentDetails"]["videoId"] for x in pl.get("items", []))
    if ids:
        vs = requests.get("https://www.googleapis.com/youtube/v3/videos", params={"part": "snippet,statistics", "id": ids}, headers=A).json()
        for v in vs.get("items", []):
            vids.append({"t": v["snippet"]["publishedAt"][5:16].replace("T", " "), "title": v["snippet"]["title"][:40], "views": int(v["statistics"].get("viewCount", 0)), "likes": int(v["statistics"].get("likeCount", 0))})
r["yt_recent"] = vids
# 유튜브 애널리틱스(일별 구독자 증감·평균 시청) — 권한 없으면 건너뜀
end = datetime.date.today(); start = end - datetime.timedelta(days=7)
an = requests.get("https://youtubeanalytics.googleapis.com/v2/reports", params={"ids": "channel==MINE", "startDate": str(start), "endDate": str(end),
                  "metrics": "views,subscribersGained,subscribersLost,averageViewDuration,averageViewPercentage", "dimensions": "day"}, headers=A).json()
r["yt_daily"] = an.get("rows") or an.get("error", {}).get("message", "")[:120]
hist.append({k: r[k] for k in ("t", "ig_followers", "th_followers", "yt_subs", "yt_views", "yt_videos")})
json.dump(hist, open(H, "w"), ensure_ascii=False, indent=1)
json.dump(r, open("coupang/stats_now.json", "w"), ensure_ascii=False, indent=1)
print(json.dumps(r, ensure_ascii=False, indent=1)[:4000])
