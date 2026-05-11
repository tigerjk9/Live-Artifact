---
name: live-artifact-setup
description: "Live Artifact 뉴스 포털을 처음부터 구축하는 오케스트레이터 스킬. 3개 GitHub 레포(Auto-Edu-news-Collector, Auto-AI-Edu-Paper-Curator, Auto-AI-Tech-news-Collector)에서 매일 뉴스를 가져와 GitHub Pages HTML 사이트를 생성하는 전체 파이프라인을 설정한다. '라이브 아티팩트 만들어', '뉴스 포털 구축', 'live artifact setup'을 요청할 때 반드시 이 스킬을 사용한다."
---

# Live Artifact Setup — 뉴스 포털 구축 오케스트레이터

3개 뉴스 소스를 매일 집계하여 GitHub Pages에 자동 배포되는 HTML 뉴스 포털을 구축한다.

## 실행 모드: 에이전트 팀

## 최종 산출물

- `docs/index.html` — 매일 갱신되는 뉴스 포털 메인 페이지
- `docs/archive/YYYY-MM-DD.html` — 최근 28일치 날짜별 아카이브
- `.github/workflows/daily-news-update.yml` — 매일 10:00 KST 자동 실행
- `scripts/fetch_and_generate.py` — 뉴스 페치 + HTML 생성 스크립트

## 에이전트 구성

| 팀원 | 파일 | 역할 | 주요 출력 |
|------|------|------|----------|
| `live-schema-explorer` | `.claude/agents/live-schema-explorer.md` | 소스 레포 스키마 파악 | `_workspace/01_schema_contract.json` |
| `live-site-designer` | `.claude/agents/live-site-designer.md` | HTML/CSS/JS 템플릿 생성 | `docs/index.html`, `docs/assets/*` |
| `live-workflow-builder` | `.claude/agents/live-workflow-builder.md` | GitHub Actions + Python 스크립트 | `.github/workflows/*`, `scripts/*` |
| `live-qa-validator` | `.claude/agents/live-qa-validator.md` | 전체 설정 검증 | `_workspace/06_qa_report.md` |

## 워크플로우

### Phase 1: 준비

1. `_workspace/` 디렉토리 생성 (중간 산출물 저장소)
2. `docs/`, `docs/assets/`, `docs/archive/`, `scripts/`, `.github/workflows/` 디렉토리 생성
3. 사용자에게 시작 알림

```bash
mkdir -p _workspace docs/assets docs/archive scripts .github/workflows
```

### Phase 2: 팀 구성

팀 생성 (3명 — QA는 Phase 4에서 별도 실행):

```
TeamCreate(
  team_name: "live-artifact-team",
  members: [
    {
      name: "live-schema-explorer",
      agent_type: "live-schema-explorer",
      model: "opus",
      prompt: """
        당신은 live-schema-explorer입니다.
        tigerjk9의 3개 뉴스 레포(Auto-Edu-news-Collector, Auto-AI-Edu-Paper-Curator,
        Auto-AI-Tech-news-Collector)를 gh CLI로 탐색하여 데이터 스키마를 파악하세요.
        결과를 _workspace/01_schema_contract.json에 저장한 뒤,
        live-site-designer와 live-workflow-builder에게 SendMessage로 완료를 알리세요.
        참조: .claude/agents/live-schema-explorer.md
      """
    },
    {
      name: "live-site-designer",
      agent_type: "live-site-designer",
      model: "opus",
      prompt: """
        당신은 live-site-designer입니다.
        live-schema-explorer로부터 스키마 완료 알림을 받으면
        _workspace/01_schema_contract.json을 읽고 HTML/CSS/JS 템플릿을 생성하세요.
        디자인 명세: .claude/skills/live-artifact-setup/references/site-design-spec.md
        완료 후 live-workflow-builder에게 플레이스홀더 명세(_workspace/02_html_template.html) 완료를 알리세요.
        참조: .claude/agents/live-site-designer.md
      """
    },
    {
      name: "live-workflow-builder",
      agent_type: "live-workflow-builder",
      model: "opus",
      prompt: """
        당신은 live-workflow-builder입니다.
        live-schema-explorer로부터 스키마 완료 알림을 받으면 스키마를 읽고,
        live-site-designer로부터 HTML 템플릿 완료 알림을 받으면 플레이스홀더 명세도 읽어서
        GitHub Actions 워크플로우와 Python 스크립트를 생성하세요.
        데이터 접근 패턴: .claude/skills/live-artifact-setup/references/data-access-patterns.md
        완료 후 리더(orchestrator)에게 SendMessage로 완료를 알리세요.
        참조: .claude/agents/live-workflow-builder.md
      """
    }
  ]
)
```

### Phase 3: 작업 등록

