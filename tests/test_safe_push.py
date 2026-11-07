"""safe_push.sh 충돌 복구 경로가 보존할 원천 JSON을 고르는 정규식."""

import os
import re

import pytest

SCRIPT = os.path.join(os.path.dirname(__file__), "..", "scripts", "safe_push.sh")


def keep_pattern() -> re.Pattern:
    with open(SCRIPT, encoding="utf-8") as f:
        line = next(l for l in f if l.startswith("KEEP="))
    # grep -E 패턴 — 이 정도 ERE는 파이썬 re와 문법이 같다
    return re.compile(re.search(r"grep -E '([^']+)'", line).group(1))


@pytest.mark.parametrize("path", [
    "docs/data/2026-10-03.json",
    "docs/data/weekly/2026-W44.json",
    "docs/data/weekly/2025-W46.json",
])
def test_keeps_source_records(path):
    assert keep_pattern().search(path)


@pytest.mark.parametrize("path", [
    "docs/data/index.json",
    "docs/data/health.json",
    "docs/data/entities.json",
    "docs/data/search/2026-10.json",
    "docs/data/search/index.json",
    "docs/data/entity/openai.json",
])
def test_skips_derived_files(path):
    assert not keep_pattern().search(path)
