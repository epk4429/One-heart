"""대출 공시 → 한도·중도상환 수수료 규칙(ontology/loans.py), 대출 계산(engine/product_math.py), 대출 비교(ontology/fit.py).

파싱 정답은 공시 원문(2026-10, knowledge/sources)을 사람이 읽고 적은 것이다(docs/12 9절 G7).
"""

import json

import pytest

from engine.product_math import deposit_interest, loan_cost, saving_interest
from llm import family as F
from ontology import loans as L
from ontology.fit import compare, won_k
from server.app import dispatch

FAM = F.validate(F.preset("newly"))


@pytest.mark.parametrize("text,ratio,of,max_manwon,none", [
    ("LTV 70%", 70, "home", None, False),                                            # 우리아파트론
    ("LTV 30% ~ 70% \n(지역별 차등 적용)", 70, "home", None, False),
    ("최대4.44억원", None, None, 44400, False),                                       # 우리전세론(주택금융보증)
    ("500백만원", None, None, 50000, False),
    ("4억 44백만원", None, None, 44400, False),
    ("임차보증금의 80% 범위내 최고 444백만원", 80, "deposit", 44400, False),
    ("- 아파트 시세(KB부동산, 한국부동산원)의 최대 70%, 최대 8억원 까지", 70, "home", 80000, False),
    ("별도 한도 없음", None, None, None, True),
])
def test_parse_limit(text, ratio, of, max_manwon, none):
    r = L.parse_limit(text)
    assert (r["ratio_pct"], r["ratio_of"], r["max_manwon"], r["none"]) == (ratio, of, max_manwon, none)
    assert r["status"] != "needs_check" and all(q in text for q in r["quotes"])


def test_parse_limit_unreadable_needs_check():
    assert L.parse_limit("내부 대출 심사기준에 따름")["status"] == "needs_check"
    assert L.parse_limit("")["status"] == "needs_check"


@pytest.mark.parametrize("text,fixed,variable,free_years,status", [
    ("- 고정금리 : 중도상환대출금×0.71%×잔존기간÷대출기간\n- 변동금리 : 중도상환대출금×0.95%×잔존기간÷대출기간", 0.71, 0.95, None, "verified"),
    ("중도상환대출금액×(고정금리:0.57, 변동금리:0.47)%×(대출잔여일수 ÷ 3년)", 0.57, 0.47, 3, "verified"),
    ("상환금액×수수료율(변동0.27%, 고정0.04%)×대출잔여일수÷대출기간(최장 3년)", 0.04, 0.27, 3, "verified"),
    ("중도상환금액×0.9%×대출잔여일수/대출기간", 0.9, 0.9, None, "verified"),
    ("중도상환금액×1.3%×대출잔여일수/대출기간 \n3년경과시 면제", 1.3, 1.3, 3, "verified"),
    ("없음", 0.0, 0.0, None, "verified"),
    # 담보 종류별로 요율이 여럿 → 가장 큰 값만 '최대'로, 확인 필요
    ("중도상환금액×수수료율×대출잔여일수/대출기간 \n수수료율 \n- 부동산 및 동산 담보: 0.61% \n- 보증서 및 기타 담보: 0.28% \n- 신용대출: 0.50%", 0.61, 0.61, None, "needs_check"),
])
def test_parse_prepay(text, fixed, variable, free_years, status):
    r = L.parse_prepay(text)
    assert (r["fixed_pct"], r["variable_pct"], r["free_after_years"], r["status"]) == (fixed, variable, free_years, status)
    assert all(q in text for q in r["quotes"])


