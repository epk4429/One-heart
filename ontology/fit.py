"""실제 상품을 "우리 목표에 잘 맞는 순서"로 줄 세운다(docs/06 3.6절, 임의결정 36·37). AI를 쓰지 않는다.

상품 종류마다 '좋은 상품'의 기준이 다르다.
- 저축형(적금·정기예금): 받는 돈이 많을수록. ① 가입 나이 ② 계획한 금액이 한도 안인가 ③ 만기 세후 이자(1만원 단위로 묶음)
  ④ 확인 필요 조건 ⑤ 할 일 수.
- 대출형(주담대·전세·신용·사업자): 내는 돈이 적을수록. ① 빌릴 돈이 한도 안인가 ② 총 비용(이자 + 일찍 갚으면 중도상환 수수료,
  10만원 단위로 묶음) ③ 확인 필요 조건 ④ 금리.
금리 %만으로 줄 세우지 않는다(작은 금리 차이는 원으로 보면 의미가 없을 때가 많다). 숫자는 공시 원본과 엔진(engine/product_math.py)이 낸다.
문장은 템플릿이다.
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path

from engine.fmt import won
from engine.product_math import METHODS, after_tax, deposit_interest, loan_cost, saving_interest
from llm import family as F

from . import conditions as C
from . import loans as L
from .products import load_products
from .search import load as load_ontology

REAL = {  # 상품 유형 → 공시 상품 범주. 필요 → 상품 유형 연결은 ontology/vocab.json(3단계에서 넓힘)
    "P_installment_savings": "saving", "P_term_deposit": "deposit", "P_mortgage_loan": "mortgage", "P_rent_loan": "rent_loan",
    "P_credit_loan": "credit_loan", "P_business_loan": "busi_loan",
}
SAVINGS = {"saving": "적금", "deposit": "정기예금"}
ACTIONS = {  # 화면에서 "내가 할 수 있는 것"으로 고르는 우대 종류(action)
    "salary": "급여 옮기기", "utility": "공과금 자동이체", "card": "카드 쓰기", "auto_transfer": "자동이체로 넣기",
    "consent": "마케팅 동의", "online": "앱·비대면 가입", "linked": "다른 상품 함께 가입", "deposit_size": "넣는 금액 조건 맞추기",
    "goal": "목표·미션 달성", "promo": "쿠폰·이벤트",
}
BAND_LABEL = {k: label for k, label, _, _ in L.BANDS} | {"avg": "모름(평균)"}
TOP = 5
ADULT = 19  # 대출 비교를 하는 나이(만)
REGIONS = ("서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종", "경기", "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주",
           "충청", "전라", "경상")  # 지역 전용 대출(가족 정보에 주소가 없어 판정할 수 없음)
NOTE = "우리 목표에 잘 맞는 순서예요. 추천이 아니라 정보예요. 선택과 가입은 직접 해요. 가입 전 금융회사에서 조건을 확인하세요. 개발용 예시 데이터(금감원 공시)예요."


def won_k(v: float) -> str:
    """만원 값을 천원 단위까지: 13.53 → '13만 5천원', 0.4 → '4천원', 733.5 → '733만 5천원'."""
    a = int(round(v * 10))
    man, chun = divmod(a, 10)
    eok, man = divmod(man, 10000)
    head = " ".join(x for x in (f"{eok}억" if eok else "", f"{man:,}만" if man else "", f"{chun}천" if chun else "") if x)
    return (head or "0") + "원"


def _short(provider: str) -> str:
    return provider.replace("주식회사", "").strip()


def _age_ok(conds: list[dict], age: int) -> tuple[bool, str]:
    ops = {">=": age.__ge__, "<=": age.__le__, "<": age.__lt__, ">": age.__gt__}
    for c in conds:
        if c["var"] == "age" and not ops[c["op"]](c["value"]):
            return False, f"가입 나이가 아니에요('{c['quote'].strip()}')"
    return True, ""


def interest(monthly: float, months: int, rate: float, rate_type: str, tax: float) -> dict:
    """적금(매달 같은 금액)의 만기 이자."""
    pre = saving_interest(monthly, months, rate, compound=rate_type == "복리")
    after = after_tax(pre, tax)
    return {"principal": round(monthly * months, 1), "interest_pre": round(pre, 2), "interest_after": round(after, 2),
            "total": round(monthly * months + after, 1)}


def lump_interest(amount: float, months: int, rate: float, rate_type: str, tax: float) -> dict:
    """정기예금(한 번에 맡김)의 만기 이자."""
    pre = deposit_interest(amount, months, rate, compound=rate_type == "복리")
    after = after_tax(pre, tax)
    return {"principal": round(amount, 1), "interest_pre": round(pre, 2), "interest_after": round(after, 2), "total": round(amount + after, 1)}


def compare(family: dict, need_id: str, product_type_id: str | None = None, *, category: str | None = None, member_id: str,
            commitment: dict | None = None, **params) -> dict:
    cat = category or REAL.get(product_type_id or "")
    if cat in SAVINGS:
        return _savings(family, need_id, cat, member_id=member_id, commitment=commitment, **params)
    if cat in L.LOAN:
        return _loans(family, need_id, cat, member_id=member_id, commitment=commitment, **params)
    return {"available": False}


def _conditions() -> list[dict]:
    p = Path(__file__).resolve().parent / "conditions.json"
    return json.loads(p.read_text(encoding="utf-8"))["products"] if p.exists() else []


def _head(need: dict, commitment: dict | None) -> str:
    return f"약속 {commitment['no']} '{commitment['text']}'" if commitment and commitment.get("no") else f"'{need.get('label', '')}'"


def _elig_unsure(r: dict) -> bool:
    return any(c in ELIG_CHECKS or "가입조건" in c or "지역 조건" in c for c in r["checks"])


def summarize(rows: list, total: int, excluded: int, no_option: int, money_given: bool) -> dict:
    """맞는 상품이 있는지 솔직하게: ok(조건에 맞음) / unsure(한도·자격을 공시로 정할 수 없음) / over(한도 초과).
    state: ok = 맞는 상품이 있음, unsure = 확실히 맞는 상품은 없고 확인이 필요한 상품만, none = 맞는 상품이 없음."""
    over = sum(1 for r in rows if r["limit_ok"] is False)
    ok = sum(1 for r in rows if r["limit_ok"] is not False and (r["limit_ok"] is True or not money_given) and not _elig_unsure(r))
    unsure = len(rows) - over - ok
    state = "ok" if ok else "unsure" if unsure else "none"
    parts = [f"가입 조건(나이·자녀·무주택)이 안 맞는 상품 {excluded}개" if excluded else "", f"이 기간·방식이 없는 상품 {no_option}개" if no_option else "",
             f"한도를 넘는 상품 {over}개" if over else "", f"한도·자격을 공시로 정할 수 없는 상품 {unsure}개" if unsure else ""]
    why = ", ".join(x for x in parts if x)
    text = {"ok": f"조건에 맞는 상품이 {ok}개 있어요." if money_given else f"아직 금액을 넣지 않아 한도는 따지지 않았어요. 기본 조건이 맞는 상품이 {ok}개 있어요.",
            "unsure": "지금 조건에서 확실히 맞는 상품은 없어요. 확인이 필요한 상품만 있어요.",
            "none": "지금 조건에 맞는 상품이 없어요."}[state]
    return {"state": state, "total": total, "ok": ok, "unsure": unsure, "over_limit": over, "excluded_age": excluded,
            "no_option": no_option, "text": text, "why": why}


def _result(cat: str, need: dict, member: dict, rows: list, extra: dict) -> dict:
    return {"available": True, "category": cat, "category_label": SAVINGS.get(cat) or L.LOAN[cat], "need_label": need.get("label", ""),
            "member": {"member_id": member["member_id"], "name": member["name"], "age": member["age"]},
            "items": rows, "shown": TOP, "as_of": sorted({r["evidence"]["as_of"] for r in rows}), "note": NOTE, **extra}


# ---------- 저축형: 적금·정기예금 ----------
def _option(p: dict, term: int) -> dict | None:
    opts = [o for o in p["options"] if o["term_months"] == term and o["base_rate"] is not None]
    if not opts:
        return None
    return sorted(opts, key=lambda o: (o["rsrv"] != "정액적립식", -(o["max_rate"] or o["base_rate"])))[0]  # 매달 같은 금액 = 정액적립식 먼저


ELIG_CHECKS = {"자녀 수", "여러 대상 중 하나", "다른 상품 보유", "일부제한", "서민전용", "청년", "서민", "장애", "기초생활", "다자녀", "한부모", "외국인", "임직원", "학생",
               "군인", "사업자등록", "근로자", "자녀", "부모", "여성", "남성"}


def person_of(family: dict, member_id: str, person: dict | None) -> dict:
    """계좌 주인의 사람 조건. kids = 18세 이하 자녀 수(None = 모름, 3 = 3명 이상), flags = 가족이 고른 조건(C.PERSON),
    no_home = 무주택인가(넣은 금융정보 기준: 본인 이름이거나 함께 가진 집이 없으면 무주택)."""
    p = person or {}
    kids = p.get("kids")
    homes = [i for i in family["finance"] if i["kind"] == "home" and i["owner_id"] in (member_id, "joint")]
    return {"age": F.member(family, member_id)["age"], "kids": None if kids is None else min(int(kids), 3),
            "flags": {f for f in p.get("flags") or [] if f in C.PERSON}, "no_home": not homes}


def _elig_person(rec: dict, me: dict) -> tuple[str | None, list[str], list[str]]:
    """가입대상의 사람 조건(자녀 수·무주택) 판정 → (가입할 수 없는 이유 | None, 아직 모르는 조건, 넣은 정보로 맞다고 본 조건)."""
    left, assumed = [], []
    for u in rec["eligibility"]["unknown"]:
        if u["var"] == "무주택":
            if not me["no_home"]:
                return f"무주택인 사람만 가입할 수 있어요('{u['quote']}')", [], []
            assumed.append("넣은 금융정보에 본인·공동 명의 집이 없어 무주택으로 봤어요")
            continue
        if u["var"] == "자녀 수":
            st, _ = C.judge_person(u["who"], me["age"], me["kids"], me["flags"])
            if st == "not_met":
                return f"가입 조건이 {C.person_label(u['who'])}이에요('{u['quote']}')", [], []
            if st == "met":
                assumed.append(f"고른 자녀 수로 가입 조건({C.person_label(u['who'])})에 맞아요")
                continue
        left.append(u["var"])
    return None, left, assumed


def _savings(family: dict, need_id: str, cat: str, *, member_id: str, commitment: dict | None, term: int = 12,
             actions: list[str] | None = None, monthly: float | None = None, amount: float | None = None,
             person: dict | None = None) -> dict:
    """적금은 monthly(매달 넣을 돈), 정기예금은 amount(한 번에 맡길 돈). person은 사람 조건(person_of)."""
    o = load_ontology()
    cond = {r["product_id"]: r for r in _conditions()}
    tax = F.assumptions()["interest_tax"]["rate"]
    who = F.member(family, member_id)
    me = person_of(family, member_id, person)
    picked = {a for a in (actions or []) if a in ACTIONS}
    money_in = monthly if cat == "saving" else amount
    rows, excluded, no_term = [], [], 0
    for p in load_products(cat):
        opt = _option(p, term)
        if opt is None:
            no_term += 1
            continue
        rec = cond.get(p["product_id"])
        ok, why = _age_ok(rec["eligibility"]["conditions"], who["age"])
        no, left, assumed = _elig_person(rec, me)
        if not ok or no:
            excluded.append({"name": p["name"].replace("\n", " "), "provider": _short(p["provider"]), "reason": why or no})
            continue
        gap = max(0.0, (opt["max_rate"] or opt["base_rate"]) - opt["base_rate"])
        items, mine, not_mine = [], [], []
        for b in rec["benefits"]:  # 사람 조건: 해당하면 우대에 넣고(명수별이면 그 금리), 해당 안 되면 뺀다
            st, pp = C.judge_person(b["who"], me["age"], me["kids"], me["flags"]) if b.get("who") and b.get("role") != "group" else (None, None)
            if st == "met":
                b = {**b, "tag": "_person", "add_pp": pp if pp is not None else b["add_pp"]}
                mine.append(b)
            elif st == "not_met":
                not_mine.append(b)
                b = {**b, "add_pp": 0}
            items.append(b)
        cap = rec["check"]["cap_pp"]
        want = C.applicable(items, picked | {"_person"})
        bonus = round(min(want, gap, cap if cap is not None else gap), 2)
        held = round(want - bonus, 2) if want > bonus + 0.005 else 0  # 원문 우대 합이 공시 최고 우대금리보다 커서 금리에 다 넣지 않은 몫
        rate = round(opt["base_rate"] + bonus, 2)
        got = [b for b in items if b.get("role") != "group" and b["tag"] in picked and (b["add_pp"] or 0) > 0]
        more = [b for b in items if b.get("role") != "group" and b["kind"] == "action" and b["tag"] not in picked and (b["add_pp"] or 0) > 0]
        maybe = [b for b in items if b.get("role") != "group" and b["kind"] in ("attribute", "relation") and b["tag"] != "_person"
                 and (b["add_pp"] or 0) > 0]
        unknown_amt = [b for b in items if b["add_pp"] is None]
        checks = left
        if rec["benefit_status"] == "needs_check":
            checks.append("우대조건(원문과 공시 숫자가 다르거나 금액이 없음)")
        if cat == "saving":
            limit = rec["limits"]["monthly_max_manwon"]
            money = interest(monthly, term, rate, opt["rate_type"] or "단리", tax) if monthly else None
        else:
            limit = round(p["max_limit"] / 10000, 1) if p.get("max_limit") else None  # 공시 최고한도(원)
            money = lump_interest(amount, term, rate, opt["rate_type"] or "단리", tax) if amount else None
        unlimited = cat == "saving" and rec["limits"].get("unlimited")
        fits = None if money_in is None else (True if unlimited else None if limit is None else money_in <= limit + 1e-9)
        rows.append({
            "product_id": p["product_id"], "name": p["name"].replace("\n", " "), "provider": _short(p["provider"]), "term_months": term,
            "rsrv": opt["rsrv"], "rate_type": opt["rate_type"], "base_rate": opt["base_rate"], "max_rate": opt["max_rate"],
            "my_rate": rate, "limit_manwon": limit, "limit_ok": fits, "money": money,
            "got": [{"label": ACTIONS.get(b["tag"], b["tag"]), "pp": b["add_pp"]} for b in got]
                   + [{"label": "해당돼요 · " + C.person_label(b["who"]), "pp": b["add_pp"], "person": True, "quote": b["quote"]} for b in mine if b["add_pp"]],
            "assumed": assumed, "held_pp": held,
            "not_mine": [{"label": C.person_label(b["who"]), "pp": b["add_pp"]} for b in not_mine if b["add_pp"]],
            "more": [{"label": ACTIONS.get(b["tag"], b["tag"]), "pp": b["add_pp"]} for b in more],
            "maybe": [{"label": C.person_label(b["who"]) if b.get("who") else C.TAG[b["tag"]]["label"], "pp": b["add_pp"], "quote": b["quote"]}
                      for b in maybe],
            "checks": checks + (["금액이 원문에 없는 우대 " + str(len(unknown_amt)) + "개"] if unknown_amt else []),
            "evidence": {"benefits": [b["quote"] for b in items if b.get("role") != "group"] + [c["quote"] for c in rec["benefit_caps"]],
                         "join_member": p["texts"].get("join_member"), "limit_quote": rec["limits"]["quote"],
                         "caveats": rec["check"]["caveats"], "source_id": p["source_id"], "as_of": p["as_of"]},
            "conditions_status": rec["status"],
        })

    def key(r):
        lim = 2 if r["limit_ok"] is False else (1 if r["limit_ok"] is None and money_in is not None else 0)
        gain = math.floor(r["money"]["interest_after"]) if r["money"] else math.floor(r["my_rate"] * 10)  # 1만원(금액 없으면 0.1%p) 단위
        elig = any(c in ELIG_CHECKS for c in r["checks"])  # 가입할 수 있는지 모르면 이자보다 먼저 뒤로
        return (lim, elig, -gain, len(r["checks"]) > 0, _todo(r), -r["my_rate"])
    rows.sort(key=key)
    need = o["needs"].get(need_id, {})
    for i, r in enumerate(rows):
        r["reasons"] = _saving_reasons(r, cat, need, commitment, money_in)
        if i:
            r["why_lower"] = _saving_lower(r, rows[0], cat, money_in)
    summary = summarize(rows, len(rows) + len(excluded) + no_term, len(excluded), no_term, money_in is not None)
    return _result(cat, need, who, rows, {"term_months": term, "monthly": monthly, "amount": amount, "actions": ACTIONS, "person": {"options": C.PERSON, "kids": me["kids"],
                                          "flags": sorted(me["flags"]), "no_home": me["no_home"]},
                                          "excluded": excluded, "no_term": no_term, "tax": F.assumptions()["interest_tax"],
                                          "summary": summary})


def _todo(r: dict) -> int:
    """지켜야 할 우대 조건 수(사람 조건 해당은 할 일이 아니다)."""
    return sum(1 for x in r["got"] if not x.get("person"))


def _saving_reasons(r: dict, cat: str, need: dict, commitment: dict | None, money_in: float | None) -> list[str]:
    what = "원금 보장 적금" if cat == "saving" else "원금 보장 정기예금"
    out = [f"{_head(need, commitment)}에 맞는 {what}이고, {r['term_months']}개월 뒤 만기예요."]
    if money_in:
        unit = "매달 " if cat == "saving" else "한 번에 "
        lim = "월 한도" if cat == "saving" else "최고 한도"
        if r["limit_ok"] is True and r["limit_manwon"] is None:
            out.append(f"{unit}{won(money_in)}을 넣을 수 있어요(원문에 {lim}가 없다고 적혀 있어요).")
        elif r["limit_ok"] is True:
            out.append(f"{unit}{won(money_in)}을 넣을 수 있어요({lim} {won(r['limit_manwon'])}).")
        elif r["limit_ok"] is False:
            out.append(f"{lim}가 {won(r['limit_manwon'])}이라 {unit}{won(money_in)}을 다 넣지는 못해요.")
        else:
            out.append(f"{lim}는 공시 원문에 없어요. 금융회사에서 확인이 필요해요.")
    acts = [x["label"] for x in r["got"] if not x.get("person")]
    mine = [x["label"].removeprefix("해당돼요 · ") for x in r["got"] if x.get("person")]
    if acts:
        out.append(f"우대 조건({', '.join(acts)})을 지키면 연 {r['my_rate']:.2f}%예요.")
    else:
        out.append(f"따로 할 일 없이 연 {r['my_rate']:.2f}%예요.")
    out += [f"{a}(가입할 때 금융회사가 확인해요)." for a in r["assumed"]]
    if r["held_pp"]:
        out.append(f"원문대로면 우대가 {r['held_pp']}%p 더 있지만 공시 최고금리를 넘어서 금리에 넣지 않았어요(금융회사 확인).")
    if mine:
        out.append(f"{', '.join(mine)}에 해당해서 우대가 들어갔어요(가입할 때 금융회사가 증빙으로 확인해요).")
    if r["money"]:
        m = r["money"]
        out.append(f"만기에 약 {won_k(m['total'])}(넣은 돈 {won(m['principal'])} + 세후 이자 약 {won_k(m['interest_after'])})을 받아요.")
    if r["maybe"]:
        out.append("해당되면 더 받아요: " + ", ".join(f"{x['label']} +{x['pp']}%p" for x in r["maybe"]) + "(금융회사 확인).")
    return out


def _saving_lower(r: dict, top: dict, cat: str, money_in: float | None) -> str:
    lim = "월 한도" if cat == "saving" else "최고 한도"
    if r["limit_ok"] is False and top["limit_ok"] is not False:
        return f"{lim}({won(r['limit_manwon'])})가 넣을 돈보다 적어요."
    if money_in and r["limit_ok"] is None and top["limit_ok"] is True:
        return f"{lim}를 원문에서 확인할 수 없어요."
    if r["money"] and top["money"]:
        d = top["money"]["interest_after"] - r["money"]["interest_after"]
        if d >= 0.1:
            return f"만기 세후 이자가 약 {won_k(d)} 적어요."
    if r["checks"] and not top["checks"]:
        return "확인이 필요한 조건이 있어요."
    if _todo(r) > _todo(top):
        return "같은 이자를 받으려면 할 일이 더 많아요."
    return "금리가 조금 낮아요."


# ---------- 대출형: 주담대·전세·신용·사업자 ----------
def _loan_rate(p: dict, cat: str, repay: str, rate_pref: str, house: str, band: str) -> dict | None:
    """그 사람이 '보통 받는 금리'. 주담대·전세: 맞는 옵션 중 지난달 평균이 가장 낮은 것(평균이 없으면 최저~최고 중간, 표시).
    신용·사업자: 신용점수 구간 금리(모르면 평균)."""
    if cat in ("mortgage", "rent_loan"):
        cands = [o for o in p["options"] if o["repay"] == repay and (rate_pref == "any" or o["rate_type"] == rate_pref)
                 and (cat == "rent_loan" or not house or o["house"] == house)]
        best = None
        for o in cands:
            typical = o["rate_avg"] or (round((o["rate_min"] + o["rate_max"]) / 2, 2) if o["rate_min"] and o["rate_max"] else None)
            if typical and (best is None or typical < best["rate"]):
                best = {"rate": typical, "rate_min": o["rate_min"], "rate_max": o["rate_max"], "rate_type": o["rate_type"],
                        "avg_missing": not o["rate_avg"]}
        return best
    rates = p["rates"]
    v = rates["avg"] if band == "avg" else rates["by_band"].get(band)
    missing = False
    if not v and band == "avg":  # 구간 평균이 비어 있으면(0) 공시 평균 → 최저~최고 중간 순서로(표시)
        v = rates.get("dcls_avg") or (round((rates["min"] + rates["max"]) / 2, 2) if rates.get("min") and rates.get("max") else None)
        missing = True
    if not v:
        return None
    vals = [x for x in rates["by_band"].values() if x] + [x for x in (rates.get("min"), rates.get("max")) if x]
    return {"rate": v, "rate_min": min(vals, default=v), "rate_max": max(vals, default=v), "rate_type": None, "avg_missing": missing}


def _prepay_fee(terms: dict, rate_type: str | None, remaining: float, prepay_month: int, months: int) -> tuple[float | None, str]:
    pp = terms["prepay"]
    if pp["none"]:
        return 0.0, "중도상환 수수료가 없어요."
    pct = pp["fixed_pct"] if rate_type == "fixed" else pp["variable_pct"] if rate_type == "variable" else \
        max(x for x in (pp["fixed_pct"], pp["variable_pct"]) if x is not None) if pp["fixed_pct"] is not None else None
    if pct is None:
        return None, "중도상환 수수료는 공시로 정할 수 없어요(확인 필요)."
    free = (pp["free_after_years"] or 0) * 12
    if free and prepay_month >= free:
        return 0.0, f"{pp['free_after_years']}년이 지나 갚으면 중도상환 수수료가 없어요."
    period = min(months, free) if free else months
    fee = remaining * pct / 100 * (max(0, period - prepay_month) / period if pp["sliding"] else 1)
    return round(fee, 2), f"{prepay_month}개월에 남은 {won(remaining)}을 갚으면 수수료 약 {won_k(fee)}(요율 {pct}%{', 남은 기간에 비례' if pp['sliding'] else ''})."


def _loans(family: dict, need_id: str, cat: str, *, member_id: str, commitment: dict | None, amount: float | None = None,
           months: int = 360, repay: str = "split", method: str = "equal_payment", rate_pref: str = "any", house: str = "아파트",
           home_price: float | None = None, deposit_amount: float | None = None, band: str = "avg",
           prepay_month: int | None = None) -> dict:
    """amount(빌릴 돈, 만원), months(기간), repay(split 나눠 갚기 / bullet 만기에 한 번에), method(나눠 갚을 때 원리금균등·원금균등),
    rate_pref(any/fixed/variable), house(주담대 담보: 아파트/아파트외), home_price(주담대 한도 비율 계산용 집값),
    deposit_amount(전세 한도 비율 계산용 보증금), band(신용·사업자대출 신용점수 구간), prepay_month(그 달에 다 갚을 계획)."""
    o = load_ontology()
    who = F.member(family, member_id)
    how = "bullet" if repay == "bullet" else method
    need = o["needs"].get(need_id, {})
    if who["age"] < ADULT:  # 대출은 어른 이름으로만 비교한다(임의결정 44)
        total = len(load_products(cat))
        sm = {"state": "none", "total": total, "ok": 0, "unsure": 0, "over_limit": 0, "excluded_age": total, "no_option": 0,
              "text": f"대출은 어른(만 {ADULT}세 이상) 이름으로 비교해요.", "why": f"{who['name']}님은 {who['age']}세예요"}
        return _result(cat, need, who, [], {"amount": amount, "months": months, "repay": repay, "method": how, "method_label": METHODS[how],
                                            "rate_pref": rate_pref, "band": band, "band_label": BAND_LABEL.get(band, band), "no_match": 0,
                                            "excluded": [], "bands": BAND_LABEL, "summary": sm})
    rows, no_match, excluded = [], 0, []
    for p in load_products(cat):
        r = _loan_rate(p, cat, repay, rate_pref, house, band)
        if r is None:
            no_match += 1
            continue
        if cat == "busi_loan":  # 가입조건(세부)의 나이: "만 39세이하 청년창업기업", "20세부터 74세 이하"
            ok, why = _age_ok(C.parse_eligibility(p["texts"].get("join_deny_detl") or "", "1")["conditions"], who["age"])
            if not ok:
                excluded.append({"name": p["name"].replace("\n", " "), "provider": _short(p["provider"]), "reason": why})
                continue
        t = p["terms"]
        lim = t["limit"]
        cap = None
        if lim["ratio_pct"] is not None:
            base = home_price if lim["ratio_of"] == "home" else deposit_amount if lim["ratio_of"] == "deposit" else None
            cap = round(base * lim["ratio_pct"] / 100, 1) if base else None
        if lim["max_manwon"] is not None:
            cap = min(cap, lim["max_manwon"]) if cap is not None else (lim["max_manwon"] if lim["ratio_pct"] is None else None)
        limit_ok = True if lim["none"] else (None if amount is None or cap is None else amount <= cap + 1e-9)
        cost = loan_cost(amount, r["rate"], months, how, prepay_month) if amount else None
        fee, fee_text = (_prepay_fee(t, r["rate_type"], cost["remaining_at_prepay"], prepay_month, months)
                         if cost and prepay_month and prepay_month < months else (0.0, ""))
        checks = list(t["issues"]) + (["지난달 평균 금리가 공시에 없어 최저~최고의 중간으로 계산"] if r["avg_missing"] and cat in ("mortgage", "rent_loan")
                                      else ["신용점수 구간 금리가 없어 공시 평균·범위로 계산"] if r["avg_missing"] else [])
        where = p["name"] + " " + (p["texts"].get("join_deny_detl") or "")
        m = re.search(r"(?:^|[\s(])([가-힣]{2,4}(?:특별자치도|광역시|특별시|시|군|도))(?=[\s)]|$)", where)
        region = m.group(1) if m else next((g for g in REGIONS if g in where), None)
        if region and cat == "busi_loan":
            checks.append(f"지역 조건 확인 필요({region})")
        rows.append({
            "product_id": p["product_id"], "name": p["name"].replace("\n", " "), "provider": _short(p["provider"]),
            "loan_kind": p.get("loan_kind"), "my_rate": r["rate"], "rate_min": r["rate_min"], "rate_max": r["rate_max"],
            "rate_type": r["rate_type"], "limit_manwon": cap, "limit_ok": limit_ok, "cost": cost, "prepay_fee": fee,
            "total_cost": round(cost["total_interest"] + (fee or 0), 2) if cost else None, "fee_text": fee_text, "checks": checks,
            "evidence": {"texts": {k: v for k, v in p["texts"].items() if k not in ("cb_name",)}, "limit_quotes": lim["quotes"],
                         "prepay_quotes": t["prepay"]["quotes"], "benefits": [b["quote"] for b in t.get("benefits", {}).get("items", [])],
                         "source_id": p["source_id"], "as_of": p["as_of"]},
        })

    def key(x):
        lim = 2 if x["limit_ok"] is False else (1 if x["limit_ok"] is None and amount is not None else 0)
        c = math.floor(x["total_cost"] / 10) if x["total_cost"] is not None else math.floor(x["my_rate"] * 10)  # 10만원(금액 없으면 0.1%p) 단위
        elig = any(k in c2 for c2 in x["checks"] for k in ("가입조건", "지역 조건"))  # 받을 수 있는지 모르면(지역·자격 전용) 비용보다 먼저 뒤로
        return (lim, elig, c, len(x["checks"]) > 0, x["my_rate"])
    rows.sort(key=key)
    for i, x in enumerate(rows):
        x["reasons"] = _loan_reasons(x, cat, need, commitment, amount, months, how, band, home_price, deposit_amount)
        if i:
            x["why_lower"] = _loan_lower(x, rows[0], amount)
    summary = summarize(rows, len(rows) + no_match + len(excluded), len(excluded), no_match, amount is not None)
    return _result(cat, need, who, rows, {"amount": amount, "months": months, "repay": repay, "method": how, "method_label": METHODS[how],
                                          "rate_pref": rate_pref, "band": band, "band_label": BAND_LABEL.get(band, band),
                                          "no_match": no_match, "excluded": excluded, "bands": BAND_LABEL, "summary": summary})


def _loan_reasons(x: dict, cat: str, need: dict, commitment: dict | None, amount: float | None, months: int, how: str,
                  band: str, home_price: float | None, deposit_amount: float | None) -> list[str]:
    out = [f"{_head(need, commitment)}에 쓰는 {L.LOAN[cat]}이에요."]
    if cat in ("mortgage", "rent_loan"):
        rt = {"fixed": "고정금리", "variable": "변동금리"}.get(x["rate_type"], "")
        rng = f", 조건이 좋으면 연 {x['rate_min']:.2f}%부터" if x["rate_min"] and x["rate_min"] < x["my_rate"] else ""
        src = "최저~최고의 중간" if "지난달 평균 금리가 공시에 없어 최저~최고의 중간으로 계산" in x["checks"] else "지난달 평균"
        out.append(f"보통 받는 금리는 {rt} 연 {x['my_rate']:.2f}%예요({src}{rng}).")
    else:
        out.append(f"신용점수 {BAND_LABEL.get(band, band)} 기준 연 {x['my_rate']:.2f}%예요(구간별 연 {x['rate_min']:.2f}~{x['rate_max']:.2f}%).")
    if amount and x["cost"]:
        c = x["cost"]
        yrs = f"{months // 12}년" if months % 12 == 0 else f"{months}개월"
        if how == "bullet":
            out.append(f"{won(amount)}을 {yrs} 동안 빌리면 매달 이자 약 {won_k(c['first_payment'])}, 만기에 원금 {won(amount)}을 갚아요. 총 이자는 약 {won_k(c['total_interest'])}이에요.")
        else:
            out.append(f"{won(amount)}을 {yrs} 동안 {METHODS[how]}으로 갚으면 첫 달 약 {won_k(c['first_payment'])}, 총 이자는 약 {won_k(c['total_interest'])}이에요.")
    if x["limit_ok"] is True and x["limit_manwon"]:
        out.append(f"빌릴 돈이 한도({won(x['limit_manwon'])}) 안이에요.")
    elif x["limit_ok"] is True:
        out.append("공시상 별도 한도가 없어요.")
    elif x["limit_ok"] is False:
        out.append(f"한도가 약 {won(x['limit_manwon'])}이라 {won(amount)}을 다 빌리기 어려워요.")
    elif amount:
        need_in = "집값을 넣으면" if cat == "mortgage" else "보증금을 넣으면" if cat == "rent_loan" else ""
        out.append(f"한도는 {need_in + ' 계산할 수 있어요' if need_in and not (home_price or deposit_amount) else '공시로 정할 수 없어요(확인 필요)'}.")
    if x["fee_text"]:
        out.append(x["fee_text"])
    return out


def _loan_lower(x: dict, top: dict, amount: float | None) -> str:
    if x["limit_ok"] is False and top["limit_ok"] is not False:
        return "빌릴 돈이 한도를 넘어요."
    if amount and x["limit_ok"] is None and top["limit_ok"] is True:
        return "한도를 확인할 수 없어요."
    if x["total_cost"] is not None and top["total_cost"] is not None:
        d = x["total_cost"] - top["total_cost"]
        if d >= 0.1:
            return f"총 비용(이자{' + 수수료' if x['prepay_fee'] else ''})이 약 {won_k(d)} 더 많아요."
    if x["checks"] and not top["checks"]:
        return "확인이 필요한 조건이 있어요."
    return "금리가 조금 높아요."