```
TaskCreate(tasks: [
  {
    title: "소스 레포 스키마 탐색",
    description: "3개 GitHub 레포의 뉴스 데이터 포맷을 파악하고 _workspace/01_schema_contract.json 생성",
    assignee: "live-schema-explorer"
  },
  {
    title: "HTML/CSS/JS 템플릿 생성",
    description: "스키마 기반 뉴스 포털 템플릿. docs/index.html, docs/assets/style.css, docs/assets/app.js",
    assignee: "live-site-designer",
    depends_on: ["소스 레포 스키마 탐색"]
  },
  {
    title: "GitHub Actions 워크플로우 생성",
    description: "일일 10:00 KST 자동 실행 워크플로우. .github/workflows/daily-news-update.yml",
    assignee: "live-workflow-builder",
    depends_on: ["소스 레포 스키마 탐색"]
  },
  {
    title: "Python 페치 스크립트 생성",
    description: "스키마 기반 뉴스 페치 + HTML 생성 스크립트. scripts/fetch_and_generate.py",
    assignee: "live-workflow-builder",
    depends_on: ["소스 레포 스키마 탐색", "HTML/CSS/JS 템플릿 생성"]
  }
])
```

### Phase 4: 팀 실행 모니터링

팀원들이 자체 조율하며 작업을 수행한다. 리더는 모니터링만 한다.

**통신 흐름:**
```
live-schema-explorer → (완료) → SendMessage → live-site-designer
                                             → live-workflow-builder
live-site-designer   → (완료) → SendMessage → live-workflow-builder
live-workflow-builder → (완료) → SendMessage → 리더(orchestrator)
```

**리더 개입 조건:**
- 팀원이 30분 이상 응답 없음 → SendMessage로 상태 확인
- 팀원이 막혔다고 알림 → 구체적 지시 또는 작업 재할당
- GitHub 인증 실패 알림 → 사용자에게 `NEWS_GITHUB_TOKEN` 설정 요청

### Phase 5: QA 검증

모든 팀원 작업 완료 후, 팀 정리 전에 QA를 실행한다.

```
# 팀 정리
TeamDelete(team_name: "live-artifact-team")

# QA 서브 에이전트 실행
Agent(
  subagent_type: "live-qa-validator",
  model: "opus",
  prompt: """
    프로젝트 전체 파일을 검증하고 _workspace/06_qa_report.md를 생성하세요.
    간단한 문제는 직접 수정하고, 수동 조치가 필요한 항목은 보고서에 명시하세요.
    참조: .claude/agents/live-qa-validator.md
  """
)
```

### Phase 6: 완료 보고

QA 보고서(`_workspace/06_qa_report.md`)를 읽고 사용자에게 요약 보고:

```
✅ Live Artifact 구축 완료

생성된 파일:
- .github/workflows/daily-news-update.yml (매일 10:00 KST 실행)
- scripts/fetch_and_generate.py
- docs/index.html (뉴스 포털 메인)
- docs/assets/style.css, app.js

QA 결과: N/N 통과

다음 단계:
1. NEWS_GITHUB_TOKEN 시크릿 설정 (scripts/setup_secrets.md 참조)
2. GitHub Pages 활성화 (Settings → Pages → Branch: main, Folder: /docs)
3. 첫 실행: Actions 탭 → Daily News Update → Run workflow
```

## 데이터 흐름

```
[리더]
  └─ TeamCreate ─┬─ [live-schema-explorer]
                 │    └─ 01_schema_contract.json
                 │         ├──→ [live-site-designer]
                 │         │       └─ docs/index.html
                 │         │          docs/assets/*
                 │         │          02_html_template.html
                 │         │               └──→ [live-workflow-builder]
                 │         └──→ [live-workflow-builder]
                 │                 └─ .github/workflows/*
                 │                    scripts/*
                 │
  └─ TeamDelete
  └─ Agent(live-qa-validator)
       └─ 06_qa_report.md
  └─ 사용자 보고
```

## 에러 핸들링

| 상황 | 전략 |
|------|------|
| GitHub 인증 실패 | 사용자에게 토큰 설정 요청 후 schema-explorer는 fallback 스키마로 계속 |
| 팀원 1명 실패 | SendMessage로 상태 확인 → 재시작 시도 → 실패 시 보고서에 누락 명시 |
| site-designer/workflow-builder 순서 충돌 | depends_on 태스크 의존성으로 자동 조율 |
| QA에서 치명적 문제 발견 | 해당 에이전트를 서브 에이전트로 재실행하여 수정 |

## 테스트 시나리오

### 정상 흐름

1. `/live-artifact-setup` 실행
2. Phase 1: 디렉토리 구조 생성
3. Phase 2-3: 3명 팀 구성 + 4개 작업 등록
4. Phase 4: schema-explorer 완료 → site-designer + workflow-builder 병렬 진행
5. Phase 5: QA 검증 (N/N 통과)
6. Phase 6: 사용자에게 완료 보고 + 다음 단계 안내
7. 예상 소요 시간: 15~25분

### 에러 흐름

1. Phase 4에서 GitHub 인증 실패 (schema-explorer)
2. schema-explorer가 리더에게 알림: "AUTH_REQUIRED"
3. 리더가 사용자에게: "NEWS_GITHUB_TOKEN 환경변수 또는 시크릿 설정 필요"
4. schema-explorer는 fallback 스키마(title/url/summary)로 계속
5. site-designer와 workflow-builder는 fallback 스키마로 진행
6. QA 보고서에 "실제 스키마 미확인 — 첫 실행 후 스크립트 조정 필요" 명시

## 참조 레퍼런스

- 데이터 접근 패턴: `references/data-access-patterns.md`
- 사이트 디자인 명세: `references/site-design-spec.md`
