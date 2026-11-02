<div align="center">

# Daily Intelligence

**교육 뉴스 · AI 논문 · AI 기술의 하루 한 번 브리핑 — 그리고 그 흐름**

[![Live](https://img.shields.io/badge/Live-GitHub%20Pages-0f172a?logo=github&logoColor=white)](https://tigerjk9.github.io/Live-Artifact/)
[![Auto Update](https://img.shields.io/badge/자동갱신-매일%2010:37%20KST-22c55e?logo=githubactions&logoColor=white)](https://github.com/tigerjk9/Live-Artifact/actions)
[![PWA](https://img.shields.io/badge/PWA-지원-5b21b6?logo=pwa&logoColor=white)](https://tigerjk9.github.io/Live-Artifact/)

</div>

---

## 무엇인가요?

별도 서버 없이 **GitHub Actions + GitHub Pages** 만으로 운영되는 AI·교육 일일 뉴스 포털입니다.
매일 오전 3개의 소스 레포에서 뉴스를 자동 수집하고, 주제·주체를 분류해 **오늘의 흐름 보드**와 함께 정적 HTML로 배포합니다.
수집한 모든 날은 `docs/data/`에 JSON으로 영구 보존되어 **전체 아카이브**와 **흐름(장기 추세)** 페이지의 재료가 됩니다.

## 세 개의 화면

| 화면 | 주소 | 내용 |
|------|------|------|
| 오늘 | `/` · `/archive/YYYY-MM-DD.html` | 교육·논문·기술 3단 브리핑 + **오늘의 흐름 보드**(헤드라인, 주제 분포, 오늘의 주체, 교차 연결, 7일 흐름) |
| 아카이브 | `/archive/` | 첫 수집일(2025-11-12)부터의 모든 날짜를 월별 카드로, 전 기간 제목 검색 |
| 흐름 | `/trends.html` | 30일~1년 기간을 직전 같은 기간과 비교: 주간 수집량, 주제 비중 변화, 주체 랭킹·타임라인, 출처, 헤드라인 연표 |

## 기능

| 기능 | 설명 |
|------|------|
| 매일 자동 갱신 | GitHub Actions 스케줄러 — 10:37 / 11:13 / 11:49 KST 3회 시도, 12:29 watchdog 복구 |
| 영구 데이터 계층 | `docs/data/YYYY-MM-DD.json` — 날짜별 정규화 레코드. 삭제하지 않는다 |
| 주제 분류 | 섹션별 7~10개 주제를 규칙 기반으로 부여 (교육: 정책·행정 / AI·디지털교육 / 수업·교육과정 …) |
| 주체 추출 | 기업·모델·교육 당국·교육 이슈·기술 개념 90여 개 사전 (별칭 정규화, 시도교육청 자동 인식) |
| 오늘의 흐름 보드 | 주제 분포 막대, 오늘의 주체, 두 섹션 이상에 걸친 교차 연결, 최근 7일 vs 직전 7일 흐름 — 클릭하면 해당 소식만 필터 |
| Gemini 종합 (선택) | `GEMINI_API_KEY` 시크릿이 있으면 헤드라인 한 문장 + 섹션을 잇는 흐름 3개 + 교실 제안을 보드 상단에 추가 |
| 시사점 분리 | 교육 뉴스의 `→ 시사점`을 요약과 구분해 표시 |
| 전체 아카이브 | 월별 날짜 카드(건수 막대·헤드라인·주요 주체) + 전 기간 제목 검색 (`?q=` 공유 가능) |
| 흐름 페이지 | 라이브러리 없이 `index.json` 하나로 그리는 기간 비교 대시보드 |
| 소스 폴백 | 당일 미수집 소스는 최근 3일 내 데이터로 대체 표시 (섹션에 날짜 병기, 게이트가 재시도) |
| 실시간 검색 · 카테고리 · 키워드 필터 | 제목·요약·시사점·출처·주제 통합 검색, 교육/논문/기술 전환, 키워드 토글 |
| 신문 1면 디자인 | 종이 바탕·잉크 괘선·세리프 디스플레이(Hahmlet·Fraunces), 발행 호수 `제 N호`, 다크 모드는 차콜+크림 (`.impeccable.md`) |
| 다크모드 · 읽음 추적 · 키보드 단축키 · PWA · SEO | `j`/`k` 탐색, `/` 검색, `0–3` 카테고리, `Esc` 해제, Service Worker, canonical/OG/JSON-LD |

## 아키텍처

```
GitHub Actions ─── 매일 10:37 KST ───► scripts/fetch_and_generate.py
                                              │
        ┌─────────────────────────────────────┼─────────────────────────────────────┐
        │                                     │                                     │
Auto-Edu-news-Collector           Auto-AI-Edu-Paper-Curator           Auto-AI-Tech-news-Collector
(교육 뉴스 JSON + 요약 TXT)         (AI 논문 JSON + 요약 TXT)             (AI 기술 뉴스 JSON + 요약 TXT)
        └─────────────────────────────────────┼─────────────────────────────────────┘
                                              ▼
                     taxonomy.py (주제·주체 분류)  →  docs/data/YYYY-MM-DD.json  (영구)
                                              │
                     insights.py (보드 계산·index.json·search.json)   synthesis.py (Gemini, 선택)
                                              ▼
                 docs/index.html · docs/archive/YYYY-MM-DD.html · docs/archive/ · docs/trends.html
```

## 빠른 시작

### 1. 레포지토리 포크 후 클론

```bash
git clone https://github.com/tigerjk9/Live-Artifact.git
cd Live-Artifact
pip install requests python-dateutil
```

### 2. GitHub 시크릿 추가

`Settings → Secrets → Actions → New repository secret`

| 이름 | 필수 | 설명 |
|------|------|------|
| `NEWS_GITHUB_TOKEN` | 예 | 소스 레포 read 권한을 가진 GitHub PAT |
| `GEMINI_API_KEY` | 아니오 | 있으면 오늘의 흐름 보드에 Gemini 종합이 붙는다 (모델 `gemini-2.5-flash`, 하루 1회 호출) |

### 3. GitHub Pages 활성화

`Settings → Pages → Branch: main, Folder: /docs`

### 4. 첫 수동 실행

`Actions 탭 → Daily News Update → Run workflow`

### 로컬에서 돌려보기

```bash
export NEWS_TOKEN=$(gh auth token)
python scripts/fetch_and_generate.py                      # 오늘 생성 (+ 최근 7일 누락분 보강)
python scripts/fetch_and_generate.py --date 2026-10-30    # 특정 날짜만 (폴백 없이) 재생성
python scripts/fetch_and_generate.py --backfill-all       # 소스 레포에 남은 전 기간을 data/로 복구
python scripts/fetch_and_generate.py --rebuild-archives   # 템플릿을 바꾼 뒤 아카이브 HTML 전체 재렌더
cd docs && python -m http.server 8765                     # http://127.0.0.1:8765/ 로 확인
```

## 파일 구조

```
Live-Artifact/
├── .github/workflows/
│   ├── daily-news-update.yml     # cron 3회(10:37/11:13/11:49 KST) + workflow_dispatch
│   ├── watchdog.yml              # 12:29 KST — 오늘 아카이브 없거나 미완성이면 복구
│   └── keepalive.yml             # 일요일 00:00 KST — 스케줄러 활성 유지
├── docs/
│   ├── index.html                # 오늘 브리핑 (자동 갱신)
│   ├── trends.html               # 흐름 — 기간 비교 대시보드
│   ├── _template.html            # 일일 페이지 템플릿 ({{ROOT}}로 루트/아카이브 경로 공용)
│   ├── archive/
│   │   ├── index.html            # 전체 아카이브 (월별 카드 + 전 기간 검색)
│   │   └── YYYY-MM-DD.html       # 날짜별 페이지 (영구)
│   ├── data/
│   │   ├── YYYY-MM-DD.json       # 날짜별 정규화 레코드 — 원천 데이터
│   │   ├── index.json            # 날짜별 집계 (건수·주제·주체·출처·헤드라인)
│   │   └── search.json           # 전 기간 제목 검색 색인
│   ├── sw.js                     # Service Worker (cache: di-v5)
│   └── assets/
│       ├── style.css · app.js · archive.js · trends.js
│       ├── manifest.json · dates.json · facilitator.png · og-image.jpg
└── scripts/
    ├── fetch_and_generate.py     # 페치 · 파싱 · 레코드 빌드 · 렌더 (진입점)
    ├── taxonomy.py               # 주제 규칙 · 주체 사전
    ├── insights.py               # 데이터 저장소 · 집계 · 오늘의 흐름 보드
    └── synthesis.py              # Gemini 종합 (선택)
```

## 데이터 소스

- **교육 뉴스** → [Auto-Edu-news-Collector](https://github.com/tigerjk9/Auto-Edu-news-Collector)
- **AI 논문** → [Auto-AI-Edu-Paper-Curator](https://github.com/tigerjk9/Auto-AI-Edu-Paper-Curator)
- **AI 기술** → [Auto-AI-Tech-news-Collector](https://github.com/tigerjk9/Auto-AI-Tech-news-Collector)

---

<div align="center">

만든이 **닷커넥터 김진관** · [litt.ly/dot_connector](https://litt.ly/dot_connector) · CC BY-NC 4.0

</div>
