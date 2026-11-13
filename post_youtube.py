"""로컬 영상 파일을 유튜브 쇼츠로 업로드한다 (YouTube Data API v3, 재개 가능 업로드).
사용법: YT_CLIENT_ID=... YT_CLIENT_SECRET=... YT_REFRESH_TOKEN=... python post_youtube.py <영상.mp4> <spec.json>
- 비밀값이 없으면 조용히 건너뛴다 (다른 게시는 그대로 진행).
- 유튜브 API 하루 한도(업로드 1회 ≈ 1600 단위 / 하루 10,000) 때문에 하루 최대 YT_DAILY_MAX(기본 5)편,
  직전 업로드 후 YT_GAP_HOURS(기본 3)시간이 지나야 올린다.
"""
import json, os, sys
from datetime import datetime, timedelta, timezone
import requests

CID, SEC, RT = (os.environ.get(k, "").strip() for k in ("YT_CLIENT_ID", "YT_CLIENT_SECRET", "YT_REFRESH_TOKEN"))
if not (CID and SEC and RT):
    print("::notice::유튜브 비밀값(YT_CLIENT_ID/YT_CLIENT_SECRET/YT_REFRESH_TOKEN)이 없어 유튜브 업로드는 건너뜁니다"); raise SystemExit(0)

video, spec_path = sys.argv[1], sys.argv[2]
s = json.load(open(spec_path, encoding="utf-8"))
KST = timezone(timedelta(hours=9)); NOW = datetime.now(KST)
LOG = os.environ.get("YT_LOG", "coupang/youtube_log.json")
log = json.load(open(LOG, encoding="utf-8")) if os.path.exists(LOG) else []
today = [x for x in log if x["time"][:10] == NOW.strftime("%Y-%m-%d")]
MAX, GAP = int(os.environ.get("YT_DAILY_MAX", "5")), float(os.environ.get("YT_GAP_HOURS", "3"))
if len(today) >= MAX:
    print(f"::notice::오늘 유튜브 {MAX}편 다 올림 → 건너뜀"); raise SystemExit(0)
if log and NOW - datetime.strptime(log[-1]["time"], "%Y-%m-%d %H:%M").replace(tzinfo=KST) < timedelta(hours=GAP):
    print(f"::notice::직전 유튜브 업로드 후 {GAP}시간 안 됨 → 건너뜀"); raise SystemExit(0)

tok = requests.post("https://oauth2.googleapis.com/token", data={
    "client_id": CID, "client_secret": SEC, "refresh_token": RT, "grant_type": "refresh_token"}, timeout=30).json()
if "access_token" not in tok:
    print(f"::error::유튜브 토큰 갱신 실패: {tok.get('error')} {tok.get('error_description')} (expired)"); raise SystemExit(1)
H = {"Authorization": f"Bearer {tok['access_token']}"}

if s.get("yt_title"):  # 코믹 쇼츠 등: 제목·설명·태그를 그대로 사용
    title, desc, tags = s["yt_title"][:100], s["yt_description"][:4900], s.get("yt_tags", [])[:20]
    cat = s.get("yt_category", "23")
else:
    title = desc = None; cat = "26"
# 제목: 후킹 문장 + #Shorts (100자 제한)
if title is None:
  hook = next((c for c in s.get("cards", []) if c.get("type") == "hook"), {})
  title = (hook.get("title") or s.get("topic", "")).replace("\n", " ").replace("[", "").replace("]", "").strip()
  title = (title[:85] + " #Shorts").strip()
  link = s["product"]["link"]
  first = (s.get("threads_text") or s.get("insta_text") or "").strip()
  desc = (f"{first}\n\n👉 소개한 상품 바로가기: {link}\n\n"
          f"{s.get('caution', '질환이 있거나 약을 드시는 분은 섭취·사용 전 전문가와 상담하세요.')}\n"
          "이 영상은 쿠팡 파트너스 활동의 일환으로, 이에 따른 일정액의 수수료를 제공받습니다.\n\n"
          + " ".join("#" + h.lstrip("#") for h in (s.get("hashtags", [])[:8] + ["Shorts"])))[:4900]
  tags = [h.lstrip("#") for h in s.get("hashtags", [])][:15] + ["건강정보", "Shorts"]
meta = {"snippet": {"title": title, "description": desc, "tags": tags, "categoryId": cat, "defaultLanguage": "ko"},
        "status": {"privacyStatus": os.environ.get("YT_PRIVACY", "public"), "selfDeclaredMadeForKids": False,
                   "containsSyntheticMedia": True}}

size = os.path.getsize(video)
r = requests.post("https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status",
                  headers={**H, "Content-Type": "application/json; charset=UTF-8",
                           "X-Upload-Content-Type": "video/mp4", "X-Upload-Content-Length": str(size)},
                  data=json.dumps(meta), timeout=60)
if r.status_code != 200:
    print(f"::error::유튜브 업로드 시작 실패 {r.status_code}: {r.text[:400]}"); raise SystemExit(1)
up = requests.put(r.headers["Location"], headers={**H, "Content-Type": "video/mp4"}, data=open(video, "rb"), timeout=600)
j = up.json()
if up.status_code not in (200, 201) or "id" not in j:
    print(f"::error::유튜브 업로드 실패 {up.status_code}: {up.text[:400]}"); raise SystemExit(1)
vid = j["id"]; st = j.get("status", {})
print("게시 완료! 유튜브 ID:", vid, "| 공개상태:", st.get("privacyStatus"), "| https://youtube.com/shorts/" + vid)
if st.get("privacyStatus") != "public":
    print("::warning::유튜브가 영상을 비공개로 두었습니다 — 구글 API 프로젝트 감사(audit) 승인 전에는 API 업로드가 비공개로 제한됩니다")
log.append({"name": os.path.basename(os.path.dirname(spec_path)), "id": vid, "time": NOW.strftime("%Y-%m-%d %H:%M"),
            "privacy": st.get("privacyStatus")})
json.dump(log[-500:], open(LOG, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
