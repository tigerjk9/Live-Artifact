#!/usr/bin/env python3
"""Daily news fetcher and HTML generator for Live Artifact.

소스 레포 3곳에서 날짜별 JSON·요약 TXT를 페치해
  1) docs/data/YYYY-MM-DD.json  — 정규화된 영구 레코드 (주제·주체 분류 포함, 삭제 안 함)
  2) docs/archive/YYYY-MM-DD.html, docs/index.html — '오늘의 흐름' 보드가 붙은 페이지
  3) docs/data/index.json, search.json, docs/assets/dates.json — 아카이브 탐색·흐름 페이지 재료
를 만든다.

사용법
  python scripts/fetch_and_generate.py                 # 오늘 생성 (+ 최근 7일 누락분 보강)
  python scripts/fetch_and_generate.py --backfill-all  # 소스 레포에 남은 전 기간을 data/로 복구
  python scripts/fetch_and_generate.py --rebuild-archives  # data/ 전부를 현재 템플릿으로 다시 렌더
  python scripts/fetch_and_generate.py --date 2026-10-30   # 특정 날짜만 (폴백 없이) 재생성
환경변수
  NEWS_TOKEN       소스 레포 read PAT (없으면 비인증 — 시간당 60회 제한)
  GEMINI_API_KEY   있으면 오늘 레코드에 Gemini 종합(헤드라인·흐름 3개)을 붙인다 (선택)
"""

from __future__ import annotations

import argparse
import base64
import html
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher

import requests
from dateutil import parser as dateutil_parser

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from insights import (  # noqa: E402
    SECTIONS,
    SECTION_SHORT,
    build_entity_index,
    build_index,
    build_search,
    compute_board,
    is_dup,
    list_dates,
    load_day,
    record_ai_count,
    record_total,
    render_board,
    save_day,
)
from enrich import enrich_range, enrich_record  # noqa: E402
from feeds import build_feeds  # noqa: E402
from synthesis import synthesize  # noqa: E402
from taxonomy import classify, detect_kind, extract_entities, topic_label  # noqa: E402
from weekly import build_weekly  # noqa: E402
import subprocess  # noqa: E402

# ---------------------------------------------------------------------------
# 설정
# ---------------------------------------------------------------------------

BASE_URL = "https://tigerjk9.github.io/Live-Artifact"
KST = timezone(timedelta(hours=9))

TOKEN = os.environ.get("NEWS_TOKEN", "")
HEADERS = (
    {"Authorization": f"token {TOKEN}", "Accept": "application/vnd.github.v3+json"}
    if TOKEN
    else {"Accept": "application/vnd.github.v3+json"}
)

SOURCES: dict[str, dict] = {
    "edu-news": {
        "section": "edu",
        "repo": "tigerjk9/Auto-Edu-news-Collector",
        "label": "교육 뉴스",
        "data_dir": "news",
        "file_template": "education_news_{YYYYMMDD}.json",
        "ai_summary_file": "education_news_{YYYYMMDD}_newsletter.txt",
        # 뉴스레터에 요약이 없던 기간(2026-03~04)의 보조 소스 — RSS 본문 '요약:' 줄
        "plain_summary_file": "education_news_{YYYYMMDD}.txt",
        "url_field": "link",
        "title_field": "title",
        "summary_field": "summary",
        "source_field": "press",
        "date_field": "date",
        "keyword_field": "keyword",
    },
    "ai-paper": {
        "section": "paper",
        "repo": "tigerjk9/Auto-AI-Edu-Paper-Curator",
        "label": "AI 교육 논문",
        "data_dir": "papers",
        "file_template": "ai_edu_papers_{YYYYMMDD}.json",
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
        "section": "tech",
        "repo": "tigerjk9/Auto-AI-Tech-news-Collector",
        "label": "AI 기술 뉴스",
        "data_dir": "news",
        "file_template": "ai_tech_news_{YYYYMMDD}.json",
        "ai_summary_file": "ai_tech_news_{YYYYMMDD}_newsletter.txt",
        "url_field": "link",
        "title_field": "title",
        "summary_field": "summary",
        "source_field": "press",
        "date_field": "date",
        "keyword_field": "keyword",
    },
}
SECTION_SOURCE = {cfg["section"]: key for key, cfg in SOURCES.items()}

# 날짜 pill 정적 폴백 개수 (JS가 dates.json으로 덮어쓴다)
NAV_DAYS = 14
# 오늘 실행 때 최근 며칠의 누락 레코드를 보강할지 (소스 커밋이 늦게 떨어지는 날 대비)
RECENT_BACKFILL_DAYS = 7
# 한국어 AI 요약이 이 비율 미만이면 "미완성"으로 보고 안내 배너 + 워크플로우 게이트 재시도
AI_COVERAGE_MIN_PCT = 60

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
            print(f"[ERROR] GitHub API {resp.status_code}: {repo}/{path}", file=sys.stderr)
            return None
        data = resp.json()
        content = data.get("content", "")
        return base64.b64decode(content.replace("\n", "")).decode("utf-8")
    except Exception as exc:
        print(f"[ERROR] fetch_file({repo}/{path}): {exc}", file=sys.stderr)
        return None


def list_source_dates(repo: str, data_dir: str) -> list[str]:
    """소스 레포의 날짜 디렉터리 목록 (YYYY-MM-DD). Contents API는 최대 1000개."""
    url = f"https://api.github.com/repos/{repo}/contents/{data_dir}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        if resp.status_code != 200:
            print(f"[ERROR] 디렉터리 목록 {resp.status_code}: {repo}/{data_dir}", file=sys.stderr)
            return []
        out = []
        for ent in resp.json():
            if ent.get("type") == "dir" and re.fullmatch(r"\d{4}-\d{2}-\d{2}", ent.get("name", "")):
                out.append(ent["name"])
        return sorted(out)
    except Exception as exc:
        print(f"[ERROR] list_source_dates({repo}): {exc}", file=sys.stderr)
        return []


# ---------------------------------------------------------------------------
# 파싱
# ---------------------------------------------------------------------------


_CONFLICT_LINE_RE = re.compile(r"^(?:<{7}|={7}|>{7}).*$\n?", re.MULTILINE)
_CONFLICT_BLOCK_RE = re.compile(r"^<{7}[^\n]*\n(.*?)^={7}[^\n]*\n(.*?)^>{7}[^\n]*\n?", re.DOTALL | re.MULTILINE)


