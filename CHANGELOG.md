# Changelog

## v2.0 — 2026-05-12

### 사용성 (Usability)

- **실시간 검색** — 제목·요약·출처 AND 조건 검색, 300ms debounce, 검색어 지우기 버튼
- **키워드 배지 클릭 필터** — 카테고리 내 세부 키워드 토글 필터
- **읽음 추적** — localStorage 기반, 읽은 기사 번호 옆 ✓ 표시 및 투명도 처리
- **다크모드 시스템 연동** — `prefers-color-scheme` 자동 감지 + localStorage 오버라이드
- **날짜 네비게이션 UX** — 로딩 스피너 + 오류 토스트 (network-first 전략)
- **키보드 단축키** — `j`/`k` 항목 탐색, `/` 검색 포커스, `0–3` 카테고리 전환, `Esc` 필터 해제

### SEO + PWA

- canonical URL, Open Graph, Twitter Card, JSON-LD WebPage 스키마 자동 삽입
- `manifest.json` — PWA 설치 지원
- Service Worker (`sw.js`) — 정적 자산 cache-first, HTML/JSON network-first

### 버그 수정

- **HTML 이중 인코딩 버그** — `html.unescape()` 2회 적용으로 `&amp;lt;img` 텍스트 완전 제거
- `fix_html_artifacts_in_archives()` — 기존 아카이브 내 잔재 `&lt;img…` 텍스트 소급 정리

### 아카이브 일괄 업그레이드

- `upgrade_archives_to_v2()` — 기존 28일치 아카이브 HTML에 v2 기능 자동 패치 (멱등적)
  - `<head>` SEO/PWA 메타 태그 삽입
  - skip-link 접근성 요소 삽입
  - 검색바 삽입
  - 푸터 profile-card 교체
  - toast-container 삽입

### 푸터 개선

- **profile-card** — 모든 페이지에 운영자 프로필 카드 (사진·이름·소개·링크)
- **"← 최신 뉴스" 링크** — 아카이브 페이지 푸터에 JS로 자동 주입
- **"↑ 상단" 버튼** — 모든 페이지 푸터에 smooth scroll 상단 이동 버튼
- 브랜드 태그: `EDU · PAPERS · TECH` → `EDU · PAPERS · TECH 뉴스 일일 브리핑`

### AI 논문 한국어 요약 매칭 개선

- 기존 정확 매칭 + 접두 매칭에 **difflib 유사도 매칭** (임계값 0.72) 3단계 추가
- 영문 논문 제목처럼 길고 복잡한 제목도 한국어 요약 파일과 매칭 성공률 향상

---

## v1.0 — 2026-04-14

- 초기 릴리스: 3개 소스 자동 집계 + GitHub Pages 배포
- Editorial Brief 레이아웃 (교육·논문·기술 3컬럼)
- 날짜 네비게이션 + 카테고리 필터 칩
