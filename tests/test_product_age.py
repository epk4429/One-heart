"""상품 유형의 가족 상황 조건(1-5, 2026-11-10): 이미 은퇴한 분의 노후 생활비에 연금저축(일하는 동안 오래 모으는 상품)을 연결하지 않는다.
판단은 나이로 짐작하지 않고, 가족이 가족방 만들기에서 고른 '지금 하는 일'(일하고 있어요 / 은퇴했어요 / 일하지 않아요)로만 한다."""

import pytest

from llm import family as F
from llm import pipeline as P
from llm.runner import RoleRun
from ontology import recommend
from ontology.search import retired_target

NEED = "N_retirement_income"
MAP = [{"commitment_id": "goal", "need_ids": [NEED], "constraint_ids": []}]
COMS = {"goal": {"no": None, "text": "지금 집에서, 지금처럼"}}


def _types(recs):
    return {r["product_type_id"] for r in recs if r.get("product_type_id")}


def _m(mid, work, age=40):
    return {"member_id": mid, "name": mid, "role": "x", "age": age, "work": work}


def test_retired_owner_does_not_get_pension_savings():
    recs = recommend(MAP, COMS, retired=True)
    assert "P_pension_savings" not in _types(recs)
    assert {"PP_reverse_mortgage", "PP_basic_pension"} <= _types(recs)  # 주택연금·기초연금은 그대로
    ex = [e for r in recs for e in r["excluded"] if e["product_type_id"] == "P_pension_savings"]
    assert ex and "은퇴한 분" in ex[0]["reason"]  # 왜 뺐는지 화면의 '제외'에 남는다


@pytest.mark.parametrize("retired", [False, None])
def test_working_or_unknown_keeps_pension_savings(retired):
    assert "P_pension_savings" in _types(recommend(MAP, COMS, retired=retired))


def test_retired_target_follows_family_input_not_age():
    # 목표에 '누구 기준'이 있으면 그 사람의 하는 일로
    fam = [_m("m0", "retired", 72), _m("m1", "retired", 69), _m("m2", "working", 45)]
    assert retired_target(fam, "m0") is True
    assert retired_target(fam, "m2") is False
    # 나이가 많아도 일하고 있으면 은퇴로 보지 않는다(나이로 짐작하지 않음)
    assert retired_target([_m("m0", "working", 66), _m("m1", "none", 63)]) is False
    # 기준 사람이 없으면 가족 전체: 일하는 사람이 없고 은퇴한 사람이 있을 때만
    assert retired_target([_m("m0", "retired", 70), _m("m1", "none", 68)]) is True
    assert retired_target([_m("m0", "working", 32), _m("m1", "working", 30)]) is False
    # 하는 일을 모르면 판단하지 않는다(예전에 저장한 가족)
    assert retired_target([_m("m0", None, 80)], "m0") is None
    assert retired_target([_m("m0", None, 80)]) is None


def test_family_check_accepts_and_validates_work():
    fam = F.preset("newly")
    assert [m["work"] for m in F.validate(fam)["members"]] == ["working", "working"]
    bad = {**fam, "members": [{**fam["members"][0], "work": "boss"}, fam["members"][1]]}
    with pytest.raises(F.FamilyError):
        F.validate(bad)
    old = {**fam, "members": [{k: v for k, v in m.items() if k != "work"} for m in fam["members"]]}
    assert [m["work"] for m in F.validate(old)["members"]] == [None, None]  # 예전 가족도 받는다


def _fake_8(monkeypatch):
    def fake_run_role(key, inp, provider, **kw):
        assert key == "8"
        return RoleRun(role="8", output={"mappings": [{"commitment_id": "goal", "need_ids": [NEED], "constraint_ids": []}]},
                       ok=True, attempts=1)
    monkeypatch.setattr(P, "run_role", fake_run_role)


def test_recommend_step_with_elder_family(monkeypatch):
    """상품 추천 단계 전체: 노후 예시 가족(목표 '누구 기준' = 은퇴하신 아버님)은 연금저축이 빠진다."""
    _fake_8(monkeypatch)
    fam = F.validate(F.preset("elder"))
    out = P.recommend(fam, {"goal": "지금 집에서, 지금처럼", "commitments": []}, None)
    types = _types(out["result"]["recommendations"])
    assert "P_pension_savings" not in types and "PP_basic_pension" in types


def test_recommend_step_with_newly_family(monkeypatch):
    """신혼부부(둘 다 일하는 중)는 은퇴 소득 필요로 이어지면 연금저축이 그대로 나온다."""
    _fake_8(monkeypatch)
    fam = F.validate(F.preset("newly"))
    out = P.recommend(fam, {"goal": "노후 준비", "commitments": []}, None)
    assert "P_pension_savings" in _types(out["result"]["recommendations"])
