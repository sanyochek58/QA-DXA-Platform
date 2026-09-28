"""Пакетная обработка набора исследований (требование ТЗ, раздел 2.5 и 2.7).

Вход: папка или zip-архив с DICOM в любой вложенности.
Выход:
  results.csv / results.xlsx — одна строка на снимок, колонки по ТЗ + служебные;
  series/<study>/*.dcm       — дополнительная серия (Secondary Capture) с визуализацией нарушений;
  previews/<study>/*.png     — те же визуализации в PNG;
  series.zip                 — дополнительные серии одним архивом.

Снимки группируются в исследования по StudyInstanceUID, при его отсутствии — по родительской папке.
Любая ошибка на снимке или исследовании попадает в отчёт (processing_status=Failure), обработка
остальных продолжается.

Запуск без Docker (из services/ml):
    uv run python -m app.batch <папка_или_zip> <папка_результатов>
Через Docker — скрипт run_batch.sh в корне репозитория.
"""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
import time
import warnings
import zipfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pydicom
from PIL import Image
from pydicom.dataset import FileDataset, FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian, SecondaryCaptureImageStorage, generate_uid

from app.pipeline.analyzer import Analyzer

COLUMNS = [
    # обязательные колонки из ТЗ (раздел 2.5), в том же порядке
    "path_to_study",
    "study_uid",
    "image_uid",
    "anatomical_region",
    "quality_class",
    "violation_type",
    "processing_status",
    "time_of_processing",
    # дополнительные колонки для удобства эксперта
    "study_quality_class",
    "violation_probability",
    "needs_review",
    "additional_series",
    "error",
]
MAX_ZIP_BYTES = 5 * 1024**3  # защита от zip-бомбы: не распаковываем больше 5 ГБ


@dataclass
class StudyGroup:
    key: str
    study_uid: str
    files: list[Path] = field(default_factory=list)
    image_uids: list[str] = field(default_factory=list)


def _is_dicom(path: Path) -> bool:
    try:
        with path.open("rb") as f:
            head = f.read(132)
    except OSError:
        return False
    return head[128:132] == b"DICM" or path.suffix.lower() in {".dcm", ".dicom"}


