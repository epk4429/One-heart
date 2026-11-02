"""대출 공시 원본 → 대출 상품 노드 + 글 항목 규칙(한도·중도상환 수수료·우대·가입조건)(docs/12 13.1절 2단계).

정형 항목(금리 최저·최고·평균, 신용점수 구간별 금리, 상환 방식, 금리 유형, 담보 유형)은 그대로 옮긴다.
글 항목은 원문을 두고, 코드가 뽑은 규칙에 인용(quote)을 붙인다. 검사(conditions.py와 같은 원칙):
- 인용은 원문에 글자 그대로 있다(G3). 숫자는 인용 안에 있다(G4).
- 하나로 정할 수 없으면(담보 종류별 수수료율 여러 개, "내부 심사기준에 따름") 짐작하지 않고 확인 필요(G8).
"""

from __future__ import annotations

import re

from . import conditions as C

LOAN = {  # 범주 → 한글 이름
    "mortgage": "주택담보대출", "rent_loan": "전세자금대출", "credit_loan": "개인신용대출", "busi_loan": "개인사업자대출",
}
BANDS = [  # 신용점수 구간: (키, 화면 이름, 신용대출 항목, 사업자대출 항목)
    ("900+", "900점 초과", "crdt_grad_1", "val1_grad_1"), ("801-900", "801~900점", "crdt_grad_4", "val1_grad_2"),
    ("701-800", "701~800점", "crdt_grad_5", "val1_grad_3"), ("601-700", "601~700점", "crdt_grad_6", "val1_grad_4"),
    ("501-600", "501~600점", "crdt_grad_10", "val1_grad_5"), ("401-500", "401~500점", "crdt_grad_11", "val1_grad_6"),
    ("301-400", "301~400점", "crdt_grad_12", "val1_grad_7"), ("300-", "300점 이하", "crdt_grad_13", "val1_grad_8"),
]
REPAY = {"D": "split", "S": "bullet"}  # 공시 상환유형: 분할상환방식 / 만기일시상환방식
RATE_TYPE = {"F": "fixed", "C": "variable"}
NONE = re.compile(r"^\s*(없음|면제|해당\s*사항\s*없음|해당없음|-|잠정\s*폐지)\s*$")
NO_LIMIT = re.compile(r"별도\s*(로)?\s*한도\s*(가)?\s*(없음|정해져\s*있지\s*않음)|^\s*제한\s*없음\s*$")
_AMT = re.compile(r"(\d+(?:\.\d+)?)\s*(억|천만|백만|만|천)")


def won_amount(text: str) -> list[tuple[float, str]]:
    """'4.44억원' → 44400, '500백만원' → 50000, '4억 44백만원' → 44400, '5천만원' → 5000 (만원 단위). (값, 인용)"""
    out = []
    for m in re.finditer(r"((?:\d+(?:\.\d+)?\s*(?:억|천만|백만|만|천)\s*)+)원", text):
        total = 0.0
        for n, unit in _AMT.findall(m.group(1)):
            total += float(n) * {"억": 10000, "천만": 1000, "백만": 100, "만": 1, "천": 0.1}[unit]
        out.append((round(total, 2), m.group(0)))
    return out


def parse_limit(text: str) -> dict:
    """한도 글 → {ratio_pct, ratio_of, max_manwon, none, quote, status}. 비율의 기준(집값·보증금)은 ratio_of."""
    t = (text or "").strip()
    out: dict = {"ratio_pct": None, "ratio_of": None, "max_manwon": None, "none": False, "quotes": [], "status": "needs_check"}
    if not t:
        return out
    if NO_LIMIT.search(t):
        out.update(none=True, quotes=[NO_LIMIT.search(t).group(0)], status="verified")
        return out
    base = "home" if re.search(r"LTV|담보|시세|감정|분양|주택", t) else "deposit" if re.search(r"보증금|임차|임대차", t) else None
    pcts = [(float(m.group(1)), m.group(0)) for m in re.finditer(r"(\d+(?:\.\d+)?)\s*%", t)]
    rng = re.search(r"(\d+(?:\.\d+)?)\s*%?\s*[~-]\s*(\d+(?:\.\d+)?)\s*%", t)
    if pcts and base:
        hi = float(rng.group(2)) if rng else max(v for v, _ in pcts)
        out.update(ratio_pct=hi, ratio_of=base)
        out["quotes"].append(rng.group(0) if rng else next(q for v, q in pcts if v == hi))
    amts = won_amount(t)
    if amts:
        v, q = max(amts)
        out["max_manwon"] = v
        out["quotes"].append(q)
    if out["ratio_pct"] is not None or out["max_manwon"] is not None:
        out["status"] = "verified" if not re.search(r"차등|따라|심사|등에\s*따라", t) else "verified_note"
    return out


