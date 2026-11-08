"""부동산원 집값 스냅샷(knowledge/sources/S_reb_house_price_*.json) 검사. 원본 xlsx가 있으면(knowledge/raw/) 숫자를 다시 대조한다."""

import hashlib
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SNAP = ROOT / "knowledge" / "sources" / "S_reb_house_price_202609.json"


def _snap():
    return json.loads(SNAP.read_text(encoding="utf-8"))


def test_snapshot_shape_and_known_values():
    d = _snap()
    assert d["month"] == "2026-09" and d["unit"].startswith("만원")
    by = {r["code"]: r for r in d["regions"]}
    # 원본 통계표 28(아파트) 전국 행: 중위 매매가격 329,000천원, 평균 523,246.36…천원
    assert by["00000"]["values"]["apt"]["median_sale"] == 32900.0
    assert by["00000"]["values"]["apt"]["mean_sale"] == 52324.6
    assert sum(r["level"] == "sido" for r in d["regions"]) == 16
    for r in d["regions"]:
        for t, v in r["values"].items():
            assert all(x > 0 for x in v.values()), (r["code"], t)


def test_snapshot_matches_raw_file_if_present():
    d = _snap()
    raw = ROOT / "knowledge" / "raw" / d["raw_file"]
    if not raw.exists():
        pytest.skip("원본 xlsx가 없어요(knowledge/raw/, git 제외). tools/fetch_reb_prices.py로 받으면 대조해요")
    assert hashlib.sha256(raw.read_bytes()).hexdigest() == d["raw_sha256"]
    from tools.fetch_reb_prices import extract
    assert extract(raw)["regions"] == d["regions"]
