"""레코드 빌드 → 중복 표시 → 집계 → 렌더까지 네트워크 없이 끝까지 돈다."""

import json
import os
import re

import pytest

import fetch_and_generate as fg
from insights import (
    build_entity_index,
    build_index,
    build_search,
    compute_board,
    index_entry,
    render_board,
    save_day,
)
from synthesis import _parse_json_loose, _validate
from weekly import build_week, completed_weeks, week_dates, week_key

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _raw(title, url, press="AI Times", summary="", keyword="", **extra):
    d = {"title": title, "link": url, "press": press, "date": "2026-11-01 10:03:10", "summary": summary, "keyword": keyword}
    d.update(extra)
    return d


def make_record(date="2026-11-01", tech_titles=None):
    edu_cfg, paper_cfg, tech_cfg = (fg.SOURCES[k] for k in ("edu-news", "ai-paper", "ai-tech"))
    edu_raw = [
        _raw("교육부, AI 디지털교과서 2027년 전면 도입 발표 - 코리아플러스", "https://news.google.com/rss/articles/e1?oc=5", "코리아플러스",
             ai_summary="교육부가 AI 디지털교과서 도입 일정을 발표했습니다.", ai_implication="교실에서 디지털교과서 활용 방안을 미리 구상할 수 있습니다.", keyword="교육정책"),
        _raw("[기자수첩] 교사의 거의 60%가 전문성 개발 필요성을 느낀다", "https://news.google.com/rss/articles/e2?oc=5", "에듀프레스",
             ai_summary="교사 전문성 개발 수요가 높다는 조사 결과입니다. → 연수 계획을 점검할 수 있습니다."),
    ]
    paper_raw = [
        {"title": "AI literacy as a core component of AI education", "link": "https://doi.org/10.1/x", "published": "2026-10-29",
         "authors": "Sri Yash Tadimalla, Mary Lou Maher, A, B", "source": "semantic_scholar", "pdf_link": "https://x/p.pdf", "keyword": "AI education",
         "ai_summary": "이 논문은 AI 리터러시 교육 과정을 설계합니다."},
    ]
    tech_titles = tech_titles or ["구글 \"AI 경제 혁명, 똑똑한 모델보다 협력하는 에이전트가 이끈다\"", "OpenAI expands partnership with Oracle"]
    tech_raw = [_raw(t, f"https://www.aitimes.com/{i}", ai_summary="AI 생태계는 협력하는 다중 에이전트 설계에 집중할 것입니다.") for i, t in enumerate(tech_titles)]
    rec = {"date": date, "generated_at": f"{date}T11:00:00+09:00", "sections": {}, "fallback": {}, "notes": {}}
    rec["sections"]["edu"] = [fg.build_item(r, edu_cfg, "edu-news", "edu", i + 1) for i, r in enumerate(edu_raw)]
    rec["sections"]["paper"] = [fg.build_item(r, paper_cfg, "ai-paper", "paper", i + 1) for i, r in enumerate(paper_raw)]
    rec["sections"]["tech"] = [fg.build_item(r, tech_cfg, "ai-tech", "tech", i + 1) for i, r in enumerate(tech_raw)]
    return rec


def test_build_item_normalizes_fields():
    rec = make_record()
    e = rec["sections"]["edu"][0]
    assert e["title"] == "교육부, AI 디지털교과서 2027년 전면 도입 발표"
    assert e["topic"] == "ai_digital" and e["ai"] is True
    assert e["implication"].startswith("교실에서") and "→" not in e["summary"]
    assert "교육부" in e["entities"] and "AI 디지털교과서" in e["entities"]
    e2 = rec["sections"]["edu"][1]
    assert e2["kind"] == "opinion"
    assert e2["implication"].startswith("연수 계획"), "'→' inside merged summary is split into implication"
    p = rec["sections"]["paper"][0]
    assert p["authors"].endswith("외 2명") and p["pdf"].endswith(".pdf")


def test_mark_duplicates_and_stats_exclusion(tmp_path):
    data_dir = str(tmp_path)
    day1 = make_record("2026-11-01")
    save_day(data_dir, day1)
    day2 = make_record("2026-11-02", tech_titles=["OpenAI expands partnership with Oracle", "새 기사 제목입니다 오늘만"])
    # 두 번째 날 기술 1번은 URL이 다르지만 제목이 같다 → 제목 매칭으로 중복, 2번은 완전히 새 기사
    day2["sections"]["tech"][0]["url"] = "https://other.example/dup"
    day2["sections"]["tech"][1]["url"] = "https://other.example/brand-new"
    n = fg.mark_duplicates(day2, data_dir)
    assert n >= 3  # edu 2 + paper 1 (같은 URL) + tech 제목 중복
    assert day2["sections"]["tech"][0]["dup_of"] == "2026-11-01"
    assert "dup_of" not in day2["sections"]["tech"][1]
    entry = index_entry(day2)
    assert entry["dups"] == n
    assert "OpenAI" not in entry["ents"] or entry["ents"].get("OpenAI", 0) == 0
    board = compute_board(day2, [index_entry(day1)])
    assert board["dups"] == n
    assert all(e["name"] != "AI 디지털교과서" for e in board["entities"]), "duplicate items do not feed entity counts"


