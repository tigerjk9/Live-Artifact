# 데이터 접근 패턴 레퍼런스

GitHub API를 통해 소스 레포의 뉴스 데이터를 페치하는 패턴 모음.
`live-workflow-builder`와 `live-schema-explorer`가 참조한다.

---

## 목차

1. [GitHub API 인증](#1-github-api-인증)
2. [파일 목록 조회](#2-파일-목록-조회)
3. [파일 내용 페치](#3-파일-내용-페치)
4. [날짜 기반 파일 탐색](#4-날짜-기반-파일-탐색)
5. [에러 처리 패턴](#5-에러-처리-패턴)
6. [시크릿 설정 가이드](#6-시크릿-설정-가이드)

---

## 1. GitHub API 인증

### Actions 환경에서

```python
import os, requests

TOKEN = os.environ.get("NEWS_TOKEN", "")
HEADERS = {
    "Authorization": f"token {TOKEN}",
    "Accept": "application/vnd.github.v3+json",
} if TOKEN else {}
```

토큰이 없으면 public 레포에만 접근 가능 (rate limit 60 req/hour).
private 레포는 `NEWS_GITHUB_TOKEN` 시크릿 필수.

### gh CLI 환경에서 (schema-explorer)

```bash
# 인증 상태 확인
gh auth status

# 인증된 경우 API 호출
gh api repos/tigerjk9/Auto-Edu-news-Collector/contents

# PAT으로 직접 인증
echo "$NEWS_GITHUB_TOKEN" | gh auth login --with-token
```

---

## 2. 파일 목록 조회

```python
def list_dir(repo: str, path: str = "") -> list[dict]:
    url = f"https://api.github.com/repos/{repo}/contents/{path}"
    resp = requests.get(url, headers=HEADERS, timeout=10)
    resp.raise_for_status()
    return resp.json()  # list of {name, type, path, sha, ...}
```

날짜 파일 필터링:
```python
import re
DATE_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}")

files = list_dir("tigerjk9/Auto-Edu-news-Collector", "data")
date_files = [f for f in files if DATE_PATTERN.search(f["name"])]
date_files.sort(key=lambda x: x["name"], reverse=True)  # 최신 순
latest = date_files[0] if date_files else None
```

---

## 3. 파일 내용 페치

### Base64 디코딩 방식 (소용량 파일)

```python
import base64, json

def fetch_file_content(repo: str, path: str) -> str | None:
    url = f"https://api.github.com/repos/{repo}/contents/{path}"
    resp = requests.get(url, headers=HEADERS, timeout=10)
    if resp.status_code != 200:
        return None
    data = resp.json()
    # content는 base64 인코딩됨 (줄바꿈 포함)
    return base64.b64decode(data["content"].replace("\n", "")).decode("utf-8")
```

### Raw URL 방식 (대용량 파일, 더 빠름)

```python
def fetch_raw(repo: str, path: str, branch: str = "main") -> str | None:
    url = f"https://raw.githubusercontent.com/{repo}/{branch}/{path}"
    resp = requests.get(url, headers=HEADERS, timeout=15)
    if resp.status_code != 200:
        return None
    return resp.text
```

private 레포의 raw 접근은 Authorization 헤더 필요.

---

## 4. 날짜 기반 파일 탐색

### 오늘 날짜 파일 페치

```python
from datetime import date

def fetch_today_news(repo: str, file_pattern: str, token: str) -> str | None:
    today = date.today().isoformat()  # "2025-05-11"
    path = file_pattern.replace("{YYYY-MM-DD}", today)
    return fetch_raw(repo, path)

# file_pattern 예시:
# "data/{YYYY-MM-DD}.json"  →  "data/2025-05-11.json"
# "news/{YYYY-MM-DD}.md"   →  "news/2025-05-11.md"
# "{YYYY-MM-DD}.json"       →  "2025-05-11.json"
```

### 스키마 계약서에서 패턴 읽기

```python
import json

with open("_workspace/01_schema_contract.json") as f:
    schema = json.load(f)

edu_pattern = schema["repos"]["edu-news"]["file_pattern"]
# → "data/{YYYY-MM-DD}.json"
```

---

## 5. 에러 처리 패턴

각 소스를 독립적으로 처리해야 한다. 하나 실패해도 나머지 두 개는 계속 진행.

```python
def safe_fetch_source(key: str, config: dict) -> list[dict]:
    try:
        raw = fetch_today_news(
            config["repo"],
            config["file_pattern"],
            TOKEN
        )
        if raw is None:
            print(f"[WARN] {key}: 오늘 파일 없음")
            return []
        return parse_items(raw, config["schema"])
    except requests.Timeout:
        print(f"[ERROR] {key}: 타임아웃")
        return []
    except Exception as e:
        print(f"[ERROR] {key}: {e}")
        return []
```

빈 리스트 반환 시 `render_cards()`가 "오늘 데이터 없음" 카드를 렌더링한다.

---

## 6. 시크릿 설정 가이드

### PAT 생성

1. GitHub → 우측 상단 프로필 → Settings
2. Developer settings → Personal access tokens → Tokens (classic)
3. **Generate new token (classic)**
4. Note: "Live Artifact News Fetcher"
5. Expiration: No expiration 또는 1년
6. Scopes: **`repo`** 체크 (private 레포 read 포함)
7. Generate token → 토큰 복사

### 시크릿 등록

1. Live Artifact 레포 → Settings → Secrets and variables → Actions
2. **New repository secret**
3. Name: `NEWS_GITHUB_TOKEN`
4. Secret: 위에서 복사한 토큰
5. Add secret

### 확인

Actions 탭 → workflow_dispatch로 수동 실행 → 로그에서 "Fetch news and generate HTML" 단계 확인.
