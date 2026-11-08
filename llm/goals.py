"""가족의 목표 카테고리와 카테고리별 필수 입력값(2026-11-04 형님 결정).

'우리 가족 이야기' 화면에서 가족이 목표 카테고리를 하나 고르고, 그 카테고리에 맞는 값을 입력한다.
- 계산 엔진이 쓰는 값(목표 종류·금액·기한·나이 기준)은 여기서 코드가 만든다(derive_goal). AI가 비워 두거나 지어내지 않는다.
- 엔진이 직접 쓰지 않는 값(지금 사는 곳, 육아휴직 기간, 은퇴 나이 등)은 글로 정리해 AI에게 '목표 상황'으로 준다(details).
- 화면과 서버가 같은 정의를 쓰도록 /api/config가 CATEGORIES를 내려 준다.
- (2026-11-08 형님 결정) "decide": True인 숫자(목표 금액·기한 등)는 비워 둘 수 있다. 비워 두면 '공동 목표 설정' 2단계에서
  엔진이 낸 우리 가족 기준(llm/goal_size.py)을 보며 가족이 함께 정한다. 입력했으면 2단계에서 그 값을 확인·고친다.
"""

from __future__ import annotations

CHOICE, NUM, TEXT, MEMBER = "choice", "number", "text", "member"

# 필드: key, label, kind, unit, min, max, options(choice), help
CATEGORIES: dict[str, dict] = {
    "home": {"label": "내 집 마련", "engine": "reach_target", "goal_label": "내 집 마련", "fields": [
        {"key": "target_amount", "label": "집 마련에 필요한 돈", "kind": NUM, "unit": "만원", "min": 1000, "max": 1_000_000, "decide": True,
         "help": "집값 전체가 아니라 모아야 하는 총액이에요. 예: 3억원이면 30000"},
        {"key": "within_years", "label": "언제까지", "kind": NUM, "unit": "년 안", "min": 1, "max": 30, "decide": True},
        {"key": "living", "label": "지금 사는 곳", "kind": CHOICE, "options": ["전세", "월세", "자가", "부모님 집"]},
    ]},
    "lump": {"label": "목돈 모으기", "engine": "reach_target", "goal_label": "목돈 모으기", "fields": [
        {"key": "purpose", "label": "무엇을 위한 돈인가요", "kind": CHOICE, "options": ["결혼", "자녀 교육", "차량", "창업", "여행·기타"]},
        {"key": "target_amount", "label": "모으고 싶은 돈", "kind": NUM, "unit": "만원", "min": 100, "max": 1_000_000, "decide": True},
        {"key": "within_years", "label": "언제까지", "kind": NUM, "unit": "년 안", "min": 1, "max": 30, "decide": True},
    ]},
    "debt": {"label": "대출 갚기", "engine": "debt_free", "goal_label": "대출 다 갚기", "fields": [
        {"key": "within_years", "label": "언제까지 다 갚고 싶나요", "kind": NUM, "unit": "년 안", "min": 1, "max": 30, "decide": True},
        {"key": "priority", "label": "가장 중요한 것", "kind": CHOICE, "options": ["이자 부담 줄이기", "빨리 끝내기", "생활이 흔들리지 않게 천천히"]},
    ]},
    "retire": {"label": "노후·은퇴 준비", "engine": "runway", "goal_label": "은퇴 후 예금이 버티는 기간", "fields": [
        {"key": "base_member_id", "label": "누구 나이를 기준으로 볼까요", "kind": MEMBER},
        {"key": "retire_age", "label": "은퇴하고 싶은 나이", "kind": NUM, "unit": "세", "min": 40, "max": 90},
        {"key": "monthly_need", "label": "은퇴 후 한 달에 필요한 돈", "kind": NUM, "unit": "만원", "min": 10, "max": 10_000, "decide": True},
    ]},
    "baby": {"label": "자녀 계획·육아", "engine": "reach_target", "goal_label": "육아 준비금 모으기", "fields": [
        {"key": "when_years", "label": "아이를 갖고 싶은 때", "kind": NUM, "unit": "년 뒤", "min": 1, "max": 15},
        {"key": "leave_months", "label": "육아휴직 예정 기간", "kind": NUM, "unit": "개월", "min": 0, "max": 36},
        {"key": "target_amount", "label": "미리 준비해 두고 싶은 돈", "kind": NUM, "unit": "만원", "min": 100, "max": 1_000_000, "decide": True},
    ]},
    "care": {"label": "부모님 부양·간병", "engine": "runway", "goal_label": "돌봄 비용을 감당하는 기간", "fields": [
        {"key": "base_member_id", "label": "누구 나이를 기준으로 볼까요", "kind": MEMBER},
        {"key": "monthly_cost", "label": "한 달에 드는 돈(예상)", "kind": NUM, "unit": "만원", "min": 10, "max": 10_000},
        {"key": "start_years", "label": "언제부터", "kind": NUM, "unit": "년 뒤(지금이면 0)", "min": 0, "max": 30},
    ]},
    "other": {"label": "기타", "engine": None, "goal_label": "", "fields": [
        {"key": "purpose_text", "label": "목표를 한 줄로 적어 주세요", "kind": TEXT, "max": 30},
        {"key": "engine_kind", "label": "어떤 계산이 필요한가요", "kind": CHOICE,
         "options": ["목표 금액 모으기", "대출 다 갚기", "예금이 얼마나 버티는지"]},
    ]},
}
OTHER_ENGINE = {"목표 금액 모으기": "reach_target", "대출 다 갚기": "debt_free", "예금이 얼마나 버티는지": "runway"}
# 기타에서 고른 계산에 따라 더 받는 값
OTHER_EXTRA = {
    "reach_target": [
        {"key": "target_amount", "label": "모으고 싶은 돈", "kind": NUM, "unit": "만원", "min": 100, "max": 1_000_000, "decide": True},
        {"key": "within_years", "label": "언제까지", "kind": NUM, "unit": "년 안", "min": 1, "max": 30, "decide": True},
    ],
    "debt_free": [{"key": "within_years", "label": "언제까지 다 갚고 싶나요", "kind": NUM, "unit": "년 안", "min": 1, "max": 30, "decide": True}],
    "runway": [{"key": "base_member_id", "label": "누구 나이를 기준으로 볼까요", "kind": MEMBER}],
}


