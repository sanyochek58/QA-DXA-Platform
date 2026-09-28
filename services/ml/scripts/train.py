"""Обучение моделей качества DXA на датасете организаторов.

Запуск (из services/ml):
    uv run python -m scripts.train --data ../../data/train --test ../../data/test

Что делает:
1. Находит все DICOM и определяет область каждого снимка (позвоночник / правое / левое бедро).
   Разметки по снимкам нет, поэтому классификатор области строится без учителя:
   HOG + KMeans на 3 кластера, кластеры именуются по асимметрии изображения,
   затем обучается логистическая регрессия. Проверка — на подписанных файлах из «Для теста».
2. Для каждой пары (исследование, область) усредняет признаки снимков.
3. Для каждого типа нарушения перебирает несколько моделей с кросс-валидацией
   по исследованиям (одно исследование никогда не бывает и в train, и в test),
   выбирает лучшую по ROC-AUC и подбирает порог по F1 на out-of-fold предсказаниях.
4. Сохраняет models/dxa_quality.joblib и models/metrics.json.
"""

from __future__ import annotations

import argparse
import json
import re
import warnings
from datetime import UTC, datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pydicom
from sklearn.base import clone
from sklearn.cluster import KMeans
from sklearn.compose import ColumnTransformer
from sklearn.decomposition import PCA
from sklearn.ensemble import ExtraTreesClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    balanced_accuracy_score,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from app.pipeline.features import hip_features, region_hog, spine_features

warnings.filterwarnings("ignore")

MODELS_DIR = Path(__file__).resolve().parents[1] / "models"
REGIONS = ("spine", "right_hip", "left_hip")

# Столбцы листа «Калибровка» (после двух строк заголовка)
COLS = [
    "n",
    "study",
    "sp_pos",
    "sp_axis",
    "sp_artifact",
    "rh_pos",
    "rh_roi",
    "lh_pos",
    "lh_roi",
    "total_spine",
    "total_rh",
    "total_lh",
    "comment",
]

# Какие цели обучаем. hip_* — объединённые правое и левое бедро (левое зеркалится).
TARGETS = {
    "spine_positioning": ("spine", "sp_pos"),
    "spine_axis": ("spine", "sp_axis"),
    "spine_artifact": ("spine", "sp_artifact"),
    "spine_total": ("spine", "total_spine"),
    "hip_rotation": ("hip", "pos"),
    "hip_roi": ("hip", "roi"),
    "hip_total": ("hip", "total"),
}


def read_dicom_pixels(path: Path) -> np.ndarray | None:
    try:
        ds = pydicom.dcmread(path, force=True)
        arr = ds.pixel_array
    except Exception:  # noqa: BLE001
        return None
    if arr.ndim == 3 and arr.shape[-1] not in (3, 4):
        arr = arr[0]
    if arr.ndim == 3:
        arr = arr[..., :3].mean(axis=-1)
    if getattr(ds, "PhotometricInterpretation", "") == "MONOCHROME1":
        arr = arr.max() - arr
    arr = arr.astype(np.float32)
    if arr.max() > 255:
        arr = arr / arr.max() * 255
    return arr.astype(np.uint8)


# ---------------------------------------------------------------- область снимка
def fit_region_model(images: list[np.ndarray]) -> tuple[object, list[str]]:
    X = np.array([region_hog(a) for a in images])
    z = PCA(10, random_state=0).fit_transform(X)
    clusters = KMeans(3, n_init=20, random_state=0).fit_predict(z)

    def asym(a: np.ndarray) -> float:
        h, w = a.shape
        top = a[: int(h * 0.4)].astype(np.float32) / 255
        return float(top[:, int(w * 0.58) :].mean() - top[:, : int(w * 0.42)].mean())

    mean_asym = {c: np.mean([asym(images[i]) for i in np.where(clusters == c)[0]]) for c in range(3)}
    order = sorted(mean_asym, key=lambda c: mean_asym[c])  # min -> left_hip, max -> right_hip
    names = {order[0]: "left_hip", order[1]: "spine", order[2]: "right_hip"}
    y = np.array([names[c] for c in clusters])
    model = make_pipeline(StandardScaler(), LogisticRegression(max_iter=3000, C=0.5))
    model.fit(X, y)
    return model, list(y)


