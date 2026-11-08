"""우대조건·가입대상 → 조건 규칙(ontology/conditions.py).

정답은 사람(Claude Code 세션)이 공시 원문을 읽고 적은 것이다(docs/06 5절 G7). 코드 추출과 따로 만든 두 번째 판독이라,
둘이 다르면 테스트가 깨진다. 원문은 knowledge/sources의 2026-10 공시(은행 권역).
"""

import json
from pathlib import Path

import pytest

from ontology import conditions as C

ROOT = Path(__file__).resolve().parents[1]
PRODUCTS = {p["product_id"]: p for cat in ("saving", "deposit")
            for p in json.loads((ROOT / f"ontology/products/{cat}.json").read_text(encoding="utf-8"))["products"]}


def rec(pid):
    return C.check_product(PRODUCTS[pid])


def benefits(r):
    """(종류, 금액) 목록. 묶음 줄(role=group)은 상한이라 뺀다."""
    return sorted((b["tag"], b["add_pp"]) for b in r["benefits"] if b.get("role") != "group")


# (상품, 원문을 읽고 적은 우대 항목, 받을 수 있는 최대 우대 %p, 상태)
GOLD = [
    # "합산 최대 연 0.2%p" 아래 가.연결 가입 0.1 / 나.오픈뱅킹 타행계좌 0.1
    ("PRD_saving_0010001_WR0001L", [("linked", 0.1), ("online", 0.1)], 0.2, "verified"),
    # "-주택청약 보유 ⏎ -iM함께예금 동시 가입 ⏎ 각 연0.20%p": 두 줄이 각 0.2
    ("PRD_saving_0010016_10521001001166004", [("linked", 0.2), ("linked", 0.2), ("loyalty", 0.1), ("online", 0.05), ("online", 0.3)], 0.85, "verified"),
    # 급여실적 1.0(①급여이체 / ②개인사업자 계좌 중복 불가) + 비대면 0.3 + 마케팅 0.2 + 농업계고 졸업 2.0 = 3.5
    ("PRD_saving_0013175_10-047-1365-0001", [("consent", 0.2), ("job", 1.0), ("job", 2.0), ("online", 0.3), ("salary", 1.0)], 3.5, "verified"),
    # 신규고객(3.0+0.1+2.0) 또는 기존고객(1.5+2.0+1.5+0.1) 중 하나 → 5.1
    ("PRD_saving_0010024_21001292", [("card", 1.5), ("card", 2.0), ("consent", 0.1), ("consent", 0.1), ("new_customer", 3.0),
                              ("salary", 1.5), ("utility", 2.0)], 5.1, "verified"),
    # 미션 0.1 + 0.2 + 대중교통(기간별 최대 0.6) + 0.1, 3년제 최고 1.0
    ("PRD_saving_0010927_010200100084", [("goal", 0.1), ("goal", 0.1), ("goal", 0.2), ("goal", 0.6)], 1.0, "verified"),
    # "자동이체 연속 성공 최고 3%p" 아래 7주차 1.0 + 26주차 2.0
    ("PRD_saving_0015130_10-01-30-355-0005", [("auto_transfer", 1.0), ("auto_transfer", 2.0)], 3.0, "verified"),
    # 저금 성공 일수 단계형 2/3/5/7/9% 중 하나 → 9.0
    ("PRD_saving_0017801_1001303001009", [("goal", 2.0), ("goal", 3.0), ("goal", 5.0), ("goal", 7.0), ("goal", 9.0)], 9.0, "verified"),
    # 5개 항목 각 0.2
    ("PRD_saving_0010024_21000111", [("auto_transfer", 0.2), ("card", 0.2), ("consent", 0.2), ("deposit_size", 0.2), ("new_customer", 0.2)], 1.0, "verified"),
    # 가입 기간별 특판 0.6 / 0.6 / 0.55 중 하나
    ("PRD_deposit_0010017_01030500510002", [("promo", 0.55), ("promo", 0.6), ("promo", 0.6)], 0.6, "verified"),
    # 목표달성 1.0(+세부 조건) + 최초거래 0.5, 최고 1.5
    ("PRD_saving_0010026_01211210113", [("goal", 1.0), ("new_customer", 0.5)], 1.5, "verified"),
    # 세부 항목 없이 "우대이율 최대 2.5%"만 → 나누지 못함
    ("PRD_saving_0010017_01020400700001", [], 2.5, "needs_check"),
    # 금리쿠폰은 금액이 원문에 없음 → 확인 필요(나머지 1.4는 공시와 맞음)
    ("PRD_saving_0010001_WR0001F", [("card", 0.3), ("consent", 0.1), ("promo", None), ("salary", 0.7), ("utility", 0.3)], 1.4, "needs_check"),
]


@pytest.mark.parametrize("pid,items,reach,status", GOLD)
def test_benefits_match_reading(pid, items, reach, status):
    r = rec(pid)
    got = benefits(r)
    assert [(t, a) for t, a in got] == sorted(items, key=lambda x: (x[0], x[1] if x[1] is not None else -1)), got
    assert r["check"]["reachable_pp"] == reach
    assert r["benefit_status"] == status


def test_disclosure_mismatch_is_flagged():
    # 신한My플러스: 원문 우대는 최고 0.2%인데 공시 최고 우대금리는 기본보다 0.75%p 높다 → 빠진 항목(이벤트 등)이 있다고 보고 확인 필요
    r = rec("PRD_deposit_0011625_207-0134-16")
    assert r["benefit_status"] == "needs_check" and any("공시 최고 우대" in i for i in r["issues"])
    # KB Star 정기예금: "없음"인데 공시 최고 우대금리가 더 높다
    assert rec("PRD_deposit_0010927_010300100335")["benefit_status"] == "needs_check"


@pytest.mark.parametrize("pid,conds,sole,unknown", [
    ("PRD_saving_0013175_10-047-1365-0001", [("age", ">=", 19), ("age", "<=", 34)], "included", ["일부제한"]),  # 만19세~만34세 개인 및 개인사업자
    ("PRD_saving_0010026_01211210113", [], "excluded", []),                                                     # 실명의 개인(개인사업자 제외)
    ("PRD_saving_0015130_10-01-30-355-0005", [("age", ">=", 14)], "unknown", []),                                # 만 14세 이상의 실명의 내국인
    ("PRD_saving_0017801_1001303001009", [], "unknown", ["다른 상품 보유"]),                                     # 토스뱅크 통장을 보유한 7세 이상
    ("PRD_saving_0015130_10-01-30-355-0007", [("age", ">=", 0), ("age", "<", 17)], "unknown", ["다른 상품 보유"]),  # 만 0세 이상 만 17세 미만
])
def test_eligibility_match_reading(pid, conds, sole, unknown):
    e = rec(pid)["eligibility"]
    got = [(c["var"], c["op"], c["value"]) for c in e["conditions"]]
    for c in conds:
        assert c in got
    assert e["entity"]["individual"] is True and e["entity"]["sole_proprietor"] == sole
    assert [u["var"] for u in e["unknown"]] == unknown


def test_quotes_and_numbers_come_from_raw():
    """G3·G4: check_product 안의 검사가 모든 상품에서 통과한다(인용은 원문에, 금액은 인용 안 숫자)."""
    for p in PRODUCTS.values():
        C.check_product(p)


def test_saved_conditions_summary():
    saved = json.loads((ROOT / "ontology/conditions.json").read_text(encoding="utf-8"))
    s = saved["summary"]
    assert s["products"] == len(PRODUCTS) == s["verified"] + s["capped"] + s["needs_check"]
    assert all(r["status"] != "verified" or not r["issues"] for r in saved["products"])