def parse_prepay(text: str) -> dict:
    """중도상환 수수료 글 → {fixed_pct, variable_pct, sliding, free_after_years, none, quotes, status}."""
    t = (text or "").strip()
    out: dict = {"fixed_pct": None, "variable_pct": None, "sliding": False, "free_after_years": None, "none": False,
                 "quotes": [], "status": "needs_check"}
    if not t:
        return out
    if NONE.match(t):
        out.update(none=True, fixed_pct=0.0, variable_pct=0.0, quotes=[t], status="verified")
        return out
    fx, vr = _labeled_rate(t, "고정", "변동"), _labeled_rate(t, "변동", "고정")
    found = [(float(m.group(1)), m.group(0)) for m in re.finditer(r"(\d+(?:\.\d+)?)\s*%", t)]
    pcts = sorted({v for v, _ in found})
    if fx and vr and not re.search(r"담보|신용대출|기업|개인\s*:", t):
        out.update(fixed_pct=fx[0], variable_pct=vr[0], quotes=[fx[1], vr[1]])
    elif len(pcts) == 1 and not re.search(r"[~∼]|이내|최대|담보", t):
        out.update(fixed_pct=pcts[0], variable_pct=pcts[0], quotes=[found[0][1]])
    elif pcts:
        out.update(fixed_pct=max(pcts), variable_pct=max(pcts), quotes=[next(q for v, q in found if v == max(pcts))])
        out["max_only"] = True  # 담보·금리·조건별로 여러 요율 → 가장 큰 값만 '최대'로 쓰고 확인 필요
    out["sliding"] = bool(re.search(r"잔여|잔존|경과", t))
    m = re.search(r"(\d+)\s*년\s*(이\s*)?(경과|후|이후)[^\n]{0,8}면제|(\d+)\s*년\s*(이내|내)", t)
    if m or re.search(r"최장\s*3\s*년|3년을\s*초과하는\s*경우\s*3년|[÷/]\s*3\s*년|3\s*년\s*-", t):
        out["free_after_years"] = int(m.group(1) or m.group(4)) if m else 3
    if out["fixed_pct"] is not None:
        out["status"] = "needs_check" if out.get("max_only") else "verified"
    return out


def _labeled_rate(t: str, label: str, other: str) -> tuple[float, str] | None:
    """'고정금리 : 중도상환대출금×0.71%', '(변동0.63%, 고정0.76%)', '(고정금리:0.57, 변동금리:0.47)%'에서 그 금리 종류의 요율.
    이름 바로 뒤(다른 금리 이름·줄바꿈 전 30자 안)의 첫 소수를 쓴다. (값, 인용)"""
    m = re.search(label + r"(?:\(혼합\))?(?:금리)?", t)
    if not m:
        return None
    window = re.split(other + r"|\n", t[m.end():m.end() + 30])[0]
    n = re.search(r"\d+\.\d+", window)
    return (float(n.group(0)), n.group(0)) if n else None


def _band_rates(row: dict, cat: str) -> dict:
    col = 2 if cat == "credit_loan" else 3
    rates = {k: (row.get(b[col]) or None) for b in BANDS for k in [b[0]]}  # 0은 그 구간에 빌려준 실적 없음 → None
    avg = row.get("crdt_grad_avg" if cat == "credit_loan" else "val1_grad_avg") or None
    return {"by_band": rates, "avg": avg}


