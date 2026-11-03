"""사람 조건 판정(5단계): 우대·가입대상의 나이·자녀 수·가족이 고르는 조건(ontology/conditions.py person_rule, ontology/fit.py).
정답 사례는 원문(금감원 공시 우대조건·가입대상)을 사람이 읽고 적었다."""

import json

import pytest

from llm import family as F
from ontology import conditions as C
from ontology.fit import compare
from server.app import dispatch

NEWLY = F.validate(F.preset("newly"))  # 민준 32, 서연 30, 집 없음
ELDER = F.validate(F.preset("elder"))  # 김영호 72(본인 명의 아파트), 박순자 69, 김태윤 45, 김지은 41
NH = "PRD_saving_0013175_10-047-1387-0001"  # 우대: "2-1. 만 65세 이상 고령자 우대 : 0.1%p", "2-2. 만 19~34세 MZ고객 우대 : 0.3%p"
KIDS = "PRD_saving_0010534_WR0001V"  # 스마트 아이플러스: "만 18세 이하 자녀 수 2명 우대이율 2.0%, / 자녀 수 3명 이상 우대이율 3.0%", 가입 "만 18세이하 다자녀를 둔 부모"
MYHOME = "PRD_saving_0010370_310037"  # 마이홈 정기적금: 가입 "… 무주택 개인", 우대 "소득취약계층 우대금리 : 연 1.0%"


@pytest.mark.parametrize("text, want", [
    ("2-2. 만 19~34세 MZ고객 우대 : 0.3%p", {"type": "age", "min": 19, "max": 34}),
    ("① 가입당시 만20세~만39세 : 0.50%", {"type": "age", "min": 20, "max": 39}),
    ("-만 65세이상 첫가입시 최초 1계좌에 한하여 우대금리 연 0.1%p적용", {"type": "age", "min": 65, "max": None}),
    ("만 18세 이하 자녀 수 2명 우대이율 2.0%,\n자녀 수 3명 이상 우대이율 3.0%", {"type": "kids", "min": 2, "tiers": [[2, 2.0], [3, 3.0]]}),
    ("세명 이상의 미성년 자녀를 둔 부모", {"type": "kids", "min": 3}),
    ("5. 다자녀 가정 +0.25%", {"type": "kids", "min": 3, "maybe_from": 2}),
    ("- 장애인 등록고객 시 : 연0.2%", {"type": "flags", "flags": ["disabled"]}),
    ("③ 미성년자 자녀가 있는 한부모 가정의 부모(0.3%)", {"type": "flags", "flags": ["single_parent"]}),
    ("신규 가입일 당시 2년 이내 출생한 자녀의 부모인 경우 : 1.00 %p", {"type": "flags", "flags": ["newborn"]}),
    ("* 임신 또는 당해연도 출산(임신: 본인에 한하여 적용, 출산: 부모 기준 적용)", {"type": "flags", "flags": ["pregnant"]}),  # 당해연도는 2년보다 좁다
])
def test_person_rule_reads_original(text, want):
    who = C.person_rule(text)
    assert {k: who.get(k) for k in want} == want
    assert who["quote"] in text  # G3


@pytest.mark.parametrize("text", [
    "② 증빙서류 제출 시점 만 16세이하 가구원수에 따른 우대 - 1명 : 3.0%p - 2명 : 4.0%p - 3명 이상 : 6.0%p",  # 자녀 나이를 모른다
    "⑤비과세종합저축 대상 고객",  # 2026년 대상 변경을 1차 출처로 확인 못 함
    "②가입기간 중 다둥이 가정(미성년 자녀 2명 이상) 출산시 + 1.50%",  # 출산과 자녀 수가 함께 걸림
    "1. 가입시점 중소기업 근로자로 확인된 경우 : 재직기간에 따라 최고 연 1.2%p",
    "- 청년층 우대금리 : 연0.9%",  # 청년 나이 기준이 원문에 없다
    "-정기예금 이용 -첫번째 적금 가입 -고객등록5년이상 -2인이상 동반가입 -다자녀(3인)를 두신 -올해의 띠 -60세 이상",  # 여러 조건 나열
])
def test_person_rule_leaves_unclear_conditions(text):
    assert C.person_rule(text) is None