def test_loan_math_matches_hand_calculation():
    # 1억원(10,000만원), 연 6%, 12개월
    assert loan_cost(10000, 6, 12, "equal_payment")["total_interest"] == 327.97   # 월 860.66 × 12 − 10,000
    assert loan_cost(10000, 6, 12, "equal_principal")["total_interest"] == 325.0  # 10,000 × 0.005 × 13/2
    assert loan_cost(10000, 6, 12, "bullet")["total_interest"] == 600.0
    early = loan_cost(10000, 6, 12, "equal_principal", prepay_month=6)
    assert (early["total_interest"], early["remaining_at_prepay"]) == (237.5, 5000.0)  # 0.005 × (10,000+…+5,833.33)
    assert round(saving_interest(60, 12, 4.1), 2) == 15.99 and deposit_interest(1000, 12, 3.5) == 35.0


def test_won_k_large_amounts():
    assert won_k(16481.34) == "1억 6,481만 3천원" and won_k(0.4) == "4천원" and won_k(10000) == "1억원"


def test_mortgage_limit_by_home_price_orders_last():
    res = compare(FAM, "N_home_purchase_prep", category="mortgage", member_id="m0", amount=30000, months=360, home_price=40000)
    over = [x for x in res["items"] if x["limit_ok"] is False]  # 집값 4억의 LTV 70% = 2.8억 < 3억
    assert over and all(x["limit_manwon"] < 30000 for x in over)
    first_over = res["items"].index(over[0])
    assert all(x["limit_ok"] is not False for x in res["items"][:first_over])


def test_rent_prepay_fee_follows_formula():
    res = compare(FAM, "N_home_purchase_prep", category="rent_loan", member_id="m0", amount=15000, months=24, repay="bullet",
                  deposit_amount=25000, prepay_month=12)
    x = next(i for i in res["items"] if i["name"] == "우리전세론(주택금융보증)")
    # 변동 0.35%, 남은 기간 비례: 15,000 × 0.35% × (24−12)/24 = 26.25만원
    assert x["rate_type"] == "variable" and x["prepay_fee"] == 26.25
    assert x["total_cost"] == round(x["cost"]["total_interest"] + 26.25, 2)


def test_business_loans_flag_region_and_eligibility_first():
    res = compare(FAM, "N_debt_repayment", category="busi_loan", member_id="m0", amount=5000, months=60)
    region = [x for x in res["items"] if any("지역 조건" in c for c in x["checks"])]
    assert region and any("순천시" in c for x in region for c in x["checks"])
    k = next(i for i, x in enumerate(res["items"]) if any(w in c for c in x["checks"] for w in ("지역 조건", "가입조건")))
    assert all(not any(w in c for c in x["checks"] for w in ("지역 조건", "가입조건")) for x in res["items"][:k])


def test_credit_loan_band_and_unknown_terms():
    res = compare(FAM, "N_debt_repayment", category="credit_loan", member_id="m0", amount=2000, months=36, band="801-900")
    x = res["items"][0]
    assert "한도가 공시에 없음" in x["checks"] and x["limit_ok"] is None  # 신용대출 공시에는 한도·수수료 항목이 없다
    assert "801~900점" in x["reasons"][1]


def test_loan_reasons_are_information():
    res = compare(FAM, "N_home_purchase_prep", category="mortgage", member_id="m0", amount=20000, months=360, home_price=40000)
    text = " ".join(t for x in res["items"] for t in x["reasons"] + [x.get("why_lower", "")])
    assert "추천" not in text and "원예요" not in text


def call(body):
    return dispatch("POST", "/api/products/fit", json.dumps(body).encode(), {}, "t")


def test_api_loans(monkeypatch):
    monkeypatch.delenv("VERCEL", raising=False)
    monkeypatch.delenv("REAL_PRODUCTS", raising=False)
    base = {"family": F.preset("newly"), "need_id": "N_home_purchase_prep", "member_id": "m0"}
    st, out = call({**base, "category": "mortgage", "amount": 20000, "months": 360, "home_price": 40000})
    assert st == 200 and out["items"] and out["category_label"] == "주택담보대출"
    assert call({**base, "category": "credit_loan", "band": "999"})[0] == 400
    assert call({**base, "category": "rent_loan", "repay": "monthly"})[0] == 400
    assert call({**base, "category": "deposit", "amount": 5000, "term_months": 12})[1]["items"]
