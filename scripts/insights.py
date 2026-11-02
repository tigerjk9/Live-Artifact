#!/usr/bin/env python3
"""insights.py — 영구 데이터 계층(docs/data/*.json) + 일일 '오늘의 흐름' 보드.

데이터 계약
  docs/data/YYYY-MM-DD.json  하루치 정규화 레코드 (원본 소스가 지워져도 여기 남는다)
  docs/data/index.json       날짜별 집계 (건수·주제 분포·주체 Top·헤드라인) — 흐름 페이지의 재료
  docs/data/search.json      전 기간 제목 검색 색인 (아카이브 탐색 페이지가 첫 검색 때 지연 로드)

레코드 스키마 (fetch_and_generate.build_day_record 가 만든다)
  {
    "date": "2026-11-01", "generated_at": "...+09:00",
    "sections": {"edu": [item], "paper": [item], "tech": [item]},
    "fallback": {"tech": "2026-10-31"},          # 폴백 사용 섹션만
    "notes": {"edu": "수집기 한 줄 요약", ...},   # 구포맷 뉴스레터에서 거둔 일일 요약 (선택)
    "synthesis": {"headline", "threads", "classroom", "model", "items_hash"}  # Gemini (선택)
  }
  item = {"n", "title", "url", "source", "published", "keyword", "topic", "kind",
          "entities", "summary", "implication", "ai", ("authors", "pdf")}
"""

from __future__ import annotations

import json
import os
import re
from collections import Counter, defaultdict
from urllib.parse import quote
from datetime import datetime, timedelta, timezone

from taxonomy import (
    BRIDGES,
    KIND_LABEL,
    entity_kind,
    topic_ids,
    topic_label,
)

SECTIONS = ("edu", "paper", "tech")
SECTION_SHORT = {"edu": "교육", "paper": "논문", "tech": "기술"}
SECTION_LABEL = {"edu": "교육 뉴스", "paper": "연구 논문", "tech": "기술 뉴스"}

INDEX_TOP_ENTITIES = 20
KST = timezone(timedelta(hours=9))


def esc(text: str) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


# ---------------------------------------------------------------------------
# 저장소
# ---------------------------------------------------------------------------


def day_path(data_dir: str, date: str) -> str:
    return os.path.join(data_dir, f"{date}.json")


def load_day(data_dir: str, date: str) -> dict | None:
    p = day_path(data_dir, date)
    if not os.path.isfile(p):
        return None
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def save_day(data_dir: str, record: dict) -> str:
    os.makedirs(data_dir, exist_ok=True)
    p = day_path(data_dir, record["date"])
    with open(p, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=1)
    return p


def list_dates(data_dir: str) -> list[str]:
    if not os.path.isdir(data_dir):
        return []
    out = []
    for fname in os.listdir(data_dir):
        if len(fname) == 15 and fname.endswith(".json"):
            stem = fname[:-5]
            try:
                datetime.strptime(stem, "%Y-%m-%d")
                out.append(stem)
            except ValueError:
                pass
    return sorted(out)


def is_dup(item: dict) -> bool:
    """전날 지면에 이미 실린 항목 (fetch_and_generate.mark_duplicates가 dup_of를 붙인다)."""
    return bool(item.get("dup_of"))


def record_total(record: dict) -> int:
    return sum(len(record["sections"].get(s, [])) for s in SECTIONS)


def record_ai_count(record: dict, fresh_only: bool = False) -> int:
    n = 0
    fb = record.get("fallback") or {}
    for s in SECTIONS:
        if fresh_only and s in fb:
            continue
        n += sum(1 for it in record["sections"].get(s, []) if it.get("ai"))
    return n


# ---------------------------------------------------------------------------
# 집계 (index.json / search.json)
# ---------------------------------------------------------------------------


