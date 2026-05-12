#!/usr/bin/env python3
"""Daily news fetcher and HTML generator for Live Artifact.

소스 레포 3곳에서 오늘 날짜 JSON을 페치하여 docs/index.html 및
docs/archive/{today}.html을 생성한다. 28일 초과 아카이브는 자동 삭제.
"""

from __future__ import annotations

import base64
import html
import json
import os
import re
import sys
from datetime import date, datetime, timedelta
from difflib import SequenceMatcher

import requests
from dateutil import parser as dateutil_parser

# ---------------------------------------------------------------------------
# 설정
# ---------------------------------------------------------------------------

BASE_URL = "https://tigerjk9.github.io/Live-Artifact"

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
        "ai_summary_file": "education_news_{YYYYMMDD}_newsletter.txt",
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
        # 일반 .txt 파일에 한국어 AI 요약이 항목별로 있음
        "ai_summary_file": "ai_edu_papers_{YYYYMMDD}.txt",
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
        # newsletter.txt에 항목별 한국어 AI 요약 있음
        "ai_summary_file": "ai_tech_news_{YYYYMMDD}_newsletter.txt",
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


def strip_html(text: str) -> str:
    """HTML 태그/엔티티/잘린 태그를 모두 제거하고 공백 정리한다.

    다중 인코딩 케이스를 포함하여 모두 처리:
      - 정상 태그: <a href=...>...</a>
      - 잘린 태그: <img width="..." src="https://..."  (닫는 > 없음)
      - 단일 인코딩 엔티티: &lt;a&gt; → <a>
      - 이중 인코딩 엔티티: &amp;lt;img → &lt;img → <img
      - 미디어 태그(img/figure/picture/video): 내용 전체 제거
    """
    if not text:
        return ""
    # 1) 이중 인코딩 대응: 두 번 unescape (안전함 — 단일 인코딩에도 멱등)
    t = html.unescape(html.unescape(text))
    # 2) 미디어 태그 선행 제거 (img/figure/picture/video — 내용 없는 태그)
    t = re.sub(r"<(?:img|figure|picture|video|source|iframe)\b[^>]*>", "", t, flags=re.IGNORECASE | re.DOTALL)
    # 3) 정상 태그 제거 (멀티라인 포함)
    t = re.sub(r"<[^>]*>", "", t, flags=re.DOTALL)
    # 4) 잘린 태그 제거
    t = re.sub(r"<\w[^<]*$", "", t)          # 끝까지 닫히지 않은 태그
    t = re.sub(r"<\w[^<]*?(?=<)", "", t)     # 다음 < 전에 닫히지 않은 태그
    t = re.sub(r"<\w[^>]*", "", t)           # 기타 미완성 태그
    # 5) 잔여 < > 제거
    t = t.replace("<", " ").replace(">", " ")
    # 6) 공백 정리
    t = re.sub(r"\s+", " ", t).strip()
    return t


def fix_html_artifacts_in_archives(archive_dir: str) -> int:
    """기존 아카이브 HTML에서 잘못 렌더된 HTML 아티팩트를 제거한다.

    이중 인코딩 버그로 entry-desc에 &lt;img...&gt; 텍스트가 삽입된 경우를 정리.
    Returns: 수정된 파일 수
    """
    artifact_desc = re.compile(
        r'<p class="entry-desc">\s*&lt;(?:img|figure|picture|video)[^<]*?</p>',
        re.DOTALL,
    )
    fixed = 0
    for fname in os.listdir(archive_dir):
        if not fname.endswith(".html"):
            continue
        fpath = os.path.join(archive_dir, fname)
        try:
            with open(fpath, encoding="utf-8") as f:
                content = f.read()
            cleaned = artifact_desc.sub("", content)
            if cleaned != content:
                with open(fpath, "w", encoding="utf-8") as f:
                    f.write(cleaned)
                fixed += 1
                print(f"[FIX] HTML 아티팩트 제거: {fname}", file=sys.stderr)
        except Exception as exc:
            print(f"[WARN] 아카이브 정리 실패 {fname}: {exc}", file=sys.stderr)
    return fixed


def normalize_title(title: str) -> str:
    """제목 매칭용 정규화: 공백 압축 + 끝 ' - 매체명' 제거 + 소문자."""
    if not title:
        return ""
    t = re.sub(r"\s+", " ", title).strip()
    t = re.sub(r"\s+-\s+[^-]{2,30}\s*$", "", t).strip()
    return t.lower()


