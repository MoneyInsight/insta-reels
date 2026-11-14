"""랭킹 쇼츠(TOP 5) 1편 만들기 — 재사용 허락 영상 5개에서 가장 웃긴 순간만 뽑아 5위→1위 순으로 공개.
make.py의 다운로드·제미나이·음성·자막 기능을 그대로 쓴다.  출력: comic/work/final.mp4, meta.json (+ 대기열에 게시용 항목 추가)
사용법: GEMINI_API_KEY=... python comic/rank_make.py
"""
import json, os, random, re, subprocess, sys, time, functools
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import make as m
import requests
print = functools.partial(print, flush=True)

THEMES = [  # (제목, 제목 키워드)
    ("웃긴 고양이", r"cat|kitten|猫|кот"), ("웃긴 강아지", r"dog|puppy|пес|соба"), ("귀여운 아기 동물", r"baby|cub|pup|kitten|puppy|calf|joey"),
    ("웃긴 새", r"bird|parrot|owl|penguin|duck|goose|chicken|crow"), ("귀여운 동물", r"panda|otter|raccoon|hamster|seal|elephant|goat|monkey|bear|fox|rabbit"),
    ("빵 터지는 순간", r"funny|fail|prank|comedy|laugh|slapstick|mascot|lol|😂|веселые"), ("감동 순간", r"rescue|reunion|kind|heart|help|save|hug"),
]
CLIP = """이 영상(원제: "{title}")에서 한국 시청자가 가장 빵 터지거나 감탄할 **단 한 순간**을 4~7초로 골라.
narration: 친구한테 말하듯 신난 반말 리액션 한 문장(18자 이내, 사실과 다르면 안 됨), caption: 화면 자막(14자 이내), highlight: 자막 속 핵심 단어,
score: 이 순간의 웃김·임팩트 점수(1~100). 위험·폭력·조롱 장면이거나 볼 만한 순간이 없으면 {{"skip": true}}.
JSON만: {{"start": 0.0, "end": 0.0, "narration": "...", "caption": "...", "highlight": "...", "score": 0}}"""


def ask_clip(src, title):
    f = m.gemini_upload(src)
    for model in ["gemini-3.8-flash"] * 4 + ["gemini-3.1-pro-preview"]:
        try:
            r = requests.post(f"{m.G}/v1beta/models/{model}:generateContent?key={m.KEY}", timeout=240, json={
                "contents": [{"parts": [{"file_data": {"mime_type": "video/mp4", "file_uri": f["uri"]}}, {"text": CLIP.format(title=title)}]}],
                "generationConfig": {"responseMimeType": "application/json", "temperature": 0.8}}).json()
            return json.loads(re.sub(r"^```json|```$", "", r["candidates"][0]["content"]["parts"][0]["text"].strip()))
        except Exception:
            print("::notice::장면 고르기 실패", model, str(r.get("error", "") if isinstance(r, dict) else "")[:160]); time.sleep(30)
    return None


def seg_video(src, st, d, ov, aud, out, tempo=1.0, orig=0.2):
    has_a = "audio" in subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type", "-of", "csv=p=0", src], capture_output=True, text=True).stdout
    vf = (f"[0:v]fps=30,scale=1080:1150:force_original_aspect_ratio=increase,crop=1080:1150,setsar=1[v];"
          f"color=black:s={m.W}x{m.H}:r=30[bg];[bg][v]overlay=0:{m.TOP}:shortest=1[b];[b][1:v]overlay=0:0,format=yuv420p[vo];"
          f"[A]aformat=sample_rates=44100:channel_layouts=mono,volume={orig}[o];"
          f"[2:a]atempo={tempo:.3f},apad,aformat=sample_rates=44100:channel_layouts=mono,volume=1.2[n];[o][n]amix=inputs=2:duration=first:normalize=0[ao]")
    ins = ["-ss", f"{st:.2f}", "-t", f"{d:.2f}", "-i", src, "-i", ov, "-i", aud]
    if has_a: vf = vf.replace("[A]", "[0:a]")
    else: ins += ["-f", "lavfi", "-t", f"{d:.2f}", "-i", "anullsrc=r=44100:cl=mono"]; vf = vf.replace("[A]", "[3:a]")
    m.sh("ffmpeg", "-v", "error", "-y", *ins, "-filter_complex", vf, "-map", "[vo]", "-map", "[ao]", "-t", f"{d:.2f}", "-c:v", "libx264",
         "-preset", "veryfast", "-crf", "20", "-r", "30", "-c:a", "aac", "-ar", "44100", "-ac", "1", "-b:a", "128k", out + ".tmp.mp4")
    os.replace(out + ".tmp.mp4", out)


