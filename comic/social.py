"""코믹 쇼츠 → 스레드·인스타용: 영상과 어울리는 쿠팡 상품을 찾아 링크 달린 글을 만든다 (유튜브에는 링크 없음).
사용법: COUPANG_ACCESS_KEY=... COUPANG_SECRET_KEY=... python comic/social.py <영상ID>
출력: comic/work/threads.txt, threads_reply.txt, insta.txt  (상품 못 찾으면 링크 없이 글만)
"""
import json, os, sys
sys.path.insert(0, ".")
import health

DIS = health.DISCLOSURE
vid = sys.argv[1]; W = "comic/work"
q = json.load(open("comic/queue.json", encoding="utf-8"))
it = next(x for x in q["items"] if x["id"] == vid); p = it.get("plan", {})
credit = "🎬 화면: Pixabay 무료 영상" if it.get("src") == "trend" else f"🎬 원본: {it['channel']} (" + ("Wikimedia Commons" if it.get("src") == "commons" else "YouTube") + ", " + it.get("license", "CC BY") + ")"
prod = None
if p.get("product_keyword"):
    try: prod = health.find_product({"product_keyword": p["product_keyword"], "product_must": p.get("product_must", "")}, W)
    except Exception as e: print("::warning::쿠팡 상품 검색 실패", e)
body = (p.get("sns_text") or f"{p.get('top1','')} {p.get('top2','')}").strip()
tags = " ".join("#" + h.lstrip("#") for h in p.get("hashtags", [])[:8])
if prod:
    label = p.get("product_label") or prod["name"][:20]
    tail = f"\n\n👉 {label}: {prod['link']}\n\n{credit}\n{DIS}"
    th = body[:max(60, 495 - len(tail))] + tail
    reply = f"📌 영상 속 그 느낌, {label} 여기 있어 👉 {prod['link']}\n{DIS}"
    ig = f"{body}\n\n🔗 추천템 {label} → 프로필 링크에서 확인!\n\n{credit}\n{DIS}\n\n{tags} #웃긴영상 #릴스"
    it["product"] = prod
else:
    th = f"{body}\n\n{credit}"; reply = ""
    ig = f"{body}\n\n{credit}\n\n{tags} #웃긴영상 #릴스"
open(f"{W}/threads.txt", "w", encoding="utf-8").write(th[:500])
open(f"{W}/threads_reply.txt", "w", encoding="utf-8").write(reply)
open(f"{W}/insta.txt", "w", encoding="utf-8").write(ig[:2200])
json.dump(q, open("comic/queue.json", "w", encoding="utf-8"), ensure_ascii=False, indent=0)
print("쿠팡 상품:", prod["name"][:40] if prod else "없음(링크 없이 게시)")
