from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field

PLACEHOLDER = re.compile(r"\{\{\s*(fact|quote)\s*:\s*([^}\s]+)\s*\}\}")

# 숫자 + 단위. "1억 4,855만원" 같은 복합 금액을 먼저 잡고, 그다음 단일 표현을 잡는다.
_NUM = r"\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?"
MONEY_COMPOSITE = re.compile(rf"(?P<eok>{_NUM})\s*억(?:\s*(?P<man>{_NUM})\s*만\s*원?)?\s*원?")
SINGLE = re.compile(rf"(?P<num>{_NUM})\s*(?P<unit>%p|%|만\s*원|만원|만|원|년|개월|세|배|명)")

UNIT_KIND = {"억": "money", "만원": "money", "만": "money", "원": "money_won", "%": "pct", "%p": "pct",
             "년": "year", "개월": "month", "세": "age", "배": "times", "명": "people"}
FACT_UNIT_KIND = {"만원": "money", "만원/월": "money", "%/년": "pct", "ratio": "pct", "year": "year",
                  "month": "month", "세": "age"}


def _f(s: str) -> float:
    return float(s.replace(",", ""))


@dataclass
class NumberHit:
    text: str
    value: float
    kind: str
    span: tuple[int, int]


def find_numbers(text: str) -> list[NumberHit]:
    hits: list[NumberHit] = []
    taken: list[tuple[int, int]] = []
    for m in MONEY_COMPOSITE.finditer(text):
        v = _f(m["eok"]) * 10000 + (_f(m["man"]) if m["man"] else 0)
        hits.append(NumberHit(m.group(0).strip(), v, "money", m.span()))
        taken.append(m.span())
    for m in SINGLE.finditer(text):
        if any(a <= m.start() < b for a, b in taken):
            continue
        unit = re.sub(r"\s+", "", m["unit"])
        v = _f(m["num"])
        kind = UNIT_KIND.get(unit, "other")
        if kind == "money_won":  # 원 단위 → 만원
            v, kind = v / 10000, "money"
        hits.append(NumberHit(m.group(0).strip(), v, kind, m.span()))
    return sorted(hits, key=lambda h: h.span)


def _fact_values(facts: dict[str, dict]) -> list[tuple[str, float, str]]:
    out = []
    for fid, f in facts.items():
        v = f.get("value")
        if isinstance(v, (int, float)):
            kind = FACT_UNIT_KIND.get(f.get("unit", ""), "other")
            if f.get("unit") == "ratio":
                v = v * 100
            out.append((fid, float(v), kind))
            if f.get("unit") == "month" and v:
                out.append((fid, round(float(v) / 12, 1), "year"))
    return out


def _close(a: float, b: float, kind: str) -> bool:
    if kind == "year":
        return abs(a - b) <= 0.051
    if kind == "money":
        return abs(a - b) <= max(0.5, abs(b) * 0.0005)
    return abs(a - b) <= 0.051


@dataclass
class VerificationRecord:
    run_id: str | None
    role: str
    checked_numbers: int = 0
    facts_used: list[str] = field(default_factory=list)
    violations: list[dict] = field(default_factory=list)
    regenerated: bool = False
    fallback_used: bool = False

    @property
    def status(self) -> str:
        if any(v["severity"] == "error" for v in self.violations):
            return "fail"
        if self.fallback_used:
            return "fallback"
        return "pass_after_retry" if self.regenerated else "pass"

    def to_dict(self) -> dict:
        return {
            "verification_id": "ver_" + uuid.uuid4().hex[:10],
            "run_id": self.run_id,
            "role": self.role,
            "checked_numbers": self.checked_numbers,
            "facts_used": sorted(set(self.facts_used)),
            "violations": self.violations,
            "regenerated": self.regenerated,
            "fallback_used": self.fallback_used,
            "status": self.status,
        }


def render(text: str, facts: dict[str, dict], quotes: dict[str, str] | None = None,
           record: VerificationRecord | None = None) -> str:
    """겹 1: 자리표시를 표시값으로 바꾼다. 없는 id는 위반으로 기록하고 '[?]'로 둔다."""
    quotes = quotes or {}

    def sub(m: re.Match) -> str:
        kind, key = m[1], m[2]
        if kind == "fact":
            f = facts.get(key)
            if f is None:
                if record is not None:
                    record.violations.append({"type": "unknown_fact", "id": key, "severity": "error"})
                return "[?]"
            if record is not None:
                record.facts_used.append(key)
                record.checked_numbers += 1
            return str(f.get("display", f.get("value")))
        q = quotes.get(key)
        if q is None:
            if record is not None:
                record.violations.append({"type": "unknown_quote", "id": key, "severity": "error"})
            return "[?]"
        if record is not None:
            record.checked_numbers += 1
        return q

    return PLACEHOLDER.sub(sub, text)


