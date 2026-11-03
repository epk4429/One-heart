"""6단계 검증 묶음(ontology/kb_eval.py): 가상 가족 12곳 × 모든 필요·제도·상품 범주에서 틀린 안내가 0인지."""

import pytest

from llm import family as F
from ontology import conditions as C
from ontology import fit, kb_eval
from ontology import programs as P


@pytest.fixture(scope="module")
def report():
    return kb_eval.run()


def test_no_wrong_guidance(report):
    m = report["metrics"]
    assert m["invalid_families"] == 0 and m["families"] >= 12
    for k in ("unrouted", "over_claim_programs", "false_exclusion_programs", "hint_wrong", "over_claim_policy", "over_claim_products", "inconsistent"):
        assert m[k] == 0, (k, report.get(k))


def test_every_family_runs_every_category(report):
    assert report["metrics"]["comparisons"] == sum(len(c["family"]["members"]) for c in kb_eval.load_families()) * len(kb_eval.PARAMS)


@pytest.mark.parametrize("text, want", [
    ("1~19세", (1, 19)), ("19~39세", (19, 39)), ("만 19세 이상 실명의 개인", (19, None)), ("만 19세미만", (None, 18)),
    ("만 18세이하 다자녀를 둔 부모", None), ("-만 18세 이하 본인 -만 18세 이하 자녀를 둔 부모", None),
])
def test_strict_age_reader(text, want):
    assert kb_eval.strict_age(text) == want


@pytest.mark.parametrize("text, want", [("1~19세", [(">=", 1), ("<=", 19)]), ("19~39세", [(">=", 19), ("<=", 39)]),
                                        ("20세부터 74세 이하", [(">=", 20), ("<=", 74)])])
def test_age_range_without_first_se(text, want):
    """'19~39세'를 '39세 이상'으로 읽어 청년 적금이 40대에게 보이고 25세에게서 빠지던 문제(2026-11-03)."""
    assert [(c["op"], c["value"]) for c in C.parse_eligibility(text, "1")["conditions"]] == want


def _case(fid):
    c = next(x for x in kb_eval.load_families() if x["id"] == fid)
    return F.validate(c["family"])


def test_reverse_mortgage_uses_home_owner_age():
    assert P.judge("PG_reverse_mortgage", _case("F06_elder_son_owner"))["status"] == "not_eligible"  # 집 주인 47세, 할아버지 76세는 무주택
    border = P.judge("PG_reverse_mortgage", _case("F11_border_ages"))  # 집 주인 54세, 함께 사는 64세는 배우자일 수도 → 확인 필요
    assert border["status"] == "check" and "배우자" in border["conditions"][0]["hint"]
    assert P.judge("PG_reverse_mortgage", _case("F05_pre_retire"))["status"] == "eligible"


def test_basic_pension_income_is_seniors_only():
    bp = P.judge("PG_basic_pension", _case("F06_elder_son_owner"))  # 아들 부부 월급을 합치지 않는다
    assert "기준 안" in bp["conditions"][1]["hint"] and "50만원" in bp["conditions"][1]["hint"]


def test_loans_only_for_adults():
    fam = _case("F02_infant")
    res = fit.compare(fam, "N_home_purchase_prep", category="mortgage", member_id="m2", amount=20000)
    assert res["items"] == [] and res["summary"]["state"] == "none" and "19세" in res["summary"]["text"]