# ---------------------------------------------------------------- данные
def load_labels(xlsx: Path) -> pd.DataFrame:
    df = pd.read_excel(xlsx, header=None, skiprows=2).iloc[:, : len(COLS)]
    df.columns = COLS
    df["study"] = df["study"].astype(str).str.strip()
    return df.set_index("study")


def collect(data_dir: Path) -> tuple[list[dict], list[np.ndarray]]:
    items, images = [], []
    for study_dir in sorted((data_dir / "Исследования").iterdir()):
        for f in sorted(study_dir.rglob("*.dcm")):
            arr = read_dicom_pixels(f)
            if arr is None:
                continue
            items.append({"study": study_dir.name, "path": str(f)})
            images.append(arr)
    return items, images


def build_tables(items, images, regions, labels):
    spine_rows, hip_rows = [], []
    by_key: dict[tuple[str, str], list[dict]] = {}
    for it, img, reg in zip(items, images, regions, strict=True):
        if reg == "spine":
            feats = spine_features(img)
        else:
            feats = hip_features(img, "right" if reg == "right_hip" else "left")
        by_key.setdefault((it["study"], reg), []).append(feats)

    for (study, reg), feats in by_key.items():
        if study not in labels.index:
            continue
        lab = labels.loc[study]
        agg = pd.DataFrame(feats).mean().to_dict()
        agg["n_images"] = len(feats)
        if reg == "spine":
            y = {k: lab[k] for k in ("sp_pos", "sp_axis", "sp_artifact", "total_spine")}
            if pd.isna(y["total_spine"]):
                continue
            spine_rows.append({"study": study, **agg, **{f"y_{k}": v for k, v in y.items()}})
        else:
            p = "rh" if reg == "right_hip" else "lh"
            y = {"pos": lab[f"{p}_pos"], "roi": lab[f"{p}_roi"], "total": lab[f"total_{p}"]}
            if pd.isna(y["total"]):
                continue
            hip_rows.append({"study": study, "side": reg, **agg, **{f"y_{k}": v for k, v in y.items()}})
    return pd.DataFrame(spine_rows), pd.DataFrame(hip_rows)


# ---------------------------------------------------------------- модели
# Короткие наборы признаков, осмысленные для конкретной проверки (экспертное знание).
# На малых данных модель на 3-8 понятных признаках часто лучше, чем на сотне.
KEY_FEATURES = {
    "spine_axis": ["sp_cl_abs_angle", "sp_top_angle", "sp_bot_angle", "sp_cl_maxdev", "sp_cl_resid", "sp_angle_diff"],
    "spine_artifact": [
        "tophat_top_energy",
        "line_top_len",
        "tophat_lateral_energy",
        "line_max_len",
        "line_total_len",
        "line_count",
        "blob_count",
        "sat_frac",
    ],
    "spine_positioning": [
        "blob_count",
        "box_rect",
        "dark_frac",
        "box_area",
        "box_cy",
        "sp_cl_resid",
        "sp_cl_offset",
        "lr_asym",
    ],
    "spine_total": [
        "sp_cl_abs_angle",
        "sp_top_angle",
        "sp_cl_maxdev",
        "tophat_top_energy",
        "line_top_len",
        "line_max_len",
        "blob_count",
        "box_rect",
        "sp_cl_resid",
    ],
    "hip_rotation": [
        "lt_mean",
        "lt_p90",
        "shaft_cl_abs_angle",
        "shaft_cl_offset",
        "shaft_width",
        "shaft_cl_width",
        "neck_mean",
        "med_edge_std",
    ],
    "hip_roi": ["h_ratio", "shaft_cl_width", "int_mean", "lt_bump_rel", "int_p99", "sat_frac"],
    "hip_total": [
        "shaft_cl_abs_angle",
        "shaft_cl_width",
        "lt_mean",
        "int_p75",
        "int_p99",
        "shaft_cl_offset",
        "h_ratio",
        "med_edge_std",
    ],
}


def _geom_idx(feature_cols: list[str]) -> list[int]:
    """Индексы «геометрических» признаков: всё, кроме сырого HOG."""
    return [i for i, c in enumerate(feature_cols) if not c.startswith("hog")]


