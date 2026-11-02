# CLAUDE.md — Live-Artifact

## 프로젝트 개요

GitHub Actions + GitHub Pages만으로 운영되는 AI·교육 일일 뉴스 포털.
매일 KST 오전, 3개 소스 레포에서 뉴스를 수집해 주제·주체를 분류하고 정적 HTML로 배포.
수집한 모든 날은 `docs/data/`에 JSON으로 **영구 보존**된다 (v3.0, 2026-11-02 — 28일 삭제 폐지).

## 아키텍처

```
GitHub Actions (cron: 10:37/11:13/11:49 KST, watchdog 12:29, maintenance 수동)
    └─ scripts/fetch_and_generate.py
            ├─ tigerjk9/Auto-Edu-news-Collector     → education_news_{YYYYMMDD}.json + _newsletter.txt
            ├─ tigerjk9/Auto-AI-Edu-Paper-Curator   → ai_edu_papers_{YYYYMMDD}.json + .txt
            └─ tigerjk9/Auto-AI-Tech-news-Collector → ai_tech_news_{YYYYMMDD}.json + _newsletter.txt
                    ↓ taxonomy.classify / extract_entities
            docs/data/YYYY-MM-DD.json      ← 원천 레코드 (삭제 금지)
            docs/data/index.json           ← 날짜별 집계 (흐름·아카이브 페이지 재료)
            docs/data/search.json          ← 전 기간 제목 색인
                    ↓ insights.compute_board / render_board (+ synthesis.synthesize, 선택)
            docs/index.html (오늘) · docs/archive/YYYY-MM-DD.html (영구) · docs/og/YYYY-MM-DD.jpg
            docs/archive/index.html · docs/trends.html · docs/entity.html (정적 셸 — JS가 data/*.json 로드)
            docs/weekly/*.html (weekly.py) · docs/feed.xml · docs/feed.json (feeds.py)
```

## 파일 구조

```
Live-Artifact/
├── .github/workflows/
│   ├── daily-news-update.yml     # cron 3회 + workflow_dispatch (env: NEWS_TOKEN, GEMINI_API_KEY)
│   ├── watchdog.yml              # 12:29 KST — 오늘 아카이브 없거나 미완성이면 직접 실행
│   ├── maintenance.yml           # 수동 — enrich/summaries/weekly-backfill/mark-dups/reclassify/og-all/rebuild
│   ├── ci.yml                    # push/PR — pytest
│   └── keepalive.yml             # 일요일 00:00 KST — 빈 커밋으로 스케줄러 활성 유지
├── docs/
│   ├── index.html                # 오늘 브리핑 (자동 갱신)
│   ├── trends.html               # 흐름 페이지 (정적 셸 + trends.js)
│   ├── entity.html               # 주체 페이지 (정적 셸 + entity.js, ?e=이름)
│   ├── weekly/                   # 주간 다이제스트 (index.html + YYYY-Www.html, weekly.py가 생성)
│   ├── og/                       # 날짜별 OG 이미지 JPEG (render_og.py)
│   ├── feed.xml · feed.json      # RSS 2.0 · JSON Feed (최근 30일)
│   ├── _template.html            # 일일 페이지 템플릿
│   ├── _weekly_template.html     # 주간 페이지 템플릿
│   ├── _og_template.html         # OG 카드 템플릿
│   ├── sw.js                     # Service Worker (cache: di-v7)
│   ├── archive/index.html        # 전체 아카이브 (정적 셸 + archive.js)
│   ├── archive/YYYY-MM-DD.html   # 날짜별 페이지 — 레코드에서 재생성 가능
│   ├── data/                     # ★ 원천 데이터 계층
│   │   ├── YYYY-MM-DD.json · index.json · health.json
│   │   ├── search/YYYY-MM.json   # 월별 검색 색인 (제목+요약) + index.json
│   │   ├── entities.json · entity/{slug}.json
│   │   └── weekly/YYYY-Www.json
│   └── assets/
│       ├── style.css             # Front Page v5 — 토큰(종이·잉크·섹션색) + 컴포넌트, 단일 파일
│       ├── app.js                # 공통 + 일일 페이지 (v7)
│       ├── archive.js · trends.js · entity.js
│       ├── manifest.json · dates.json · facilitator.png · og-image.jpg
└── scripts/
    ├── fetch_and_generate.py     # 진입점: 페치·파싱·레코드 빌드·렌더·CLI
    ├── taxonomy.py               # 주제 규칙(TOPICS) · 주체 사전(ENTITIES) · BRIDGES
    ├── insights.py               # load/save_day · build_index/search/entity_index · compute_board · render_board
    ├── synthesis.py              # Gemini 종합 (헤드라인·흐름 3개·교실 제안)
    ├── enrich.py                 # Gemini 항목 보강 (주제 보정·논문 한국어 제목·요약 백필)
    ├── weekly.py                 # 주간 다이제스트 데이터·Gemini 주간 종합·렌더
    ├── feeds.py                  # feed.xml / feed.json
    ├── render_og.py              # OG 이미지 (Playwright)
    └── healthcheck.py            # 운영 경보 판정 → data/health.json, 종료코드 2면 이슈
tests/                            # pytest (ci.yml)
```

