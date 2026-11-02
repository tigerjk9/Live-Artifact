#!/usr/bin/env python3
"""feeds.py — RSS 2.0(feed.xml) · JSON Feed 1.1(feed.json). 하루 한 항목, 최근 30일.

항목 내용: 헤드라인(또는 자동 집계 문장) + Gemini 흐름 3개 + 섹션별 제목 목록(원문 링크).
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone, timedelta
from email.utils import format_datetime

from insights import SECTION_LABEL, SECTIONS, esc, load_day

KST = timezone(timedelta(hours=9))
FEED_DAYS = 30


def _entry_html(record: dict, base_url: str) -> str:
    syn = record.get("synthesis") or {}
    parts: list[str] = []
    if syn.get("headline"):
        parts.append(f"<p><strong>{esc(syn['headline'])}</strong></p>")
    for th in syn.get("threads") or []:
        parts.append(f"<p><b>{esc(th.get('title', ''))}</b> — {esc(th.get('body', ''))}</p>")
    if syn.get("classroom"):
        parts.append(f"<p><i>교실에서:</i> {esc(syn['classroom'])}</p>")
    for s in SECTIONS:
        items = record["sections"].get(s, [])
        if not items:
            continue
        parts.append(f"<h3>{SECTION_LABEL[s]} ({len(items)})</h3><ol>")
        for it in items:
            title = it.get("title_ko") or it["title"]
            parts.append(f'<li><a href="{esc(it["url"])}">{esc(title)}</a></li>')
        parts.append("</ol>")
    parts.append(f'<p><a href="{base_url}/archive/{record["date"]}.html">지면 보기</a></p>')
    return "\n".join(parts)


def _title(record: dict, issue_no: int) -> str:
    syn = record.get("synthesis") or {}
    head = syn.get("headline") or (record.get("notes") or {}).get("edu") or ""
    total = sum(len(record["sections"].get(s, [])) for s in SECTIONS)
    base = f"제 {issue_no}호 · {record['date']}"
    return f"{base} · {head}" if head else f"{base} · 교육·논문·기술 {total}건"


def build_feeds(data_dir: str, docs_dir: str, index_days: list[dict], base_url: str) -> None:
    dates = [e["d"] for e in index_days]
    recent = dates[-FEED_DAYS:]
    rss_items: list[str] = []
    json_items: list[dict] = []
    for d in reversed(recent):
        rec = load_day(data_dir, d)
        if not rec:
            continue
        issue_no = dates.index(d) + 1
        link = f"{base_url}/archive/{d}.html"
        gen = rec.get("generated_at") or f"{d}T10:00:00+09:00"
        try:
            pub = datetime.fromisoformat(gen)
        except ValueError:
            pub = datetime.strptime(d, "%Y-%m-%d").replace(tzinfo=KST)
        html = _entry_html(rec, base_url)
        title = _title(rec, issue_no)
        rss_items.append(
            "    <item>\n"
            f"      <title>{esc(title)}</title>\n"
            f"      <link>{link}</link>\n"
            f'      <guid isPermaLink="true">{link}</guid>\n'
            f"      <pubDate>{format_datetime(pub)}</pubDate>\n"
            f"      <description><![CDATA[{html}]]></description>\n"
            "    </item>"
        )
        json_items.append({
            "id": link, "url": link, "title": title,
            "content_html": html, "date_published": pub.isoformat(),
            "image": f"{base_url}/og/{d}.jpg" if os.path.isfile(os.path.join(docs_dir, "og", f"{d}.jpg")) else None,
        })

    now = format_datetime(datetime.now(tz=KST))
    rss = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">\n'
        "  <channel>\n"
        "    <title>Daily Intelligence</title>\n"
        f"    <link>{base_url}/</link>\n"
        "    <description>교육 뉴스 · AI 논문 · AI 기술 뉴스 일일 브리핑 — 닷커넥터 김진관</description>\n"
        "    <language>ko</language>\n"
        f"    <lastBuildDate>{now}</lastBuildDate>\n"
        f'    <atom:link href="{base_url}/feed.xml" rel="self" type="application/rss+xml"/>\n'
        + "\n".join(rss_items) + "\n"
        "  </channel>\n</rss>\n"
    )
    with open(os.path.join(docs_dir, "feed.xml"), "w", encoding="utf-8") as f:
        f.write(rss)
    jf = {
        "version": "https://jsonfeed.org/version/1.1",
        "title": "Daily Intelligence",
        "home_page_url": f"{base_url}/",
        "feed_url": f"{base_url}/feed.json",
        "description": "교육 뉴스 · AI 논문 · AI 기술 뉴스 일일 브리핑",
        "language": "ko",
        "authors": [{"name": "닷커넥터 김진관", "url": "https://litt.ly/dot_connector"}],
        "items": [{k: v for k, v in it.items() if v is not None} for it in json_items],
    }
    with open(os.path.join(docs_dir, "feed.json"), "w", encoding="utf-8") as f:
        json.dump(jf, f, ensure_ascii=False, indent=1)
    print(f"[OK] feed.xml / feed.json: {len(rss_items)}일", flush=True)
