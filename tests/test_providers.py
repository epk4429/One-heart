"""Anthropic 공급자 요청 형식과 실행기의 대화 기록 규칙(네트워크 없이 가짜 클라이언트로)."""

import json
from types import SimpleNamespace

import pytest

pytest.importorskip("anthropic")

from llm.providers import AnthropicProvider  # noqa: E402
from llm.runner import run_role  # noqa: E402


class FakeResp:
    def __init__(self, content, stop_reason="end_turn"):
        self._content = content
        self.stop_reason = stop_reason
        self.stop_details = None
        self.model = "claude-opus-5-5"
        self.usage = SimpleNamespace(input_tokens=10, output_tokens=5, cache_read_input_tokens=0,
                                     cache_creation_input_tokens=0)

    def to_dict(self):
        return {"content": self._content}


class FakeMessages:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def create(self, **kw):
        self.calls.append(json.loads(json.dumps(kw, ensure_ascii=False)))
        return self.replies.pop(0)


def make(replies):
    p = AnthropicProvider("claude-opus-5-5", api_key="test-key")
    fake = FakeMessages(replies)
    p.client = SimpleNamespace(beta=SimpleNamespace(messages=fake))
    return p, fake


THINK = {"type": "thinking", "thinking": "", "signature": "sig"}


def test_request_shape_for_opus_5_5():
    p, fake = make([FakeResp([THINK, {"type": "text", "text": '{"a": 1}'}])])
    r = p.complete("sys", [{"role": "user", "content": "hi"}], max_tokens=1000)
    kw = fake.calls[0]
    assert "temperature" not in kw and "thinking" not in kw  # Opus 5.5: 샘플링 값·생각 끄기 금지
    assert kw["output_config"] == {"effort": "medium"}
    assert kw["max_tokens"] >= 16000  # 생각 토큰 여유
    assert kw["fallbacks"] == "default" and kw["betas"] == ["server-side-fallback-2026-07-01"]
    assert r.text == '{"a": 1}' and r.raw_message["content"][0]["type"] == "thinking"


def test_runner_keeps_history_append_only():
    """도구 왕복과 재요청에서 이전 응답(생각 블록 포함)을 그대로 두고, 도구 목록도 바꾸지 않는다."""
    tool_turn = [THINK, {"type": "tool_use", "id": "t1", "name": "run_simulation", "input": {"options": []}}]
    bad = [THINK, {"type": "text", "text": "not json"}]
    good = [THINK, {"type": "text", "text": json.dumps({"family_stage": "신혼", "living": "전세",
                                                         "shared_goal": "집", "differences": ["순서"]})}]
    p, fake = make([FakeResp(tool_turn, "tool_use"), FakeResp(bad), FakeResp(good)])
    tools = [{"name": "run_simulation", "description": "d", "input_schema": {"type": "object"}}]
    run = run_role("1a", {"story": "우리 가족 이야기", "today": "2026-10-06", "members": [], "reason": ""}, p, tools=tools, tool_handler=lambda n, a: {"ok": True})
    assert len(fake.calls) == 3
    assert all(c["tools"] == fake.calls[0]["tools"] for c in fake.calls)
    last = fake.calls[2]["messages"]
    for i, c in enumerate(fake.calls[:2]):  # 앞 요청의 메시지가 다음 요청의 앞부분과 똑같다
        assert last[:len(c["messages"])] == c["messages"]
    assert last[1]["content"] == tool_turn and last[3]["content"] == bad
    assert run.tool_calls == 1


def test_cache_only_when_reused():
    p, fake = make([FakeResp([THINK, {"type": "text", "text": "{}"}]), FakeResp([THINK, {"type": "text", "text": "{}"}])])
    p.complete("sys", [{"role": "user", "content": "hi"}])
    assert "cache_control" not in fake.calls[0]  # 한 번만 쓰는 호출에는 캐시 쓰기 비용을 내지 않는다
    p.complete("sys", [{"role": "user", "content": "hi"}], tools=[{"name": "t", "description": "d", "input_schema": {"type": "object"}}])
    assert fake.calls[1]["cache_control"] == {"type": "ephemeral"}
