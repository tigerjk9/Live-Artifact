#!/usr/bin/env python3
"""healthcheck.py — 최근 레코드로 운영 상태를 판정해 docs/data/health.json을 쓰고, 경보면 종료코드 2.

경보 조건 (워크플로우가 이슈를 연다):
  - 한국어 요약 커버리지 60% 미만이 **이틀 연속**
  - GEMINI_API_KEY가 설정돼 있는데 종합(synthesis)이 **사흘 연속** 없음
  - 오늘 레코드가 폴백 섹션을 포함한 채 **이틀 연속**
항상 stdout에 한 줄 요약을 찍고, 경보 사유는 `::warning::`으로도 낸다.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from insights import list_dates, load_day, record_ai_count, record_total  # noqa: E402

KST = timezone(timedelta(hours=9))


def main() -> int:
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    data_dir = os.path.join(root, "docs", "data")
    today = datetime.now(tz=KST).date()
    dates = list_dates(data_dir)
    recent = [d for d in dates if d >= (today - timedelta(days=6)).isoformat()]
    rows = []
    for d in recent:
        rec = load_day(data_dir, d) or {}
        total = record_total(rec) if rec else 0
        fresh = record_ai_count(rec, fresh_only=True) if rec else 0
        rows.append({
            "d": d, "total": total,
            "pct": round(fresh * 100 / total) if total else 0,
            "fallback": sorted((rec.get("fallback") or {}).keys()),
            "synthesis": bool((rec.get("synthesis") or {}).get("headline")),
            "enrich": bool(rec.get("enrich")),
        })
    key_set = bool(os.environ.get("GEMINI_API_KEY"))
    reasons: list[str] = []
    last2 = rows[-2:]
    if len(last2) == 2 and all(r["total"] and r["pct"] < 60 for r in last2):
        reasons.append(f"요약 커버리지 60% 미만 이틀 연속 ({last2[0]['d']} {last2[0]['pct']}%, {last2[1]['d']} {last2[1]['pct']}%)")
    if len(last2) == 2 and all(r["fallback"] for r in last2):
        reasons.append(f"폴백 섹션 이틀 연속 ({', '.join(last2[-1]['fallback'])})")
    last3 = rows[-3:]
    if key_set and len(last3) == 3 and not any(r["synthesis"] for r in last3):
        reasons.append("GEMINI_API_KEY가 있는데 종합이 사흘 연속 없음")
    missing_today = today.isoformat() not in dates
    health = {
        "checked_at": datetime.now(tz=KST).strftime("%Y-%m-%dT%H:%M:%S+09:00"),
        "today": today.isoformat(),
        "today_present": not missing_today,
        "gemini_key": key_set,
        "days": rows,
        "alert": bool(reasons),
        "reasons": reasons,
    }
    os.makedirs(data_dir, exist_ok=True)
    with open(os.path.join(data_dir, "health.json"), "w", encoding="utf-8") as f:
        json.dump(health, f, ensure_ascii=False, indent=1)
    summary = " | ".join(f"{r['d'][5:]} {r['pct']}%{'·FB' if r['fallback'] else ''}{'·AI' if r['synthesis'] else ''}" for r in rows[-4:])
    print(f"[HEALTH] {summary} | alert={bool(reasons)}")
    for r in reasons:
        print(f"::warning::{r}")
    return 2 if reasons else 0


if __name__ == "__main__":
    sys.exit(main())
