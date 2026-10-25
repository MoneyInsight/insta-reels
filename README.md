# insta-reels — 정보·꿀팁 릴스 매일 자동 게시

1. Claude 예약 작업이 매일 아침 `queue/날짜.json`(대본·캡션)을 넣는다.
2. 대본이 들어오는 즉시 깃허브 자동 실행이 영상을 만들고(`make_reel.py`), 공개 주소를 만든 뒤 인스타그램에 게시한다(`post_instagram.py`).
3. 게시가 끝난 대본은 `posted/`로 옮겨진다.

## 처음 한 번 설정
- Settings → Pages → Source: **GitHub Actions**
- Settings → Secrets and variables → Actions → New repository secret
  - `IG_ACCESS_TOKEN`: 인스타그램 장기 액세스 토큰
  - `GH_PAT` (선택): 토큰 자동 연장용 깃허브 토큰 (Secrets 쓰기 권한)
- Actions 탭 → "매일 릴스 자동 게시" → Run workflow 로 바로 테스트

## 대본 형식 (queue/YYYY-MM-DD.json)
```json
{"date": "2026-10-27", "topic": "주제", "source": "출처: 매체 (날짜)",
 "scenes": [{"badge": "모르면 손해", "title": ["제목1", "제목2"], "body": ["설명1", "설명2"], "sec": 3.2}],
 "caption": "캡션과 해시태그"}
```
