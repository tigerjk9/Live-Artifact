#!/usr/bin/env python3
"""weekly.py — 주간 다이제스트. ISO 주(월~일) 단위로 docs/data/weekly/YYYY-Www.json을 만들고
docs/weekly/YYYY-Www.html · docs/weekly/index.html을 렌더한다.

- 결정적 부분(일수·건수·주제 비중·주체 순위와 전주 대비·날짜별 헤드라인)은 레코드만으로 만든다.
- GEMINI_API_KEY가 있으면 그 주 175건을 한 번 더 종합해 헤드라인·흐름 4개·교실 제안을 붙인다 (캐시).
- 일일 실행은 "가장 최근에 끝난 주"만 채우고, 유지보수 작업 weekly-backfill 이 과거 전체를 만든다.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from collections import Counter
from datetime import date, datetime, timedelta, timezone

import requests

from insights import SECTIONS, SECTION_LABEL, SECTION_SHORT, esc, is_dup, load_day
from synthesis import DEFAULT_MODEL, GEMINI_ENDPOINT, _parse_json_loose
from taxonomy import entity_kind, topic_label

KST = timezone(timedelta(hours=9))


# ---------------------------------------------------------------------------
# 주 계산
# ---------------------------------------------------------------------------


def week_key(d: str) -> str:
    y, w, _ = date.fromisoformat(d).isocalendar()
    return f"{y}-W{w:02d}"


def week_dates(key: str) -> list[str]:
    y, w = key.split("-W")
    monday = date.fromisocalendar(int(y), int(w), 1)
    return [(monday + timedelta(days=i)).isoformat() for i in range(7)]


def week_label(key: str) -> str:
    ds = week_dates(key)
    a, b = date.fromisoformat(ds[0]), date.fromisoformat(ds[-1])
    if a.month == b.month:
        return f"{a.year}년 {a.month}월 {a.day}일 ~ {b.day}일"
    return f"{a.year}년 {a.month}월 {a.day}일 ~ {b.month}월 {b.day}일"


def completed_weeks(dates: list[str], today: str) -> list[str]:
    """레코드가 하나라도 있고, 일요일이 오늘 이전인 주들 (오름차순)."""
    keys = sorted({week_key(d) for d in dates})
    return [k for k in keys if week_dates(k)[-1] < today]


def prev_week(key: str) -> str:
    monday = date.fromisoformat(week_dates(key)[0])
    return week_key((monday - timedelta(days=7)).isoformat())


# ---------------------------------------------------------------------------
# 데이터
# ---------------------------------------------------------------------------


def _collect(data_dir: str, key: str) -> tuple[list[dict], dict[str, dict]]:
    recs: dict[str, dict] = {}
    for d in week_dates(key):
        r = load_day(data_dir, d)
        if r:
            recs[d] = r
    items: list[dict] = []
    for d, r in recs.items():
        for s in SECTIONS:
            for it in r["sections"].get(s, []):
                if is_dup(it):
                    continue
                items.append({**it, "d": d, "s": s})
    return items, recs


def _stats(items: list[dict]) -> dict:
    ents: Counter = Counter()
    topics: dict[str, Counter] = {s: Counter() for s in SECTIONS}
    counts: Counter = Counter()
    for it in items:
        counts[it["s"]] += 1
        topics[it["s"]][it.get("topic", "")] += 1
        for e in it.get("entities", []):
            ents[e] += 1
    return {"counts": dict(counts), "ents": ents, "topics": topics}


def build_week(data_dir: str, key: str, synthesize: bool = True) -> dict | None:
    items, recs = _collect(data_dir, key)
    if not items:
        return None
    cur = _stats(items)
    prev_items, _ = _collect(data_dir, prev_week(key))
    prev = _stats(prev_items)

    top_ents = []
    for name, n in cur["ents"].most_common(12):
        top_ents.append({"name": name, "kind": entity_kind(name), "n": n, "delta": n - prev["ents"].get(name, 0)})
    rising = sorted(
        ({"name": e, "kind": entity_kind(e), "n": n, "delta": n - prev["ents"].get(e, 0)} for e, n in cur["ents"].items()),
        key=lambda x: (-x["delta"], -x["n"]),
    )
    rising = [r for r in rising if r["delta"] >= 3][:6]

    topic_share = {}
    for s in SECTIONS:
        tot = sum(cur["topics"][s].values()) or 1
        ptot = sum(prev["topics"][s].values()) or 0
        topic_share[s] = [
            {
                "id": t, "label": topic_label(s, t), "n": n, "pct": round(n * 100 / tot),
                "delta": (round(n * 100 / tot) - round(prev["topics"][s].get(t, 0) * 100 / ptot)) if ptot else None,
            }
            for t, n in cur["topics"][s].most_common()
        ]

    daily = []
    for d in week_dates(key):
        r = recs.get(d)
        if not r:
            continue
        syn = r.get("synthesis") or {}
        head = syn.get("headline") or (r.get("notes") or {}).get("edu") or ""
        daily.append({"d": d, "n": sum(len(r["sections"].get(s, [])) for s in SECTIONS), "head": head,
                      "src": "ai" if syn.get("headline") else ("note" if head else "")})

    # 대표 기사: 주체 언급이 많은 순 (섹션별 3개)
    picks = {}
    for s in SECTIONS:
        sec_items = [it for it in items if it["s"] == s]
        sec_items.sort(key=lambda it: (-sum(cur["ents"][e] for e in it.get("entities", [])), it["d"]))
        picks[s] = [{"d": it["d"], "n": it["n"], "t": it.get("title_ko") or it["title"], "url": it["url"],
                     "src": it.get("source", "")} for it in sec_items[:3]]

    week = {
        "key": key,
        "label": week_label(key),
        "dates": week_dates(key),
        "days_present": len(recs),
        "counts": cur["counts"],
        "total": len(items),
        "prev_total": len(prev_items),
        "top_entities": top_ents,
        "rising": rising,
        "topic_share": topic_share,
        "daily": daily,
        "picks": picks,
        "generated_at": datetime.now(tz=KST).strftime("%Y-%m-%dT%H:%M:%S+09:00"),
    }
    if synthesize:
        syn = synthesize_week(week, items)
        if syn:
            week["synthesis"] = syn
    return week


# ---------------------------------------------------------------------------
# Gemini 주간 종합
# ---------------------------------------------------------------------------

WEEK_PROMPT = """당신은 교사 독자를 위한 AI·교육 주간 브리핑의 편집장입니다. 아래는 {label} 한 주 동안 실린 소식입니다.
각 항목은 "[날짜:섹션-번호] 제목 — 요약 앞부분" 형식입니다.

