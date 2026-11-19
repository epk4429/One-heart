"""대출 다 갚기 가족 홈: 정해진 월 상환과 '추가로 갚은 돈'을 나누고, 기록은 추가로 갚은 돈으로 받는다(2026-11-20).

기준 가족(대출 갚기 부부): 월급 750, 생활비 280(방법 B로 245), 양가 용돈 30, 예금 3,300, 주담대 3억(월 147)·신용 2천(월 60), 비상금 1,500.
형님 화면에서 '한 달 대출 상환 2,283 / 계획 −1,808'로 보이던 값이 어떻게 갈라지는지 고정한다. AI 없음.
"""

import copy
import json

from engine.api import simulate
from llm import family as F
from llm import plan as PL
from llm.plan import assumptions
from server.app import dispatch

GOAL = {"type": "debt_free", "label": "대출", "within_months": 180, "floor": 1500}


def _family():
    f = copy.deepcopy(F.preset("newly"))  # 예시 가족은 다른 테스트와 공유하므로 복사해서 쓴다
    f["members"][0]["name"], f["members"][1]["name"] = "민수", "지은"
    f["finance"] = [
        {"item_id": "f1", "owner_id": "m0", "kind": "income", "label": "남편 월급", "amount": 420},
        {"item_id": "f2", "owner_id": "m1", "kind": "income", "label": "아내 월급", "amount": 330},
        {"item_id": "f3", "owner_id": "joint", "kind": "expense", "label": "생활비", "amount": 280},
        {"item_id": "f4", "owner_id": "joint", "kind": "deposit", "label": "비상금 통장", "amount": 1500},
        {"item_id": "f5", "owner_id": "m0", "kind": "deposit", "label": "적금", "amount": 1200},
        {"item_id": "f6", "owner_id": "m1", "kind": "deposit", "label": "청약저축", "amount": 600},
        {"item_id": "f7", "owner_id": "joint", "kind": "home", "label": "아파트", "amount": 48000},
        {"item_id": "f8", "owner_id": "joint", "kind": "loan", "loan_type": "mortgage", "label": "주담대", "amount": 30000, "rate": 4.2, "payment": 147},
        {"item_id": "f9", "owner_id": "m0", "kind": "loan", "loan_type": "credit", "label": "신용대출", "amount": 2000, "rate": 5.9, "payment": 60},
        {"item_id": "f10", "owner_id": "joint", "kind": "transfer_out", "label": "양가 용돈", "amount": 30},
    ]
    return F.validate(f)


def _specs():
    rid = assumptions()["returns"][0]["id"]
    return [{"option_id": "A", "label": "B", "return_id": rid,
             "monthly_changes": [{"item_id": "f3", "amount": 245, "reason": "외식·여행 줄이기"}]}]


def _call(actuals=None, goal=GOAL, fam=None):
    body = {"family": fam or _family(), "goal": goal, "specs": _specs()}
    if actuals:
        body["actuals"] = actuals
    st, out = dispatch("POST", "/api/simulate", json.dumps(body).encode(), {}, "t")
    return st, out


def test_first_month_splits_scheduled_payment_and_extra():
    st, out = _call()
    r = out["results"][0]
    m1, m2 = r["monthly"][0], r["monthly"][1]
    assert st == 200 and r["extra_mode"] is True
    assert round(m1["loan_payment"] - m1["extra"], 1) == 207  # 은행에 내는 원래 상환: 주담대 147 + 신용 60
    assert round(m1["extra"]) == 2076  # 예금 중 비상금 1,500 위 1,800 + 이번 달 남는 돈
    assert m1["loan_payment"] == 2282.7  # 형님 화면의 '한 달 대출 상환 2,283'
    assert r["monthly_flow"] == 268  # 합의문의 매달 모이는 돈(수입 750 − 생활비 245 − 용돈 30 − 원래 상환 207)
    assert round(m2["loan_payment"] - m2["extra"]) == 147  # 첫 달에 비싼 신용대출(5.9%)을 먼저 다 갚아서 둘째 달부터 원래 상환은 주담대 147만