def repair_json_variants(raw: str):
    """소스 레포에 가끔 남는 깨진 JSON(git 충돌 마커 — 2025-12-19 등 4일)을 살리는 후보들.

    마커만 지우기 → 충돌의 뒤쪽(theirs)만 남기기 → 앞쪽(ours)만 남기기 순으로 시도한다.
    후행 쉼표도 함께 정리한다.
    """
    for fixed in (
        _CONFLICT_LINE_RE.sub("", raw),
        _CONFLICT_BLOCK_RE.sub(lambda m: m.group(2), raw),
        _CONFLICT_BLOCK_RE.sub(lambda m: m.group(1), raw),
    ):
        yield re.sub(r",(\s*[}\]])", r"\1", fixed)


def parse_items(raw: str) -> list[dict]:
    """JSON 문자열을 파싱하여 아이템 목록을 반환한다 (배열 또는 {items|data|...: [...]}).

    파싱 실패 시 repair_json_variants()로 재시도하고, 충돌 양쪽이 모두 남아 생긴 중복은 URL로 제거한다.
    """
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        data = None
        for candidate in repair_json_variants(raw):
            try:
                data = json.loads(candidate)
                print(f"[WARN] JSON 복구 후 파싱 (원인: {exc})", file=sys.stderr)
                break
            except json.JSONDecodeError:
                continue
        if data is None:
            print(f"[ERROR] JSON 파싱 실패: {exc}", file=sys.stderr)
            return []
    items: list | None = None
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        for key in ("items", "data", "results", "news", "papers"):
            if key in data and isinstance(data[key], list):
                items = data[key]
                break
        if items is None:
            for val in data.values():
                if isinstance(val, list):
                    items = val
                    break
    if items is None:
        print(f"[WARN] 인식할 수 없는 JSON 구조: {type(data)}", file=sys.stderr)
        return []
    seen: set[str] = set()
    out: list[dict] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        key = str(it.get("link") or it.get("url") or it.get("title") or "")
        if key and key in seen:
            continue
        seen.add(key)
        out.append(it)
    return out


def iso_date(date_str: str) -> str:
    """다양한 날짜 문자열을 YYYY-MM-DD로. 실패 시 ''."""
    if not date_str:
        return ""
    try:
        return dateutil_parser.parse(date_str).date().isoformat()
    except Exception:
        m = re.search(r"(\d{4})-(\d{2})-(\d{2})", date_str)
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else ""


def format_date(date_str: str) -> str:
    """YYYY-MM-DD 또는 임의 형식 → 'M월 D일'. 실패 시 원본."""
    iso = iso_date(date_str)
    if iso:
        y, m, d = iso.split("-")
        return f"{int(m)}월 {int(d)}일"
    return date_str


def format_authors(authors_raw: str) -> str:
    """저자 문자열을 최대 2명 + '외 N명' 형식으로 줄인다."""
    if not authors_raw:
        return ""
    parts = [a.strip() for a in authors_raw.split(",") if a.strip()]
    if len(parts) <= 2 and len(authors_raw) <= 50:
        return ", ".join(parts)
    shown = parts[:2]
    rest = len(parts) - 2
    return f"{', '.join(shown)} 외 {rest}명" if rest > 0 else ", ".join(shown)


def escape_html(text: str) -> str:
    return (
        str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    )


def strip_html(text: str) -> str:
    """HTML 태그/엔티티/잘린 태그를 모두 제거하고 공백 정리한다 (이중 인코딩 포함)."""
    if not text:
        return ""
    t = html.unescape(html.unescape(text))
    t = re.sub(r"<(?:img|figure|picture|video|source|iframe)\b[^>]*>", "", t, flags=re.IGNORECASE | re.DOTALL)
    t = re.sub(r"<[^>]*>", "", t, flags=re.DOTALL)
    t = re.sub(r"<\w[^<]*$", "", t)
    t = re.sub(r"<\w[^<]*?(?=<)", "", t)
    t = re.sub(r"<\w[^>]*", "", t)
    t = t.replace("<", " ").replace(">", " ")
    return re.sub(r"\s+", " ", t).strip()


def normalize_title(title: str) -> str:
    """제목 매칭용 정규화: 공백 압축 + 끝 ' - 매체명' 제거 + 소문자."""
    if not title:
        return ""
    t = re.sub(r"\s+", " ", title).strip()
    t = re.sub(r"\s+-\s+[^-]{2,30}\s*$", "", t).strip()
    return t.lower()


def clean_title(title: str, source: str) -> str:
    """제목 끝의 ' - 매체명' 중복 접미사를 제거한다 (Google News RSS 형식)."""
    if not title:
        return ""
    t = title.strip()
    if source:
        suffix = f" - {source}"
        if t.endswith(suffix):
            t = t[: -len(suffix)].strip()
    m = re.search(r"\s+-\s+([^\-]{2,20})\s*$", t)
    if m:
        t = t[: m.start()].strip()
    return t


# ---------------------------------------------------------------------------
# AI 요약 TXT 파싱 — 세 가지 포맷
# ---------------------------------------------------------------------------

_EMOJI_HEAD_RE = re.compile(r"^#\s*(?:([1-9])️?⃣|\U0001F51F)\s*(.+?)\s*$", re.MULTILINE)
_NOTE_RE = re.compile(
    r"^>?\s*(?:오늘의\s*(?:한\s*줄\s*요약|AI\s*트렌드|핵심|교육\s*트렌드)|한줄요약)\s*[:：]\s*(.+?)\s*$"
)
_FOOTER_RE = re.compile(r"^(?:──|━━|==|# |☕)|^[\s─-╿─━═#]+$")
# 수집기가 Gemini 실패 시 넣는 상투 문구 — 헤드라인으로 쓸 가치가 없다
_BOILERPLATE_NOTE_RE = re.compile(r"^(?:교육|AI|인공지능)[을를]?\s*중심으로\s*교육\s*현장의\s*혁신이\s*가속화되고\s*있습니다\.?$")


