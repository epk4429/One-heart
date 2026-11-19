"""곧 은퇴(퇴직)하는 분의 월급 끊기: 대출 갚기·간병(·기타의 대출/예금 지내기)의 선택 입력 3개(2026-11-20, U8·U9)."""

import copy

import pytest

from engine.api import simulate
from llm import family as F
from llm import goals as G
from llm import plan as PL
from llm.eval import load_family
from llm.plan import assumptions, normalize_goal

RID = assumptions()["returns"][0]["id"]


def _run(key, **fields):
    raw = copy.deepcopy(load_family(key))
    fl = raw["goal_input"]["fields"]
    for k in ("work_end_member_id", "work_end_age", "work_end_pension"):
        fl.pop(k, None)
    fl.update(fields)
    fam = F.validate(raw)
    g = normalize_goal(fam, G.derive_goal(fam["goal_input"], fam["members"]))
    spec = PL.check_option(fam, g, {"option_id": "A", "label": "x", "return_id": RID})
    return fam, g, simulate(PL.build_request(fam, g, [spec]))["results"][0]


def test_care_goal_stops_the_wage_of_the_member_who_retires():
    fam0, g0, r0 = _run("care_parents")  # 입력 없음: 일하는 가족의 월급이 끝까지 이어진다고 계산
    fam, g1, r1 = _run("care_parents", work_end_member_id="m0", work_end_age=60)
    assert g0["life"].get("work_end") is None and g1["life"]["work_end"]["month"] == 73  # 54세 → 60세 = 72개월 뒤
    m0, m1 = r0["monthly"], r1["monthly"]
    assert m0[10]["inflow"] == m1[10]["inflow"]  # 은퇴 전은 같고
    assert m1[80]["inflow"] < m0[80]["inflow"] - 400  # 은퇴 뒤에는 정환님 월급(480)이 빠진다
    assert any("60세에 은퇴" in line for line in PL.life_lines(fam, g1))
    assert any("끝까지 이어진다고" in line for line in PL.life_lines(fam0, g0))


def test_debt_goal_adds_the_pension_from_the_retirement_month():
    _, _, no_pen = _run("retire_mortgage", work_end_member_id="m0", work_end_age=62)
    _, _, pen = _run("retire_mortgage", work_end_member_id="m0", work_end_age=62, work_end_pension=150)
    assert pen["monthly"][30]["inflow"] - no_pen["monthly"][30]["inflow"] > 140  # 연금 월 150(월급 상승률과 별개로 그대로)
    assert pen["monthly"][5]["inflow"] == no_pen["monthly"][5]["inflow"]  # 은퇴 전에는 연금이 없다


def test_work_end_inputs_must_be_given_together():
    raw = copy.deepcopy(load_family("retire_mortgage"))
    raw["goal_input"]["fields"].pop("work_end_age")
    with pytest.raises(F.FamilyError):
        F.validate(raw)
    raw = copy.deepcopy(load_family("retire_mortgage"))
    raw["goal_input"]["fields"].pop("work_end_member_id")
    with pytest.raises(F.FamilyError):
        F.validate(raw)


def test_retire_category_keeps_its_own_retire_age_and_ignores_work_end():
    raw = copy.deepcopy(load_family("retire_pre"))
    raw["goal_input"]["fields"].update({"work_end_member_id": "m1", "work_end_age": 58})
    fam = F.validate(raw)
    assert "work_end_member_id" not in fam["goal_input"]["fields"]  # 노후·은퇴는 받지 않는 값은 버린다
