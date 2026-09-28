"""Инференс: DICOM-файлы исследования -> вердикт по контракту AnalyzeResponse.

Шаги:
1. Каждый снимок: чтение, определение области (позвоночник / правое / левое бедро).
2. Для каждой области: признаки снимков усредняются (как при обучении).
3. Модели выдают вероятность каждого нарушения; порог подобран на кросс-валидации.
4. Неуверенные случаи (вероятность близко к порогу, сомнительная область) -> в очередь врачу.
5. Для каждого снимка рендерится PNG с осью и найденными артефактами.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import yaml

from app.pipeline.dicom_io import extract_metadata, read_dicom, to_uint8
from app.pipeline.features import hip_features, region_hog, spine_features
from app.pipeline.overlay import render
from app.schemas import AnalyzeResponse, ImageResult, RegionResult, Violation

ROOT = Path(__file__).resolve().parents[2]
REVIEW_MARGIN = 0.12  # |p - порог| меньше этого -> модель не уверена
REGION_MIN_CONF = 0.8
REGION_RU = {"spine": "позвоночник", "right_hip": "правое бедро", "left_hip": "левое бедро"}

# цель модели -> код нарушения и признаки, которые показываем как доказательство
SPECIFIC = {
    "spine_positioning": ("SPINE_POSITIONING", ["sp_cl_offset", "lr_asym"]),
    "spine_axis": ("SPINE_AXIS", ["sp_cl_abs_angle", "sp_cl_maxdev"]),
    "spine_artifact": ("SPINE_ARTIFACT", ["line_count", "line_total_len", "blob_count"]),
    "hip_rotation": ("HIP_ROTATION", ["shaft_cl_abs_angle", "lt_mean"]),
    "hip_roi": ("HIP_ROI", ["shaft_cl_width", "box_area"]),
}
EVIDENCE_LABELS = {
    "sp_cl_abs_angle": "axis_angle_deg",
    "sp_cl_maxdev": "axis_max_deviation",
    "sp_cl_offset": "center_offset",
    "lr_asym": "left_right_asymmetry",
    "line_count": "foreign_lines",
    "line_total_len": "foreign_lines_length",
    "blob_count": "bright_spots",
    "shaft_cl_abs_angle": "shaft_angle_deg",
    "lt_mean": "lesser_trochanter_signal",
    "shaft_cl_width": "shaft_width",
    "box_area": "masked_area",
}


@dataclass
class _Image:
    index: int
    file: str
    pixels: np.ndarray | None
    region: str
    conf: float
    feats: dict[str, float] | None


class Analyzer:
    def __init__(self, model_path: Path | None = None, reference_path: Path | None = None) -> None:
        self.bundle = joblib.load(model_path or ROOT / "models" / "dxa_quality.joblib")
        self.reference: dict = yaml.safe_load(
            (reference_path or ROOT / "reference" / "violations.yml").read_text("utf-8")
        )
        self.version = "1.0"

    # ------------------------------------------------------------ helpers
    def _predict(self, target: str, feats: dict[str, float], columns: list[str]) -> tuple[float, float]:
        t = self.bundle["targets"][target]
        X = pd.DataFrame([feats]).reindex(columns=columns, fill_value=0.0).to_numpy(dtype=np.float32)
        # threshold_scale подобран на кросс-валидации для итога по исследованию (см. train.py)
        thr = min(0.99, float(t["threshold"]) * float(self.bundle.get("threshold_scale", 1.0)))
        return float(t["model"].predict_proba(X)[0, 1]), thr

    def _violation(
        self, code: str, region: str, p: float, thr: float, evidence: dict[str, float], images: list[int]
    ) -> Violation:
        ref = self.reference[code]
        return Violation(
            code=code,
            region=region,
            severity=ref["severity"],
            probability=round(p, 3),
            threshold=round(thr, 3),
            title_ru=ref["title_ru"],
            message_ru=ref["message_ru"].strip(),
            how_to_fix_ru=ref["how_to_fix_ru"].strip(),
            evidence=evidence,
            image_indexes=images,
        )

    # ------------------------------------------------------------ main
    def analyze(self, study_id: str, files: list[Path], rel_files: list[str], data_dir: Path) -> AnalyzeResponse:
        started = time.perf_counter()
        images: list[_Image] = []
        metadata: dict[str, str] = {}
        review_reasons: list[str] = []

        for i, (path, rel) in enumerate(zip(files, rel_files, strict=True)):
            try:
                ds = read_dicom(path)
                px = to_uint8(ds)
                metadata = metadata or extract_metadata(ds)
            except Exception:  # noqa: BLE001
                images.append(_Image(i, rel, None, "unknown", 0.0, None))
                review_reasons.append(f"Снимок {i + 1}: не удалось прочитать изображение")
                continue
            proba = self.bundle["region_model"].predict_proba([region_hog(px)])[0]
            classes = list(self.bundle["region_model"].classes_)
            region = str(classes[int(np.argmax(proba))])
            conf = float(np.max(proba))
            if conf < REGION_MIN_CONF:
                review_reasons.append(f"Снимок {i + 1}: область определена неуверенно ({conf:.0%})")
            if region == "spine":
                feats = spine_features(px)
            else:
                feats = hip_features(px, "right" if region == "right_hip" else "left")
            images.append(_Image(i, rel, px, region, conf, feats))

        violations: list[Violation] = []
        regions: list[RegionResult] = []
        for region in ("spine", "right_hip", "left_hip"):
            group = [im for im in images if im.region == region and im.feats is not None]
            if not group:
                continue
            idx = [im.index for im in group]
            agg = pd.DataFrame([im.feats for im in group]).mean().to_dict()
            agg["n_images"] = len(group)
            kind = "spine" if region == "spine" else "hip"
            columns = self.bundle["spine_features"] if kind == "spine" else self.bundle["hip_features"]

            found: list[Violation] = []
            for target, (code, ev_keys) in SPECIFIC.items():
                if not target.startswith(kind):
                    continue
                p, thr = self._predict(target, agg, columns)
                if abs(p - thr) < REVIEW_MARGIN:
                    review_reasons.append(f"{self.reference[code]['title_ru']}: вероятность {p:.0%}, близко к порогу")
                if p >= thr:
                    evidence = {EVIDENCE_LABELS[k]: round(float(agg.get(k, 0.0)), 3) for k in ev_keys}
                    found.append(self._violation(code, region, p, thr, evidence, idx))

            p_tot, thr_tot = self._predict(f"{kind}_total", agg, columns)
            if abs(p_tot - thr_tot) < REVIEW_MARGIN:
                name = REGION_RU.get(region, region)
                review_reasons.append(f"Общая оценка, {name}: вероятность нарушения {p_tot:.0%}, близко к порогу")
            bad = bool(found) or p_tot >= thr_tot
            if p_tot >= thr_tot and not found:
                found.append(self._violation(f"{kind.upper()}_OTHER", region, p_tot, thr_tot, {}, idx))
            violations.extend(found)
            regions.append(
                RegionResult(
                    region=region,
                    quality_ok=not bad,
                    probability_bad=round(p_tot, 3),
                    threshold=round(thr_tot, 3),
                    image_indexes=idx,
                )
            )

        if not regions:
            review_reasons.append("Не найдено ни одного снимка позвоночника или бедра")

        results: list[ImageResult] = []
        bad_regions = {r.region for r in regions if not r.quality_ok}
        for im in images:
            preview = None
            if im.pixels is not None:
                preview_rel = str(Path(im.file).with_name(f"preview_{im.index}.png"))
                render(im.pixels, im.region, im.region in bad_regions, data_dir / preview_rel)
                preview = preview_rel
            meas = {}
            if im.feats:
                key = "sp_cl_abs_angle" if im.region == "spine" else "shaft_cl_abs_angle"
                meas["axis_angle_deg"] = round(float(im.feats.get(key, 0.0)), 2)
                meas["foreign_lines"] = float(im.feats.get("line_count", 0.0))
            results.append(
                ImageResult(
                    index=im.index,
                    file=im.file,
                    region=im.region,
                    region_confidence=round(im.conf, 3),
                    preview_path=preview,
                    measurements=meas,
                )
            )

        quality_ok = bool(regions) and all(r.quality_ok for r in regions)
        return AnalyzeResponse(
            study_id=study_id,
            quality_ok=quality_ok,
            needs_review=bool(review_reasons),
            review_reasons=review_reasons,
            regions=regions,
            violations=violations,
            images=results,
            metadata=metadata,
            model_version=self.version,
            processing_ms=int((time.perf_counter() - started) * 1000),
        )