## 데이터 계약 — `docs/data/YYYY-MM-DD.json`

```json
{"date": "2026-11-01", "generated_at": "...+09:00",
 "sections": {"edu": [item], "paper": [item], "tech": [item]},
 "fallback": {"tech": "2026-10-31"},         // 폴백 사용 섹션만
 "notes": {"edu": "수집기 한 줄 요약"},        // 구포맷 뉴스레터(2025-11~2026-03)에서 수확
 "synthesis": {"headline","threads","classroom","model","items_hash"}}   // Gemini (선택)
item = {n, title, url, source, published(YYYY-MM-DD), keyword, topic, kind, entities[],
        summary, implication, ai(bool), [authors, pdf],
        선택: dup_of(전날 지면 날짜), title_ko, topic_src="ai"+topic_rule, summary_src="ai-backfill"}
record 선택 키: enrich {hash, model, topics, title_ko, summaries}
```
- `topic`은 `taxonomy.classify(section, title, summary)` — 섹션별 id (`policy`, `genai_tutor`, `industry` …). 라벨은 `topic_label()`.
- `ai`는 한국어 요약 20자 이상 여부 → 커버리지 게이트의 분자. 폴백 섹션은 `record_ai_count(fresh_only=True)`에서 0으로 센다.
- `dup_of`가 있는 항목은 지면에 "M/D 실림" 표시로 남되 `index_entry`·`compute_board`·주체 색인·주간 집계에서 빠진다 (`insights.is_dup`).
- `index.json`의 `days[]` 항목: `{d, n{edu,paper,tech}, ai, fb[], topics{sec:{topic:n}}, ents{name:n}(상위 20), kinds, srcs{"sec:출처":n}, head, head_src}`.

## fetch_and_generate.py 핵심 구조

