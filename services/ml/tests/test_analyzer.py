"""Проверка инференса на подписанных тестовых снимках организаторов.

Файлы лежат в data/test (не в git). Если их нет — тест пропускается.
Запуск: uv run pytest
"""

import shutil
from pathlib import Path

import pytest

from app.pipeline.analyzer import Analyzer

TEST_DIR = Path(__file__).resolve().parents[3] / "data" / "test"
EXPECTED = {"ПОП": "spine", "ППОБ": "right_hip", "ЛПОБ": "left_hip"}


@pytest.fixture(scope="module")
def analyzer():
    return Analyzer()


@pytest.mark.skipif(not TEST_DIR.exists(), reason="нет data/test")
def test_regions_and_contract(analyzer, tmp_path):
    files = sorted(TEST_DIR.rglob("*.dcm"))
    assert files, "в data/test нет DICOM"
    rel = []
    for i, f in enumerate(files):
        dst = tmp_path / "studies" / "t" / f"{i}.dcm"
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(f, dst)
        rel.append(f"studies/t/{i}.dcm")

    res = analyzer.analyze("t", [tmp_path / r for r in rel], rel, tmp_path)

    for f, img in zip(files, res.images, strict=True):
        tag = f.stem.split("_")[-1]
        assert img.region == EXPECTED[tag], f.name
        assert img.preview_path and (tmp_path / img.preview_path).is_file()
    assert {r.region for r in res.regions} == {"spine", "right_hip", "left_hip"}
    for v in res.violations:
        assert v.how_to_fix_ru and 0 <= v.probability <= 1
    assert res.quality_ok == all(r.quality_ok for r in res.regions)
