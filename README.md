<div align="center">

# Daily Intelligence

**교육 뉴스 · AI 논문 · AI 기술의 하루 한 번 브리핑**

[![Live](https://img.shields.io/badge/Live-GitHub%20Pages-0f172a?logo=github&logoColor=white)](https://tigerjk9.github.io/Live-Artifact/)
[![Auto Update](https://img.shields.io/badge/자동갱신-매일%2010:00%20KST-22c55e?logo=githubactions&logoColor=white)](https://github.com/tigerjk9/Live-Artifact/actions)
[![PWA](https://img.shields.io/badge/PWA-지원-5b21b6?logo=pwa&logoColor=white)](https://tigerjk9.github.io/Live-Artifact/)

</div>

---

## 무엇인가요?

별도 서버 없이 **GitHub Actions + GitHub Pages** 만으로 운영되는 AI·교육 일일 뉴스 포털입니다.
매일 오전 10시(KST), 3개의 소스 레포에서 뉴스를 자동 수집하고 정적 HTML로 배포합니다.

## 기능

| 기능 | 설명 |
|------|------|
| 매일 자동 갱신 | GitHub Actions 스케줄러 — KST 10:00 |
| 28일 아카이브 | 날짜 네비게이션으로 과거 브리핑 열람 |
| 실시간 검색 | 제목·요약·출처 통합 검색, 300ms debounce |
| 카테고리 필터 | 교육 / 논문 / 기술 / 전체 즉시 전환 |
| 키워드 배지 필터 | 카테고리 내 세부 키워드 클릭 필터 |
| 다크모드 | 시스템 설정 자동 연동 + 수동 전환 |
| 읽음 추적 | localStorage 기반 읽은 기사 시각 표시 |
| 키보드 단축키 | `j`/`k` 탐색, `/` 검색, `0–3` 카테고리, `Esc` 해제 |
| PWA | Service Worker 오프라인 지원 |
| SEO | canonical · Open Graph · Twitter Card · JSON-LD 자동 생성 |
| 헤더 날짜+요일 | 브리핑 날짜에 요일 표시 + 실시간 KST 시각 (30s 갱신) |
| 모바일 최적화 | iOS 입력 자동줌 방지 · 44px 터치 타겟 · sticky 스택 재계산 |

## 아키텍처

```
GitHub Actions  ──── 매일 10:00 KST ────►  fetch_and_generate.py
                                                    │
                    ┌───────────────────────────────┤
                    │                               │                               │
         Auto-Edu-news-Collector      Auto-AI-Edu-Paper-Curator      Auto-AI-Tech-news-Collector
         (교육 뉴스 JSON                (AI 논문 JSON                  (AI 기술 뉴스 JSON
          + Gemini 요약 TXT)             + 한국어 요약 TXT)              + Gemini 요약 TXT)
                    │                               │                               │
                    └───────────────────────────────┘
                                        │
                                   docs/ (GitHub Pages)
                          ┌─────────────┴──────────────┐
                     index.html                  archive/YYYY-MM-DD.html
                     (오늘)                        (최대 28일)
```

## 빠른 시작

### 1. 레포지토리 포크 후 클론

```bash
git clone https://github.com/tigerjk9/Live-Artifact.git
cd Live-Artifact
```

### 2. GitHub 시크릿 추가

`Settings → Secrets → Actions → New repository secret`

| 이름 | 설명 |
|------|------|
| `NEWS_GITHUB_TOKEN` | 소스 레포 read 권한을 가진 GitHub PAT |

### 3. GitHub Pages 활성화

`Settings → Pages → Branch: main, Folder: /docs`

### 4. 첫 수동 실행

`Actions 탭 → Daily News Update → Run workflow`

## 파일 구조

```
Live-Artifact/
├── .github/workflows/
│   └── daily-news-update.yml     # Cron: 0 1 * * * (KST 10:00)
├── docs/
│   ├── index.html                # 오늘 브리핑 (자동 갱신)
│   ├── _template.html            # HTML 생성 템플릿
│   ├── archive/                  # 날짜별 아카이브 (최대 28일)
│   ├── assets/
│   │   ├── style.css             # Editorial Brief UI
│   │   ├── app.js                # 다크모드·검색·단축키·PWA
│   │   ├── sw.js                 # Service Worker
│   │   ├── manifest.json         # PWA 매니페스트
│   │   └── dates.json            # 아카이브 날짜 목록
│   └── assets/facilitator.png   # 프로필 이미지
└── scripts/
    └── fetch_and_generate.py     # 뉴스 페치 + HTML 생성
```

## 데이터 소스

- **교육 뉴스** → [Auto-Edu-news-Collector](https://github.com/tigerjk9/Auto-Edu-news-Collector)
- **AI 논문** → [Auto-AI-Edu-Paper-Curator](https://github.com/tigerjk9/Auto-AI-Edu-Paper-Curator)
- **AI 기술** → [Auto-AI-Tech-news-Collector](https://github.com/tigerjk9/Auto-AI-Tech-news-Collector)

---

<div align="center">

만든이 **닷커넥터 김진관** · [litt.ly/dot_connector](https://litt.ly/dot_connector) · CC BY-NC 4.0

</div>
