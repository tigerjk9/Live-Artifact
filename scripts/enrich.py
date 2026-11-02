#!/usr/bin/env python3
"""enrich.py — 하루 레코드의 항목별 메타데이터를 Gemini로 보강한다 (선택 기능, 키 없으면 no-op).

하루 1회 호출로 세 가지를 한꺼번에 받는다.
  topics     모든 항목의 주제를 섹션별 주제 목록 중 하나로 다시 고른다 (규칙 분류의 오분류 보정).
             적용 시 item["topic_rule"]에 원래 규칙 결과를 남기고 item["topic_src"]="ai".
  title_ko   논문(영문·다국어 제목)의 한국어 제목. item["title_ko"].
  summaries  한국어 요약이 없는 항목(수집기가 링크만 남긴 2026-03~04 등)에 제목 기반 1~2문장 요약 +
             교육 뉴스는 교실 시사점 한 문장. item["summary"], item["implication"], item["summary_src"]="ai-backfill".

- 결과는 레코드에 저장되고 enrich_hash(항목 URL + 과제 집합)가 같으면 재호출하지 않는다.
- 모델·호출 방식은 synthesis.py와 같다 (REST, gemini-2.5-flash, thinkingBudget 0).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time

import requests

from synthesis import DEFAULT_MODEL, GEMINI_ENDPOINT, _parse_json_loose
from taxonomy import topic_ids, topic_label

SECTIONS = ("edu", "paper", "tech")
SECTION_KO = {"edu": "교육 뉴스", "paper": "연구 논문", "tech": "AI 기술 뉴스"}
_HANGUL_RE = re.compile(r"[가-힣]")

PROMPT = """당신은 교사 독자를 위한 AI·교육 일일 브리핑의 데이터 편집자입니다. 아래 항목들에 대해 JSON 하나로 답하세요.

## 주제 목록 (섹션별 — 반드시 이 id 중 하나만)
{topic_lists}

## 항목
형식: [id] 제목 — 요약 (요약이 '없음'이면 제목만 있는 항목)
{items}

## 과제
1. topics: 모든 id에 대해 그 섹션의 주제 id 하나. 제목이 말하는 핵심 사안 기준. 칼럼·기고라도 다루는 주제로 분류.
2. title_ko: 다음 논문 id의 한국어 제목 (60자 이내, 자연스러운 번역, 고유명사는 원어 병기 가능): {paper_ids}
3. summaries: 다음 id는 요약이 없습니다: {missing_ids}
   각각 제목이 말하는 바를 1~2문장 한국어로 풀어 쓰고(제목에 없는 사실·수치를 지어내지 말 것, 불확실하면 "~라는 소식입니다"처럼 전달체로),
   교육 뉴스(edu-)에는 implication으로 교사가 교실에서 생각해 볼 점을 한 문장(제안형, "~할 수 있습니다") 덧붙입니다. 기술·논문은 implication을 빈 문자열로.
   목록이 '없음'이면 summaries는 빈 객체로.

