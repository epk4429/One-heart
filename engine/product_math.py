"""상품 비교용 계산(docs/06 2.2절, ontology/fit.py가 쓴다). 금액 단위는 만원, 금리는 연 %.

가족 시뮬레이션(core.schedule)과 같은 약속을 쓴다: 한 달 이자 = 잔액 × 연 금리 / 12.
- 적금: 매달 같은 금액을 넣는다(정액). 단리는 넣은 달마다 남은 개월 수만큼 이자, 복리는 월복리.
- 정기예금: 한 번에 맡긴다. 단리 = 원금 × 금리 × 개월/12, 복리 = 월복리.
- 대출: 원리금균등(매달 같은 금액), 원금균등(원금을 같게 나누고 이자는 잔액만큼), 만기일시(이자만 내다 만기에 원금).
"""

from __future__ import annotations

METHODS = {"equal_payment": "원리금균등(매달 같은 금액)", "equal_principal": "원금균등(원금을 똑같이 나눠 갚기)",
           "bullet": "만기일시(이자만 내다 만기에 한 번에)"}


def saving_interest(monthly: float, months: int, rate: float, compound: bool = False) -> float:
    r = rate / 100
    if compound:
        return sum(monthly * ((1 + r / 12) ** k - 1) for k in range(1, months + 1))
    return monthly * r * months * (months + 1) / 2 / 12


def deposit_interest(amount: float, months: int, rate: float, compound: bool = False) -> float:
    r = rate / 100
    return amount * ((1 + r / 12) ** months - 1) if compound else amount * r * months / 12


def after_tax(interest: float, tax_rate: float) -> float:
    return interest * (1 - tax_rate / 100)


def loan_cost(amount: float, rate: float, months: int, method: str, prepay_month: int | None = None) -> dict:
    """대출 하나의 상환 계산. prepay_month가 있으면 그 달에 남은 원금을 모두 갚는다고 보고 그때까지의 이자와 남은 원금을 낸다."""
    if method not in METHODS:
        raise ValueError(method)
    r = rate / 100 / 12
    bal, total_interest, pays = amount, 0.0, []
    pmt = amount * r / (1 - (1 + r) ** -months) if method == "equal_payment" and r > 0 else amount / months
    last = min(prepay_month, months) if prepay_month else months
    for m in range(1, last + 1):
        interest = bal * r
        if method == "equal_payment":
            principal = pmt - interest if r > 0 else pmt
        elif method == "equal_principal":
            principal = amount / months
        else:
            principal = amount if m == months else 0.0
        principal = min(principal, bal)
        bal -= principal
        total_interest += interest
        pays.append(interest + principal)
    return {"method": method, "months": months, "first_payment": round(pays[0], 2), "last_payment": round(pays[-1], 2),
            "total_interest": round(total_interest, 2), "paid_months": last,
            "remaining_at_prepay": round(bal, 2) if prepay_month and prepay_month < months else 0.0}
