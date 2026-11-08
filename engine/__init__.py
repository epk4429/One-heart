"""ONE-Heart 계산엔진.

금융 숫자는 LLM이 아니라 이 엔진이 낸다(docs/04_계산엔진.md).
외부 의존성 없는 순수 Python이라 서버리스 함수와 로컬 테스트에서 같은 코드를 쓴다.
"""

from .api import ENGINE_VERSION, compare, simulate
from .schema import EngineInputError

__all__ = ["ENGINE_VERSION", "EngineInputError", "compare", "simulate"]