def test_extra_records_replace_the_plan_and_unpaid_money_stays_in_savings():
    st, base = _call()
    plan_end = base["results"][0]["monthly"][0]["end"]
    st, out = _call({"1": 500})
    r = out["results"][0]
    assert st == 200 and out["actual_basis"]["extra_mode"] is True
    assert out["actual_basis"]["flow"]["1"] == 2075.7  # 계획의 그 달 추가 상환(엔진 값)
    assert r["monthly"][0]["extra"] == 500
    assert r["monthly"][0]["end"] > plan_end + 1500  # 안 갚은 돈은 예금에 남는다
    st, out = _call({"1": 2076})
    assert out["results"][0]["debt_free_month"] == base["results"][0]["debt_free_month"]  # 계획대로 갚으면 시점이 그대로


def test_extra_records_reject_negative_and_other_goals_keep_the_saved_money_meaning():
    st, out = _call({"1": -5})
    assert st == 400
    fam = copy.deepcopy(F.preset("newly"))
    goal = {"type": "reach_target", "label": "목돈", "target_amount": 10000}
    st, out = dispatch("POST", "/api/simulate", json.dumps({"family": fam, "goal": goal, "actuals": {"1": 100}}).encode(), {}, "t")
    if st == 200:  # 모으기 목표는 예전 그대로 '실제로 모은 돈'
        assert out["results"][0].get("extra_mode") is False
        assert out["actual_basis"]["extra_mode"] is False


def test_lump_goal_does_not_count_the_lease_deposit_but_home_goal_does():
    """목돈·기타 목표는 살고 있는 집의 전세 보증금을 목표 돈에 넣지 않고, 내 집 마련은 넣는다(2026-11-20, U6)."""
    f = copy.deepcopy(F.preset("newly"))  # 예금·투자 4,000 + 전세 보증금 25,000 − 전세대출 15,000
    f["goal_input"] = {"category": "lump", "fields": {"purpose": "차량", "target_amount": 8000, "within_years": 3}}
    g = PL.normalize_goal(F.validate(f), {"type": "reach_target", "target_amount": 8000, "within_months": 36})
    assert g["start_pool"] == 4000 and g["pool_includes_lease"] is False
    f["goal_input"] = {"category": "home", "fields": {"target_amount": 30000, "within_years": 5, "living": "전세"}}
    g = PL.normalize_goal(F.validate(f), {"type": "reach_target", "target_amount": 30000, "within_months": 60})
    assert g["start_pool"] == 14000 and g["pool_includes_lease"] is True


def test_one_time_loan_prepayment_is_not_part_of_the_planned_saved_money():
    """방법이 6개월째 학자금대출을 일시 상환하면 그 달 가족 홈 '실제로 모은 돈' 계획에서 일시 상환은 빠진다(2026-11-20, U1)."""
    from llm.eval import load_family
    fam = copy.deepcopy(load_family("newly_rent"))
    fam.pop("scripts", None)
    v = F.validate(copy.deepcopy(fam))
    from llm import goals as G
    goal = G.derive_goal(v["goal_input"], v["members"])
    specs = [{"option_id": "A", "label": "학자금 일시 상환", "return_id": assumptions()["returns"][0]["id"],
              "policies": [{"policy": "lump_repayment", "item_id": "f9", "month": 6, "amount": 500}]}]
    st, out = dispatch("POST", "/api/simulate", json.dumps({"family": fam, "goal": goal, "specs": specs}).encode(), {}, "t")
    m5, m6 = out["results"][0]["monthly"][4], out["results"][0]["monthly"][5]
    assert m6["prepay"] == 500 and m5["prepay"] == 0
    assert round(m6["inflow"] + m6["outflow"]) < 0  # 일시 상환이 섞이면 마이너스
    st, out = dispatch("POST", "/api/simulate", json.dumps({"family": fam, "goal": goal, "specs": specs, "actuals": {"6": 226}}).encode(), {}, "t")
    assert abs(out["actual_basis"]["flow"]["6"] - 227.2) < 0.5  # 계획에서 일시 상환을 뺀 값
