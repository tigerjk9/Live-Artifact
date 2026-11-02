"""요약 TXT 포맷 3종 · 깨진 JSON 복구 · 평문 요약 · 제목 정규화."""

import json

import pytest

from fetch_and_generate import (
    canon_url,
    clean_title,
    iso_date,
    normalize_title,
    parse_ai_summary_txt,
    parse_items,
    parse_plain_txt,
    strip_html,
)

FORMAT_A = """날씨: 대전 흐림 10°C

──────────────────────
[2026년 11월 01일] AI·디지털 교육 브리핑
──────────────────────

1. 【광화문 칼럼】세계 48위, 숫자가 보내는 경고
   세계 48위라는 낮은 순위는 교육부의 영어교육 정책이 표방하는 글로벌 교육의 실제 모습을 보여주는 경고입니다.
   → 낮은 영어 성과 지표를 인지하고, 교실에서 실제적인 영어 의사소통 경험을 확대할 수 있습니다.
   https://news.google.com/rss/articles/abc?oc=5

2. LGU+-교육부-티오리한국, AI·정보보호 영재교육원 교육과정 고도화 나선다
   LGU+, 교육부, 티오리한국이 AI·정보보호 영재교육원 교육과정 고도화에 나섭니다.
   → AI 및 정보보호 교육과정 고도화에 맞춰 관련 내용을 수업에 적극적으로 다룰 수 있습니다.
   https://news.google.com/rss/articles/def?oc=5
"""

FORMAT_B = """11월 01일 주요 논문 소식:

1. AI literacy as a core component of AI education
   - 이 논문은 AI 교육의 기술적 초점을 넘어 사회-기술적 AI 리터러시 프레임워크를 기반으로 입문 AI 교육 과정을 설계합니다.
   - [논문 보기](https://www.semanticscholar.org/paper/18fbb8)

2. Use of AI in Developing English Speaking Skills
   - 방글라데시 학부생 대상 혼합 연구 결과, AI가 영어 말하기 능력 향상에 효과적임을 보여 줍니다.
   - [논문 보기](https://doi.org/10.3329/spectrum)

# 📅 오늘도 한 걸음 더, AI와 함께!
선생님, 따뜻한 차 한 잔으로 활기찬 하루를 시작하세요.
"""

FORMAT_C = """🌤️ 오늘 대전 날씨는 흐림

━━━━━━━━━━━━━━━━━━━━

📌 오늘의 AI·디지털 교육 브리핑 (11월 20일)

| # | 핵심 뉴스 |
|---|---|
| 1️⃣ | [이낙종 칼럼] 교원의 정치기본권 제한: 해외 교육현장에서 던지는 질문 |
| 🔟 | 교육부, 모두를 위한 인공지능(AI) 인재양성 방안 발표 |

> 오늘의 한 줄 요약: AI 시대에 발맞춰 교육계는 교사의 역할 재정립, AI·에듀테크 활용 확대를 추진하고 있습니다. 🚀

━━━━━━━━━━━━━━━━━━━━

# 1️⃣ [이낙종 칼럼] 교원의 정치기본권 제한: 해외 교육현장에서 던지는 질문
오피니언: 교원의 정치기본권 제한 문제는, 다문화 사회로 진입하는 교육 현장에서 균형 잡힌 시각을 갖춘 교원 양성의 필요성을 시사합니다.
🔗 링크: https://www.edupress.kr/news/articleView.html?idxno=21407

# 🔟 교육부, 모두를 위한 인공지능(AI) 인재양성 방안 발표
오피니언: 교육부의 AI 인재 양성 방안은 디지털 전환 시대에 발맞춰 교육 전반의 혁신을 가속화하는 중요한 발걸음입니다.
🔗 링크: https://news.google.com/rss/articles/xyz?oc=5

# 📅 오늘도 한 걸음 더, AI와 함께!
상쾌한 아침입니다!
"""


def test_format_a_splits_summary_and_implication():
    res, note = parse_ai_summary_txt(FORMAT_A)
    assert len(res) == 2
    first = res[normalize_title("【광화문 칼럼】세계 48위, 숫자가 보내는 경고")]
    assert first["summary"].startswith("세계 48위")
    assert first["implication"].startswith("낮은 영어 성과")
    assert "→" not in first["summary"]
    assert note is None