def parse_ai_summary_txt(text: str) -> dict[str, str]:
    """newsletter/요약 .txt 파일을 파싱하여 {normalized_title: ai_summary} 반환.

    지원 포맷 두 가지:

    Format A (ai-tech newsletter):
      1. 제목
         AI 요약 (들여쓰기 한 줄, 한국어)
         https://...

    Format B (ai-paper):
      1. 제목
         - AI 요약 (들여쓰기 + 하이픈)
         - [논문 보기](URL)
    """
    if not text:
        return {}
    result: dict[str, str] = {}

    # 번호 항목으로 분할 (각 블록 시작이 'N. ')
    blocks = re.split(r"(?m)^(?=\d{1,2}\.\s+)", text)
    for blk in blocks:
        m = re.match(r"^(\d{1,2})\.\s+(.+?)(?:\n|$)", blk)
        if not m:
            continue
        title = m.group(2).strip()
        rest = blk[m.end():]

        summary_lines: list[str] = []
        for line in rest.split("\n"):
            ln = line.strip()
            if not ln:
                continue
            # 종료 조건: 푸터/섹션 구분자 만나면 이 항목의 요약 수집 중단
            if (
                ln.startswith("──") or ln.startswith("━━") or ln.startswith("==")
                or ln.startswith("# ") or ln.startswith("☕")
                or "한 줄 요약" in ln or "한줄요약" in ln
                or re.match(r"^[\s─-╿─━═#]+$", ln)
            ):
                break
            # URL 라인 스킵
            if ln.startswith("http://") or ln.startswith("https://"):
                continue
            # 마크다운 링크 라인 스킵: [...] (...)
            if re.match(r"^-?\s*\[.+?\]\(.+?\)\s*$", ln):
                continue
            # 하이픈 prefix 제거 (Format B)
            if ln.startswith("- "):
                ln = ln[2:].strip()
            elif ln.startswith("-"):
                ln = ln[1:].strip()
            if not ln:
                continue
            summary_lines.append(ln)

        if summary_lines:
            result[normalize_title(title)] = " ".join(summary_lines)

    return result


def fetch_ai_summaries(key: str, cfg: dict, target_date: str) -> dict[str, str]:
    """소스의 AI 요약 .txt 파일을 페치하여 {title: summary} 매핑 반환.

    cfg["ai_summary_file"]가 None이면 빈 dict.
    """
    pattern = cfg.get("ai_summary_file")
    if not pattern:
        return {}
    yyyymmdd = target_date.replace("-", "")
    filename = pattern.replace("{YYYYMMDD}", yyyymmdd)
    path = f"{cfg['data_dir']}/{target_date}/{filename}"
    raw = fetch_file(cfg["repo"], path)
    if raw is None:
        return {}
    summaries = parse_ai_summary_txt(raw)
    if summaries:
        print(f"[OK] {key}: AI 요약 {len(summaries)}건 파싱", file=sys.stderr)
    return summaries


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

    # 요약 우선순위: ai_summary (newsletter.txt에서 머지된 한국어 요약)
    # → 그게 없으면 JSON 'summary' 필드 (영문 초록/RSS 본문)
    ai_summary = str(item.get("ai_summary", "")).strip()
    json_summary = str(item.get(cfg.get("summary_field", "summary"), "")).strip()
    used_ai_summary = bool(ai_summary)
    summary_raw = ai_summary if ai_summary else json_summary

    title_clean = clean_title(raw_title, source_raw)
    title = escape_html(title_clean) if title_clean else "제목 없음"
    source = escape_html(source_raw)
    date_fmt = format_date(date_raw)
    # strip_html 강화: 잘린 태그/엔티티/HTML 모두 처리
    clean_sum = strip_html(summary_raw)
    # 뉴스 기사 서두의 '[매체=기자이름 기자]' 형태 attribution 제거
    clean_sum = re.sub(r'^\s*\[[^\]]{2,30}\]\s*', '', clean_sum)
    # 한국어 AI 요약은 전문 표시, 영문 원본(초록/RSS 본문)은 250자로 제한
    if not used_ai_summary and len(clean_sum) > 250:
        clean_sum = clean_sum[:250].rsplit(' ', 1)[0] + '…'

    # meta 컴포지션
    meta_parts: list[str] = []
    if source:
        meta_parts.append(f'<span class="entry-src">{source}</span>')
    if source and date_fmt:
        meta_parts.append('<span class="entry-sep" aria-hidden="true">·</span>')
    if date_fmt:
        meta_parts.append(f'<span class="entry-dt">{date_fmt}</span>')
    # 키워드 배지: 15자 초과(긴 영문 학술 용어 등)는 표시 안 함
    if keyword and keyword not in ("press_rss", "None", "") and len(keyword) <= 15:
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