def parse_ai_summary_txt(text: str) -> tuple[dict[str, dict], str | None]:
    """newsletter/요약 .txt → ({normalized_title: {"summary", "implication"}}, 일일 한 줄 요약).

    Format A (2026-04~, 뉴스): `N. 제목` / `   요약` / `   → 시사점`(교육) / `   URL`
    Format B (논문):           `N. 제목` / `   - 요약` / `   - [논문 보기](URL)`
    Format C (2025-11~2026-03): `# 1️⃣ 제목` / `오피니언: 요약` / `🔗 링크: URL`,
                                 머리에 `| 1️⃣ | 제목 |` 표와 `> 오늘의 한 줄 요약: …`
    """
    if not text:
        return {}, None
    note: str | None = None
    for line in text.split("\n"):
        m = _NOTE_RE.match(line.strip())
        if m:
            note = re.sub(r"\s*[🚀✨💡📚🎯]+\s*$", "", m.group(1)).strip()
            if len(note) < 25 or _BOILERPLATE_NOTE_RE.match(note):
                note = None
            break

    result: dict[str, dict] = {}
    if _EMOJI_HEAD_RE.search(text.replace("\r", "")):
        # ── Format C
        cur_title: str | None = None
        for raw in text.split("\n"):
            ln = raw.strip()
            m = _EMOJI_HEAD_RE.match(ln)
            if m:
                cur_title = m.group(2).strip()
                continue
            if not cur_title or not ln:
                continue
            if ln.startswith("🔗") or ln.startswith("http"):
                cur_title = None
                continue
            body = re.sub(r"^(?:오피니언|요약|시사점)\s*[:：]\s*", "", ln)
            if body:
                key = normalize_title(cur_title)
                ent = result.setdefault(key, {"summary": "", "implication": ""})
                ent["summary"] = (ent["summary"] + " " + body).strip()
        return result, note

    # ── Format A / B
    blocks = re.split(r"(?m)^(?=\d{1,2}\.\s+)", text)
    for blk in blocks:
        m = re.match(r"^(\d{1,2})\.\s+(.+?)(?:\n|$)", blk)
        if not m:
            continue
        title = m.group(2).strip()
        rest = blk[m.end():]
        summary_lines: list[str] = []
        impl_lines: list[str] = []
        for line in rest.split("\n"):
            ln = line.strip()
            if not ln:
                continue
            if _FOOTER_RE.match(ln) or "한 줄 요약" in ln or "한줄요약" in ln:
                break
            if ln.startswith("http://") or ln.startswith("https://"):
                continue
            if re.match(r"^-?\s*\[.+?\]\(.+?\)\s*$", ln):
                continue
            if ln.startswith("→") or ln.startswith("->"):
                impl_lines.append(ln.lstrip("→->").strip())
                continue
            if ln.startswith("- "):
                ln = ln[2:].strip()
            elif ln.startswith("-"):
                ln = ln[1:].strip()
            if ln:
                summary_lines.append(ln)
        if summary_lines or impl_lines:
            result[normalize_title(title)] = {
                "summary": " ".join(summary_lines),
                "implication": " ".join(impl_lines),
            }
    return result, note


def parse_plain_txt(text: str) -> dict[str, dict]:
    """수집기 평문 .txt (`N. 제목` / `   출처:` / `   날짜:` / `   링크:` / `   요약: …`) → {norm_title: {...}}.

    요약은 RSS 본문 앞부분이라 AI 요약은 아니지만, 뉴스레터에 요약이 빠진 날(2026-03~04)에는
    제목만 남는 것보다 낫다. '요약:' 줄이 없는 항목은 건너뛴다.
    """
    if not text:
        return {}
    result: dict[str, dict] = {}
    for blk in re.split(r"(?m)^(?=\d{1,2}\.\s+)", text):
        m = re.match(r"^(\d{1,2})\.\s+(.+?)(?:\n|$)", blk)
        if not m:
            continue
        title = m.group(2).strip()
        sm = re.search(r"(?m)^\s*요약\s*[:：]\s*(.+?)\s*$", blk[m.end():])
        if not sm:
            continue
        body = re.sub(r"\s*\.{3}$|\s*…$", "", sm.group(1)).strip()
        if len(body) >= 20:
            result[normalize_title(title)] = {"summary": body, "implication": ""}
    return result


def fetch_ai_summaries(key: str, cfg: dict, target_date: str) -> tuple[dict[str, dict], str | None]:
    pattern = cfg.get("ai_summary_file")
    if not pattern:
        return {}, None
    yyyymmdd = target_date.replace("-", "")
    raw = fetch_file(cfg["repo"], f"{cfg['data_dir']}/{target_date}/{pattern.replace('{YYYYMMDD}', yyyymmdd)}")
    summaries, note = parse_ai_summary_txt(raw) if raw is not None else ({}, None)
    if summaries:
        print(f"[OK] {key}: AI 요약 {len(summaries)}건 파싱", file=sys.stderr)
    # 뉴스레터에 요약이 거의 없으면 평문 .txt의 RSS 요약으로 보강 (교육 뉴스만 설정됨)
    plain_pattern = cfg.get("plain_summary_file")
    if plain_pattern and len(summaries) < 3:
        plain_raw = fetch_file(cfg["repo"], f"{cfg['data_dir']}/{target_date}/{plain_pattern.replace('{YYYYMMDD}', yyyymmdd)}")
        plain = parse_plain_txt(plain_raw) if plain_raw else {}
        added = 0
        for k, v in plain.items():
            if k not in summaries:
                summaries[k] = v
                added += 1
        if added:
            print(f"[OK] {key}: 평문 요약 {added}건 보강", file=sys.stderr)
    return summaries, note


def match_summaries(items: list[dict], cfg: dict, summaries: dict[str, dict]) -> int:
    """제목 정규화 → 정확/접두/유사도(0.72) 3단계 매칭으로 ai_summary·ai_implication을 붙인다."""
    if not summaries:
        return 0
    keys = list(summaries.keys())
    matched = 0
    for item in items:
        t = normalize_title(str(item.get(cfg["title_field"], "")))
        if not t:
            continue
        hit = None
        if t in summaries:
            hit = t
        else:
            t_prefix = t[:20]
            for k in keys:
                if k.startswith(t_prefix) or t.startswith(k[:20]):
                    hit = k
                    break
            if hit is None:
                best_r, best_k = 0.0, None
                for k in keys:
                    r = SequenceMatcher(None, t, k, autojunk=False).ratio()
                    if r > best_r:
                        best_r, best_k = r, k
                if best_r >= 0.72:
                    hit = best_k
        if hit:
            item["ai_summary"] = summaries[hit]["summary"]
            item["ai_implication"] = summaries[hit]["implication"]
            matched += 1
    return matched


