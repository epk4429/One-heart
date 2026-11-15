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
    with pytest.raises(PlanError, match="보유 자산"):
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
    f = fam("elder")  # 아버지 예금 f1은 '비공개'
    f["disclosure"]["f6"] = "hide"
    g = normalize_goal(f, {"type": "runway"})
    with pytest.raises(PlanError):
        check_option(f, g, {"option_id": "A", "label": "x", "return_id": "safe",
                            "monthly_changes": [{"item_id": "f6", "amount": 10, "reason": "?"}]})


def test_policy_amounts_come_from_code_not_ai():
    f = fam("elder")
    g = normalize_goal(f, {"type": "runway"})
    rm = next(p for p in policy_menu(f, g) if p["policy"] == "reverse_mortgage")
    assert rm["monthly"] == 163 and "월지급금 예시표" in rm["basis"]  # 공사 예시표: 부부 중 젊은 69세·5.5억(65·70세, 5·6억 칸 사이)
    specs = [check_option(f, g, {"option_id": "A", "label": "연금", "return_id": "safe",
                                 "policies": [{"policy": "reverse_mortgage", "from_month": 1}]}),
             check_option(f, g, {"option_id": "B", "label": "이사", "return_id": "safe",
                                 "policies": [{"policy": "sell_home", "month": 6, "new_home_ratio": 0.6}]})]
    out = simulate(build_request(f, g, specs))
    a, b = out["results"]
    assert any(x["label"] == "주택연금" and x["value"] == 163 for x in a["basis"])
    assert any(x["key"] == "lump:6" and x["value"] == 55000 * 0.4 - 55000 * 0.04 for x in b["basis"])
    with pytest.raises(PlanError, match="함께"):
        check_option(f, g, {"option_id": "C", "label": "둘 다", "return_id": "safe",
                            "policies": [{"policy": "reverse_mortgage"}, {"policy": "sell_home", "month": 6, "new_home_ratio": 0.6}]})


def test_lump_repayment_and_realism_checks():
    """현실성 검사(2026-11-15): 똑같은 방법 거부, 일시 상환은 예금에서 비상금 선을 남기는 만큼만, 가족이 정한 선보다 낮은 비상금 거부."""
    from llm.roles import _c5
    f = fam("mortgage_couple")
    g = normalize_goal(f, {"type": "debt_free", "floor": 500})
    same = [{"option_id": o, "label": o, "return_id": "safe"} for o in "ABC"]
    assert any("똑같은 방법" in e for e in _c5({"options": same}, {"family": f, "goal_full": g}))
    diff = [{"option_id": "A", "label": "a", "return_id": "safe"},
            {"option_id": "B", "label": "b", "return_id": "deposit_heavy"},
            {"option_id": "C", "label": "c", "return_id": "safe", "floor": 1500, "adjustments": [{"label": "여유 지출", "amount": -20, "reason": "여유"}]}]
    notes = [{"option_id": o, "intent": "x", "why": "근거 한 문장이에요."} for o in "ABC"]
    assert _c5({"options": diff, "design_notes": notes}, {"family": f, "goal_full": g}) == []
    b_floor = [diff[0], {**diff[1], "floor": 1500}, diff[2]]  # 더 넉넉한 비상금은 C에서만(2026-11-15)
    assert any("C에서만" in e for e in _c5({"options": b_floor, "design_notes": notes}, {"family": f, "goal_full": g}))
    with pytest.raises(PlanError):
        check_option(f, g, {"option_id": "A", "label": "x", "return_id": "safe",
                            "policies": [{"policy": "lump_repayment", "item_id": "f8", "month": 1, "amount": 9999}]})
    with pytest.raises(PlanError):
        check_option(f, g, {"option_id": "A", "label": "x", "return_id": "safe", "floor": 100})



def test_unchanged_c_is_named_as_baseline():
    """C가 아무것도 바꾸지 않으면 '지금처럼(비교용)'으로 이름 붙인다(2026-11-15 형님 결정). A·B는 이름을 바꾸지 않는다."""
    from llm.plan import mark_baseline
    f = fam("mortgage_couple")
    g = normalize_goal(f, {"type": "debt_free", "floor": 500})
    specs = [check_option(f, g, {"option_id": o, "label": f"{o} 원래 이름", "return_id": "safe"}) for o in "ABC"]
    out = mark_baseline(specs)
    assert [s["label"] for s in out] == ["A 원래 이름", "B 원래 이름", "지금처럼(비교용)"]
    changed = check_option(f, g, {"option_id": "C", "label": "여유", "return_id": "safe", "floor": 800})
    assert mark_baseline([changed])[0]["label"] == "여유"
