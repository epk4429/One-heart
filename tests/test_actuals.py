"""가족 홈 '이번 달 실제로 모은 돈' 기록(2026-11-16): 서버가 계획과의 차이를 그 달만의 수입 변화로 엔진에 넣어 다시 계산한다."""
import json

from llm import family as F
from server.app import dispatch

GOAL = {"type": "reach_target", "label": "내 집 마련", "target_amount": 30000, "within_months": 60, "floor": 1000}
SPEC = {"option_id": "A", "label": "x", "return_id": "deposit_heavy", "monthly_changes": [], "adjustments": [],
        "events": [], "lump_sums": [], "policies": []}


def _sim(**extra):
    body = {"family": F.validate(F.preset("newly")), "goal": GOAL, "specs": [SPEC], **extra}
    return dispatch("POST", "/api/simulate", json.dumps(body).encode(), {}, "t")


def test_actual_saved_changes_that_month_and_carries_forward():
    st, base = _sim()
    assert st == 200
    m = base["results"][0]["monthly"]
    plan = m[2]["inflow"] + m[2]["outflow"]
    st, out = _sim(actuals={"3": plan - 100})
    assert st == 200
    m2 = out["results"][0]["monthly"]
    assert m2[1]["end"] == m[1]["end"]                                   # 기록 전 달은 그대로
    assert abs((m[2]["end"] - m2[2]["end"]) - 100) < 0.5                  # 3개월째 월말 잔액이 100만원 적어진다
    assert m2[3]["end"] < m[3]["end"]                                     # 그 뒤 달에도 이어진다
    assert abs(out["actual_basis"]["flow"]["3"] - plan) < 0.11            # 계획 값을 같이 돌려준다


def test_actual_equal_to_plan_changes_nothing():
    st, base = _sim()
    m = base["results"][0]["monthly"]
    st, out = _sim(actuals={"3": round(m[2]["inflow"] + m[2]["outflow"], 1)})
    assert st == 200 and abs(out["results"][0]["monthly"][2]["end"] - m[2]["end"]) < 0.2


def test_actual_input_is_checked():
    for bad in ({"x": 1}, {"0": 1}, {"121": 1}, {"3": "많이"}, {"3": 99999}, {"3": True}, [1]):
        st, out = _sim(actuals=bad)
        assert st == 400 and out["error"]["code"] == "bad_request", bad


def test_several_months_each_replace_their_own_plan_value():
    """누적: 여러 달을 기록하면 달마다 계획 값과의 차이가 따로 들어가고, 같은 달을 다른 금액으로 다시 보내면 그 달 값만 바뀐다(더해지지 않는다)."""
    st, base = _sim()
    m = base["results"][0]["monthly"]
    plan = lambda i: m[i]["inflow"] + m[i]["outflow"]
    _, two = _sim(actuals={"1": plan(0) + 50, "2": plan(1) - 20})
    t = two["results"][0]["monthly"]
    assert abs((t[0]["end"] - m[0]["end"]) - 50) < 0.5 and abs((t[1]["end"] - m[1]["end"]) - 30) < 0.8   # 1개월 +50, 2개월째까지 누적 +30
    _, redo = _sim(actuals={"1": plan(0) + 10, "2": plan(1) - 20})
    r = redo["results"][0]["monthly"]
    assert abs((r[0]["end"] - m[0]["end"]) - 10) < 0.5                                                   # 1개월 금액을 바꾸면 그 값으로(50+10이 아니다)
    assert abs(sum(redo["actual_basis"]["flow"].values()) - (plan(0) + plan(1))) < 0.3
