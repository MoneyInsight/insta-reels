"""공개 영상 주소를 인스타그램 릴스로 게시한다 (Instagram API with Instagram Login).
사용법: IG_ACCESS_TOKEN=... python post_instagram.py <영상URL> <캡션파일>
"""
import os, sys, time, requests

G = "https://graph.instagram.com/v21.0"
TOKEN = os.environ["IG_ACCESS_TOKEN"]
video_url, caption_file = sys.argv[1], sys.argv[2]
caption = open(caption_file, encoding="utf-8").read()[:2200]

def call(method, path, **params):
    params["access_token"] = TOKEN
    r = requests.request(method, f"{G}/{path}", params=params if method == "GET" else None,
                         data=params if method == "POST" else None, timeout=60)
    j = r.json()
    if "error" in j:
        raise SystemExit(f"인스타 API 오류: {j['error'].get('message')}")
    return j

me = call("GET", "me", fields="user_id,username")
ig = me["user_id"]
print("계정:", me.get("username"))

cid = call("POST", f"{ig}/media", media_type="REELS", video_url=video_url,
           caption=caption, share_to_feed="true")["id"]
print("업로드 처리 중:", cid)

for _ in range(60):  # 최대 10분 대기
    st = call("GET", cid, fields="status_code,status").get("status_code")
    if st == "FINISHED": break
    if st in ("ERROR", "EXPIRED"):
        raise SystemExit(f"영상 처리 실패: {st}")
    time.sleep(10)
else:
    raise SystemExit("영상 처리 시간 초과")

pub = call("POST", f"{ig}/media_publish", creation_id=cid)
print("게시 완료! 미디어 ID:", pub["id"])
