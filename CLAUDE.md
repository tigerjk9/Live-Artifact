# CLAUDE.md — Live-Artifact

## 프로젝트 개요

GitHub Actions + GitHub Pages만으로 운영되는 AI·교육 일일 뉴스 포털.
매일 KST 10:00, 3개 소스 레포에서 뉴스를 수집해 정적 HTML로 배포.

## 아키텍처

```
GitHub Actions (cron: 10:00 KST)
    └─ scripts/fetch_and_generate.py
            ├─ tigerjk9/Auto-Edu-news-Collector     → education_news_{YYYYMMDD}.json
            │                                         + education_news_{YYYYMMDD}_newsletter.txt
            ├─ tigerjk9/Auto-AI-Edu-Paper-Curator   → ai_edu_papers_{YYYYMMDD}.json
            │                                         + ai_edu_papers_{YYYYMMDD}.txt
            └─ tigerjk9/Auto-AI-Tech-news-Collector → ai_tech_news_{YYYYMMDD}.json
                                                      + ai_tech_news_{YYYYMMDD}_newsletter.txt
                    ↓
            docs/index.html (오늘)
            docs/archive/YYYY-MM-DD.html (최대 28일)
```

## 파일 구조

```
Live-Artifact/
├── .github/workflows/
│   ├── daily-news-update.yml     # cron 3회(09:30/10:00/10:30 KST) + workflow_dispatch
│   ├── watchdog.yml              # 11:00 KST — 오늘 아카이브 없으면 직접 실행 (복구)
│   └── keepalive.yml             # 일요일 00:00 KST — 빈 커밋으로 스케줄러 활성 유지
├── docs/
│   ├── index.html                # 오늘 브리핑 (자동 갱신)
│   ├── _template.html            # HTML 생성 템플릿
│   ├── archive/                  # 날짜별 아카이브
│   ├── assets/
│   │   ├── style.css
│   │   ├── app.js
│   │   ├── sw.js                 # Service Worker (cache: di-v3)
│   │   ├── manifest.json
│   │   ├── dates.json
│   │   └── facilitator.png
└── scripts/
    └── fetch_and_generate.py     # 핵심 생성 스크립트
```

## fetch_and_generate.py 핵심 구조

### SOURCES 설정
각 소스에 `ai_summary_file` 패턴을 지정하면 해당 날짜의 AI 요약 txt 파일을 페치해 카드에 반영한다.

### AI 요약 파싱 (`parse_ai_summary_txt`)
지원 형식:
- **Format A** (ai-tech / edu-news newsletter): `N. 제목\n   요약\n   → 시사점\n   URL`
- **Format B** (ai-paper): `N. 제목\n   - 요약\n   - [논문 보기](URL)`

URL·구분선 라인은 스킵, 나머지 들여쓰기 라인은 모두 합쳐 `ai_summary`로 저장.

### `filter_described(items, cfg, source_key)`
- `ai-paper`, `edu-news`: 필터 없음 (항상 전체 표시)
- `ai-tech`: 설명 20자 미만 기사 제외 (전부 없으면 원본 유지)

### `render_entry()` 요약 로직
- `ai_summary`(AI 생성) 있으면 전문 표시
- 없으면 RSS/JSON summary 필드 사용, 영문 250자 제한
- 기자 attribution 패턴 `[매체=기자명 기자]` 자동 제거

### 날짜/시각: 모두 KST 기준
```python
KST = timezone(timedelta(hours=9))
now_kst = datetime.now(tz=KST)
today = now_kst.date().isoformat()  # date.today() 사용 금지
```

## UI 기능 목록

| 기능 | 구현 위치 |
|------|-----------|
| 다크모드 (시스템 연동 + 수동) | app.js `initTheme()` |
| 실시간 검색 (300ms debounce) | app.js `initSearch()` |
| 카테고리 필터 (전체/교육/논문/기술) | app.js `initCatFilter()` |
| 키워드 배지 클릭 필터 | app.js `initKeywordFilter()` |
| 날짜 네비게이션 | app.js `initDateNav()` |
| 키보드 단축키 (j/k/0-3//) | app.js `initKeyboard()` |
| 읽음 추적 (localStorage) | app.js `initReadTracker()` |
| 날짜 공유 액션바 | app.js `initDateActionBar()` |
| 헤더 실시간 KST 시각 | app.js `initLiveClock()` |
| PWA / Service Worker | sw.js (cache: di-v3) |

## 주요 결정 사항

- **SW 캐시 버전**: `di-v3` — CSS/JS 변경 시 버전 올려야 클라이언트 강제 갱신
- **교육 뉴스 설명**: Gemini 요약이 없어도 전체 표시 (필터 안 함)
- **과거 아카이브 백필 안 함**: 신규 기능은 앞으로만 적용

## GitHub Secrets

| 레포 | 시크릿 | 용도 |
|------|--------|------|
| Live-Artifact | `NEWS_GITHUB_TOKEN` | 소스 레포 read 권한 PAT |
| Auto-Edu-news-Collector | `GEMINI_API_KEY` | Gemini 요약 생성 |
| Auto-AI-Edu-Paper-Curator | `GEMINI_API_KEY` | Gemini 요약 생성 |
| Auto-AI-Tech-news-Collector | `GEMINI_API_KEY` | Gemini 요약 생성 |

## 트러블슈팅 — Gemini 요약 의존성

한국어 AI 요약은 본 레포가 아니라 **3개 소스 수집기**가 생성한다. 세 레포 모두
`gemini_summarizer.py` + `config.json`의 `"model"`에 Gemini 모델명을 둔다(config.json이 권위 소스).

**증상 → 원인:** 요약이 영문(논문 `[원문 초록]`)이거나 누락되면 → 수집기의 Gemini 호출 실패.
가장 흔한 원인은 **모델 폐기**(예: 2026-06-02 `gemini-2.0-flash` 404 "no longer available").
세 레포가 같은 모델명을 쓰므로 한꺼번에 망가진다. 2차로 `filter_described`가 설명 없는
ai-tech 기사를 잘라 건수가 급감한다.

**진단:** 수집기 Actions 로그에서 `404 ... no longer available` 확인, 실행 시간 급증(재시도)도 단서.
소스 `.txt`/newsletter 파일을 `gh api`로 직접 받아 한국어 여부 확인.

**복구:** 세 레포 `config.json`의 `"model"`을 살아있는 모델로 교체. 2026-06-03부터
`GeminiSummarizer._resolve_model()` 폴백이 있어 모델 폐기 시 `list_models()`로 자동 대체된다.

**소스 수정 후 오늘자 강제 갱신** (본 레포 워크플로우는 당일 아카이브가 이미 있으면 skip):
```bash
# 오늘 아카이브 삭제 → workflow_dispatch 하면 재생성됨
gh api --method DELETE repos/tigerjk9/Live-Artifact/contents/docs/archive/$(TZ=Asia/Seoul date +%F).html \
  -f message="regenerate" -f sha="<file-sha>" -f branch=main
gh workflow run "Daily News Update" --repo tigerjk9/Live-Artifact
```
