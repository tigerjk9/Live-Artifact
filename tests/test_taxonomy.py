"""분류 규칙 회귀 세트 — 라벨은 사람이 확인한 것. 규칙을 고치면 여기서 깨진 것만 보면 된다."""

import pytest

from taxonomy import classify, detect_kind, extract_entities, topic_ids, topic_label

EDU = [
    ("교육부, AI 디지털교과서 2027년 전면 도입 발표", "ai_digital"),
    ("안민석 경기도교육감 “학생 질문·도전이 과학·수학교육의 중심”", "classroom"),
    ("충남교육청, 2026 신규 특수교사 역량 강화 배움 자리 운영", "teacher"),
    ("학생·학부모·교사 국회서 교육정책 논의…고교학점제·교원업무 쟁점", "policy"),
    ("경기도교육청 학생건강증진센터, 누적 방문객 1만 명 돌파", "student_care"),
    ("경상국립대학교 사범대학, 경남교육청과 미래교육·예비교원 양성 협력 강화", "higher_ed"),
    ("[OECD] 교사 빠진 교육혁신은 한계…교사 중심 정책 전환 촉구", "global"),
    ("인천시교육청, ‘읽걷쓰AI’ 국제 교육협력 기반 마련", "ai_digital"),
    ("수능 앞둔 고3 만난 김대중 교육감…“실력 발휘하길”", "higher_ed"),
    ("경남교육청, 민관 합동 통학로 안전 캠페인…어린이 교통사고 예방", "student_care"),
    ("최순자 경기도의원, 포천시 교육정책 주요사업 점검", "policy"),
    ("하성고, AI·디지털 기반 수업 혁신 현장 전격 공개…미래 교육 모델 제시", "ai_digital"),
]
TECH = [
    ("오픈AI, GPT-Rosalind 연구기관 접근 확대", "model"),
    ("How Albertsons Companies is reimagining retail from the inside out", "usecase"),
    ("OpenAI, 교사용 무료 ChatGPT 2027년 6월까지 제공", "edu_ai"),
    ("엔비디아 AI 반도체 '담보대출' 전략 성공할까, 삼성전자 SK하이닉스 실적에도 변수", "industry"),
    ("챗GPT서 옷 입어보고 쇼핑한다... 오픈AI, '가상 착용' 도입", "product"),
    ("MIT·사카나, 자가 진화 AI 에이전트 'SIFT' 발표...'검증 비용 병목' 해결", "agent_dev"),
    ("NYC 시의회 청문회, Anthropic, OpenAI, Google, Meta에게 선서 요구", "policy_safety"),
    ("아마존, 11조 규모 AI 칩 투자자에 매각 후 리스…재무 부담 낮춘다", "industry"),
    ("XBOW, GPT-5.6 솔로 크롬 제로데이 취약점 체인 6일 만에 개발", "policy_safety"),
    ("카카오, 개인화 AI 에이전트 기반 기술 ‘Kanana-2-embedding’ 모델 2종 오픈소스 공개", "agent_dev"),
]
PAPER = [
    ("AI literacy as a core component of AI education", "literacy_ethics"),
    ("Empowering Physical Education Teachers: AI-Driven Personalized Learning in Schools", "genai_tutor"),
    ("Implementasi Computational Thinking (CT) dalam Mata Pelajaran Informatika/TIK di SMP", "stem_ct"),
    ("Use of AI in Developing English Speaking Skills: Bangladeshi Undergraduate Students’ Perceptions", "language"),
    ("Early Prediction of At-Risk MCA Students Using Machine Learning", "personalized"),
    ("Teaching Competency in the Age of Artificial Intelligence: A Review of Teachers’ Attitudes", "teacher_pd"),
    ("The flipped classroom model in medical education: A PRISMA-based systematic review", "design_curric"),
    ("Promoting Sustainable Social Emotional Learning at School", "inclusion_sel"),
    ("Metacognitive awareness in music education: an empirical investigation", "learning_sci"),
    ("Formative feedback and rubric-based grading of student essays", "assessment"),
]


@pytest.mark.parametrize("title,expected", EDU)
def test_edu_topics(title, expected):
    assert classify("edu", title) == expected


@pytest.mark.parametrize("title,expected", TECH)
def test_tech_topics(title, expected):
    assert classify("tech", title) == expected


@pytest.mark.parametrize("title,expected", PAPER)
def test_paper_topics(title, expected):
    assert classify("paper", title) == expected


def test_topic_ids_have_labels():
    for sec in ("edu", "paper", "tech"):
        for tid in topic_ids(sec):
            assert topic_label(sec, tid) != tid


def test_fallback_topic_when_nothing_matches():
    assert classify("tech", "DevDay 2026 Recap") == "model"
    assert classify("edu", "ㅇㅇ") == "policy"


@pytest.mark.parametrize("title,kind", [
    ("[기자수첩] 오석진 대전시교육감 100일", "opinion"),
    ("【인터뷰】안민석 경기도교육감", "interview"),
    ("[기획] 미래교육 해답 찾기 나선 충남교육청", "feature"),
    ("교육부, 방안 발표", None),
])
def test_detect_kind(title, kind):
    assert detect_kind(title) == kind


def test_entities_canonical_and_ordered():
    ents = extract_entities("오픈AI가 교사용 ChatGPT를 경기도교육청과 함께 시범 운영한다. 제미나이도 비교 대상.")
    assert ents[:2] == ["OpenAI", "ChatGPT"]
    assert "경기도교육청" in ents and "Gemini" in ents


def test_region_office_normalization():
    assert extract_entities("대전시교육청 설동호 교육감") == ["대전시교육청"]
    assert extract_entities("충남교육청과 세종교육") == ["충남교육청", "세종시교육청"]


def test_entities_do_not_overmatch_meta():
    assert "Meta" not in extract_entities("메타버스 교육과 메타인지 수업")