def item_description_text(item: dict, cfg: dict) -> str:
    """아이템의 최종 설명 텍스트를 반환 (없으면 빈 문자열).

    render_entry와 동일한 우선순위: ai_summary → json summary → strip_html → attribution 제거
    """
    ai_sum = str(item.get("ai_summary", "")).strip()
    json_sum = str(item.get(cfg.get("summary_field", "summary"), "")).strip()
    raw = ai_sum if ai_sum else json_sum
    text = strip_html(raw)
    text = re.sub(r'^\s*\[[^\]]{2,30}\]\s*', '', text)
    return text


def filter_described(items: list[dict], cfg: dict, source_key: str) -> list[dict]:
    """설명이 있는 기사만 반환.

    - ai-paper : 필터 없음 — 항상 AI 요약 보장
    - edu-news : 필터 없음 — newsletter AI 요약 세팅 완료, 과도기 기사도 제목만으로 표시
    - ai-tech  : 설명(20자+) 없는 기사 제외, 전부 없으면 원본 유지
    """
    if source_key in ("ai-paper", "edu-news"):
        return items
    described = [it for it in items if len(item_description_text(it, cfg)) >= 20]
    return described if described else items


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
    """오늘 날짜 JSON을 페치하고, 가능하면 AI 요약 .txt도 머지한다.

    각 아이템에 'ai_summary' 키가 추가될 수 있다 (제목 매칭 성공 시).
    실패 시 빈 리스트 반환.
    """
    yyyymmdd = today.replace("-", "")
    filename = cfg["file_template"].replace("{YYYYMMDD}", yyyymmdd)
    path = f"{cfg['data_dir']}/{today}/{filename}"
    raw = fetch_file(cfg["repo"], path)
    if raw is None:
        print(f"[WARN] {key}: {today} 파일 없음 ({path})", file=sys.stderr)
        return []
    items = parse_items(raw)
    print(f"[OK] {key}: {len(items)}건 로드", file=sys.stderr)

    # AI 요약 머지 (있는 소스만)
    ai_summaries = fetch_ai_summaries(key, cfg, today)
    if ai_summaries:
        matched = 0
        # 제목 기반 매칭 — 정규화 후 정확/접두 매칭 시도
        norm_to_summary = ai_summaries
        norm_keys = list(norm_to_summary.keys())
        for item in items:
            t = normalize_title(str(item.get(cfg["title_field"], "")))
            if not t:
                continue
            # 1) 정확 매칭
            if t in norm_to_summary:
                item["ai_summary"] = norm_to_summary[t]
                matched += 1
                continue
            # 2) 접두 매칭 (제목 앞 20자 일치)
            t_prefix = t[:20]
            found = False
            for k in norm_keys:
                if k.startswith(t_prefix) or t.startswith(k[:20]):
                    item["ai_summary"] = norm_to_summary[k]
                    matched += 1
                    found = True
                    break
            if found:
                continue
            # 3) 유사도 매칭 — 논문 제목처럼 긴 문자열 대응 (임계값 0.72)
            best_r, best_k = 0.0, None
            for k in norm_keys:
                r = SequenceMatcher(None, t, k, autojunk=False).ratio()
                if r > best_r:
                    best_r, best_k = r, k
            if best_r >= 0.72 and best_k:
                item["ai_summary"] = norm_to_summary[best_k]
                matched += 1
        print(f"[OK] {key}: AI 요약 매칭 {matched}/{len(items)}건", file=sys.stderr)

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
# dates.json 관리 (archive_dir 스캔 기반)
# ---------------------------------------------------------------------------


