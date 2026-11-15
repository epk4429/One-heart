"""엔진 입력 스키마와 입력 검사(docs/04_계산엔진.md 2절).

LLM(역할 5)이 이상한 조건을 내도 엔진이 멈추거나 터무니없는 숫자를 내지 않도록,
허용 범위를 벗어난 값은 EngineInputError로 거부한다. 오류 메시지는 LLM에 그대로 돌려줘
조건을 고치게 한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

MAX_HORIZON = 960  # 80년(노후는 100세까지 계산, 2026-11-15에 360에서 늘림)
MAX_RETURN = 12.0
MAX_VOLATILITY = 30.0
MAX_CASHFLOW = 2000.0
MAX_LUMP = 100000.0
MAX_EVENTS = 10

GOAL_TYPES = ("reach_target", "runway", "debt_free")
AUX_KINDS = ("asset", "debt")
LOAN_KINDS = ("amortizing", "interest_only")
MAX_LOAN = 1_000_000.0
MAX_INFLATION = 10.0


class EngineInputError(ValueError):
    def __init__(self, field_path: str, reason: str):
        super().__init__(f"{field_path}: {reason}")
        self.field = field_path
        self.reason = reason

    def to_dict(self) -> dict:
        return {"error": {"field": self.field, "reason": self.reason}}


@dataclass
class Cashflow:
    label: str
    amount: float
    category: str = "other"
    from_month: int = 1   # 이 달부터(2026-11-15: 은퇴·휴직처럼 기간이 있는 수입·지출)
    to_month: int = 0     # 이 달까지(0 = 끝까지)
    grows: bool = False   # 월급처럼 해마다 오르는 수입(요청의 income_growth를 붙인다)

    def active(self, m: int) -> bool:
        return self.from_month <= m and (not self.to_month or m <= self.to_month)


@dataclass
class Event:
    label: str
    from_month: int
    to_month: int
    monthly_delta: float
    category: str = "other"


@dataclass
class LumpSum:
    month: int
    amount: float
    label: str = ""


@dataclass
class AuxAccount:
    id: str
    kind: str
    value: float
    growth: float = 0.0  # 자산 가치 상승률 %/년
    rate: float = 0.0  # 부채 이자율 %/년(참고용, 이자만 내는 대출은 잔액 고정)
    label: str = ""


@dataclass
class AuxChange:
    """순자산용 보조 계정 변화. 목표 풀에는 영향이 없다(05 6절)."""

    type: str  # "accrue" | "set"
    account_id: str
    from_month: int = 1
    to_month: int = 0
    monthly_amount: float = 0.0
    rate: float = 0.0
    month: int = 0
    value: float = 0.0


@dataclass
class Loan:
    """대출. 매달 이자 = 잔액 × 금리/12. amortizing은 정해진 월 상환액에서 이자를 뺀 만큼 원금이 준다.
    interest_only(전세대출 등)는 이자만 내고 잔액은 그대로다. in_pool이면 잔액이 이미 목표 풀에서 빠져 있다."""

    id: str
    label: str
    balance: float
    rate: float
    kind: str = "amortizing"
    payment: float = 0.0  # 월 상환액(원리금, 양수). interest_only는 무시하고 이자로 계산
    in_pool: bool = False


@dataclass
class ExtraPayment:
    """방법(Option)이 정하는 추가 상환: 매달 이만큼 더 갚는다(목표 풀에서 나감)."""

    loan_id: str
    monthly: float
    from_month: int = 1


@dataclass
class Option:
    option_id: str
    label: str
    cashflows: list[Cashflow]
    expected_return: float
    volatility: float = 0.0
    return_assumption_id: str = ""
    description: str = ""
    events: list[Event] = field(default_factory=list)
    lump_sums: list[LumpSum] = field(default_factory=list)
    aux_changes: list[AuxChange] = field(default_factory=list)
    extra_payments: list[ExtraPayment] = field(default_factory=list)
    loan_prepayments: list[LumpSum] = field(default_factory=list)  # label 자리에 loan_id
    floor: float | None = None  # 이 방법이 지키는 비상금 선(가족이 정한 선 이상). 없으면 요청의 floor
    loan_payments: dict = field(default_factory=dict)  # 대출 id → 이 방법의 월 상환액(대출 기간 늘리기, 2026-11-15)

    @property
    def monthly_flow(self) -> float:
        return sum(c.amount for c in self.cashflows)


@dataclass
class Goal:
    type: str
    target_amount: float = 0.0
    label: str = ""
    within_months: int | None = None  # "○년 안 가능성" 기준(범위 계산)
    target_growth: float = 0.0  # 목표 금액이 해마다 오르는 비율 %/년(내 집 마련: 집값 상승, 2026-11-15)


@dataclass
class Request:
    scenario_id: str
    horizon_months: int
    start_pool: float
    pool_label: str
    goal: Goal
    options: list[Option]
    aux_accounts: list[AuxAccount] = field(default_factory=list)
    loans: list[Loan] = field(default_factory=list)
    inflation: float = 0.0  # %/년. category가 "expense"인 현금흐름·이벤트에만 붙는다
    base_age: int | None = None
    range_paths: int = 1000
    range_seed: int = 1000
    idle_pool: float = 0.0  # 목표 풀 중 이자가 안 붙는 몫(전세 보증금 − 전세대출 등). 이자는 (풀 − 이 값)에만 붙는다(2026-11-15)
    floor: float = 0.0       # 비상금 선(가족이 정함). 예금(풀 − idle − illiquid)이 이 아래로 가면 안 되는 선(2026-11-15)
    illiquid: float = 0.0    # 풀 중 비상금으로 세지 않는 몫(주식 등)
    income_growth: float = 0.0  # 월급 상승률 %/년(grows인 수입에만)
    sweep: bool = False      # 대출 다 갚기: 예금이 비상금 선을 넘는 만큼을 금리 높은 대출부터 더 갚는다
    min_until: int = 0       # 이 달까지는 목표에 닿은 뒤에도 '예금이 가장 적을 때'를 본다(육아: 휴직이 끝날 때까지 비상금을 지키는지)

    def cash(self, pool: float) -> float:
        """비상금으로 셀 수 있는 예금 = 풀 − 이자 없는 몫(보증금) − 주식 등."""
        return pool - self.idle_pool - self.illiquid


def _num(d: dict, key: str, path: str, *, default: Any = None, lo: float | None = None,
         hi: float | None = None, integer: bool = False) -> Any:
    if key not in d or d[key] is None:
        if default is not None:
            return default
        raise EngineInputError(f"{path}.{key}", "필수 값이 없어요")
    v = d[key]
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise EngineInputError(f"{path}.{key}", "숫자여야 해요")
    if integer and int(v) != v:
        raise EngineInputError(f"{path}.{key}", "정수여야 해요")
    if lo is not None and v < lo:
        raise EngineInputError(f"{path}.{key}", f"{lo} 이상이어야 해요")
    if hi is not None and v > hi:
        raise EngineInputError(f"{path}.{key}", f"{hi} 이하여야 해요")
    return int(v) if integer else float(v)


def _month(d: dict, key: str, path: str, horizon: int, default: Any = None) -> int:
    return _num(d, key, path, default=default, lo=1, hi=horizon, integer=True)


def _parse_option(o: dict, i: int, horizon: int, aux_ids: set[str], loan_ids: set[str] | None = None) -> Option:
    path = f"options[{i}]"
    if not isinstance(o, dict):
        raise EngineInputError(path, "객체여야 해요")
    oid = str(o.get("option_id") or "").strip()
    if not oid:
        raise EngineInputError(f"{path}.option_id", "필수 값이 없어요")
    raw_cf = o.get("cashflows")
    if not isinstance(raw_cf, list) or not raw_cf:
        raise EngineInputError(f"{path}.cashflows", "현금흐름 항목이 1개 이상 필요해요")
    cashflows = []
    for j, c in enumerate(raw_cf):
        cp = f"{path}.cashflows[{j}]"
        f_m = _month(c, "from_month", cp, horizon, default=1)
        t_m = _num(c, "to_month", cp, default=0, lo=0, hi=horizon, integer=True)
        if t_m and t_m < f_m:
            raise EngineInputError(f"{cp}.to_month", "from_month보다 작을 수 없어요")
        cashflows.append(Cashflow(label=str(c.get("label", "")), amount=_num(c, "amount", cp, lo=-MAX_CASHFLOW, hi=MAX_CASHFLOW),
                                  category=str(c.get("category", "other")), from_month=f_m, to_month=t_m,
                                  grows=bool(c.get("grows", False))))
    events_raw = o.get("events") or []
    lumps_raw = o.get("lump_sums") or []
    if len(events_raw) > MAX_EVENTS:
        raise EngineInputError(f"{path}.events", f"{MAX_EVENTS}개 이하여야 해요")
    if len(lumps_raw) > MAX_EVENTS:
        raise EngineInputError(f"{path}.lump_sums", f"{MAX_EVENTS}개 이하여야 해요")
    events = []
    for j, e in enumerate(events_raw):
        ep = f"{path}.events[{j}]"
        f_m = _month(e, "from_month", ep, horizon)
        t_m = _month(e, "to_month", ep, horizon)
        if t_m < f_m:
            raise EngineInputError(f"{ep}.to_month", "from_month보다 작을 수 없어요")
        events.append(Event(
            label=str(e.get("label", "")), from_month=f_m, to_month=t_m,
            monthly_delta=_num(e, "monthly_delta", ep, lo=-MAX_CASHFLOW, hi=MAX_CASHFLOW),
            category=str(e.get("category", "other")),
        ))
    lumps = [
        LumpSum(month=_month(l, "month", f"{path}.lump_sums[{j}]", horizon),
                amount=_num(l, "amount", f"{path}.lump_sums[{j}]", lo=-MAX_LUMP, hi=MAX_LUMP),
                label=str(l.get("label", "")))
        for j, l in enumerate(lumps_raw)
    ]
    changes = []
    for j, a in enumerate(o.get("aux_changes") or []):
        ap = f"{path}.aux_changes[{j}]"
        t = a.get("type")
        acc = str(a.get("account_id", ""))
        if acc not in aux_ids:
            raise EngineInputError(f"{ap}.account_id", "없는 보조 계정이에요")
        if t == "accrue":
            f_m = _month(a, "from_month", ap, horizon)
            t_m = _month(a, "to_month", ap, horizon)
            changes.append(AuxChange(type=t, account_id=acc, from_month=f_m, to_month=t_m,
                                     monthly_amount=_num(a, "monthly_amount", ap, lo=0, hi=MAX_CASHFLOW),
                                     rate=_num(a, "rate", ap, default=0.0, lo=0, hi=MAX_RETURN)))
        elif t == "set":
            changes.append(AuxChange(type=t, account_id=acc, month=_month(a, "month", ap, horizon),
                                     value=_num(a, "value", ap, lo=0, hi=10_000_000)))
        else:
            raise EngineInputError(f"{ap}.type", "accrue 또는 set이어야 해요")
    extras = []
    for j, x in enumerate(o.get("extra_payments") or []):
        xp = f"{path}.extra_payments[{j}]"
        lid = str(x.get("loan_id", ""))
        if lid not in (loan_ids or set()):
            raise EngineInputError(f"{xp}.loan_id", "없는 대출이에요")
        extras.append(ExtraPayment(loan_id=lid, monthly=_num(x, "monthly", xp, lo=0, hi=MAX_CASHFLOW),
                                   from_month=_month(x, "from_month", xp, horizon, default=1)))
    prepays = []
    for j, x in enumerate(o.get("loan_prepayments") or []):
        xp = f"{path}.loan_prepayments[{j}]"
        lid = str(x.get("loan_id", ""))
        if lid not in (loan_ids or set()):
            raise EngineInputError(f"{xp}.loan_id", "없는 대출이에요")
        prepays.append(LumpSum(month=_month(x, "month", xp, horizon), amount=_num(x, "amount", xp, lo=1, hi=MAX_LOAN),
                               label=lid))
    return Option(
        option_id=oid,
        label=str(o.get("label", oid)),
        description=str(o.get("description", "")),
        cashflows=cashflows,
        expected_return=_num(o, "expected_return", path, lo=0, hi=MAX_RETURN),
        volatility=_num(o, "volatility", path, default=0.0, lo=0, hi=MAX_VOLATILITY),
        return_assumption_id=str(o.get("return_assumption_id", "")),
        events=events,
        lump_sums=lumps,
        aux_changes=changes,
        extra_payments=extras,
        loan_prepayments=prepays,
        floor=_num(o, "floor", path, lo=0, hi=MAX_LUMP * 10) if o.get("floor") is not None else None,
        loan_payments=_loan_payments(o, path, loan_ids),
    )


def _loan_payments(o: dict, path: str, loan_ids: set | None) -> dict:
    out = {}
    for j, x in enumerate(o.get("loan_payments") or []):
        xp = f"{path}.loan_payments[{j}]"
        lid = str(x.get("loan_id", ""))
        if lid not in (loan_ids or set()):
            raise EngineInputError(f"{xp}.loan_id", "없는 대출이에요")
        out[lid] = _num(x, "payment", xp, lo=0, hi=MAX_CASHFLOW * 5)
    return out


def parse_request(d: dict) -> Request:
    if not isinstance(d, dict):
        raise EngineInputError("request", "객체여야 해요")
    horizon = _num(d, "horizon_months", "request", lo=1, hi=MAX_HORIZON, integer=True)
    start = d.get("start") or {}
    goal_raw = d.get("goal") or {}
    gtype = goal_raw.get("type")
    if gtype not in GOAL_TYPES:
        raise EngineInputError("goal.type", "reach_target, runway, debt_free 중 하나여야 해요")
    goal = Goal(
        type=gtype,
        target_amount=_num(goal_raw, "target_amount", "goal", default=0.0, lo=-MAX_LUMP * 10, hi=MAX_LUMP * 10),
        label=str(goal_raw.get("label", "")),
        within_months=(_num(goal_raw, "within_months", "goal", lo=1, hi=horizon, integer=True)
                       if goal_raw.get("within_months") is not None else None),
        target_growth=_num(goal_raw, "target_growth", "goal", default=0.0, lo=0, hi=20),
    )
    aux = []
    for j, a in enumerate(start.get("aux_accounts") or []):
        ap = f"start.aux_accounts[{j}]"
        if a.get("kind") not in AUX_KINDS:
            raise EngineInputError(f"{ap}.kind", "asset 또는 debt여야 해요")
        aux.append(AuxAccount(id=str(a.get("id", f"aux{j}")), kind=a["kind"],
                              value=_num(a, "value", ap, lo=0, hi=10_000_000),
                              growth=_num(a, "growth", ap, default=0.0, lo=-20, hi=20),
                              rate=_num(a, "rate", ap, default=0.0, lo=0, hi=MAX_RETURN),
                              label=str(a.get("label", ""))))
    aux_ids = {a.id for a in aux}
    loans = []
    for j, l in enumerate(start.get("loans") or []):
        lp = f"start.loans[{j}]"
        kind = l.get("kind", "amortizing")
        if kind not in LOAN_KINDS:
            raise EngineInputError(f"{lp}.kind", "amortizing 또는 interest_only여야 해요")
        in_pool = bool(l.get("in_pool", False))
        if in_pool and kind != "interest_only":
            raise EngineInputError(f"{lp}.in_pool", "목표 풀에서 빼 둔 대출은 이자만 내는 대출이어야 해요")
        rate = _num(l, "rate", lp, default=0.0, lo=0, hi=30)
        balance = _num(l, "balance", lp, lo=0, hi=MAX_LOAN)
        payment = _num(l, "payment", lp, default=0.0, lo=0, hi=MAX_CASHFLOW * 5)
        if kind == "amortizing" and balance > 0 and payment <= balance * rate / 100 / 12:
            raise EngineInputError(f"{lp}.payment", "월 상환액이 한 달 이자보다 커야 원금이 줄어요")
        loans.append(Loan(id=str(l.get("id", f"loan{j}")), label=str(l.get("label", "")), balance=balance,
                          rate=rate, kind=kind, payment=payment, in_pool=in_pool))
    loan_ids = {l.id for l in loans}
    if gtype == "debt_free" and not [l for l in loans if not l.in_pool and l.kind != "interest_only"]:
        raise EngineInputError("goal.type", "갚아 나가는 대출이 있어야 debt_free 목표를 쓸 수 있어요")
    raw_options = d.get("options")
    if not isinstance(raw_options, list) or not raw_options:
        raise EngineInputError("options", "방법이 1개 이상 필요해요")
    if len(raw_options) > 5:
        raise EngineInputError("options", "5개 이하여야 해요")
    options = [_parse_option(o, i, horizon, aux_ids, loan_ids) for i, o in enumerate(raw_options)]
    ids = [o.option_id for o in options]
    if len(set(ids)) != len(ids):
        raise EngineInputError("options", "option_id가 겹쳐요")
    ctx = d.get("member_context") or {}
    base_age = ctx.get("base_age")
    rng = d.get("range") or {}
    return Request(
        scenario_id=str(d.get("scenario_id", "")),
        horizon_months=horizon,
        start_pool=_num(start, "goal_pool", "start", lo=-MAX_LUMP * 10, hi=MAX_LUMP * 10),
        pool_label=str(start.get("pool_label", "목표 풀")),
        goal=goal,
        options=options,
        aux_accounts=aux,
        loans=loans,
        inflation=_num(d, "inflation", "request", default=0.0, lo=0, hi=MAX_INFLATION),
        base_age=int(base_age) if isinstance(base_age, (int, float)) else None,
        range_paths=_num(rng, "paths", "range", default=1000, lo=0, hi=5000, integer=True),
        range_seed=_num(rng, "seed", "range", default=1000, lo=0, hi=2**31, integer=True),
        idle_pool=_num(start, "idle_pool", "start", default=0.0, lo=-MAX_LUMP * 10, hi=MAX_LUMP * 10),
        floor=_num(start, "floor", "start", default=0.0, lo=0, hi=MAX_LUMP * 10),
        illiquid=_num(start, "illiquid", "start", default=0.0, lo=0, hi=MAX_LUMP * 10),
        income_growth=_num(d, "income_growth", "request", default=0.0, lo=0, hi=20),
        sweep=bool(d.get("sweep", False)),
        min_until=_num(d, "min_until", "request", default=0, lo=0, hi=horizon, integer=True),
    )
