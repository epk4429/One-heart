"""원문 저장소의 공시 원본 → 상품 노드·범주 통계(ontology/products.py). API를 부르지 않는다.

사용: python tools/build_products.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ontology.products import build_all  # noqa: E402

if __name__ == "__main__":
    for path, n in build_all().items():
        print(f"{path}  {n}")