# ---------------------------------------------------------------------------
# 소스 페치
# ---------------------------------------------------------------------------


def fetch_today_source(key: str, cfg: dict, date: str) -> tuple[list[dict], str | None]:
    """날짜 JSON을 페치하고 AI 요약 .txt를 머지한다. (items, 일일 한 줄 요약)"""
    filename = cfg["file_template"].replace("{YYYYMMDD}", date.replace("-", ""))
    raw = fetch_file(cfg["repo"], f"{cfg['data_dir']}/{date}/{filename}")
    if raw is None:
        print(f"[WARN] {key}: {date} 파일 없음", file=sys.stderr)
        return [], None
    items = parse_items(raw)
    print(f"[OK] {key}: {len(items)}건 로드", file=sys.stderr)
    summaries, note = fetch_ai_summaries(key, cfg, date)
    if summaries:
        matched = match_summaries(items, cfg, summaries)
        print(f"[OK] {key}: AI 요약 매칭 {matched}/{len(items)}건", file=sys.stderr)
    return items, note


def fetch_source_with_fallback(
    key: str, cfg: dict, today: str, max_fallback: int = 3
) -> tuple[list[dict], str | None, str | None]:
    """오늘 데이터가 없으면 최대 max_fallback일 이전까지 재시도. (items, fallback_date, note)"""
    items, note = fetch_today_source(key, cfg, today)
    if items:
        return items, None, note
    today_dt = datetime.strptime(today, "%Y-%m-%d").date()
    for d in range(1, max_fallback + 1):
        prev = (today_dt - timedelta(days=d)).isoformat()
        items, note = fetch_today_source(key, cfg, prev)
        if items:
            print(f"[FALLBACK] {key}: {today} 데이터 없음 → {prev} 폴백", file=sys.stderr)
            return items, prev, note
    return [], None, None


# ---------------------------------------------------------------------------
# 레코드 빌드 (정규화 + 분류)
# ---------------------------------------------------------------------------

_HANGUL_RE = re.compile(r"[가-힣]")
_ATTRIB_RE = re.compile(r"^\s*\[[^\]]{2,30}\]\s*")


def item_description_text(item: dict, cfg: dict) -> str:
    ai_sum = str(item.get("ai_summary", "")).strip()
    json_sum = str(item.get(cfg.get("summary_field", "summary"), "")).strip()
    text = strip_html(ai_sum if ai_sum else json_sum)
    return _ATTRIB_RE.sub("", text)


def filter_described(items: list[dict], cfg: dict, source_key: str) -> list[dict]:
    """ai-tech만: Gemini 요약이 1건 이상 매칭됐을 때 설명 20자+ 필터. 나머지는 전체 표시."""
    if source_key in ("ai-paper", "edu-news"):
        return items
    if not any(item.get("ai_summary") for item in items):
        return items
    described = [it for it in items if len(item_description_text(it, cfg)) >= 20]
    return described if described else items


def build_item(raw: dict, cfg: dict, source_key: str, section: str, n: int) -> dict:
    """원본 아이템 → 레코드 아이템 (렌더링·분석에 필요한 것만, 분류 포함)."""
    source = str(raw.get(cfg.get("source_field", ""), "")).strip()
    title = clean_title(str(raw.get(cfg["title_field"], "제목 없음")), source) or "제목 없음"
    url = str(raw.get(cfg["url_field"], "#")).strip() or "#"
    keyword = str(raw.get(cfg.get("keyword_field", "keyword"), "")).strip()
    if keyword in ("press_rss", "None") or len(keyword) > 15:
        keyword = ""

    ai_summary = str(raw.get("ai_summary", "")).strip()
    used_ai = bool(ai_summary)
    summary = item_description_text(raw, cfg)
    if not used_ai and len(summary) > 250:
        summary = summary[:250].rsplit(" ", 1)[0] + "…"
    implication = strip_html(str(raw.get("ai_implication", "")).strip())
    # 구포맷·수동 병합으로 요약 안에 '→'가 남아 있으면 시사점으로 분리
    if not implication and "→" in summary:
        head, _, tail = summary.partition("→")
        if len(tail.strip()) >= 10:
            summary, implication = head.strip(), tail.strip()

    full_text = f"{title} {summary} {implication}"
    item = {
        "n": n,
        "title": title,
        "url": url,
        "source": source,
        "published": iso_date(str(raw.get(cfg.get("date_field", "date"), "")).strip()),
        "keyword": keyword,
        "topic": classify(section, title, f"{summary} {implication}"),
        "kind": detect_kind(title),
        "entities": extract_entities(full_text),
        "summary": summary,
        "implication": implication,
        "ai": len(summary) >= 20 and bool(_HANGUL_RE.search(summary)),
    }
    if section == "paper":
        item["authors"] = format_authors(str(raw.get(cfg.get("authors_field", "authors"), "")).strip())
        pdf = str(raw.get(cfg.get("pdf_field", "pdf_link"), "")).strip()
        item["pdf"] = pdf if pdf not in ("#", "None") else ""
    return item


_TRACK_RE = re.compile(r"(?:utm_[a-z]+|fbclid|gclid|ref)=[^&#]*&?")


def canon_url(url: str) -> str:
    u = (url or "").strip().lower()
    u = re.sub(r"^https?://(www\.)?", "", u)
    u = _TRACK_RE.sub("", u)
    u = re.sub(r"/+(\?|#|$)", r"\1", u)
    return u.rstrip("?&/#")


