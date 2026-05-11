#!/usr/bin/env python3
"""Daily news fetcher and HTML generator for Live Artifact.

소스 레포 3곳에서 오늘 날짜 JSON을 페치하여 docs/index.html 및
docs/archive/{today}.html을 생성한다. 28일 초과 아카이브는 자동 삭제.
"""

from __future__ import annotations

import base64
import json
import os
import re
import sys
from datetime import date, datetime, timedelta

import requests
from dateutil import parser as dateutil_parser

# ---------------------------------------------------------------------------
# 설정
# ---------------------------------------------------------------------------

TOKEN = os.environ.get("NEWS_TOKEN", "")
HEADERS = (
    {
        "Authorization": f"token {TOKEN}",
        "Accept": "application/vnd.github.v3+json",
    }
    if TOKEN
    else {"Accept": "application/vnd.github.v3+json"}
)

SOURCES: dict[str, dict] = {
    "edu-news": {
        "repo": "tigerjk9/Auto-Edu-news-Collector",
        "label": "교육 뉴스",
        "data_dir": "news",
        "file_template": "education_news_{YYYYMMDD}.json",
        "url_field": "link",
        "title_field": "title",
        "summary_field": "summary",
        "source_field": "press",
        "date_field": "date",
        "keyword_field": "keyword",
    },
    "ai-paper": {
        "repo": "tigerjk9/Auto-AI-Edu-Paper-Curator",
        "label": "AI 교육 논문",
        "data_dir": "papers",
        "file_template": "ai_edu_papers_{YYYYMMDD}.json",
        "url_field": "link",
        "title_field": "title",
        "summary_field": "summary",
        "source_field": "source",
        "date_field": "published",
        "keyword_field": "keyword",
        "authors_field": "authors",
        "pdf_field": "pdf_link",
    },
    "ai-tech": {
        "repo": "tigerjk9/Auto-AI-Tech-news-Collector",
        "label": "AI 기술 뉴스",
        "data_dir": "news",
        "file_template": "ai_tech_news_{YYYYMMDD}.json",
        "url_field": "link",
        "title_field": "title",
        "summary_field": "summary",
        "source_field": "press",
        "date_field": "date",
        "keyword_field": "keyword",
    },
}

KEEP_DAYS = 28

# ---------------------------------------------------------------------------
# GitHub API 유틸리티
# ---------------------------------------------------------------------------


def fetch_file(repo: str, path: str) -> str | None:
    """GitHub Contents API로 파일 raw content를 반환한다. 실패 시 None."""
    url = f"https://api.github.com/repos/{repo}/contents/{path}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code == 404:
            print(f"[WARN] 파일 없음: {repo}/{path}", file=sys.stderr)
            return None
        if resp.status_code != 200:
            print(
                f"[ERROR] GitHub API {resp.status_code}: {repo}/{path}",
                file=sys.stderr,
            )
            return None
        data = resp.json()
        # Base64 디코딩 (GitHub API는 항상 base64 인코딩 반환)
        content = data.get("content", "")
        return base64.b64decode(content.replace("\n", "")).decode("utf-8")
    except Exception as exc:
        print(f"[ERROR] fetch_file({repo}/{path}): {exc}", file=sys.stderr)
        return None


# ---------------------------------------------------------------------------
# 파싱
# ---------------------------------------------------------------------------


def parse_items(raw: str) -> list[dict]:
    """JSON 문자열을 파싱하여 아이템 목록을 반환한다.

    지원 형식:
      - 배열: [{"title": ...}, ...]
      - 객체: {"items": [...], ...}  또는 {"data": [...], ...}
    """
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"[ERROR] JSON 파싱 실패: {exc}", file=sys.stderr)
        return []

    if isinstance(data, list):
        return data

    if isinstance(data, dict):
        # 배열 값을 가진 첫 번째 키를 사용
        for key in ("items", "data", "results", "news", "papers"):
            if key in data and isinstance(data[key], list):
                return data[key]
        # 그 외: 딕셔너리 내의 첫 번째 리스트 값
        for val in data.values():
            if isinstance(val, list):
                return val

    print(f"[WARN] 인식할 수 없는 JSON 구조: {type(data)}", file=sys.stderr)
    return []


