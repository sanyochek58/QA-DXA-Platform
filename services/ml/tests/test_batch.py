"""Пакетная обработка: формат отчёта по ТЗ, устойчивость к мусору, zip-slip, HTTP API."""

import io
import zipfile
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.batch import COLUMNS, run_batch, safe_extract
from app.pipeline.analyzer import Analyzer

TEST_DIR = Path(__file__).resolve().parents[3] / "data" / "test"
REQUIRED = [
    "path_to_study",
    "study_uid",
    "image_uid",
    "anatomical_region",
    "quality_class",
    "violation_type",
    "processing_status",
    "time_of_processing",
]
needs_data = pytest.mark.skipif(not TEST_DIR.exists(), reason="нет data/test")


def _make_input(tmp_path: Path) -> Path:
    src = tmp_path / "in"
    (src / "nested" / "deeper").mkdir(parents=True)
    for f in sorted(TEST_DIR.glob("*.dcm")):
        (src / "nested" / "deeper" / f.name).write_bytes(f.read_bytes())
    (src / "broken.dcm").write_bytes(b"not a dicom at all")
    (src / "notes.txt").write_text("мусор, который надо пропустить")
    return src


@needs_data
def test_batch_report_format_and_resilience(tmp_path):
    out = tmp_path / "out"
    df = run_batch(_make_input(tmp_path), out, Analyzer(), log=lambda *_: None)

    assert list(df.columns) == COLUMNS
    assert df.columns[: len(REQUIRED)].tolist() == REQUIRED  # порядок как в ТЗ
    assert (out / "results.csv").exists() and (out / "results.xlsx").exists()
    assert (out / "series.zip").exists()

    ok = df[df.processing_status == "Success"]
    assert len(ok) == 3
    assert set(ok.anatomical_region) == {"spine", "right_hip", "left_hip"}
    assert set(ok.quality_class.dropna().astype(int)) <= {0, 1}
    assert (ok.time_of_processing >= 0).all()

    broken = df[df.path_to_study.str.endswith("broken.dcm")]
    assert broken.processing_status.tolist() == ["Failure"]
    assert not df.path_to_study.str.endswith("notes.txt").any()

    xlsx = pd.read_excel(out / "results.xlsx")
    assert len(xlsx) == len(df)


def test_zip_slip_rejected(tmp_path):
    evil = tmp_path / "evil.zip"
    with zipfile.ZipFile(evil, "w") as zf:
        zf.writestr("../../escape.dcm", b"x")
    with pytest.raises(ValueError, match="Недопустимый путь"):
        safe_extract(evil, tmp_path / "dest")


@needs_data
def test_batch_http_api():
    from app.main import app

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for f in sorted(TEST_DIR.glob("*.dcm")):
            zf.write(f, f"study/{f.name}")
    with TestClient(app) as client:
        resp = client.post("/v1/batch", files={"archive": ("s.zip", buf.getvalue(), "application/zip")})
        assert resp.status_code == 200
        names = zipfile.ZipFile(io.BytesIO(resp.content)).namelist()
        assert "results.csv" in names and "results.xlsx" in names
        assert any(n.startswith("series/") for n in names)

        bad = client.post("/v1/batch", files={"archive": ("x.zip", b"not a zip", "application/zip")})
        assert bad.status_code == 400
