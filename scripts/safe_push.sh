#!/usr/bin/env bash
# safe_push.sh — docs/ 변경을 커밋하고 push한다. rebase 충돌이 나면 "원천 데이터(JSON)만 보존 → 원격 기준으로 리셋 →
# 파생물(HTML·색인·피드·OG 메타) 재생성 → 재커밋"으로 복구한다.
#
# 왜: 생성 산출물(아카이브 HTML, index.json, feed.xml …)은 여러 워크플로우가 같은 파일을 다시 쓰므로
#     텍스트 병합이 불가능하다. 하지만 전부 docs/data/의 JSON에서 결정적으로 다시 만들 수 있으니,
#     충돌 때는 병합 대신 "데이터만 합치고 다시 만들기"가 맞다. (2026-11-02 weekly-backfill이 enrich와 겹쳐 실패)
#
# 사용: bash scripts/safe_push.sh "<commit message>"
set -euo pipefail
MSG="${1:-chore: update}"

git add docs/
if git diff --staged --quiet; then
  echo "[PUSH] 변경 없음"
  exit 0
fi
git commit -q -m "$MSG"

if git pull --rebase origin main; then
  git push
  echo "[PUSH] 완료"
  exit 0
fi

echo "::warning::rebase 충돌 — 원천 JSON만 보존하고 파생물을 다시 만든다"
git rebase --abort || true

# 우리 커밋(HEAD)이 바꾼 원천 데이터만 추린다: 날짜 레코드 · 주간 JSON. (index/search/entity 등 집계는 재생성 대상)
KEEP=$(git diff --name-only HEAD~1 HEAD -- 'docs/data/' | grep -E '^docs/data/([0-9]{4}-[0-9]{2}-[0-9]{2}|weekly/[0-9]{4}-W[0-9]{2})\.json$' || true)
TMP=$(mktemp -d)
for f in $KEEP; do
  mkdir -p "$TMP/$(dirname "$f")"
  git show "HEAD:$f" > "$TMP/$f"
done
echo "[PUSH] 보존 파일 $(echo "$KEEP" | grep -c . || true)개"

git fetch origin main
git reset -q --hard origin/main
for f in $KEEP; do
  mkdir -p "$(dirname "$f")"
  cp "$TMP/$f" "$f"
done

# 파생물 재생성 (Gemini 호출 없음, OG는 기존 파일 유지)
python scripts/fetch_and_generate.py --task rebuild --no-synthesis

git add docs/
if git diff --staged --quiet; then
  echo "[PUSH] 재생성 후 변경 없음"
  exit 0
fi
git commit -q -m "$MSG (충돌 복구: 데이터 보존 후 재생성)"
git pull --rebase origin main
git push
echo "[PUSH] 완료 (복구 경로)"
