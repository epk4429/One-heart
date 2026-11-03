"""6단계 검증 묶음(docs/14): 예시 가족이 아니라 생애 단계·경계 사례 가상 가족으로 온톨로지 전체(필요의 길·제도 판정·실제 상품 비교)를
끝까지 돌리고, 틀린 안내가 없는지 숫자로 본다. AI를 쓰지 않는다(비용 없음).

정답은 두 가지로 따로 둔다(판정 코드와 독립):
- 제도: data/eval/kb_families.json에 사람이 규칙 원문을 읽고 적은 가족별 정답(eligible / not_eligible / unknown)과 소득 방향.
- 상품: 원문 글(가입대상)을 판정 코드와 다른 단순·엄격한 패턴으로 다시 읽은 검사(나이·무주택·자녀 수)와, 결과 안의 숫자끼리 맞는지(한도·요약).

지표
- 부적격 노출(over_claim): 정답이 '확실히 맞음'이 아닌데 '기본 조건은 맞아요', 또는 가입할 수 없는 상품이 목록에 남음. 0이어야 한다.
- 부당 제외(false_exclusion): 정답이 '안 맞음'이 아닌데 '해당하지 않아요'로 뺌. 0이어야 한다.
- 방향 틀림(hint_wrong): 추정 소득의 "기준 안이에요/넘어요"가 정답 방향과 다름. 0이어야 한다.
- 연결 안 된 필요(unrouted): 길이 없는 필요. 0이어야 한다.
- 결과 숫자 불일치(inconsistent): 한도를 넘는데 '한도 안', 맞는 상품이 없는데 요약이 '있어요' 등. 0이어야 한다.
- 참고 지표: 확인 필요 비율, '맞는 상품 없음' 사례 수, 제도 확인 필요 비율.

실행: python -m ontology.kb_eval → data/eval/kb_report.json. 테스트: tests/test_kb_eval.py.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

from llm import family as F
from llm.plan import policy_menu

from . import fit
from . import programs as P
from .products import load_products
from .routes import coverage

ROOT = Path(__file__).resolve().parents[1]
FAMILIES = ROOT / "data/eval/kb_families.json"
REPORT = ROOT / "data/eval/kb_report.json"
PARAMS = {  # 범주별 대표 입력(만원·개월). 주담대 집값·전세 보증금은 가족 정보에 있으면 그 값
    "saving": {"monthly": 30, "term": 12}, "deposit": {"amount": 1000, "term": 12},
    "mortgage": {"amount": 20000, "months": 360}, "rent_loan": {"amount": 10000, "months": 24, "repay": "bullet"},
    "credit_loan": {"amount": 3000, "months": 36}, "busi_loan": {"amount": 5000, "months": 60},
}
CAT_NEED = {"saving": "N_goal_saving", "deposit": "N_goal_saving", "mortgage": "N_home_purchase_prep", "rent_loan": "N_rent_deposit",
            "credit_loan": "N_debt_repayment", "busi_loan": "N_business_fund"}
_KIDS_WORDS = re.compile(r"자녀|부모|아동|미성년|가구원|손자|손녀|본인|보호자")
_NUMK = {"두": 2, "세": 3, "네": 4}


def load_families() -> list[dict]:
    return json.loads(FAMILIES.read_text(encoding="utf-8"))["families"]


# ---------- 원문 다시 읽기(판정 코드와 다른 단순·엄격한 패턴) ----------
def strict_age(join_member: str) -> tuple[int | None, int | None] | None:
    """가입대상이 '만 N세 이상/이하/미만', 'N~M세'만으로 나이를 정하는 글일 때만 (최소, 최대). 자녀·부모 등 다른 사람 말이 있거나
    여러 대상을 나열한 글은 None(엄격하게 확실한 것만)."""
    t = join_member or ""
    if not t or _KIDS_WORDS.search(t) or t.count(",") > 2 or re.search(r"또는|하나\s*이상", t):
        return None
    lo = hi = None
    for a, b, op in re.findall(r"(\d+)\s*세?\s*[~∼]\s*만?\s*(\d+)\s*세\s*(이하|미만)?", t):
        lo, hi = int(a), int(b) - (op == "미만")
    for n, op in re.findall(r"(\d+)\s*세\s*(이상|이하|미만|초과)", t):
        n = int(n)
        if op == "이상":
            lo = max(lo or 0, n)
        elif op == "초과":
            lo = max(lo or 0, n + 1)
        elif op == "이하":
            hi = n if hi is None else min(hi, n)
        else:
            hi = n - 1 if hi is None else min(hi, n - 1)
    return (lo, hi) if lo is not None or hi is not None else None


def strict_kids(join_member: str) -> int | None:
    """가입대상이 '자녀 N명 이상(을 둔 부모)' 하나뿐인 글일 때 N."""
    t = join_member or ""
    if re.search(r"또는|하나\s*이상|본인|및", t):
        return None
    m = re.search(r"(\d|두|세|네)\s*명\s*이상의?\s*(?:미성년\s*)?자녀|자녀\s*(\d|두|세|네)\s*명\s*이상", t)
    if not m:
        return None
    g = m.group(1) or m.group(2)
    return _NUMK.get(g) or int(g)


def _owns_home(family: dict, mid: str) -> bool:
    return any(i["kind"] == "home" and i["owner_id"] in (mid, "joint") for i in family["finance"])


# ---------- 검사 ----------
def _programs(case: dict, fam: dict) -> tuple[list, list, list, Counter]:
    over, wrong_out, hint_wrong, st = [], [], [], Counter()
    rules = P.load()
    for pid, truth in case["programs"].items():
        j = P.judge(pid, fam)
        st[j["status"]] += 1
        if j["status"] == "eligible" and truth != "eligible":
            over.append({"family": case["id"], "program": pid, "truth": truth, "got": j["status"],
                         "conditions": [(c["label"], c["status"]) for c in j["conditions"]]})
        if j["status"] == "not_eligible" and truth != "not_eligible":
            wrong_out.append({"family": case["id"], "program": pid, "truth": truth, "got": j["status"],
                              "conditions": [(c["label"], c["status"]) for c in j["conditions"]]})
        want = (case.get("income_hint") or {}).get(pid)
        if want:
            i = next(k for k, c in enumerate(rules[pid]["eligibility"]) if c["var"] in ("household_income_year", "income_recognition_month"))
            h = j["conditions"][i]["hint"]
            got = "in" if "기준 안" in h else "over" if "넘어요" in h else "none"
            if got != want:
                hint_wrong.append({"family": case["id"], "program": pid, "want": want, "got": got, "hint": h})
    return over, wrong_out, hint_wrong, st


def _policy(case: dict, fam: dict) -> list:
    """미래 계산의 정책 블록(주택연금)은 제도 정답이 '안 맞음'이면 나오면 안 된다."""
    goal = {"type": "reach_target", "target_amount": 1, "horizon_months": 120}
    offered = any(p["policy"] == "reverse_mortgage" for p in policy_menu(fam, goal))
    if offered and case["programs"].get("PG_reverse_mortgage") == "not_eligible":
        return [{"family": case["id"], "policy": "reverse_mortgage", "truth": "not_eligible"}]
    return []


def _products(case: dict, fam: dict) -> tuple[list, list, dict]:
    over, bad, stats = [], [], {}
    host = fam["room"]["host_member_id"]
    raw = {cat: {p["product_id"]: p for p in load_products(cat)} for cat in PARAMS}
    homes = sum(i["amount"] for i in fam["finance"] if i["kind"] == "home")
    lease = sum(i["amount"] for i in fam["finance"] if i["kind"] == "lease_deposit")
    for m in fam["members"]:
        person = case.get("person") if m["member_id"] == host else None
        for cat, base in PARAMS.items():
            kw = dict(base)
            if cat in ("saving", "deposit"):
                kw["person"] = person
            if cat == "mortgage":
                kw["home_price"] = homes or 40000
            if cat == "rent_loan":
                kw["deposit_amount"] = lease or 20000
            res = fit.compare(fam, CAT_NEED[cat], category=cat, member_id=m["member_id"], **kw)
            money = kw.get("monthly") or kw.get("amount")
            key = f"{case['id']}|{m['member_id']}|{cat}"
            sm = res["summary"]
            stats[key] = {"state": sm["state"], "rows": len(res["items"]), "ok": sm["ok"], "unsure": sm["unsure"],
                          "with_checks": sum(1 for r in res["items"] if r["checks"]), "excluded": len(res.get("excluded", []))}
            kids = (person or {}).get("kids")
            for r in res["items"]:
                p = raw[cat][r["product_id"]]
                jm = p["texts"].get("join_member") or ""
                where = {"family": case["id"], "member": m["name"], "age": m["age"], "category": cat, "product": r["name"], "provider": r["provider"]}
                if cat not in ("saving", "deposit") and m["age"] < 19:
                    over.append({**where, "why": "19세 미만 이름으로 대출 상품을 보여 줌"})
                ages = strict_age(jm) if cat in ("saving", "deposit") else strict_age(p["texts"].get("join_deny_detl") or "") if cat == "busi_loan" else None
                if ages and ((ages[0] is not None and m["age"] < ages[0]) or (ages[1] is not None and m["age"] > ages[1])):
                    over.append({**where, "why": f"가입대상 나이 {ages}", "text": jm[:80]})
                if cat in ("saving", "deposit") and "무주택" in jm and _owns_home(fam, m["member_id"]):
                    over.append({**where, "why": "무주택 전용인데 본인·공동 명의 집이 있음", "text": jm[:80]})
                need_kids = strict_kids(jm) if cat in ("saving", "deposit") else None
                if need_kids and kids is not None and kids < need_kids:
                    over.append({**where, "why": f"자녀 {need_kids}명 이상 전용인데 자녀 {kids}명", "text": jm[:80]})
                for g in r.get("got", []):  # 사람 조건 '해당돼요'가 나이와 맞는지
                    a = re.search(r"나이 만 (\d+)(?:~(\d+))?세( 이상| 이하)?", g["label"])
                    if g.get("person") and a:
                        lo, hi, op = int(a.group(1)), a.group(2), a.group(3)
                        ok = (lo <= m["age"] <= int(hi)) if hi else (m["age"] >= lo if op == " 이상" else m["age"] <= lo)
                        if not ok:
                            over.append({**where, "why": f"'{g['label']}' 해당이라고 했는데 {m['age']}세"})
                lim = r.get("limit_manwon")
                if r["limit_ok"] is True and lim is not None and money and money > lim + 1e-6:
                    bad.append({**where, "why": f"한도 {lim} < 금액 {money}인데 '한도 안'"})
            if sm["state"] == "ok" and sm["ok"] == 0 or sm["state"] != "ok" and sm["ok"] > 0:
                bad.append({"family": case["id"], "member": m["name"], "category": cat, "why": f"요약 상태 {sm['state']}와 맞는 상품 수 {sm['ok']}가 다름"})
    return over, bad, stats


def run() -> dict:
    cov = coverage()
    unrouted = [nid for nid, c in cov.items() if not c["routes"]]
    unrouted += [f"{nid}:{r['category']}" for nid, c in cov.items() for r in c["routes"] if r["route"] == "real" and not load_products(r["category"])]
    unrouted += [f"{nid}:{pid}" for nid, c in cov.items() for r in c["routes"] if r["route"] == "program" for pid in r["programs"] if pid not in P.load()]
    over_p, out_p, hint_wrong, over_s, bad, invalid, policy = [], [], [], [], [], [], []
    prog_status, stats = Counter(), {}
    for case in load_families():
        try:
            fam = F.validate(case["family"])
        except F.FamilyError as e:
            invalid.append({"family": case["id"], "error": str(e)})
            continue
        a, b, c, st = _programs(case, fam)
        over_p += a
        out_p += b
        hint_wrong += c
        prog_status += st
        policy += _policy(case, fam)
        d, e, s = _products(case, fam)
        over_s += d
        bad += e
        stats.update(s)
    states = Counter(s["state"] for s in stats.values())
    rows = sum(s["rows"] for s in stats.values())
    metrics = {
        "families": len(load_families()), "invalid_families": len(invalid), "needs": len(cov), "unrouted": len(unrouted),
        "over_claim_programs": len(over_p), "false_exclusion_programs": len(out_p), "hint_wrong": len(hint_wrong),
        "over_claim_policy": len(policy), "over_claim_products": len(over_s), "inconsistent": len(bad),
        "comparisons": len(stats), "comparison_states": dict(states), "product_rows": rows,
        "product_rows_with_checks_pct": round(100 * sum(s["with_checks"] for s in stats.values()) / rows, 1) if rows else 0,
        "program_judgments": dict(prog_status),
        "program_check_pct": round(100 * prog_status["check"] / sum(prog_status.values()), 1) if prog_status else 0,
    }
    return {"_note": "6단계 검증 묶음 결과(ontology/kb_eval.py). 개발용 공시 스냅샷 기준.", "metrics": metrics,
            "invalid_families": invalid, "unrouted": unrouted, "over_claim_programs": over_p, "false_exclusion_programs": out_p,
            "hint_wrong": hint_wrong, "over_claim_policy": policy, "over_claim_products": over_s[:200], "inconsistent": bad[:200],
            "comparisons": stats}


if __name__ == "__main__":
    rep = run()
    REPORT.write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(rep["metrics"], ensure_ascii=False, indent=1))
