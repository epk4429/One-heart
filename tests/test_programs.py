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
    for n, unit in re.findall(r"(\d+(?:\.\d+)?)\s*(억|천만|천|만|세)?", q.replace(",", "")):  # "4,400만 원"처럼 쉼표·만 단위도
        v = float(n)
        out.add({"억": v * 10000, "천만": v * 1000, "천": v * 1000, "만": v, "세": v}.get(unit, v))
    return out


def test_numbers_come_from_the_quote():
    """G4: 조건의 기준 숫자가 그 조건의 인용 안에 있다(단위 환산 포함)."""
    for p in P.load().values():
        for c in p["eligibility"]:
            if isinstance(c["value"], (int, float)) and not isinstance(c["value"], bool) and c["var"] not in ("home_count", "has_youth_19_34"):  # has_youth_19_34는 있다(1)/없다(0) 값이라 원문 숫자가 아니다(나이 19·34는 인용에 있음)
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
    # 2026-11-17에 더한 제도 중 육아휴직급여·근로장려금은 법령 RAG에 색인했고, 아래 4개는 근거 법령 원문이 아직 없어 표에 없다(할 일 1-7 #3). 받으면 여기서 빼고 표를 채운다.
    pending = {"PG_parent_benefit", "PG_future_youth_savings", "PG_debt_adjustment", "PG_kinfa_counseling"}  # 근거 법령(아동수당법·청년미래적금 관련 조문·채무자회생법 등)을 아직 못 받음
    assert set(table) == set(P.load()) - pending, set(P.load()) ^ set(table)
    known = {x["doc_key"] for x in laws()}
    for pid, rows in table.items():
        for label, q, want in rows:
            assert set(want) <= known, (pid, want)
            hits = search(q, want, topic=True)
            assert hits and all(h["doc_key"] in want for h in hits), (pid, label)
    for p in P.load().values():  # 제도 규칙이 법령 원문을 출처로 쓰지 않는다(법령은 RAG 쪽)
        # 예외: 비과세종합저축은 안내 페이지가 낡아(금감원 한눈에: 가입 2025.12.31까지, 65세 이상만) 현행 법령 원문을 출처로 쓴다(임의결정 105)
        assert not str(p.get("source", "")).startswith("law_") or p["id"] == "PG_tax_free_savings", p["id"]


def test_rag_search_api_takes_law_filter_and_topic_flag():
    st, out = dispatch("POST", "/api/rag/search", json.dumps({"query": "기초연금 수급권자의 범위 65세 이상 소득인정액 선정기준액",
                                                              "laws": ["law_basic_pension"], "topic": True}).encode(), {}, "t")
    if st == 404:  # 원문 찾기를 쓰지 않는 환경
        return
    assert st == 200 and out["results"] and {r["doc_key"] for r in out["results"]} == {"law_basic_pension"}
    assert any("제3조" in r["title"] for r in out["results"])


def test_programs_added_2026_11_17_match_official_pages():
    """2026-11-17에 형님이 내려받은 공식 자료로 더한 제도 5개. 정답은 원문(knowledge/sources/docs)을 사람이 읽고 적은 값(G7)."""
    from llm import family as F
    newly, elder = F.validate(F.preset("newly")), F.validate(F.preset("elder"))
    p = P.load()
    facts = {q["label"]: q["quote"] for q in p["PG_eitc"]["facts"]}  # 국세청: 단독 165 / 홑벌이 285 / 맞벌이 330만 원
    assert [facts[k] for k in ("단독가구 최대 지급액", "홑벌이가구 최대 지급액", "맞벌이가구 최대 지급액")] == ["165만 원", "285만 원", "330만 원"]
    assert "1~3개월 (상한 250만원" in p["PG_parental_leave"]["facts"][0]["quote"] and "7개월~ (상한 160만원, 통상임금 80%)" in p["PG_parental_leave"]["facts"][0]["quote"]
    pb = {q["label"]: q["quote"] for q in p["PG_parent_benefit"]["facts"]}  # 복지로 2026년 기준: 0세 월 100만원, 1세 월 50만원
    assert "월 100만원" in pb["월 지급액(0세, 2026년 기준, 가정 양육)"] and "월 50만원" in pb["월 지급액(1세, 2026년 기준, 가정 양육)"]
    assert p["PG_debt_adjustment"]["eligibility"][0]["value"] == 150000  # 총 채무 15억원 = 150,000만원
    # 판정: 아이도 청년도 없는 가족은 해당 안 됨, 청년이 있으면 나이 조건은 충족(소득·가구 요건은 기관 확인), 소득은 추정이라 확인 필요
    assert P.judge("PG_parental_leave", newly)["status"] == "not_eligible"
    assert P.judge("PG_future_youth_savings", newly)["status"] == "eligible" and P.judge("PG_future_youth_savings", elder)["status"] == "not_eligible"
    assert P.judge("PG_eitc", newly)["status"] == "not_eligible"  # 월 700 → 연 8,400만원은 기준 4,400의 1.9배(2026-11-20: 크게 넘으면 해당 안 됨)
    young_kid = {**newly, "members": newly["members"] + [{"member_id": "m9", "name": "아이", "age": 1, "role": "child"}]}
    assert P.variables(young_kid)["youngest_child_age"][0] == 1 and P.variables(young_kid)["newborn_2y"][0] is True