def scan_numbers(text: str, facts: dict[str, dict], quotes: dict[str, str] | None = None,
                 allow: list[str] | None = None, record: VerificationRecord | None = None) -> list[dict]:
    """겹 2: 자리표시 밖의 숫자를 찾는다(자리표시를 채우기 전 원문에 적용)."""
    quotes = quotes or {}
    allow = allow or []
    stripped = PLACEHOLDER.sub(" ", text)
    quote_hits = [h for q in quotes.values() for h in find_numbers(q)]
    fact_vals = _fact_values(facts)
    found = []
    for h in find_numbers(stripped):
        if h.kind == "year" and 1900 <= h.value <= 2100:  # 연도(2027년 4월 등)는 계산 숫자가 아니다
            continue
        if any(a in stripped[max(0, h.span[0] - 10):h.span[1] + 10] and h.text in a for a in allow):
            continue
        if any(q.kind == h.kind and _close(h.value, q.value, h.kind) for q in quote_hits):
            continue
        match = next((fid for fid, v, k in fact_vals if k == h.kind and _close(h.value, v, k)), None)
        v = ({"type": "raw_number_matching_fact", "text": h.text, "fact_id": match, "severity": "warning"}
             if match else {"type": "raw_number_mismatch", "text": h.text, "severity": "error"})
        found.append(v)
    if record is not None:
        record.checked_numbers += len(find_numbers(stripped))
        record.violations.extend(found)
    return found


# 숫자+받침 있는 단위(원·년·개월·세·명·억) 뒤 조사를 바로잡는다: "35만원가" → "35만원이", "0만원라서" → "0만원이라서".
# 자리표시를 채우면 AI가 숫자를 모른 채 고른 조사가 어색해지기 때문이다.
_PARTICLE = re.compile(r"(\d[\d,.]*\s*(?:만원|억원|억|원|년|개월|세|명))(라서|라고|라는|예요|가|는|를|와|랑|야|로)(?=[^가-힣]|$|는|도|만)")
_FIX = {"가": "이", "는": "은", "를": "을", "와": "과", "랑": "이랑", "야": "이야", "로": "으로",
        "라서": "이라서", "라고": "이라고", "라는": "이라는", "예요": "이에요"}


def fix_particles(text: str) -> str:
    text = re.sub(r"(월|한 달|매달)\s+월\s+(?=\d)", lambda m: m[1] + " ", text)  # "월 월 210만원" → "월 210만원"(표시값에 이미 '월'이 있음)
    return _PARTICLE.sub(lambda m: m[1] + _FIX[m[2]], text)


def verify_texts(texts: dict[str, str], facts: dict[str, dict], *, role: str, run_id: str | None = None,
                 quotes: dict[str, str] | None = None, allow: list[str] | None = None
                 ) -> tuple[dict[str, str], VerificationRecord]:
    """여러 글(필드 경로 → 원문)을 한 번에 검사하고 렌더링한다."""
    rec = VerificationRecord(run_id=run_id, role=role)
    rendered = {}
    for path, t in texts.items():
        if not isinstance(t, str):
            continue
        before = len(rec.violations)
        scan_numbers(t, facts, quotes, allow, rec)
        rendered[path] = fix_particles(render(t, facts, quotes, rec))
        for v in rec.violations[before:]:
            v.setdefault("path", path)
    return rendered, rec


def check_refs(refs: list[tuple[str, str, set]], record: VerificationRecord) -> None:
    """겹 3: (경로, 참조 id, 허용 id 집합) 목록에서 없는 id를 위반으로 기록."""
    for path, ref, allowed in refs:
        if ref not in allowed:
            record.violations.append({"type": "unknown_ref", "path": path, "id": ref, "severity": "error"})


def check_agreement(agreement: dict, saving: float | None, goal: dict, conditions: list[dict],
                    record: VerificationRecord) -> None:
    """겹 3·4: 합의안의 근거와 산술 일관성(docs/05 3.1절).

    분담방식에서 '매달 모이는 돈'을 용도별로 나눈 항목(part_of)이 있으면 그 합이 매달 모이는 돈과 같아야 한다."""
    parts = [float(c.get("amount", 0)) for c in agreement.get("contribution") or [] if c.get("part_of")]
    if parts and (saving is None or abs(sum(parts) - saving) > 0.5):
        record.violations.append({"type": "contribution_sum_mismatch", "expected": saving, "actual": sum(parts),
                                  "severity": "error"})
    ta = agreement.get("target_amount") or {}
    if "value" in ta and goal.get("type") == "reach_target" and abs(float(ta["value"]) - float(goal["target_amount"])) > 0.5:
        record.violations.append({"type": "target_amount_mismatch", "expected": goal["target_amount"],
                                  "actual": ta["value"], "severity": "error"})
    covered = {(c.get("source") or {}).get("member_id") for c in agreement.get("commitments", [])
               if (c.get("source") or {}).get("type") == "condition"}
    for cond in conditions:
        if cond["member_id"] not in covered:
            record.violations.append({"type": "condition_not_reflected", "member_id": cond["member_id"],
                                      "text": cond.get("text", ""), "severity": "error"})
