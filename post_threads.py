"""공개 영상 주소를 스레드(Threads)에 게시한다 (Threads API).
사용법: THREADS_ACCESS_TOKEN=... python post_threads.py <영상URL> <글 파일>
토큰이 없으면 게시하지 않고 조용히 건너뛴다.
"""
import os, sys, time, requests

G = "https://graph.threads.net/v1.0"
TOKEN = os.environ.get("THREADS_ACCESS_TOKEN", "").strip()
if not TOKEN:
    print("::notice::THREADS_ACCESS_TOKEN 비밀값이 없어 스레드 게시는 건너뜁니다"); raise SystemExit(0)
video_url, text_file = sys.argv[1], sys.argv[2]
text = open(text_file, encoding="utf-8").read().strip()[:500]  # 스레드 글자 수 제한


def call(method, path, **params):
    params["access_token"] = TOKEN
    r = requests.request(method, f"{G}/{path}", params=params if method == "GET" else None,
                         data=params if method == "POST" else None, timeout=60)
    j = r.json()
    if "error" in j:
        e = j["error"]
        print(f"::error::스레드 API 오류 [{path.split('/')[-1]}] code={e.get('code')}: {e.get('message')}")
        raise SystemExit(1)
    return j


me = call("GET", "me", fields="id,username")
uid = me["id"]
print("스레드 계정:", me.get("username"))

cid = call("POST", f"{uid}/threads", media_type="VIDEO", video_url=video_url, text=text)["id"]
print("업로드 처리 중:", cid)

for _ in range(60):  # 최대 10분 대기
    st = call("GET", cid, fields="status,error_message")
    if st.get("status") == "FINISHED":
        break
    if st.get("status") in ("ERROR", "EXPIRED"):
        print(f"::error::스레드 영상 처리 실패: {st.get('status')} {st.get('error_message')}"); raise SystemExit(1)
    time.sleep(10)
else:
    print("::error::스레드 영상 처리 시간 초과"); raise SystemExit(1)

pub = call("POST", f"{uid}/threads_publish", creation_id=cid)
print("스레드 게시 완료! 게시물 ID:", pub["id"])

# 첫 댓글에 링크 다시 달기 (클릭 유도) — 실패해도 본문 게시는 성공으로 둔다
rf = os.environ.get("THREADS_REPLY", "")
if rf and os.path.exists(rf):
    try:
        time.sleep(20)
        r = requests.post(f"{G}/{uid}/threads", data={"media_type": "TEXT", "text": open(rf, encoding="utf-8").read().strip()[:500],
                          "reply_to_id": pub["id"], "access_token": TOKEN}, timeout=60).json()
        if "id" in r:
            time.sleep(5)
            q = requests.post(f"{G}/{uid}/threads_publish", data={"creation_id": r["id"], "access_token": TOKEN}, timeout=60).json()
            print("링크 댓글:", q.get("id") or q)
        else: print("::warning::링크 댓글 실패:", r)
    except Exception as e: print("::warning::링크 댓글 실패:", e)