class GoalInputError(ValueError):
    pass


def fields_for(category: str, values: dict | None = None) -> list[dict]:
    """그 카테고리에서 받아야 하는 필드 목록(기타는 고른 계산에 따라 더 받는다)."""
    spec = CATEGORIES[category]
    out = list(spec["fields"])
    if category == "other":
        eng = OTHER_ENGINE.get((values or {}).get("engine_kind"))
        if eng:
            out += OTHER_EXTRA[eng]
    return out


def _num(v, f: dict) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise GoalInputError(f"'{f['label']}'은(는) 숫자로 적어 주세요")
    if not f["min"] <= v <= f["max"]:
        raise GoalInputError(f"'{f['label']}'은(는) {f['min']:g}~{f['max']:g}{f.get('unit', '')} 사이여야 해요")
    return float(v)


def validate_input(raw, member_ids: set[str]) -> dict | None:
    """가족 입력의 goal_input을 검사해 정리한다. 없으면 None(예전 방식: AI가 목표를 정한다)."""
    if not raw:
        return None
    if not isinstance(raw, dict) or raw.get("category") not in CATEGORIES:
        raise GoalInputError("목표 카테고리를 골라 주세요")
    cat = raw["category"]
    vals = raw.get("fields") if isinstance(raw.get("fields"), dict) else {}
    out: dict = {}
    for f in fields_for(cat, vals):
        v = vals.get(f["key"])
        if v is None or (isinstance(v, str) and not v.strip()):
            if f.get("decide"):
                continue  # 공동 목표 설정 2단계에서 함께 정한다
            raise GoalInputError(f"'{f['label']}'을(를) 입력해 주세요")
        if f["kind"] == NUM:
            out[f["key"]] = round(_num(v, f), 1)
        elif f["kind"] == CHOICE:
            if v not in f["options"]:
                raise GoalInputError(f"'{f['label']}'에서 하나를 골라 주세요")
            out[f["key"]] = v
        elif f["kind"] == MEMBER:
            if v not in member_ids:
                raise GoalInputError(f"'{f['label']}'에서 가족을 골라 주세요")
            out[f["key"]] = v
        else:
            s = str(v).strip()
            if len(s) > f["max"]:
                raise GoalInputError(f"'{f['label']}'은(는) {f['max']}자까지예요")
            out[f["key"]] = s
    return {"category": cat, "fields": out}


