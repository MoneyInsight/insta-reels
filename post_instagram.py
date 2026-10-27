"""공개 영상 주소를 인스타그램 릴스로 게시한다 (Instagram API with Instagram Login).
사용법: IG_ACCESS_TOKEN=... python post_instagram.py <영상URL> <캡션파일>
"""
import os, sys, time, requests
 
G = "https://graph.instagram.com/v21.0"
TOKEN = os.environ.get("IG_ACCESS_TOKEN", "").strip()
if not TOKEN:
    print("::error::IG_ACCESS_TOKEN 비밀값이 비어 있습니다"); raise SystemExit(1)
video_url, caption_file = sys.argv[1], sys.argv[2]
caption = open(caption_file, encoding="utf-8").read()[:2200]
 
def call(method, path, **params):
    params["access_token"] = TOKEN
    r = requests.request(method, f"{G}/{path}", params=params if method == "GET" else None,
                         data=params if method == "POST" else None, timeout=60)
    j = r.json()
    if "error" in j:
        e = j["error"]; print(f"::error::인스타 API 오류 [{path.split('/')[-1]}] code={e.get('code')} sub={e.get('error_subcode')}: {e.get('message')}"); raise SystemExit(1)
    return j
 
me = call("GET", "me", fields="user_id,username")
ig = me.get("user_id") or me.get("id")
print("계정:", me.get("username"))
EXPECTED = os.environ.get("IG_USERNAME", "soomndurion").strip().lstrip("@").lower()
if (me.get("username") or "").lower() != EXPECTED:  # 다른 계정 토큰이면 게시하지 않는다
    print(f"::error::토큰 계정({me.get('username')})이 게시할 계정(@{EXPECTED})과 다릅니다. IG_ACCESS_TOKEN을 @{EXPECTED} 토큰으로 바꿔주세요"); raise SystemExit(1)
 
cid = call("POST", f"{ig}/media", media_type="REELS", video_url=video_url,
           caption=caption, share_to_feed="true")["id"]
print("업로드 처리 중:", cid)
 
for _ in range(60):  # 최대 10분 대기
    st = call("GET", cid, fields="status_code,status").get("status_code")
    if st == "FINISHED": break
    if st in ("ERROR", "EXPIRED"):
        print(f"::error::영상 처리 실패: {st} {call('GET', cid, fields='status').get('status')}"); raise SystemExit(1)
    time.sleep(10)
else:
    print("::error::영상 처리 시간 초과"); raise SystemExit(1)
 
pub = call("POST", f"{ig}/media_publish", creation_id=cid)
print("게시 완료! 미디어 ID:", pub["id"])
