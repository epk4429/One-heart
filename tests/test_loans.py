"""대출 공시 → 한도·중도상환 수수료 규칙(ontology/loans.py), 대출 계산(engine/product_math.py), 대출 비교(ontology/fit.py).

파싱 정답은 공시 원문(2026-10, knowledge/sources)을 사람이 읽고 적은 것이다(docs/06 5절 G7).
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


def test_monthly_flow_excludes_first_month_lump_repayment():
    """첫 달에 예금으로 한 번에 갚는 돈(일시 상환)은 '매달 모이는 돈'을 마이너스로 만들면 안 된다(2026-11-15 형님 지적: -1,428만원)."""
    import copy
    from engine import simulate

    def req(prepay):
        return {"scenario_id": "t", "horizon_months": 60, "start": {"goal_pool": 2000, "pool_label": "예금",
                "aux_accounts": [], "loans": [{"id": "L1", "label": "신용대출", "balance": 3000, "rate": 6, "kind": "amortizing", "payment": 60}]},
                "goal": {"type": "debt_free", "label": "대출 다 갚기", "target_amount": 0},
                "options": [{"option_id": "A", "label": "A", "expected_return": 3.3, "volatility": 0, "return_assumption_id": "",
                             "cashflows": [{"label": "월급", "amount": 400, "category": "income"},
                                           {"label": "생활비", "amount": -200, "category": "expense"}],
                             "events": [], "lump_sums": [], "aux_changes": [], "extra_payments": [],
                             "loan_prepayments": prepay}],
                "inflation": 0, "member_context": {"base_age": 35}, "range": {"paths": 0, "seed": 1}}
    plain = simulate(req([]), include_monthly=False)["results"][0]
    lump = simulate(req([{"loan_id": "L1", "month": 1, "amount": 1500}]), include_monthly=False)["results"][0]
    assert plain["monthly_flow"] == lump["monthly_flow"] == 140.0  # 400 − 200 − 상환 60
    detail = next(b["detail"] for b in lump["basis"] if b["key"] == "monthly_flow")
    assert "대출 상환 60" in detail
    assert lump["goal_hit_month"] < plain["goal_hit_month"]  # 일시 상환은 갚는 때에는 그대로 반영된다


def test_debt_free_ignores_interest_only_lease_loan():
    """전세대출(이자만 내는 대출)이 있어도 '대출 다 갚기'는 갚아 나가는 대출만 본다(2026-11-15). 예전에는 전세대출 원금이 안 줄어 영원히 '다 갚는 때'가 없었다."""
    from engine import simulate
    lease = {"id": "S", "label": "전세대출", "balance": 15000, "rate": 4.1, "kind": "interest_only", "payment": 0, "in_pool": False}
    credit = {"id": "C", "label": "신용대출", "balance": 3000, "rate": 6, "kind": "amortizing", "payment": 60}
    req = {"scenario_id": "t", "horizon_months": 120, "start": {"goal_pool": 1000, "pool_label": "예금", "aux_accounts": [], "loans": [lease, credit]},
           "goal": {"type": "debt_free", "label": "대출 다 갚기", "target_amount": 0},
           "options": [{"option_id": "A", "label": "A", "expected_return": 3.3, "volatility": 0, "return_assumption_id": "",
                        "cashflows": [{"label": "월급", "amount": 900, "category": "income"}], "events": [], "lump_sums": [],
                        "aux_changes": [], "extra_payments": [], "loan_prepayments": []}],
           "inflation": 0, "member_context": {"base_age": 35}, "range": {"paths": 0, "seed": 1}}
    r = simulate(req)["results"][0]
    assert r["debt_free_month"] == 58 and r["goal_hit_month"] == 58 and r["start_debt"] == 3000.0
    assert r["yearly"][-1]["debt_end"] == 0.0
    # 순자산에는 전세대출 원금이 그대로 들어간다(보증금 같은 자산 없이 비교해도 빚 1억 5천만원이 빠져 있다)
    assert r["net_worth"][0]["value"] == 1000 - 15000 - 3000
    only_lease = {**req, "start": {**req["start"], "loans": [lease]}}
    assert "error" in simulate(only_lease)  # 전세대출뿐이면 '대출 다 갚기' 목표를 쓸 수 없다


def test_idle_pool_earns_no_interest():
    """전세 보증금−전세대출 몫(idle_pool)에는 예금 이자가 붙지 않는다(2026-11-15). 예전에는 풀 전체에 3.3%가 붙어 목표 달성이 너무 빨리 나왔다."""
    from engine import simulate

    def run(idle):
        req = {"scenario_id": "t", "horizon_months": 240, "start": {"goal_pool": 14000, "idle_pool": idle, "pool_label": "x",
               "aux_accounts": [], "loans": []}, "goal": {"type": "reach_target", "label": "t", "target_amount": 30000},
               "options": [{"option_id": "A", "label": "A", "expected_return": 3.3, "volatility": 2.0, "return_assumption_id": "",
                            "cashflows": [{"label": "월급", "amount": 300, "category": "income"}], "events": [], "lump_sums": [],
                            "aux_changes": [], "extra_payments": [], "loan_prepayments": []}],
               "inflation": 0, "member_context": {"base_age": 35}, "range": {"paths": 200, "seed": 1}}
        return simulate(req, include_monthly=True)["results"][0]

    def independent(idle):
        pool, m = 14000.0, 0
        while pool < 30000:
            m += 1
            pool += max(pool - idle, 0) * 0.033 / 12 + 300
        return m
    for idle in (0, 10000, -5000):
        assert run(idle)["goal_hit_month"] == independent(idle), idle
    assert run(10000)["goal_hit_month"] > run(0)["goal_hit_month"]
    assert run(10000)["monthly"][0]["interest"] == round(4000 * 0.033 / 12, 1)
    assert run(10000)["range"]["p50_hit_month"] >= run(0)["range"]["p50_hit_month"]  # 범위 계산도 같은 규칙


def test_plan_puts_lease_deposit_net_of_loan_into_idle_pool():
    from llm import family as F
    from llm.plan import build_request, check_option, normalize_goal
    fam = F.validate(F.preset("newly"))
    g = normalize_goal(fam, {"type": "reach_target", "target_amount": 30000})
    assert g["idle_pool"] == 10000.0 and g["start_pool"] == 14000.0  # 보증금 2억 5천 − 전세대출 1억 5천
    req = build_request(fam, g, [check_option(fam, g, {"option_id": "A", "label": "A", "return_id": "safe"})])
    assert req["start"]["idle_pool"] == 10000.0
    g2 = normalize_goal(F.validate(F.preset("elder")), {"type": "runway"})
    assert g2.get("idle_pool", 0.0) == 0.0  # 노후·대출 목표는 풀이 예금·투자뿐이라 이자가 전부에 붙는다
