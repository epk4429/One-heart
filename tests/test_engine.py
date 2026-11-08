"""계산엔진 수용 테스트(docs/04_계산엔진.md 5절). 기획안 숫자가 정답이다."""

import copy
import json
from pathlib import Path

import pytest

from engine import compare, simulate
from engine.api import tool_summary

ROOT = Path(__file__).resolve().parents[1]
CASES = json.loads((ROOT / "data/golden/engine_cases.json").read_text(encoding="utf-8"))["cases"]


def _case(case_id):
    return next(c for c in CASES if c["case_id"] == case_id)


@pytest.mark.parametrize("case", CASES, ids=[c["case_id"] for c in CASES])
def test_golden_hit_months(case):
    out = simulate(case["request"])
    assert "error" not in out, out
    by_id = {r["option_id"]: r for r in out["results"]}
    for oid, exp in case["expect"].items():
        r = by_id[oid]
        assert r["goal_hit_month"] == exp["goal_hit_month"], oid
        assert r["goal_hit_display"] == exp["display"], oid
        if "end_pool" in exp:
            assert round(r["end_pool"]) == exp["end_pool"], oid
        if "age_at_hit" in exp:
            assert r["age_at_hit"] == exp["age_at_hit"], oid
        if "pool_after_3_months" in exp:
            assert round(r["monthly"][2]["end"]) == exp["pool_after_3_months"], oid


def test_newly_display_matches_plan_table():
    # 기획안 12쪽: A 약 4.3년 / B 약 4.9년 / C 약 6.1년
    out = simulate(_case("newly_options")["request"])
    assert [r["goal_hit_display"] for r in out["results"]] == ["약 4.3년", "약 4.9년", "약 6.1년"]


def test_agreed_contribution_sums_to_235():
    # 기획안 14쪽 분담방식: 함께 모으는 돈 175 + 휴직 준비 적금 60 = 235
    out = simulate(_case("newly_agreed")["request"])
    assert out["results"][0]["monthly_flow"] == 235


def test_elder_reverse_mortgage_reduces_net_worth_not_runway():
    out = simulate(_case("elder_options")["request"])
    r = {x["option_id"]: x for x in out["results"]}
    # 주택연금은 목표 풀(예금)에는 영향이 없고, 순자산(물려줄 몫)만 줄인다
    assert r["B"]["goal_hit_month"] is None
    assert r["B"]["net_worth"][-1]["value"] < r["B"]["end_pool"] + 55000
    # 작은 집: 6개월째 집 가치가 3억으로 바뀐다
    assert r["C"]["net_worth"][1]["value"] == pytest.approx(r["C"]["yearly"][0]["end"] + 30000, abs=0.2)


def test_run_id_is_stable_and_input_sensitive():
    req = _case("newly_options")["request"]
    a, b = simulate(req), simulate(copy.deepcopy(req))
    assert a["run_id"] == b["run_id"]
    req2 = copy.deepcopy(req)
    req2["options"][1]["expected_return"] = 4.0
    assert simulate(req2)["run_id"] != a["run_id"]


def test_range_is_reproducible_and_bracketed():
    req = _case("newly_options")["request"]
    r1 = simulate(req)["results"][1]["range"]
    r2 = simulate(req)["results"][1]["range"]
    assert r1 == r2
    assert r1["p10_hit_month"] <= r1["p50_hit_month"] <= r1["p90_hit_month"]
    assert 0 <= r1["prob_reach_within"] <= 1


def test_facts_cover_displayed_numbers():
    out = simulate(_case("newly_options")["request"])
    facts = {f["fact_id"]: f for r in out["results"] for f in r["facts"]}
    assert facts["B.goal_hit_years"]["display"] == "약 4.9년"
    assert facts["B.monthly_flow"]["display"] == "235만원"
    assert facts["B.return"]["display"] == "연 3.8%"
    assert facts["goal.target_amount"]["display"] == "3억원"
    assert facts["start.pool"]["display"] == "1억 4,000만원"
    # 공통 fact는 한 번만
    ids = [f["fact_id"] for r in out["results"] for f in r["facts"]]
    assert ids.count("goal.target_amount") == 1