def index_entry(record: dict) -> dict:
    topics: dict[str, dict[str, int]] = {}
    ents: Counter = Counter()
    kinds: Counter = Counter()
    srcs: Counter = Counter()
    counts: dict[str, int] = {}
    dups = 0
    for s in SECTIONS:
        items = record["sections"].get(s, [])
        counts[s] = len(items)
        fresh = [it for it in items if not is_dup(it)]
        dups += len(items) - len(fresh)
        tc: Counter = Counter(it.get("topic", "other") for it in fresh)
        topics[s] = dict(tc)
        for it in fresh:
            for e in it.get("entities", []):
                ents[e] += 1
            if it.get("kind"):
                kinds[it["kind"]] += 1
            if it.get("source"):
                srcs[f"{s}:{it['source']}"] += 1
    entry = {
        "d": record["date"],
        "n": counts,
        "ai": record_ai_count(record),
        "fb": sorted((record.get("fallback") or {}).keys()),
        "topics": topics,
        "ents": dict(ents.most_common(INDEX_TOP_ENTITIES)),
        "kinds": dict(kinds),
        "srcs": dict(srcs.most_common(12)),
        "dups": dups,
    }
    syn = record.get("synthesis") or {}
    notes = record.get("notes") or {}
    head = syn.get("headline") or notes.get("edu") or notes.get("tech") or ""
    if head:
        entry["head"] = head
        entry["head_src"] = "ai" if syn.get("headline") else "note"
    return entry


def build_index(data_dir: str, write: bool = True) -> dict:
    days = []
    for d in list_dates(data_dir):
        rec = load_day(data_dir, d)
        if rec and record_total(rec):
            days.append(index_entry(rec))
    index = {
        "updated": datetime.now(tz=KST).strftime("%Y-%m-%dT%H:%M:%S+09:00"),
        "first": days[0]["d"] if days else None,
        "latest": days[-1]["d"] if days else None,
        "total_items": sum(sum(e["n"].values()) for e in days),
        "topic_labels": {s: {t: topic_label(s, t) for t in topic_ids(s)} for s in SECTIONS},
        "kind_labels": KIND_LABEL,
        "days": days,
    }
    if write:
        with open(os.path.join(data_dir, "index.json"), "w", encoding="utf-8") as f:
            json.dump(index, f, ensure_ascii=False, separators=(",", ":"))
    return index


def build_search(data_dir: str, write: bool = True) -> list[dict]:
    """월별 검색 색인 docs/data/search/YYYY-MM.json (제목·출처·주제·요약 앞 160자) + index.json."""
    by_month: dict[str, list[dict]] = defaultdict(list)
    rows: list[dict] = []
    for d in list_dates(data_dir):
        rec = load_day(data_dir, d)
        if not rec:
            continue
        for s in SECTIONS:
            for it in rec["sections"].get(s, []):
                row = {
                    "d": d, "s": s, "n": it["n"], "t": it.get("title_ko") or it["title"],
                    "src": it.get("source", ""), "tp": it.get("topic", ""),
                    "sm": (it.get("summary") or "")[:160],
                }
                if it.get("title_ko"):
                    row["t2"] = it["title"]
                rows.append(row)
                by_month[d[:7]].append(row)
    if write:
        sdir = os.path.join(data_dir, "search")
        os.makedirs(sdir, exist_ok=True)
        for m, lst in by_month.items():
            with open(os.path.join(sdir, f"{m}.json"), "w", encoding="utf-8") as f:
                json.dump(lst, f, ensure_ascii=False, separators=(",", ":"))
        with open(os.path.join(sdir, "index.json"), "w", encoding="utf-8") as f:
            json.dump({"months": [{"m": m, "n": len(by_month[m])} for m in sorted(by_month)], "total": len(rows)},
                      f, ensure_ascii=False)
        legacy = os.path.join(data_dir, "search.json")
        if os.path.isfile(legacy):
            os.remove(legacy)
    return rows


def slugify(name: str) -> str:
    return re.sub(r"[^0-9A-Za-z가-힣]+", "_", name).strip("_") or "x"