def _fix_name(info: zipfile.ZipInfo) -> str:
    """Архивы с Windows хранят кириллицу в cp866 без флага UTF-8; zipfile читает их как cp437."""
    if info.flag_bits & 0x800:
        return info.filename
    raw = info.filename.encode("cp437", errors="replace")
    for enc in ("utf-8", "cp866"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return info.filename


def safe_extract(archive: Path, dest: Path) -> None:
    """Распаковка zip с защитой от zip-slip (../../etc) и чрезмерного размера."""
    with zipfile.ZipFile(archive) as zf:
        infos = zf.infolist()
        if sum(i.file_size for i in infos) > MAX_ZIP_BYTES:
            raise ValueError(f"Архив после распаковки больше {MAX_ZIP_BYTES // 1024**3} ГБ")
        root = dest.resolve()
        for info in infos:
            target = (dest / _fix_name(info)).resolve()
            if not target.is_relative_to(root):
                raise ValueError(f"Недопустимый путь в архиве: {info.filename}")
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, target.open("wb") as dst:
                shutil.copyfileobj(src, dst)


def group_studies(root: Path) -> list[StudyGroup]:
    groups: dict[str, StudyGroup] = {}
    for path in sorted(p for p in root.rglob("*") if p.is_file() and _is_dicom(p)):
        study_uid = image_uid = ""
        try:
            ds = pydicom.dcmread(path, stop_before_pixels=True, force=True)
            study_uid = str(getattr(ds, "StudyInstanceUID", "") or "")
            image_uid = str(getattr(ds, "SOPInstanceUID", "") or "")
        except Exception:  # noqa: BLE001 — нечитаемый файл всё равно попадёт в отчёт как Failure
            pass
        key = study_uid or f"folder:{path.parent.relative_to(root)}"
        g = groups.setdefault(key, StudyGroup(key=key, study_uid=study_uid))
        g.files.append(path)
        g.image_uids.append(image_uid)
    return list(groups.values())


def _secondary_capture(png: Path, out: Path, study_uid: str, series_uid: str, number: int) -> None:
    """DICOM Secondary Capture с визуализацией: открывается в любом DICOM-просмотрщике рядом с исходником."""
    rgb = np.asarray(Image.open(png).convert("RGB"))
    meta = FileMetaDataset()
    meta.MediaStorageSOPClassUID = SecondaryCaptureImageStorage
    meta.MediaStorageSOPInstanceUID = generate_uid()
    meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds = FileDataset(str(out), {}, file_meta=meta, preamble=b"\0" * 128)
    now = datetime.now(UTC)
    ds.SOPClassUID = SecondaryCaptureImageStorage
    ds.SOPInstanceUID = meta.MediaStorageSOPInstanceUID
    ds.StudyInstanceUID = study_uid or generate_uid()
    ds.SeriesInstanceUID = series_uid
    ds.Modality = "OT"
    ds.ConversionType = "WSD"
    ds.SeriesDescription = "DXA-QA: визуализация контроля качества"
    ds.SeriesNumber = 999
    ds.InstanceNumber = number
    ds.ContentDate = now.strftime("%Y%m%d")
    ds.ContentTime = now.strftime("%H%M%S")
    ds.Rows, ds.Columns = rgb.shape[:2]
    ds.SamplesPerPixel = 3
    ds.PhotometricInterpretation = "RGB"
    ds.PlanarConfiguration = 0
    ds.BitsAllocated = ds.BitsStored = 8
    ds.HighBit = 7
    ds.PixelRepresentation = 0
    ds.PixelData = rgb.tobytes()
    ds.save_as(out, enforce_file_format=True)


def process_study(analyzer: Analyzer, g: StudyGroup, n: int, input_root: Path, out_dir: Path) -> list[dict]:
    """Одно исследование -> строки отчёта. Никогда не бросает исключение наружу."""
    folder = f"study_{n:04d}"
    rel_paths = [str(p.relative_to(input_root)) for p in g.files]
    started = time.perf_counter()
    try:
        # rel_files задают, куда анализатор положит превью: previews/study_NNNN/preview_i.png
        pseudo = [f"{folder}/{i}.dcm" for i in range(len(g.files))]
        res = analyzer.analyze(folder, g.files, pseudo, out_dir / "previews")
    except Exception as e:  # noqa: BLE001
        per_image = (time.perf_counter() - started) / max(len(g.files), 1)
        return [
            {
                "path_to_study": rel,
                "study_uid": g.study_uid,
                "image_uid": uid,
                "anatomical_region": "unknown",
                "quality_class": None,
                "violation_type": "",
                "processing_status": "Failure",
                "time_of_processing": round(per_image, 3),
                "error": f"{type(e).__name__}: {e}",
            }
            for rel, uid in zip(rel_paths, g.image_uids, strict=True)
        ]

    elapsed = time.perf_counter() - started
    per_image = elapsed / max(len(g.files), 1)
    bad_regions = {r.region for r in res.regions if not r.quality_ok}
    codes_by_region: dict[str, list[str]] = {}
    prob_by_region: dict[str, float] = {r.region: r.probability_bad for r in res.regions}
    for v in res.violations:
        codes_by_region.setdefault(v.region, []).append(v.code)

    series_uid = generate_uid()
    rows = []
    for img in res.images:
        failed = img.preview_path is None  # анализатор не смог прочитать пиксели
        series_file = ""
        if not failed:
            png = out_dir / "previews" / img.preview_path
            sc = out_dir / "series" / folder / f"qa_{img.index + 1}.dcm"
            try:
                sc.parent.mkdir(parents=True, exist_ok=True)
                _secondary_capture(png, sc, g.study_uid, series_uid, img.index + 1)
                series_file = str(sc.relative_to(out_dir))
            except Exception:  # noqa: BLE001 — визуализация необязательна, результат важнее
                series_file = ""
        region = img.region
        known = region in ("spine", "right_hip", "left_hip")
        rows.append(
            {
                "path_to_study": rel_paths[img.index],
                "study_uid": g.study_uid,
                "image_uid": g.image_uids[img.index],
                "anatomical_region": region,
                "quality_class": (1 if region in bad_regions else 0) if known and not failed else None,
                "violation_type": ";".join(codes_by_region.get(region, [])) if known else "",
                "processing_status": "Failure" if failed else "Success",
                "time_of_processing": round(per_image, 3),
                "study_quality_class": 0 if res.quality_ok else 1,
                "violation_probability": prob_by_region.get(region),
                "needs_review": res.needs_review,
                "additional_series": series_file,
                "error": "Не удалось прочитать изображение" if failed else ("" if known else "Область не определена"),
            }
        )
    return rows


def run_batch(input_path: Path, out_dir: Path, analyzer: Analyzer | None = None, log=print) -> pd.DataFrame:
    out_dir.mkdir(parents=True, exist_ok=True)
    analyzer = analyzer or Analyzer()
    with tempfile.TemporaryDirectory(prefix="dxa-batch-") as tmp:
        if input_path.is_file() and zipfile.is_zipfile(input_path):
            root = Path(tmp) / "input"
            safe_extract(input_path, root)
        elif input_path.is_dir():
            root = input_path
        else:
            raise ValueError(f"Ожидается папка или zip-архив: {input_path}")

        groups = group_studies(root)
        log(f"Найдено исследований: {len(groups)}, снимков: {sum(len(g.files) for g in groups)}")
        rows: list[dict] = []
        t0 = time.perf_counter()
        for n, g in enumerate(groups, 1):
            study_rows = process_study(analyzer, g, n, root, out_dir)
            rows.extend(study_rows)
            status = "ошибка" if any(r["processing_status"] == "Failure" for r in study_rows) else "ок"
            log(f"  [{n}/{len(groups)}] {len(g.files)} сним. — {status}")

    df = pd.DataFrame(rows).reindex(columns=COLUMNS)
    df["quality_class"] = df["quality_class"].astype("Int64")
    df["study_quality_class"] = df["study_quality_class"].astype("Int64")
    df.to_csv(out_dir / "results.csv", index=False, encoding="utf-8-sig")  # BOM — чтобы Excel открыл кириллицу
    df.to_excel(out_dir / "results.xlsx", index=False)
    series_dir = out_dir / "series"
    if series_dir.exists():
        shutil.make_archive(str(out_dir / "series"), "zip", series_dir)
    total = time.perf_counter() - t0
    ok = int((df["processing_status"] == "Success").sum())
    log(f"Готово за {total:.1f} с: успешно {ok} из {len(df)} снимков. Результаты: {out_dir}")
    return df


def main() -> int:
    # предупреждения pydicom о нестандартных тегах и skimage не нужны в отчёте эксперту
    warnings.filterwarnings("ignore")
    ap = argparse.ArgumentParser(description="Пакетная проверка качества DXA-исследований")
    ap.add_argument("input", type=Path, help="папка или zip-архив с DICOM")
    ap.add_argument("output", type=Path, help="папка для results.csv/xlsx и дополнительных серий")
    args = ap.parse_args()
    try:
        run_batch(args.input, args.output)
    except Exception as e:  # noqa: BLE001
        print(f"Ошибка: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
