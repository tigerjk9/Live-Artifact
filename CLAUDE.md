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
│   ├── daily-news-update.yml     # cron 3회(10:37/11:13/11:49 KST) + workflow_dispatch
│   ├── watchdog.yml              # 12:29 KST — 오늘 아카이브 없으면 직접 실행 (복구)
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
- `ai-tech`: Gemini AI 요약이 1건 이상 매칭됐을 때만 설명 20자+ 필터 적용.
  매칭 0건(newsletter 미생성·Gemini 실패)이면 전체 수집 아이템 반환.

### `fetch_source_with_fallback(key, cfg, today, max_fallback=3)`
오늘 데이터가 없으면 최대 3일 이전 날짜를 재시도. `(items, fallback_date_or_None)` 반환.
`render_date_html(use_fallback=True)` 시 활성화 (오늘 렌더링에만 적용, 백필은 제외).
폴백 사용 시 섹션 카운트에 날짜 표시 예: `5건 (6/3)`.

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
세 레포가 같은 키·모델을 쓰므로 한꺼번에 망가진다. 2차로 `filter_described`가 설명 없는
ai-tech 기사를 잘라 건수가 급감한다. 원인은 로그의 HTTP 코드로 갈린다:

| 코드 | 원인 | 복구 |
|------|------|------|
| 404 `no longer available` | **모델 폐기** (2026-06-02 `gemini-2.0-flash`) | 세 레포 `config.json`의 `"model"` 교체 (2026-06-03부터 `_resolve_model()` 폴백 자동 대체) |
| 429 `exceeded its monthly spending cap` | **AI Studio 월 지출 한도 초과** (2026-07-28) | https://ai.studio/spend 에서 캡 상향 — 아니면 익월 1일 자동 리셋까지 요약 없음 |
| 429 `RESOURCE_EXHAUSTED` / quota | 분당·일일 쿼터 | 대기 후 재시도 |

**진단:** 수집기 Actions 로그에서 `404 ... no longer available` 확인, 실행 시간 급증(재시도)도 단서.
소스 `.txt`/newsletter 파일을 `gh api`로 직접 받아 한국어 여부 확인.

**복구:** 세 레포 `config.json`의 `"model"`을 살아있는 모델로 교체. 2026-06-03부터
`GeminiSummarizer._resolve_model()` 폴백이 있어 모델 폐기 시 `list_models()`로 자동 대체된다.

### 요약 커버리지 게이트 (2026-07-28 도입)

건수만 보는 skip 게이트는 이 장애를 못 잡는다 — Gemini가 죽어도 **건수는 정상**이고
카드만 제목으로 비기 때문이다. 그래서 첫 실행이 요약 없는 아카이브를 만들면 이후
cron이 전부 skip해 하루 종일 고착됐다. 이를 막기 위해:

- `has_korean_summary()` — 설명이 20자 이상이고 한글이 포함돼야 "요약 있음"으로 친다.
  논문의 영문 `[원문 초록]` 폴백도 이 기준에서 걸러진다.
- 생성 HTML `<head>`에 `<meta name="ai-summary-coverage" content="{요약}/{전체}">` 기록.
- 두 워크플로우의 skip 게이트가 **건수 + 커버리지 60% 이상**을 함께 요구 →
  요약이 깨진 날은 이후 cron·watchdog이 계속 재시도한다 (수집기 복구 시 자동 반영).
- 커버리지가 낮으면 페이지 상단에 `.brief-notice` 안내 배너 표시 (제목만 있는 카드가
  고장으로 보이지 않도록).
- **폴백 섹션은 커버리지 0으로 집계** — 어제 데이터는 요약이 온전하므로 그대로 세면
  커버리지가 부풀어 게이트가 꺼지고 묵은 데이터가 굳는다.
- `main()`의 재생성 가드: 기존 아카이브가 더 완전하면(`read_archive_coverage()` 비교)
  덮어쓰지 않는다 — 재시도가 하루 중 퇴보한 수집 결과로 좋은 페이지를 지우지 못하게.