def complete(raw, member_ids: set[str]) -> bool:
    try:
        return validate_input(raw, member_ids) is not None
    except GoalInputError:
        return False


def decide_fields(gi: dict) -> list[dict]:
    """2단계에서 가족이 함께 정하는(또는 확인하는) 숫자 필드."""
    return [f for f in fields_for(gi["category"], gi["fields"]) if f.get("decide")]


def missing(gi: dict) -> list[str]:
    """아직 정하지 않은 숫자의 key."""
    return [f["key"] for f in decide_fields(gi) if gi["fields"].get(f["key"]) is None]


def with_values(gi: dict, values) -> dict:
    """2단계에서 가족이 정한 숫자를 목표 입력에 합친다(정할 수 있는 숫자만, 범위 검사). 빈 값(None)은 '아직 안 정함'."""
    out = {"category": gi["category"], "fields": dict(gi["fields"])}
    if not isinstance(values, dict):
        return out
    for f in decide_fields(gi):
        if f["key"] not in values:
            continue
        v = values[f["key"]]
        if v is None or (isinstance(v, str) and not v.strip()):
            out["fields"].pop(f["key"], None)
        else:
            out["fields"][f["key"]] = round(_num(v, f), 1)
    return out


def derive_goal(gi: dict, members: list[dict]) -> dict:
    """계산 엔진에 넘길 목표(plan.normalize_goal의 입력). 가족이 입력한 값 그대로다."""
    cat, v = gi["category"], gi["fields"]
    spec = CATEGORIES[cat]
    eng = spec["engine"] or OTHER_ENGINE[v["engine_kind"]]
    label = spec["goal_label"] or v["purpose_text"]
    if cat == "lump":
        label = f"{v['purpose']} 목돈 모으기"
    goal = {"type": eng, "label": label[:40], "target_amount": None, "within_months": None, "base_member_id": None, "target_note": None}
    if eng == "reach_target":
        goal["target_amount"] = v.get("target_amount")  # 비어 있으면 2단계에서 정한다
    years = v.get("within_years") if cat != "baby" else v.get("when_years")
    if years:
        goal["within_months"] = int(round(years * 12))
    if eng == "runway":
        goal["base_member_id"] = v.get("base_member_id")
    return goal


def details_text(gi: dict, members: list[dict]) -> list[str]:
    """엔진이 직접 쓰지 않는 값까지 포함해, AI에게 주는 '목표 상황' 줄들."""
    cat, v = gi["category"], gi["fields"]
    names = {m["member_id"]: m["name"] for m in members}
    out = [f"목표 종류: {CATEGORIES[cat]['label']}"]
    for f in fields_for(cat, v):
        if f["key"] not in v:
            if f.get("decide"):
                out.append(f"{f['label']}: 아직 정하지 않았어요(공동 목표 설정 2단계에서 가족이 함께 정해요)")
            continue
        val = v[f["key"]]
        if f["kind"] == MEMBER:
            val = f"{names.get(val, val)}님"
        elif f["kind"] == NUM:
            val = f"{val:g}{f.get('unit', '')}"
        out.append(f"{f['label']}: {val}")
    return out


def public_config() -> dict:
    """화면에 내려 주는 정의(필드 목록·선택지·기타의 추가 필드)."""
    return {"categories": {k: {"label": c["label"], "fields": c["fields"]} for k, c in CATEGORIES.items()},
            "other_engine": list(OTHER_ENGINE), "other_extra": {k: v for k, v in OTHER_EXTRA.items()},
            "other_engine_map": OTHER_ENGINE}