def update_dates_json(today: str, docs_dir: str, archive_dir: str) -> None:
    """archive_dir를 스캔하여 모든 아카이브 날짜 + 오늘을 dates.json에 기록한다."""
    json_path = os.path.join(docs_dir, "assets", "dates.json")

    dates: list[str] = []
    if os.path.isdir(archive_dir):
        for fname in os.listdir(archive_dir):
            if not fname.endswith(".html"):
                continue
            stem = fname[:-5]
            try:
                datetime.strptime(stem, "%Y-%m-%d")
                dates.append(stem)
            except ValueError:
                continue

    # 오늘은 항상 포함 (index.html은 archive에 없을 수도 있음)
    if today not in dates:
        dates.append(today)

    dates = sorted(set(dates))

    # 28일 초과 제거
    cutoff_dt = datetime.strptime(today, "%Y-%m-%d").date() - timedelta(days=KEEP_DAYS)
    dates = [d for d in dates if datetime.strptime(d, "%Y-%m-%d").date() > cutoff_dt]

    result = {"available_dates": dates, "latest": today}

    os.makedirs(os.path.dirname(json_path), exist_ok=True)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"[OK] dates.json: {len(dates)}개 날짜, latest={today}", file=sys.stderr)


# ---------------------------------------------------------------------------
# 단일 날짜 렌더링 (백필/오늘 공용)
# ---------------------------------------------------------------------------


def fixup_archive_paths(html: str) -> str:
    """archive/ 하위 HTML에서 자산 경로를 ../assets/ 로 보정한다.

    템플릿은 root(docs/index.html) 기준 상대경로 'assets/' 를 사용하므로,
    archive/YYYY-MM-DD.html에 그대로 저장하면 'docs/archive/assets/' 로
    잘못 해석된다. 이 함수가 그것을 보정.
    """
    return (
        html
        .replace('href="assets/', 'href="../assets/')
        .replace('src="assets/', 'src="../assets/')
    )


def fix_existing_archive_paths(archive_dir: str) -> int:
    """기존 archive/*.html 파일의 자산 경로를 일괄 보정. 이미 보정된 파일은 스킵."""
    if not os.path.isdir(archive_dir):
        return 0
    fixed = 0
    for fname in os.listdir(archive_dir):
        if not fname.endswith(".html"):
            continue
        path = os.path.join(archive_dir, fname)
        with open(path, encoding="utf-8") as f:
            content = f.read()
        if 'href="assets/' not in content and 'src="assets/' not in content:
            continue
        new_content = fixup_archive_paths(content)
        with open(path, "w", encoding="utf-8") as f:
            f.write(new_content)
        fixed += 1
    if fixed:
        print(f"[OK] 기존 아카이브 경로 보정: {fixed}개 파일", file=sys.stderr)
    return fixed


