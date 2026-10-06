"""LLM 출력에서 JSON 객체를 꺼낸다. 코드 펜스, 생각 태그, 앞뒤 설명문을 견딘다."""

from __future__ import annotations

import json
import re

THINK = re.compile(r"<think>.*?</think>", re.S)
FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.S)


def extract_json(text: str) -> dict:
    t = THINK.sub("", text or "").strip()
    m = FENCE.search(t)
    if m:
        t = m.group(1).strip()
    try:
        v = json.loads(t)
        if isinstance(v, dict):
            return v
    except json.JSONDecodeError:
        pass
    # 첫 '{'부터 짝이 맞는 '}'까지
    start = t.find("{")
    while start != -1:
        depth, in_str, esc = 0, False, False
        for i in range(start, len(t)):
            ch = t[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        v = json.loads(t[start:i + 1])
                        if isinstance(v, dict):
                            return v
                    except json.JSONDecodeError:
                        break
        start = t.find("{", start + 1)
    raise ValueError("JSON 객체를 찾지 못했어요")
