"""실제 LLM으로 한 가족의 흐름을 처음부터 끝까지 돌려 보고 결과·검증·비용을 기록한다.

사용: python -m llm.eval --family newly|elder|single_parent [--provider anthropic|replay] [--model ID] [--max-usd 1.0]
      [--blank-numbers] [--back-goal]
- --blank-numbers: '우리 가족 이야기'에서 목표 금액·기한 등(정할 수 있는 숫자)을 비워 두고, 공동 목표 2단계에서
  가족 파일의 원래 값으로 정한 것처럼 진행한다(2026-11-08 흐름). 2단계의 우리 가족 기준·세상 기준·size_note를 기록한다.
- --back-goal: 합의안 점검 뒤 한 사람이 이유를 적고 공동 목표로 돌아온 것처럼 수정 제안(역할 4c, discussion)을 한 번 받는다.
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
from . import goal_size
from . import goals as G
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


def evaluate(key: str, provider_name: str = "anthropic", model: str | None = None, max_usd: float = 1.0,
             blank_numbers: bool = False, back_goal: bool = False, tag: str = "") -> dict:
    raw = load_family(key)
    decided = {}
    if blank_numbers and raw.get("goal_input"):
        gi = raw["goal_input"]
        keys = [f["key"] for f in G.fields_for(gi["category"], gi["fields"]) if f.get("decide")]
        decided = {k: gi["fields"].pop(k) for k in keys if k in gi["fields"]}
    fam = F.validate(raw)
    scripts = raw.get("scripts", {})
    base = get_provider(provider_name, model)
    prov = MeteredProvider(base, "eval")
    rep: dict = {"model": base.model, "family": key, "started": time.strftime("%Y-%m-%d %H:%M:%S"), "steps": {},
                 "options_run": {"blank_numbers": blank_numbers, "back_goal": back_goal, "decided_in_step2": decided}}

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
        # 핑퐁 1번(P.MAX_ROUNDS_PER_CYCLE): 마지막 쪽에서도 갈리면 '이야기가 필요한 부분'(역할 4d)을 받아 기록하고, 평가는 그 쪽으로 이어 간다.
        for n in range(P.MAX_ROUNDS_PER_CYCLE + 1):
            reps = script_rounds[n] if n < len(script_rounds) else {m["member_id"]: {"v": "good", "text": ""} for m in fam["members"]}
            rounds.append({"proposal": prop["text"], "reasons": prop["reasons"], "replies": reps})
            if all(r["v"] == "good" for r in reps.values()):
                break
            if n == P.MAX_ROUNDS_PER_CYCLE:
                rep["stuck"] = step("goal_stuck", lambda: P.goal_stuck(fam, summaries, rounds, prov))["result"]
                break
            prop = step(f"revise_goal.{n}", lambda: P.goal_revise(fam, summaries, analysis, rounds, prov, clars))["result"]["proposal"]
        replies = {m: (r.get("text") or "좋아요.") for m, r in rounds[-1]["replies"].items()}
        rep["rounds"] = [{"proposal": r["proposal"], "replies": r["replies"]} for r in rounds]
        cr = step("criterion", lambda: P.goal_criterion(fam, prop["text"], rounds[-1]["replies"], summaries, prov, su, prop["reasons"]))["result"]
        goal_raw = dict(cr["goal"])
        if fam.get("goal_input"):  # 2단계: 우리 가족 기준을 보며 숫자를 정한다(비워 뒀으면 가족 파일의 원래 값으로)
            before = goal_size.size(fam, {})
            after = goal_size.size(fam, decided)
            rep["step2"] = {"missing_before": before["missing"], "size_note": cr.get("size_note"),
                            "anchors": [f"{x['label']}: {x['display']}" for x in after["anchors"]["lines"]],
                            "world": [f"{x['label']}: {x['display']}" for x in ((after.get("world") or {}).get("lines") or [])],
                            "message": after["message"]}
            if after["goal_raw"]:
                goal_raw = dict(after["goal_raw"])
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
        # 합의안(2026-11-08): 각자 괜찮은 방법만 누른다(조건·이유 없음). 모두가 누른 방법이 합의안, 없으면 공동 목표로 돌아간다
        ids = [s["option_id"] for s in specs]
        names = {m["member_id"]: m["name"] for m in fam["members"]}
        if back_goal:  # 첫 사람은 A만, 나머지는 A를 빼고 고른다 → 모두가 고른 방법이 없음 → 공동 목표로 돌아온다
            picks = {m["member_id"]: (ids[:1] if i == 0 else ids[1:]) for i, m in enumerate(fam["members"])}
            summary = ", ".join(f"{oid}는 " + ("·".join(names[m] + "님" for m, p in picks.items() if oid in p) or "아무도") + " 괜찮다고 했어요" for oid in ids)
            disc = f"합의안 단계에서 가족 모두가 고른 방법이 없어 공동 목표로 돌아왔어요. {summary}"
            bk = step("back_goal", lambda: P.goal_revise(fam, summaries, analysis, rounds, prov, clars, disc))["result"]["proposal"]
            rep["back_goal"] = {"picks": picks, "discussion": disc, "proposal": bk["text"], "changed": bk.get("changed"), "reasons": bk["reasons"]}
        first = fam["members"][0]["member_id"]
        picks = {m["member_id"]: ([i for i in ids if i != ids[0]] if m["member_id"] == first else ids) for m in fam["members"]}
        rep["picks"] = picks
        common = [i for i in ids if all(i in p for p in picks.values())]
        spec = specs[ids.index(common[0])]
        res = P.simulate_specs(fam, goal, [spec])["results"][0]
        a = step("draft", lambda: P.agreement_draft(fam, goal, cr["criterion"], spec, res, f"{spec['option_id']}. {spec['label']}", [],
                                                    summaries, prov, None))["result"]
        step("recommend", lambda: P.recommend(fam, a, prov))
        rep["status"] = "done"
    except (Budget, PlanError) as e:
        rep["status"] = str(e)
    rep["cost_usd"] = round(prov.cost_usd, 4)
    out_dir = ROOT / "data/eval"
    out_dir.mkdir(parents=True, exist_ok=True)
    fn = out_dir / f"{base.model.replace('/', '_')}__{key}{'_' + tag if tag else ''}.json"
    fn.write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"→ {fn.relative_to(ROOT)}  {rep['status']}  ${rep['cost_usd']}", file=sys.stderr)
    return rep


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--family", default="newly")
    ap.add_argument("--provider", default="anthropic")
    ap.add_argument("--model", default=None)
    ap.add_argument("--max-usd", type=float, default=1.0)
    ap.add_argument("--blank-numbers", action="store_true")
    ap.add_argument("--back-goal", action="store_true")
    ap.add_argument("--tag", default="", help="결과 파일 이름 꼬리(예: blank)")
    a = ap.parse_args()
    evaluate(a.family, a.provider, a.model, a.max_usd, a.blank_numbers, a.back_goal, a.tag)
