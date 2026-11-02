#!/usr/bin/env python3
"""taxonomy.py — 주제 분류 · 주체(엔티티) 추출 규칙 (LLM 없이 결정적으로 동작).

수집기가 붙여 주는 `keyword`는 기술 뉴스의 70%, 논문의 80%에서 비어 있어(`press_rss`,
15자 초과 영문 용어) 분류 축으로 쓸 수 없다. 그래서 제목(가중치 2)과 요약(가중치 1)에
패턴 매칭 점수를 합산해 섹션별 주제 하나를 고른다. 규칙은 2025-11 ~ 2026-11 약 8천 건을
관찰해 만들었고, 새 패턴은 해당 주제의 patterns 리스트에 추가하면 된다.

공개 API
  classify(section, title, summary)  -> topic_id
  topic_label(section, topic_id)     -> 한국어 라벨
  extract_entities(text)             -> [canonical, ...] (등장 순, 중복 제거)
  entity_kind(name)                  -> "org" | "model" | "edu_org" | "issue" | "tech"
  detect_kind(title)                 -> "opinion" | "interview" | "feature" | None
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# 주제(topic) — 섹션별. 리스트 순서가 동점일 때의 우선순위다 (구체적인 주제를 앞에).
# 각 패턴은 정규식. 영문 단어는 \b 경계와 (?i)를 명시한다.
# ---------------------------------------------------------------------------

TOPICS: dict[str, list[tuple[str, str, list[str]]]] = {
    "edu": [
        ("ai_digital", "AI·디지털교육", [
            r"\bAI\b", r"인공지능", r"디지털", r"에듀테크", r"교과서", r"코스웨어", r"생성형",
            r"챗GPT", r"ChatGPT", r"소프트웨어", r"코딩", r"정보교육", r"메타버스", r"로봇",
            r"\bSW\b", r"스마트", r"온라인", r"플랫폼", r"데이터", r"튜터",
        ]),
        ("global", "해외·연구", [
            r"\bOECD\b", r"유네스코", r"\bUNESCO\b", r"해외", r"국제", r"글로벌", r"보고서",
            r"연구소", r"미국", r"일본", r"싱가포르", r"핀란드", r"중국", r"영국", r"독일",
            r"프랑스", r"베트남", r"호주", r"북한", r"北",
        ]),
        ("teacher", "교사·교권", [
            r"교사(?!용)", r"교원", r"연수", r"교권", r"교직", r"전문적\s?학습\s?공동체", r"노조",
            r"교총", r"업무\s?경감", r"교장", r"교감", r"담임", r"교무",
        ]),
        ("student_care", "학생·돌봄·안전", [
            r"마음\s?건강", r"정서", r"안전", r"학폭", r"학교\s?폭력", r"돌봄", r"늘봄", r"급식",
            r"복지", r"유보통합", r"특수\s?교육", r"다문화", r"상담", r"위기\s?학생", r"학생\s?인권",
            r"체육", r"건강", r"심리", r"유치원", r"어린이집",
        ]),
        ("higher_ed", "대학·입시·평생", [
            r"대학(?!원생)", r"대학교", r"사범대", r"수능", r"입시", r"대입", r"평생\s?교육", r"직업\s?교육", r"취업",
            r"정시", r"수시", r"학과", r"캠퍼스", r"전문대", r"학위",
        ]),
        ("classroom", "수업·교육과정", [
            r"수업", r"교실", r"교육\s?과정", r"탐구", r"프로젝트", r"평가", r"\bIB\b", r"고교\s?학점제",
            r"독서", r"문해력", r"교과", r"학습", r"미래\s?교육", r"혁신\s?학교", r"배움", r"체험",
            r"과학\s?교육", r"수학\s?교육", r"영어\s?교육", r"놀이", r"창의",
        ]),
        ("policy", "정책·행정", [
            r"교육\s?정책", r"교육부", r"교육청", r"교육감", r"국회", r"국감", r"국정\s?감사", r"의회", r"의원",
            r"예산", r"조례", r"정책", r"계획", r"방안", r"발표", r"감사", r"선거", r"협의회",
            r"시행", r"법안", r"개편", r"추진", r"행정", r"공약", r"타운홀", r"시도", r"지자체",
            r"시장", r"군수", r"구청",
        ]),
    ],
    "tech": [
        ("edu_ai", "교육 AI", [
            r"교육", r"학습(?!법|률)", r"학생", r"교사", r"학교", r"수능", r"튜터", r"에듀테크",
            r"(?i)\beducation", r"(?i)\bstudents?\b", r"(?i)\bteachers?\b", r"(?i)\bclassroom",
            r"(?i)\blearners?\b", r"(?i)\bK-?12\b", r"(?i)\bschool",
        ]),
        ("policy_safety", "정책·윤리·안전", [
            r"규제", r"정책", r"법(?:안|원|률)", r"윤리", r"안전", r"저작권", r"보안", r"취약점",
            r"개인\s?정보", r"소송", r"정부", r"규범", r"편향", r"딥페이크", r"위험", r"경고",
            r"의회", r"청문회", r"선서", r"국회", r"당국", r"공정위", r"법원", r"반독점", r"제재",
            r"(?i)\bhearing", r"(?i)\bcouncil", r"(?i)\bsenate", r"(?i)\bcongress", r"(?i)\bantitrust", r"(?i)\bgovern",
            r"(?i)\bsafety\b", r"(?i)\bregulat", r"(?i)\bpolicy\b", r"(?i)\bcopyright", r"(?i)\bsecurity",
            r"(?i)\bprivacy", r"(?i)\blawsuit", r"(?i)\bethic",
        ]),
        ("industry", "산업·투자·인프라", [
            r"투자", r"인수", r"파트너십", r"매출", r"시장", r"펀드", r"\bIPO\b", r"데이터\s?센터",
            r"칩\b", r"\bGPU\b", r"엔비디아", r"반도체", r"전력", r"클라우드", r"계약", r"고용",
            r"경제", r"버블", r"\bCEO\b", r"기업\s?가치", r"억\s?달러", r"조\s?원", r"상장", r"지분",
            r"수익", r"광고", r"요금", r"가격", r"구독", r"위성", r"우주",
            r"(?i)\binvest", r"(?i)\bacqui", r"(?i)\bpartnership", r"(?i)\brevenue", r"(?i)\bfunding",
            r"(?i)\bvaluation", r"(?i)\bdata ?cent", r"(?i)\bchips?\b", r"(?i)\bcloud\b", r"(?i)\benterprise",
        ]),
        ("agent_dev", "에이전트·개발도구", [
            r"에이전트", r"\bAPI\b", r"코딩", r"개발자", r"자동화", r"프레임워크", r"\bSDK\b", r"\bMCP\b",
            r"도구", r"플랫폼", r"워크플로", r"오케스트레이션", r"\bIDE\b", r"커서", r"Cursor",
            r"(?i)\bagent", r"(?i)\bdevelopers?\b", r"(?i)\bcoding", r"(?i)\bautomat", r"(?i)\bworkflow",
            r"(?i)\bCodex", r"(?i)\btools?\b", r"(?i)\bopen[-\s]?source", r"오픈\s?소스",
        ]),
        ("model", "모델·연구", [
            r"모델", r"\bGPT", r"클로드", r"Claude", r"제미나이", r"제미니", r"Gemini", r"\bLLM",
            r"벤치마크", r"추론", r"성능", r"파라미터", r"논문", r"연구", r"알고리즘", r"학습법",
            r"정확도", r"\bSOTA\b", r"멀티모달", r"음성\s?모델", r"이미지\s?생성", r"영상\s?생성",
            r"오픈\s?웨이트", r"경량", r"\b\d+B\b", r"데이터셋", r"강화\s?학습", r"신경망", r"양자",
            r"(?i)\bmodels?\b", r"(?i)\bbenchmark", r"(?i)\breasoning", r"(?i)\bresearch", r"(?i)\bpaper\b",
            r"(?i)\btraining", r"(?i)\breleases?\b", r"(?i)\blaunch",
        ]),
        ("product", "제품·서비스", [
            r"기능", r"서비스", r"앱\b", r"출시", r"도입", r"챗GPT", r"ChatGPT", r"쇼핑", r"검색",
            r"브라우저", r"음성", r"이미지", r"영상", r"업데이트", r"사용자", r"이용자", r"구독",
            r"스마트폰", r"웨어러블", r"디바이스", r"기기",
            r"(?i)\bfeatures?\b", r"(?i)\busers?\b", r"(?i)\bapps?\b", r"(?i)\bbrowser", r"(?i)\bsearch\b",
            r"(?i)\bshopping", r"(?i)\bvoice\b", r"(?i)\bupdate",
        ]),
        ("usecase", "활용·사례", [
            r"(?i)^how\b", r"(?i)\bhow\s+\w+\s+(?:is|are|uses?|built|scal)", r"사례", r"활용", r"튜토리얼",
            r"생산성", r"업무", r"의료", r"금융", r"제조", r"유통", r"마케팅", r"고객", r"리테일",
            r"법률", r"농업", r"물류", r"번역", r"상담", r"창작", r"디자인", r"게임",
            r"(?i)\bcustomer", r"(?i)\bretail", r"(?i)\bhealthcare", r"(?i)\bfinanc", r"(?i)\bproductivity",
            r"(?i)\bcase stud", r"(?i)\bwith OpenAI\b", r"(?i)\bscales?\b", r"(?i)\breimagin",
        ]),
    ],
    "paper": [
        ("genai_tutor", "생성형 AI·튜터", [
            r"(?i)\bgenerative", r"(?i)\bChatGPT", r"(?i)\bGPT", r"(?i)\bLLMs?\b", r"(?i)\blarge language",
            r"(?i)\bchatbot", r"(?i)\btutor", r"(?i)\bintelligent tutoring", r"(?i)\bAI[-\s]?(?:assisted|powered|driven|based|enabled)",
            r"(?i)\bconversational", r"(?i)\bprompt", r"(?i)\bco-?agent", r"(?i)\bagents?\b", r"(?i)\bcopilot",
            r"생성형", r"챗GPT", r"튜터", r"에이전트",
        ]),
        ("literacy_ethics", "AI 리터러시·윤리", [
            r"(?i)\bliteracy", r"(?i)\bethic", r"(?i)\bresponsible", r"(?i)\bacademic integrity",
            r"(?i)\bplagiarism", r"(?i)\btrust", r"(?i)\bbias", r"(?i)\bpolicy", r"(?i)\bgovernance",
            r"(?i)\bperception", r"(?i)\bacceptance", r"(?i)\breadiness", r"(?i)\bcritical thinking",
            r"리터러시", r"윤리", r"인식",
        ]),
        ("personalized", "개인화·학습분석", [
            r"(?i)\bpersonali[sz]", r"(?i)\badaptive", r"(?i)\blearning analytics", r"(?i)\bdata mining",
            r"(?i)\brecommend", r"(?i)\bpredict", r"(?i)\bdropout", r"(?i)\bpathway", r"(?i)\bknowledge tracing",
            r"(?i)\bdeep learning", r"(?i)\bmachine learning", r"(?i)\bneural network", r"(?i)\bmultidimensional",
            r"개인화", r"맞춤형", r"적응형", r"학습\s?분석",
        ]),
        ("assessment", "평가·피드백", [
            r"(?i)\bassess", r"(?i)\bfeedback", r"(?i)\bevaluat", r"(?i)\bgrading", r"(?i)\brubric",
            r"(?i)\bexam", r"(?i)\bformative", r"(?i)\bscoring", r"(?i)\btest(?:ing)?\b", r"(?i)\bmeasur",
            r"평가", r"피드백", r"채점",
        ]),
        ("teacher_pd", "교사 전문성", [
            r"(?i)\bteachers?\b", r"(?i)\beducators?\b", r"(?i)\bprofessional development", r"(?i)\bcompetenc",
            r"(?i)\bTPACK", r"(?i)\bpre-?service", r"(?i)\bin-?service", r"(?i)\blesson plan", r"(?i)\bteaching quality",
            r"(?i)\binstructors?\b", r"(?i)\bfaculty", r"(?i)\bprofessional learning", r"(?i)\bteacher training",
            r"교사", r"교원", r"교수\s?역량",
        ]),
        ("learning_sci", "학습과학·인지", [
            r"(?i)\bcognit", r"(?i)\bmetacognit", r"(?i)\bself-?regulat", r"(?i)\bmotivation", r"(?i)\bengagement",
            r"(?i)\bcognitive load", r"(?i)\bmemory", r"(?i)\battention", r"(?i)\bretention", r"(?i)\bneuro",
            r"(?i)\bdesirable difficult", r"(?i)\bembodied", r"(?i)\bself-?efficacy", r"(?i)\bagency\b",
            r"(?i)\bmindset", r"(?i)\bepistem", r"(?i)\bconnectivis", r"(?i)\bdual process", r"(?i)\boffloading",
            r"인지", r"메타인지", r"자기\s?조절", r"동기", r"몰입",
        ]),
        ("stem_ct", "컴퓨팅·STEM", [
            r"(?i)\bcomputational thinking", r"(?i)\bprogramming", r"(?i)\bcoding", r"(?i)\bSTEM\b", r"(?i)\bSTEAM\b",
            r"(?i)\bmathematic", r"(?i)\bmath\b", r"(?i)\bscience\b", r"(?i)\bphysics", r"(?i)\bchemistry",
            r"(?i)\bbiology", r"(?i)\bengineering", r"(?i)\brobotic", r"(?i)\bquantum", r"(?i)\bScratch\b",
            r"(?i)\binformatic", r"(?i)\bcomputer science", r"(?i)\bunplugged", r"\bCT\b",
            r"컴퓨팅\s?사고", r"프로그래밍", r"코딩", r"수학", r"과학", r"물리", r"로봇",
        ]),
        ("language", "언어·문해", [
            r"(?i)\bEnglish", r"(?i)\blanguage learning", r"(?i)\bEFL\b", r"(?i)\bESL\b", r"(?i)\bspeaking",
            r"(?i)\bwriting", r"(?i)\breading", r"(?i)\bvocabulary", r"(?i)\btranslation", r"(?i)\bbilingual",
            r"(?i)\bArabic", r"(?i)\bChinese\b", r"(?i)\bKorean\b", r"(?i)\bliterature", r"(?i)\bdrama\b",
            r"(?i)\bsecond language", r"(?i)\bforeign language", r"(?i)\bInglés", r"(?i)\bidioma",
            r"영어", r"언어", r"문해", r"읽기", r"쓰기", r"말하기",
        ]),
        ("inclusion_sel", "포용·정서·웰빙", [
            r"(?i)\bSEL\b", r"(?i)\bsocial[-\s]emotional", r"(?i)\binclusi", r"(?i)\bequity", r"(?i)\bemotion",
            r"(?i)\bwell-?being", r"(?i)\bspecial needs", r"(?i)\bdisabilit", r"(?i)\bmental health",
            r"(?i)\bvulnerable", r"(?i)\bidentity", r"(?i)\bautism", r"(?i)\bdiversity", r"(?i)\bgender",
            r"(?i)\bphysical education", r"(?i)\bhealth\b", r"(?i)\bsport",
            r"정서", r"포용", r"형평", r"웰빙", r"특수",
        ]),
        ("design_curric", "교수설계·교육과정", [
            r"(?i)\bcurricul", r"(?i)\binstructional design", r"(?i)\bbackward design", r"(?i)\bflipped",
            r"(?i)\bpedagog", r"(?i)\bframework", r"(?i)\bblended", r"(?i)\bhybrid", r"(?i)\bonline learning",
            r"(?i)\bMOOC", r"(?i)\bcourse design", r"(?i)\bUDL\b", r"(?i)\binquiry", r"(?i)\bproject-?based",
            r"(?i)\bgamif", r"(?i)\bgame-?based", r"(?i)\bserious game", r"(?i)\bsimulation", r"(?i)\bvirtual reality",
            r"(?i)\bVR\b", r"(?i)\bAR\b", r"(?i)\bimmersive", r"(?i)\bteaching (?:method|strateg|model)",
            r"(?i)\bdidactic", r"(?i)\bcollaborative learning", r"(?i)\bcooperative", r"(?i)\bactive learning",
            r"(?i)\bhigher education", r"(?i)\bvocational", r"(?i)\bmedical education", r"(?i)\bnursing",
            r"교육\s?과정", r"교수\s?설계", r"수업\s?모형", r"게임", r"협력\s?학습",
        ]),
    ],
}

TOPIC_FALLBACK = {"edu": "policy", "tech": "model", "paper": "design_curric"}

# 파이썬의 \b는 한글도 단어 문자로 보므로 "오픈AI가"·"읽걷쓰AI"에서 영문 토큰 경계를 못 잡는다.
# 영문·숫자만 단어 문자로 치는 경계로 바꿔 컴파일한다.
_ASCII_B = r"(?:(?<![A-Za-z0-9])|(?![A-Za-z0-9]))"


def _ascii_boundary(pattern: str) -> str:
    return pattern.replace(r"\b", _ASCII_B)


_TOPIC_RE: dict[str, list[tuple[str, list[re.Pattern]]]] = {
    sec: [(tid, [re.compile(_ascii_boundary(p)) for p in pats]) for tid, _label, pats in rules]
    for sec, rules in TOPICS.items()
}
_TOPIC_LABEL: dict[str, dict[str, str]] = {
    sec: {tid: label for tid, label, _ in rules} for sec, rules in TOPICS.items()
}


def topic_label(section: str, topic_id: str) -> str:
    return _TOPIC_LABEL.get(section, {}).get(topic_id, topic_id)


def topic_ids(section: str) -> list[str]:
    return [tid for tid, _, _ in TOPICS.get(section, [])]


def classify(section: str, title: str, summary: str = "") -> str:
    """제목(×2)·요약(×1) 패턴 점수 합산으로 섹션별 주제 하나를 고른다."""
    rules = _TOPIC_RE.get(section)
    if not rules:
        return "other"
    title = title or ""
    summary = summary or ""
    best_id, best_score = None, 0.0
    for tid, pats in rules:
        score = 0.0
        for p in pats:
            if p.search(title):
                score += 2.0
            elif p.search(summary):
                score += 1.0
        # 동점이면 리스트 앞쪽(구체적 주제) 우선 — '>' 비교로 유지
        if score > best_score:
            best_id, best_score = tid, score
    return best_id or TOPIC_FALLBACK.get(section, "other")


# ---------------------------------------------------------------------------
# 글의 형식(kind) — 칼럼/인터뷰/기획은 주제와 별개의 축이다
# ---------------------------------------------------------------------------

_KIND_RULES = [
    ("opinion", re.compile(r"칼럼|기고|사설|시론|기자수첩|논단|오피니언|제언|데스크|\[시선\]|\[의견\]|寄稿")),
    ("interview", re.compile(r"인터뷰|대담|\[만남\]")),
    ("feature", re.compile(r"\[기획|\[르포|\[현장|\[특집|\[분석|\[심층|\[포커스|\[이슈")),
]

KIND_LABEL = {"opinion": "칼럼·오피니언", "interview": "인터뷰", "feature": "기획·현장"}


def detect_kind(title: str) -> str | None:
    t = title or ""
    for kind, rx in _KIND_RULES:
        if rx.search(t):
            return kind
    return None


# ---------------------------------------------------------------------------
# 주체(entity) 사전 — canonical 이름, 종류, 별칭 정규식
#   (canonical, kind, 대소문자 구분 패턴, 영문 대소문자 무시 패턴) — 둘 중 하나는 비어도 된다.
# ---------------------------------------------------------------------------

ENTITIES: list[tuple[str, str, str, str]] = [
    # AI 기업 (org) — 모델명은 별도 엔티티로 세어 "회사 vs 제품" 흐름을 구분한다
    ("OpenAI", "org", r"OpenAI|오픈\s?AI\b|오픈에이아이|알트먼|Altman", r""),
    ("ChatGPT", "model", r"ChatGPT|챗GPT|챗지피티|\bGPT[-\s]?\d|\bGPT-(?:[A-Z]|o|Rosalind|Synopsys|라이브)|\bGPTs\b|\bSora\b|소라\s?\d", r""),
    ("Google", "org", r"Google|구글|DeepMind|딥마인드|Alphabet|알파벳|피차이|Pichai|하사비스|Hassabis", r""),
    ("Gemini", "model", r"Gemini|제미나이|제미니|\bGemma\b|젬마|NotebookLM|노트북LM|\bVeo\b|\bImagen\b|나노\s?바나나|Nano Banana", r""),
    ("Anthropic", "org", r"Anthropic|앤스로픽|앤트로픽|아모데이|Amodei", r""),
    ("Claude", "model", r"Claude|클로드|\bMythos\b|미소스", r""),
    ("Microsoft", "org", r"Microsoft|마이크로소프트|\bMS\b|Copilot|코파일럿|Azure|애저|나델라|Nadella", r""),
    ("Meta", "org", r"\bMeta\b|메타(?!버스|인지|데이터|분석)|\bLlama\b|라마\s?\d|저커버그|Zuckerberg", r""),
    ("NVIDIA", "org", r"NVIDIA|Nvidia|엔비디아|젠슨\s?황|Jensen Huang", r""),
    ("Apple", "org", r"\bApple\b|애플(?!리케이션)|\bSiri\b|시리\b", r""),
    ("Amazon", "org", r"Amazon|아마존|\bAWS\b|Bedrock|베드록|Alexa|알렉사|베조스|Bezos", r""),
    ("xAI", "org", r"\bxAI\b|\bGrok\b|그록|머스크|Musk", r""),
    ("DeepSeek", "org", r"DeepSeek|딥시크", r""),
    ("Mistral", "org", r"Mistral|미스트랄", r""),
    ("Perplexity", "org", r"Perplexity|퍼플렉시티", r""),
    ("Alibaba", "org", r"Alibaba|알리바바|\bQwen\b|큐원|통이", r""),
    ("Hugging Face", "org", r"Hugging\s?Face|허깅\s?페이스", r""),
    ("Oracle", "org", r"\bOracle\b|오라클", r""),
    ("Moonshot", "org", r"Moonshot|문샷|\bKimi\b|키미\s?K", r""),
    # 국내 기업
    ("네이버", "org", r"네이버|NAVER|하이퍼클로바|HyperCLOVA", r""),
    ("카카오", "org", r"카카오|Kakao|카나나|Kanana", r""),
    ("삼성", "org", r"삼성|Samsung", r""),
    ("LG", "org", r"\bLG\b|엑사원|EXAONE|LGU\+|LG유플러스", r""),
    ("SK", "org", r"\bSKT\b|SK텔레콤|SK하이닉스|\bSK\b", r""),
    ("KT", "org", r"\bKT\b", r""),
    ("업스테이지", "org", r"업스테이지|Upstage", r""),
    ("뤼튼", "org", r"뤼튼|Wrtn", r""),
    ("천재교과서", "org", r"천재교과서|천재교육", r""),
    # 교육 당국·기관 (edu_org)
    ("교육부", "edu_org", r"교육부|교육\s?부총리|교육장관|Ministry of Education", r""),
    ("국회", "edu_org", r"국회|국정\s?감사|국감|교육위원회|교육위\b", r""),
    ("OECD", "org", r"\bOECD\b", r""),
    ("유네스코", "org", r"\bUNESCO\b|유네스코", r""),
    ("EBS", "edu_org", r"\bEBS\b", r""),
    ("KERIS", "edu_org", r"\bKERIS\b|한국교육학술정보원", r""),
    ("평가원", "edu_org", r"교육과정평가원|평가원|\bKICE\b", r""),
    ("교원단체", "edu_org", r"교총|교사노조|전교조|교원단체|교사노동조합", r""),
    # 교육 이슈 (issue)
    ("AI 디지털교과서", "issue", r"AI\s?디지털\s?교과서|\bAIDT\b|디지털\s?교과서", r""),
    ("고교학점제", "issue", r"고교\s?학점제", r""),
    ("IB", "issue", r"\bIB\b|국제\s?바칼로레아", r""),
    ("늘봄학교", "issue", r"늘봄", r""),
    ("유보통합", "issue", r"유보\s?통합", r""),
    ("교권", "issue", r"교권|교사\s?보호|무고성\s?아동학대", r""),
    ("학교폭력", "issue", r"학교\s?폭력|학폭", r""),
    ("수능·대입", "issue", r"수능|대입|입시|정시\b|수시\b", r""),
    ("사교육", "issue", r"사교육|학원\b", r""),
    ("마음건강", "issue", r"마음\s?건강|정신\s?건강|정서\s?위기|심리\s?지원", r""),
    ("문해력", "issue", r"문해력|독서\s?교육|읽기\s?교육", r""),
    ("특수교육", "issue", r"특수\s?교육|특수\s?교사|장애\s?학생", r""),
    ("다문화", "issue", r"다문화|이주\s?배경", r""),
    ("교사 연수", "issue", r"교원\s?연수|교사\s?연수|전문적\s?학습\s?공동체|전문성\s?개발", r"professional development|teacher training"),
    ("교육감 선거", "issue", r"교육감\s?선거|교육감\s?후보|예비\s?후보", r""),
    ("교육 예산", "issue", r"교육\s?예산|교부금|재정\s?교부", r""),
    # AI 기술 개념 (tech)
    ("에이전트", "tech", r"에이전트", r"\bagent(?:ic|s)?\b"),
    ("오픈소스", "tech", r"오픈\s?소스", r"\bopen[-\s]?(?:source|weight)"),
    ("벤치마크", "tech", r"벤치마크", r"\bbenchmark"),
    ("추론 모델", "tech", r"추론\s?(?:모델|능력|성능|엔진)", r"\breasoning"),
    ("GPU·데이터센터", "tech", r"\bGPU\b|데이터\s?센터|반도체|AI\s?칩|\bH[12]00\b|\bTPU\b|\bNPU\b", r"\bdata ?cent"),
    ("AI 안전·규제", "tech", r"AI\s?안전|안전성|AI\s?규제|AI\s?윤리", r"\balignment|\bAI safety|\bregulat"),
    ("저작권·소송", "tech", r"저작권|소송", r"\bcopyright|\blawsuit"),
    ("딥페이크", "tech", r"딥페이크", r"\bdeepfake"),
    ("코딩 AI", "tech", r"코딩|바이브\s?코딩|Claude Code|클로드\s?코드|\bCursor\b|커서\b", r"\bvibe coding|\bCodex\b|\bcoding"),
    ("로봇·휴머노이드", "tech", r"로봇|휴머노이드", r"\brobot"),
    ("생성형 AI", "tech", r"생성형\s?AI|생성\s?AI", r"\bgenerative AI|\bGenAI"),
    ("LLM", "tech", r"\bLLMs?\b|대규모\s?언어\s?모델|거대\s?언어\s?모델", r"\blarge language model"),
    ("AI 리터러시", "tech", r"AI\s?리터러시|디지털\s?리터러시", r"\bAI literacy|\bdigital literacy"),
    ("개인화 학습", "tech", r"개인화|맞춤형\s?(?:학습|교육)", r"\bpersonali[sz]ed|\badaptive learning"),
    ("AI 튜터", "tech", r"AI\s?튜터|튜터링", r"\btutor"),
    ("온디바이스 AI", "tech", r"온디바이스|엣지\s?AI", r"\bon-?device|\bedge AI"),
    ("AI 검색", "tech", r"AI\s?검색|검색\s?엔진", r"\bAI search"),
    ("영상·이미지 생성", "tech", r"영상\s?생성|이미지\s?생성", r"\bvideo generation|\bimage generation|\btext-to-(?:video|image)"),
]

# 시도교육청·교육감 — 지역을 잡아 교육청 단위 canonical로 통일
_REGION_CANON = {
    "서울": "서울시교육청", "부산": "부산시교육청", "대구": "대구시교육청", "인천": "인천시교육청",
    "광주": "광주시교육청", "대전": "대전시교육청", "울산": "울산시교육청", "세종": "세종시교육청",
    "경기": "경기도교육청", "강원": "강원교육청", "충북": "충북교육청", "충남": "충남교육청",
    "전북": "전북교육청", "전남": "전남교육청", "경북": "경북교육청", "경남": "경남교육청",
    "제주": "제주교육청",
}
_REGION_RE = re.compile(
    r"(서울|부산|대구|인천|광주|대전|울산|세종|경기|강원|충북|충남|전북|전남|경북|경남|제주)"
    r"(?:특별시|광역시|특별자치시|특별자치도|시|도)?\s?(?:교육청|교육감|교육)"
)


def _compile_entity(cs: str, ci: str) -> re.Pattern:
    """대소문자 구분 패턴(cs)과 영문 무시 패턴(ci)을 하나의 정규식으로 합친다."""
    combined = []
    if cs:
        combined.append("(?:" + _ascii_boundary(cs) + ")")
    if ci:
        combined.append("(?i:" + _ascii_boundary(ci) + ")")
    return re.compile("|".join(combined))


_ENTITY_RE: list[tuple[str, str, re.Pattern]] = [
    (name, kind, _compile_entity(cs, ci)) for name, kind, cs, ci in ENTITIES
]

_ENTITY_KIND = {name: kind for name, kind, _cs, _ci in ENTITIES}
for _canon in _REGION_CANON.values():
    _ENTITY_KIND[_canon] = "edu_org"

ENTITY_KIND_LABEL = {
    "org": "기업·기관", "model": "모델·제품", "edu_org": "교육 당국", "issue": "교육 이슈", "tech": "기술 개념",
}


def entity_kind(name: str) -> str:
    return _ENTITY_KIND.get(name, "org")


def extract_entities(text: str) -> list[str]:
    """텍스트에서 사전에 있는 주체를 등장 순서대로(중복 없이) 반환한다."""
    if not text:
        return []
    found: list[tuple[int, str]] = []
    for name, _kind, rx in _ENTITY_RE:
        m = rx.search(text)
        if m:
            found.append((m.start(), name))
    for m in _REGION_RE.finditer(text):
        found.append((m.start(), _REGION_CANON[m.group(1)]))
    found.sort()
    out: list[str] = []
    for _, name in found:
        if name not in out:
            out.append(name)
    return out


# 교차 연결용 — 섹션이 달라도 같은 흐름으로 묶이는 주제 묶음
BRIDGES: list[tuple[str, dict[str, set[str]]]] = [
    ("AI × 교육", {"edu": {"ai_digital"}, "tech": {"edu_ai"}, "paper": {"genai_tutor", "literacy_ethics", "personalized"}}),
    ("정책·규범", {"edu": {"policy"}, "tech": {"policy_safety"}, "paper": {"literacy_ethics"}}),
    ("교사 역량", {"edu": {"teacher"}, "paper": {"teacher_pd"}}),
    ("평가·학습분석", {"edu": {"classroom"}, "paper": {"assessment", "personalized"}}),
]


if __name__ == "__main__":  # 간단 자가 점검
    tests = [
        ("edu", "교육부, AI 디지털교과서 2027년 전면 도입 발표", ""),
        ("edu", "안민석 경기도교육감 “학생 질문·도전이 과학·수학교육의 중심”", ""),
        ("edu", "[기자수첩] 오석진 대전시교육감 100일…AI보다 먼저 바뀌어야 할 교실", ""),
        ("edu", "충남교육청, 2026 신규 특수교사 역량 강화 배움 자리 운영", ""),
        ("tech", "오픈AI, GPT-Rosalind 연구기관 접근 확대", ""),
        ("tech", "How Albertsons Companies is reimagining retail from the inside out", ""),
        ("tech", "OpenAI, 교사용 무료 ChatGPT 2027년 6월까지 제공", ""),
        ("tech", "구글 \"AI 경제 혁명, 똑똑한 모델보다 협력하는 에이전트가 이끈다\"", ""),
        ("paper", "AI literacy as a core component of AI education", ""),
        ("paper", "Empowering Physical Education Teachers: AI-Driven Personalized Learning in Schools", ""),
        ("paper", "Implementasi Computational Thinking (CT) dalam Mata Pelajaran Informatika/TIK di SMP", ""),
    ]
    for sec, t, s in tests:
        print(f"[{sec:5}] {classify(sec, t, s):>15} | {detect_kind(t) or '-':>9} | {extract_entities(t)} | {t[:48]}")