def test_render_page_replaces_all_placeholders_and_keeps_gate_markers(tmp_path):
    rec = make_record()
    tpl = open(os.path.join(ROOT, "docs", "_template.html"), encoding="utf-8").read()
    board = render_board(compute_board(rec, [index_entry(rec)]))
    html = fg.render_page(rec, tpl, board, "", "", "https://x/", "2026-11-01T11:00:00+09:00", "2026년 11월 1일 11:00 KST", issue_no=7)
    assert not re.search(r"{{[A-Z_]+}}", html), "unreplaced placeholder"
    assert 'name="ai-summary-coverage" content="5/5"' in html
    assert 'col-count">2건' in html and 'col-count">1건' in html
    assert "제 7호" in html
    assert 'id="edu-1"' in html and 'data-topic="ai_digital"' in html
    assert "entry-impl" in html and "교실에서 디지털교과서" in html
    assert 'og:image" content="https://tigerjk9.github.io/Live-Artifact/assets/og-image.jpg"' in html


def test_render_page_fallback_label_and_low_coverage_notice():
    rec = make_record()
    rec["fallback"] = {"tech": "2026-10-31"}
    for it in rec["sections"]["edu"] + rec["sections"]["paper"]:
        it["ai"] = False
        it["summary"] = ""
    tpl = open(os.path.join(ROOT, "docs", "_template.html"), encoding="utf-8").read()
    html = fg.render_page(rec, tpl, "", "", "", "https://x/", "", "")
    assert 'col-count">2건 (10/31)' in html, "fallback section label keeps the (M/D) marker the workflow gate greps"
    assert 'content="0/5"' in html, "fallback section counts 0 toward fresh coverage; others have no korean summary"
    assert "brief-notice" in html


def test_index_search_entity_outputs(tmp_path):
    data_dir = str(tmp_path / "data")
    os.makedirs(data_dir)
    for d in ("2026-10-30", "2026-10-31", "2026-11-01"):
        save_day(data_dir, make_record(d))
    idx = build_index(data_dir)
    assert idx["latest"] == "2026-11-01" and len(idx["days"]) == 3 and idx["total_items"] == 15
    rows = build_search(data_dir)
    assert len(rows) == 15 and os.path.isfile(os.path.join(data_dir, "search", "2026-10.json"))
    assert os.path.isfile(os.path.join(data_dir, "search", "index.json"))
    n = build_entity_index(data_dir, min_mentions=3)
    ents = json.load(open(os.path.join(data_dir, "entities.json"), encoding="utf-8"))["entities"]
    names = [e["name"] for e in ents]
    assert n >= 1 and "교육부" in names
    slug = [e for e in ents if e["name"] == "교육부"][0]["slug"]
    ent = json.load(open(os.path.join(data_dir, "entity", f"{slug}.json"), encoding="utf-8"))
    assert ent["n"] == 3 and ent["items"][0]["d"] == "2026-11-01"


def test_synthesis_validation_and_loose_json():
    assert _parse_json_loose('```json\n{"headline": "a", "threads": [{"title":"t","body":"b","refs":["edu-1"],}],}\n```')["headline"] == "a"
    assert _parse_json_loose('{"headline": "a", "threads": [') is None
    ok = _validate({"headline": "h", "threads": [{"title": "t", "body": "b", "refs": ["edu-1", "bogus-9"]}], "classroom": "c"}, {"edu-1"})
    assert ok["threads"][0]["refs"] == ["edu-1"]
    assert _validate({"headline": "h", "threads": []}, {"edu-1"}) is None


def test_weekly_helpers_and_build(tmp_path):
    assert week_key("2026-11-01") == "2026-W44" and week_dates("2026-W44")[0] == "2026-10-26"
    assert completed_weeks(["2026-10-26", "2026-11-01", "2026-11-02"], "2026-11-02") == ["2026-W44"]
    data_dir = str(tmp_path)
    for d in ("2026-10-27", "2026-10-29", "2026-11-01"):
        save_day(data_dir, make_record(d))
    wk = build_week(data_dir, "2026-W44", synthesize=False)
    assert wk["days_present"] == 3 and wk["total"] == 15
    assert wk["top_entities"][0]["n"] >= 3 and len(wk["daily"]) == 3
    assert all(len(v) <= 3 for v in wk["picks"].values())


def test_issue_number():
    days = [{"d": "2025-11-12"}, {"d": "2025-11-13"}, {"d": "2025-11-15"}]
    assert fg.issue_number("2025-11-12", days) == 1
    assert fg.issue_number("2025-11-15", days) == 3
    assert fg.issue_number("2025-11-14", days) == 3  # 레코드 없는 날은 앞까지 +1
