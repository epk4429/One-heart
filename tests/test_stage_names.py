"""G12 금지 이름 목록(ontology/products.py): 금융회사 이름 + 한 회사에만 있는 브랜드 상품 이름. 흔한 말로 된 상품 이름은 막지 않는다."""

import glob
from pathlib import Path

from ontology.products import banned_names_in, product_brand_names, provider_names, stage_banned_names

ROOT = Path(__file__).resolve().parents[1]


def test_generic_product_names_are_not_banned():
    b = product_brand_names()
    for w in ("정기예금", "정기적금", "신용대출", "주택담보대출", "햇살론", "개인사업자 대출", "중도금대출", "모기지론"):
        assert w not in b, w
    assert banned_names_in("비상금은 정기예금이나 정기적금으로, 신용대출부터 갚아요.") == []


def test_brand_product_and_company_names_are_banned():
    assert provider_names() <= stage_banned_names()
    kb = sorted(n for n in product_brand_names() if n.startswith("KB"))
    assert kb and banned_names_in(f"{kb[0]}에 넣어요") == [kb[0]]
    assert banned_names_in("우리은행 적금") == ["우리은행"]


def test_recorded_real_outputs_have_no_banned_names():
    """실제 Claude로 돌린 평가 기록(4가족)과 예시 가족에 금지 이름이 하나도 없다 = 오탐으로 다시 쓰게 하지 않는다."""
    files = glob.glob(str(ROOT / "data/eval/*.json")) + glob.glob(str(ROOT / "data/presets/*.json"))
    text = "".join(Path(f).read_text(encoding="utf-8") for f in files)
    assert files and banned_names_in(text) == []