# ---------------------------------------------------------------------------
# 날짜 포맷 유틸리티
# ---------------------------------------------------------------------------


def format_date(date_str: str) -> str:
    """다양한 날짜 형식을 'M월 D일' 형식으로 변환한다.

    지원 형식:
      - RFC 2822: "Sun, 10 May 2026 06:50:35 GMT"
      - YYYY-MM-DD HH:MM:SS: "2026-05-09 18:31:15"
      - YYYY-MM-DD: "2026-05-08"
    실패 시 원본 문자열을 그대로 반환한다.
    """
    if not date_str:
        return ""
    try:
        dt = dateutil_parser.parse(date_str)
        return f"{dt.month}월 {dt.day}일"
    except Exception:
        # dateutil 실패 시 간단한 정규식 시도
        m = re.search(r"(\d{4})-(\d{2})-(\d{2})", date_str)
        if m:
            month = int(m.group(2))
            day = int(m.group(3))
            return f"{month}월 {day}일"
        return date_str


def format_authors(authors_raw: str) -> str:
    """저자 문자열을 최대 2명 + '외 N명' 형식으로 줄인다.

    authors는 쉼표 구분 문자열. 50자 초과 또는 3명 이상이면 축약.
    """
    if not authors_raw:
        return ""
    parts = [a.strip() for a in authors_raw.split(",") if a.strip()]
    if len(parts) <= 2 and len(authors_raw) <= 50:
        return ", ".join(parts)
    shown = parts[:2]
    rest = len(parts) - 2
    if rest > 0:
        return f"{', '.join(shown)} 외 {rest}명"
    return ", ".join(shown)


