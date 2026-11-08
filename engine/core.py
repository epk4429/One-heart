"""결정론 계산(docs/04_계산엔진.md 1절).

매달 m(1부터)에 대해:
  1. 목표 풀 잔액이 0보다 크면 잔액 × (1 + 기대수익률/12). 0 이하면 이자 없음.
  2. 이번 달 현금흐름(기본 항목 + 유효 기간 안의 이벤트)을 더한다. 생활비 같은 지출(category "expense")에는
     물가 상승을 붙인다.
  3. 대출 상환액(이자 + 원금, 추가 상환 포함)을 뺀다.
  4. 이번 달 일시금을 더한다.
  5. 목표 판정(reach_target: 풀 ≥ 목표, runway: 풀 < 0, debt_free: 갚아 나가는 대출 잔액 0)의 첫 달을 기록한다.
  6. 순자산용 보조 계정을 갱신한다(목표 풀에는 영향 없음).

물가 0·대출 없음이면 v3 프로토타입 simulate()와 같은 규칙이라 기획안 숫자가 그대로 나온다.
현금흐름·대출·일시금은 수익률과 무관하므로 먼저 달마다 계산해 두고(Schedule), 범위 계산도 같은 표를 쓴다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .schema import Option, Request


@dataclass
class MonthRow:
    m: int
    start: float
    interest: float
    inflow: float
    outflow: float
    lump: float
    end: float
    net_worth: float
    loan_payment: float = 0.0
    debt: float = 0.0


@dataclass
class Schedule:
    """수익률과 상관없이 정해지는 달별 값."""

    inflow: list[float] = field(default_factory=list)
    outflow: list[float] = field(default_factory=list)  # 대출 상환 포함, 음수
    lump: list[float] = field(default_factory=list)
    loan_payment: list[float] = field(default_factory=list)  # 양수
    debt: list[float] = field(default_factory=list)  # 목표 풀 밖 대출 잔액(달 말)
    debt_free_month: int | None = None


@dataclass
class DeterministicResult:
    option_id: str
    hit_month: int | None
    end_pool: float
    rows: list[MonthRow]
    start_net_worth: float
    debt_free_month: int | None = None


def goal_reached(goal_type: str, pool: float, target: float, debt: float = 0.0) -> bool:
    if goal_type == "reach_target":
        return pool >= target
    if goal_type == "debt_free":
        return debt <= 0.005
    return pool < 0  # runway: 바닥난 달


def _inflate(category: str, amount: float, factor: float) -> float:
    return amount * factor if category == "expense" and amount < 0 else amount


def month_flow(option: Option, m: int, factor: float = 1.0) -> tuple[float, float]:
    """이번 달 (들어오는 돈, 나가는 돈). 나가는 돈은 음수. factor는 지출에 붙는 물가 배율."""
    inflow = outflow = 0.0
    for c in option.cashflows:
        a = _inflate(c.category, c.amount, factor)
        if a >= 0:
            inflow += a
        else:
            outflow += a
    for e in option.events:
        if e.from_month <= m <= e.to_month:
            d = _inflate(e.category, e.monthly_delta, factor)
            if d >= 0:
                inflow += d
            else:
                outflow += d
    return inflow, outflow


def month_lump(option: Option, m: int) -> float:
    return sum(l.amount for l in option.lump_sums if l.month == m)


def schedule(req: Request, option: Option) -> Schedule:
    sch = Schedule()
    bal = {l.id: l.balance for l in req.loans}
    extra: dict[str, list] = {}
    for x in option.extra_payments:
        extra.setdefault(x.loan_id, []).append(x)
    monthly_infl = (1 + req.inflation / 100) ** (1 / 12)
    for m in range(1, req.horizon_months + 1):
        factor = monthly_infl ** (m - 1)
        inflow, outflow = month_flow(option, m, factor)
        paid = 0.0
        for l in req.loans:
            b = bal[l.id]
            if b <= 0:
                continue
            interest = b * l.rate / 100 / 12
            add = sum(x.monthly for x in extra.get(l.id, []) if m >= x.from_month)
            add += sum(x.amount for x in option.loan_prepayments if x.label == l.id and x.month == m)
            if l.kind == "interest_only":
                principal = min(add, b)
                pay = interest + principal
            else:
                pay = l.payment + add
                principal = pay - interest
                if principal >= b:
                    principal, pay = b, b + interest
            bal[l.id] = b - principal
            paid += pay
        outflow -= paid
        debt = sum(bal[l.id] for l in req.loans if not l.in_pool)
        if sch.debt_free_month is None and req.loans and debt <= 0.005:
            sch.debt_free_month = m
        sch.inflow.append(inflow)
        sch.outflow.append(outflow)
        sch.lump.append(month_lump(option, m))
        sch.loan_payment.append(paid)
        sch.debt.append(debt)
    return sch


class AuxBook:
    """순자산 보조 계정(05 6절). 자산은 성장률대로, 부채는 accrue 변화대로 움직인다."""

    def __init__(self, req: Request, option: Option):
        self.kind = {a.id: a.kind for a in req.aux_accounts}
        self.value = {a.id: a.value for a in req.aux_accounts}
        self.growth = {a.id: a.growth for a in req.aux_accounts}
        self.changes = option.aux_changes

    def step(self, m: int) -> None:
        for aid, g in self.growth.items():
            if self.kind[aid] == "asset" and g:
                self.value[aid] *= 1 + g / 100 / 12
        for ch in self.changes:
            if ch.type == "accrue" and ch.from_month <= m <= ch.to_month:
                self.value[ch.account_id] = self.value[ch.account_id] * (1 + ch.rate / 100 / 12) + ch.monthly_amount
            elif ch.type == "set" and ch.month == m:
                self.value[ch.account_id] = ch.value

    def net(self) -> float:
        return sum(v if self.kind[k] == "asset" else -v for k, v in self.value.items())


def run_deterministic(req: Request, option: Option, sch: Schedule | None = None) -> DeterministicResult:
    sch = sch or schedule(req, option)
    pool = req.start_pool
    aux = AuxBook(req, option)
    start_debt = sum(l.balance for l in req.loans if not l.in_pool)
    start_net_worth = pool + aux.net() - start_debt
    r = option.expected_return / 100 / 12
    hit: int | None = None
    rows: list[MonthRow] = []
    for i in range(req.horizon_months):
        m = i + 1
        start = pool
        interest = pool * r if pool > 0 else 0.0
        pool += interest
        pool += sch.inflow[i] + sch.outflow[i] + sch.lump[i]
        if hit is None and goal_reached(req.goal.type, pool, req.goal.target_amount, sch.debt[i]):
            hit = m
        aux.step(m)
        rows.append(MonthRow(m, start, interest, sch.inflow[i], sch.outflow[i], sch.lump[i], pool,
                             pool + aux.net() - sch.debt[i], sch.loan_payment[i], sch.debt[i]))
    return DeterministicResult(option.option_id, hit, pool, rows, start_net_worth, sch.debt_free_month)
