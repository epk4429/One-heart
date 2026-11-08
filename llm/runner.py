"""역할 실행기: 호출 → JSON 추출 → 출력 검사 → 틀리면 오류를 붙여 1회 재요청(docs/05 1절)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Callable

from .jsonutil import extract_json
from .providers import LLMError
from .roles import ROLES

REASONING_HEADROOM = 3000  # 추론형 모델은 생각 토큰도 max_tokens에 포함된다


@dataclass
class RoleRun:
    role: str
    output: dict | None
    ok: bool
    attempts: int
    errors: list[str] = field(default_factory=list)
    usage: dict = field(default_factory=lambda: {"input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0})
    latency_s: float = 0.0
    tool_calls: int = 0
    model: str = ""


def _add_usage(acc: dict, u: dict) -> None:
    acc["input_tokens"] += u.get("prompt_tokens", u.get("input_tokens", 0)) or 0
    acc["output_tokens"] += u.get("completion_tokens", u.get("output_tokens", 0)) or 0
    acc["cost_usd"] = round(acc.get("cost_usd", 0) + (u.get("cost_usd", 0) or 0), 6)


def run_role(key: str, inputs: dict, provider, *, tools: list[dict] | None = None,
             tool_handler: Callable[[str, dict], dict] | None = None, max_tool_rounds: int = 2,
             retries: int = 1) -> RoleRun:
    role = ROLES[key]
    messages: list[dict] = [{"role": "user", "content": role.build(inputs)}]
    run = RoleRun(role=key, output=None, ok=False, attempts=0)
    tool_rounds = 0
    while run.attempts <= retries:
        run.attempts += 1
        try:
            # 도구 목록은 대화 내내 같게 둔다(중간에 빼면 Claude의 이전 생각 블록이 무효가 된다).
            res = provider.complete(role.system, messages, tools=tools,
                                    max_tokens=role.max_tokens + REASONING_HEADROOM, role_key=key,
                                    effort=role.effort, inputs=inputs)
        except LLMError as e:
            run.errors.append(f"호출 실패: {e}")
            return run
        run.model = res.model
        run.latency_s += res.latency_s
        _add_usage(run.usage, res.usage)
        if res.tool_calls and tool_handler:
            tool_rounds += 1
            run.tool_calls += len(res.tool_calls)
            messages.append(res.raw_message)
            for tc in res.tool_calls:
                if tool_rounds > max_tool_rounds:
                    out = {"error": f"도구 호출은 {max_tool_rounds}번까지예요. 지금까지의 결과로 최종 JSON만 출력해 주세요."}
                else:
                    out = tool_handler(tc.name, tc.arguments)
                    if tool_rounds == max_tool_rounds and isinstance(out, dict):
                        out = {**out, "note": "도구는 이번이 마지막이에요. 다음 응답에서는 최종 JSON만 출력해 주세요."}
                messages.append(provider.tool_result_message(tc, json.dumps(out, ensure_ascii=False)))
            run.attempts -= 1  # 도구 호출 왕복은 재시도로 세지 않는다
            continue
        try:
            obj = extract_json(res.text)
        except ValueError:
            errs = ["JSON 객체 하나만 출력해야 해요"]
            obj = None
        else:
            errs = role.check(obj, inputs)
        if not errs:
            run.output, run.ok = obj, True
            return run
        run.errors.extend(errs)
        run.output = obj
        # 응답은 고치지 않고 그대로 붙인다(생각 블록 포함, 덧붙이기만 하는 대화 기록).
        messages.append(res.raw_message if res.raw_message.get("content") else
                        {"role": "assistant", "content": res.text or "(빈 응답)"})
        messages.append({"role": "user", "content": "출력에 문제가 있어요. 고쳐서 JSON만 다시 출력해 주세요:\n- "
                                                   + "\n- ".join(errs)})
    return run
