"""실제 상품을 '우리 목표에 잘 맞는 순서'로(ontology/fit.py, /api/products/fit)."""

import json

import pytest

from llm import family as F
from ontology import conditions as C
from ontology.fit import compare, interest
from server.app import dispatch

FAM = F.validate(F.preset("newly"))
KAKAO = "PRD_saving_0015130_10-01-30-355-0002"  # 카카오뱅크 자유적금: 기본 3.85%, 자동이체 +0.2%p, 월 300만원 이하
MYKIDS = "PRD_saving_0014674_01012000200000000006"  # 케이뱅크 마이키즈 적금: 만 17세 미만


def run(**kw):
    args = dict(monthly=60, term=12, member_id="m1", actions=[])
    args.update(kw)
    return compare(FAM, "N_leave_fund", "P_installment_savings", **args)


def row(res, pid):
    return next(r for r in res["items"] if r["product_id"] == pid)


def test_interest_simple_and_monthly_compound():
    # 단리 적금: 60만원 × 12개월, 연 4.1% → 이자 60 × 0.041 × (12·13/2)/12 = 15.99만원, 세후(15.4%) 13.53만원
    m = interest(60, 12, 4.1, "단리", 15.4)
    assert (m["principal"], m["interest_pre"], m["interest_after"], m["total"]) == (720, 15.99, 13.53, 733.5)
    assert interest(60, 12, 4.1, "복리", 15.4)["interest_pre"] > m["interest_pre"]


def test_my_rate_follows_chosen_actions():
    assert row(run(), KAKAO)["my_rate"] == 3.85  # 아무것도 안 고르면 기본금리
    r = row(run(actions=["auto_transfer"]), KAKAO)
    assert r["my_rate"] == 4.05 and [g["label"] for g in r["got"]] == ["자동이체로 넣기"]


def test_age_excludes_and_explains():
    res = run()
    assert MYKIDS not in {r["product_id"] for r in res["items"]}
    assert any("만 17세 미만" in e["reason"] for e in res["excluded"])


def test_monthly_limit_orders_first():
    res = run(monthly=400)  # 월 한도 300만원인 상품은 400만원을 다 못 넣는다
    k = row(res, KAKAO)
    assert k["limit_ok"] is False and any("다 넣지는 못해요" in t for t in k["reasons"])
    first_bad = next(i for i, r in enumerate(res["items"]) if r["limit_ok"] is False)
    assert all(r["limit_ok"] is not False for r in res["items"][:first_bad])


def test_reasons_are_information_not_recommendation():
    res = run(actions=["auto_transfer", "consent"])
    assert "우리 목표에 잘 맞는 순서" in res["note"]
    text = " ".join(t for r in res["items"] for t in r["reasons"] + [r.get("why_lower", "")])
    assert "추천" not in text and "가입하세요" not in text
    assert res["items"][0]["money"]["total"] > 720  # 넣은 돈 + 세후 이자


def test_applicable_respects_one_of_group():
    rec = C.check_product(next(p for p in json.load(open("ontology/products/saving.json", encoding="utf-8"))["products"]
                               if p["product_id"] == "PRD_saving_0013175_10-047-1365-0001"))  # 급여실적 1.0(①급여 / ②개인사업자 중복 불가)
    assert C.applicable(rec["benefits"], set()) == 0
    assert C.applicable(rec["benefits"], {"salary"}) == 1.0
    assert C.applicable(rec["benefits"], {"salary", "online", "consent"}) == 1.5


def call(body):
    return dispatch("POST", "/api/products/fit", json.dumps(body).encode(), {}, "t")


def test_api_fit_and_validation(monkeypatch):
    monkeypatch.delenv("VERCEL", raising=False)
    monkeypatch.delenv("REAL_PRODUCTS", raising=False)
    base = {"family": F.preset("newly"), "need_id": "N_leave_fund", "product_type_id": "P_installment_savings", "member_id": "m1"}
    st, out = call({**base, "monthly": 60, "term_months": 12, "actions": ["auto_transfer"]})
    assert st == 200 and out["items"] and out["available"] is True
    assert call({**base, "term_months": 7})[0] == 400
    assert call({**base, "monthly": -5})[0] == 400
    assert call({**base, "product_type_id": "P_joint_account"})[1]["available"] is False


def test_api_on_in_public_and_switchable(monkeypatch):
    monkeypatch.setenv("VERCEL", "1")  # 공개 배포에서도 켠다(2026-11-03 형님 결정)
    monkeypatch.delenv("REAL_PRODUCTS", raising=False)
    body = {"family": F.preset("newly"), "need_id": "N_leave_fund", "product_type_id": "P_installment_savings", "member_id": "m1"}
    assert call(body)[0] == 200
    assert dispatch("POST", "/api/config", b"{}", {}, "t")[1]["real_products"] is True
    monkeypatch.setenv("REAL_PRODUCTS", "0")
    assert call(body)[0] == 404
    assert dispatch("POST", "/api/config", b"{}", {}, "t")[1]["real_products"] is False