def mark_duplicates(record: dict, data_dir: str, lookback: int = 3) -> int:
    """전 lookback일 레코드와 URL·정규화 제목이 같은 항목에 dup_of(날짜)를 붙인다. 붙인 수 반환.

    지면에서는 그대로 보이되 '전날 실림' 표시가 붙고, 주체·흐름 집계에서는 빠진다.
    """
    today_dt = datetime.strptime(record["date"], "%Y-%m-%d").date()
    seen: dict[str, str] = {}
    for d in range(lookback, 0, -1):
        prev_date = (today_dt - timedelta(days=d)).isoformat()
        prev = load_day(data_dir, prev_date)
        if not prev:
            continue
        for sec in SECTIONS:
            for it in prev["sections"].get(sec, []):
                seen.setdefault("u:" + canon_url(it.get("url", "")), prev_date)
                seen.setdefault("t:" + normalize_title(it.get("title", "")), prev_date)
    marked = 0
    for sec in SECTIONS:
        for it in record["sections"].get(sec, []):
            it.pop("dup_of", None)
            hit = seen.get("u:" + canon_url(it.get("url", ""))) if it.get("url", "#") != "#" else None
            if not hit:
                t = normalize_title(it.get("title", ""))
                hit = seen.get("t:" + t) if len(t) >= 12 else None
            if hit:
                it["dup_of"] = hit
                marked += 1
    return marked


def build_day_record(date: str, use_fallback: bool) -> dict:
    """세 소스를 페치해 하루 레코드를 만든다. 아이템 0개여도 레코드는 반환 (호출자가 판단)."""
    record = {
        "date": date,
        "generated_at": datetime.now(tz=KST).strftime("%Y-%m-%dT%H:%M:%S+09:00"),
        "sections": {},
        "fallback": {},
        "notes": {},
    }
    for key, cfg in SOURCES.items():
        sec = cfg["section"]
        try:
            if use_fallback:
                items, fb, note = fetch_source_with_fallback(key, cfg, date)
            else:
                items, note = fetch_today_source(key, cfg, date)
                fb = None
            before = len(items)
            items = filter_described(items, cfg, key)
            if len(items) < before:
                print(f"[INFO] {key}: 설명 없는 기사 {before - len(items)}건 제외", file=sys.stderr)
            record["sections"][sec] = [build_item(it, cfg, key, sec, i + 1) for i, it in enumerate(items)]
            if fb:
                record["fallback"][sec] = fb
            if note:
                record["notes"][sec] = note
            covered = sum(1 for it in record["sections"][sec] if it["ai"])
            if covered < len(items):
                print(f"[WARN] {key}: 한국어 AI 요약 {covered}/{len(items)}건", file=sys.stderr)
        except Exception as exc:
            print(f"[ERROR] {key} {date}: {exc}", file=sys.stderr)
            record["sections"][sec] = []
    return record


# ---------------------------------------------------------------------------
# HTML 렌더링
# ---------------------------------------------------------------------------


def render_item(item: dict, section: str) -> str:
    source = escape_html(item.get("source", ""))
    date_fmt = format_date(item.get("published", ""))
    topic = item.get("topic", "")
    meta: list[str] = []
    if source:
        meta.append(f'<span class="entry-src">{source}</span>')
    if source and date_fmt:
        meta.append('<span class="entry-sep" aria-hidden="true">·</span>')
    if date_fmt:
        meta.append(f'<span class="entry-dt">{date_fmt}</span>')
    if topic:
        meta.append(
            f'<button type="button" class="entry-topic" data-topic-filter="{section}:{topic}" '
            f'title="이 주제만 보기">{escape_html(topic_label(section, topic))}</button>'
        )
    if item.get("keyword"):
        meta.append(f'<span class="entry-kw">{escape_html(item["keyword"])}</span>')
    if item.get("kind"):
        meta.append(f'<span class="entry-kind">{escape_html({"opinion": "칼럼", "interview": "인터뷰", "feature": "기획"}.get(item["kind"], item["kind"]))}</span>')
    if item.get("dup_of"):
        dd = item["dup_of"]
        meta.append(f'<span class="entry-dup" title="{dd} 지면에 먼저 실림">{int(dd[5:7])}/{int(dd[8:10])} 실림</span>')
    if item.get("summary_src") == "ai-backfill":
        meta.append('<span class="entry-kind entry-kind-ai" title="제목 기반으로 나중에 생성한 요약">요약 보강</span>')
    meta_html = f'      <div class="entry-meta">{"".join(meta)}</div>\n' if meta else ""

    by_html = ""
    if section == "paper" and item.get("authors"):
        by_html = f'      <p class="entry-by">{escape_html(item["authors"])}</p>\n'
    desc_html = f'      <p class="entry-desc">{escape_html(item["summary"])}</p>\n' if item.get("summary") else ""
    impl_html = (
        f'      <p class="entry-impl"><span class="entry-impl-k" aria-label="시사점">→</span>{escape_html(item["implication"])}</p>\n'
        if item.get("implication") else ""
    )
    actions_html = ""
    if section == "paper" and item.get("pdf"):
        actions_html = (
            '      <div class="entry-actions">\n'
            f'        <a class="entry-pdf" href="{escape_html(item["pdf"])}" target="_blank" rel="noopener noreferrer">PDF &darr;</a>\n'
            "      </div>\n"
        )
    ents = "|".join(item.get("entities", []))
    title_main = item.get("title_ko") or item["title"]
    orig_html = (
        f'        <p class="entry-title-orig">{escape_html(item["title"])}</p>\n'
        if item.get("title_ko") and item["title_ko"] != item["title"] else ""
    )
    dup_cls = " entry--dup" if item.get("dup_of") else ""
    return (
        f'    <li class="entry{dup_cls}" id="{section}-{item["n"]}" data-topic="{escape_html(topic)}" data-ents="{escape_html(ents)}">\n'
        f'      <span class="entry-num" aria-hidden="true">{item["n"]:02d}</span>\n'
        f'      <div class="entry-body">\n'
        f"{meta_html}"
        f'        <h3 class="entry-title"><a href="{escape_html(item["url"])}" target="_blank" rel="noopener noreferrer">{escape_html(title_main)}</a></h3>\n'
        f"{orig_html}"
        f"{by_html}{desc_html}{impl_html}{actions_html}"
        f"      </div>\n"
        f"    </li>"
    )


def render_section_body(items: list[dict], section: str) -> str:
    if not items:
        label = SOURCES[SECTION_SOURCE[section]]["label"]
        return f'<p class="col-empty">이 날짜의 {label} 데이터가 없습니다.</p>'
    return '<ol class="col-list">\n' + "\n".join(render_item(it, section) for it in items) + "\n  </ol>"


def date_kr(date: str, weekday: bool = True) -> str:
    dt = datetime.strptime(date, "%Y-%m-%d")
    s = f"{dt.year}년 {dt.month}월 {dt.day}일"
    if weekday:
        s += " " + ["월", "화", "수", "목", "금", "토", "일"][dt.weekday()] + "요일"
    return s


