"""시나리오 15개로 현실성 검사(할 일 1-9 D2, 비용 0, 2026-11-15).

① 나쁜 AI 답을 넣으면 서버가 막거나 코드가 채우는지 ② 재생 공급자로 설계한 방법이 현실성 검사기를 모두 통과하는지.
실제 AI 결과는 `python tools/realism_check.py --provider anthropic --yes-cost`(비용 발생, 형님께 먼저 알림)로 따로 본다.
"""

import json
from pathlib import Path

import pytest

from llm import family as F
from llm import pipeline as P
from llm.plan import PlanError, _bounds, check_option, cut_limit, floor_errors, normalize_goal
from tools.realism_check import check, design, goal_raw, load

SC = load()
IDS = [s["id"] for s in SC]


def _fam_goal(sc):
    fam = F.validate(sc["family"])
    return fam, normalize_goal(fam, goal_raw(fam))


@pytest.mark.parametrize("sc", SC, ids=IDS)
def test_bad_ai_answers_are_blocked_or_filled(sc):
    fam, goal = _fam_goal(sc)
    spend = [i for i in fam["finance"] if i["kind"] == "expense"]
    # 생활비 0원 → 서버가 거부
    with pytest.raises(PlanError):
        check_option(fam, goal, {"option_id": "A", "label": "x", "return_id": "safe",
                                 "monthly_changes": [{"item_id": spend[0]["item_id"], "amount": 0, "reason": "다 줄이기"}]},
                     cut_limit=cut_limit(fam, sc["summaries"]))  # 방법을 짜는 단계의 한도(20% 또는 가족이 말한 금액)
    # 가진 예금보다 큰 지출 → 비상금 선 검사에 걸림(노후·간병은 결과 자체가 '바닥나는 때'라 제외)
    big = check_option(fam, goal, {"option_id": "A", "label": "x", "return_id": "safe",
                                   "lump_sums": [{"label": "큰 지출", "month": 1, "amount": -min(_bounds(fam)["lump"], goal["start_pool"] + 1000), "reason": "?"}]})
    sim = P.simulate_specs(fam, goal, [big], include_monthly=False)
    if goal["type"] != "runway" and not goal.get("deficit"):
        assert floor_errors(goal, [big], sim["results"])
    if goal.get("deficit"):  # 적자 상태는 거부하지 않고 '비상금 아래로 내려가는 때'를 보여 준다(2026-11-15 형님 결정 A)
        assert not floor_errors(goal, [big], sim["results"]) and sim["results"][0]["floor_breach_month"]
    # 아무 이벤트도 없는 방법(AI가 은퇴·간병·휴직을 빠뜨린 경우)이어도 코드가 계산에 넣는다
    bare = check_option(fam, goal, {"option_id": "A", "label": "x", "return_id": "safe", "adjustments": [{"label": "a", "amount": 10, "reason": "r"}]})
    found = check(fam, goal, [bare], P.simulate_specs(fam, goal, [bare]))
    life_rules = {"은퇴 뒤 월급 없음", "은퇴 후 생활비 반영", "연금 처리", "간병비 반영", "휴직 중 월급 빠짐", "100세까지 계산"}
    assert all(f["ok"] for f in found if f["rule"] in life_rules), [f for f in found if f["rule"] in life_rules and not f["ok"]]


@pytest.mark.parametrize("sc", SC, ids=IDS)
def test_replay_designs_pass_realism_check(sc):
    fam = F.validate(sc["family"])
    out = design(fam, sc, "replay")
    assert "specs" in out, out.get("design_run", {}).get("errors")
    found = check(fam, out["goal"], out["specs"], out["simulation"], out.get("deadline_note", ""))
    assert all(f["ok"] for f in found), [f for f in found if not f["ok"]]


def test_scenarios_cover_every_goal_kind():
    kinds = {s["goal"] for s in SC}
    assert kinds == {"home", "debt", "retire", "care", "baby", "lump", "other"} and len(SC) == 18
    assert all(s["tests"] and s["expect"] for s in SC)  # 시나리오마다 무엇을 확인하는지·사람 눈 기대 결과를 적어 둔다
    assert json.loads(Path("data/scenarios/scenarios.json").read_text(encoding="utf-8"))["_note"]
