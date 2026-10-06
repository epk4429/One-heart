"""AI 호출 장부(data/usage/calls.jsonl) 요약. 처음부터 끝까지 한 번 이용하는 데 토큰·비용이 얼마나 드는지 본다.

사용: python -m server.usage_report            (전체 + 이용 묶음별)
      python -m server.usage_report --gap 20   (호출 사이가 20분 넘게 비면 다른 이용으로 나눔, 기본 30)

토큰 수는 Anthropic 응답에 실린 실제 값이다. 비용은 공개 단가로 계산한 값이라(캐시 쓰기 1.25배·읽기 0.1배),
청구서와 몇 % 다를 수 있다. 정확한 청구액은 Anthropic 콘솔의 Usage/Cost 화면과 맞춰 본다.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import datetime

from server.guard import CALLS_FILE

ROLE_NAMES = {"1a": "이야기 정리", "1b": "대화 요약", "2b": "말뜻 해석", "3": "쟁점 분석", "4a": "공동 목표 제안",
              "4b": "기준·목표", "5": "방법 설계(도구 포함)", "5r": "수정안", "6a": "결과 해석", "6b": "점검표",
              "7": "합의안", "8": "상품 매핑"}
KEYS = ("uncached_input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens", "output_tokens", "cost_usd")


def load() -> list[dict]:
    if not CALLS_FILE.exists():
        return []
    return [json.loads(l) for l in CALLS_FILE.read_text(encoding="utf-8").splitlines() if l.strip()]


def summarize(calls: list[dict]) -> dict:
    tot = defaultdict(float)
    by_role: dict = defaultdict(lambda: defaultdict(float))
    for c in calls:
        for k in KEYS:
            tot[k] += c.get(k, 0)
            by_role[c.get("role")][k] += c.get(k, 0)
        by_role[c.get("role")]["calls"] += 1
    tot["calls"] = len(calls)
    return {"total": dict(tot), "by_role": {k: dict(v) for k, v in by_role.items()}}


def sessions(calls: list[dict], gap_min: int) -> list[list[dict]]:
    out: list[list[dict]] = []
    last = None
    for c in sorted(calls, key=lambda x: x["ts"]):
        t = datetime.strptime(c["ts"], "%Y-%m-%d %H:%M:%S")
        if last is None or (t - last).total_seconds() > gap_min * 60 or c.get("code") != out[-1][-1].get("code"):
            out.append([])
        out[-1].append(c)
        last = t
    return out


def _line(t: dict) -> str:
    inp = t["uncached_input_tokens"] + t["cache_read_input_tokens"] + t["cache_creation_input_tokens"]
    return (f"호출 {int(t['calls']):3d}  입력 {inp:8,.0f}(캐시 읽기 {t['cache_read_input_tokens']:,.0f})  "
            f"출력 {t['output_tokens']:7,.0f}  ${t['cost_usd']:.3f}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gap", type=int, default=30)
    a = ap.parse_args()
    calls = load()
    if not calls:
        print(f"기록이 없어요({CALLS_FILE}). 실제 AI로 이용하면 쌓여요.")
        return
    s = summarize(calls)
    print("== 전체\n  " + _line(s["total"]))
    print("== 역할별")
    for r, t in sorted(s["by_role"].items(), key=lambda x: -x[1]["cost_usd"]):
        print(f"  {ROLE_NAMES.get(r, r):14s} " + _line(t))
    print(f"== 이용 묶음별(호출 사이 {a.gap}분 넘게 비면 나눔)")
    for grp in sessions(calls, a.gap):
        t = summarize(grp)["total"]
        roles = {c.get("role") for c in grp}
        done = "합의안까지" if "7" in roles else "중간까지"
        print(f"  {grp[0]['ts']} ~ {grp[-1]['ts'][11:]} [{grp[0].get('code')}] {done}  " + _line(t))


if __name__ == "__main__":
    main()