**소스 수정 후 오늘자 강제 갱신** — 요약 장애면 아카이브를 지울 필요가 없다.
커버리지 게이트가 미완성 아카이브(60% 미만)를 스스로 재시도하므로 수집기만 되살리면 된다:
```bash
gh workflow run "Daily News Collection" --repo tigerjk9/Auto-Edu-news-Collector
gh workflow run "Daily Paper Collection" --repo tigerjk9/Auto-AI-Edu-Paper-Curator
gh workflow run "Daily News Collection" --repo tigerjk9/Auto-AI-Tech-news-Collector
# 수집기 완료 후 (cron을 기다려도 되고 즉시 돌려도 된다)
gh workflow run "Daily News Update" --repo tigerjk9/Live-Artifact
```
2026-07-28 실제 복구 경로 — 캡 상향 → 수집기 3개 재실행 → 본 레포 dispatch에서
`[RUN] ... (기존 AI 요약 4/25 = 16%)`로 게이트 통과 → 25/25(100%) 재생성.

커버리지가 **정상(60%+)인데도** 강제로 다시 만들어야 하면 그때만 아카이브를 지운다:
```bash
gh api --method DELETE repos/tigerjk9/Live-Artifact/contents/docs/archive/$(TZ=Asia/Seoul date +%F).html \
  -f message="regenerate" -f sha="<file-sha>" -f branch=main
gh workflow run "Daily News Update" --repo tigerjk9/Live-Artifact
```

### 스케줄 설계 근거 (2026-07-31 조정)

소스 수집기 cron은 23:20 UTC(edu·paper) / 23:40 UTC(ai-tech)이고, 실제 데이터 커밋은
**edu·paper ~00:18 UTC, ai-tech ~01:17 UTC**에 떨어진다(관측 최악값). 본 레포의 이전
1차 cron은 00:30 UTC라 **ai-tech보다 먼저** 돌 수 있었다 — 지금은 GitHub cron 큐 지연
(7월 내내 매일 3~4시간)에 가려져 있었을 뿐이다. 그래서 1차를 01:37 UTC(10:37 KST)로
늦추고, 큐가 가장 혼잡한 정각·30분을 피해 분을 배치했다(지연 자체는 GitHub 사정이라 보장 불가).

### 폴백 섹션 = 60% 경계 함정 (커버리지만으로는 못 막는다)

`ai-tech`(10건)만 폴백되고 edu(10)·paper(5)가 정상이면 fresh 커버리지가
**15/25 = 정확히 60%** — `-ge 60` 게이트를 아슬아슬하게 통과해 **묵은 기술 뉴스가
하루 종일 굳는다**. 섹션 건수(10/5/10)가 하필 경계에 딱 걸린다.

그래서 두 워크플로우 게이트에 **폴백 섹션 검사**를 추가했다. 폴백 섹션은 건수 라벨이
`10건 (7/30)` 형태이므로 괄호로 판별한다:
```bash
FALLBACK=no
grep -q 'col-count">[^<]*(' "$ARCHIVE" 2>/dev/null && FALLBACK=yes
# ... && [ "$PCT" -ge 60 ] && [ "$FALLBACK" = "no" ]
```
폴백이 하나라도 있으면 커버리지와 무관하게 재시도한다.

### 워크플로우 게이트의 `bash -e` 함정 (2026-07-29~31 전면 중단)

**증상:** 소스 수집기 3개는 전부 정상인데 본 레포 Actions만 매 실행 `failure`,
아카이브가 하루도 안 생김. 실패 스텝은 `Check if today already updated`,
로그에는 스크립트 본문만 에코되고 `Process completed with exit code 1`.

