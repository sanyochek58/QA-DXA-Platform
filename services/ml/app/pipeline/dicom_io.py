"""Чтение DICOM и приведение пикселей к 8-битному изображению."""

from pathlib import Path

import numpy as np
import pydicom
from pydicom.dataset import FileDataset


def read_dicom(path: Path) -> FileDataset:
    # force=True: читать даже файлы без стандартной преамбулы
    return pydicom.dcmread(path, force=True)


def to_uint8(ds: FileDataset) -> np.ndarray:
    """Пиксели -> 2D uint8. Учитывает MONOCHROME1 (инвертированная шкала) и многокадровые файлы."""
    arr = ds.pixel_array
    if arr.ndim == 3 and arr.shape[-1] not in (3, 4):
        arr = arr[0]
    if arr.ndim == 3:
        arr = arr[..., :3].mean(axis=-1)
    arr = arr.astype(np.float32)
    if getattr(ds, "PhotometricInterpretation", "") == "MONOCHROME1":
        arr = arr.max() - arr
    lo, hi = float(arr.min()), float(arr.max())
    if hi > 255 or lo < 0:
        arr = (arr - lo) / max(hi - lo, 1e-6) * 255
    return np.clip(arr, 0, 255).astype(np.uint8)


def extract_metadata(ds: FileDataset) -> dict[str, str]:
    """Только модальность. Производитель, модель и серийный номер аппарата, версия ПО,
    учреждение и данные пациента наружу не отдаются и нигде не сохраняются."""
    val = getattr(ds, "Modality", None)
    return {"modality": str(val)} if val else {}