{items}

이 주를 가로지르는 흐름을 찾아 JSON 하나로 답하세요. 규칙:
- headline: 이 주를 한 문장(50자 이내)으로. 과장 없이.
- threads: 4개. 서로 다른 날짜·섹션(교육/논문/기술)을 묶는 흐름을 우선. 각 thread는 title(16자 이내),
  body(2~3문장, 어떤 소식들이 어떻게 이어지는지), refs(근거 id 배열 3~6개, 반드시 위 목록의 id 형식 그대로 "2026-10-28:edu-3").
- classroom: 다음 주 교실에서 생각해 볼 한 가지를 1문장, 제안형.
- 한국어, 번역투·상투어 없이, 항목에 없는 사실을 만들지 마세요.

JSON 스키마:
{{"headline": "...", "threads": [{{"title": "...", "body": "...", "refs": ["2026-10-28:edu-3"]}}], "classroom": "..."}}"""


def synthesize_week(week: dict, items: list[dict], api_key: str | None = None, model: str | None = None) -> dict | None:
    api_key = api_key or os.environ.get("GEMINI_API_KEY", "")
    if not api_key or len(items) < 20:
        return None
    model = model or os.environ.get("GEMINI_MODEL", DEFAULT_MODEL)
    valid = {f"{it['d']}:{it['s']}-{it['n']}" for it in items}
    h = hashlib.sha1("|".join(sorted(valid)).encode()).hexdigest()[:12]
    prev = week.get("synthesis") or {}
    if prev.get("items_hash") == h:
        return prev
    lines = []
    for it in sorted(items, key=lambda x: (x["d"], x["s"], x["n"])):
        summ = (it.get("summary") or "")[:120]
        lines.append(f"[{it['d']}:{it['s']}-{it['n']}] {it['title'].strip()}" + (f" — {summ}" if summ else ""))
    body = {
        "contents": [{"role": "user", "parts": [{"text": WEEK_PROMPT.format(label=week["label"], items="\n".join(lines))}]}],
        "generationConfig": {"temperature": 0.4, "maxOutputTokens": 4096, "responseMimeType": "application/json",
                             "thinkingConfig": {"thinkingBudget": 0}},
    }
    try:
        resp = requests.post(GEMINI_ENDPOINT.format(model=model), params={"key": api_key}, json=body, timeout=120)
    except requests.RequestException as exc:
        print(f"[WEEK] 요청 실패: {exc}", file=sys.stderr)
        return None
    if resp.status_code != 200:
        print(f"[WEEK] Gemini HTTP {resp.status_code}: {resp.text[:160]}", file=sys.stderr)
        return None
    text = ""
    try:
        cand = resp.json()["candidates"][0]
        text = "".join(p.get("text", "") for p in cand["content"]["parts"])
        data = _parse_json_loose(text) or {}
    except (KeyError, IndexError, TypeError) as exc:
        print(f"[WEEK] 응답 파싱 실패: {exc} | head={text[:120]!r}", file=sys.stderr)
        return None
    headline = str(data.get("headline", "")).strip()
    threads = []
    for th in data.get("threads") or []:
        if not isinstance(th, dict):
            continue
        refs = [r for r in (th.get("refs") or []) if isinstance(r, str) and r in valid]
        if th.get("title") and th.get("body"):
            threads.append({"title": str(th["title"])[:40], "body": str(th["body"])[:500], "refs": refs[:6]})
    if not headline or not threads:
        print("[WEEK] 응답 검증 실패", file=sys.stderr)
        return None
    print(f"[WEEK] {week['key']}: 종합 생성 ({len(threads)}개 흐름)", file=sys.stderr)
    return {"headline": headline[:100], "threads": threads[:4], "classroom": str(data.get("classroom", "")).strip()[:200],
            "model": model, "items_hash": h}


# ---------------------------------------------------------------------------
# 저장·렌더
# ---------------------------------------------------------------------------


def weekly_dir(data_dir: str) -> str:
    d = os.path.join(data_dir, "weekly")
    os.makedirs(d, exist_ok=True)
    return d


def load_week(data_dir: str, key: str) -> dict | None:
    p = os.path.join(weekly_dir(data_dir), f"{key}.json")
    if not os.path.isfile(p):
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def save_week(data_dir: str, week: dict) -> None:
    with open(os.path.join(weekly_dir(data_dir), f"{week['key']}.json"), "w", encoding="utf-8") as f:
        json.dump(week, f, ensure_ascii=False, indent=1)


def list_weeks(data_dir: str) -> list[str]:
    d = weekly_dir(data_dir)
    return sorted(f[:-5] for f in os.listdir(d) if f.endswith(".json") and "-W" in f)


def _ref(r: str, root: str) -> str:
    d, rest = r.split(":", 1)
    sec = rest.split("-")[0]
    n = rest.split("-")[1]
    md = f"{int(d[5:7])}/{int(d[8:10])}"
    return f'<a class="ref ref-{sec}" href="{root}archive/{d}.html#{sec}-{n}">{md} {SECTION_SHORT[sec]} {n}</a>'


def _delta(v: int | None, unit: str = "") -> str:
    if v is None:
        return ""
    cls = "up" if v > 0 else "down" if v < 0 else "flat"
    sign = "+" if v > 0 else ""
    return f'<span class="delta {cls}">{sign}{v}{unit}</span>'


def render_week_page(week: dict, template: str, root: str, base_url: str, issue_label: str) -> str:
    syn = week.get("synthesis") or {}
    h: list[str] = []
    # 종합
    if syn:
        h.append('<section class="wk-syn">')
        h.append(f'  <p class="wk-kicker">이 주의 흐름 <span class="board-tag">AI 종합</span></p>')
        h.append(f'  <h2 class="wk-headline">{esc(syn["headline"])}</h2>')
        h.append('  <div class="board-threads wk-threads">')
        for th in syn["threads"]:
            refs = "".join(_ref(r, root) for r in th.get("refs", []))
            h.append(f'    <article class="thread"><h3 class="thread-title">{esc(th["title"])}</h3>'
                     f'<p class="thread-body">{esc(th["body"])}</p><p class="thread-refs">{refs}</p></article>')
        if syn.get("classroom"):
            h.append(f'    <p class="board-classroom"><span class="board-classroom-k">다음 주 교실에서</span>{esc(syn["classroom"])}</p>')
        h.append('  </div>')
        h.append('</section>')
    else:
        tot = week["total"]
        tops = ", ".join(f"{e['name']}({e['n']})" for e in week["top_entities"][:3])
        h.append('<section class="wk-syn">')
        h.append('  <p class="wk-kicker">이 주의 흐름 <span class="board-tag">자동 집계</span></p>')
        h.append(f'  <h2 class="wk-headline">{week["days_present"]}일 {tot}건 · 가장 많이 등장한 주체 {esc(tops)}</h2>')
        h.append('</section>')

    # 숫자 띠
    c = week["counts"]
    h.append('<div class="wk-stats stat-row">')
    h.append(f'  <div class="stat"><span class="stat-n">{week["total"]}건</span><span class="stat-k">이 주 소식 {_delta(week["total"] - week["prev_total"], "건") if week["prev_total"] else ""}</span></div>')
    for s in SECTIONS:
        h.append(f'  <div class="stat"><span class="stat-n">{c.get(s, 0)}</span><span class="stat-k">{SECTION_LABEL[s]}</span></div>')
    h.append(f'  <div class="stat"><span class="stat-n">{week["days_present"]}일</span><span class="stat-k">발행</span></div>')
    h.append('</div>')

    # 그리드: 주체 / 주제 비중 / 날짜별 헤드라인 / 대표 기사
    h.append('<div class="wk-grid">')
    h.append('  <section class="wk-cell"><h3 class="cell-title">이 주의 주체 <span class="cell-hint">전주 대비</span></h3><ol class="rank-list">')
    mx = week["top_entities"][0]["n"] if week["top_entities"] else 1
    for i, e in enumerate(week["top_entities"], 1):
        h.append(f'    <li><span class="rank-i">{i}</span><a class="rank-name" href="{root}entity.html?e={esc(e["name"])}">{esc(e["name"])}</a>'
                 f'<span class="rank-bar"><i style="width:{round(e["n"] * 100 / mx)}%"></i></span><span class="rank-n">{e["n"]}</span>'
                 f'<span class="rank-d">{_delta(e["delta"])}</span></li>')
    h.append('  </ol>')
    if week["rising"]:
        h.append('  <div class="trend-deltas">' + "".join(
            f'<a class="trend-chip up kind-{r["kind"]}" href="{root}entity.html?e={esc(r["name"])}">▲ {esc(r["name"])}<b>+{r["delta"]}</b></a>'
            for r in week["rising"]) + '</div>')
    h.append('  </section>')

    h.append('  <section class="wk-cell"><h3 class="cell-title">주제 비중 <span class="cell-hint">전주 대비 %p</span></h3>')
    for s in SECTIONS:
        rows = week["topic_share"].get(s, [])
        if not rows:
            continue
        h.append(f'    <div class="share-row" data-cat="{s}"><div class="share-head"><span>{SECTION_LABEL[s]}</span><small>{c.get(s, 0)}건</small></div>')
        h.append('      <div class="share-bar">' + "".join(f'<i class="seg-{min(i, 5)}" style="flex:{r["n"]}" title="{esc(r["label"])} {r["n"]}건"></i>' for i, r in enumerate(rows)) + '</div>')
        h.append('      <div class="share-legend">' + "".join(
            f'<span class="topic-chip seg-{min(i, 5)}">{esc(r["label"])}<b>{r["pct"]}%</b>{_delta(r["delta"], "p")}</span>'
            for i, r in enumerate(rows[:5])) + '</div></div>')
    h.append('  </section>')

    h.append('  <section class="wk-cell span-2"><h3 class="cell-title">날짜별 헤드라인</h3><ul class="head-list">')
    for dy in week["daily"]:
        d = dy["d"]
        wd = ["월", "화", "수", "목", "금", "토", "일"][date.fromisoformat(d).weekday()]
        tag = '<span class="src-ai">AI 종합</span>' if dy["src"] == "ai" else ""
        txt = esc(dy["head"]) if dy["head"] else f'<span class="cell-empty">{dy["n"]}건 · 헤드라인 없음</span>'
        h.append(f'    <li><span class="head-date"><a href="{root}archive/{d}.html">{int(d[5:7])}/{int(d[8:10])} ({wd})</a></span><span class="head-txt">{txt}{tag}</span></li>')
    h.append('  </ul></section>')

    h.append('  <section class="wk-cell span-2"><h3 class="cell-title">주체가 가장 많이 겹친 기사 <span class="cell-hint">섹션별 3건</span></h3><div class="wk-picks">')
    for s in SECTIONS:
        if not week["picks"].get(s):
            continue
        h.append(f'    <div class="wk-pick-col" data-cat="{s}"><h4>{SECTION_LABEL[s]}</h4><ol class="col-list">')
        for p in week["picks"][s]:
            h.append(f'      <li class="entry"><span class="entry-num" aria-hidden="true">{int(p["d"][8:10]):02d}</span><div class="entry-body">'
                     f'<div class="entry-meta"><span class="entry-src">{esc(p["src"])}</span><span class="entry-sep">·</span><span class="entry-dt">{int(p["d"][5:7])}월 {int(p["d"][8:10])}일</span></div>'
                     f'<h3 class="entry-title"><a href="{esc(p["url"])}" target="_blank" rel="noopener noreferrer">{esc(p["t"])}</a></h3>'
                     f'<p class="entry-desc"><a class="ref ref-{s}" href="{root}archive/{p["d"]}.html#{s}-{p["n"]}">지면에서 보기</a></p></div></li>')
        h.append('    </ol></div>')
    h.append('  </div></section>')
    h.append('</div>')

    body = "\n".join(h)
    return (template
            .replace("{{ROOT}}", root)
            .replace("{{WEEK_KEY}}", week["key"])
            .replace("{{WEEK_LABEL}}", week["label"])
            .replace("{{WEEK_TITLE}}", syn.get("headline") or f"{week['label']} 주간 다이제스트")
            .replace("{{ISSUE_LABEL}}", issue_label)
            .replace("{{CANONICAL}}", f"{base_url}/weekly/{week['key']}.html")
            .replace("{{OG_IMAGE}}", f"{base_url}/assets/og-image.jpg")
            .replace("{{BODY}}", body)
            .replace("{{GENERATED_AT}}", week.get("generated_at", "")))


def render_weekly_index(weeks: list[dict], template: str, root: str, base_url: str) -> str:
    h = ['<ul class="wk-list">']
    for w in sorted(weeks, key=lambda x: x["key"], reverse=True):
        syn = w.get("synthesis") or {}
        head = syn.get("headline") or ""
        tops = " · ".join(e["name"] for e in w["top_entities"][:4])
        h.append(f'  <li class="wk-item"><a href="{w["key"]}.html">'
                 f'<span class="wk-item-key">{w["key"]}</span><span class="wk-item-label">{esc(w["label"])}</span>'
                 f'<span class="wk-item-head">{esc(head) if head else esc(tops)}</span>'
                 f'<span class="wk-item-n">{w["total"]}건 · {w["days_present"]}일{" · AI 종합" if head else ""}</span></a></li>')
    h.append('</ul>')
    return (template.replace("{{ROOT}}", root).replace("{{WEEK_KEY}}", "weekly").replace("{{WEEK_LABEL}}", "주간 다이제스트")
            .replace("{{WEEK_TITLE}}", "주간 다이제스트").replace("{{ISSUE_LABEL}}", "주간")
            .replace("{{CANONICAL}}", f"{base_url}/weekly/").replace("{{OG_IMAGE}}", f"{base_url}/assets/og-image.jpg")
            .replace("{{BODY}}", "\n".join(h)).replace("{{GENERATED_AT}}", datetime.now(tz=KST).strftime("%Y-%m-%dT%H:%M:%S+09:00")))


def build_weekly(data_dir: str, docs_dir: str, dates: list[str], today: str, base_url: str,
                 backfill: bool = False, synthesize: bool = True) -> list[str]:
    """끝난 주의 다이제스트를 만들고 페이지를 렌더한다. 만든/갱신한 주 키 목록 반환."""
    tpl_path = os.path.join(docs_dir, "_weekly_template.html")
    if not os.path.isfile(tpl_path):
        print("[WEEK] 템플릿 없음 — 건너뜀", file=sys.stderr)
        return []
    with open(tpl_path, encoding="utf-8") as f:
        template = f.read()
    out_dir = os.path.join(docs_dir, "weekly")
    os.makedirs(out_dir, exist_ok=True)

    done = completed_weeks(dates, today)
    targets = done if backfill else done[-1:]
    changed: list[str] = []
    for key in targets:
        existing = load_week(data_dir, key)
        if existing and existing.get("synthesis") and not backfill:
            continue
        week = build_week(data_dir, key, synthesize=synthesize)
        if not week:
            continue
        if existing and not week.get("synthesis") and existing.get("synthesis"):
            week["synthesis"] = existing["synthesis"]
        save_week(data_dir, week)
        changed.append(key)
    # 페이지는 항상 전체 재렌더 (템플릿 변경 반영, 수십 개라 가볍다)
    weeks = [w for w in (load_week(data_dir, k) for k in list_weeks(data_dir)) if w]
    for w in weeks:
        html = render_week_page(w, template, "../", base_url, f"{w['key']} · {w['days_present']}일 {w['total']}건")
        with open(os.path.join(out_dir, f"{w['key']}.html"), "w", encoding="utf-8") as f:
            f.write(html)
    with open(os.path.join(out_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(render_weekly_index(weeks, template, "../", base_url))
    print(f"[OK] 주간 다이제스트: {len(weeks)}주 렌더, 신규/갱신 {len(changed)}", file=sys.stderr)
    return changed