def products_from(body: dict, source: dict) -> list[dict]:
    cat = body["category"]
    opts: dict[tuple, list] = {}
    for pg in body["pages"]:
        for o in pg.get("optionList") or []:
            opts.setdefault((o["fin_co_no"], o["fin_prdt_cd"], o.get("crdt_prdt_type")), []).append(o)  # 신용대출은 같은 상품 코드에 대출 종류가 여럿
    out = []
    for pg in body["pages"]:
        for b in pg.get("baseList") or []:
            raw = opts.get((b["fin_co_no"], b["fin_prdt_cd"], b.get("crdt_prdt_type")), [])
            node = {
                "product_id": f"PRD_{cat}_{b['fin_co_no']}_{b['fin_prdt_cd']}" + (f"_{b['crdt_prdt_type']}" if b.get("crdt_prdt_type") else ""), "provider": b["kor_co_nm"], "provider_code": b["fin_co_no"],
                "name": b["fin_prdt_nm"], "category": cat, "category_label": LOAN[cat], "group": body["group"],
                "join_way": [w.strip() for w in (b.get("join_way") or "").split(",") if w.strip()],
                "source_id": source["source_id"], "as_of": b.get("dcls_month"), "disclosed_from": b.get("dcls_strt_day"), "dev_only": True,
            }
            if cat in ("mortgage", "rent_loan"):
                node["options"] = sorted(({"house": o.get("mrtg_type_nm"), "repay": REPAY.get(o.get("rpay_type")), "repay_label": o.get("rpay_type_nm"),
                                           "rate_type": RATE_TYPE.get(o.get("lend_rate_type")), "rate_min": o.get("lend_rate_min"),
                                           "rate_max": o.get("lend_rate_max"), "rate_avg": o.get("lend_rate_avg")} for o in raw),
                                         key=lambda x: (x["house"] or "", x["repay"] or "", x["rate_type"] or ""))
                node["texts"] = {k: b.get(k) for k in ("loan_lmt", "erly_rpay_fee", "loan_inci_expn", "dly_rate") if b.get(k)}
            elif cat == "credit_loan":
                rows = {o.get("crdt_lend_rate_type_nm"): o for o in raw}
                node["loan_kind"] = b.get("crdt_prdt_type_nm")
                node["rates"] = _band_rates(rows.get("대출금리", {}), cat)
                node["rate_parts"] = {k: _band_rates(v, cat)["avg"] for k, v in rows.items() if k != "대출금리"}
                node["texts"] = {"cb_name": b.get("cb_name")} if b.get("cb_name") else {}
            else:  # busi_loan
                o = raw[0] if raw else {}
                node["rates"] = _band_rates(o, cat) | {"min": o.get("lend_rate_min"), "max": o.get("lend_rate_max"), "dcls_avg": o.get("lend_rate_avg")}
                node.update(loan_kind=b.get("fin_prdt_type_nm"), loan_type=b.get("loan_type"), use_way=b.get("use_way"),
                            repay_types=b.get("rpay_type"), rate_types=b.get("lend_rate_type"))
                node["texts"] = {k: b.get(k) for k in ("loan_limit", "loan_limit_detl", "join_deny", "join_deny_detl", "spcl_rate", "loan_term",
                                                       "erly_rpay_fee", "loan_inci_expn", "dly_rate") if b.get(k) and b.get(k) != "None"}
            node["terms"] = terms(node)
            out.append(node)
    return out


def terms(node: dict) -> dict:
    """글 항목 → 규칙 + 검사. status: verified(한도·수수료를 하나로 정함) / needs_check."""
    t = node["texts"]
    lim_text = t.get("loan_lmt") or " ".join(x for x in (t.get("loan_limit"), t.get("loan_limit_detl")) if x and x not in ("기타",))
    limit = parse_limit(lim_text)
    prepay = parse_prepay(t.get("erly_rpay_fee", ""))
    out = {"limit": limit, "prepay": prepay}
    issues = []
    for q in limit["quotes"]:
        assert q in lim_text, q  # G3
    for q in prepay["quotes"]:
        assert q in t.get("erly_rpay_fee", ""), q
    if node["category"] == "busi_loan":
        sp = t.get("spcl_rate", "")
        out["benefits"] = C.parse_benefits(sp) if sp and not C._NONE.search(sp) else {"items": [], "caps": [], "notes": [], "none": True}
        unknown = [w for w in ("전문직", "온라인셀러", "저신용자", "청년", "여성") if w in (t.get("join_deny") or "")]
        if t.get("join_deny_detl") and not re.match(r"^\s*(제한\s*없음|해당\s*사항\s*없음|해당없음|없음|-)\s*$", t["join_deny_detl"]):
            unknown.append("세부 가입조건")
        out["eligibility_unknown"] = unknown
        if unknown:
            issues.append("가입조건 확인 필요: " + ", ".join(unknown))
    if limit["status"] == "needs_check":
        issues.append("한도를 원문에서 숫자로 정할 수 없음" if lim_text else "한도가 공시에 없음")
    if prepay["status"] != "verified":
        issues.append("중도상환 수수료를 하나로 정할 수 없음(담보·조건별로 다름)" if prepay["fixed_pct"] is not None
                      else "중도상환 수수료가 공시에 없음" if not t.get("erly_rpay_fee") else "중도상환 수수료를 원문에서 숫자로 정할 수 없음")
    out["issues"] = issues
    out["status"] = "verified" if not issues else "needs_check"
    return out


def stats(products: list[dict]) -> dict:
    """대출 범주 통계: 주담대·전세는 (상환·금리 유형)별 평균 금리 분포, 신용·사업자는 신용점수 구간별 금리 분포."""
    from statistics import median
    out = {}
    for cat in LOAN:
        ps = [p for p in products if p["category"] == cat]
        if not ps:
            continue
        rows = {}
        if cat in ("mortgage", "rent_loan"):
            for p in ps:
                for o in p["options"]:
                    v = o["rate_avg"] or None
                    if v:
                        rows.setdefault(f"{o['house'] or '-'}·{o['repay_label']}·{o['rate_type']}", []).append(v)
        else:
            for p in ps:
                for k, v in p["rates"]["by_band"].items():
                    if v:
                        rows.setdefault(k, []).append(v)
        out[cat] = {"label": LOAN[cat], "products": len(ps), "groups": sorted({p["group"] for p in ps}),
                    "as_of": sorted({p["as_of"] for p in ps}),
                    "rates": {k: {"n": len(v), "min": min(v), "median": round(median(v), 2), "max": max(v)} for k, v in sorted(rows.items())}}
    return out
