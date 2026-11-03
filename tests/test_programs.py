"""제도·정책금융 규칙(ontology/programs.json)과 판정(ontology/programs.py). 원문은 knowledge/sources/docs(2026-11-03 수집)."""

import json
import re

from llm import family as F
from llm.plan import normalize_goal, policy_menu
from ontology import programs as P
from server.app import dispatch


def test_every_quote_is_in_the_official_text():
    """G3: 모든 조건·사실·조건표 인용이 원문에 글자 그대로 있고, 월지급금 표의 줄은 원문에 같은 순서로 있다."""
    assert P.check_quotes() == []


def _amounts(q: str) -> set[float]:
    """'6천만원' 6000, '1.3억원' 13000, '5.11억원' 51100, '12억원' 120000, '55세' 55 (만원·세)."""
    out = set()
    for n, unit in re.findall(r"(\d+(?:\.\d+)?)\s*(억|천만|천|세)?", q):
        v = float(n)
        out.add({"억": v * 10000, "천만": v * 1000, "천": v * 1000, "세": v}.get(unit, v))
    return out


def test_numbers_come_from_the_quote():
    """G4: 조건의 기준 숫자가 그 조건의 인용 안에 있다(단위 환산 포함)."""
    for p in P.load().values():
        for c in p["eligibility"]:
            if isinstance(c["value"], (int, float)) and not isinstance(c["value"], bool) and c["var"] != "home_count":
                assert float(c["value"]) in _amounts(c["quote"]) or c["var"] == "income_recognition_month", (p["id"], c)
        rate = p.get("terms", {}).get("rate", {})
        if rate.get("min") is not None:
            assert {rate["min"], rate["max"]} <= _amounts(rate["quote"]), p["id"]


def test_reverse_mortgage_table_reproduces_official_example():
    # 공사 원문: "70세(부부 중 연소자 기준), 3억원 주택 기준으로 매월 약 92만 3천원"
    assert P.reverse_mortgage_monthly(70, 30000)[0] == 92.3
    assert P.reverse_mortgage_monthly(54, 30000) is None
    v, basis = P.reverse_mortgage_monthly(69, 55000)  # 65·70세, 5·6억 칸 사이 → 직선 보간(추정이라고 적음)
    assert 150 < v < 170 and "추정" in basis
    assert P.reverse_mortgage_monthly(85, 150000)[0] == 406.0  # 80세 줄·12억 칸에서 더 늘지 않음


def test_younger_spouse_age_is_used():
    fam = F.validate(F.preset("elder"))  # 아버지 72, 어머니 69
    assert P.reverse_mortgage_age(fam) == 69
    g = normalize_goal(fam, {"type": "runway"})
    rm = next(x for x in policy_menu(fam, g) if x["policy"] == "reverse_mortgage")
    assert rm["monthly"] == round(P.reverse_mortgage_monthly(69, 55000)[0]) and "월지급금 예시표" in rm["basis"]


def statuses(r):
    return {c["label"]: c["status"] for c in r["conditions"]}


def test_judgments_newly():
    fam = F.validate(F.preset("newly"))
    d = P.judge("PG_didimdol", fam)
    assert statuses(d)["세대원 모두 무주택"] == "met"
    inc = next(c for c in d["conditions"] if c["label"].startswith("부부합산 연소득"))
    assert inc["status"] == "unknown" and "기준을 넘어요" in inc["hint"]  # 추정 소득(월 700 × 12)은 짐작하지 않고 확인 필요
    nb = P.judge("PG_newborn_didimdol", fam)
    assert nb["status"] == "not_eligible" and any("출산하면" in c["hint"] for c in nb["conditions"])
    assert P.judge("PG_reverse_mortgage", fam)["status"] == "not_eligible"


def test_judgments_elder():
    fam = F.validate(F.preset("elder"))
    rm = P.judge("PG_reverse_mortgage", fam)
    assert rm["status"] == "eligible" and rm["estimate"]["monthly_manwon"] > 0
    dd = P.judge("PG_didimdol", fam)  # 부모님 집이 있지만 자녀(45·41세) 세대가 신청하면 다를 수 있다(여러 세대 가족방)
    assert dd["status"] == "check" and "여러 세대" in dd["conditions"][0]["hint"]
    bp = P.judge("PG_basic_pension", fam)
    assert statuses(bp)["만 65세 이상"] == "met" and bp["status"] == "check"  # 소득인정액은 재산 환산을 못 해 확인 필요


def test_api_programs_judge():
    st, out = dispatch("POST", "/api/programs/judge", json.dumps({"family": F.preset("elder"), "need_id": "N_living_income_at_home"}).encode(), {}, "t")
    assert st == 200 and [g["program_id"] for g in out["programs"]] == ["PG_reverse_mortgage", "PG_basic_pension"]
    st, out = dispatch("POST", "/api/programs/judge", json.dumps({"family": F.preset("newly"), "need_id": "N_rent_deposit"}).encode(), {}, "t")
    assert st == 200 and {g["program_id"] for g in out["programs"]} == {"PG_beotimmok", "PG_newborn_beotimmok"}