def upgrade_archives_to_v2(
    archive_dir: str, last_updated_iso: str, last_updated_kr: str
) -> int:
    """기존 archive/*.html을 v2 템플릿 수준으로 일괄 업그레이드한다.

    패치 항목 (이미 적용된 항목은 마커 체크로 스킵 — 멱등적):
    1. <head>: canonical, manifest, theme-color, OG, Twitter, JSON-LD
    2. <body> 직후: skip-link
    3. date-nav 직후: 검색바
    4. brand-tag 텍스트 업데이트
    5. footer: profile-card가 없으면 전체 교체
    6. </body> 직전: toast-container

    반환: 실제 수정된 파일 수
    """
    if not os.path.isdir(archive_dir):
        return 0

    SEARCH_BAR = (
        '  <div class="search-bar-wrap" role="search" aria-label="기사 검색">\n'
        '    <div class="search-bar-inner">\n'
        '      <svg class="search-icon" aria-hidden="true" width="15" height="15"'
        ' viewBox="0 0 15 15" fill="none">\n'
        '        <circle cx="6.5" cy="6.5" r="5.25" stroke="currentColor" stroke-width="1.4"/>\n'
        '        <path d="M10.5 10.5L13.5 13.5" stroke="currentColor"'
        ' stroke-width="1.4" stroke-linecap="round"/>\n'
        '      </svg>\n'
        '      <input type="search" id="di-search" class="search-input"\n'
        '             placeholder="제목, 요약, 출처 검색… (단축키: /)"\n'
        '             aria-label="기사 검색" autocomplete="off" spellcheck="false">\n'
        '      <span class="search-count-badge" aria-live="polite"'
        ' aria-atomic="true" hidden></span>\n'
        '      <button class="search-clear" type="button"'
        ' aria-label="검색어 지우기" hidden>✕</button>\n'
        '    </div>\n'
        '  </div>'
    )

    upgraded = 0
    for fname in sorted(os.listdir(archive_dir)):
        if not fname.endswith(".html"):
            continue
        date_str = fname[:-5]
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            continue

        fpath = os.path.join(archive_dir, fname)
        try:
            with open(fpath, encoding="utf-8") as f:
                content = f.read()
        except Exception as exc:
            print(f"[WARN] 업그레이드 읽기 실패 {fname}: {exc}", file=sys.stderr)
            continue

        original = content
        date_kr = f"{dt.year}년 {dt.month}월 {dt.day}일"
        canonical_url = f"{BASE_URL}/archive/{date_str}.html"

        # 1. <head> 보강 (manifest 유무로 체크)
        if 'rel="manifest"' not in content:
            head_block = (
                f'  <link rel="canonical" href="{canonical_url}">\n'
                f'  <link rel="manifest" href="../assets/manifest.json">\n'
                f'  <meta name="theme-color" content="#131a2a">\n'
                f'  <!-- Open Graph -->\n'
                f'  <meta property="og:type" content="website">\n'
                f'  <meta property="og:title" content="Daily Intelligence — {date_kr}">\n'
                f'  <meta property="og:description"'
                f' content="교육 뉴스, AI 논문, AI 기술 뉴스 일일 브리핑 — 닷커넥터 김진관">\n'
                f'  <meta property="og:url" content="{canonical_url}">\n'
                f'  <meta property="og:image" content="{BASE_URL}/assets/facilitator.png">\n'
                f'  <meta property="og:locale" content="ko_KR">\n'
                f'  <!-- Twitter Card -->\n'
                f'  <meta name="twitter:card" content="summary">\n'
                f'  <meta name="twitter:title" content="Daily Intelligence — {date_kr}">\n'
                f'  <meta name="twitter:description"'
                f' content="교육 뉴스, AI 논문, AI 기술 뉴스 일일 브리핑">\n'
                f'  <meta name="twitter:image" content="{BASE_URL}/assets/facilitator.png">\n'
                f'  <!-- JSON-LD -->\n'
                f'  <script type="application/ld+json">\n'
                f'  {{\n'
                f'    "@context": "https://schema.org",\n'
                f'    "@type": "WebPage",\n'
                f'    "name": "Daily Intelligence — {date_kr}",\n'
                f'    "description": "교육 뉴스, AI 논문, AI 기술 뉴스 일일 브리핑",\n'
                f'    "url": "{canonical_url}",\n'
                f'    "inLanguage": "ko",\n'
                f'    "publisher": {{\n'
                f'      "@type": "Person",\n'
                f'      "name": "닷커넥터 김진관",\n'
                f'      "url": "https://litt.ly/dot_connector"\n'
                f'    }},\n'
                f'    "dateModified": "{last_updated_iso}"\n'
                f'  }}\n'
                f'  </script>'
            )
            content = content.replace("</head>", head_block + "\n</head>", 1)

        # 2. skip-link
        if 'class="skip-link"' not in content:
            content = re.sub(
                r'(<body[^>]*>)',
                r'\1\n\n  <a class="skip-link" href="#main-content">본문으로 건너뛰기</a>',
                content,
                count=1,
            )

        # 3. 검색바 — 첫 번째 </nav>(date-nav) 직후 삽입
        if 'class="search-bar-wrap"' not in content:
            idx = content.find('</nav>')
            if idx != -1:
                ins = idx + len('</nav>')
                content = content[:ins] + '\n\n' + SEARCH_BAR + '\n' + content[ins:]

        # 4. brand-tag 텍스트
        content = content.replace(
            ">EDU · PAPERS · TECH<",
            ">EDU · PAPERS · TECH 뉴스 일일 브리핑<",
        )

        # 5. footer 교체 (profile-card 없는 구버전)
        if 'class="profile-card"' not in content:
            new_footer = (
                '  <footer class="site-footer">\n'
                '    <a class="profile-card" href="https://litt.ly/dot_connector"'
                ' target="_blank" rel="noopener noreferrer"'
                ' aria-label="닷커넥터 김진관의 링크 페이지로 이동">\n'
                '      <img class="profile-photo" src="../assets/facilitator.png"'
                ' alt="닷커넥터 김진관" width="64" height="64" loading="lazy">\n'
                '      <span class="profile-name">닷커넥터'
                '<span class="profile-name-sub">(김진관)</span></span>\n'
                '      <span class="profile-bio">배움, 나눔, 성장을 추구하는 연결주의자</span>\n'
                '      <span class="profile-link-hint">litt.ly/dot_connector ↗</span>\n'
                '    </a>\n'
                '    <div class="footer-meta">\n'
                f'      <span class="footer-updated">갱신'
                f' <time datetime="{last_updated_iso}">{last_updated_kr}</time></span>\n'
                '      <a class="footer-link" href="https://github.com/tigerjk9"'
                ' target="_blank" rel="noopener noreferrer">GitHub ↗</a>\n'
                '    </div>\n'
                '  </footer>'
            )
            content = re.sub(
                r'<footer class="site-footer">.*?</footer>',
                new_footer,
                content,
                flags=re.DOTALL,
            )

        # 6. toast-container
        if 'toast-container' not in content:
            content = content.replace(
                '<script src="../assets/app.js">',
                '  <div class="toast-container" aria-live="polite" aria-atomic="true"'
                ' aria-relevant="additions"></div>\n\n  <script src="../assets/app.js">',
                1,
            )

        if content != original:
            try:
                with open(fpath, "w", encoding="utf-8") as f:
                    f.write(content)
                upgraded += 1
                print(f"[UPGRADE] {fname}", file=sys.stderr)
            except Exception as exc:
                print(f"[WARN] 업그레이드 저장 실패 {fname}: {exc}", file=sys.stderr)

    if upgraded:
        print(f"[OK] 아카이브 v2 업그레이드: {upgraded}개 파일", file=sys.stderr)
    return upgraded