**원인:** Actions의 `run:`은 `bash -e`로 돈다. 커버리지 게이트가 쓰는
```bash
COV=$(grep -o '...' "$ARCHIVE" | head -1 | grep -o '[0-9]*/[0-9]*')
```
에서 **grep은 매칭 0건이면 exit 1**이고, 이 종료 코드가 그대로 할당문의 종료 코드가 돼
`-e`가 스텝을 즉사시킨다. 하필 매칭이 0건인 상황이 **"오늘 아카이브가 아직 없다"**
= 반드시 생성해야 하는 날이라, 게이트가 판정을 내리기도 전에 죽고 이후 생성·커밋
단계가 전부 `skip != 'true'` 조건에서 스킵된다. 아카이브가 영영 안 생기니
다음 실행도 똑같이 죽는 **영구 고착**. 2026-07-28 커버리지 게이트 도입 당일은
아카이브가 이미 있어 통과했고, 다음날부터 터졌다.

**교훈:** 파이프라인 마지막이 `grep`인 명령 치환을 `bash -e` 스텝에서 변수에 대입하지 말 것.
전부 `|| true`로 막았다 (두 워크플로우의 게이트 + `Validate article counts`의 건수 추출 4곳).
검증은 반드시 `bash -e script.sh`로 — `bash script.sh`는 셔뱅의 `-e`를 무시해서 재현이 안 된다.

**설계 원칙:** skip 게이트는 **불리언 계산 전용**이며 실행을 실패시키면 안 된다.
판정이 불가능하면 `skip=false`(=작업 수행)로 폴백하는 것이 안전한 방향이다.

### 추가 함정 — 소스 레포 로컬 수집 (요약 누락의 또 다른 원인)

카드 설명이 비는 증상은 모델 폐기뿐 아니라 **로컬 수집**으로도 발생한다. 소스 수집기를
**이 PC에서 직접 실행하면 `GEMINI_API_KEY`가 없어** 요약 없는 데이터가 당일 디렉터리를
덮어쓴다(news_collector.py는 `news/{today}/`를 조건 없이 덮어씀). 정작 시크릿을 가진
Actions 수집기가 그날 cron 드롭으로 안 돌면 빈 요약이 그대로 남는다.

**구분법** — 소스 레포 커밋 author/메시지로 판별:
- Actions: `github-actions[bot]` / `📰 자동 뉴스 수집 ...` (요약 정상)
- 로컬:    `Dot_Connector` / `[Auto] 뉴스 수집 - ...` (요약 누락 위험)

**복구:** 소스 수집기를 Actions로 재실행 → 본 레포 아카이브 삭제 후 재생성(위 절차).
```bash
gh workflow run "Daily News Collection" --repo tigerjk9/Auto-AI-Tech-news-Collector
```
**예방:** 소스 수집기를 로컬에서 키 없이 돌리지 말 것. `filter_described`가 요약 매칭
0건이면 필터를 꺼 건수는 안 잘리지만, 카드는 제목만 남는다.

## 트러블슈팅 — Pages 배포 실패 (레포는 최신인데 사이트가 옛날)

커밋·푸시가 성공해도 **Pages 배포는 별도 워크플로우**(pages-build-deployment)라
그것만 조용히 실패할 수 있다. 2026-07-03 장애: deploy 잡이 GitHub 측 일시 장애
("Deployment failed, try again later")로 실패 후 빌드 상태가 `building`으로 고착,
이후 실행들은 레포 아카이브만 보고 skip → 사이트가 전날 상태로 방치.

**진단/복구:**
```bash
gh api repos/tigerjk9/Live-Artifact/pages/builds/latest   # errored, 커밋≠HEAD, 10분+ building이면 고착
gh api -X POST repos/tigerjk9/Live-Artifact/pages/builds  # 재빌드 요청 (즉효)
```

**자동화:** daily-news-update.yml·watchdog.yml 마지막의 `Verify Pages deployment`
단계(`if: always()`)가 최신 커밋 배포를 최대 10분 폴링하고, 실패/고착 시 재빌드를
1회 자동 요청한다 (`pages: write` 권한 필요).
