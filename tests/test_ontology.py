"""온톨로지 탐색 테스트. 기대 결과는 기획안 10·15쪽(docs/08_온톨로지.md 5절)."""

import json
from pathlib import Path

import pytest

from ontology import load, recommend, vocab_ids

ROOT = Path(__file__).resolve().parents[1]
GOLD = json.loads((ROOT / "data/golden/ontology_mappings.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("scenario", ["newly", "elder"])
def test_recommendations_match_plan(scenario):
    g = GOLD[scenario]
    recs = recommend(g["mappings"], g["commitments"])
    got: dict[str, list] = {}
    for r in recs:
        got.setdefault(r["commitment_id"], []).append(r["product_type_id"])
    assert got == g["expect"]


def test_principal_protection_excludes_fund_with_reason():
    g = GOLD["newly"]
    rec = next(r for r in recommend(g["mappings"], g["commitments"]) if r["commitment_id"] == "c2")
    ex = {e["product_type_id"]: e["reason"] for e in rec["excluded"]}
    assert ex["P_balanced_fund"] == "원금 보장이 아니라서"
    assert "P_parking_account" in ex  # 기간을 정해 모으는 상품이 아님
    assert ["N_leave_fund", "satisfiedBy", "P_installment_savings"] in rec["path"]
    assert rec["reason_text"].startswith("약속 2 '휴직 준비금")


def test_vocab_is_consistent():
    o = load()
    needs, cons = vocab_ids()
    for n in o["needs"].values():
        for t in n["satisfied_by"]:
            assert t in o["types"], t
    assert set(o["rules"]) <= cons
    # 상품 유형에 특정 금융회사 이름을 쓰지 않는다(기획안 15쪽)
    for t in o["types"].values():
        for bank in ("가온", "나래", "다솜", "라움"):
            assert bank not in t["label"]


def test_goal_need_reason_text():
    g = GOLD["newly"]
    rec = next(r for r in recommend(g["mappings"], g["commitments"]) if r["commitment_id"] == "goal")
    assert rec["reason_text"].startswith("함께 정한 목표")