### CLI
```
python scripts/fetch_and_generate.py                  # 오늘(폴백 허용) + 최근 7일 누락 레코드 보강
  --date YYYY-MM-DD    특정 날짜만, 폴백 없이. latest가 아니면 index.html은 건드리지 않음
  --backfill-all       소스 레포 디렉터리 목록 기준 전 기간 누락 레코드 복구 (오늘 제외)
  --rebuild-archives   data/ 전체를 현재 템플릿으로 다시 렌더 (템플릿·CSS 구조 바꾼 날)
  --no-fetch           기존 레코드로 렌더만    --no-synthesis  Gemini 생략
  --task NAME [--from D --to D]   유지보수 (오늘 생성 대신; maintenance.yml이 호출)
      mark-dups   전날 중복 표시            reclassify  규칙만 다시 적용 (재페치 없음, Gemini 주제는 유지)
      enrich      Gemini 주제 보정+논문 한국어 제목   summaries  요약 없는 항목 제목 기반 요약 (2026-03~04 공백)
      weekly-backfill  끝난 모든 주 다이제스트     og-all  OG 전부 재렌더     rebuild  아카이브 전부 재렌더
```
유지보수 작업은 영향 범위의 아카이브·OG·색인·피드·index.html을 함께 다시 만든다.
**Maintenance는 한 번에 하나씩 띄운다** — 일일·유지보수 워크플로우가 같은 concurrency 그룹(`live-artifact-write`)이라
실행 중 1개 + 대기 1개만 유지되고, 대기 중에 또 띄우면 먼저 대기하던 실행이 `cancelled`된다 (2026-11-02 summaries 실행이 이렇게 취소됨). Gemini가 필요한 작업(enrich·summaries·weekly-backfill)은
키가 있는 Actions(`maintenance.yml`)에서 돌린다 — 로컬에는 키가 없다.

### main() 흐름
1. `--backfill-all` → `all_source_dates()` ∖ data → `build_day_record(d, use_fallback=False)` 저장 (0건이면 저장 안 함)
2. 최근 7일 중 레코드 없는 날 보강 (소스 커밋이 늦게 떨어진 날을 다음 날이 메운다)
3. 대상 날짜: 새 레코드 vs 기존 레코드를 `(fresh ai 수, total)`로 비교 → **더 완전한 쪽 유지**. 세 소스 모두 0건이면 기존 유지 또는 exit 0
3.5. `mark_duplicates()` — 직전 3일 레코드와 URL(`canon_url`)·정규화 제목 비교 → `dup_of`
4. 오늘이면 `synthesize()` + `enrich_record()` (키 없으면 no-op, 해시 같으면 재호출 안 함)
5. `build_index` · `build_search`(월별) · `build_entity_index` → `render_og.py --date`(Playwright 없으면 건너뜀) →
   대상 날짜 아카이브 렌더 → latest면 index.html → dates.json → `build_feeds` → `build_weekly`(가장 최근에 끝난 주)

### 요약 TXT 파싱 (`parse_ai_summary_txt` → `({norm_title: {summary, implication}}, note)`)
- **Format A** (2026-04~ 뉴스): `N. 제목` / `   요약` / `   → 시사점`(교육만) / `   URL`
- **Format B** (논문): `N. 제목` / `   - 요약` / `   - [논문 보기](URL)`
- **Format C** (2025-11~2026-03): `# 1️⃣ 제목` / `오피니언: 요약` / `🔗 링크:` — 감지는 `_EMOJI_HEAD_RE`(**re.MULTILINE 필수**), `> 오늘의 한 줄 요약:`은 `note`로
- 2026-03 중순~04 교육 뉴스레터는 링크만 있어 요약이 비어 있다 (JSON summary도 빈 문자열). 평문 `education_news_*.txt`의
  `요약:` 줄로 보강하지만(`plain_summary_file`, 뉴스레터 요약 3건 미만일 때만 1회 추가 페치) Google News RSS 항목엔
  요약이 거의 없어 수확이 적다 — 그 기간은 `.brief-notice` 배너가 뜨는 게 정상
- 소스 JSON에 git 충돌 마커가 남은 날이 4일 있다(2025-12-19, 2026-01-06, 2026-02-20 교육 / 2026-03-31 기술) —
  `repair_json_variants()`가 마커 제거 → theirs → ours 순으로 복구하고 URL 중복을 제거한다
- 수집기가 Gemini 실패 시 넣는 상투 한 줄 요약("교육을 중심으로 교육 현장의 혁신이 가속화되고 있습니다")은
  `_BOILERPLATE_NOTE_RE`로 버린다 (헤드라인 연표 노이즈 방지)
- 매칭은 `match_summaries()`: 정규화 → 정확 → 접두 20자 → difflib 0.72

