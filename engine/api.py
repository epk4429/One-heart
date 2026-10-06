"""엔진 진입점: simulate(), compare() (docs/05_계산엔진.md 3·7절)."""

from __future__ import annotations

import hashlib
import json

from . import fmt
from .core import DeterministicResult, run_deterministic, schedule
from .montecarlo import run_range
from .schema import EngineInputError, Option, Request, parse_request

ENGINE_VERSION = "0.2.0"


def _run_id(raw: dict) -> str:
    payload = json.dumps(raw, ensure_ascii=False, sort_keys=True)
    return "run_" + hashlib.sha256((ENGINE_VERSION + payload).encode()).hexdigest()[:12]


def _yearly(det: DeterministicResult) -> list[dict]:
    out = []
    for y in range(len(det.rows) // 12):
        chunk = det.rows[y * 12:(y + 1) * 12]
        out.append({
            "year": y + 1,
            "start": round(chunk[0].start, 1),
            "net_flow": round(sum(r.inflow + r.outflow + r.lump for r in chunk), 1),
            "interest": round(sum(r.interest for r in chunk), 1),
            "end": round(chunk[-1].end, 1),
            "net_worth_end": round(chunk[-1].net_worth, 1),
            "loan_payment": round(sum(r.loan_payment for r in chunk), 1),
            "debt_end": round(chunk[-1].debt, 1),
        })
    return out


def first_month_flow(det: DeterministicResult) -> float:
    """첫 달에 늘거나 줄어드는 돈(현금흐름 + 이벤트 + 대출 상환, 일시금 제외)."""
    r = det.rows[0]
    return round(r.inflow + r.outflow, 1)


def _basis(req: Request, opt: Option, det: DeterministicResult) -> list[dict]:
    flow = first_month_flow(det)
    parts = [(c.label, c.amount) for c in opt.cashflows]
    if det.rows[0].loan_payment:
        parts.append(("대출 상환", -round(det.rows[0].loan_payment, 1)))
    detail = " ".join(
        (("+ " if i and a >= 0 else "") + ("− " if a < 0 else "") + f"{lab} {abs(a):g}")
        for i, (lab, a) in enumerate(parts)
    )
    rows = [
        {"key": "start", "label": "출발 금액", "value": req.start_pool, "display": fmt.won(req.start_pool),
         "detail": req.pool_label, "source": "financial_snapshot"},
        {"key": "monthly_flow", "label": "한 달에 늘거나 줄어드는 돈", "value": flow,
         "display": ("+" if flow > 0 else "") + fmt.won(flow), "detail": detail, "source": "option"},
        {"key": "return", "label": "1년에 불어나는 비율", "value": opt.expected_return,
         "display": "연 " + fmt.pct(opt.expected_return),
         "source": f"assumption:{opt.return_assumption_id}" if opt.return_assumption_id else "assumption"},
    ]
    if req.inflation:
        rows.append({"key": "inflation", "label": "물가 오름(생활비에 반영)", "value": req.inflation,
                     "display": "연 " + fmt.pct(req.inflation), "source": "assumption:inflation"})
    for l in req.loans:
        how = "이자만 내요" if l.kind == "interest_only" else f"한 달 {fmt.won(l.payment)}씩 갚아요"
        rows.append({"key": f"loan:{l.id}", "label": l.label or "대출", "value": -l.balance,
                     "display": "-" + fmt.won(l.balance), "detail": f"연 {fmt.pct(l.rate)} · {how}"
                     + (" · 목표 금액에서 이미 뺐어요" if l.in_pool else ""), "source": "financial_snapshot"})
    for x in opt.extra_payments:
        lab = next((l.label for l in req.loans if l.id == x.loan_id), x.loan_id)
        rows.append({"key": f"extra:{x.loan_id}", "label": f"{lab} 더 갚기", "value": -x.monthly,
                     "display": fmt.won(-x.monthly) + " / 한 달", "detail": f"{x.from_month}개월째부터", "source": "option"})
    for x in opt.loan_prepayments:
        lab = next((l.label for l in req.loans if l.id == x.label), x.label)
        rows.append({"key": f"prepay:{x.label}:{x.month}", "label": f"{lab} 한 번에 갚기", "value": -x.amount,
                     "display": fmt.won(-x.amount), "detail": f"{x.month}개월째, 예금에서", "source": "option"})
    for e in opt.events:
        rows.append({"key": f"event:{e.label}", "label": e.label, "value": e.monthly_delta,
                     "display": fmt.won(e.monthly_delta) + " / 한 달",
                     "detail": f"{e.from_month}~{e.to_month}개월째", "source": "assumption"})
    for l in opt.lump_sums:
        rows.append({"key": f"lump:{l.month}", "label": l.label or "한 번에 들어오는 돈", "value": l.amount,
                     "display": ("+" if l.amount > 0 else "") + fmt.won(l.amount),
                     "detail": f"{l.month}개월째", "source": "assumption"})
    rows.append({"key": "goal", "label": "가족이 정한 기준", "value": req.goal.target_amount,
                 "display": req.goal.label or (fmt.won(req.goal.target_amount) if req.goal.type == "reach_target"
                                               else {"runway": "예금이 바닥나지 않기", "debt_free": "대출 다 갚기"}[req.goal.type]),
                 "source": "goal_setting"})
    return rows


def _facts(req: Request, opt: Option, det: DeterministicResult, rng: dict | None) -> list[dict]:
    p = opt.option_id
    h = det.hit_month
    flow = first_month_flow(det)
    facts = [
        {"fact_id": f"{p}.goal_hit_month", "value": h, "unit": "month",
         "display": f"{h}개월" if h else fmt.years_display(None, req.horizon_months, req.goal.type)},
        {"fact_id": f"{p}.goal_hit_years", "value": fmt.years_from_months(h) if h else None, "unit": "year",
         "display": fmt.years_display(h, req.horizon_months, req.goal.type)},
        {"fact_id": f"{p}.monthly_flow", "value": flow, "unit": "만원/월",
         "display": fmt.won(flow)},
        {"fact_id": f"{p}.return", "value": opt.expected_return, "unit": "%/년",
         "display": "연 " + fmt.pct(opt.expected_return)},
        {"fact_id": f"{p}.end_pool", "value": round(det.end_pool, 1), "unit": "만원",
         "display": fmt.won(det.end_pool)},
        {"fact_id": f"{p}.min_pool", "value": round(min(r.end for r in det.rows), 1), "unit": "만원",
         "display": fmt.won(min(r.end for r in det.rows)), "label": "기간 중 예금이 가장 적을 때"},
        {"fact_id": f"{p}.end_net_worth", "value": round(det.rows[-1].net_worth, 1), "unit": "만원",
         "display": fmt.won(det.rows[-1].net_worth)},
        {"fact_id": "goal.target_amount", "value": req.goal.target_amount, "unit": "만원",
         "display": fmt.won(req.goal.target_amount)},
        {"fact_id": "start.pool", "value": req.start_pool, "unit": "만원", "display": fmt.won(req.start_pool)},
        {"fact_id": "horizon.years", "value": req.horizon_months / 12, "unit": "year",
         "display": f"{req.horizon_months // 12}년"},
    ]
    if req.base_age is not None and h:
        facts.append({"fact_id": f"{p}.age_at_hit", "value": fmt.age_at(req.base_age, h), "unit": "세",
                      "display": f"{fmt.age_at(req.base_age, h)}세쯤"})
    for i, c in enumerate(opt.cashflows):
        facts.append({"fact_id": f"{p}.cashflow.{i}", "value": c.amount, "unit": "만원/월",
                      "display": fmt.won(abs(c.amount)), "label": c.label})  # 부호는 항목 이름이 말해 준다
    for e in opt.events:
        facts.append({"fact_id": f"{p}.event.{e.label}", "value": e.monthly_delta, "unit": "만원/월",
                      "display": fmt.won(abs(e.monthly_delta)), "label": e.label})
    for j, l in enumerate(opt.lump_sums):
        facts.append({"fact_id": f"{p}.lump.{j}", "value": l.amount, "unit": "만원",
                      "display": fmt.won(abs(l.amount)), "label": l.label})
    if req.loans:
        facts.append({"fact_id": f"{p}.loan_payment", "value": round(det.rows[0].loan_payment, 1), "unit": "만원/월",
                      "display": fmt.won(det.rows[0].loan_payment), "label": "한 달 대출 상환"})
        d = det.debt_free_month
        facts.append({"fact_id": f"{p}.debt_free_years", "value": fmt.years_from_months(d) if d else None,
                      "unit": "year", "display": f"약 {fmt.round1(d / 12)}년" if d else f"{req.horizon_months // 12}년 넘게",
                      "label": "대출을 다 갚는 때"})
        facts.append({"fact_id": f"{p}.end_debt", "value": round(det.rows[-1].debt, 1), "unit": "만원",
                      "display": fmt.won(det.rows[-1].debt), "label": "기간 끝 대출 잔액"})
    if rng:
        for key in ("p10_hit_month", "p50_hit_month", "p90_hit_month"):
            v = rng[key]
            facts.append({"fact_id": f"{p}.range.{key}", "value": v, "unit": "month",
                          "display": fmt.years_display(v, req.horizon_months, req.goal.type)})
        prob_key = "prob_reach_within" if "prob_reach_within" in rng else "prob_last_through"
        facts.append({"fact_id": f"{p}.range.{prob_key}", "value": rng[prob_key], "unit": "ratio",
                      "display": f"{round(rng[prob_key] * 100)}%"})
    # facts 키는 중복 없이(goal/start/horizon은 옵션마다 같으므로 api에서 한 번만 남긴다)
    return facts


def simulate(raw: dict, *, include_monthly: bool = True) -> dict:
    """엔진 요청(dict) → 결과(dict). 입력 오류는 {"error": {...}}로 돌려준다."""
    try:
        req = parse_request(raw)
    except EngineInputError as e:
        return e.to_dict()
    results = []
    seen_shared: set[str] = set()
    for i, opt in enumerate(req.options):
        sch = schedule(req, opt)
        det = run_deterministic(req, opt, sch)
        rng = run_range(req, opt, req.range_seed + i * 17, sch)
        facts = []
        for f in _facts(req, opt, det, rng):
            if not f["fact_id"].startswith(opt.option_id + "."):
                if f["fact_id"] in seen_shared:
                    continue
                seen_shared.add(f["fact_id"])
            facts.append(f)
        item = {
            "option_id": opt.option_id,
            "label": opt.label,
            "goal_hit_month": det.hit_month,
            "goal_hit_years": fmt.years_from_months(det.hit_month) if det.hit_month else None,
            "goal_hit_display": fmt.years_display(det.hit_month, req.horizon_months, req.goal.type),
            "end_pool": round(det.end_pool, 1),
            "monthly_flow": first_month_flow(det),
            "debt_free_month": det.debt_free_month,
            "start_debt": round(sum(l.balance for l in req.loans if not l.in_pool), 1),
            "yearly": _yearly(det),
            "net_worth": [{"m": 0, "value": round(det.start_net_worth, 1)}]
                         + [{"m": r.m, "value": round(r.net_worth, 1)} for r in det.rows if r.m % 12 == 0],
            "range": rng,
            "basis": _basis(req, opt, det),
            "facts": facts,
        }
        if req.base_age is not None and det.hit_month:
            item["age_at_hit"] = fmt.age_at(req.base_age, det.hit_month)
        if include_monthly:
            item["monthly"] = [{"m": r.m, "start": round(r.start, 1), "interest": round(r.interest, 1),
                                "inflow": round(r.inflow, 1), "outflow": round(r.outflow, 1), "lump": r.lump,
                                "loan_payment": round(r.loan_payment, 1), "debt": round(r.debt, 1),
                                "end": round(r.end, 1), "net_worth": round(r.net_worth, 1)} for r in det.rows]
        results.append(item)
    return {
        "run_id": _run_id(raw),
        "engine_version": ENGINE_VERSION,
        "scenario_id": req.scenario_id,
        "goal": {"type": req.goal.type, "target_amount": req.goal.target_amount, "label": req.goal.label},
        "horizon_months": req.horizon_months,
        "inflation": req.inflation,
        "results": results,
    }


def tool_summary(result: dict) -> dict:
    """LLM tool(run_simulation)용 요약: monthly 표를 빼고 facts 중심으로(05 8절)."""
    if "error" in result:
        return result
    return {
        "run_id": result["run_id"],
        "results": [{
            "option_id": r["option_id"],
            "goal_hit": r["goal_hit_display"],
            "end_pool": r["end_pool"],
            "range": {k: v for k, v in (r["range"] or {}).items() if k.startswith("prob")},
            "facts": [{"fact_id": f["fact_id"], "display": f["display"]} for f in r["facts"]],
        } for r in result["results"]],
    }


def compare(before: dict, after: dict) -> dict:
    """재점검: 두 simulate 결과의 차이(05 7절). 같은 option_id끼리 비교."""
    a = {r["option_id"]: r for r in before.get("results", [])}
    b = {r["option_id"]: r for r in after.get("results", [])}
    diffs = []
    for oid in a.keys() & b.keys():
        ra, rb = a[oid], b[oid]
        ha, hb = ra["goal_hit_month"], rb["goal_hit_month"]
        diffs.append({
            "option_id": oid,
            "hit_month_before": ha,
            "hit_month_after": hb,
            "hit_month_delta": (hb - ha) if (ha is not None and hb is not None) else None,
            "end_pool_delta": round(rb["end_pool"] - ra["end_pool"], 1),
            "end_net_worth_delta": round(rb["net_worth"][-1]["value"] - ra["net_worth"][-1]["value"], 1),
            "before_display": ra["goal_hit_display"],
            "after_display": rb["goal_hit_display"],
        })
    return {"run_before": before.get("run_id"), "run_after": after.get("run_id"),
            "diffs": sorted(diffs, key=lambda d: d["option_id"])}