def build_entity_index(data_dir: str, min_mentions: int = 3) -> int:
    """docs/data/entities.json (목록·월별 추이) + docs/data/entity/{slug}.json (주체별 전체 등장)."""
    from taxonomy import entity_kind

    ents: dict[str, dict] = {}
    for d in list_dates(data_dir):
        rec = load_day(data_dir, d)
        if not rec:
            continue
        for s in SECTIONS:
            for it in rec["sections"].get(s, []):
                if is_dup(it):
                    continue
                names = it.get("entities", [])
                for e in names:
                    ent = ents.setdefault(e, {"items": [], "co": Counter(), "topics": defaultdict(Counter)})
                    ent["items"].append({
                        "d": d, "s": s, "n": it["n"], "t": it.get("title_ko") or it["title"], "tp": it.get("topic", ""),
                    })
                    ent["topics"][s][it.get("topic", "")] += 1
                    for other in names:
                        if other != e:
                            ent["co"][other] += 1
    edir = os.path.join(data_dir, "entity")
    os.makedirs(edir, exist_ok=True)
    listing = []
    written = 0
    for name, ent in ents.items():
        items = ent["items"]
        if len(items) < min_mentions:
            continue
        months: Counter = Counter(it["d"][:7] for it in items)
        by_sec: Counter = Counter(it["s"] for it in items)
        slug = slugify(name)
        listing.append({
            "name": name, "slug": slug, "kind": entity_kind(name), "n": len(items),
            "first": items[0]["d"], "last": items[-1]["d"],
            "sec": dict(by_sec), "months": dict(sorted(months.items())),
        })
        with open(os.path.join(edir, f"{slug}.json"), "w", encoding="utf-8") as f:
            json.dump({
                "name": name, "kind": entity_kind(name), "n": len(items),
                "co": dict(ent["co"].most_common(12)),
                "topics": {s: dict(c) for s, c in ent["topics"].items()},
                "items": list(reversed(items)),
            }, f, ensure_ascii=False, separators=(",", ":"))
        written += 1
    listing.sort(key=lambda x: -x["n"])
    with open(os.path.join(data_dir, "entities.json"), "w", encoding="utf-8") as f:
        json.dump({"min_mentions": min_mentions, "entities": listing,
                   "topic_labels": {s: {t: topic_label(s, t) for t in topic_ids(s)} for s in SECTIONS}},
                  f, ensure_ascii=False, separators=(",", ":"))
    return written


# ---------------------------------------------------------------------------
# 오늘의 흐름 보드 — 계산
# ---------------------------------------------------------------------------


def _window(index_days: list[dict], end: str, days: int) -> list[dict]:
    end_dt = datetime.strptime(end, "%Y-%m-%d").date()
    start_dt = end_dt - timedelta(days=days - 1)
    return [e for e in index_days if start_dt.isoformat() <= e["d"] <= end_dt.isoformat()]


