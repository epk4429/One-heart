"""미래 계산 현실성 검사기(할 일 1-9 D2·D3, 2026-11-15).

data/scenarios/scenarios.json의 시나리오마다 방법 A·B·C를 설계해(기본: 재생 공급자, 비용 0) 계산하고,
'사람 눈에 말이 되는지'를 규칙으로 판정해 표로 낸다. 실제 AI 답은 저장해 두고 엔진만 바뀌면 AI 없이 다시 계산한다.

사용:
  python tools/realism_check.py                         # 재생 공급자(비용 0)
  python tools/realism_check.py --only debt_mortgage_credit
  python tools/realism_check.py --resim anthropic       # 저장해 둔 실제 AI 답을 지금 엔진으로 다시 계산(비용 0)
  python tools/realism_check.py --provider anthropic --yes-cost --max-usd 1.0
                                                        # 실제 AI(비용 발생! 형님께 먼저 알린 뒤에만, CLAUDE.md 7절 8번)
결과: data/scenarios/runs/<공급자>/<id>.json(설계 결과), data/scenarios/report_<공급자>.md(표)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from llm import family as F  # noqa: E402
from llm import goals as G  # noqa: E402
from llm.plan import PlanError, build_request, check_option, floor_errors, is_unchanged, mark_baseline, normalize_goal  # noqa: E402

SC_FILE = ROOT / "data/scenarios/scenarios.json"
RUNS = ROOT / "data/scenarios/runs"


def load(only: str | None = None) -> list[dict]:
    sc = json.loads(SC_FILE.read_text(encoding="utf-8"))["scenarios"]
    return [s for s in sc if not only or s["id"] == only]


def goal_raw(fam: dict) -> dict:
    return G.derive_goal(fam["goal_input"], fam["members"])


# ---------- 판정 규칙 ----------
def check(fam: dict, goal: dict, specs: list[dict], sim: dict, deadline_note: str = "") -> list[dict]:
    """방법마다(또는 시나리오 전체) 사람 눈에 말이 안 되는 점을 찾는다. [{option, rule, ok, detail}]"""
    out = []

    def add(opt, rule, ok, detail=""):
        out.append({"option": opt, "rule": rule, "ok": bool(ok), "detail": detail})

    results = {r["option_id"]: r for r in sim["results"]}
    req = build_request(fam, goal, specs)
    life = goal.get("life") or {}
    start_cash = goal["start_pool"] - goal.get("idle_pool", 0) - goal.get("illiquid", 0)
    # 1. 비상금 선(노후·간병 제외)
    for e in floor_errors(goal, specs, sim["results"]):
        add(e.split(":")[0].replace("방법 ", ""), "비상금 지킴", False, e)
    if goal["type"] != "runway":
        bad = {e.split(":")[0].replace("방법 ", "") for e in floor_errors(goal, specs, sim["results"])}
        for s in specs:
            if s["option_id"] not in bad:
                add(s["option_id"], "비상금 지킴", True, f"가장 적을 때 {results[s['option_id']]['min_cash']:,.0f}만원 / 선 {min(goal['floor'], max(start_cash, 0)):,.0f}")
    # 1-2. 적자 상태(2026-11-15 형님 결정 A): 거부 대신 '비상금 아래로 내려가는 때'를 보여 주고, 적어도 한 방법은 지금처럼보다 오래 버텨야 한다
    if goal.get("deficit"):
        br = {s["option_id"]: results[s["option_id"]].get("floor_breach_month") for s in specs}
        base = [s["option_id"] for s in specs if is_unchanged(s)]
        far = lambda m: m or 10**9
        best = max(far(v) for v in br.values())
        ok = not base or best > far(br[base[0]])
        add("-", "적자: 지금처럼보다 오래 버티는 방법", ok, " / ".join(f"{k} {v}개월째" if v else f"{k} 끝까지" for k, v in br.items()))
    # 2. 대출 남았는데 예금 쌓아 두기(대출 목표, 적자 상태는 버틸 돈이 먼저라 제외)
    if goal["type"] == "debt_free" and not goal.get("deficit"):
        for s in specs:
            r = results[s["option_id"]]
            fl = r.get("floor") or goal["floor"]
            margin = max(300.0, 3 * abs(r["monthly_flow"]))
            idle = [y for y in r["yearly"] if y["debt_end"] > 1 and y["end"] - goal.get("idle_pool", 0) - goal.get("illiquid", 0) > fl + margin]
            add(s["option_id"], "대출 두고 예금 쌓기 없음", not idle,
                f"{idle[0]['year']}년째 예금 {idle[0]['end']:,.0f}만원·남은 대출 {idle[0]['debt_end']:,.0f}만원" if idle else "")
    # 3. 가족이 입력한 앞으로의 일이 계산에 들어갔나(AI가 빠뜨려도 코드가 넣는지)
    for o in req["options"]:
        cfs = o["cashflows"]
        if life.get("kind") == "retire":
            late_wage = [c for c in cfs if c.get("grows") and (not c.get("to_month") or c["to_month"] >= life["month"])]
            add(o["option_id"], "은퇴 뒤 월급 없음", not late_wage, f"은퇴 {life['month']}달째부터")
            if life.get("monthly_need") and life["month"] > 1:
                add(o["option_id"], "은퇴 후 생활비 반영", any(c["label"] == "은퇴 후 생활비" for c in cfs))
            add(o["option_id"], "연금 처리", any(c["label"] == "은퇴 후 연금" for c in cfs) == bool(life.get("pension")),
                "연금 입력 있음" if life.get("pension") else "연금 없이 계산")
        if life.get("kind") == "care":
            add(o["option_id"], "간병비 반영", any(c["label"] == "부모님 간병비" and c.get("from_month") == life["month"]
                                                 and (c.get("to_month") or 0) == (life.get("to") or 0) for c in cfs),
                f"{life['month']}달째부터 월 {life['monthly_cost']}" + (f", {life['to']}달째까지" if life.get("to") else ", 끝까지"))
        if life.get("kind") == "baby":
            mid = life["member_id"]
            wages = [c for c in cfs if c.get("grows") and any(it["item_id"] == c.get("item_id") and it["owner_id"] == mid for it in fam["finance"])]
            during = [c for c in wages if c.get("from_month", 1) <= life["from"] and (not c.get("to_month") or c["to_month"] >= life["from"])]
            add(o["option_id"], "휴직 중 월급 빠짐", not during, f"{life['from']}~{life['to']}달째")
    if goal["type"] == "runway":
        need = min(960, (100 - goal["base_age"]) * 12)
        add("-", "100세까지 계산", goal["horizon_months"] >= need, f"{goal['base_age'] + goal['horizon_months'] // 12}세까지")
    # 4. 기한
    w = goal.get("within_months")
    if w and goal["type"] in ("reach_target", "debt_free"):
        met = [s["option_id"] for s in specs if (results[s["option_id"]]["goal_hit_month"] or 10**9) <= w]
        add("-", "기한을 맞추는 방법 또는 설명", bool(met) or bool(deadline_note.strip()),
            f"맞추는 방법 {','.join(met)}" if met else (f"설명: {deadline_note[:60]}" if deadline_note else "맞추는 방법도 설명도 없음"))
    # 5. A·B는 무언가를 바꾸는 방법이어야 한다. C는 '지금처럼(비교용)'이면 인정(2026-11-15 형님 결정)
    for s in specs:
        if s["option_id"] == "C" and is_unchanged(s):
            add("C", "C는 비교용 이름", s["label"] == "지금처럼(비교용)", s["label"])
            continue
        add(s["option_id"], "바꾸는 방법", not is_unchanged(s) or s["return_id"] != "safe",
            "" if not is_unchanged(s) else f"바꾼 것: 돈 불리는 방식({s['return_id']})만" if s["return_id"] != "safe" else "바꾼 것 없음")
    # 5-2. 변별력: 세 방법 결과가 사실상 같으면 가족이 고를 이유가 없다(2026-11-15 시나리오 재검토)
    rs = [results[s["option_id"]] for s in specs]
    hits = {r["goal_hit_month"] for r in rs}
    ends = [r["end_pool"] for r in rs]
    same = len(hits) == 1 and (max(ends) - min(ends)) <= max(abs(max(ends)), 1) * 0.03
    add("-", "세 방법 결과가 갈림", not same, " / ".join(r["goal_hit_display"] for r in rs) if same else "")
    # 6. 목표 전에 모이는 돈이 마이너스인 해(노후·간병 제외)
    if goal["type"] != "runway":
        for s in specs:
            r = results[s["option_id"]]
            hit_y = ((r["goal_hit_month"] or 10**9) - 1) // 12 + 1
            leave = range(life["from"], life["to"] + 1) if life.get("kind") == "baby" else range(0)  # 계획된 휴직 기간의 마이너스는 정상
            neg = [y for y in r["yearly"] if y["year"] < hit_y and y["year"] > 1 and y["net_flow"] < 0 and goal["type"] == "reach_target"
                   and not any((y["year"] - 1) * 12 < m <= y["year"] * 12 for m in leave)]
            add(s["option_id"], "목표 전 마이너스인 해 없음", not neg, f"{neg[0]['year']}년째 {neg[0]['net_flow']:,.0f}만원" if neg else "")
    return out


# ---------- 실행 ----------
def design(fam: dict, sc: dict, provider_name: str) -> dict:
    from llm import pipeline as P
    from llm.providers import get_provider, load_env
    load_env()
    prov = get_provider(provider_name)
    return P.options_design(fam, goal_raw(fam), sc["criterion"], sc["summaries"], prov)


def resim(fam: dict, saved: dict) -> tuple[dict, list[dict], dict]:
    from llm import pipeline as P
    goal = normalize_goal(fam, goal_raw(fam))
    specs = mark_baseline([check_option(fam, goal, {k: v for k, v in s.items()}) for s in saved["raw_options"]])
    return goal, specs, P.simulate_specs(fam, goal, specs)


def row_md(sc: dict, goal: dict, specs: list[dict], sim: dict, found: list[dict], note: str) -> str:
    res = {r["option_id"]: r for r in sim["results"]}
    opts = " / ".join(f"{s['option_id']} {s['label']}: {res[s['option_id']]['goal_hit_display']}" for s in specs)
    bad = [f for f in found if not f["ok"]]
    flags = "<br>".join(f"❌ {f['option']} {f['rule']}" + (f" ({f['detail']})" if f["detail"] else "") for f in bad) or "✅ 문제 없음"
    return f"| {sc['id']} | {sc['title']} | {opts} | {flags} |"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", default="replay")
    ap.add_argument("--only")
    ap.add_argument("--resim", help="저장해 둔 이 공급자의 설계를 지금 엔진으로 다시 계산(AI 호출 없음)")
    ap.add_argument("--yes-cost", action="store_true", help="실제 AI 비용이 드는 것을 알고 돌린다")
    ap.add_argument("--max-usd", type=float, default=1.0)
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    name = a.resim or a.provider
    if not a.resim and a.provider not in ("replay",) and not a.yes_cost:
        sys.exit("실제 AI는 비용이 들어요. 형님께 먼저 알린 뒤 --yes-cost를 붙여 돌려 주세요.")
    (RUNS / name).mkdir(parents=True, exist_ok=True)
    lines = [f"# 현실성 검사 ({name}{' · 다시 계산' if a.resim else ''})", "",
             "| 시나리오 | 내용 | 방법별 결과 | 판정 |", "|---|---|---|---|"]
    spent = 0.0
    for sc in load(a.only):
        fam = F.validate(sc["family"])
        path = RUNS / name / f"{sc['id']}.json"
        try:
            if a.resim:
                saved = json.loads(path.read_text(encoding="utf-8"))
                goal, specs, sim = resim(fam, saved)
                note = saved.get("deadline_note", "")
            else:
                out = design(fam, sc, a.provider)
                run = out.get("design_run", {})
                for rr in (run, out.get("interpret_run") or {}):  # 역할 5 + 6a 실제 토큰 비용
                    spent += float(((rr or {}).get("usage") or {}).get("cost_usd") or 0)
                if "specs" not in out:
                    lines.append(f"| {sc['id']} | {sc['title']} | 설계 실패 | ❌ {str(run.get('error') or out.get('error'))[:200]} |")
                    print(sc["id"], "설계 실패", str(run.get("error") or out.get("error"))[:300])
                    continue
                goal, specs, sim, note = out["goal"], out["specs"], out["simulation"], out.get("deadline_note", "")
                path.write_text(json.dumps({"scenario": sc["id"], "raw_options": (run.get("output") or {}).get("options") or specs,
                                            "deadline_note": note, "design_notes": out.get("design_notes"),
                                            "assumptions": out.get("assumptions"), "interpretation": out.get("interpretation")},
                                           ensure_ascii=False, indent=1), encoding="utf-8")
        except (PlanError, FileNotFoundError) as e:
            lines.append(f"| {sc['id']} | {sc['title']} | - | ❌ {e} |")
            print(sc["id"], "오류", e)
            continue
        found = check(fam, goal, specs, sim, note)
        lines.append(row_md(sc, goal, specs, sim, found, note))
        bad = [f for f in found if not f["ok"]]
        print(f"{'✅' if not bad else '❌'} {sc['id']}: " + " / ".join(f"{r['option_id']} {r['goal_hit_display']}" for r in sim["results"])
              + ("" if not bad else "  →  " + "; ".join(f"{f['option']} {f['rule']} {f['detail']}" for f in bad)))
        if spent > a.max_usd:
            print(f"비용 상한 {a.max_usd}달러를 넘어 멈춰요(지금까지 {spent:.3f}달러)")
            break
    report = ROOT / f"data/scenarios/report_{name}.md"
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("표:", report.relative_to(ROOT), f"(이번 실행 AI 비용 약 {spent:.3f}달러)" if spent else "")


if __name__ == "__main__":
    main()
