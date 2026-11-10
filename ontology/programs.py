"""제도·정책금융 판정(docs/06 3.7절). 규칙은 ontology/programs.json(공식 원문 인용), 판정은 이 코드.

판정은 세 가지: met(충족) / not_met(불충족) / unknown(확인 필요).
- 가족 정보로 확실히 아는 값(나이, 집 수)은 그대로 판정한다.
- 추정 값(연소득 = 매달 수입 × 12, 순자산 = 넣은 자산 − 대출, 공시가격은 모르고 시세만 앎)은 짐작해서 충족·불충족을 정하지 않고
  unknown으로 두되, "넣은 정보로 추정하면 기준 안이에요/넘어요"라는 방향(hint)을 붙인다(G8 보수적 기본값).
- unmodeled(세대주·신용·중복대출 등)는 가족 정보로 판정할 수 없어 늘 '기관 확인' 목록으로 보여 준다.
전체 결과: not_met이 하나라도 있으면 해당 안 됨 / 모두 met이면 기본 조건 충족 / 나머지는 확인 필요.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HERE = Path(__file__).resolve().parent
CHILD = re.compile(r"자녀|아들|딸|아이|첫째|둘째|막내")


@lru_cache(maxsize=1)
def load() -> dict:
    return {p["id"]: p for p in json.loads((HERE / "programs.json").read_text(encoding="utf-8"))["programs"]}


@lru_cache(maxsize=16)
def source_text(key: str) -> tuple[str, str]:
    """원문 저장소의 가장 최근 스냅샷: (source_id, 글)."""
    idx = json.loads((ROOT / "knowledge/sources/index.json").read_text(encoding="utf-8"))["sources"]
    s = sorted((x for x in idx if x.get("doc_key") == key), key=lambda x: x["source_id"])[-1]
    return s["source_id"], (ROOT / s["file"]).read_text(encoding="utf-8")


SPOUSE_GAP = 20  # 집 주인과 나이 차이가 이 안인 55세 이상 가족은 배우자'일 수 있음'(관계는 가족 정보에 확실히 없다)


def owner_ages(family: dict) -> list[int]:
    """집 주인 나이. 공동 명의(joint)는 성인 가족 중 가장 나이 많은 사람을 주인 쪽으로 본다."""
    ms = {m["member_id"]: m for m in family["members"]}
    out = set()
    for i in family["finance"]:
        if i["kind"] == "home":
            if i["owner_id"] in ms:
                out.add(ms[i["owner_id"]]["age"])
            else:
                out.add(max(m["age"] for m in family["members"]))
    return sorted(out, reverse=True)


def multi_generation(family: dict) -> bool:
    """가족방에 성인 세대가 둘 이상(성인끼리 20살 이상 차이) → 누가 한 세대인지 몰라 '세대원 무주택·부부합산 소득'을 확실히 정할 수 없다."""
    adults = [m["age"] for m in family["members"] if m["age"] >= 19]
    return len(adults) >= 2 and max(adults) - min(adults) >= 20


def variables(family: dict) -> dict:
    """가족 정보 → 규칙 변수. (값, 추정 여부)."""
    f = family["finance"]
    tot = lambda *k: sum(i["amount"] for i in f if i["kind"] in k)  # noqa: E731
    ages = [m["age"] for m in family["members"]]
    seniors = {m["member_id"] for m in family["members"] if m["age"] >= 65}
    children = sum(1 for m in family["members"] if m["age"] < 19)  # 다자녀 기준은 미성년 자녀(성인 자녀는 세지 않음)
    owners = owner_ages(family)
    return {
        "eldest_age": (max(ages), False),
        "owner_age": (owners[0] if owners else 0, False),
        "home_count": (sum(1 for i in f if i["kind"] == "home"), False),
        "home_value_gongsi": (tot("home"), True),  # 가족은 시세를 넣는다. 공시가격은 보통 시세보다 낮다
        "household_income_year": (round(tot("income") * 12, 1), True),
        "net_assets": (round(tot("deposit", "investment", "lease_deposit", "home") - tot("loan"), 1), True),
        "newborn_2y": (any(m["age"] <= 1 for m in family["members"]), False),
        "income_recognition_month": (sum(i["amount"] for i in f if i["kind"] == "income" and i["owner_id"] in seniors), True),  # 65세 이상 본인 소득만, 재산 환산액은 빠짐
        "always": (True, False),
        "children": (children, False),
        "couple_65": (len(seniors) >= 2, False),
    }


def _cmp(v, op: str, x) -> bool:
    return {">=": v >= x, "<=": v <= x, "==": v == x, ">": v > x, "<": v < x}[op]


def _threshold(cond: dict, var: dict):
    value = cond["value"]
    for a in cond.get("alt", []):
        name, _, num = a["if"].partition(">=")
        hit = var[name][0] >= int(num) if num else bool(var[a["if"]][0])
        if hit:
            value = max(value, a["value"]) if cond["op"] == "<=" else a["value"]
    return value


def judge(pid: str, family: dict) -> dict:
    p = load()[pid]
    var = variables(family)
    try:
        sid, _ = source_text(p["source"])
    except (FileNotFoundError, IndexError, KeyError):  # 원문 저장소가 없는 배포 묶음(Vercel). 인용은 programs.json에 있다
        sid = None
    conds = []
    multi = multi_generation(family)
    for c in p["eligibility"]:
        v, est = var[c["var"]]
        x = _threshold(c, var)
        ok = _cmp(v, c["op"], x)
        hint = ""
        if c["var"] == "home_value_gongsi":  # 시세가 기준 이하면 공시가격도 기준 이하. 넘으면 공시가격을 확인해야 함
            status = "met" if ok else "unknown"
            hint = "" if ok else "시세가 기준보다 높아요. 공시가격으로 다시 확인해야 해요"
        elif c["var"] == "owner_age" and not ok:  # 집 주인이 55세 미만이어도 배우자가 55세 이상이면 된다(원문 "부부 중 1명")
            other = [m["age"] for m in family["members"] if m["age"] >= c["value"] and abs(m["age"] - v) <= SPOUSE_GAP]
            status = "unknown" if v and other else "not_met"
            hint = "집 주인의 배우자가 55세 이상이면 돼요" if status == "unknown" else (f"집 주인({v}세)과 배우자가 55세 미만이에요" if v else "")
        elif c["var"] in ("home_count", "household_income_year", "net_assets") and multi and (c["var"] != "home_count" or var["home_count"][0])                 and pid != "PG_reverse_mortgage":
            status = "unknown"  # 여러 세대가 한 가족방: 신청하는 세대에 집·소득·자산이 얼마인지 모른다
            hint = "가족방에 여러 세대가 있어요. 신청하는 세대 기준으로 확인해야 해요"
        elif est:
            status = "unknown"
            hint = ("넣은 정보로 추정하면 기준 안이에요" if ok else "넣은 정보로 추정하면 기준을 넘어요") + f"({_fmt(c['var'], v)})"
        else:
            status = "met" if ok else "not_met"
            if c["var"] == "newborn_2y" and not ok:
                hint = "출산하면 2년 안에 신청할 수 있어요"
        conds.append({"label": c["label"], "status": status, "hint": hint, "quote": c["quote"]})
    overall = "not_eligible" if any(c["status"] == "not_met" for c in conds) else \
        "eligible" if all(c["status"] == "met" for c in conds) else "check"
    out = {"program_id": pid, "label": p["label"], "publisher": p["publisher"], "kind": p["kind"], "summary": p["summary"],
           "status": overall, "status_text": {"eligible": "기본 조건은 맞아요(기관 심사 조건은 확인 필요)",
                                              "not_eligible": "지금은 해당하지 않아요", "check": "확인이 필요해요"}[overall],
           "conditions": conds, "unmodeled": p.get("unmodeled", []), "facts": p.get("facts", []), "terms": p.get("terms", {}),
           "source_id": sid}
    # 주택연금 '예상 월지급금' 같은 금액은 온톨로지가 계산하지 않는다(2026-11-10, CLAUDE.md 5절). 서버가 계산엔진(engine/policies.py)에서 받아 붙인다.
    return out


def _fmt(var: str, v) -> str:
    from engine.fmt import won
    if var == "household_income_year":
        return f"연소득 약 {won(v)}"
    if var == "net_assets":
        return f"순자산 약 {won(v)}"
    if var == "income_recognition_month":
        return f"65세 이상 가족의 월 수입 {won(v)}, 재산 환산 제외"
    return str(v)


def check_quotes() -> list[str]:
    """G3: 모든 인용이 원문에 글자 그대로 있다. 문제 목록을 돌려준다(주택연금 월지급금 표는 계산엔진 데이터로 옮겨 tests/test_programs.py가 원문과 대조)."""
    problems = []
    for p in load().values():
        _, text = source_text(p["source"])
        for part in ("eligibility", "unmodeled", "facts"):
            for c in p.get(part, []):
                if c["quote"] and c["quote"] not in text:
                    problems.append(f"{p['id']} {part}: {c['quote']}")
        for k, term in p.get("terms", {}).items():
            src = source_text(term["source"])[1] if term.get("source") else text
            if term.get("quote") and term["quote"] not in src:
                problems.append(f"{p['id']} terms.{k}: {term['quote']}")
    return problems