def compute_board(record: dict, index_days: list[dict]) -> dict:
    """하루 레코드 + 과거 집계로 보드에 필요한 숫자를 모두 계산한다 (렌더링과 분리)."""
    date = record["date"]
    secs = record["sections"]
    fallback = record.get("fallback") or {}

    # 1) 주제 분포 (섹션별)
    topics: dict[str, list[dict]] = {}
    for s in SECTIONS:
        c: dict[str, list[int]] = defaultdict(list)
        for it in secs.get(s, []):
            c[it.get("topic", "other")].append(it["n"])
        topics[s] = sorted(
            ({"id": t, "label": topic_label(s, t), "n": len(nums), "items": nums} for t, nums in c.items()),
            key=lambda x: -x["n"],
        )

    # 2) 오늘의 주체
    ent_sec: dict[str, dict[str, list[int]]] = defaultdict(lambda: defaultdict(list))
    dups = 0
    for s in SECTIONS:
        for it in secs.get(s, []):
            if is_dup(it):
                dups += 1
                continue
            for e in it.get("entities", []):
                ent_sec[e][s].append(it["n"])
    entities = sorted(
        (
            {
                "name": e, "kind": entity_kind(e),
                "n": sum(len(v) for v in by.values()),
                "sections": {s: by[s] for s in SECTIONS if s in by},
            }
            for e, by in ent_sec.items()
        ),
        key=lambda x: (-x["n"], -len(x["sections"]), x["name"]),
    )

    # 3) 교차 연결 — 두 섹션 이상에 등장한 주체 + 주제 묶음(bridge)
    links: list[dict] = []
    for ent in entities:
        if len(ent["sections"]) >= 2:
            links.append({"type": "entity", "label": ent["name"], "kind": ent["kind"], "sections": ent["sections"]})
    for label, groups in BRIDGES:
        hit: dict[str, list[int]] = {}
        for s, tids in groups.items():
            nums = [it["n"] for it in secs.get(s, []) if it.get("topic") in tids]
            if nums:
                hit[s] = nums
        if len(hit) >= 2:
            links.append({"type": "bridge", "label": label, "kind": "bridge", "sections": hit})
    links.sort(key=lambda l: (-len(l["sections"]), -sum(len(v) for v in l["sections"].values())))

    # 4) 7일 흐름 — 최근 7일 vs 직전 7일 주체 언급 비교 (오늘 레코드 포함)
    today_entry = index_entry(record)
    hist = [e for e in index_days if e["d"] < date] + [today_entry]
    cur = _window(hist, date, 7)
    prev_end = (datetime.strptime(date, "%Y-%m-%d").date() - timedelta(days=7)).isoformat()
    prev = _window(hist, prev_end, 7)
    cur_c: Counter = Counter()
    prev_c: Counter = Counter()
    for e in cur:
        cur_c.update(e.get("ents", {}))
    for e in prev:
        prev_c.update(e.get("ents", {}))
    deltas = []
    for name in set(cur_c) | set(prev_c):
        a, b = cur_c.get(name, 0), prev_c.get(name, 0)
        deltas.append({"name": name, "kind": entity_kind(name), "cur": a, "prev": b, "delta": a - b})
    rising = sorted((d for d in deltas if d["delta"] >= 2), key=lambda d: (-d["delta"], -d["cur"]))[:5]
    falling = sorted((d for d in deltas if d["delta"] <= -2), key=lambda d: (d["delta"], -d["prev"]))[:3]
    # 주간 상위 주체 + 일별 스파크라인
    week_dates = [(datetime.strptime(date, "%Y-%m-%d").date() - timedelta(days=i)).isoformat() for i in range(6, -1, -1)]
    by_date = {e["d"]: e for e in cur}
    week_top = []
    for name, total in cur_c.most_common(6):
        series = [by_date.get(d, {}).get("ents", {}).get(name, 0) for d in week_dates]
        week_top.append({"name": name, "kind": entity_kind(name), "total": total, "series": series})

    # 5) 기본 수치
    counts = {s: len(secs.get(s, [])) for s in SECTIONS}
    total = sum(counts.values())
    ai = record_ai_count(record)
    kinds = Counter(it.get("kind") for s in SECTIONS for it in secs.get(s, []) if it.get("kind"))

    syn = record.get("synthesis") or {}
    notes = record.get("notes") or {}
    headline = syn.get("headline") or _fallback_headline(total, entities, links)

    return {
        "date": date,
        "counts": counts,
        "total": total,
        "ai": ai,
        "fallback": fallback,
        "kinds": dict(kinds),
        "dups": dups,
        "topics": topics,
        "entities": entities[:10],
        "links": links[:6],
        "rising": rising,
        "falling": falling,
        "week_top": week_top,
        "week_dates": week_dates,
        "week_days_present": len(cur),
        "headline": headline,
        "threads": syn.get("threads") or [],
        "classroom": syn.get("classroom") or "",
        "synth_model": syn.get("model"),
        "notes": notes,
    }


def _fallback_headline(total: int, entities: list[dict], links: list[dict]) -> str:
    if not total:
        return "이 날짜에는 수집된 소식이 없습니다."
    parts = [f"오늘 {total}건"]
    tops = [e for e in entities if e["kind"] in ("org", "edu_org", "model")][:2]
    if tops:
        parts.append("가장 많이 등장한 주체는 " + ", ".join(f"{e['name']}({e['n']}건)" for e in tops))
    cross = [l for l in links if len(l["sections"]) >= 2]
    if cross:
        parts.append(f"섹션을 가로지르는 흐름 {len(cross)}개")
    return " · ".join(parts)


# ---------------------------------------------------------------------------
# 오늘의 흐름 보드 — 렌더링
# ---------------------------------------------------------------------------


def _ref(sec: str, n: int) -> str:
    return (
        f'<a class="ref ref-{sec}" href="#{sec}-{n}" data-ref="{sec}-{n}">'
        f'{SECTION_SHORT[sec]} {n}</a>'
    )


def _refs(sections: dict[str, list[int]]) -> str:
    out = []
    for s in SECTIONS:
        for n in sections.get(s, []):
            out.append(_ref(s, n))
    return "".join(out)


