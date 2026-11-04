"""실제 LLM으로 한 가족의 흐름을 처음부터 끝까지 돌려 보고 결과·검증·비용을 기록한다.

사용: python -m llm.eval --family newly|elder|single_parent [--provider anthropic|replay] [--model ID] [--max-usd 1.0]
      → data/eval/<모델>__<가족>.json

- 사람 입력(대화 답·제안에 대한 답)은 가족 파일의 scripts를 쓴다. 의사 표시는 규칙으로 정한다(첫 사람이 모두 반대 → 수정안 확인).
- 비용이 --max-usd를 넘으면 그 자리에서 멈춘다. 한 번에 하나씩 돌린다(동시에 돌리지 않는다).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from server.guard import MeteredProvider

from . import family as F
from . import pipeline as P
from .plan import PlanError, normalize_goal
from .providers import get_provider

ROOT = Path(__file__).resolve().parents[1]


class Budget(Exception):
    pass


def load_family(key: str) -> dict:
    if key in ("newly", "elder"):
        return F.preset(key)
    return json.loads((ROOT / f"data/eval/families/{key}.json").read_text(encoding="utf-8"))


def evaluate(key: str, provider_name: str = "anthropic", model: str | None = None, max_usd: float = 1.0) -> dict:
    raw = load_family(key)
    fam = F.validate(raw)
    scripts = raw.get("scripts", {})
    base = get_provider(provider_name, model)
    prov = MeteredProvider(base, "eval")
    rep: dict = {"model": base.model, "family": key, "started": time.strftime("%Y-%m-%d %H:%M:%S"), "steps": {}}

    def step(name, fn):
        t0 = time.time()
        out = fn()
        runs = {k: {x: v.get(x) for x in ("ok", "attempts", "errors", "latency_s", "usage", "tool_calls", "model")}
                for k, v in out.items() if k.endswith("run") and isinstance(v, dict)}
        rep["steps"][name] = {"seconds": round(time.time() - t0, 1), "runs": runs,
                              "verification": out.get("verification"), "result": out.get("result"),
                              "error": out.get("error")}
        print(f"{name:10s} ok={all(r['ok'] for r in runs.values())} cost=${prov.cost_usd:.3f}", file=sys.stderr)
        if not all(r["ok"] for r in runs.values()) or out.get("error"):
            raise Budget(f"{name} 실패")
        if prov.cost_usd > max_usd:
            raise Budget(f"비용 상한 {max_usd}달러를 넘어 멈춤")
        return out

    try:
        su = step("story", lambda: P.story_understand(fam, prov))["result"]
        summaries, clars = {}, []
        for m in fam["members"]:
            mid = m["member_id"]
            qa = [[q["text"], a] for q, a in zip(F.QUESTIONS, scripts["answers"][mid])]
            r = step(f"review.{mid}", lambda: P.interview_review(fam, mid, qa, prov))["result"]
            if r["ambiguous"]:
                cl = scripts.get("clarify") or {}
                ans = cl.get("answer") if cl.get("member_id") == mid else r["choices"][0]
                res = step(f"resolve.{mid}", lambda: P.interview_resolve(fam, mid, r, ans, prov))["result"]
                if res["resolved"]:
                    c = {"word": r["ambiguous"][0]["word"], "meaning": res["meaning"]}
                    clars.append({"member_id": mid, **c})
                    r = step(f"review2.{mid}", lambda: P.interview_review(fam, mid, qa, prov, c))["result"]
            summaries[mid] = {k: r[k] for k in ("keep", "flexible", "worry")}
        g = step("goal", lambda: P.goal_analyze(fam, summaries, su, prov, clars))["result"]
        # 제안 핑퐁: scripts.rounds(쪽마다 구성원별 {v, text})대로 의견을 내고, 조건·다른 의견이 있으면 수정 제안(역할 4c)을 받는다. 없으면 모두 '좋아요'.
        prop, rounds, script_rounds = g["proposal"], [], scripts.get("rounds") or []
        analysis = {"headline": g["headline"], "agreed_points": g["agreed_points"], "issues": g["issues"]}
        for n in range(4):
            reps = script_rounds[n] if n < len(script_rounds) else {m["member_id"]: {"v": "good", "text": ""} for m in fam["members"]}
            rounds.append({"proposal": prop["text"], "reasons": prop["reasons"], "replies": reps})
            if all(r["v"] == "good" for r in reps.values()) or n == 3:
                break
            prop = step(f"revise_goal.{n}", lambda: P.goal_revise(fam, summaries, analysis, rounds, prov, clars))["result"]["proposal"]
        replies = {m: (r.get("text") or "좋아요.") for m, r in rounds[-1]["replies"].items()}
        rep["rounds"] = [{"proposal": r["proposal"], "replies": r["replies"]} for r in rounds]
        cr = step("criterion", lambda: P.goal_criterion(fam, prop["text"], rounds[-1]["replies"], summaries, prov, su, prop["reasons"]))["result"]
        goal_raw = dict(cr["goal"])
        ex = scripts.get("goal_form") or {}
        if goal_raw["type"] == ex.get("type", goal_raw["type"]):
            for k in ("target_amount", "within_months"):
                if not goal_raw.get(k) and ex.get(k):
                    goal_raw[k] = ex[k]  # 화면에서 가족이 '예시 값 넣기'로 채우는 것과 같다
                    rep.setdefault("note", []).append(f"AI가 비워 둔 {k}를 가족 예시 값({ex[k]})으로 채움")
        if goal_raw["type"] == "reach_target" and not goal_raw.get("target_amount"):
            rep["status"] = "목표 금액이 비어 있어 멈춤(화면에서는 가족이 넣어야 함)"
            raise Budget(rep["status"])
        goal = normalize_goal(fam, goal_raw)
        rep["goal"] = goal
        d = step("design", lambda: P.options_design(fam, goal_raw, cr["criterion"], summaries, prov))
        specs = d["specs"]
        rep["options"] = [{"option_id": r["option_id"], "hit": r["goal_hit_display"], "flow": r["monthly_flow"]}
                          for r in d["simulation"]["results"]]
        changes = {v["option_id"]: v["changes"] for v in d.get("views", [])}
        rep["steps"]["design"]["result"] = {  # 미래 계산 화면에 나오는 내용 전부(방법·바꾼 것·결과·해석)
            "options": [{"option_id": sp["option_id"], "label": sp["label"], "description": sp["description"],
                         "changes": changes.get(sp["option_id"]), "hit": r["goal_hit_display"], "monthly_flow": r["monthly_flow"],
                         "range": r.get("range"), "basis": [(b["label"], b["display"], b.get("detail", "")) for b in r["basis"]]}
                        for sp, r in zip(specs, d["simulation"]["results"])],
            "design_notes": d.get("design_notes"), "interpretation": d.get("interpretation")}
        rep["inputs"] = {"family": raw, "summaries": summaries, "replies": replies}
        sim = P.simulate_specs(fam, goal, specs, include_monthly=False)
        step("check", lambda: P.agreement_check(fam, goal, specs, sim, summaries, prov))
        first = fam["members"][0]["member_id"]
        stances = {m["member_id"]: {s["option_id"]: ({"v": "no", "text": "지키고 싶은 것이 깨져서 어려워요"} if m["member_id"] == first
                                                     else {"v": "good", "text": ""}) for s in specs} for m in fam["members"]}
        rep["stances"] = stances
        rv = step("revise", lambda: P.agreement_revise(fam, goal, specs, sim, stances, summaries, prov))["result"]
        res = P.simulate_specs(fam, goal, [rv["spec"]])["results"][0]
        conds = [{"member_id": first, "text": "6개월마다 꼭 같이 다시 봐요."}]
        a = step("draft", lambda: P.agreement_draft(fam, goal, cr["criterion"], rv["spec"], res, rv["label"], conds,
                                                    summaries, prov, rv))["result"]
        step("recommend", lambda: P.recommend(fam, a, prov))
        rep["status"] = "done"
    except (Budget, PlanError) as e:
        rep["status"] = str(e)
    rep["cost_usd"] = round(prov.cost_usd, 4)
    out_dir = ROOT / "data/eval"
    out_dir.mkdir(parents=True, exist_ok=True)
    fn = out_dir / f"{base.model.replace('/', '_')}__{key}.json"
    fn.write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"→ {fn.relative_to(ROOT)}  {rep['status']}  ${rep['cost_usd']}", file=sys.stderr)
    return rep


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--family", default="newly")
    ap.add_argument("--provider", default="anthropic")
    ap.add_argument("--model", default=None)
    ap.add_argument("--max-usd", type=float, default=1.0)
    a = ap.parse_args()
    evaluate(a.family, a.provider, a.model, a.max_usd)
