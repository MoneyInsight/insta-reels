"""왜 클릭이 안 나오는지 진단: 인스타 릴스 시청시간·도달·저장·프로필 링크 클릭, 스레드 반응, 쿠팡 클릭"""
import os, json, requests, datetime
TH = os.environ["THREADS_ACCESS_TOKEN"]; IG = os.environ["IG_ACCESS_TOKEN"]
G = "https://graph.instagram.com/v21.0"; T = "https://graph.threads.net/v1.0"
out = {"ig_posts": [], "ig_account": {}, "th_posts": [], "th_account": {}, "links_page": None}
media = requests.get(f"{G}/me/media", params={"fields": "id,caption,media_type,timestamp,permalink", "limit": 40, "access_token": IG}).json().get("data", [])
for m in media[:40]:
    row = {"t": m["timestamp"][5:16], "cap": (m.get("caption") or "")[:30].replace("\n", " ")}
    for met in ["views", "reach", "ig_reels_avg_watch_time", "ig_reels_video_view_total_time", "likes", "comments", "saved", "shares", "total_interactions"]:
        r = requests.get(f"{G}/{m['id']}/insights", params={"metric": met, "access_token": IG}).json()
        try: row[met] = r["data"][0]["values"][0]["value"]
        except Exception: row[met] = None
    out["ig_posts"].append(row)
since = int((datetime.datetime.utcnow() - datetime.timedelta(days=7)).timestamp()); until = int(datetime.datetime.utcnow().timestamp())
for met in ["reach", "profile_views", "website_clicks", "profile_links_taps", "follower_count", "accounts_engaged", "views"]:
    r = requests.get(f"{G}/me/insights", params={"metric": met, "period": "day", "metric_type": "total_value", "since": since, "until": until, "access_token": IG}).json()
    out["ig_account"][met] = r.get("data", [{}])[0].get("total_value", {}).get("value") if "data" in r and r["data"] else r.get("error", {}).get("message", "")[:80]
me = requests.get(f"{G}/me", params={"fields": "username,followers_count,biography,website", "access_token": IG}).json()
out["ig_profile"] = me
th = requests.get(f"{T}/me/threads", params={"fields": "id,text,timestamp", "limit": 40, "access_token": TH}).json().get("data", [])
for p in th[:40]:
    r = requests.get(f"{T}/{p['id']}/insights", params={"metric": "views,likes,replies,reposts,quotes,shares", "access_token": TH}).json()
    row = {"t": p["timestamp"][5:16], "txt": (p.get("text") or "")[:30].replace("\n", " ")}
    for d in r.get("data", []): row[d["name"]] = d["values"][0]["value"] if d.get("values") else d.get("total_value", {}).get("value")
    out["th_posts"].append(row)
for met in ["views", "likes", "replies", "followers_count", "clicks"]:
    r = requests.get(f"{T}/me/threads_insights", params={"metric": met, "since": since, "until": until, "access_token": TH}).json()
    out["th_account"][met] = r.get("data", [{}])[0].get("total_value", r.get("data", [{}])[0].get("link_total_values")) if r.get("data") else r.get("error", {}).get("message", "")[:80]
    if met == "clicks" and r.get("data"): out["th_account"]["clicks_raw"] = r["data"][0]
out["th_profile"] = requests.get(f"{T}/me", params={"fields": "username,threads_biography", "access_token": TH}).json()
json.dump(out, open("coupang/deep_insights.json", "w"), ensure_ascii=False, indent=1)
print(json.dumps(out, ensure_ascii=False)[:3000])