def _sec_dots(sections: dict[str, list[int]]) -> str:
    return "".join(
        f'<i class="dot dot-{s}" title="{SECTION_SHORT[s]} {len(sections[s])}건"></i>'
        for s in SECTIONS if s in sections
    )


def render_board(board: dict, root: str = "") -> str:
    if not board["total"]:
        return ""
    b = board
    h: list[str] = []
    h.append('<section class="board" id="board" aria-labelledby="board-title">')
    h.append('  <div class="board-inner">')

    # 헤더 + 헤드라인
    tag = "AI 종합" if b["threads"] else "자동 집계"
    h.append('    <header class="board-head">')
    h.append('      <div class="board-head-main">')
    h.append(f'        <h2 class="board-title" id="board-title">오늘의 흐름 <span class="board-tag">{tag}</span></h2>')
    h.append(f'        <p class="board-headline">{esc(b["headline"])}</p>')
    h.append('      </div>')
    h.append('      <button class="board-toggle" type="button" aria-expanded="true" aria-controls="board-body">접기</button>')
    h.append('    </header>')
    h.append('    <div class="board-body" id="board-body">')

    # Gemini 종합 스레드 (있을 때만)
    if b["threads"]:
        h.append('      <div class="board-threads">')
        for th in b["threads"]:
            refs = "".join(
                _ref(r.split("-")[0], int(r.split("-")[1]))
                for r in th.get("refs", [])
                if isinstance(r, str) and r.count("-") == 1
                and r.split("-")[0] in SECTIONS and r.split("-")[1].isdigit()
            )
            h.append('        <article class="thread">')
            h.append(f'          <h3 class="thread-title">{esc(th.get("title", ""))}</h3>')
            h.append(f'          <p class="thread-body">{esc(th.get("body", ""))}</p>')
            if refs:
                h.append(f'          <p class="thread-refs">{refs}</p>')
            h.append('        </article>')
        if b["classroom"]:
            h.append(f'        <p class="board-classroom"><span class="board-classroom-k">교실에서</span>{esc(b["classroom"])}</p>')
        h.append('      </div>')
    elif b["notes"]:
        h.append('      <div class="board-notes">')
        for s in SECTIONS:
            if b["notes"].get(s):
                h.append(f'        <p class="board-note"><span class="dot dot-{s}"></span>{esc(b["notes"][s])}</p>')
        h.append('      </div>')

    h.append('      <div class="board-grid">')

    # 주제 분포
    h.append('        <div class="board-cell board-topics">')
    h.append('          <h3 class="cell-title">주제 분포 <span class="cell-hint">클릭하면 해당 주제만 보기</span></h3>')
    for s in SECTIONS:
        rows = b["topics"].get(s, [])
        n = b["counts"][s]
        if not n:
            continue
        h.append(f'          <div class="topic-row" data-cat="{s}">')
        h.append(f'            <span class="topic-cat">{SECTION_SHORT[s]}<b>{n}</b></span>')
        h.append('            <div class="topic-bar" role="list">')
        for i, t in enumerate(rows):
            pct = t["n"] * 100 / n
            h.append(
                f'              <button type="button" class="topic-seg seg-{i % 6}" role="listitem" '
                f'style="flex-basis:{pct:.1f}%" data-topic-filter="{s}:{t["id"]}" '
                f'title="{esc(t["label"])} {t["n"]}건" aria-label="{esc(t["label"])} {t["n"]}건"></button>'
            )
        h.append('            </div>')
        h.append('            <div class="topic-legend">')
        for i, t in enumerate(rows[:4]):
            h.append(
                f'              <button type="button" class="topic-chip seg-{i % 6}" data-topic-filter="{s}:{t["id"]}">'
                f'{esc(t["label"])}<b>{t["n"]}</b></button>'
            )
        if len(rows) > 4:
            rest = sum(t["n"] for t in rows[4:])
            h.append(f'              <span class="topic-chip topic-chip-rest">외 {len(rows) - 4}개 주제 {rest}건</span>')
        h.append('            </div>')
        h.append('          </div>')
    foot = []
    if b["kinds"]:
        foot.append("형식: " + " · ".join(f"{KIND_LABEL.get(k, k)} {v}" for k, v in b["kinds"].items()))
    if b.get("dups"):
        foot.append(f"전날 지면과 겹치는 {b['dups']}건은 주체·흐름 집계에서 제외")
    if foot:
        h.append(f'          <p class="cell-foot">{esc(" · ".join(foot))}</p>')
    h.append('        </div>')

    # 오늘의 주체
    h.append('        <div class="board-cell board-ents">')
    h.append('          <h3 class="cell-title">오늘의 주체 <span class="cell-hint">클릭하면 관련 소식만 보기</span></h3>')
    if b["entities"]:
        h.append('          <ul class="ent-list">')
        for e in b["entities"]:
            h.append(
                f'            <li><button type="button" class="ent-chip kind-{e["kind"]}" data-ent-filter="{esc(e["name"])}">'
                f'<span class="ent-name">{esc(e["name"])}</span><b class="ent-n">{e["n"]}</b>'
                f'<span class="ent-dots">{_sec_dots(e["sections"])}</span></button>'
                f'<a class="ent-link" href="{root}entity.html?e={quote(e["name"])}" title="{esc(e["name"])} 1년 흐름" aria-label="{esc(e["name"])} 주체 페이지">&#8599;</a></li>'
            )
        h.append('          </ul>')
    else:
        h.append('          <p class="cell-empty">사전에 등록된 주체가 오늘은 없습니다.</p>')
    h.append('        </div>')

    # 교차 연결
    h.append('        <div class="board-cell board-links">')
    h.append('          <h3 class="cell-title">교차 연결 <span class="cell-hint">두 섹션 이상에 걸친 흐름</span></h3>')
    if b["links"]:
        h.append('          <ul class="link-list">')
        for l in b["links"]:
            kind_cls = "link-bridge" if l["type"] == "bridge" else f"kind-{l['kind']}"
            h.append(
                f'            <li class="link-item {kind_cls}"><span class="link-label">{esc(l["label"])}</span>'
                f'<span class="link-refs">{_refs(l["sections"])}</span></li>'
            )
        h.append('          </ul>')
    else:
        h.append('          <p class="cell-empty">오늘은 섹션을 가로지르는 공통 주체가 없습니다.</p>')
    h.append('        </div>')

    # 7일 흐름
    h.append('        <div class="board-cell board-trend">')
    present = b["week_days_present"]
    h.append(f'          <h3 class="cell-title">7일 흐름 <span class="cell-hint">최근 {present}일 vs 그 전 7일</span></h3>')
    if b["rising"] or b["falling"]:
        h.append('          <div class="trend-deltas">')
        for d in b["rising"]:
            h.append(
                f'            <button type="button" class="trend-chip up kind-{d["kind"]}" data-ent-filter="{esc(d["name"])}" '
                f'title="최근 7일 {d["cur"]}건 / 그 전 {d["prev"]}건">▲ {esc(d["name"])}<b>+{d["delta"]}</b></button>'
            )
        for d in b["falling"]:
            h.append(
                f'            <span class="trend-chip down kind-{d["kind"]}" '
                f'title="최근 7일 {d["cur"]}건 / 그 전 {d["prev"]}건">▼ {esc(d["name"])}<b>{d["delta"]}</b></span>'
            )
        h.append('          </div>')
    if b["week_top"]:
        h.append('          <ul class="spark-list">')
        mx = max(max(w["series"]) for w in b["week_top"]) or 1
        for w in b["week_top"]:
            bars = "".join(
                f'<i style="height:{max(8, v * 100 // mx) if v else 4}%" title="{d[5:].replace("-", "/")} {v}건"></i>'
                for d, v in zip(b["week_dates"], w["series"])
            )
            h.append(
                f'            <li><span class="spark-name kind-{w["kind"]}">{esc(w["name"])}</span>'
                f'<span class="spark" aria-label="일별 언급">{bars}</span><b class="spark-total">{w["total"]}</b></li>'
            )
        h.append('          </ul>')
    if not (b["rising"] or b["falling"] or b["week_top"]):
        h.append('          <p class="cell-empty">비교할 과거 데이터가 아직 없습니다.</p>')
    h.append('        </div>')

    h.append('      </div>')  # board-grid
    h.append('    </div>')    # board-body
    h.append('  </div>')
    h.append('</section>')
    return "\n".join(h)