@pytest.mark.parametrize("mutate,field", [
    (lambda r: r.__setitem__("horizon_months", 500), "request.horizon_months"),
    (lambda r: r["options"][0].__setitem__("expected_return", 40), "options[0].expected_return"),
    (lambda r: r["options"][0]["cashflows"][0].__setitem__("amount", 99999), "options[0].cashflows[0].amount"),
    (lambda r: r["options"][1]["events"][0].__setitem__("to_month", 999), "options[1].events[0].to_month"),
    (lambda r: r["goal"].__setitem__("type", "maximize"), "goal.type"),
    (lambda r: r["options"][2].__setitem__("option_id", "A"), "options"),
])
def test_invalid_inputs_are_rejected(mutate, field):
    req = copy.deepcopy(_case("newly_options")["request"])
    mutate(req)
    out = simulate(req)
    assert out["error"]["field"] == field


def test_compare_reports_delay_when_return_drops():
    req = _case("newly_agreed")["request"]
    lower = copy.deepcopy(req)
    lower["options"][0]["expected_return"] = 3.7
    diff = compare(simulate(req), simulate(lower))["diffs"][0]
    assert diff["hit_month_delta"] > 0


def test_tool_summary_has_no_monthly_table():
    s = tool_summary(simulate(_case("newly_options")["request"]))
    assert "monthly" not in s["results"][0]
    assert any(f["fact_id"] == "A.goal_hit_years" for f in s["results"][0]["facts"])


# ---------- 0.2.0: 대출·물가·빚 다 갚기 ----------
def _base(**kw):
    req = {"horizon_months": 120, "start": {"goal_pool": 1000, "loans": []},
           "goal": {"type": "reach_target", "target_amount": 5000},
           "options": [{"option_id": "A", "expected_return": 0, "range_paths": 0,
                        "cashflows": [{"label": "월급", "amount": 400, "category": "income"},
                                      {"label": "생활비", "amount": -300, "category": "expense"}]}],
           "range": {"paths": 0}}
    req.update(kw)
    return req


def test_amortizing_loan_payment_and_debt_free_month():
    req = _base(goal={"type": "debt_free"})
    req["start"]["loans"] = [{"id": "L1", "label": "신용대출", "balance": 1200, "rate": 0, "kind": "amortizing",
                              "payment": 100}]
    r = simulate(req)["results"][0]
    assert r["goal_hit_month"] == 12 and r["debt_free_month"] == 12
    assert r["monthly"][0]["loan_payment"] == 100 and r["monthly"][12]["loan_payment"] == 0
    assert r["monthly_flow"] == 0  # 400 - 300 - 100


def test_extra_payment_shortens_loan():
    req = _base(goal={"type": "debt_free"})
    req["start"]["loans"] = [{"id": "L1", "label": "신용대출", "balance": 1200, "rate": 6, "kind": "amortizing",
                              "payment": 60}]
    base = simulate(req)["results"][0]["debt_free_month"]
    req["options"][0]["extra_payments"] = [{"loan_id": "L1", "monthly": 60}]
    faster = simulate(req)["results"][0]["debt_free_month"]
    assert faster < base


def test_interest_only_loan_in_pool_keeps_balance():
    req = _base()
    req["start"]["loans"] = [{"id": "L1", "label": "전세대출", "balance": 12000, "rate": 4, "kind": "interest_only",
                              "in_pool": True}]
    r = simulate(req)["results"][0]
    assert r["monthly"][0]["loan_payment"] == 40  # 12000 × 4% / 12
    assert r["monthly"][-1]["debt"] == 0  # 목표 풀에서 이미 뺀 대출은 순자산에서 다시 빼지 않는다


def test_inflation_raises_expenses_only():
    flat = simulate(_base())["results"][0]
    infl = simulate(_base(inflation=2.0))["results"][0]
    assert flat["monthly"][0]["outflow"] == infl["monthly"][0]["outflow"]  # 첫 달은 같다
    assert infl["monthly"][24]["outflow"] < flat["monthly"][24]["outflow"]  # 2년 뒤 생활비가 더 크다
    assert infl["monthly"][24]["inflow"] == flat["monthly"][24]["inflow"]


def test_amortizing_payment_must_exceed_interest():
    req = _base()
    req["start"]["loans"] = [{"id": "L1", "balance": 10000, "rate": 12, "kind": "amortizing", "payment": 50}]
    assert simulate(req)["error"]["field"] == "start.loans[0].payment"
