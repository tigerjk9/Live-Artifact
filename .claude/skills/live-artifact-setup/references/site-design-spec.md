# 사이트 디자인 명세 레퍼런스

Live Artifact 뉴스 포털의 상세 UI/UX 명세.
`live-site-designer`가 참조한다.

---

## 목차

1. [전체 레이아웃](#1-전체-레이아웃)
2. [CSS 시스템](#2-css-시스템)
3. [날짜 네비게이션](#3-날짜-네비게이션)
4. [뉴스 카드 컴포넌트](#4-뉴스-카드-컴포넌트)
5. [JavaScript 기능](#5-javascript-기능)
6. [HTML 플레이스홀더 명세](#6-html-플레이스홀더-명세)
7. [GitHub Pages 설정](#7-github-pages-설정)

---

## 1. 전체 레이아웃

```html
<!DOCTYPE html>
<html lang="ko" data-theme="light">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Daily Intelligence — {{CURRENT_DATE}}</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;700&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="assets/style.css">
</head>
<body>
  <header class="site-header">
    <div class="header-inner">
      <div class="brand">
        <span class="brand-icon">📡</span>
        <h1 class="brand-name">Daily Intelligence</h1>
      </div>
      <div class="header-meta">
        <span class="current-date">{{CURRENT_DATE}}</span>
        <button class="theme-toggle" aria-label="다크모드 전환">🌙</button>
      </div>
    </div>
  </header>

  <nav class="date-nav" aria-label="날짜 선택">
    {{DATE_NAV}}
  </nav>

  <main class="news-grid">
    <section class="news-column" data-category="edu">
      <h2 class="column-title">
        <span class="icon">📚</span> 교육 뉴스
      </h2>
      <div class="cards">{{EDU_NEWS_CARDS}}</div>
    </section>

    <section class="news-column" data-category="paper">
      <h2 class="column-title">
        <span class="icon">🔬</span> AI 논문
      </h2>
      <div class="cards">{{AI_PAPER_CARDS}}</div>
    </section>

    <section class="news-column" data-category="tech">
      <h2 class="column-title">
        <span class="icon">🤖</span> AI 기술
      </h2>
      <div class="cards">{{AI_TECH_CARDS}}</div>
    </section>
  </main>

  <footer class="site-footer">
    <span>Last updated: <time>{{LAST_UPDATED}}</time></span>
    <a href="https://github.com/tigerjk9" target="_blank" rel="noopener">GitHub ↗</a>
  </footer>

  <script src="assets/app.js"></script>
</body>
</html>
```

---

## 2. CSS 시스템

### 커스텀 프로퍼티 (라이트 / 다크)

```css
:root {
  --edu-color: #4CAF50;
  --edu-bg: #e8f5e9;
  --paper-color: #2196F3;
  --paper-bg: #e3f2fd;
  --tech-color: #FF9800;
  --tech-bg: #fff3e0;

  --bg: #f4f6f9;
  --surface: #ffffff;
  --border: #e0e4ea;
  --text-primary: #1a1a2e;
  --text-secondary: #64648a;
  --text-link: #2196F3;

  --radius: 12px;
  --radius-sm: 6px;
  --shadow: 0 2px 12px rgba(0,0,0,0.07);
  --shadow-hover: 0 6px 24px rgba(0,0,0,0.12);

  --font: 'Noto Sans KR', -apple-system, sans-serif;
  --transition: 0.2s ease;
}

[data-theme="dark"] {
  --bg: #0f0f1a;
  --surface: #1a1a2e;
  --border: #2a2a45;
  --text-primary: #e8e8f5;
  --text-secondary: #9090b8;
  --text-link: #64b5f6;
  --edu-bg: rgba(76,175,80,0.12);
  --paper-bg: rgba(33,150,243,0.12);
  --tech-bg: rgba(255,152,0,0.12);
}
```

### 주요 컴포넌트 스타일

```css
/* 헤더 */
.site-header {
  background: var(--surface);
  border-bottom: 1px solid var(--border);
  position: sticky;
  top: 0;
  z-index: 100;
  box-shadow: var(--shadow);
}
.header-inner {
  max-width: 1400px;
  margin: 0 auto;
  padding: 1rem 1.5rem;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

/* 날짜 네비게이션 */
.date-nav {
  background: var(--surface);
  border-bottom: 1px solid var(--border);
  overflow-x: auto;
  scrollbar-width: thin;
}
.date-nav-inner {
  display: flex;
  gap: 0.5rem;
  padding: 0.75rem 1.5rem;
  min-width: max-content;
}
.date-pill {
  padding: 0.35rem 0.85rem;
  border-radius: 20px;
  border: 1px solid var(--border);
  background: var(--bg);
  color: var(--text-secondary);
  font-size: 0.8rem;
  text-decoration: none;
  white-space: nowrap;
  transition: var(--transition);
}
.date-pill:hover { background: var(--surface); color: var(--text-primary); }
.date-pill.active {
  background: var(--text-primary);
  color: var(--bg);
  border-color: var(--text-primary);
  font-weight: 700;
}

/* 뉴스 그리드 */
.news-grid {
  max-width: 1400px;
  margin: 0 auto;
  padding: 1.5rem;
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 1.5rem;
}
@media (max-width: 960px) { .news-grid { grid-template-columns: 1fr; } }
@media (min-width: 961px) and (max-width: 1200px) { .news-grid { grid-template-columns: repeat(2, 1fr); } }

/* 컬럼 타이틀 */
.column-title {
  font-size: 1rem;
  font-weight: 700;
  padding: 0.5rem 0.75rem;
  border-radius: var(--radius-sm);
  margin-bottom: 1rem;
}
[data-category="edu"]   .column-title { color: var(--edu-color);   background: var(--edu-bg); }
[data-category="paper"] .column-title { color: var(--paper-color); background: var(--paper-bg); }
[data-category="tech"]  .column-title { color: var(--tech-color);  background: var(--tech-bg); }
```

---

## 3. 날짜 네비게이션

Python 스크립트가 생성하는 `{{DATE_NAV}}` HTML:

```html
<div class="date-nav-inner">
  <a href="archive/2025-04-14.html" class="date-pill">4/14</a>
  <a href="archive/2025-04-15.html" class="date-pill">4/15</a>
  <!-- ... -->
  <a href="index.html" class="date-pill active">오늘 (5/11)</a>
</div>
```

- 최근 28일을 오래된 날짜부터 왼쪽에 나열한다
- 오늘 날짜 pill에 `class="active"` 추가
- 오늘은 `index.html`로, 과거 날짜는 `archive/{date}.html`로 링크

---

## 4. 뉴스 카드 컴포넌트

### 정상 카드 HTML

```html
<article class="news-card">
  <div class="card-meta">
    <span class="card-source">소스명</span>
    <span class="card-time">오후 2:30</span>   <!-- 있을 경우만 -->
  </div>
  <h3 class="card-title">
    <a href="https://..." target="_blank" rel="noopener">기사 제목</a>
  </h3>
  <p class="card-summary">요약 텍스트 (최대 120자)</p>  <!-- 있을 경우만 -->
  <a href="https://..." class="card-link" target="_blank" rel="noopener">
    읽기 →
  </a>
</article>
```

### 데이터 없음 카드

```html
<div class="news-card news-card--empty">
  <p>오늘 데이터가 없습니다.</p>
</div>
```

### 카드 CSS

```css
.news-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 1rem 1.25rem;
  box-shadow: var(--shadow);
  transition: var(--transition);
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  margin-bottom: 0.75rem;
}
.news-card:hover { box-shadow: var(--shadow-hover); transform: translateY(-2px); }
.card-title a { color: var(--text-primary); text-decoration: none; font-weight: 600; font-size: 0.95rem; line-height: 1.4; }
.card-title a:hover { color: var(--text-link); }
.card-summary { color: var(--text-secondary); font-size: 0.85rem; line-height: 1.5; }
.card-link { color: var(--text-link); font-size: 0.8rem; font-weight: 500; text-decoration: none; align-self: flex-end; }
.card-meta { font-size: 0.75rem; color: var(--text-secondary); display: flex; gap: 0.5rem; }
```

---

## 5. JavaScript 기능

### `docs/assets/app.js` 전체 구조

```javascript
// 1. 다크모드
const toggleTheme = () => {
  const current = document.documentElement.getAttribute("data-theme");
  const next = current === "dark" ? "light" : "dark";
  document.documentElement.setAttribute("data-theme", next);
  localStorage.setItem("theme", next);
};
document.querySelector(".theme-toggle")?.addEventListener("click", toggleTheme);
// 초기화
const saved = localStorage.getItem("theme") || "light";
document.documentElement.setAttribute("data-theme", saved);
document.querySelector(".theme-toggle").textContent = saved === "dark" ? "☀️" : "🌙";

// 2. 날짜 pill active 상태 (아카이브 페이지에서도 동작)
const currentPath = location.pathname;
document.querySelectorAll(".date-pill").forEach(pill => {
  const href = pill.getAttribute("href");
  if (currentPath.endsWith(href) || (href === "index.html" && currentPath.endsWith("/"))) {
    pill.classList.add("active");
  }
});

// 3. 날짜 네비게이션 스크롤 (오늘 pill이 보이도록)
document.querySelector(".date-pill.active")?.scrollIntoView({
  behavior: "smooth", block: "nearest", inline: "center"
});
```

---

## 6. HTML 플레이스홀더 명세

Python 스크립트(`fetch_and_generate.py`)가 치환해야 하는 플레이스홀더 전체 목록:

| 플레이스홀더 | 치환값 | 예시 |
|------------|--------|------|
| `{{CURRENT_DATE}}` | `YYYY년 MM월 DD일` 형식 | `2025년 05월 11일` |
| `{{EDU_NEWS_CARDS}}` | 교육 뉴스 카드 HTML 블록 | `<article class="news-card">...</article>` |
| `{{AI_PAPER_CARDS}}` | AI 논문 카드 HTML 블록 | |
| `{{AI_TECH_CARDS}}` | AI 기술 뉴스 카드 HTML 블록 | |
| `{{DATE_NAV}}` | 날짜 pill HTML 블록 | `<div class="date-nav-inner">...</div>` |
| `{{LAST_UPDATED}}` | ISO 8601 UTC 시각 | `2025-05-11T01:00:00Z` |

치환 방식:
```python
with open("docs/index.html") as f:
    template = f.read()

html = (template
    .replace("{{CURRENT_DATE}}", current_date_kr)
    .replace("{{EDU_NEWS_CARDS}}", edu_cards_html)
    .replace("{{AI_PAPER_CARDS}}", paper_cards_html)
    .replace("{{AI_TECH_CARDS}}", tech_cards_html)
    .replace("{{DATE_NAV}}", date_nav_html)
    .replace("{{LAST_UPDATED}}", datetime.utcnow().isoformat() + "Z"))
```

---

## 7. GitHub Pages 설정

레포 Settings → Pages:
- **Source**: `Deploy from a branch`
- **Branch**: `main` / `docs` 폴더
- URL: `https://tigerjk9.github.io/Live-Artifact/`

`docs/` 폴더가 GitHub Pages 루트가 된다.
아카이브 파일 경로: `https://tigerjk9.github.io/Live-Artifact/archive/2025-05-11.html`