JSON 스키마:
{{"topics": {{"edu-1": "policy"}}, "title_ko": {{"paper-1": "..."}}, "summaries": {{"edu-3": {{"summary": "...", "implication": "..."}}}}}}"""


def enrich_hash(record: dict, tasks: tuple[str, ...]) -> str:
    keys = [",".join(tasks)]
    for s in SECTIONS:
        for it in record["sections"].get(s, []):
            keys.append(f"{s}:{it.get('url', '')}")
    return hashlib.sha1("|".join(keys).encode("utf-8")).hexdigest()[:12]


def _needs(record: dict) -> tuple[list[str], list[str]]:
    paper_ids, missing = [], []
    for s in SECTIONS:
        for it in record["sections"].get(s, []):
            rid = f"{s}-{it['n']}"
            if s == "paper" and not it.get("title_ko") and not _HANGUL_RE.search(it.get("title", "")):
                paper_ids.append(rid)
            if not it.get("ai") and not it.get("summary_src"):
                missing.append(rid)
    return paper_ids, missing


def _format(record: dict) -> tuple[str, str, set[str]]:
    topic_lists = []
    for s in SECTIONS:
        ids = ", ".join(f"{t}({topic_label(s, t)})" for t in topic_ids(s))
        topic_lists.append(f"- {s} ({SECTION_KO[s]}): {ids}")
    lines, valid = [], set()
    for s in SECTIONS:
        for it in record["sections"].get(s, []):
            rid = f"{s}-{it['n']}"
            valid.add(rid)
            summ = (it.get("summary") or "").strip()[:200] or "없음"
            lines.append(f"[{rid}] {it['title'].strip()} — {summ}")
    return "\n".join(topic_lists), "\n".join(lines), valid


def enrich_record(
    record: dict,
    api_key: str | None = None,
    model: str | None = None,
    tasks: tuple[str, ...] = ("topics", "title_ko", "summaries"),
    timeout: int = 90,
) -> bool:
    """레코드를 제자리에서 보강한다. 변경이 있으면 True."""
    api_key = api_key or os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        return False
    model = model or os.environ.get("GEMINI_MODEL", DEFAULT_MODEL)

    h = enrich_hash(record, tasks)
    if (record.get("enrich") or {}).get("hash") == h:
        return False
    paper_ids, missing = _needs(record)
    topic_lists, items_txt, valid = _format(record)
    if not valid:
        return False

    prompt = PROMPT.format(
        topic_lists=topic_lists,
        items=items_txt,
        paper_ids=", ".join(paper_ids) if ("title_ko" in tasks and paper_ids) else "없음",
        missing_ids=", ".join(missing) if ("summaries" in tasks and missing) else "없음",
    )
    body = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 6144,
            "responseMimeType": "application/json",
            "thinkingConfig": {"thinkingBudget": 0},
        },
    }
    try:
        resp = requests.post(GEMINI_ENDPOINT.format(model=model), params={"key": api_key}, json=body, timeout=timeout)
    except requests.RequestException as exc:
        print(f"[ENR] 요청 실패: {exc}", file=sys.stderr)
        return False
    if resp.status_code != 200:
        print(f"[ENR] Gemini HTTP {resp.status_code}: {resp.text[:160]}", file=sys.stderr)
        return False
    text = ""
    try:
        cand = resp.json()["candidates"][0]
        text = "".join(p.get("text", "") for p in cand["content"]["parts"])
        data = _parse_json_loose(text)
        if data is None:
            raise ValueError(f"finishReason={cand.get('finishReason')} len={len(text)}")
    except (KeyError, IndexError, ValueError, TypeError) as exc:
        print(f"[ENR] 응답 파싱 실패: {exc} | head={text[:120]!r}", file=sys.stderr)
        return False

    by_id = {f"{s}-{it['n']}": (s, it) for s in SECTIONS for it in record["sections"].get(s, [])}
    n_topic = n_title = n_sum = 0

    if "topics" in tasks:
        for rid, tid in (data.get("topics") or {}).items():
            if rid not in by_id or not isinstance(tid, str):
                continue
            s, it = by_id[rid]
            if tid in topic_ids(s) and tid != it.get("topic"):
                it.setdefault("topic_rule", it.get("topic"))
                it["topic"] = tid
                it["topic_src"] = "ai"
                n_topic += 1
            elif tid in topic_ids(s):
                it["topic_src"] = "ai"
    if "title_ko" in tasks:
        for rid, ko in (data.get("title_ko") or {}).items():
            if rid in by_id and isinstance(ko, str) and 2 <= len(ko.strip()) <= 80 and _HANGUL_RE.search(ko):
                by_id[rid][1]["title_ko"] = ko.strip()
                n_title += 1
    if "summaries" in tasks:
        for rid, obj in (data.get("summaries") or {}).items():
            if rid not in by_id or not isinstance(obj, dict):
                continue
            s, it = by_id[rid]
            summ = str(obj.get("summary", "")).strip()
            if len(summ) >= 20 and _HANGUL_RE.search(summ) and not it.get("ai"):
                it["summary"] = summ[:400]
                it["implication"] = str(obj.get("implication", "")).strip()[:200] if s == "edu" else ""
                it["ai"] = True
                it["summary_src"] = "ai-backfill"
                n_sum += 1

    record["enrich"] = {"hash": h, "model": model, "topics": n_topic, "title_ko": n_title, "summaries": n_sum}
    print(f"[ENR] {record['date']}: 주제 보정 {n_topic} · 한국어 제목 {n_title} · 요약 보강 {n_sum} ({model})", file=sys.stderr)
    return True


def enrich_range(data_dir: str, dates: list[str], tasks: tuple[str, ...], pause: float = 1.5) -> int:
    """유지보수용 — 여러 날짜를 순서대로 보강하고 저장한다. 변경된 레코드 수 반환."""
    from insights import load_day, save_day  # 순환 import 회피

    changed = 0
    for d in dates:
        rec = load_day(data_dir, d)
        if not rec:
            continue
        if enrich_record(rec, tasks=tasks):
            save_day(data_dir, rec)
            changed += 1
            time.sleep(pause)
    return changed
