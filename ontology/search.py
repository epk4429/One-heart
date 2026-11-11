"""온톨로지 탐색(docs/06_온톨로지와_RAG.md 3.3절).

LLM(역할 8)은 약속을 필요·제약 id로 바꾸기만 하고, 상품 유형 선택은 이 코드가 한다.
따라간 경로가 그대로 "왜 이 상품인가요" 설명이 된다.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

HERE = Path(__file__).resolve().parent


@lru_cache(maxsize=1)
def load() -> dict:
    vocab = json.loads((HERE / "vocab.json").read_text(encoding="utf-8"))
    types = json.loads((HERE / "product_types.json").read_text(encoding="utf-8"))["product_types"]
    rules = json.loads((HERE / "rules.json").read_text(encoding="utf-8"))["rules"]
    return {
        "needs": {n["id"]: n for n in vocab["needs"]},
        "constraints": {c["id"]: c for c in vocab["constraints"]},
        "types": {t["id"]: t for t in types},
        "rules": rules,
    }


def vocab_ids() -> tuple[set[str], set[str]]:
    o = load()
    return set(o["needs"]), set(o["constraints"])


def _value(pt: dict, field: str):
    if field in ("features", "requires_home_sale", "kind"):
        return pt.get(field)
    return pt["attributes"].get(field)


def passes(pt: dict, constraint_id: str) -> tuple[bool, str]:
    rule = load()["rules"].get(constraint_id)
    if rule is None:
        return True, ""
    v = _value(pt, rule["field"])
    if v == "해당 없음":  # 그 속성이 없는 유형(행동·상담·정책)에는 이 제약이 해당하지 않는다
        return True, ""
    if "in" in rule:
        ok = v in rule["in"]
    elif "equals" in rule:
        ok = v == rule["equals"]
    elif "contains" in rule:
        ok = rule["contains"] in (v or [])
    else:
        ok = True
    return ok, ("" if ok else rule["reason"])


def retired_target(members: list[dict], base_member_id: str | None = None) -> bool | None:
    """노후 생활비의 주인이 이미 은퇴했는지(1-5, 2026-11-10). 가족이 가족방 만들기에서 고른 '지금 하는 일'로만 판단하고 나이로 짐작하지 않는다.
    - 목표에 '누구 기준'(base_member_id)이 있으면 그 사람: 은퇴했어요 → True, 다른 것 → False.
    - 없으면 가족 전체: 일하는 사람이 아무도 없고 은퇴한 사람이 있으면 True.
    - 하는 일을 모르면 None(판단하지 않음)."""
    if base_member_id:
        m = next((x for x in members if x.get("member_id") == base_member_id), None)
        if m is None or not m.get("work"):
            return None
        return m["work"] == "retired"
    works = [m.get("work") for m in members if m.get("work")]
    if not works:
        return None
    return "working" not in works and "retired" in works


def person_fails(pt: dict, retired: bool | None) -> str | None:
    """상품 유형의 가족 상황 조건(requires.before_retirement)에 맞지 않으면 그 이유."""
    r = pt.get("requires") or {}
    if r.get("before_retirement") and retired is True:
        return r.get("why") or "이미 은퇴한 분께는 연결하지 않아요"
    return None


def recommend(mappings: list[dict], commitments: dict[str, dict], retired: bool | None = None) -> list[dict]:
    """mappings: [{commitment_id, need_ids, constraint_ids}] (역할 8 출력, 검증 통과 후).
    commitments: {commitment_id: {"no": 1, "text": ...}}. 목표에서 나온 필요는 commitment_id가 "goal".
    retired: 노후 생활비의 주인이 이미 은퇴했는지(retired_target). None이면 이 조건을 보지 않는다."""
    o = load()
    out = []
    for mp in mappings:
        cid = mp["commitment_id"]
        com = commitments.get(cid, {"no": None, "text": ""})
        for nid in mp.get("need_ids", []):
            need = o["needs"][nid]
            cands = [o["types"][t] for t in need["satisfied_by"]]
            chosen, excluded = [], []
            for pt in cands:
                why_person = person_fails(pt, retired)
                if why_person:  # 예: 이미 은퇴한 분의 노후 생활비에 연금저축(일하는 동안 오래 모으는 상품)은 연결하지 않는다
                    excluded.append({"product_type_id": pt["id"], "label": pt["label"], "constraint_id": "person", "reason": why_person})
                    continue
                fails = [(c, r) for c in mp.get("constraint_ids", []) for ok, r in [passes(pt, c)] if not ok]
                if fails:
                    excluded.append({"product_type_id": pt["id"], "label": pt["label"],
                                     "constraint_id": fails[0][0], "reason": fails[0][1]})
                else:
                    chosen.append(pt)
            for pt in chosen:
                path = [[cid, "requires", nid]]
                path += [[cid, "constrainedBy", c] for c in mp.get("constraint_ids", [])]
                path.append([nid, "satisfiedBy", pt["id"]])
                for c in mp.get("constraint_ids", []):
                    rule = o["rules"].get(c)
                    if rule:
                        path.append([pt["id"], "hasAttribute", f"{rule['field']}={_value(pt, rule['field'])}"])
                out.append({
                    "commitment_id": cid,
                    "need_id": nid,
                    "need_label": need["label"],
                    "constraint_ids": mp.get("constraint_ids", []),
                    "product_type_id": pt["id"],
                    "product_label": pt["label"],
                    "kind": pt["kind"],
                    "summary": pt["summary"],
                    "attributes": pt["attributes"],
                    "path": path,
                    "excluded": excluded,
                    "reason_text": _reason(com, need, mp.get("constraint_ids", []), pt),
                })
            if not chosen:
                out.append({"commitment_id": cid, "need_id": nid, "need_label": need["label"],
                            "product_type_id": None, "excluded": excluded,
                            "reason_text": _reason(com, need, mp.get("constraint_ids", []), None)})
    return out


def _reason(com: dict, need: dict, constraint_ids: list[str], pt: dict | None) -> str:
    o = load()
    q = "" if str(com.get("text", "")).startswith("'") else "'"  # 약속 문장이 이미 따옴표로 시작하면 한 번 더 감싸지 않는다
    head = f"약속 {com['no']} {q}{com['text']}{q}" if com.get("no") else "함께 정한 목표"
    why = f" ({' · '.join(o['constraints'][c]['label'] for c in constraint_ids)})" if constraint_ids else ""
    if pt is None:
        topic = "은" if com.get("no") else "는"
        return f"{head}{topic} 상품 연결 없이 가족이 직접 지켜요{why}."
    return f"{head} → {need['label']}{why} → {pt['label']}을 연결했어요."