def test_judge_person_three_values():
    mz = C.person_rule("만 19~34세 MZ고객 우대 : 0.3%p")
    assert C.judge_person(mz, 30, None, set())[0] == "met" and C.judge_person(mz, 40, None, set())[0] == "not_met"
    kids = C.person_rule("만 18세 이하 자녀 수 2명 우대이율 2.0%,\n자녀 수 3명 이상 우대이율 3.0%")
    assert C.judge_person(kids, 40, 3, set()) == ("met", 3.0) and C.judge_person(kids, 40, 2, set()) == ("met", 2.0)
    assert C.judge_person(kids, 40, None, set())[0] == "unknown" and C.judge_person(kids, 40, 1, set())[0] == "not_met"
    many = C.person_rule("다자녀 가정 +0.25%")
    assert C.judge_person(many, 40, 2, set())[0] == "unknown"  # 은행마다 2명·3명
    flag = C.person_rule("장애인 등록고객 시 : 연0.2%")
    assert C.judge_person(flag, 40, 0, set())[0] == "unknown"  # 안 고른 것은 '해당 안 됨'이 아니라 '모름'
    assert C.judge_person(flag, 40, 0, {"disabled"})[0] == "met"


def _row(res, pid):
    return next(r for r in res["items"] if r["product_id"] == pid)


def _saving(fam, mid, **kw):
    return compare(fam, "N_goal_saving", category="saving", member_id=mid, monthly=30, **kw)


def test_age_benefit_by_account_holder():
    young = _row(_saving(NEWLY, "m1"), NH)  # 서연 30세: MZ 우대 해당, 65세 우대 아님
    assert [g["label"] for g in young["got"]] == ["해당돼요 · 나이 만 19~34세"]
    assert young["my_rate"] == round(young["base_rate"] + 0.3, 2)
    assert not any("65" in m["label"] for m in young["maybe"])
    old = _row(_saving(ELDER, "m0"), NH)  # 72세: 고령자 우대
    assert [g["label"] for g in old["got"]] == ["해당돼요 · 나이 만 65세 이상"] and old["my_rate"] == round(old["base_rate"] + 0.1, 2)
    mid = _row(_saving(ELDER, "m2"), NH)  # 45세: 둘 다 아님
    assert mid["got"] == [] and mid["my_rate"] == mid["base_rate"]


def test_kids_tiers_and_eligibility():
    # 원문은 자녀 수별 +2.0/+3.0%인데 공시 최고금리는 기본금리와 같다(docs/13): 해당은 보여 주되 금리에는 공시까지만, 이유를 말한다
    three = _row(_saving(ELDER, "m2", person={"kids": 3}), KIDS)
    assert [(g["label"], g["pp"]) for g in three["got"]] == [("해당돼요 · 18세 이하 자녀 2명 이상", 3.0)] and "자녀 수" not in three["checks"]
    assert three["my_rate"] == three["max_rate"] and three["held_pp"] == 3.0 and any("공시 최고금리를 넘어서" in t for t in three["reasons"])
    two = _row(_saving(ELDER, "m2", person={"kids": 2}), KIDS)
    assert two["got"][0]["pp"] == 2.0 and "자녀 수" in two["checks"]  # 가입대상 '다자녀'는 2명이면 확인 필요
    one = _saving(ELDER, "m2", person={"kids": 1})
    assert KIDS not in [r["product_id"] for r in one["items"]] and any("자녀" in e["reason"] for e in one["excluded"])
    unknown = _row(_saving(ELDER, "m2"), KIDS)
    assert unknown["my_rate"] == unknown["base_rate"] and "자녀 수" in unknown["checks"]


def test_no_home_eligibility_from_finance():
    owner = _saving(ELDER, "m0")  # 본인 명의 아파트
    assert MYHOME not in [r["product_id"] for r in owner["items"]] and any("무주택" in e["reason"] for e in owner["excluded"])
    r = _row(_saving(NEWLY, "m1", person={"flags": ["low_income"]}), MYHOME)
    assert any("무주택으로 봤어요" in t for t in r["reasons"]) and r["my_rate"] >= r["base_rate"] + 1.0 - 1e-9


def test_non_resident_foreigner_exclusion_is_not_a_family_condition():
    elig = C.parse_eligibility("비거주 외국인 외 제한없음", "1")
    assert elig["unknown"] == []


def test_api_person():
    body = {"family": NEWLY, "need_id": "N_goal_saving", "category": "saving", "member_id": "m1", "monthly": 30, "person": {"kids": 2, "flags": ["pregnant"]}}
    status, res = dispatch("POST", "/api/products/fit", json.dumps(body).encode(), {})
    assert status == 200 and res["person"]["kids"] == 2 and res["person"]["flags"] == ["pregnant"]
    status, _ = dispatch("POST", "/api/products/fit", json.dumps({**body, "person": {"kids": 9}}).encode(), {})
    assert status == 400
