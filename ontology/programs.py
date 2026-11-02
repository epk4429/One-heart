"""제도·정책금융 판정(docs/12 13.1절 4단계). 규칙은 ontology/programs.json(공식 원문 인용), 판정은 이 코드.

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


def variables(family: dict) -> dict:
    """가족 정보 → 규칙 변수. (값, 추정 여부)."""
    f = family["finance"]
    tot = lambda *k: sum(i["amount"] for i in f if i["kind"] in k)  # noqa: E731
    ages = [m["age"] for m in family["members"]]
    children = sum(1 for m in family["members"] if CHILD.search(m.get("role") or "") or m["age"] < 19)
    return {
        "eldest_age": (max(ages), False),
        "home_count": (sum(1 for i in f if i["kind"] == "home"), False),
        "home_value_gongsi": (tot("home"), True),  # 가족은 시세를 넣는다. 공시가격은 보통 시세보다 낮다
        "household_income_year": (round(tot("income") * 12, 1), True),
        "net_assets": (round(tot("deposit", "investment", "lease_deposit", "home") - tot("loan"), 1), True),
        "newborn_2y": (any(m["age"] <= 1 for m in family["members"]), False),
        "income_recognition_month": (tot("income"), True),  # 재산 환산액은 빠져 있다
        "always": (True, False),
        "children": (children, False),
        "couple_65": (sum(1 for a in ages if a >= 65) >= 2, False),
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
    for c in p["eligibility"]:
        v, est = var[c["var"]]
        x = _threshold(c, var)
        ok = _cmp(v, c["op"], x)
        hint = ""
        if c["var"] == "home_value_gongsi":  # 시세가 기준 이하면 공시가격도 기준 이하. 넘으면 공시가격을 확인해야 함
            status = "met" if ok else "unknown"
            hint = "" if ok else "시세가 기준보다 높아요. 공시가격으로 다시 확인해야 해요"
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
    if pid == "PG_reverse_mortgage" and overall != "not_eligible":
        age = reverse_mortgage_age(family)
        home = var["home_value_gongsi"][0]
        m = reverse_mortgage_monthly(age, home)
        if m:
            out["estimate"] = {"label": "예상 월지급금", "monthly_manwon": m[0], "basis": m[1]}
    return out


def _fmt(var: str, v) -> str:
    from engine.fmt import won
    if var == "household_income_year":
        return f"연소득 약 {won(v)}"
    if var == "net_assets":
        return f"순자산 약 {won(v)}"
    if var == "income_recognition_month":
        return f"월 수입 {won(v)}, 재산 환산 제외"
    return str(v)


def reverse_mortgage_age(family: dict) -> int:
    """월지급금은 부부 중 나이가 젊은 사람 기준(원문). 55세 이상 가족 중 가장 나이 많은 두 사람을 부부로 보고 그중 젊은 쪽."""
    seniors = sorted((m["age"] for m in family["members"] if m["age"] >= 55), reverse=True)
    return min(seniors[:2]) if seniors else max(m["age"] for m in family["members"])


def reverse_mortgage_monthly(age: int, home_manwon: float) -> tuple[float, str] | None:
    """공사 월지급금 예시표(종신지급방식·정액형, 2026.03.01 기준)에서 연령·주택가격으로 읽는다(만원).
    표에 없는 나이·가격은 앞뒤 칸을 직선으로 이어 계산한 추정이다. 80세 넘으면 80세 줄, 12억 넘으면 12억 칸."""
    t = load()["PG_reverse_mortgage"]["monthly_table"]
    if age < 55 or home_manwon <= 0:
        return None
    ages = sorted(int(a) for a in t["rows"])
    a = min(max(age, ages[0]), ages[-1])
    lo = max(x for x in ages if x <= a)
    hi = min(x for x in ages if x >= a)
    eok = min(home_manwon / 10000, t["prices_eok"][-1])

    def at(row_age: int) -> float:
        row = t["rows"][str(row_age)]
        ps = t["prices_eok"]
        if eok <= ps[0]:
            return row[0] * eok / ps[0]
        i = max(k for k, p in enumerate(ps) if p <= eok)
        if i == len(ps) - 1:
            return row[-1]
        return row[i] + (row[i + 1] - row[i]) * (eok - ps[i]) / (ps[i + 1] - ps[i])
    v = at(lo) if lo == hi else at(lo) + (at(hi) - at(lo)) * (a - lo) / (hi - lo)
    exact = lo == hi and eok in t["prices_eok"]
    note = "" if exact else " · 표 사이 값은 직선으로 이어 계산한 추정"
    cap = " · 12억원 넘는 집은 12억원 칸" if home_manwon > 120000 else ""
    return round(v / 10, 1), f"한국주택금융공사 월지급금 예시표(종신·정액형, 2026.03.01 기준) {age}세·{home_manwon / 10000:g}억원{note}{cap}"


def check_quotes() -> list[str]:
    """G3: 모든 인용이 원문에 글자 그대로 있다. 월지급금 표의 줄은 원문에 같은 순서로 이어서 있다. 문제 목록을 돌려준다."""
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
        t = p.get("monthly_table")
        if t:
            _, ttext = source_text(t["source"])
            lines = [x.strip() for x in ttext.split("\n")]
            for q in (t["basis_quote"], t["example_quote"]):
                if q not in ttext:
                    problems.append(f"{p['id']} table quote: {q}")
            for age, row in t["rows"].items():
                want = [f"{age}세"] + [f"{v:,}" for v in row]
                if not any(lines[i:i + len(want)] == want for i in range(len(lines))):
                    problems.append(f"{p['id']} table row {age}세")
    return problems
