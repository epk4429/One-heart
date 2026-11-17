"""가족방 합치기(web/js/room.js mergeState·shareState·assignState)를 Node로 돌려 본다. Node가 없는 PC에서는 건너뛴다."""

import shutil
import subprocess
from pathlib import Path

import pytest

JS = Path(__file__).parent / "js" / "room_merge.js"


@pytest.mark.skipif(shutil.which("node") is None, reason="Node가 없어요")
def test_room_merge_logic():
    r = subprocess.run(["node", str(JS)], capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stdout + r.stderr
    assert r.stdout.count("ok ") == 11 and "FAIL" not in r.stdout