### `filter_described` / `fetch_source_with_fallback`
- `ai-paper`, `edu-news`: 필터 없음. `ai-tech`: AI 요약 1건 이상 매칭됐을 때만 설명 20자+ 필터
- 오늘 데이터 없으면 최대 3일 이전 재시도 → `record["fallback"][sec]`, 건수 라벨 `5건 (6/3)`

### 렌더링
- 템플릿 플레이스홀더: `{{ROOT}}`(루트 `""` / 아카이브 `"../"`), `{{PAGE_DATE}}`, `{{BOARD}}`, `{{BRIEF_NOTICE}}`, `{{AI_COVERAGE_META}}`, `{{DATE_NAV}}`, 섹션 카드·건수, `{{PAGE_CANONICAL}}`, `{{LAST_UPDATED_*}}`
- 카드: `<li class="entry" id="{sec}-{n}" data-topic="…" data-ents="A|B">` — 보드 필터·참조 칩·검색 색인이 이 id를 쓴다
- 아카이브 HTML의 `LAST_UPDATED`는 레코드 `generated_at` → 재렌더가 결정적
- 날짜/시각은 모두 KST (`datetime.now(tz=KST)`), `date.today()` 금지

## UI 기능 목록

| 기능 | 구현 위치 |
|------|-----------|
| 오늘의 흐름 보드 (접기, 주제/주체 필터, 참조 칩 점프, `#edu-3` 해시 하이라이트) | insights.render_board + app.js `initBoard()` |
| 사이트 메뉴 (오늘·아카이브·흐름), 모바일 2행 + `--header-h` 실측 | app.js `markSiteNav()` `syncHeaderHeight()` |
| 날짜 네비 (최근 14일 + 전체 아카이브, 과거 열람일 고정) | app.js `renderDatePills()` |
| 전체 아카이브 (월별 카드, 전 기간 검색 `?q=`) | archive.js (`data/index.json`, `data/search.json` 지연 로드) |
| 흐름 (기간 비교 차트, 라이브러리 없음) | trends.js (`data/index.json`) — 주체 이름은 주체 페이지로 링크 |
| 주체 페이지 (월별 언급·주제·동시 등장·전체 목록, `?e=`) | entity.js (`data/entities.json`, `data/entity/*.json`) |
| 주간 다이제스트 (끝난 주 집계 + Gemini 주간 종합) | weekly.py → `docs/weekly/` |
| OG 이미지 (헤드라인·흐름 3개·건수·주체) | render_og.py + `_og_template.html` → `docs/og/*.jpg`, 없으면 og-image.jpg 폴백 |
| RSS / JSON Feed | feeds.py → `feed.xml`, `feed.json` |
| 전 기간 검색 (제목+요약, 월별 색인 지연 로드) | archive.js (`data/search/*.json`) |
| 다크모드 · 검색 · 카테고리 · 키워드 · 읽음 · 단축키 · 공유 바 · 시계 · PWA | app.js (기존) |

## 주요 결정 사항