def test_format_b_paper_skips_markdown_links():
    res, _ = parse_ai_summary_txt(FORMAT_B)
    assert len(res) == 2
    s = res[normalize_title("AI literacy as a core component of AI education")]["summary"]
    assert "논문 보기" not in s and "http" not in s
    assert s.startswith("이 논문은")


def test_format_c_old_newsletter_and_daily_note():
    res, note = parse_ai_summary_txt(FORMAT_C)
    assert len(res) == 2, "emoji numeral headings (1️⃣ … 🔟) must be detected with MULTILINE"
    s = res[normalize_title("교육부, 모두를 위한 인공지능(AI) 인재양성 방안 발표")]["summary"]
    assert s.startswith("교육부의 AI 인재 양성 방안")
    assert "오피니언:" not in s
    assert note and note.startswith("AI 시대에 발맞춰") and "🚀" not in note


def test_boilerplate_note_is_dropped():
    _, note = parse_ai_summary_txt("> 오늘의 한 줄 요약: 교육을 중심으로 교육 현장의 혁신이 가속화되고 있습니다.\n")
    assert note is None
    _, note2 = parse_ai_summary_txt("> 오늘의 한 줄 요약: 짧음\n")
    assert note2 is None


def test_plain_txt_summary_lines():
    txt = """📚 디지털/AI 교육 뉴스 브리핑
총 2건
============================================================

1. [싱가포르] 교육부, 학교 버스요금 인상 “합리적 검토” 권고
   출처: 교육플러스
   날짜: 2026-04-19 22:06:00
   링크: https://www.edpl.co.kr/news/articleView.html?idxno=20374
   요약: [교육플러스=한은주 기자] 중동 분쟁으로 촉발된 국제 유가 급등이 싱가포르 교육 현장에도 직접적인 영향을 미치고 있다...

2. 요약 없는 기사 제목
   출처: 매체
   링크: https://example.com/a
"""
    res = parse_plain_txt(txt)
    assert len(res) == 1
    body = next(iter(res.values()))["summary"]
    assert body.startswith("[교육플러스=한은주 기자] 중동 분쟁") and not body.endswith("...")


def test_parse_items_repairs_conflict_markers_and_dedupes():
    raw = """[
  {"title": "A", "link": "https://x/a", "press": "p"},
  {
<<<<<<< HEAD
=======
    "title": "B", "link": "https://x/b", "press": "p"
>>>>>>> origin/main
  },
  {"title": "A again", "link": "https://x/a", "press": "p"},
]"""
    items = parse_items(raw)
    assert [it["title"] for it in items] == ["A", "B"], "trailing comma + markers repaired, duplicate URL removed"


def test_parse_items_keeps_theirs_when_both_sides_present():
    raw = """[
  {
<<<<<<< HEAD
    "title": "old", "link": "https://x/1", "press": "p"
=======
    "title": "new", "link": "https://x/2", "press": "p"
>>>>>>> origin/main
  }
]"""
    items = parse_items(raw)
    assert len(items) == 1 and items[0]["title"] == "new"


def test_parse_items_accepts_wrapped_objects():
    assert parse_items(json.dumps({"items": [{"title": "t", "link": "u"}]}))[0]["title"] == "t"
    assert parse_items("not json at all") == []


@pytest.mark.parametrize("raw,expected", [
    ("Sun, 10 May 2026 06:50:35 GMT", "2026-05-10"),
    ("2026-05-09 18:31:15", "2026-05-09"),
    ("2026-05-08", "2026-05-08"),
    ("", ""),
])
def test_iso_date(raw, expected):
    assert iso_date(raw) == expected


def test_clean_title_strips_press_suffix():
    assert clean_title("제목 - 코리아플러스", "코리아플러스") == "제목"
    assert clean_title("제목 - 네이트", "") == "제목"
    assert clean_title("A - B - C 는 긴 접미사가 아니라서 유지됩니다 어쩌구저쩌구 매우 길다", "") .startswith("A - B")


def test_strip_html_handles_double_encoding():
    assert strip_html("&amp;lt;img src=x&amp;gt; 본문 <b>굵게</b>") == "본문 굵게"


def test_canon_url_ignores_tracking_and_scheme():
    assert canon_url("https://www.example.com/a/?utm_source=x&id=1") == canon_url("http://example.com/a?id=1")
