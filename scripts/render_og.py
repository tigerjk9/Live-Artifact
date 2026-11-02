#!/usr/bin/env python3
"""render_og.py — 날짜별 OG 이미지(1200×630 JPEG)를 Playwright로 만든다.

사용
  python scripts/render_og.py --date 2026-11-02 [2026-11-01 ...]
  python scripts/render_og.py --missing      # docs/og/ 에 없는 날짜 전부
  python scripts/render_og.py --all          # 전부 다시
Playwright가 없으면(로컬·러너 미설치) 종료코드 3으로 조용히 끝난다 — 페이지는 기본 og-image.jpg로 폴백.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from insights import SECTIONS, compute_board, esc, list_dates, load_day  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(ROOT, "docs")
DATA = os.path.join(DOCS, "data")
OG_DIR = os.path.join(DOCS, "og")
TEMPLATE = os.path.join(DOCS, "_og_template.html")


def issue_no(date: str, dates: list[str]) -> int:
    return dates.index(date) + 1 if date in dates else sum(1 for d in dates if d < date) + 1


def build_html(record: dict, template: str, index_days: list[dict], dates: list[str]) -> str:
    board = compute_board(record, index_days)
    d = record["date"]
    y, m, dd = d.split("-")
    import datetime as _dt
    wd = ["월", "화", "수", "목", "금", "토", "일"][_dt.date(int(y), int(m), int(dd)).weekday()]
    ents = [e for e in board["entities"] if e["kind"] in ("org", "edu_org", "model", "issue")][:5]
    chips = "".join(f'<span class="chip kind-{e["kind"]}">{esc(e["name"])}<b>{e["n"]}</b></span>' for e in ents)
    counts = "".join(
        f'<span class="cnt cnt-{s}"><i></i>{label} <b>{board["counts"].get(s, 0)}</b></span>'
        for s, label in (("edu", "교육"), ("paper", "논문"), ("tech", "기술"))
    )
    tag = "AI 종합" if board["threads"] else "자동 집계"
    threads_html = ""
    if board["threads"]:
        parts = []
        for th in board["threads"][:3]:
            refs = [r.split("-")[0] for r in th.get("refs", []) if "-" in r]
            sec = max(set(refs), key=refs.count) if refs else ""
            parts.append(f'<div class="th {sec}">{esc(th.get("title", ""))}</div>')
        threads_html = '<div class="threads">' + "".join(parts) + "</div>"
    elif ents:
        parts = [f'<div class="th">{esc(e["name"])} <span style="font-weight:400;color:oklch(54% 0.015 55)">{e["n"]}건</span></div>' for e in ents[:3]]
        threads_html = '<div class="threads">' + "".join(parts) + "</div>"
    head_cls = "long" if len(board["headline"]) > 48 else ""
    return (template
            .replace("{{THREADS}}", threads_html)
            .replace("{{HEAD_CLASS}}", head_cls)
            .replace("{{DATE_KR}}", f"{int(y)}년 {int(m)}월 {int(dd)}일 {wd}요일")
            .replace("{{ISSUE_NO}}", str(issue_no(d, dates)))
            .replace("{{HEADLINE}}", esc(board["headline"]))
            .replace("{{TAG}}", tag)
            .replace("{{COUNTS}}", counts)
            .replace("{{CHIPS}}", chips)
            .replace("{{ASSET_BASE}}", "file:///" + DOCS.replace("\\", "/") + "/"))


async def render(dates: list[str]) -> int:
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print("[OG] playwright 미설치 — 건너뜀", file=sys.stderr)
        return 3
    import json
    with open(TEMPLATE, encoding="utf-8") as f:
        template = f.read()
    with open(os.path.join(DATA, "index.json"), encoding="utf-8") as f:
        index = json.load(f)
    index_days = index["days"]
    all_dates = [e["d"] for e in index_days]
    os.makedirs(OG_DIR, exist_ok=True)
    done = 0
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        ctx = await browser.new_context(viewport={"width": 1200, "height": 630}, device_scale_factor=1)
        page = await ctx.new_page()
        for d in dates:
            rec = load_day(DATA, d)
            if not rec:
                continue
            html = build_html(rec, template, index_days, all_dates)
            await page.set_content(html, wait_until="networkidle")
            try:
                await page.evaluate("document.fonts && document.fonts.ready")
            except Exception:
                pass
            await page.wait_for_timeout(150)
            await page.screenshot(path=os.path.join(OG_DIR, f"{d}.jpg"), type="jpeg", quality=80)
            done += 1
        await browser.close()
    print(f"[OG] {done}개 생성 → docs/og/", file=sys.stderr)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", nargs="*", default=[])
    ap.add_argument("--missing", action="store_true")
    ap.add_argument("--all", action="store_true")
    args = ap.parse_args()
    dates = list(args.date)
    have = list_dates(DATA)
    if args.all:
        dates = have
    elif args.missing:
        dates = [d for d in have if not os.path.isfile(os.path.join(OG_DIR, f"{d}.jpg"))]
    if not dates:
        print("[OG] 대상 없음", file=sys.stderr)
        return 0
    return asyncio.run(render(dates))


if __name__ == "__main__":
    sys.exit(main())
