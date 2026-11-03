"""필요마다 갈 수 있는 길(ontology/routes.py)과 '맞는 상품이 없어요' 요약(ontology/fit.py summarize)."""

from llm import family as F
from ontology import load
from ontology.fit import compare, summarize
from ontology.products import load_products
from ontology.routes import ROUTE_LABEL, coverage
from server.app import dispatch

FAM = F.validate(F.preset("newly"))


def test_every_need_has_an_explicit_route():
    """몰래 빠진 필요가 없게: 모든 필요는 길이 하나 이상 명시돼 있다('아직 데이터 없음'·'가족이 직접'도 명시된 길)."""
    cov = coverage()
    assert set(cov) == set(load()["needs"])
    for nid, c in cov.items():
        assert c["routes"], nid
        for r in c["routes"]:
            assert r["route"] in ROUTE_LABEL, (nid, r)
            if r["route"] == "none":
                assert r["note"], (nid, r)  # 왜 데이터가 없는지 말한다


def test_real_routes_have_product_data():
    for c in coverage().values():
        for r in c["routes"]:
            if r["route"] == "real":
                assert load_products(r["category"]), r


def test_new_needs_for_real_service():
    cov = coverage()
    assert [r["category"] for r in cov["N_rent_deposit"]["routes"] if r["route"] == "real"] == ["rent_loan"]
    assert any("PG_beotimmok" in r["programs"] for r in cov["N_rent_deposit"]["routes"])
    assert [r["category"] for r in cov["N_business_fund"]["routes"]] == ["busi_loan"]
    assert {"mortgage", "credit_loan"} <= {r["category"] for r in cov["N_debt_repayment"]["routes"]}
    assert cov["N_invest_cap"]["routes"][0]["route"] == "self"


def row(limit_ok, checks=()):
    return {"limit_ok": limit_ok, "checks": list(checks)}


def test_summary_says_none_honestly():
    s = summarize([row(False), row(False)], total=10, excluded=3, no_option=5, money_given=True)
    assert s["state"] == "none" and s["text"] == "지금 조건에 맞는 상품이 없어요."
    assert "가입 조건(나이·자녀·무주택)이 안 맞는 상품 3개" in s["why"] and "한도를 넘는 상품 2개" in s["why"]
    assert summarize([], total=4, excluded=4, no_option=0, money_given=True)["state"] == "none"


def test_summary_unsure_and_ok():
    s = summarize([row(None), row(True, ["지역 조건 확인 필요(제주)"])], total=2, excluded=0, no_option=0, money_given=True)
    assert s["state"] == "unsure" and "확인이 필요한 상품만" in s["text"]
    assert summarize([row(True)], total=1, excluded=0, no_option=0, money_given=True)["state"] == "ok"
    assert summarize([row(None)], total=1, excluded=0, no_option=0, money_given=False)["state"] == "ok"  # 금액을 안 넣으면 한도는 따지지 않음


def test_compare_reports_summary():
    r = compare(FAM, "N_home_purchase_prep", category="mortgage", member_id="m0", amount=300000, months=360, home_price=40000)
    assert r["summary"]["state"] != "ok" and r["summary"]["over_limit"] > 0  # 집값 4억에 30억은 어디서도 한도 초과
    r = compare(FAM, "N_goal_saving", category="saving", member_id="m0", monthly=60, term=12)
    assert r["summary"]["state"] == "ok" and r["summary"]["ok"] > 0


def test_config_exposes_routes(monkeypatch):
    monkeypatch.delenv("VERCEL", raising=False)
    cfg = dispatch("POST", "/api/config", b"{}", {}, "t")[1]
    assert set(cfg["need_routes"]) == set(load()["needs"]) and cfg["route_labels"]["none"]
