"""계산엔진: 우대금리 합산(2026-11-11 온톨로지에서 옮김, CLAUDE.md 5절 '계산할 때는 계산엔진만').

온톨로지(ontology/conditions.py)는 우대조건 원문을 읽어 항목으로 만들고(묶음·단계형·택일 구조, 금액, 종류), 가족에게 어떤 항목이
해당하는지 판정한다. 그 항목들을 더해 '받는 우대'와 '내가 받을 금리'를 내는 산수는 여기서만 한다.

항목(dict) 필드: add_pp(이 항목의 %p, 없으면 None), group(묶음 id), role="group"(묶음 머리 줄 = 아래 항목들의 상한),
group_rule("sum" 합 / "one_of" 그중 하나), group id가 't'로 시작하면 단계형(그중 큰 것), alt(고객 구분 택일 무리), tag(종류).
"""

from __future__ import annotations


def _sum(items: list[dict]) -> float:
    total, seen = 0.0, set()
    for it in items:
        g = it.get("group")
        if it.get("role") == "group":
            kids = [r for r in items if r.get("group") == g and r is not it]
            got = [r["add_pp"] or 0 for r in kids]
            total += min(sum(got) if it["group_rule"] == "sum" else max(got, default=0), it["add_pp"])
        elif g and g[0] in "ta":
            if g not in seen:
                total += max(r["add_pp"] for r in items if r.get("group") == g)
                seen.add(g)
        elif not g:
            total += it["add_pp"] or 0
    return total


def reachable(items: list[dict]) -> float:
    """항목을 모두 충족할 때 받을 수 있는 우대 합(상한 줄 적용 전). 고객 구분 택일 무리는 그중 큰 쪽."""
    alts = sorted({it["alt"] for it in items if it.get("alt")})
    base = _sum([it for it in items if not it.get("alt")])
    return round(base + max((_sum([it for it in items if it.get("alt") == a]) for a in alts), default=0.0), 2)


def applicable(items: list[dict], tags: set[str]) -> float:
    """고른 종류(tags)의 항목만 충족했을 때 받는 우대(상한 줄 적용 전). 묶음·단계형·택일 규칙은 reachable과 같다."""
    picked = [{**it, "add_pp": (it["add_pp"] or 0) if it.get("role") == "group" or it["tag"] in tags else 0} for it in items]
    return reachable(picked)


def my_rate(base_rate: float, max_rate: float | None, items: list[dict], tags: set[str], cap_pp: float | None) -> dict:
    """내가 받을 금리 = 기본금리 + 우대. 우대는 고른 항목의 합을 공시 최고 우대폭(최고금리 − 기본금리)과 원문 상한(cap_pp) 안으로.
    held: 원문 우대 합이 공시 최고 우대폭보다 커서 금리에 다 넣지 않은 몫."""
    gap = max(0.0, (max_rate or base_rate) - base_rate)
    want = applicable(items, tags)
    bonus = round(min(want, gap, cap_pp if cap_pp is not None else gap), 2)
    held = round(want - bonus, 2) if want > bonus + 0.005 else 0
    return {"rate": round(base_rate + bonus, 2), "bonus": bonus, "held": held, "want": want}
