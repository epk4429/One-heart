"""제도·정책금융 규칙(ontology/programs.json)과 판정(ontology/programs.py). 원문은 knowledge/sources/docs(2026-11-03 수집)."""

import json
import re

from llm import family as F
from llm.plan import normalize_goal, policy_menu
from engine import policies as EP
from ontology import programs as P
from server.app import dispatch


def test_every_quote_is_in_the_official_text():
    """G3: 모든 조건·사실·조건표 인용이 원문에 글자 그대로 있다(월지급금 표는 test_engine_table_matches_official_text)."""
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
    """주택연금 월지급금은 계산엔진이 계산한다(engine/policies.py, 2026-11-10). 공사 원문: "70세(부부 중 연소자 기준), 3억원 주택 기준으로 매월 약 92만 3천원"."""
    assert EP.reverse_mortgage_monthly(70, 30000)[0] == 92.3
    assert EP.reverse_mortgage_monthly(54, 30000) is None
    v, basis = EP.reverse_mortgage_monthly(69, 55000)  # 65·70세, 5·6억 칸 사이 → 직선 보간(추정이라고 적음)
    assert 150 < v < 170 and "추정" in basis
    assert EP.reverse_mortgage_monthly(85, 150000)[0] == 406.0  # 80세 줄·12억 칸에서 더 늘지 않음


def test_engine_table_matches_official_text():
    """G3: 계산엔진 데이터(data/assumptions.json)의 월지급금 표가 공사 원문과 글자 그대로 같다(인용 3개 + 표의 줄이 같은 순서로)."""
    t = F.assumptions()["reverse_mortgage"]["monthly_table"]
    _, text = P.source_text(t["source"])
    for q in (t["basis_quote"], t["example_quote"]):
        assert q in text, q
    _, rules_text = P.source_text(P.load()["PG_reverse_mortgage"]["source"])
    assert t["age_basis_quote"] in rules_text
    lines = [x.strip() for x in text.splitlines()]
    for age, row in t["rows"].items():
        want = [f"{age}세"] + [f"{v:,}" for v in row]
        assert any(lines[i:i + len(want)] == want for i in range(len(lines))), age


def test_ontology_does_not_calculate_amounts():
    """온톨로지는 판정만, 금액은 계산엔진(CLAUDE.md 5절). 제도 규칙에 금액 표·계산 함수가 없다."""
    assert "monthly_table" not in P.load()["PG_reverse_mortgage"]
    assert not hasattr(P, "reverse_mortgage_monthly") and "estimate" not in P.judge("PG_reverse_mortgage", F.validate(F.preset("elder")))


def test_younger_spouse_age_is_used():
    fam = F.validate(F.preset("elder"))  # 아버지 72, 어머니 69
    assert EP.reverse_mortgage_age(fam["members"], fam["finance"]) == 69
    g = normalize_goal(fam, {"type": "runway"})
    rm = next(x for x in policy_menu(fam, g) if x["policy"] == "reverse_mortgage")
    assert rm["monthly"] == round(EP.reverse_mortgage_monthly(69, 55000)[0]) and "월지급금 예시표" in rm["basis"]


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
    assert rm["status"] == "eligible"
    dd = P.judge("PG_didimdol", fam)  # 부모님 집이 있지만 자녀(45·41세) 세대가 신청하면 다를 수 있다(여러 세대 가족방)
    assert dd["status"] == "check" and "여러 세대" in dd["conditions"][0]["hint"]
    bp = P.judge("PG_basic_pension", fam)
    assert statuses(bp)["만 65세 이상"] == "met" and bp["status"] == "check"  # 소득인정액은 재산 환산을 못 해 확인 필요


def test_api_programs_judge():
    st, out = dispatch("POST", "/api/programs/judge", json.dumps({"family": F.preset("elder"), "need_id": "N_living_income_at_home"}).encode(), {}, "t")
    assert st == 200 and [g["program_id"] for g in out["programs"]] == ["PG_reverse_mortgage", "PG_basic_pension"]
    est = out["programs"][0]["estimate"]  # 화면 카드의 예상 월지급금: 판정 뒤 서버가 계산엔진에서 받아 붙인다
    assert est["monthly_manwon"] == EP.reverse_mortgage_monthly(69, 55000)[0] and "월지급금 예시표" in est["basis"]
    st, out = dispatch("POST", "/api/programs/judge", json.dumps({"family": F.preset("newly"), "need_id": "N_rent_deposit"}).encode(), {}, "t")
    assert st == 200 and {g["program_id"] for g in out["programs"]} == {"PG_beotimmok", "PG_newborn_beotimmok"}


def _prog_law():
    """화면(web/js/app.js PROG_LAW)의 제도 → [버튼, 검색어, 법령] 표."""
    import json as _json
    from pathlib import Path
    js = (Path(__file__).resolve().parents[1] / "web/js/app.js").read_text(encoding="utf-8")
    body = js[js.index("const PROG_LAW = {") + len("const PROG_LAW = "): js.index("};", js.index("const PROG_LAW = {")) + 1]
    body = re.sub(r"(\w+):", r'"\1":', body)
    body = re.sub(r",\s*}", "}", body)
    return _json.loads(body)


def test_every_program_card_has_its_own_law_search():
    """1-7의 1번(형님 결정 A): 제도 카드의 '이 제도의 근거 법령 보기'는 법령 RAG에서 그 제도에 맞춘 말로, 그 제도의 법령만 찾는다.
    온톨로지 제도 규칙에는 법령을 넣지 않는다(온톨로지·RAG는 서로 참조하지 않음). 새 제도를 더하면 이 표도 채워야 한다."""
    from rag.index import laws, search
    table = _prog_law()
    assert set(table) == set(P.load()), set(P.load()) ^ set(table)
    known = {x["doc_key"] for x in laws()}
    for pid, rows in table.items():
        for label, q, want in rows:
            assert set(want) <= known, (pid, want)
            hits = search(q, want, topic=True)
            assert hits and all(h["doc_key"] in want for h in hits), (pid, label)
    for p in P.load().values():  # 제도 규칙이 법령 원문을 출처로 쓰지 않는다(법령은 RAG 쪽)
        assert not str(p.get("source", "")).startswith("law_"), p["id"]


def test_rag_search_api_takes_law_filter_and_topic_flag():
    st, out = dispatch("POST", "/api/rag/search", json.dumps({"query": "기초연금 수급권자의 범위 65세 이상 소득인정액 선정기준액",
                                                              "laws": ["law_basic_pension"], "topic": True}).encode(), {}, "t")
    if st == 404:  # 원문 찾기를 쓰지 않는 환경
        return
    assert st == 200 and out["results"] and {r["doc_key"] for r in out["results"]} == {"law_basic_pension"}
    assert any("제3조" in r["title"] for r in out["results"])