def build_date_nav(latest: str, dates: list[str], root: str) -> str:
    """정적 날짜 pill (최근 NAV_DAYS개 + 전체 아카이브 링크). JS가 dates.json으로 다시 그린다."""
    pills = []
    for d in sorted(dates, reverse=True)[:NAV_DAYS]:
        dt = datetime.strptime(d, "%Y-%m-%d")
        if d == latest:
            pills.append(
                f'<a class="date-pill today active" href="{root}index.html" aria-current="page">오늘 {dt.month}/{dt.day:02d}</a>'
            )
        else:
            pills.append(f'<a class="date-pill" href="{root}archive/{d}.html">{dt.month}/{dt.day:02d}</a>')
    pills.append(f'<a class="date-pill date-pill-all" href="{root}archive/">전체 아카이브 ›</a>')
    return "\n".join(pills)


def render_page(
    record: dict,
    template: str,
    board_html: str,
    date_nav: str,
    root: str,
    canonical: str,
    last_updated_iso: str,
    last_updated_kr: str,
    issue_no: int | None = None,
    og_image: str | None = None,
) -> str:
    secs = record["sections"]
    fallback = record.get("fallback") or {}
    total = record_total(record)
    covered_all = record_ai_count(record)
    covered_fresh = record_ai_count(record, fresh_only=True)
    coverage_pct = round(covered_all * 100 / total) if total else 0

    notice_html = ""
    if total and coverage_pct < AI_COVERAGE_MIN_PCT:
        notice_html = (
            '  <div class="brief-notice" role="status">\n'
            '    <span class="brief-notice-icon" aria-hidden="true">⚠</span>\n'
            f"    <span>이 날짜는 AI 요약이 일부만 생성되어(요약 {covered_all}/{total}건) 나머지 항목은"
            " 제목·링크만 표시됩니다. 원문 링크는 정상 동작합니다.</span>\n"
            "  </div>\n"
        )

    def count_label(sec: str) -> str:
        n = len(secs.get(sec, []))
        if sec in fallback:
            fb = datetime.strptime(fallback[sec], "%Y-%m-%d")
            return f"{n}건 ({fb.month}/{fb.day})"
        return f"{n}건"

    out = (
        template
        .replace("{{ROOT}}", root)
        .replace("{{PAGE_DATE}}", record["date"])
        .replace("{{CURRENT_DATE}}", date_kr(record["date"]))
        .replace("{{EDU_NEWS_CARDS}}", render_section_body(secs.get("edu", []), "edu"))
        .replace("{{AI_PAPER_CARDS}}", render_section_body(secs.get("paper", []), "paper"))
        .replace("{{AI_TECH_CARDS}}", render_section_body(secs.get("tech", []), "tech"))
        .replace("{{EDU_NEWS_COUNT}}", count_label("edu"))
        .replace("{{AI_PAPER_COUNT}}", count_label("paper"))
        .replace("{{AI_TECH_COUNT}}", count_label("tech"))
        .replace("{{DATE_NAV}}", date_nav)
        .replace("{{BOARD}}", board_html)
        .replace("{{BRIEF_NOTICE}}", notice_html)
        .replace("{{LAST_UPDATED_ISO}}", last_updated_iso)
        .replace("{{LAST_UPDATED_KR}}", last_updated_kr)
        .replace("{{PAGE_CANONICAL}}", canonical)
        .replace("{{ISSUE_NO}}", str(issue_no) if issue_no else "·")
        .replace("{{OG_IMAGE}}", og_image or f"{BASE_URL}/assets/og-image.jpg")
        .replace("{{AI_COVERAGE_META}}", f'<meta name="ai-summary-coverage" content="{covered_fresh}/{total}">')
    )
    return out


def issue_number(date: str, index_days: list[dict]) -> int:
    """발행 호수 — 첫 수집일(2025-11-12)을 1호로 센다. 레코드가 없는 날은 그 앞까지의 수 + 1."""
    dates = [e["d"] for e in index_days]
    if date in dates:
        return dates.index(date) + 1
    return sum(1 for d in dates if d < date) + 1


def og_image_url(date: str, docs_dir: str) -> str | None:
    return f"{BASE_URL}/og/{date}.jpg" if os.path.isfile(os.path.join(docs_dir, "og", f"{date}.jpg")) else None


def write_archive_page(record: dict, template: str, index_days: list[dict], archive_dir: str) -> str:
    """레코드 → docs/archive/{date}.html. 보드의 7일 흐름은 그 날짜 기준 과거만 본다."""
    board = render_board(compute_board(record, index_days), root="../")
    docs_dir = os.path.dirname(archive_dir)
    gen = record.get("generated_at", "")
    gen_kr = ""
    if gen:
        try:
            g = datetime.fromisoformat(gen)
            gen_kr = f"{g.year}년 {g.month}월 {g.day}일 {g.strftime('%H:%M')} KST"
        except ValueError:
            gen_kr = gen
    html_out = render_page(
        record, template, board, "", "../",
        f"{BASE_URL}/archive/{record['date']}.html", gen, gen_kr,
        issue_no=issue_number(record["date"], index_days),
        og_image=og_image_url(record["date"], docs_dir),
    )
    path = os.path.join(archive_dir, f"{record['date']}.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(html_out)
    return path


def render_og_images(dates: list[str] | None = None, missing: bool = False) -> bool:
    """scripts/render_og.py를 서브프로세스로 호출한다 (Playwright 없으면 조용히 False)."""
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "render_og.py")
    cmd = [sys.executable, script] + (["--missing"] if missing else ["--date", *(dates or [])])
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f"[OG] 실행 실패: {exc}", file=sys.stderr)
        return False
    for line in (res.stderr or "").strip().splitlines()[-3:]:
        print(line, file=sys.stderr)
    return res.returncode == 0


def update_dates_json(docs_dir: str, dates: list[str], latest: str) -> None:
    json_path = os.path.join(docs_dir, "assets", "dates.json")
    os.makedirs(os.path.dirname(json_path), exist_ok=True)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({"available_dates": sorted(dates), "latest": latest}, f, ensure_ascii=False, indent=2)
    print(f"[OK] dates.json: {len(dates)}개 날짜, latest={latest}", file=sys.stderr)