def main():
    if not m.KEY: print("::error::GEMINI_API_KEY 없음"); raise SystemExit(1)
    os.makedirs(m.WD, exist_ok=True)
    for f in os.listdir(m.WD): os.remove(os.path.join(m.WD, f))
    q = json.load(open(m.Q, encoding="utf-8"))
    pool = [x for x in q["items"] if x.get("src") == "commons" and x.get("url") and x["status"] not in ("fail", "fail_download", "skip") and not x.get("rk")]
    random.shuffle(THEMES)
    theme = next(((t, [x for x in pool if re.search(k, x["title"], re.I)]) for t, k in THEMES if sum(bool(re.search(k, x["title"], re.I)) for x in pool) >= 6), None)
    if not theme: theme = ("레전드 웃긴 순간", pool)
    name, cands = theme[0], sorted(theme[1], key=lambda x: -x.get("score", 0))[:12]
    random.shuffle(cands)
    print("주제:", name, "후보", len(cands))
    clips = []
    for it in cands:
        if len(clips) >= 5: break
        src = m.download_any(it)
        if not src: continue
        keep = f"{m.WD}/clip{len(clips)}.mp4"; os.replace(src, keep)
        c = ask_clip(keep, it["title"])
        if c is None: print("::error::제미나이 응답 없음 → 다음 회차에"); raise SystemExit(1)
        it["rk"] = time.strftime("%Y-%m-%d")
        if c.get("skip") or float(c.get("end", 0)) - float(c.get("start", 0)) < 2: continue
        c.update(src=keep, it=it); clips.append(c)
    if len(clips) < 3: m.save_q(q); print("::error::쓸 장면이 부족"); raise SystemExit(1)
    clips.sort(key=lambda c: c.get("score", 0))  # 점수 낮은 것부터 → 마지막이 1위
    n = len(clips); title = f"{name} TOP {n}"
    credit = "원본: " + ", ".join(dict.fromkeys(c["it"]["channel"][:18] for c in clips))[:60] + " (설명란)"
    parts, cuts, t = [], [], 0.0
    # 오프닝 2.5초: 1위 장면 살짝 + 후킹
    a0 = f"{m.WD}/n_intro.wav"
    if not m.tts(f"{name} 탑{n}! 1위는 진짜 미쳤어 ㅋㅋ", a0, "funny"): raise SystemExit("음성 실패")
    d0 = max(2.5, m.dur(a0) + 0.3); top = clips[-1]
    ov = m.overlay(0, f"{name}", f"TOP {n}", "끝까지 보면\n1위에 기절 ㅋㅋ", "1위", credit)
    seg_video(top["src"], float(top["start"]), d0, ov, a0, f"{m.WD}/p0.mp4", orig=0.1)
    parts.append(f"{m.WD}/p0.mp4"); t += d0; cuts.append(t)
    for i, c in enumerate(clips):
        rank = n - i; a = f"{m.WD}/n{i}.wav"
        line = f"{rank}위! " + c.get("narration", "")
        if i == n - 1: line = "대망의 1위! " + c.get("narration", "")
        if not m.tts(line, a, "funny"): raise SystemExit("음성 실패")
        total = m.dur(c["src"]); st = max(0.0, float(c["start"])); ad = m.dur(a)
        d = max(min(float(c["end"]) - st, 8.0), ad + 0.4); d = min(d, total - st)
        tempo = min(1.3, (ad + 0.2) / d) if ad + 0.2 > d else 1.0
        ov = m.overlay(i + 1, name, f"{rank}위", c.get("caption", ""), c.get("highlight", ""), credit)
        out = f"{m.WD}/p{i + 1}.mp4"; seg_video(c["src"], st, d, ov, a, out, tempo); parts.append(out); t += d; cuts.append(t)
    # 마무리 문구는 1위 장면 자막 대신 마지막 1.5초 추가 없이 SNS 글에서 유도
    open(f"{m.WD}/list.txt", "w").write("".join(f"file '{os.path.basename(p)}'\n" for p in parts))
    m.sh("ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", f"{m.WD}/list.txt", "-c", "copy", f"{m.WD}/joined.mp4")
    cuts = cuts[:-1]
    sfx = "".join(f"aevalsrc='0.35*sin(2*PI*(600+2500*t)*t)*exp(-14*t)':d=0.25:s=44100,adelay={int(x*1000)},aformat=channel_layouts=mono[s{k}];" for k, x in enumerate(cuts))
    mix = "[0:a]aformat=channel_layouts=mono[m];" + sfx + "[m]" + "".join(f"[s{k}]" for k in range(len(cuts))) + f"amix=inputs={len(cuts)+1}:duration=first:normalize=0[a]"
    m.sh("ffmpeg", "-v", "error", "-y", "-i", f"{m.WD}/joined.mp4", "-filter_complex", mix, "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", f"{m.WD}/final.tmp.mp4")
    os.replace(f"{m.WD}/final.tmp.mp4", f"{m.WD}/final.mp4")
    if not m.qa(f"{m.WD}/final.mp4"): m.save_q(q); raise SystemExit("검수 실패")
    rid = "rank" + time.strftime("%Y%m%d%H%M")
    src_lines = "\n".join(f"{n - i}위: \"{c['it']['title'][:60]}\" — {c['it']['channel']} ({c['it'].get('license', 'CC BY')}) {c['it'].get('page', '')}" for i, c in enumerate(clips))
    tags = ["랭킹", "TOP5", name.replace(" ", ""), "웃긴영상", "쇼츠"]
    meta = {"yt_title": f"{name} TOP {n} 😂 1위 실화냐 ㅋㅋㅋ #Shorts"[:100],
            "yt_description": f"{title} — 끝까지 보면 1위에 빵 터짐 ㅋㅋ\n당신의 1위는? 댓글로 알려줘!\n\n🎬 원본 영상 (재사용 허락된 영상에 한국어 더빙·자막·편집)\n{src_lines}\n\n" + " ".join("#" + x for x in tags + ["Shorts"]),
            "yt_tags": tags + ["Shorts", "해외반응"], "yt_category": "23"}
    json.dump(meta, open(f"{m.WD}/meta.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    kw = {"웃긴 고양이": ("고양이 장난감", "고양이", "고양이 낚싯대"), "웃긴 강아지": ("강아지 장난감", "강아지", "강아지 장난감"),
          "귀여운 아기 동물": ("반려동물 간식", "간식", "반려동물 간식"), "웃긴 새": ("새 모이", "모이", "새 모이"),
          "귀여운 동물": ("동물 인형", "인형", "동물 인형"), "감동 순간": ("반려동물 간식", "간식", "반려동물 간식")}.get(name, ("웃긴 파티 소품", "파티", "파티 소품"))
    q["items"].append({"id": rid, "src": "commons", "title": title, "channel": "여러 원작자(설명란 참고)", "license": "CC BY 등", "status": "made",
                       "rank": 0, "made_at": time.strftime("%Y-%m-%d %H:%M"), "kind": "ranking",
                       "plan": {"top1": name, "top2": f"TOP {n}", "hashtags": tags, "product_keyword": kw[0], "product_must": kw[1], "product_label": kw[2],
                                "sns_text": f"{title} ㅋㅋㅋ 5위부터 1위까지 다 레전드\n1위 보고 커피 뿜음 😂 너의 1위는 몇 위야?\n친구 태그해서 같이 봐!"}})
    m.save_q(q)
    with open(os.environ.get("GITHUB_OUTPUT", "/dev/null"), "a") as o: o.write(f"vid={rid}\n")
    print(f"완성: {t:.1f}초 → {meta['yt_title']}")


if __name__ == "__main__":
    main()
