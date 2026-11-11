"""영상별 조회수 리포트: 최근 7일 게시물의 스레드·인스타 조회수와 쿠팡 클릭 → coupang/views.md"""
import json, os, requests
from datetime import datetime, timedelta, timezone
import auto_coupang as ac
TH = os.environ["THREADS_ACCESS_TOKEN"]; IG = os.environ["IG_ACCESS_TOKEN"]
KST = timezone(timedelta(hours=9)); now = datetime.now(KST)
log = [e for e in json.load(open("coupang/auto_log.json", encoding="utf-8"))
       if (e.get("threads") or e.get("insta")) and not e.get("deleted") and e["time"] >= (now - timedelta(days=7)).strftime("%Y-%m-%d")]
ig_media = requests.get("https://graph.instagram.com/v21.0/me/media", params={"fields": "id,caption", "limit": 100, "access_token": IG}).json().get("data", [])


def th_views(i):
    try:
        d = requests.get(f"https://graph.threads.net/v1.0/{i}/insights", params={"metric": "views,likes", "access_token": TH}).json()["data"]
        return {m["name"]: m["values"][0]["value"] for m in d}
    except Exception:
        return {}


def ig_views(i):
    for metric in ("views", "plays"):
        try:
            d = requests.get(f"https://graph.instagram.com/v21.0/{i}/insights", params={"metric": metric + ",likes", "access_token": IG}).json()["data"]
            r = {m["name"]: m["values"][0]["value"] for m in d}; r["views"] = r.get("views", r.get("plays", 0)); return r
        except Exception:
            continue
    return {}


clicks = {}
try:
    s = (now - timedelta(days=7)).strftime("%Y%m%d"); d = ac.cp.call("GET", ac.cp.BASE + "/reports/clicks", f"startDate={s}&endDate={now:%Y%m%d}") or []
    for row in d if isinstance(d, list) else d.get("data", []):
        k = row.get("subId") or ""; clicks[k] = clicks.get(k, 0) + int(row.get("click") or 0)
except BaseException as e:
    print("클릭 조회 실패", e)
rows, tt, ti, tc = [], 0, 0, 0
for e in sorted(log, key=lambda x: x["time"], reverse=True):
    t = th_views(e["threads_id"]) if e.get("threads_id") else {}
    iid = e.get("insta_id") or next((m["id"] for m in ig_media if e["product"].replace("[로켓프레시] ", "")[:14] in (m.get("caption") or "")), None)
    i = ig_views(iid) if iid and e.get("insta") else {}
    c = clicks.get(e.get("subId", ""), 0)
    tt += t.get("views", 0); ti += i.get("views", 0); tc += c
    rows.append(f"| {e['time'][5:]} | {e['product'][:24]} | {t.get('views', '-')} | {i.get('views', '-')} | {c} |")
md = (f"# 영상별 조회수 ({now:%Y-%m-%d %H:%M} 기준, 최근 7일)\n\n합계: 스레드 {tt:,} · 인스타 {ti:,} · 쿠팡 클릭 {tc:,}\n\n"
      "| 게시 | 상품 | 스레드 | 인스타 | 클릭 |\n|---|---|---:|---:|---:|\n" + "\n".join(rows) + "\n\n클릭은 쿠팡 리포트가 하루쯤 늦게 반영된다.\n")
open("coupang/views.md", "w", encoding="utf-8").write(md); print(md)