# ---------------------------------------------------------------------------
# 백필
# ---------------------------------------------------------------------------


def backfill_dates(dates: list[str], data_dir: str, label: str) -> int:
    """data/에 없는 날짜를 소스에서 페치해 저장 (폴백 없음). 저장 건수 반환."""
    created = 0
    for d in dates:
        if load_day(data_dir, d):
            continue
        rec = build_day_record(d, use_fallback=False)
        total = record_total(rec)
        if total == 0:
            print(f"[SKIP] {d}: 데이터 없음", file=sys.stderr)
            continue
        mark_duplicates(rec, data_dir)
        save_day(data_dir, rec)
        created += 1
        print(f"[{label}] {d}: {total}건 저장", file=sys.stderr)
    return created


def all_source_dates() -> list[str]:
    dates: set[str] = set()
    for key, cfg in SOURCES.items():
        ds = list_source_dates(cfg["repo"], cfg["data_dir"])
        print(f"[OK] {key}: 소스에 {len(ds)}일치 존재", file=sys.stderr)
        dates.update(ds)
    return sorted(dates)


# ---------------------------------------------------------------------------
# 메인
# ---------------------------------------------------------------------------


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--date", help="생성할 날짜 (기본: 오늘 KST). 지정 시 폴백 없이 그 날짜만 재생성")
    ap.add_argument("--backfill-all", action="store_true", help="소스 레포의 전 기간 누락 레코드를 복구")
    ap.add_argument("--rebuild-archives", action="store_true", help="data/ 전체를 현재 템플릿으로 다시 렌더")
    ap.add_argument("--no-fetch", action="store_true", help="오늘 페치 생략 (기존 레코드로 렌더만)")
    ap.add_argument("--no-synthesis", action="store_true", help="Gemini 종합 생략")
    ap.add_argument("--task", choices=["mark-dups", "reclassify", "enrich", "summaries", "weekly-backfill", "og-all", "rebuild"],
                    help="유지보수 작업 (오늘 생성 대신 실행). enrich/summaries는 --from/--to 날짜 범위")
    ap.add_argument("--from", dest="date_from", help="유지보수 범위 시작 (YYYY-MM-DD)")
    ap.add_argument("--to", dest="date_to", help="유지보수 범위 끝 (YYYY-MM-DD)")
    args = ap.parse_args()

    now_kst = datetime.now(tz=KST)
    today = now_kst.date().isoformat()
    target = args.date or today

    script_dir = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.dirname(script_dir)
    docs_dir = os.path.join(repo_root, "docs")
    archive_dir = os.path.join(docs_dir, "archive")
    data_dir = os.path.join(docs_dir, "data")
    template_path = os.path.join(docs_dir, "_template.html")
    os.makedirs(archive_dir, exist_ok=True)
    os.makedirs(data_dir, exist_ok=True)

    print(f"[START] {target} 생성 시작 (KST {now_kst.strftime('%H:%M')})", file=sys.stderr)
    if not os.path.isfile(template_path):
        print(f"[ERROR] 템플릿 없음: {template_path}", file=sys.stderr)
        sys.exit(1)
    with open(template_path, encoding="utf-8") as f:
        template = f.read()

    if args.task:
        run_task(args, today, docs_dir, data_dir, archive_dir, template)
        return

    # 1. 전 기간 복구 (옵션) — 소스 디렉터리 목록 기준
    if args.backfill_all:
        dates = [d for d in all_source_dates() if d < today]
        n = backfill_dates(dates, data_dir, "BACKFILL")
        print(f"[OK] 전 기간 백필: {n}개 신규", file=sys.stderr)

    # 2. 최근 누락 보강 — 소스 커밋이 늦게 떨어진 날을 다음 날 실행이 메운다
    if not args.date and not args.no_fetch:
        recent = [(now_kst.date() - timedelta(days=i)).isoformat() for i in range(RECENT_BACKFILL_DAYS, 0, -1)]
        backfill_dates(recent, data_dir, "RECENT")

    # 3. 대상 날짜 레코드
    prev = load_day(data_dir, target)
    if args.no_fetch and prev:
        record = prev
    else:
        record = build_day_record(target, use_fallback=(not args.date))
        total = record_total(record)
        if total == 0:
            if prev:
                print(f"[KEEP] {target}: 새 데이터 없음 — 기존 레코드 유지", file=sys.stderr)
                record = prev
            else:
                print(f"[ERROR] {target}: 세 소스 모두 데이터 없음 — 페이지 생성 생략", file=sys.stderr)
                sys.exit(0)
        elif prev:
            # 요약 커버리지가 낮으면 이후 cron이 재시도하므로, 그 재시도가 더 좋은 기존
            # 결과를 덮어쓰지 않게 막는다 (수집기가 하루 중 퇴보할 수 있음).
            new_key = (record_ai_count(record, fresh_only=True), total)
            old_key = (record_ai_count(prev, fresh_only=True), record_total(prev))
            if old_key > new_key:
                print(f"[KEEP] 기존 레코드가 더 완전함 (요약 {old_key[0]}/{old_key[1]} > {new_key[0]}/{new_key[1]})", file=sys.stderr)
                record = prev
            elif prev.get("synthesis"):
                record["synthesis"] = prev["synthesis"]  # 해시가 같으면 재사용, 다르면 아래서 재생성

    # 3.5 전날 지면과 겹치는 항목 표시 (집계에서 제외)
    dups = mark_duplicates(record, data_dir)
    if dups:
        print(f"[DUP] {target}: 전날 지면과 겹치는 {dups}건 표시", file=sys.stderr)

    # 4. Gemini 종합 + 항목 보강 (키가 있을 때만, 오늘만)
    if not args.no_synthesis and target == today:
        syn = synthesize(record)
        if syn:
            record["synthesis"] = syn
        enrich_record(record)
    save_day(data_dir, record)
    total = record_total(record)
    cov = record_ai_count(record, fresh_only=True)
    print(f"[OK] {target}: 총 {total}건 / 한국어 요약 {cov}건 ({round(cov * 100 / total) if total else 0}%)", file=sys.stderr)

    # 5. 집계 + 파생 산출물
    index = build_index(data_dir)
    build_search(data_dir)
    index_days = index["days"]
    all_dates = [e["d"] for e in index_days]
    print(f"[OK] index.json: {len(index_days)}일 / {index['total_items']}건", file=sys.stderr)
    n_ent = build_entity_index(data_dir)
    print(f"[OK] 주체 색인: {n_ent}개", file=sys.stderr)
    render_og_images([target])

    # 6. 대상 날짜 페이지
    write_archive_page(record, template, index_days, archive_dir)
    print(f"[OK] 아카이브 저장: archive/{target}.html", file=sys.stderr)
    latest = all_dates[-1] if all_dates else target
    if target == latest:
        last_iso = now_kst.strftime("%Y-%m-%dT%H:%M:%S+09:00")
        last_kr = f"{now_kst.year}년 {now_kst.month}월 {now_kst.day}일 {now_kst.strftime('%H:%M')} KST"
        board = render_board(compute_board(record, index_days))
        nav = build_date_nav(latest, all_dates, "")
        html_out = render_page(record, template, board, nav, "", BASE_URL + "/", last_iso, last_kr,
                               issue_no=issue_number(target, index_days), og_image=og_image_url(target, docs_dir))
        with open(os.path.join(docs_dir, "index.html"), "w", encoding="utf-8") as f:
            f.write(html_out)
        print("[OK] index.html 갱신", file=sys.stderr)

    # 7. 아카이브 전체 재렌더 (옵션 — 템플릿 바뀐 날)
    if args.rebuild_archives:
        n = 0
        for d in all_dates:
            if d == target:
                continue
            rec = load_day(data_dir, d)
            if rec:
                write_archive_page(rec, template, index_days, archive_dir)
                n += 1
        print(f"[OK] 아카이브 재렌더: {n}개", file=sys.stderr)

    # 8. dates.json — 레코드가 있는 모든 날짜 (삭제 없음)
    update_dates_json(docs_dir, all_dates, latest)

    # 9. 피드 · 주간 다이제스트 (가장 최근에 끝난 주)
    build_feeds(data_dir, docs_dir, index_days, BASE_URL)
    build_weekly(data_dir, docs_dir, all_dates, today, BASE_URL, backfill=False, synthesize=not args.no_synthesis)
    print(f"[DONE] {target} 완료", file=sys.stderr)


