"""범위 계산(보조 정보, docs/05_계산엔진.md 4절).

매달 수익률을 정규분포(평균 r/12, 표준편차 volatility/√12)에서 뽑아 결정론 계산과 같은
규칙으로 여러 번 돌린다. 시드를 고정해 시연할 때마다 같은 결과가 나온다.
화면의 주 숫자는 결정론 값이고, 이 결과는 "운이 좋으면/보통이면/운이 나쁘면" 펼쳐 보기에 쓴다.
현금흐름·대출·일시금은 수익률과 무관하므로 결정론 계산과 같은 달별 표(Schedule)를 쓴다.
"""

from __future__ import annotations

import math
import random

from .core import Schedule, goal_reached, schedule
from .schema import Option, Request


def _quantile(sorted_vals: list[float], q: float) -> float:
    # v3 시안과 같은 방식(내림 인덱스)
    return sorted_vals[min(len(sorted_vals) - 1, int(q * (len(sorted_vals) - 1)))]


def run_range(req: Request, option: Option, seed: int, sch: Schedule | None = None) -> dict | None:
    n = req.range_paths
    if n <= 0 or option.volatility <= 0 or req.goal.type == "debt_free":
        return None  # 빚을 다 갚는 때는 수익률과 상관없이 정해진다
    sch = sch or schedule(req, option)
    rnd = random.Random(seed)
    mu = option.expected_return / 100 / 12
    sd = option.volatility / 100 / math.sqrt(12)
    horizon = req.horizon_months
    flows = [sch.inflow[i] + sch.outflow[i] + sch.lump[i] for i in range(horizon)]
    hits: list[float] = []
    ends: list[float] = []
    for _ in range(n):
        pool = req.start_pool
        hit = math.inf
        for i in range(horizon):
            if pool > 0:
                pool *= 1 + rnd.gauss(mu, sd)
            pool += flows[i]
            if hit == math.inf and goal_reached(req.goal.type, pool, req.goal.target_amount):
                hit = i + 1
        hits.append(hit)
        ends.append(pool)
    hits.sort()
    ends.sort()
    within = req.goal.within_months or horizon
    reached = sum(1 for h in hits if h <= within) / n

    def m_or_none(v: float) -> int | None:
        return None if v == math.inf else int(v)

    out = {
        "paths": n,
        "seed": seed,
        "p10_hit_month": m_or_none(_quantile(hits, 0.1)),
        "p50_hit_month": m_or_none(_quantile(hits, 0.5)),
        "p90_hit_month": m_or_none(_quantile(hits, 0.9)),
        "p10_end_pool": round(_quantile(ends, 0.1), 1),
        "p50_end_pool": round(_quantile(ends, 0.5), 1),
        "p90_end_pool": round(_quantile(ends, 0.9), 1),
        "within_months": within,
    }
    if req.goal.type == "reach_target":
        out["prob_reach_within"] = round(reached, 3)  # 기한 안에 목표에 닿을 가능성
    else:
        out["prob_last_through"] = round(1 - reached, 3)  # 기한 끝까지 바닥나지 않을 가능성
    return out
