"""은행연합회 중도상환수수료율 표 → 은행 신용대출 노드(ontology/kfb.py, 2026-11-17). 정답은 원문 표를 사람이 읽고 적은 값(G7)."""

from ontology import kfb
from ontology.products import load_products


def _banks():
    return {p["provider"]: p for p in load_products("credit_loan") if p["group"] == "020000"}


def test_bank_prepay_matches_table_and_stays_unconfirmed():
    b = _banks()
    kb = b["국민은행"]["terms"]["prepay"]  # 원문 KB국민은행 신용: 가계 고정 0.18% / 변동 0.11%
    assert (kb["fixed_pct"], kb["variable_pct"]) == (0.18, 0.11)
    sh = b["신한은행"]["terms"]["prepay"]  # 0.17% / 0.13%
    assert (sh["fixed_pct"], sh["variable_pct"]) == (0.17, 0.13)
    assert b["토스뱅크 주식회사"]["terms"]["prepay"]["fixed_pct"] == 0.0  # 원문 0.00%(수수료 없음 표시가 아니라 요율 0%)
    assert "erly_rpay_fee" not in b["한국씨티은행"]["texts"]  # 원문 가계 신용 칸이 '-' → 짐작하지 않는다
    for p in b.values():
        if p["texts"].get("erly_rpay_fee"):
            assert p["terms"]["status"] == "needs_check" and any("은행 평균" in i for i in p["terms"]["issues"])
            assert all(q in p["texts"]["erly_rpay_fee"] for q in p["terms"]["prepay"]["quotes"])


def test_all_19_banks_map_to_finlife_names():
    assert len(kfb.credit_prepay()) == 19 and set(kfb.credit_prepay()) <= {p["provider"] for p in _banks().values()}