def run_task(args, today: str, docs_dir: str, data_dir: str, archive_dir: str, template: str) -> None:
    """유지보수 작업 — 오늘 생성을 건너뛰고 데이터 계층만 손본 뒤 파생물을 다시 만든다."""
    dates = list_dates(data_dir)
    lo, hi = args.date_from or (dates[0] if dates else today), args.date_to or today
    rng = [d for d in dates if lo <= d <= hi]
    task = args.task
    print(f"[TASK] {task} ({lo} ~ {hi}, {len(rng)}일)", file=sys.stderr)

    if task == "mark-dups":
        total = 0
        for d in rng:
            rec = load_day(data_dir, d)
            if rec:
                n = mark_duplicates(rec, data_dir)
                total += n
                save_day(data_dir, rec)
        print(f"[DUP] 총 {total}건 표시", file=sys.stderr)
    elif task == "reclassify":
        # 규칙(taxonomy.py)을 고친 뒤 재페치 없이 주제·형식·주체만 다시 계산. Gemini가 고른 주제(topic_src=ai)는 유지.
        changed = 0
        for d in rng:
            rec = load_day(data_dir, d)
            if not rec:
                continue
            for sec in SECTIONS:
                for it in rec["sections"].get(sec, []):
                    text = f"{it.get('summary', '')} {it.get('implication', '')}"
                    new_topic = classify(sec, it["title"], text)
                    if it.get("topic_src") == "ai":
                        it["topic_rule"] = new_topic
                    else:
                        it["topic"] = new_topic
                    it["kind"] = detect_kind(it["title"])
                    it["entities"] = extract_entities(f"{it['title']} {text}")
            save_day(data_dir, rec)
            changed += 1
        print(f"[RECLASS] {changed}일 재분류", file=sys.stderr)
    elif task == "enrich":
        n = enrich_range(data_dir, rng, tasks=("topics", "title_ko"))
        print(f"[ENR] {n}일 보강", file=sys.stderr)
    elif task == "summaries":
        n = enrich_range(data_dir, rng, tasks=("summaries",))
        print(f"[ENR] 요약 보강 {n}일", file=sys.stderr)

    index = build_index(data_dir)
    build_search(data_dir)
    index_days = index["days"]
    all_dates = [e["d"] for e in index_days]
    build_entity_index(data_dir)

    if task == "og-all":
        render_og_images(missing=False, dates=all_dates)
    elif task in ("mark-dups", "reclassify", "enrich", "summaries"):
        render_og_images(rng)
    if task == "weekly-backfill":
        build_weekly(data_dir, docs_dir, all_dates, today, BASE_URL, backfill=True, synthesize=not args.no_synthesis)
    else:
        build_weekly(data_dir, docs_dir, all_dates, today, BASE_URL, backfill=False, synthesize=False)

    # 영향받은 페이지 재렌더 (rebuild·og-all은 전부)
    targets = all_dates if task in ("rebuild", "og-all") else rng
    n = 0
    for d in targets:
        rec = load_day(data_dir, d)
        if rec:
            write_archive_page(rec, template, index_days, archive_dir)
            n += 1
    latest = all_dates[-1] if all_dates else today
    rec = load_day(data_dir, latest)
    if rec:
        now_kst = datetime.now(tz=KST)
        last_iso = now_kst.strftime("%Y-%m-%dT%H:%M:%S+09:00")
        last_kr = f"{now_kst.year}년 {now_kst.month}월 {now_kst.day}일 {now_kst.strftime('%H:%M')} KST"
        board = render_board(compute_board(rec, index_days))
        nav = build_date_nav(latest, all_dates, "")
        with open(os.path.join(docs_dir, "index.html"), "w", encoding="utf-8") as f:
            f.write(render_page(rec, template, board, nav, "", BASE_URL + "/", last_iso, last_kr,
                                issue_no=issue_number(latest, index_days), og_image=og_image_url(latest, docs_dir)))
    update_dates_json(docs_dir, all_dates, latest)
    build_feeds(data_dir, docs_dir, index_days, BASE_URL)
    print(f"[DONE] {task}: 아카이브 {n}개 재렌더", file=sys.stderr)


if __name__ == "__main__":
    main()
