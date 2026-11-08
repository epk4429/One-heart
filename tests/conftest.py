"""모든 테스트 공통 격리: 이 PC의 .env(체험 코드·공급자)나 앞 테스트의 호출 수에 따라 결과가 달라지지 않게 한다.
(2026-11-08: 체험 코드가 있는 PC에서 401, 호출이 늘면 429가 나던 문제. 개별 테스트가 필요하면 그 안에서 다시 바꾼다.)"""

import pytest

from server import app as A
from server import guard


@pytest.fixture(autouse=True)
def _isolate_server_env(tmp_path, monkeypatch):
    monkeypatch.setattr(guard, "USAGE_FILE", tmp_path / "usage.json")
    monkeypatch.setenv("LLM_PROVIDER", "replay")
    monkeypatch.setenv("ACCESS_CODES", "")  # 빈 값이면 .env를 읽어도 덮어쓰지 않는다(load_env는 setdefault)
    monkeypatch.setenv("RATE_PER_MIN", "1000")
    A._provider = None
    yield
    A._provider = None