def candidates(feature_cols: list[str], target: str | None = None):
    geom = ColumnTransformer([("geom", "passthrough", _geom_idx(feature_cols))])
    extra = {}
    keys = [feature_cols.index(k) for k in KEY_FEATURES.get(target or "", []) if k in feature_cols]
    if keys:
        sel = ColumnTransformer([("key", "passthrough", keys)])
        extra = {
            "logreg_key": make_pipeline(
                clone(sel), StandardScaler(), LogisticRegression(C=0.5, class_weight="balanced", max_iter=5000)
            ),
            "rf_key": make_pipeline(
                clone(sel),
                RandomForestClassifier(
                    n_estimators=400, min_samples_leaf=3, class_weight="balanced_subsample", random_state=0, n_jobs=-1
                ),
            ),
        }
    return {
        **extra,
        # На ~100 примерах меньше признаков = меньше переобучения: отдельные модели только на геометрии
        "logreg_geom": make_pipeline(
            clone(geom), StandardScaler(), LogisticRegression(C=0.1, class_weight="balanced", max_iter=5000)
        ),
        "rf_geom": make_pipeline(
            clone(geom),
            RandomForestClassifier(
                n_estimators=400,
                min_samples_leaf=2,
                max_features="sqrt",
                class_weight="balanced_subsample",
                random_state=0,
                n_jobs=-1,
            ),
        ),
        "logreg_l2": make_pipeline(StandardScaler(), LogisticRegression(C=0.1, class_weight="balanced", max_iter=5000)),
        "logreg_l1": make_pipeline(
            StandardScaler(), LogisticRegression(C=0.3, penalty="l1", solver="liblinear", class_weight="balanced")
        ),
        "random_forest": RandomForestClassifier(
            n_estimators=400,
            min_samples_leaf=2,
            max_features="sqrt",
            class_weight="balanced_subsample",
            random_state=0,
            n_jobs=-1,
        ),
        "extra_trees": ExtraTreesClassifier(
            n_estimators=400,
            min_samples_leaf=2,
            max_features="sqrt",
            class_weight="balanced_subsample",
            random_state=0,
            n_jobs=-1,
        ),
    }


def oof_predict(model, X, y, groups, repeats=5):
    """Out-of-fold вероятности, усреднённые по нескольким разбиениям (разбиение по исследованиям)."""
    n_splits = int(min(5, max(2, y.sum())))
    probs = np.zeros(len(y))
    for r in range(repeats):
        cv = StratifiedGroupKFold(n_splits=n_splits, shuffle=True, random_state=r)
        for tr, te in cv.split(X, y, groups):
            m = clone(model)
            m.fit(X[tr], y[tr])
            probs[te] += m.predict_proba(X[te])[:, 1]
    return probs / repeats


def best_threshold(y, p):
    grid = np.unique(np.round(p, 3))
    best = (0.5, -1.0)
    for t in grid:
        f = f1_score(y, p >= t, zero_division=0)
        if f > best[1]:
            best = (float(t), f)
    return best[0]


def metrics(y, p, thr):
    pred = p >= thr
    return {
        "roc_auc": round(float(roc_auc_score(y, p)), 3),
        "pr_auc": round(float(average_precision_score(y, p)), 3),
        "f1": round(float(f1_score(y, pred, zero_division=0)), 3),
        "precision": round(float(precision_score(y, pred, zero_division=0)), 3),
        "recall": round(float(recall_score(y, pred, zero_division=0)), 3),
        "balanced_accuracy": round(float(balanced_accuracy_score(y, pred)), 3),
        "positives": int(y.sum()),
        "n": int(len(y)),
        "threshold": round(thr, 3),
    }


def _ci(values: list[float]) -> list[float]:
    return [round(float(np.percentile(values, 2.5)), 3), round(float(np.percentile(values, 97.5)), 3)]


def bootstrap_ci(y, p, thr, groups, n_boot=1000, seed=42):
    """95% доверительные интервалы кластерным бутстрапом: пересэмплируем целые исследования,
    чтобы снимки одного пациента не завышали уверенность."""
    rng = np.random.default_rng(seed)
    uniq = np.unique(groups)
    by_group = {g: np.flatnonzero(groups == g) for g in uniq}
    pred = p >= thr
    stats: dict[str, list[float]] = {k: [] for k in ("roc_auc", "f1", "recall", "specificity", "balanced_accuracy")}
    for _ in range(n_boot):
        idx = np.concatenate([by_group[g] for g in rng.choice(uniq, size=len(uniq), replace=True)])
        yt, yp, pp = y[idx], pred[idx], p[idx]
        if yt.min() == yt.max():
            continue  # в выборку попал один класс — AUC не определён
        stats["roc_auc"].append(roc_auc_score(yt, pp))
        stats["f1"].append(f1_score(yt, yp, zero_division=0))
        stats["recall"].append(recall_score(yt, yp, zero_division=0))
        stats["specificity"].append(((yt == 0) & ~yp).sum() / max((yt == 0).sum(), 1))
        stats["balanced_accuracy"].append(balanced_accuracy_score(yt, yp))
    return {
        k: [round(float(np.percentile(v, 2.5)), 3), round(float(np.percentile(v, 97.5)), 3)] for k, v in stats.items()
    }


