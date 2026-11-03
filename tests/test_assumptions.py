"""미래 계산 가정값(data/assumptions.json)이 공시 통계와 맞는지: 근거가 있는 값은 범주 통계로 다시 계산해 대조한다."""

import json
from pathlib import Path

import pytest

from ontology.products import load_products, rate_benchmark

ROOT = Path(__file__).resolve().parents[1]
A = json.loads((ROOT / "data/assumptions.json").read_text(encoding="utf-8"))


@pytest.mark.skipif(not load_products("deposit"), reason="공시 상품 데이터 없음")
def test_benchmarked_returns_match_disclosure():
    rows = [r for r in A["returns"] if "benchmark" in r]
    assert [r["id"] for r in rows] == ["safe"]
    for r in rows:
        bm = rate_benchmark(**r["benchmark"])
        assert bm and bm["n_products"] >= 20
        assert r["expected_return"] == round(bm["median"], 1)  # 값은 통계를 0.1%p로 반올림
        assert f"{bm['median']:g}%" in r["source"] and f"{bm['n_products']}개" in r["source"]
        y, m = bm["as_of"][-1][:4], int(bm["as_of"][-1][4:])
        assert f"{y}년 {m}월" in r["source"]  # 기준월을 화면에 보인다


def test_every_return_has_source_and_order():
    rs = A["returns"]
    assert all(r.get("source") for r in rs)
    assert [r["expected_return"] for r in rs] == sorted(r["expected_return"] for r in rs)  # 원금 보장 → 주식 위주 순서 유지