- **데이터는 지우지 않는다.** `docs/data/*.json`이 원천, HTML은 파생물. 과거 아카이브도 `--rebuild-archives`로 현행 템플릿을 따라간다 (v2의 "백필 안 함" 원칙 폐기)
- **SW 캐시 버전**: `di-v7` — CSS/JS 변경 시 버전 올려야 클라이언트 강제 갱신
- **분류는 규칙 기반이 바닥, Gemini가 보정.** 규칙 추가는 `taxonomy.TOPICS`/`ENTITIES`에 패턴 한 줄 → `--task reclassify`로 재페치 없이 과거 전체에 적용 (Gemini가 고른 `topic_src: ai`는 유지, 규칙 결과는 `topic_rule`에). 패턴의 `\b`는 컴파일 때 ASCII 경계로 바뀐다 — 한글 조사가 붙은 영문 토큰 때문. 라벨 회귀 세트는 `tests/test_taxonomy.py`
- **중복은 지우지 않고 표시한다.** 같은 기사가 이틀 실리면 둘째 날에 `dup_of` — 지면 구조(10/5/10)와 게이트 건수는 유지, 집계만 제외
- **OG 이미지는 파생물.** Playwright 설치 실패·렌더 실패 시 페이지는 기본 `og-image.jpg`로 폴백하고 작업은 계속된다. JPEG 품질 80, 장당 약 25KB
- **Gemini 종합은 선택**. 없으면 결정적 헤드라인("오늘 25건 · 가장 많이 등장한 주체 …")로 대체. 모델은 수집기와 같은 `gemini-2.5-flash`(`GEMINI_MODEL`로 변경), REST 직접 호출
  - Gemini 2.5는 **생각(thinking) 토큰이 `maxOutputTokens`를 잠식**한다. 2026-11-02 첫 실행에서 한도 1200으로 JSON이 잘려 `[SYN] 응답 파싱 실패`.
    지금은 한도 4096 + `thinkingConfig.thinkingBudget: 0` + 느슨한 JSON 파싱(`_parse_json_loose`). 실패 로그에 응답 앞 160자가 남는다
- 교육 뉴스 설명: Gemini 요약이 없어도 전체 표시 (필터 안 함)
- `docs/assets/og-image.png`(6.4MB)는 어디서도 참조하지 않는다 (og는 .jpg 사용)

## 운영 경보 (healthcheck.py, 2026-11-02)

일일 워크플로우 마지막의 `Health check` 단계가 `docs/data/health.json`을 쓰고, 아래 중 하나면 `ops-alert` 라벨 이슈를 연다(열린 게 있으면 댓글):
커버리지 60% 미만 이틀 연속 · `GEMINI_API_KEY`가 있는데 종합이 사흘 연속 없음 · 폴백 섹션 이틀 연속.
조건이 해소되면 이슈는 사람이 닫는다. 단계 자체는 `continue-on-error`라 실행을 실패시키지 않는다.

## 디자인 — 신문 1면 (v3.1, 2026-11-02)

디자인 맥락은 `.impeccable.md`가 권위 소스다 (독자·브랜드·원칙). 요지:
- 종이색 바탕(`--bg` oklch 97.5% 0.009 85)과 잉크(`--ink`), 괘선(얇은 선·두꺼운 선·이중선)으로 위계를 만든다. 박스·그림자·둥근 모서리 금지.
- 글꼴: 한글 디스플레이 **Hahmlet**(`--font-ko`), 영문 네임플레이트·숫자 **Fraunces**(`--font-en`, opsz·SOFT·WONK 축 요청), 본문·UI Pretendard(`--font`). 세 폰트 모두 CDN(Google Fonts·jsDelivr).
- 헤더는 두 층: 비고정 `.masthead`(네임플레이트 + 날짜·발행 호수 `제 N호`) + 고정 `.site-header`(발행 바: DI·메뉴·시계·테마). sticky 오프셋은 JS가 `.site-header` 실측 높이를 `--header-h`에 쓴다.
- 섹션 머리는 원색 띠(`.col-head` 배경 = 섹션색), 호수 숫자는 Fraunces 300 2.1rem. 첫 기사는 제목을 한 단계 키운다.
- 발행 호수 `{{ISSUE_NO}}` = 첫 수집일(2025-11-12)을 1호로 센 순번(`issue_number()`), 정적 페이지는 "전체 아카이브"/"흐름" 라벨.
- 다크 모드는 "밤에 읽는 잉크 종이" — 따뜻한 차콜 + 크림, 섹션색은 밝게. 네온·발광 없음.

## GitHub Secrets

| 레포 | 시크릿 | 용도 |
|------|--------|------|
| Live-Artifact | `NEWS_GITHUB_TOKEN` | 소스 레포 read 권한 PAT |
| Live-Artifact | `GEMINI_API_KEY` (선택) | 오늘의 흐름 보드 Gemini 종합 — 2026-11-02 등록됨. 없으면 자동 집계만 |
| 수집기 3곳 | `GEMINI_API_KEY` | 한국어 요약 생성 |