def train_target(name, df, ycol, feature_cols):
    d = df.dropna(subset=[ycol])
    X = d[feature_cols].to_numpy(dtype=np.float32)
    y = d[ycol].to_numpy().astype(int)
    groups = d["study"].to_numpy()
    results = {}
    for mname, model in candidates(feature_cols, name).items():
        p = oof_predict(model, X, y, groups)
        results[mname] = (roc_auc_score(y, p), p)
    best_name = max(results, key=lambda k: results[k][0])
    p = results[best_name][1]
    thr = best_threshold(y, p)
    final = clone(candidates(feature_cols, name)[best_name]).fit(X, y)
    report = metrics(y, p, thr)
    report["specificity"] = round(float(((y == 0) & (p < thr)).sum() / max((y == 0).sum(), 1)), 3)
    report["ci95"] = bootstrap_ci(y, p, thr, groups)
    report["model"] = best_name
    report["candidates_auc"] = {k: round(float(v[0]), 3) for k, v in results.items()}
    report["_oof"] = pd.Series(p, index=d.index)
    print(
        f"  {name:20s} best={best_name:13s} AUC={report['roc_auc']:.3f} F1={report['f1']:.3f} "
        f"R={report['recall']:.2f} P={report['precision']:.2f} pos={report['positives']}/{report['n']}"
    )
    return final, thr, report


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, required=True, help="папка с «Исследования» и разметка.xlsx")
    ap.add_argument("--test", type=Path, default=None, help="папка «Для теста» с подписанными снимками")
    args = ap.parse_args()

    xlsx = next(args.data.glob("*.xlsx"))
    labels = load_labels(xlsx)
    print(f"Разметка: {len(labels)} исследований")

    items, images = collect(args.data)
    print(f"Снимков: {len(images)}")

    region_model, regions = fit_region_model(images)
    print("Области:", pd.Series(regions).value_counts().to_dict())

    region_check = {}
    if args.test:
        tag = {"ПОП": "spine", "ППОБ": "right_hip", "ЛПОБ": "left_hip"}
        for f in sorted(args.test.rglob("*.dcm")):
            m = re.search(r"_(ПОП|ППОБ|ЛПОБ)", f.name)
            arr = read_dicom_pixels(f)
            if not m or arr is None:
                continue
            pred = region_model.predict([region_hog(arr)])[0]
            region_check[f.name] = {"expected": tag[m.group(1)], "predicted": pred}
            print(f"  тест {f.name}: {pred} (ожидалось {tag[m.group(1)]})")

    spine_df, hip_df = build_tables(items, images, regions, labels)
    print(f"Пары исследование-область: позвоночник {len(spine_df)}, бёдра {len(hip_df)}")

    spine_feats = [c for c in spine_df.columns if not c.startswith("y_") and c not in ("study",)]
    hip_feats = [c for c in hip_df.columns if not c.startswith("y_") and c not in ("study", "side")]

    bundle = {
        "version": datetime.now(UTC).strftime("%Y%m%d-%H%M"),
        "region_model": region_model,
        "spine_features": spine_feats,
        "hip_features": hip_feats,
        "targets": {},
    }
    report = {
        "trained_at": datetime.now(UTC).isoformat(),
        "n_images": len(images),
        "n_studies": int(labels.shape[0]),
        "region_test": region_check,
        "targets": {},
    }

    print("Обучение (кросс-валидация по исследованиям, 5 повторов):")
    oof: dict[str, tuple[pd.Series, float]] = {}
    for tname, (kind, ycol) in TARGETS.items():
        df, feats = (spine_df, spine_feats) if kind == "spine" else (hip_df, hip_feats)
        model, thr, rep = train_target(tname, df, f"y_{ycol}", feats)
        bundle["targets"][tname] = {"model": model, "threshold": thr, "kind": kind}
        oof[tname] = (rep.pop("_oof"), thr)
        report["targets"][tname] = rep

    # Итог по исследованию — ровно та же логика, что в инференсе (analyzer.py):
    # область «плохая», если любая модель области дала p >= порог * scale.
    # Исследование «качественное», если все его области хорошие.
    # Пороги подобраны по F1 для каждой проверки отдельно; при объединении через «ИЛИ» они
    # слишком строгие, поэтому подбираем общий множитель scale по сбалансированной точности.
    rows = []  # (study, true_bad, {target: (p, thr)})
    for kind, df in (("spine", spine_df), ("hip", hip_df)):
        tcol = "y_total_spine" if kind == "spine" else "y_total"
        kind_targets = [t for t, (k, _) in TARGETS.items() if k == kind]
        for idx in df.index:
            if pd.isna(df.loc[idx, tcol]):
                continue
            probs = {t: (oof[t][0][idx], oof[t][1]) for t in kind_targets if idx in oof[t][0].index}
            rows.append((df.loc[idx, "study"], int(df.loc[idx, tcol]), probs))

    def study_eval(scale: float):
        yt_d, yp_d = {}, {}
        for study, true_bad, probs in rows:
            bad = int(any(p >= min(0.99, thr * scale) for p, thr in probs.values()))
            yt_d[study] = max(yt_d.get(study, 0), true_bad)
            yp_d[study] = max(yp_d.get(study, 0), bad)
        yt = np.array(list(yt_d.values()))
        yp = np.array([yp_d[k] for k in yt_d])
        return yt, yp

    best_scale, best_ba = 1.0, -1.0
    for scale in np.round(np.arange(0.8, 2.01, 0.05), 2):
        yt, yp = study_eval(float(scale))
        ba = balanced_accuracy_score(yt, yp)
        if ba > best_ba + 1e-9:
            best_scale, best_ba = float(scale), ba
    bundle["threshold_scale"] = best_scale
    yt, yp = study_eval(best_scale)
    report["threshold_scale"] = best_scale
    report["study_level"] = {
        "n": int(len(yt)),
        "bad_studies": int(yt.sum()),
        "accuracy": round(float((yt == yp).mean()), 3),
        "recall_bad": round(float(recall_score(yt, yp)), 3),
        "precision_bad": round(float(precision_score(yt, yp, zero_division=0)), 3),
        "specificity": round(float(((yt == 0) & (yp == 0)).sum() / max((yt == 0).sum(), 1)), 3),
        "balanced_accuracy": round(float(balanced_accuracy_score(yt, yp)), 3),
        "f1": round(float(f1_score(yt, yp, zero_division=0)), 3),
    }
    # 95% ДИ по исследованиям (здесь одна строка = одно исследование, бутстрап обычный)
    rng = np.random.default_rng(42)
    boot: dict[str, list[float]] = {"recall_bad": [], "specificity": [], "balanced_accuracy": [], "f1": []}
    for _ in range(1000):
        i = rng.integers(0, len(yt), len(yt))
        a, b = yt[i], yp[i]
        if a.min() == a.max():
            continue
        boot["recall_bad"].append(recall_score(a, b))
        boot["specificity"].append(((a == 0) & (b == 0)).sum() / max((a == 0).sum(), 1))
        boot["balanced_accuracy"].append(balanced_accuracy_score(a, b))
        boot["f1"].append(f1_score(a, b, zero_division=0))
    report["study_level"]["ci95"] = {
        k: [round(float(np.percentile(v, 2.5)), 3), round(float(np.percentile(v, 97.5)), 3)] for k, v in boot.items()
    }
    print("  итог по исследованию:", report["study_level"])

    # Прозрачное правило для оси позвоночника: сам угол как оценка (без ML)
    d = spine_df.dropna(subset=["y_sp_axis"])
    rule_auc = roc_auc_score(d["y_sp_axis"].astype(int), d["sp_cl_abs_angle"])
    report["rule_spine_axis_angle_auc"] = round(float(rule_auc), 3)
    print(f"  правило «угол оси» без ML: AUC={rule_auc:.3f}")

    MODELS_DIR.mkdir(exist_ok=True)
    joblib.dump(bundle, MODELS_DIR / "dxa_quality.joblib", compress=3)
    (MODELS_DIR / "metrics.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), "utf-8")
    print(f"Сохранено: {MODELS_DIR / 'dxa_quality.joblib'}")


if __name__ == "__main__":
    main()