# ---------------------------------------------------------------------------
# 단일 날짜 렌더링 (백필/오늘 공용)
# ---------------------------------------------------------------------------


def render_date_html(
    target_date: str,
    template: str,
    date_nav: str,
    last_updated_iso: str,
    last_updated_kr: str,
) -> tuple[str, int]:
    """target_date의 3개 소스를 페치하여 HTML 문자열과 총 아이템 수를 반환한다.

    아이템이 0개여도 HTML은 반환한다 (호출자가 저장 여부 판단).
    """
    cards: dict[str, str] = {}
    counts: dict[str, int] = {}
    for key, cfg in SOURCES.items():
        try:
            items = fetch_today_source(key, cfg, target_date)
            before = len(items)
            items = filter_described(items, cfg, key)
            after = len(items)
            if after < before:
                print(f"[INFO] {key}: 설명 없는 기사 {before - after}건 제외 → {after}건 표시", file=sys.stderr)
            counts[key] = len(items)
            cards[key] = render_section_body(items, cfg, key)
        except Exception as exc:
            print(f"[ERROR] {key} {target_date}: {exc}", file=sys.stderr)
            counts[key] = 0
            label = cfg.get("label", "데이터")
            cards[key] = f'<p class="col-empty">이 날짜의 {label} 데이터가 없습니다.</p>'

    total = sum(counts.values())

    dt_obj = datetime.strptime(target_date, "%Y-%m-%d")
    _WEEKDAYS = ['월', '화', '수', '목', '금', '토', '일']
    current_date_kr = (
        f"{dt_obj.year}년 {dt_obj.month}월 {dt_obj.day}일"
        f" {_WEEKDAYS[dt_obj.weekday()]}요일"
    )

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
    return html, total


# ---------------------------------------------------------------------------
# 백필: 과거 27일치 아카이브 자동 생성
# ---------------------------------------------------------------------------