## 운영 메모

- 로컬 개발: `pip install requests python-dateutil`, `NEWS_TOKEN=$(gh auth token)`; `cd docs && python -m http.server 8765`
- 큰 파일 쓰기: 이 환경의 Bash heredoc은 `'#'` 등이 든 긴 본문에서 깨진다 — Write 도구로 쓰고 Bash는 짧은 명령에만
- 시각 확인: Chrome 확장이 없으면 `playwright`(파이썬) 헤드리스 스크린샷으로 대체 가능
- 테스트: `pip install -r requirements.txt -r requirements-dev.txt && pytest -q` (네트워크 불필요, 0.5초). 파서·분류·렌더를 고치면 먼저 돌린다
- 이 PC는 TLS 가로채기 때문에 `curl`/`requests`로 github.io에 직접 못 붙는다 — 라이브 확인은 Playwright(Chromium)로

## 트러블슈팅 — Gemini 요약 의존성

한국어 AI 요약은 본 레포가 아니라 **3개 소스 수집기**가 생성한다. 세 레포 모두
`gemini_summarizer.py` + `config.json`의 `"gemini.model"`에 Gemini 모델명을 둔다(config.json이 권위 소스).

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

### 요약 커버리지 게이트 (2026-07-28 도입)

건수만 보는 skip 게이트는 이 장애를 못 잡는다 — Gemini가 죽어도 **건수는 정상**이고
카드만 제목으로 비기 때문이다. 그래서:

- `item["ai"]` — 설명이 20자 이상이고 한글이 포함돼야 "요약 있음". 논문의 영문 `[원문 초록]` 폴백도 걸러진다.
- 생성 HTML `<head>`에 `<meta name="ai-summary-coverage" content="{fresh 요약}/{전체}">` 기록.
- 두 워크플로우의 skip 게이트가 **건수 + 커버리지 60% 이상 + 폴백 섹션 없음**을 함께 요구 →
  요약이 깨진 날은 이후 cron·watchdog이 계속 재시도한다 (수집기 복구 시 자동 반영).
- 커버리지가 낮으면 페이지 상단에 `.brief-notice` 안내 배너 표시.
- **폴백 섹션은 커버리지 0으로 집계** — 어제 데이터는 요약이 온전하므로 그대로 세면 게이트가 꺼진다.
- `main()`의 재생성 가드: 기존 레코드가 더 완전하면(`(fresh ai, total)` 비교) 덮어쓰지 않는다.

**소스 수정 후 오늘자 강제 갱신** — 요약 장애면 아카이브를 지울 필요가 없다.
커버리지 게이트가 미완성(60% 미만)을 스스로 재시도하므로 수집기만 되살리면 된다:
```bash
gh workflow run "Daily News Collection" --repo tigerjk9/Auto-Edu-news-Collector
gh workflow run "Daily Paper Collection" --repo tigerjk9/Auto-AI-Edu-Paper-Curator
gh workflow run "Daily News Collection" --repo tigerjk9/Auto-AI-Tech-news-Collector
gh workflow run "Daily News Update" --repo tigerjk9/Live-Artifact   # 수집기 완료 후
```

커버리지가 **정상(60%+)인데도** 다시 만들어야 하면(예: Gemini 종합만 다시 붙이기) `force` 입력으로 게이트만 끈다.
레코드 보호 가드는 그대로라 더 나쁜 결과로 덮어쓰지 않고, 항목 집합이 같으면 기존 종합을 재사용한다:
```bash
gh workflow run "Daily News Update" --repo tigerjk9/Live-Artifact -f force=true
```
레코드 자체를 버리고 처음부터 만들어야 할 때만 **레코드와 아카이브를 함께** 지운다
(레코드만 남기면 "기존이 더 완전함" 가드가 새 결과를 버린다):
```bash
TODAY=$(TZ=Asia/Seoul date +%F)
for f in docs/data/$TODAY.json docs/archive/$TODAY.html; do
  SHA=$(gh api repos/tigerjk9/Live-Artifact/contents/$f --jq .sha)
  gh api --method DELETE repos/tigerjk9/Live-Artifact/contents/$f -f message="regenerate $TODAY" -f sha="$SHA" -f branch=main
done
gh workflow run "Daily News Update" --repo tigerjk9/Live-Artifact
```

