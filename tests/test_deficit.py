"""적자 상태(2026-11-15 형님 결정 A, 시안12): 엔진이 판정하고, 거부 대신 '비상금 아래로 내려가는 때'와 적자 메우기 표를 보여 준다."""

from engine.policies import annuity_payment, extend_term, total_interest
from llm import family as F
from llm import pipeline as P
from llm.plan import check_option, deficit_info, deficit_levers, floor_errors, normalize_goal
from tools.realism_check import goal_raw, load


def _deficit():
    sc = load("debt_deficit_family")[0]
    fam = F.validate(sc["family"])
    return fam, normalize_goal(fam, goal_raw(fam))


def test_annuity_and_extend_term_match_independent_math():
    p = annuity_payment(22000, 4.3, 480)
    b = 22000.0
    for _ in range(480):
        b = b * (1 + 4.3 / 1200) - p
    assert abs(b) < 0.01
    ex = extend_term(22000, 4.3, 110, 40)
    assert ex["payment"] == round(p, 1) and ex["monthly_saving"] == round(110 - p, 1)
    assert ex["extra_interest"] == round(total_interest(22000, 4.3, p) - total_interest(22000, 4.3, 110), -1) > 0


def test_deficit_is_detected_by_code_and_floor_check_is_relaxed():
    fam, goal = _deficit()
    d = goal["deficit"]
    assert d and d["monthly_gap"] == 180.0 and d["cut_max"] == 104.0
    spec = check_option(fam, goal, {"option_id": "A", "label": "x", "return_id": "safe"})
    sim = P.simulate_specs(fam, goal, [spec], include_monthly=False)
    assert floor_errors(goal, [spec], sim["results"]) == []  # 거부하지 않는다
    assert sim["results"][0]["floor_breach_month"]           # 대신 비상금 아래로 내려가는 달을 낸다
    ok = load("debt_mortgage_credit")[0]
    fam2 = F.validate(ok["family"])
    assert normalize_goal(fam2, goal_raw(fam2))["deficit"] is None  # 남는 돈이 있는 가족은 적자 상태가 아니다


def test_extend_term_policy_lowers_payment_and_delays_breach():
    fam, goal = _deficit()
    base = check_option(fam, goal, {"option_id": "A", "label": "x", "return_id": "safe"})
    ext = check_option(fam, goal, {"option_id": "B", "label": "y", "return_id": "safe",
                                   "policies": [{"policy": "extend_term", "item_id": "f7", "years": 40}]})
    rs = {r["option_id"]: r for r in P.simulate_specs(fam, goal, [base, ext], include_monthly=False)["results"]}
    assert rs["B"]["floor_breach_month"] > rs["A"]["floor_breach_month"]
    assert any(p["policy"] == "extend_term" for p in P.design_context(fam, goal)["policies"])


def test_levers_do_not_invent_income_and_sum_up():
    fam, goal = _deficit()
    lv = deficit_levers(fam, goal)
    labels = [r["label"] for r in lv["rows"]]
    assert "생활비 20% 줄이기" in labels and any("기간 늘리기" in l for l in labels) and any("집을 줄여" in l for l in labels)
    assert not any("일하면" in l or "벌면" in l for l in labels + lv["combos"])  # 부족한 돈을 새로 벌라는 방법은 넣지 않는다(형님 결정)
    # 지출 줄이기·기간 늘리기로는 못 메우지만, 집을 줄여 그 집 대출을 갚으면 상환액이 없어져 적자가 사라진다(실제 AI A안과 같은 결론)
    assert "62만원 모자라요" in lv["combos"][0] and "집을 줄여 대출 갚기 → 매달 약 34만원 남아요" in lv["combos"][1] and lv["solvable"] is True
    cuts = sum(r["monthly"] for r in lv["rows"] if "줄이기" in r["label"]) + next(r["monthly"] for r in lv["rows"] if "기간 늘리기" in r["label"])
    assert f"{round(180 - cuts):,}만원 모자라요" in lv["combos"][0]


def test_levers_say_cannot_when_nothing_works():
    """가진 것으로 못 메우면 그대로 말한다(집이 없는 적자 가족)."""
    fam, goal = _deficit()
    fam = {**fam, "finance": [i for i in fam["finance"] if i["kind"] != "home"]}
    lv = deficit_levers(fam, goal)
    assert lv["solvable"] is False and lv["combos"][-1] == "지금 가진 방법들로는 매달 적자를 메울 수 없어요"


def test_size_warns_deficit_in_goal_numbers():
    from llm import goal_size as GS
    fam, _ = _deficit()
    assert GS.size(fam, {})["deficit"]["monthly_gap"] == 180.0


def test_breach_fact_and_extend_term_required_in_deficit():
    from llm.roles import _c5
    fam, goal = _deficit()
    spec = check_option(fam, goal, {"option_id": "A", "label": "x", "return_id": "safe"})
    r = P.simulate_specs(fam, goal, [spec], include_monthly=False)["results"][0]
    f = next(x for x in r["facts"] if x["fact_id"] == "A.floor_breach")
    assert f["value"] == r["floor_breach_month"] and "개월" in f["display"] or "년" in f["display"]
    adj = lambda n: [{"label": "생활비 줄이기", "amount": n, "reason": "r"}]
    no_ext = [{"option_id": "A", "label": "a", "return_id": "safe", "adjustments": adj(100)},
              {"option_id": "B", "label": "b", "return_id": "safe", "adjustments": adj(50)},
              {"option_id": "C", "label": "c", "return_id": "safe"}]
    errs = _c5({"options": no_ext, "deadline_note": "적자라 어려워요"}, {"family": fam, "goal_full": goal})
    assert any("extend_term" in e for e in errs)
    with_ext = [{**no_ext[0], "policies": [{"policy": "extend_term", "item_id": "f7", "years": 40}]}] + no_ext[1:]
    errs = _c5({"options": with_ext, "deadline_note": "적자라 어려워요"}, {"family": fam, "goal_full": goal})
    assert not any("extend_term" in e for e in errs)
