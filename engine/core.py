"""결정론 계산(docs/04_계산엔진.md 1절).

매달 m(1부터)에 대해:
  1. 이자가 붙는 몫(목표 풀 − 보증금처럼 이자 없는 몫)이 0보다 크면 그 몫 × 기대수익률/12를 더한다.
  2. 이번 달 현금흐름(기본 항목 + 유효 기간 안의 이벤트)을 더한다. 생활비 같은 지출(category "expense")에는
     물가 상승을, 월급(grows)에는 월급 상승률을 붙인다. 기간(from_month~to_month)이 있는 항목은 그 기간에만.
  3. 대출 상환액(이자 + 원금, 추가 상환 포함)을 뺀다.
  4. 이번 달 일시금을 더한다.
  5. (대출 다 갚기 + sweep) 예금이 비상금 선을 넘는 만큼을 금리 높은 대출부터 더 갚는다.
  6. 목표 판정의 첫 달을 기록한다. reach_target: 풀 − 비상금 선 ≥ 목표(집값 상승을 붙인 목표),
     runway: 예금 < 비상금 선(비상금만 남는 때, 선이 0이면 바닥난 때), debt_free: 갚아 나가는 대출 잔액 0.
  7. 순자산용 보조 계정을 갱신한다(목표 풀에는 영향 없음).

물가·월급 상승·비상금 선·대출이 없으면 v3 프로토타입 simulate()와 같은 규칙이라 기획안 숫자가 그대로 나온다.
현금흐름·대출·일시금은 수익률과 무관하므로 먼저 달마다 계산해 두고(Schedule), 범위 계산도 같은 표를 쓴다.
sweep은 예금 잔액에 따라 대출 상환이 달라지므로 달마다 한 번에 계산한다(범위 계산은 대출 목표에 쓰지 않는다).
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
    swept: float = 0.0  # 이번 달 비상금 선을 넘어 대출을 더 갚은 돈(outflow·loan_payment에 들어 있음)


@dataclass
class Schedule:
    """수익률과 상관없이 정해지는 달별 값."""

    inflow: list[float] = field(default_factory=list)
    outflow: list[float] = field(default_factory=list)  # 대출 상환 포함, 음수
    lump: list[float] = field(default_factory=list)
    loan_payment: list[float] = field(default_factory=list)  # 양수
    debt: list[float] = field(default_factory=list)  # 화면·목표에 쓰는 대출 잔액(달 말). 대출 다 갚기 목표에서는 이자만 내는 전세대출을 뺀다(만기에 보증금으로 정리하므로)
    debt_all: list[float] = field(default_factory=list)  # 목표 풀 밖 대출 잔액 전부(순자산 계산용)
    debt_free_month: int | None = None


@dataclass
class DeterministicResult:
    option_id: str
    hit_month: int | None
    end_pool: float
    rows: list[MonthRow]
    start_net_worth: float
    debt_free_month: int | None = None
    min_cash: float | None = None  # 기간 중 비상금으로 셀 수 있는 예금이 가장 적을 때(목표 달성 전까지, runway는 바닥나기 전까지)
    floor_breach_month: int | None = None  # 예금이 처음으로 비상금 선 아래로 내려가는 달(같은 범위, 2026-11-15 적자 상태)
    floor_fill_month: int | None = None    # 처음부터 예금이 비상금 선보다 적었다면, 선을 처음 채우는 달


def goal_reached(goal_type: str, pool: float, target: float, debt: float = 0.0, floor: float = 0.0,
                 cash: float | None = None) -> bool:
    if goal_type == "reach_target":
        return pool - floor >= target
    if goal_type == "debt_free":
        return debt <= 0.005
    return (pool if cash is None else cash) < floor  # runway: 비상금만 남는(선이 0이면 바닥난) 달


def floor_of(req: Request, option: Option) -> float:
    return req.floor if option.floor is None else max(req.floor, option.floor)


def target_at(req: Request, m: int) -> float:
    """m달째의 목표 금액(집값 상승률을 붙인 값)."""
    g = req.goal.target_growth
    return req.goal.target_amount * (1 + g / 100) ** ((m - 1) / 12) if g else req.goal.target_amount


def _inflate(category: str, amount: float, factor: float) -> float:
    return amount * factor if category == "expense" and amount < 0 else amount


def month_flow(option: Option, m: int, factor: float = 1.0, wage: float = 1.0) -> tuple[float, float]:
    """이번 달 (들어오는 돈, 나가는 돈). 나가는 돈은 음수. factor는 지출에 붙는 물가 배율, wage는 월급 상승 배율."""
    inflow = outflow = 0.0
    for c in option.cashflows:
        if not c.active(m):
            continue
        a = _inflate(c.category, c.amount, factor)
        if c.grows and a > 0:
            a *= wage
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


def _factors(req: Request, m: int) -> tuple[float, float]:
    infl = (1 + req.inflation / 100) ** ((m - 1) / 12)
    wage = (1 + req.income_growth / 100) ** ((m - 1) / 12)
    return infl, wage


def _pay_loans(req: Request, option: Option, bal: dict, extra: dict, m: int) -> float:
    """이번 달 대출 상환(정해진 상환 + 추가 상환 + 일시 상환). bal을 고치고 낸 돈(양수)을 돌려준다."""
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
            pay = option.loan_payments.get(l.id, l.payment) + add
            principal = pay - interest
            if principal >= b:
                principal, pay = b, b + interest
        bal[l.id] = b - principal
        paid += pay
    return paid


def _debts(req: Request, bal: dict) -> tuple[float, float]:
    debt_all = sum(bal[l.id] for l in req.loans if not l.in_pool)
    debt = sum(bal[l.id] for l in req.loans if not l.in_pool and not (req.goal.type == "debt_free" and l.kind == "interest_only"))
    return debt, debt_all


def schedule(req: Request, option: Option) -> Schedule:
    sch = Schedule()
    bal = {l.id: l.balance for l in req.loans}
    extra: dict[str, list] = {}
    for x in option.extra_payments:
        extra.setdefault(x.loan_id, []).append(x)
    for m in range(1, req.horizon_months + 1):
        inflow, outflow = month_flow(option, m, *_factors(req, m))
        paid = _pay_loans(req, option, bal, extra, m)
        outflow -= paid
        debt, debt_all = _debts(req, bal)
        if sch.debt_free_month is None and req.loans and debt <= 0.005:
            sch.debt_free_month = m
        sch.inflow.append(inflow)
        sch.outflow.append(outflow)
        sch.lump.append(month_lump(option, m))
        sch.loan_payment.append(paid)
        sch.debt.append(debt)
        sch.debt_all.append(debt_all)
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


def _sweep(req: Request, bal: dict, excess: float) -> float:
    """비상금 선을 넘는 돈으로 금리가 높은 갚아 나가는 대출부터 더 갚는다. 갚은 돈을 돌려준다."""
    paid = 0.0
    for l in sorted((l for l in req.loans if l.kind == "amortizing" and not l.in_pool), key=lambda l: -l.rate):
        if excess - paid <= 0.005:
            break
        b = bal[l.id]
        if b <= 0:
            continue
        p = min(b, excess - paid)
        bal[l.id] = b - p
        paid += p
    return paid


def run_deterministic(req: Request, option: Option, sch: Schedule | None = None) -> DeterministicResult:
    if req.sweep and req.goal.type == "debt_free":
        return _run_sweep(req, option)
    sch = sch or schedule(req, option)
    pool = req.start_pool
    aux = AuxBook(req, option)
    floor = floor_of(req, option)
    start_debt = sum(l.balance for l in req.loans if not l.in_pool)
    start_net_worth = pool + aux.net() - start_debt
    r = option.expected_return / 100 / 12
    hit: int | None = None
    min_cash: float | None = None
    breach: int | None = None
    fill: int | None = None
    below0 = req.cash(req.start_pool) < floor - 0.005  # 처음부터 비상금 선보다 적은 가족
    rows: list[MonthRow] = []
    for i in range(req.horizon_months):
        m = i + 1
        start = pool
        interest = max(pool - req.idle_pool, 0.0) * r  # 이자는 불어나는 돈에만(전세 보증금 몫에는 안 붙는다)
        pool += interest
        pool += sch.inflow[i] + sch.outflow[i] + sch.lump[i]
        cash = req.cash(pool)
        if hit is None or m <= req.min_until:
            min_cash = cash if min_cash is None else min(min_cash, cash)
            if cash >= floor - 0.005 and fill is None and below0:
                fill = m
            if breach is None and cash < floor - 0.005 and req.goal.type != "runway" and (not below0 or fill):
                breach = m
        if hit is None and goal_reached(req.goal.type, pool, target_at(req, m), sch.debt[i], floor, cash):
            hit = m
        aux.step(m)
        rows.append(MonthRow(m, start, interest, sch.inflow[i], sch.outflow[i], sch.lump[i], pool,
                             pool + aux.net() - sch.debt_all[i], sch.loan_payment[i], sch.debt[i]))
    return DeterministicResult(option.option_id, hit, pool, rows, start_net_worth, sch.debt_free_month, _round(min_cash), breach, fill)


def _run_sweep(req: Request, option: Option) -> DeterministicResult:
    """대출 다 갚기 + 남는 돈 규칙: 달마다 예금이 비상금 선을 넘는 만큼을 대출에 더 갚는다(2026-11-15)."""
    pool = req.start_pool
    aux = AuxBook(req, option)
    floor = floor_of(req, option)
    bal = {l.id: l.balance for l in req.loans}
    extra: dict[str, list] = {}
    for x in option.extra_payments:
        extra.setdefault(x.loan_id, []).append(x)
    start_net_worth = pool + aux.net() - sum(l.balance for l in req.loans if not l.in_pool)
    r = option.expected_return / 100 / 12
    hit = debt_free = breach = fill = None
    below0 = req.cash(req.start_pool) < floor - 0.005
    min_cash: float | None = None
    rows: list[MonthRow] = []
    for m in range(1, req.horizon_months + 1):
        start = pool
        interest = max(pool - req.idle_pool, 0.0) * r
        inflow, outflow = month_flow(option, m, *_factors(req, m))
        paid = _pay_loans(req, option, bal, extra, m)
        lump = month_lump(option, m)
        pool += interest + inflow + outflow - paid + lump
        swept = _sweep(req, bal, req.cash(pool) - floor) if req.cash(pool) > floor else 0.0
        pool -= swept
        paid += swept
        debt, debt_all = _debts(req, bal)
        cash = req.cash(pool)
        if hit is None or m <= req.min_until:
            min_cash = cash if min_cash is None else min(min_cash, cash)
            if cash >= floor - 0.005 and fill is None and below0:
                fill = m
            if breach is None and cash < floor - 0.005 and (not below0 or fill):
                breach = m
        if debt_free is None and req.loans and debt <= 0.005:
            debt_free = m
        if hit is None and goal_reached(req.goal.type, pool, target_at(req, m), debt, floor, cash):
            hit = m
        aux.step(m)
        rows.append(MonthRow(m, start, interest, inflow, outflow - paid, lump, pool, pool + aux.net() - debt_all, paid, debt, swept))
    return DeterministicResult(option.option_id, hit, pool, rows, start_net_worth, debt_free, _round(min_cash), breach, fill)


def _round(v: float | None) -> float | None:
    return None if v is None else round(v, 1)
