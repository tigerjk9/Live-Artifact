#!/usr/bin/env python3
"""synthesis.py — 하루치 25건을 Gemini로 종합해 '오늘의 흐름' 3개 + 헤드라인을 만든다 (선택 기능).

- 환경변수 GEMINI_API_KEY 가 없으면 아무 것도 하지 않고 None 을 돌려준다.
  보드는 결정적 집계(주제·주체·교차 연결·7일 흐름)만으로도 완전하게 그려진다.
- 모델은 수집기 3곳과 동일한 gemini-2.5-flash 기본 (GEMINI_MODEL 로 변경).
- SDK 없이 REST 로 호출해 워크플로우 의존성을 requests 하나로 유지한다.
- 결과는 레코드에 저장되고 items_hash 가 같으면 재호출하지 않는다 (cron 재시도 시 비용 0).
"""

from __future__ import annotations

import hashlib
import json
import os
import sys

import requests

GEMINI_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
DEFAULT_MODEL = "gemini-2.5-flash"

SECTION_KO = {"edu": "교육 뉴스", "paper": "연구 논문", "tech": "AI 기술 뉴스"}

PROMPT = """당신은 교사 독자를 위한 AI·교육 일일 브리핑의 편집장입니다.
아래는 오늘 수집된 소식 전체입니다. 각 항목은 "[섹션-번호] 제목 — 요약" 형식입니다.

{items}

이 소식들을 가로지르는 흐름을 찾아 JSON 하나로 답하세요. 규칙:
- headline: 오늘 하루를 한 문장(45자 이내)으로. 과장 없이, 교사가 읽을 신문 1면 요약처럼.
- threads: 2~3개. 서로 다른 섹션(교육/논문/기술)을 최소 둘 이상 묶는 흐름을 우선하세요.
  각 thread는 title(14자 이내), body(2문장, 서로 다른 섹션의 소식이 어떻게 연결되는지 명시),
  refs(근거 항목 id 배열, 예 ["edu-3","tech-7","paper-1"], 2~5개, 반드시 위 목록에 있는 id만).
- classroom: 교사가 내일 교실에서 생각해 볼 한 가지를 1문장으로. 지시형이 아니라 제안형.
- 한국어로, 번역투·상투어 없이. 항목에 없는 사실을 만들지 마세요.

JSON 스키마:
{{"headline": "...", "threads": [{{"title": "...", "body": "...", "refs": ["edu-1"]}}], "classroom": "..."}}"""


def items_hash(record: dict) -> str:
    keys = []
    for s in ("edu", "paper", "tech"):
        for it in record["sections"].get(s, []):
            keys.append(f"{s}:{it.get('url', '')}:{bool(it.get('ai'))}")
    return hashlib.sha1("|".join(keys).encode("utf-8")).hexdigest()[:12]


def _format_items(record: dict) -> tuple[str, set[str]]:
    lines = []
    valid: set[str] = set()
    for s in ("edu", "paper", "tech"):
        items = record["sections"].get(s, [])
        if not items:
            continue
        lines.append(f"## {SECTION_KO[s]}")
        for it in items:
            rid = f"{s}-{it['n']}"
            valid.add(rid)
            summ = (it.get("summary") or "").strip()
            if it.get("implication"):
                summ = f"{summ} (시사점: {it['implication']})"
            summ = summ[:300]
            lines.append(f"[{rid}] {it['title'].strip()}" + (f" — {summ}" if summ else ""))
        lines.append("")
    return "\n".join(lines), valid


def synthesize(record: dict, api_key: str | None = None, model: str | None = None, timeout: int = 60) -> dict | None:
    """Gemini 로 종합을 생성한다. 키가 없거나 실패하면 None (호출자는 그냥 넘어간다)."""
    api_key = api_key or os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        return None
    model = model or os.environ.get("GEMINI_MODEL", DEFAULT_MODEL)

    h = items_hash(record)
    prev = record.get("synthesis") or {}
    if prev.get("items_hash") == h and prev.get("headline"):
        print(f"[SYN] {record['date']}: 동일 항목 집합 — 기존 종합 재사용", file=sys.stderr)
        return prev

    items_txt, valid = _format_items(record)
    if len(valid) < 5:
        return None

    body = {
        "contents": [{"role": "user", "parts": [{"text": PROMPT.format(items=items_txt)}]}],
        "generationConfig": {
            "temperature": 0.4,
            "maxOutputTokens": 1200,
            "responseMimeType": "application/json",
        },
    }
    url = GEMINI_ENDPOINT.format(model=model)
    try:
        resp = requests.post(url, params={"key": api_key}, json=body, timeout=timeout)
    except requests.RequestException as exc:
        print(f"[SYN] 요청 실패: {exc}", file=sys.stderr)
        return None
    if resp.status_code != 200:
        print(f"[SYN] Gemini HTTP {resp.status_code}: {resp.text[:200]}", file=sys.stderr)
        return None
    try:
        text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
        data = json.loads(text)
    except (KeyError, IndexError, ValueError, TypeError) as exc:
        print(f"[SYN] 응답 파싱 실패: {exc}", file=sys.stderr)
        return None

    out = _validate(data, valid)
    if not out:
        print("[SYN] 응답 검증 실패 — 종합 생략", file=sys.stderr)
        return None
    out["model"] = model
    out["items_hash"] = h
    print(f"[SYN] {record['date']}: 종합 생성 ({len(out['threads'])}개 흐름, {model})", file=sys.stderr)
    return out


def _validate(data: dict, valid: set[str]) -> dict | None:
    if not isinstance(data, dict):
        return None
    headline = str(data.get("headline", "")).strip()
    if not headline:
        return None
    threads = []
    for th in data.get("threads", []) or []:
        if not isinstance(th, dict):
            continue
        title = str(th.get("title", "")).strip()
        body = str(th.get("body", "")).strip()
        refs = [r for r in (th.get("refs") or []) if isinstance(r, str) and r in valid]
        if title and body:
            threads.append({"title": title[:40], "body": body[:400], "refs": refs[:5]})
    if not threads:
        return None
    return {
        "headline": headline[:90],
        "threads": threads[:3],
        "classroom": str(data.get("classroom", "")).strip()[:200],
    }


if __name__ == "__main__":
    # 사용: GEMINI_API_KEY=... python scripts/synthesis.py docs/data/2026-11-01.json
    if len(sys.argv) < 2:
        print("usage: synthesis.py <day.json>", file=sys.stderr)
        sys.exit(1)
    with open(sys.argv[1], encoding="utf-8") as f:
        rec = json.load(f)
    res = synthesize(rec)
    print(json.dumps(res, ensure_ascii=False, indent=2))