def backfill_archives(
    today: str,
    archive_dir: str,
    template: str,
    last_updated_iso: str,
    last_updated_kr: str,
) -> int:
    """archive_dir에 없는 과거 27일치 날짜를 페치하여 HTML을 생성한다.

    date_nav는 빈 문자열 — JS가 페이지 로드 시 dates.json 기반으로 채운다.
    반환: 새로 생성된 아카이브 개수.
    """
    today_dt = datetime.strptime(today, "%Y-%m-%d").date()
    created = 0
    for delta in range(1, KEEP_DAYS):
        target_dt = today_dt - timedelta(days=delta)
        target_str = target_dt.strftime("%Y-%m-%d")
        archive_path = os.path.join(archive_dir, f"{target_str}.html")
        if os.path.isfile(archive_path):
            continue

        html, total = render_date_html(
            target_str, template, "", last_updated_iso, last_updated_kr
        )
        if total == 0:
            print(f"[SKIP] {target_str}: 데이터 없음", file=sys.stderr)
            continue

        canonical = f"{BASE_URL}/archive/{target_str}.html"
        with open(archive_path, "w", encoding="utf-8") as f:
            f.write(fixup_archive_paths(html).replace("{{PAGE_CANONICAL}}", canonical))
        created += 1
        print(f"[BACKFILL] {target_str}.html ({total}건)", file=sys.stderr)

    if created:
        print(f"[OK] 백필 완료: {created}개 아카이브 신규 생성", file=sys.stderr)
    else:
        print("[OK] 백필 필요 없음 (전부 존재 또는 데이터 없음)", file=sys.stderr)
    return created


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
    from datetime import timezone

    today = date.today().isoformat()

    # 경로 계산
    script_dir = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.dirname(script_dir)
    docs_dir = os.path.join(repo_root, "docs")
    archive_dir = os.path.join(docs_dir, "archive")
    template_path = os.path.join(docs_dir, "_template.html")
    output_path = os.path.join(docs_dir, "index.html")

    print(f"[START] {today} 뉴스 생성 시작", file=sys.stderr)

    # 1. 템플릿 로드
    if not os.path.isfile(template_path):
        print(f"[ERROR] 템플릿 없음: {template_path}", file=sys.stderr)
        sys.exit(1)
    with open(template_path, encoding="utf-8") as f:
        template = f.read()

    os.makedirs(archive_dir, exist_ok=True)

    # 2. KST 갱신 시각
    KST = timezone(timedelta(hours=9))
    now_kst = datetime.now(tz=KST)
    # GitHub Actions cron은 UTC 01:00 = KST 10:00 실행이므로 스케줄 시각으로 고정
    if os.environ.get("GITHUB_ACTIONS"):
        now_kst = now_kst.replace(hour=10, minute=0, second=0, microsecond=0)
    last_updated_iso = now_kst.strftime("%Y-%m-%dT%H:%M:%S+09:00")
    last_updated_kr = f"{now_kst.year}년 {now_kst.month}월 {now_kst.day}일 {now_kst.strftime('%H:%M')} KST"

    # 2.5. 기존 archive 파일들의 자산 경로 일괄 보정 (구버전 잔재 정리)
    fix_existing_archive_paths(archive_dir)
    fix_html_artifacts_in_archives(archive_dir)
    upgrade_archives_to_v2(archive_dir, last_updated_iso, last_updated_kr)

    # 3. 백필: archive_dir에 없는 과거 27일치 페치
    backfill_archives(today, archive_dir, template, last_updated_iso, last_updated_kr)

    # 4. 날짜 네비게이션 (정적 fallback — JS가 dates.json 기반으로 덮어씀)
    date_nav = build_date_nav(today, archive_dir)

    # 5. 오늘 렌더링
    html, total = render_date_html(today, template, date_nav, last_updated_iso, last_updated_kr)
    print(f"[OK] 오늘({today}): 총 {total}건", file=sys.stderr)

    # 6. archive/{today}.html 저장 (경로 보정 + canonical 적용)
    archive_path = os.path.join(archive_dir, f"{today}.html")
    archive_canonical = f"{BASE_URL}/archive/{today}.html"
    with open(archive_path, "w", encoding="utf-8") as f:
        f.write(fixup_archive_paths(html).replace("{{PAGE_CANONICAL}}", archive_canonical))
    print(f"[OK] 아카이브 저장: {archive_path}", file=sys.stderr)

    # 7. index.html 갱신 (root canonical)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html.replace("{{PAGE_CANONICAL}}", BASE_URL + "/"))
    print(f"[OK] index.html 갱신: {output_path}", file=sys.stderr)

    # 8. dates.json 업데이트 (archive_dir 스캔)
    update_dates_json(today, docs_dir, archive_dir)

    # 9. 28일 초과 아카이브 삭제
    cleanup_archive(archive_dir)

    print(f"[DONE] {today} 완료", file=sys.stderr)


if __name__ == "__main__":
    main()