def test_kinfa_counseling_is_shown_with_debt_adjustment_only_in_deficit():
    """서민금융 상담은 채무조정과 같은 약속·같은 조건(매달 적자)에서만 보인다(2026-11-17). 상담은 누구나 받을 수 있어 조건 판정은 '기본 조건 충족'."""
    from llm import family as F
    from server.app import dispatch
    assert P.load()["PG_kinfa_counseling"]["gate"] == "deficit" and P.load()["PG_debt_adjustment"]["gate"] == "deficit"
    for key, expect in (("newly", set()), ("elder", {"PG_debt_adjustment", "PG_kinfa_counseling"})):
        st, out = dispatch("POST", "/api/programs/judge", json.dumps({"family": F.preset(key), "need_id": "N_debt_repayment"}).encode(), {}, "t")
        assert st == 200 and {g["program_id"] for g in out["programs"]} == expect, key
    assert P.judge("PG_kinfa_counseling", F.validate(F.preset("elder")))["status"] == "eligible"


def test_tax_free_savings_follows_current_law_not_outdated_page():
    """비과세종합저축(2026-11-17): 금감원 한눈에 페이지는 '2025.12.31까지, 65세 이상'이라 적혀 있으나 현행 조세특례제한법(2025-12-23 개정)은
    '2028년 12월 31일까지, 65세 이상 기초연금 수급자 등'이다. 규칙은 법령 원문을 따르고 기초연금 수급 여부는 가족 정보에 없어 기관 확인으로 둔다."""
    from llm import family as F
    p = P.load()["PG_tax_free_savings"]
    assert any("2028년 12월 31일" in f["quote"] for f in p["facts"]) and any("5천만원" in f["quote"] for f in p["facts"])
    assert any("기초연금 수급자" in u["quote"] for u in p["unmodeled"])
    assert P.judge("PG_tax_free_savings", F.validate(F.preset("elder")))["status"] == "eligible"      # 65세 이상 가족이 있다
    assert P.judge("PG_tax_free_savings", F.validate(F.preset("newly")))["status"] == "not_eligible"


def test_bogeumjari_rate_from_monthly_notice():
    """보금자리론 금리(2026-11-17 공시 2026-11-09): u-보금자리론 만기 10~50년 연 5.10~5.40%(고정). 정답은 공사 금리안내 표를 사람이 읽고 적은 값(G7)."""
    r = P.load()["PG_bogeumjari"]["terms"]["rate"]
    assert (r["min"], r["max"]) == (5.1, 5.4) and r["source"] == "hf_bogeumjari_rates_2026_11"
    _, text = P.source_text("hf_bogeumjari_rates_2026_11")
    assert r["quote"] in text and "공시일 : 2026년 11월 09일" in text


def _inc_family(monthly, extra=()):
    ms = [{"member_id": f"m{i}", "name": "x", "role": "x", "age": a, "easy_mode": False, "work": "working"} for i, a in enumerate((34, 32))]
    return {"members": ms, "finance": [{"item_id": "i", "owner_id": "joint", "kind": "income", "label": "월급", "amount": monthly}, *extra]}


def test_income_far_over_limit_is_not_eligible_but_near_limit_stays_unknown():
    """추정 소득이 상한의 1.3배 이상이면 해당 안 됨, 그 아래는 확인 필요, 기준 안쪽도 확인 필요(2026-11-20)."""
    assert P.judge("PG_eitc", _inc_family(750))["status"] == "not_eligible"   # 연 9,000 > 4,400×1.3
    assert P.judge("PG_eitc", _inc_family(400))["status"] == "check"          # 연 4,800: 기준을 넘지만 1.3배(5,720) 미만
    assert P.judge("PG_eitc", _inc_family(300))["status"] == "check"          # 연 3,600: 기준 안이어도 추정이라 확인 필요
    # 가족 정보로 모르는 우대(신혼 7,500)까지 넣은 가장 큰 기준으로 비교한다: 연 7,680은 버팀목에서 확인 필요
    f = _inc_family(640)
    assert P.judge("PG_beotimmok", f)["status"] == "check"


def test_programs_judge_api_hides_ineligible_programs():
    """해당하지 않는 제도는 화면용 API에서 빠진다. 안 맞는 이유가 '출산하면'처럼 앞으로 바뀔 조건뿐이면 남는다."""
    def api_fam(monthly):  # 서버 검사를 통과하도록 예시 가족의 금융 정보만 바꾼다
        f = __import__("copy").deepcopy(F.preset("newly")); f["finance"] = [{"item_id": "f1", "owner_id": "joint", "kind": "income", "label": "월급", "amount": monthly}]; return f
    fam = api_fam(750)
    st, out = dispatch("POST", "/api/programs/judge", json.dumps({"family": fam, "need_id": "N_emergency_fund"}).encode(), {}, "t")
    assert st == 200 and "PG_eitc" not in {g["program_id"] for g in out["programs"]}
    st, out = dispatch("POST", "/api/programs/judge", json.dumps({"family": api_fam(300), "need_id": "N_emergency_fund"}).encode(), {}, "t")
    assert "PG_eitc" in {g["program_id"] for g in out["programs"]}  # 기준 안쪽은 확인 필요로 남는다
    st, out = dispatch("POST", "/api/programs/judge", json.dumps({"family": F.preset("newly"), "need_id": "N_rent_deposit"}).encode(), {}, "t")
    assert all(g["status"] != "not_eligible" or all(c.get("future") for c in g["conditions"] if c["status"] == "not_met") for g in out["programs"])
