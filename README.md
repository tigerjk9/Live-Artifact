<div align="center">

# Daily Intelligence

**교육 뉴스 · AI 논문 · AI 기술을 매일 한 지면으로. 그리고 그 1년치 흐름까지.**

[![Live](https://img.shields.io/badge/Live-tigerjk9.github.io%2FLive--Artifact-17120e)](https://tigerjk9.github.io/Live-Artifact/)
[![Actions](https://img.shields.io/badge/GitHub%20Actions-%EB%A7%A4%EC%9D%BC%2010%3A37%20KST-2b6a3a?logo=githubactions&logoColor=white)](https://github.com/tigerjk9/Live-Artifact/actions)
[![Python](https://img.shields.io/badge/Python-3.11%2B-3b5ba5?logo=python&logoColor=white)](scripts/fetch_and_generate.py)
[![Deps](https://img.shields.io/badge/deps-requests%20%C2%B7%20python--dateutil%20%C2%B7%20playwright-555)](requirements.txt)
[![CI](https://github.com/tigerjk9/Live-Artifact/actions/workflows/ci.yml/badge.svg)](https://github.com/tigerjk9/Live-Artifact/actions/workflows/ci.yml)
[![PWA](https://img.shields.io/badge/PWA-offline-c2410c)](docs/sw.js)

[오늘 지면](https://tigerjk9.github.io/Live-Artifact/) · [주간](https://tigerjk9.github.io/Live-Artifact/weekly/) · [전체 아카이브](https://tigerjk9.github.io/Live-Artifact/archive/) · [흐름](https://tigerjk9.github.io/Live-Artifact/trends.html) · [주체](https://tigerjk9.github.io/Live-Artifact/entity.html) · [RSS](https://tigerjk9.github.io/Live-Artifact/feed.xml)

</div>

---

## 왜 만들었나

AI·교육 소식은 하루에도 수십 건이 쏟아지지만, 교사가 아침에 쓸 수 있는 시간은 몇 분입니다. 그래서 세 수집기(교육 뉴스·AI 교육 논문·AI 기술 뉴스)가 모은 하루치 25건을 **한 지면**에 놓고, 그 위에 **오늘의 흐름**(주제 분포 · 자주 등장한 주체 · 섹션을 가로지르는 연결 · 7일 변화)을 얹습니다. 그리고 지면은 지워지지 않습니다. 첫 수집일부터 모든 날을 보관하고, 전 기간 검색과 기간 비교로 다시 꺼내 볼 수 있습니다.

서버는 없습니다. **GitHub Actions가 매일 아침 정적 HTML을 만들고 GitHub Pages가 배포**합니다.

> [!NOTE]
> 2026-11-02 기준 **356일 · 8,129건**이 `docs/data/`에 날짜별 JSON으로 쌓여 있고 매일 25건씩 늘어납니다. 소스 레포 3곳이 원본을 전부 보관하고 있어 28일만 남기던 옛 아카이브를 첫 호부터 되살렸고, 요약이 비어 있던 2026년 3~4월도 제목 기반 요약으로 채웠습니다.

## 세 개의 화면

| 화면 | 주소 | 무엇을 보나 |
|------|------|-------------|
| **오늘** | `/` · `/archive/YYYY-MM-DD.html` | 교육·논문·기술 3단 + 오늘의 흐름 보드. 보드의 주제·주체를 누르면 관련 소식만 남고, `교육 3` 같은 참조 칩은 카드로 데려갑니다 |
| **주간** | `/weekly/` | 끝난 주마다 집계와 Gemini 주간 종합. 이 주의 주체(전주 대비), 주제 비중 %p, 날짜별 헤드라인, 주체가 가장 많이 겹친 기사 |
| **아카이브** | `/archive/` | 첫 수집일부터의 모든 날짜를 월별 격자로. 전 기간 제목·요약 검색(`?q=디지털교과서`처럼 공유 가능) |
| **흐름** | `/trends.html` | 30일·90일·180일·1년을 직전 같은 기간과 비교. 주간 수집량, 주제 비중 %p 변화, 주체 랭킹·타임라인, 출처, 헤드라인 연표 |
| **주체** | `/entity.html?e=OpenAI` | 한 주체의 월별 언급, 어떤 주제로 등장했는지, 함께 등장한 주체, 전체 기사 목록. 보드의 칩과 흐름 랭킹에서 바로 연결 |

## 어떻게 만들어지나

```
GitHub Actions (10:37 · 11:13 · 11:49 KST, watchdog 12:29)
   └─ scripts/fetch_and_generate.py
        ├─ Auto-Edu-news-Collector      교육 뉴스 JSON + 요약 TXT
        ├─ Auto-AI-Edu-Paper-Curator    AI 교육 논문 JSON + 요약 TXT
        └─ Auto-AI-Tech-news-Collector  AI 기술 뉴스 JSON + 요약 TXT
              ↓ taxonomy.py   주제 7~10개/섹션 · 주체 사전 90여 개 (규칙 기반, LLM 불필요)
        docs/data/YYYY-MM-DD.json       ← 영구 레코드 (원천)
        docs/data/index.json · search/ · entities.json · weekly/
              ↓ insights.py 보드 · synthesis.py 종합 · enrich.py 보강 · weekly.py 주간 · feeds.py 피드 · render_og.py OG
        docs/index.html · archive/*.html · weekly/*.html · og/*.jpg · feed.xml · trends.html · entity.html
```

- **분류**는 수집기 키워드에 기대지 않습니다. 기술 뉴스의 70%, 논문의 80%는 키워드가 비어 있어서, 제목·요약 패턴 점수로 주제를 고르고 별칭 사전으로 주체(OpenAI·경기도교육청·AI 디지털교과서 …)를 뽑습니다.
- **Gemini 종합**은 `GEMINI_API_KEY` 시크릿이 있을 때만 켜집니다. 헤드라인 한 문장, 섹션을 잇는 흐름 3개, 교실 제안 하나를 보드 상단에 더합니다. 없어도 보드는 자동 집계만으로 완전합니다.
- **공유하면 그날 지면이 보입니다.** 날짜별 OG 이미지(1200×630)를 Actions가 Playwright로 찍어 둡니다. RSS(`feed.xml`)와 JSON Feed(`feed.json`)로 구독할 수 있습니다.
- **같은 기사가 이틀 실리면** 둘째 날에 "M/D 실림"으로 표시되고 집계에서 빠집니다. 논문은 한국어 제목을 병기하고(원제는 아래 작게), 요약이 없던 기간은 제목 기반으로 보강합니다.
- **지면 디자인**은 신문 1면입니다. 종이 바탕과 잉크 괘선, 한글 디스플레이 Hahmlet과 영문 Fraunces, 발행 호수 `제 N호`. 다크 모드는 차콜과 크림입니다. 원칙은 [`.impeccable.md`](.impeccable.md)에 있습니다.

## 빠른 시작

```bash
git clone https://github.com/tigerjk9/Live-Artifact.git
cd Live-Artifact
pip install requests python-dateutil
```

1. **시크릿** — `Settings → Secrets and variables → Actions`

   | 이름 | 필수 | 용도 |
   |------|------|------|
   | `NEWS_GITHUB_TOKEN` | 예 | 소스 레포 3곳을 읽는 PAT |
   | `GEMINI_API_KEY` | 아니오 | 오늘의 흐름 보드에 Gemini 종합 (`gemini-3.5-flash-lite`, 하루 1회) |

2. **Pages** — `Settings → Pages → Branch: main, Folder: /docs`
3. **첫 실행** — `Actions → Daily News Update → Run workflow`

<details>
<summary>로컬에서 돌려보기</summary>

```bash
export NEWS_TOKEN=$(gh auth token)              # 소스 레포 read
python scripts/fetch_and_generate.py            # 오늘 생성 + 최근 7일 누락분 보강
python scripts/fetch_and_generate.py --date 2026-10-30     # 특정 날짜만 (폴백 없이)
python scripts/fetch_and_generate.py --backfill-all        # 소스에 남은 전 기간을 data/로 복구
python scripts/fetch_and_generate.py --rebuild-archives    # 템플릿을 바꾼 뒤 아카이브 HTML 전체 재렌더
python scripts/fetch_and_generate.py --no-fetch --date 2026-11-01   # 기존 레코드로 렌더만
python scripts/fetch_and_generate.py --task reclassify              # 분류 규칙을 고친 뒤 전체 재적용
python scripts/fetch_and_generate.py --task weekly-backfill         # 끝난 모든 주의 다이제스트
pytest -q                                        # 테스트 64개, 0.5초
cd docs && python -m http.server 8765           # http://127.0.0.1:8765/
```

`GEMINI_API_KEY`를 환경변수로 주면 로컬에서도 종합·보강이 붙습니다. `--no-synthesis`로 끌 수 있습니다.
키가 필요한 백필(`enrich`, `summaries`, `weekly-backfill`)은 Actions의 **Maintenance** 워크플로우에서 범위를 지정해 돌리는 것을 권합니다.

</details>

<details>
<summary>파일 구조</summary>

```
Live-Artifact/
├── .github/workflows/
│   ├── daily-news-update.yml     # cron 3회 + workflow_dispatch
│   ├── watchdog.yml              # 12:29 KST — 오늘 지면이 없거나 미완성이면 복구
│   └── keepalive.yml             # 일요일 — 스케줄러 활성 유지
├── docs/                         # GitHub Pages 루트
│   ├── index.html                # 오늘
│   ├── trends.html · entity.html # 흐름 · 주체
│   ├── weekly/                   # 주간 다이제스트
│   ├── og/                       # 날짜별 OG 이미지
│   ├── feed.xml · feed.json      # RSS · JSON Feed
│   ├── _template.html            # 일일 지면 템플릿 ({{ROOT}}로 루트/아카이브 공용)
│   ├── _weekly_template.html · _og_template.html
│   ├── archive/index.html        # 전체 아카이브
│   ├── archive/YYYY-MM-DD.html   # 날짜별 지면 (영구)
│   ├── data/                     # YYYY-MM-DD.json · index.json · search/ · entities.json · entity/ · weekly/ · health.json
│   ├── sw.js                     # Service Worker (cache: di-v7)
│   └── assets/                   # style.css · app.js · archive.js · trends.js · manifest · dates.json
├── scripts/
│   ├── fetch_and_generate.py     # 진입점: 페치 · 파싱 · 레코드 · 렌더 · CLI
│   ├── taxonomy.py               # 주제 규칙 · 주체 사전
│   ├── insights.py               # 저장소 · 집계 · 오늘의 흐름 보드 · 검색/주체 색인
│   ├── synthesis.py · enrich.py  # Gemini 종합 · 항목 보강 (선택)
│   ├── weekly.py · feeds.py      # 주간 다이제스트 · 피드
│   ├── render_og.py · healthcheck.py
├── tests/                        # pytest
├── .impeccable.md                # 디자인 맥락과 원칙
└── CLAUDE.md                     # 운영 지침 · 트러블슈팅
```

</details>

<details>
<summary>운영 중 흔한 상황</summary>

- **요약이 비어 보인다** — 요약은 수집기 3곳이 Gemini로 만듭니다. 본 레포의 커버리지 게이트가 60% 미만이면 이후 cron이 자동 재시도하므로 수집기만 복구하면 됩니다. 자세한 진단은 [CLAUDE.md](CLAUDE.md)의 트러블슈팅.
- **레포는 최신인데 사이트가 옛날이다** — Pages 배포만 실패한 경우입니다. 워크플로우 마지막 단계가 10분간 확인하고 재빌드를 요청합니다.
- **한 섹션만 어제 날짜로 표시된다** — 수집기가 늦은 날의 폴백입니다. 게이트가 재시도하고, 다음 날 실행이 레코드를 보강합니다.
- **이슈가 자동으로 열렸다** — 커버리지가 이틀 연속 낮거나 종합이 사흘 연속 없을 때 `ops-alert` 이슈가 생깁니다. 원인을 고친 뒤 이슈를 닫으면 됩니다.

</details>

## 데이터 소스

- 교육 뉴스 → [Auto-Edu-news-Collector](https://github.com/tigerjk9/Auto-Edu-news-Collector)
- AI 교육 논문 → [Auto-AI-Edu-Paper-Curator](https://github.com/tigerjk9/Auto-AI-Edu-Paper-Curator)
- AI 기술 뉴스 → [Auto-AI-Tech-news-Collector](https://github.com/tigerjk9/Auto-AI-Tech-news-Collector)

---

<div align="center">

만든이 **닷커넥터 김진관** · [litt.ly/dot_connector](https://litt.ly/dot_connector) · CC BY-NC 4.0

</div>
