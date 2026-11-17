"""저축은행중앙회 표 → 저축은행 신용대출 노드(ontology/fsb.py, 2026-11-17).

정답은 원문 표(knowledge/sources/S_fsb_*.json)의 칸을 사람이 읽고 적은 값이다(docs/06 5절 G7).
"""

import json
from pathlib import Path

from llm import family as F
from ontology import fsb
from ontology.fit import compare
from ontology.products import load_products

ROOT = Path(__file__).resolve().parents[1]
FAM = F.validate(F.preset("newly"))


def _nodes():
    return [p for p in load_products("credit_loan") if p["group"] == "030300"]


def test_all_products_in_table_become_nodes_once():
    grid = json.loads((ROOT / "knowledge/sources/S_fsb_credit_loan_202611.json").read_text(encoding="utf-8"))["grid"]
    n_rows = sum(1 for r in grid[3:] if r[0] and r[2] == "취급비중(%)")  # 상품마다 첫 줄이 '취급비중(%)'
    nodes = _nodes()
    assert len(nodes) == n_rows == 129
    assert len({p["product_id"] for p in nodes}) == n_rows
    assert all(p["source_id"] == "S_fsb_credit_loan_202611" for p in nodes)  # 금감원의 회사별 한 줄(36줄)은 노드로 안 쓴다


def test_rates_copied_as_is_and_blank_stays_none():
    by_name = {(p["provider_code"], p["name"]): p for p in _nodes()}
    a = by_name[("fsb:DB", "DreamBig 신용대출")]  # 원문: 평균금리 11.24 / 12.12 / 12.56 / 13.33 / - / - / - / - / 합계 12.31
    assert a["rates"]["by_band"] == {"900+": 11.24, "801-900": 12.12, "701-800": 12.56, "601-700": 13.33,
                                     "501-600": None, "401-500": None, "301-400": None, "300-": None}
    assert a["rates"]["avg"] == 12.31
    assert "한도 최대 6천만" in a["texts"]["intro"] and a["texts"]["dly_rate"].startswith("약정금리+3%")  # 원문 글 그대로
    b = by_name[("fsb:BNK", "BNKSB중금리생활안정")]  # 801~900점 구간만 값이 있음
    assert b["rates"]["by_band"]["801-900"] == 7.88 and b["rates"]["by_band"]["900+"] is None


def test_prepay_rates_match_table_and_stay_unconfirmed():
    by = {p["provider_code"]: p for p in _nodes()}
    bnk = by["fsb:BNK"]["terms"]["prepay"]  # 원문 BNK 신용대출 가계: 변동 0.42% / 고정 1.68%
    assert (bnk["variable_pct"], bnk["fixed_pct"]) == (0.42, 1.68)
    sam = by["fsb:삼호"]["terms"]["prepay"]  # 변동은 '-'(그 유형의 신용대출 없음), 고정 1.15%
    assert sam["fixed_pct"] == 1.15
    hanseong = by["fsb:한성"]  # 표에 값이 없는 저축은행은 짐작하지 않는다
    assert hanseong["terms"]["prepay"]["fixed_pct"] is None and "erly_rpay_fee" not in hanseong["texts"]
    for p in _nodes():  # 상품별 약정이 아니라 저축은행 평균이고 한도는 공시에 없으므로 확인 필요를 지킨다
        assert p["terms"]["status"] == "needs_check" and "한도가 공시에 없음" in p["terms"]["issues"]
        if p["texts"].get("erly_rpay_fee"):
            assert any("저축은행 평균" in i for i in p["terms"]["issues"])


def test_prepay_text_quotes_are_in_text():
    for p in _nodes():
        for q in p["terms"]["prepay"]["quotes"]:
            assert q in p["texts"]["erly_rpay_fee"]


def test_company_names_match_finlife_naming():
    assert fsb.provider_name("DB") == "디비저축은행" and fsb.provider_name("KB") == "KB저축은행"
    finlife = {"디비저축은행", "엔에이치저축은행", "MS저축은행", "SBI저축은행", "키움예스저축은행", "KB저축은행", "OK저축은행"}
    assert {fsb.provider_name(c) for c in ("DB", "NH", "엠에스", "교보SBI", "키움YES", "KB", "OK")} == finlife


def test_compare_uses_fsb_nodes_and_prepay_fee():
    res = compare(FAM, "N_debt_repayment", category="credit_loan", member_id="m0", amount=2000, months=36, band="801-900", prepay_month=12)
    saving_bank = [x for x in res["items"] if x["product_id"].startswith("PRD_credit_loan_fsb_")]
    assert saving_bank
    x = next(i for i in saving_bank if i["provider"] == "BNK저축은행" and i["name"] == "BNKSB중금리생활안정")
    assert x["my_rate"] == 7.88 and x["prepay_fee"] is not None and x["prepay_fee"] > 0
    assert "한도가 공시에 없음" in x["checks"]