### 스케줄 설계 근거 (2026-07-31 조정)

소스 수집기 cron은 23:20 UTC(edu·paper) / 23:40 UTC(ai-tech)이고, 실제 데이터 커밋은
**edu·paper ~00:18 UTC, ai-tech ~01:17 UTC**에 떨어진다(관측 최악값). 그래서 1차를 01:37 UTC(10:37 KST)로
두고, 큐가 가장 혼잡한 정각·30분을 피해 분을 배치했다. 당일 ai-tech가 늦으면 폴백 섹션이 생기고
게이트가 재시도한다. 이와 별개로 **다음 날 실행의 "최근 7일 보강"**이 레코드가 없는 날을 메운다
(단, 이미 폴백으로 레코드가 만들어진 날은 보강 대상이 아니다 — 그날은 당일 재시도에 맡긴다).

### 폴백 섹션 = 60% 경계 함정

`ai-tech`(10건)만 폴백되고 edu(10)·paper(5)가 정상이면 fresh 커버리지가 **15/25 = 정확히 60%**라
게이트를 통과해 묵은 기술 뉴스가 굳는다. 그래서 게이트에 **폴백 섹션 검사**가 있다 — 건수 라벨이
`10건 (7/30)` 형태이므로 괄호로 판별:
```bash
FALLBACK=no
grep -q 'col-count">[^<]*(' "$ARCHIVE" 2>/dev/null && FALLBACK=yes
```

### 워크플로우 게이트의 `bash -e` 함정 (2026-07-29~31 전면 중단)

Actions의 `run:`은 `bash -e`로 돈다. `COV=$(grep … | grep -o …)`에서 **grep 매칭 0건이면 exit 1**이
할당문 종료 코드가 돼 스텝이 즉사한다. 매칭 0건 = "오늘 아카이브가 아직 없다" = 반드시 생성해야 하는 날이라
영구 고착된다. 모든 grep 추출에 `|| true`. **설계 원칙:** skip 게이트는 불리언 계산 전용, 판정 불가면
`skip=false`(=작업 수행)로 폴백.

### 소스 레포 로컬 수집 (요약 누락의 또 다른 원인)

소스 수집기를 **이 PC에서 직접 실행하면 `GEMINI_API_KEY`가 없어** 요약 없는 데이터가 당일 디렉터리를 덮어쓴다.
구분: Actions 커밋은 `github-actions[bot]` / `📰 자동 뉴스 수집 ...`, 로컬은 `Dot_Connector` / `[Auto] 뉴스 수집 - ...`.
복구: 수집기를 Actions로 재실행 → 본 레포 레코드·아카이브 삭제 후 재생성(위 절차).

## 트러블슈팅 — Pages 배포 실패 (레포는 최신인데 사이트가 옛날)

커밋·푸시가 성공해도 **Pages 배포는 별도 워크플로우**(pages-build-deployment)라 그것만 조용히 실패할 수 있다.
```bash
gh api repos/tigerjk9/Live-Artifact/pages/builds/latest   # errored, 커밋≠HEAD, 10분+ building이면 고착
gh api -X POST repos/tigerjk9/Live-Artifact/pages/builds  # 재빌드 요청 (즉효)
```
두 워크플로우 마지막의 `Verify Pages deployment`(`if: always()`)가 최신 커밋 배포를 최대 10분 폴링하고,
실패/고착 시 재빌드를 1회 자동 요청한다 (`pages: write` 권한 필요).