def escape_html(text: str) -> str:
    """최소한의 HTML 이스케이프 처리."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def clean_title(title: str, source: str) -> str:
    """제목 끝의 ' - 매체명' 중복 접미사를 제거한다.

    Google News RSS는 제목 끝에 ' - 매체명' 형식을 붙이는데,
    source 필드가 별도로 있으므로 중복이다.
    """
    if not title:
        return ""
    t = title.strip()
    if source:
        suffix = f" - {source}"
        if t.endswith(suffix):
            t = t[: -len(suffix)].strip()
    # 일반 패턴: 끝부분의 ' - XXX' 형태 (XXX가 짧을 때)
    m = re.search(r"\s+-\s+([^\-]{2,20})\s*$", t)
    if m:
        t = t[: m.start()].strip()
    return t


# ---------------------------------------------------------------------------
# HTML 엔트리 렌더링 (Editorial Brief)
# ---------------------------------------------------------------------------


def render_entry(item: dict, cfg: dict, source_key: str, index: int) -> str:
    """단일 뉴스/논문 엔트리 HTML을 반환한다 (Editorial Brief 구조).

    HTML 구조:
      <li class="entry">
        <span class="entry-num">01</span>
        <div class="entry-body">
          <div class="entry-meta">
            <span class="entry-src">출처</span>
            <span class="entry-sep">·</span>
            <span class="entry-dt">날짜</span>
            <span class="entry-kw">키워드</span>
          </div>
          <h3 class="entry-title"><a>제목</a></h3>
          <p class="entry-by">저자</p>    <!-- 논문 전용 -->
          <p class="entry-desc">요약</p>
          <div class="entry-actions">     <!-- 논문 PDF만 -->
            <a class="entry-pdf">PDF</a>
          </div>
        </div>
      </li>
    """
    raw_title = str(item.get(cfg["title_field"], "제목 없음"))
    url = str(item.get(cfg["url_field"], "#")).strip() or "#"
    source_raw = str(item.get(cfg.get("source_field", ""), "")).strip()
    date_raw = str(item.get(cfg.get("date_field", "date"), "")).strip()
    keyword = str(item.get(cfg.get("keyword_field", "keyword"), "")).strip()
    summary_raw = str(item.get(cfg.get("summary_field", "summary"), "")).strip()

    title_clean = clean_title(raw_title, source_raw)
    title = escape_html(title_clean) if title_clean else "제목 없음"
    source = escape_html(source_raw)
    date_fmt = format_date(date_raw)
    clean_sum = re.sub(r"<[^>]+>", "", summary_raw).strip() if summary_raw else ""

    # meta 컴포지션
    meta_parts: list[str] = []
    if source:
        meta_parts.append(f'<span class="entry-src">{source}</span>')
    if source and date_fmt:
        meta_parts.append('<span class="entry-sep" aria-hidden="true">·</span>')
    if date_fmt:
        meta_parts.append(f'<span class="entry-dt">{date_fmt}</span>')
    if keyword and keyword not in ("press_rss", "None", ""):
        meta_parts.append(f'<span class="entry-kw">{escape_html(keyword)}</span>')

    meta_html = (
        f'      <div class="entry-meta">{"".join(meta_parts)}</div>\n'
        if meta_parts
        else ""
    )

    # 저자 (논문)
    by_html = ""
    if source_key == "ai-paper":
        authors_raw = str(item.get(cfg.get("authors_field", "authors"), "")).strip()
        authors_fmt = escape_html(format_authors(authors_raw))
        if authors_fmt:
            by_html = f'      <p class="entry-by">{authors_fmt}</p>\n'

    # 요약
    desc_html = ""
    if clean_sum:
        desc_html = f'      <p class="entry-desc">{escape_html(clean_sum)}</p>\n'

    # PDF 링크 (논문 전용)
    actions_html = ""
    if source_key == "ai-paper":
        pdf_link = str(item.get(cfg.get("pdf_field", "pdf_link"), "")).strip()
        if pdf_link and pdf_link not in ("#", "None", ""):
            actions_html = (
                '      <div class="entry-actions">\n'
                f'        <a class="entry-pdf" href="{pdf_link}" '
                f'target="_blank" rel="noopener noreferrer">PDF &darr;</a>\n'
                "      </div>\n"
            )

    return (
        f'    <li class="entry">\n'
        f'      <span class="entry-num" aria-hidden="true">{index:02d}</span>\n'
        f'      <div class="entry-body">\n'
        f"{meta_html}"
        f'        <h3 class="entry-title">'
        f'<a href="{url}" target="_blank" rel="noopener noreferrer">{title}</a>'
        f"</h3>\n"
        f"{by_html}"
        f"{desc_html}"
        f"{actions_html}"
        f"      </div>\n"
        f"    </li>"
    )


def render_section_body(items: list[dict], cfg: dict, source_key: str) -> str:
    """섹션 본문 (ol.col-list 또는 col-empty)을 반환한다."""
    if not items:
        label = cfg.get("label", "데이터")
        return f'<p class="col-empty">이 날짜의 {label} 데이터가 없습니다.</p>'
    entries = "\n".join(
        render_entry(item, cfg, source_key, idx + 1) for idx, item in enumerate(items)
    )
    return f'<ol class="col-list">\n{entries}\n  </ol>'


# 하위 호환 — 기존 main()에서 render_cards 호출
def render_cards(items: list[dict], cfg: dict, source_key: str) -> str:
    return render_section_body(items, cfg, source_key)


# ---------------------------------------------------------------------------
# 소스 페치
# ---------------------------------------------------------------------------


def fetch_today_source(key: str, cfg: dict, today: str) -> list[dict]:
    """오늘 날짜 파일을 페치하고 파싱하여 아이템 목록을 반환한다.

    실패 시 빈 리스트를 반환한다 (독립 장애 처리).
    """
    yyyymmdd = today.replace("-", "")
    filename = cfg["file_template"].replace("{YYYYMMDD}", yyyymmdd)
    path = f"{cfg['data_dir']}/{today}/{filename}"
    raw = fetch_file(cfg["repo"], path)
    if raw is None:
        print(
            f"[WARN] {key}: {today} 파일 없음 ({path})",
            file=sys.stderr,
        )
        return []
    items = parse_items(raw)
    print(f"[OK] {key}: {len(items)}건 로드", file=sys.stderr)
    return items


# ---------------------------------------------------------------------------
# 날짜 네비게이션
# ---------------------------------------------------------------------------


def build_date_nav(today: str, archive_dir: str) -> str:
    """최근 28일치 날짜 pill HTML을 생성한다.

    아카이브 파일이 존재하는 날짜만 pill을 출력하며,
    오늘은 항상 맨 앞에 표시한다.
    """
    today_dt = datetime.strptime(today, "%Y-%m-%d").date()
    pills: list[str] = []

    for delta in range(KEEP_DAYS):
        target_dt = today_dt - timedelta(days=delta)
        target_str = target_dt.strftime("%Y-%m-%d")
        month = target_dt.month
        day = target_dt.day

        if delta == 0:
            # 오늘 pill — 항상 출력
            pills.append(
                f'<a class="date-pill today active"\n'
                f'   href="index.html"\n'
                f'   aria-current="page">\n'
                f"  오늘 ({month}/{day:02d})\n"
                f"</a>"
            )
        else:
            # 과거 날짜 — 아카이브 파일이 있을 때만 출력
            archive_path = os.path.join(archive_dir, f"{target_str}.html")
            if os.path.isfile(archive_path):
                pills.append(
                    f'<a class="date-pill"\n'
                    f'   href="archive/{target_str}.html">\n'
                    f"  {month}/{day:02d}\n"
                    f"</a>"
                )

    return "\n".join(pills)


# ---------------------------------------------------------------------------
# dates.json 관리
# ---------------------------------------------------------------------------


def update_dates_json(today: str, docs_dir: str) -> None:
    """docs/assets/dates.json에 오늘 날짜를 추가하고 28일 초과 항목을 제거한다."""
    json_path = os.path.join(docs_dir, "assets", "dates.json")

    # 기존 파일 로드 (없으면 초기화)
    existing: dict = {"available_dates": [], "latest": ""}
    if os.path.isfile(json_path):
        try:
            with open(json_path, encoding="utf-8") as f:
                existing = json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            print(f"[WARN] dates.json 로드 실패, 초기화: {exc}", file=sys.stderr)

    dates: list[str] = existing.get("available_dates", [])

    # 오늘 날짜 추가 (중복 방지)
    if today not in dates:
        dates.append(today)

    # 정렬 후 28일 초과 항목 제거
    dates = sorted(set(dates))
    cutoff_dt = datetime.strptime(today, "%Y-%m-%d").date() - timedelta(days=KEEP_DAYS)
    dates = [d for d in dates if datetime.strptime(d, "%Y-%m-%d").date() > cutoff_dt]

    latest = dates[-1] if dates else ""
    result = {"available_dates": dates, "latest": latest}

    os.makedirs(os.path.dirname(json_path), exist_ok=True)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"[OK] dates.json 업데이트: {len(dates)}개 날짜, latest={latest}", file=sys.stderr)


# ---------------------------------------------------------------------------
# 아카이브 정리
# ---------------------------------------------------------------------------


def cleanup_archive(archive_dir: str, keep_days: int = KEEP_DAYS) -> None:
    """28일 이전 아카이브 HTML 파일을 삭제한다."""
    if not os.path.isdir(archive_dir):
        return

    today_dt = date.today()
    cutoff_dt = today_dt - timedelta(days=keep_days)
    deleted = 0

    for fname in os.listdir(archive_dir):
        if not fname.endswith(".html"):
            continue
        date_part = fname.replace(".html", "")
        try:
            file_dt = datetime.strptime(date_part, "%Y-%m-%d").date()
        except ValueError:
            continue
        if file_dt <= cutoff_dt:
            os.remove(os.path.join(archive_dir, fname))
            deleted += 1
            print(f"[DEL] 아카이브 삭제: {fname}", file=sys.stderr)

    if deleted:
        print(f"[OK] 아카이브 {deleted}개 파일 삭제 완료", file=sys.stderr)


# ---------------------------------------------------------------------------
# 메인
# ---------------------------------------------------------------------------


def main() -> None:
    today = date.today().isoformat()  # "2026-05-11"

    # 경로 계산 (스크립트 위치 기준 상위 디렉토리가 레포 루트)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.dirname(script_dir)
    docs_dir = os.path.join(repo_root, "docs")
    archive_dir = os.path.join(docs_dir, "archive")
    template_path = os.path.join(docs_dir, "_template.html")
    output_path   = os.path.join(docs_dir, "index.html")

    print(f"[START] {today} 뉴스 생성 시작", file=sys.stderr)

    # 1. 템플릿 로드 (_template.html → 플레이스홀더 원본)
    if not os.path.isfile(template_path):
        print(f"[ERROR] 템플릿 없음: {template_path}", file=sys.stderr)
        sys.exit(1)

    with open(template_path, encoding="utf-8") as f:
        template = f.read()

    # 2. 3개 소스 페치 (독립 try-except — 하나 실패해도 나머지 진행)
    cards: dict[str, str] = {}
    counts: dict[str, int] = {}
    for key, cfg in SOURCES.items():
        try:
            items = fetch_today_source(key, cfg, today)
            counts[key] = len(items)
            cards[key] = render_section_body(items, cfg, key)
        except Exception as exc:
            print(f"[ERROR] {key} 처리 실패: {exc}", file=sys.stderr)
            label = cfg.get("label", "데이터")
            counts[key] = 0
            cards[key] = (
                f'<p class="col-empty">이 날짜의 {label} 데이터가 없습니다.</p>'
            )

    # 3. 날짜 네비게이션 생성
    os.makedirs(archive_dir, exist_ok=True)
    date_nav = build_date_nav(today, archive_dir)

    # 4. 플레이스홀더 치환
    today_dt = datetime.strptime(today, "%Y-%m-%d")
    current_date_kr = f"{today_dt.year}년 {today_dt.month}월 {today_dt.day}일"

    from datetime import timezone, timedelta
    KST = timezone(timedelta(hours=9))
    now_kst = datetime.now(tz=KST)
    last_updated_iso = now_kst.strftime("%Y-%m-%dT%H:%M:%S+09:00")
    last_updated_kr = f"{now_kst.year}년 {now_kst.month}월 {now_kst.day}일 {now_kst.strftime('%H:%M')} KST"

    html = (
        template
        .replace("{{CURRENT_DATE}}", current_date_kr)
        .replace("{{EDU_NEWS_CARDS}}", cards["edu-news"])
        .replace("{{AI_PAPER_CARDS}}", cards["ai-paper"])
        .replace("{{AI_TECH_CARDS}}", cards["ai-tech"])
        .replace("{{EDU_NEWS_COUNT}}", f"{counts['edu-news']}건")
        .replace("{{AI_PAPER_COUNT}}", f"{counts['ai-paper']}건")
        .replace("{{AI_TECH_COUNT}}", f"{counts['ai-tech']}건")
        .replace("{{DATE_NAV}}", date_nav)
        .replace("{{LAST_UPDATED_ISO}}", last_updated_iso)
        .replace("{{LAST_UPDATED_KR}}", last_updated_kr)
    )

    # 5. docs/archive/{today}.html 저장
    archive_path = os.path.join(archive_dir, f"{today}.html")
    with open(archive_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"[OK] 아카이브 저장: {archive_path}", file=sys.stderr)

    # 6. docs/index.html 갱신 (템플릿은 _template.html로 보존)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"[OK] index.html 갱신: {output_path}", file=sys.stderr)

    # 7. dates.json 업데이트
    update_dates_json(today, docs_dir)

    # 8. 28일 초과 아카이브 삭제
    cleanup_archive(archive_dir)

    print(f"[DONE] {today} 완료", file=sys.stderr)


if __name__ == "__main__":
    main()
