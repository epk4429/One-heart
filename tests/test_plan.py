"""방법(spec) 출처 검사와 목표 정리(llm/plan.py). AI가 지어낸 숫자·정책은 엔진에 들어가기 전에 막힌다."""

import json
from pathlib import Path

import pytest

from engine import simulate
from llm import family as F
from llm.plan import PlanError, build_request, check_option, normalize_goal, policy_menu

ROOT = Path(__file__).resolve().parents[1]


def fam(key):
    if key in ("newly", "elder"):
        return F.validate(F.preset(key))
    return F.validate(json.loads((ROOT / f"data/eval/families/{key}.json").read_text(encoding="utf-8")))


def test_target_must_exceed_money_already_saved():
    f = fam("newly")
    with pytest.raises(PlanError, match="지금 모여 있는 돈"):
        normalize_goal(f, {"type": "reach_target", "target_amount": 8000})
    g = normalize_goal(f, {"type": "reach_target", "target_amount": 30000, "within_months": 60})
    assert g["start_pool"] == 14000  # 예금·투자 4,000 + 보증금 2.5억 − 전세대출 1.5억


def test_debt_free_needs_repaying_loan():
    with pytest.raises(PlanError):
        normalize_goal(fam("newly"), {"type": "debt_free"})  # 전세대출은 이자만 내서 '다 갚기' 대상이 아니다
    assert normalize_goal(fam("single_parent"), {"type": "debt_free"})["horizon_months"] % 12 == 0


@pytest.mark.parametrize("bad, msg", [
    ({"return_id": "moon"}, "return_id"),
    ({"adjustments": [{"label": "부업", "amount": 900, "reason": "?"}]}, "adjustments"),
    ({"lump_sums": [{"label": "복권", "month": 3, "amount": 5000, "reason": "?"}]}, "lump_sums"),
    ({"monthly_changes": [{"item_id": "f3", "amount": 1, "reason": "?"}]}, "매달"),
    ({"policies": [{"policy": "reverse_mortgage"}]}, "정책"),
    ({"events": [{"label": "휴직", "from_month": 30, "to_month": 10, "amount": -100, "reason": "?"}]}, "to_month"),
])
def test_invented_conditions_are_rejected(bad, msg):
    f = fam("newly")
    g = normalize_goal(f, {"type": "reach_target", "target_amount": 30000})
    spec = {"option_id": "A", "label": "x", "return_id": "safe", **bad}
    with pytest.raises(PlanError, match=msg):
        check_option(f, g, spec)


def test_hidden_item_cannot_be_changed():
    f = fam("elder")  # 아버지 예금 f1은 '합계만'
    f["disclosure"]["f6"] = "hide"
    g = normalize_goal(f, {"type": "runway"})
    with pytest.raises(PlanError):
        check_option(f, g, {"option_id": "A", "label": "x", "return_id": "safe",
                            "monthly_changes": [{"item_id": "f6", "amount": 10, "reason": "?"}]})


def test_policy_amounts_come_from_code_not_ai():
    f = fam("elder")
    g = normalize_goal(f, {"type": "runway"})
    rm = next(p for p in policy_menu(f, g) if p["policy"] == "reverse_mortgage")
    assert rm["monthly"] == 110  # 5.5억 × 0.2%(72세 가정)
    specs = [check_option(f, g, {"option_id": "A", "label": "연금", "return_id": "safe",
                                 "policies": [{"policy": "reverse_mortgage", "from_month": 1}]}),
             check_option(f, g, {"option_id": "B", "label": "이사", "return_id": "safe",
                                 "policies": [{"policy": "sell_home", "month": 6, "new_home_ratio": 0.6}]})]
    out = simulate(build_request(f, g, specs))
    a, b = out["results"]
    assert any(x["label"] == "주택연금" and x["value"] == 110 for x in a["basis"])
    assert any(x["key"] == "lump:6" and x["value"] == 55000 * 0.4 - 55000 * 0.04 for x in b["basis"])
    with pytest.raises(PlanError, match="함께"):
        check_option(f, g, {"option_id": "C", "label": "둘 다", "return_id": "safe",
                            "policies": [{"policy": "reverse_mortgage"}, {"policy": "sell_home", "month": 6, "new_home_ratio": 0.6}]})


def test_lump_repayment_and_result_spread_check():
    from llm.roles import _c5
    f = fam("mortgage_couple")
    g = normalize_goal(f, {"type": "debt_free"})
    same = [{"option_id": o, "label": o, "return_id": r} for o, r in zip("ABC", ["safe", "deposit_heavy", "stock30"])]
    errs = _c5({"options": same}, {"family": f, "goal_full": g})
    assert any("거의 같아요" in e for e in errs)  # 투자 방식만 바꾸면 다 갚는 때는 같다 → 다시 설계하게
    diff = [{"option_id": "A", "label": "a", "return_id": "safe"},
            {"option_id": "B", "label": "b", "return_id": "safe",
             "policies": [{"policy": "lump_repayment", "item_id": "f8", "month": 1, "amount": 1500}]},
            {"option_id": "C", "label": "c", "return_id": "safe",
             "policies": [{"policy": "extra_repayment", "item_id": "f8", "amount": 100}]}]
    assert _c5({"options": diff}, {"family": f, "goal_full": g}) == []
    with pytest.raises(PlanError):  # 가진 예금보다 많이 한 번에 갚을 수는 없다
        check_option(f, g, {"option_id": "A", "label": "x", "return_id": "safe",
                            "policies": [{"policy": "lump_repayment", "item_id": "f8", "month": 1, "amount": 9999}]})
