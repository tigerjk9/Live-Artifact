# GitHub Secrets 설정 가이드

이 문서는 Daily News Update 워크플로우가 private 레포지토리에서 데이터를 읽기 위해
필요한 GitHub Personal Access Token(PAT) 생성 및 시크릿 등록 방법을 안내합니다.

---

## 1. Personal Access Token (Classic) 생성

1. GitHub에 로그인한 뒤 오른쪽 상단 프로필 아이콘 클릭
2. **Settings** 선택
3. 왼쪽 사이드바 하단 **Developer settings** 클릭
4. **Personal access tokens** > **Tokens (classic)** 선택
5. **Generate new token** > **Generate new token (classic)** 클릭
6. 다음 항목 입력:
   - **Note**: `Live Artifact News Token` (식별용 이름)
   - **Expiration**: 90일 또는 No expiration (보안 정책에 맞게 선택)
   - **Scopes**: `repo` 체크 (private 레포 읽기 권한 포함)
7. 하단 **Generate token** 클릭
8. 생성된 토큰 값을 안전한 곳에 복사 (페이지를 벗어나면 다시 볼 수 없음)

---

## 2. Live Artifact 레포에 시크릿 등록

1. `tigerjk9/Live-Artifact` 레포지토리 페이지로 이동
2. 상단 탭에서 **Settings** 클릭
3. 왼쪽 사이드바 **Security** > **Secrets and variables** > **Actions** 선택
4. **New repository secret** 클릭
5. 다음 항목 입력:
   - **Name**: `NEWS_GITHUB_TOKEN`
   - **Secret**: 위에서 복사한 PAT 값
6. **Add secret** 클릭

---

## 3. 토큰 접근 대상 레포지토리

이 토큰은 아래 3개 private 레포지토리에서 데이터를 읽는 데 사용됩니다:

| 레포지토리 | 설명 |
|-----------|------|
| `tigerjk9/Auto-Edu-news-Collector` | 교육 뉴스 JSON 데이터 |
| `tigerjk9/Auto-AI-Edu-Paper-Curator` | AI 교육 논문 JSON 데이터 |
| `tigerjk9/Auto-AI-Tech-news-Collector` | AI 기술 뉴스 JSON 데이터 |

---

## 4. 워크플로우 수동 실행 테스트

시크릿 등록 후 아래 절차로 워크플로우가 정상 동작하는지 확인합니다:

1. `tigerjk9/Live-Artifact` 레포지토리 > **Actions** 탭
2. 왼쪽 목록에서 **Daily News Update** 선택
3. **Run workflow** > **Run workflow** 클릭
4. 실행 로그에서 각 소스 페치 결과 확인
5. `docs/archive/` 폴더에 오늘 날짜 HTML 파일이 생성되었는지 확인

---

## 5. 보안 주의사항

- PAT는 절대 소스 코드에 하드코딩하지 않습니다.
- 토큰을 분실하면 GitHub에서 새 토큰을 재발급하고 시크릿을 업데이트합니다.
- 정기적으로 토큰 만료일을 확인하고 갱신합니다.
- 토큰에는 최소 필요 권한(`repo`)만 부여합니다.
