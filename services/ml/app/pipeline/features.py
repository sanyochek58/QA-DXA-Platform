"""Признаки снимка DXA.

Идея «геометрия прежде ML»: сначала считаем измеримые, объяснимые величины
(угол оси позвоночника, угол диафиза бедра, яркие артефакты), а классификатор
уже решает по ним. Эти же числа показываем пользователю как доказательство.

Все функции принимают 2D-массив uint8/float (одно изображение) и ничего не знают о DICOM.
"""

from __future__ import annotations

import numpy as np
from skimage.feature import hog
from skimage.measure import label, regionprops
from skimage.morphology import disk, white_tophat
from skimage.transform import resize

SIZE = 128  # всё приводим к одному размеру, чтобы признаки были сравнимы


def normalize(img: np.ndarray) -> np.ndarray:
    """uint8 -> float [0, 1] фиксированного размера."""
    a = img.astype(np.float32)
    if a.max() > 1.5:
        a = a / 255.0
    return resize(a, (SIZE, SIZE), anti_aliasing=True, preserve_range=True).astype(np.float32)


def region_hog(img: np.ndarray) -> np.ndarray:
    """HOG для классификатора области (позвоночник / правое / левое бедро)."""
    a = resize(normalize(img), (64, 64), anti_aliasing=True)
    return hog(a, orientations=8, pixels_per_cell=(16, 16), cells_per_block=(1, 1))


def _intensity(a: np.ndarray) -> dict[str, float]:
    p = np.percentile(a, [5, 25, 50, 75, 95, 99])
    return {
        "int_mean": float(a.mean()),
        "int_std": float(a.std()),
        **{f"int_p{q}": float(v) for q, v in zip((5, 25, 50, 75, 95, 99), p, strict=True)},
        "dark_frac": float((a < 0.05).mean()),
    }


def _bright_blobs(raw: np.ndarray) -> dict[str, float]:
    """Металл, пуговицы, импланты: почти насыщенные компактные пятна ярче кости."""
    a = raw.astype(np.float32)
    if a.max() > 1.5:
        a = a / 255.0
    bone_level = np.percentile(a, 97)
    thr = max(0.92, bone_level + 0.05)
    mask = a >= thr
    lab = label(mask)
    props = [p for p in regionprops(lab) if p.area >= 6]
    areas = sorted((p.area for p in props), reverse=True)
    total = a.size
    ecc = [p.eccentricity for p in props[:5]] if props else [0.0]
    return {
        "blob_count": float(len(props)),
        "blob_max_area": float(areas[0] / total) if areas else 0.0,
        "blob_total_area": float(sum(areas) / total),
        "blob_mean_ecc": float(np.mean(ecc)),
        "sat_frac": float((a >= 0.98).mean()),
    }


def _masked_box(raw: np.ndarray) -> dict[str, float]:
    """Чёрный прямоугольник, которым аппарат закрывает часть поля (зона анализа)."""
    zero = raw <= 1
    lab = label(zero)
    props = sorted(regionprops(lab), key=lambda p: p.area, reverse=True)
    if not props or props[0].area < 0.01 * raw.size:
        return {"box_area": 0.0, "box_cy": 0.0, "box_cx": 0.0, "box_rect": 0.0}
    p = props[0]
    h, w = raw.shape
    return {
        "box_area": float(p.area / raw.size),
        "box_cy": float(p.centroid[0] / h),
        "box_cx": float(p.centroid[1] / w),
        "box_rect": float(p.extent),  # 1.0 = идеальный прямоугольник
    }


def _centerline(a: np.ndarray, rows: slice, band: tuple[float, float] = (0.0, 1.0)) -> dict[str, float]:
    """Средняя линия яркой структуры по строкам: для позвоночника или диафиза бедра.

    Для каждой строки берём центр масс пикселей ярче 70-го перцентиля строки,
    затем аппроксимируем линией x = k*y + b. Угол линии к вертикали — главный признак.
    """
    h, w = a.shape
    x0, x1 = int(band[0] * w), int(band[1] * w)
    ys, xs, widths = [], [], []
    for y in range(rows.start or 0, rows.stop or h):
        row = a[y, x0:x1]
        thr = np.percentile(row, 70)
        m = row > max(thr, 0.15)
        if m.sum() < 3:
            continue
        idx = np.nonzero(m)[0]
        wgt = row[idx]
        xs.append(x0 + float((idx * wgt).sum() / wgt.sum()))
        ys.append(float(y))
        widths.append(float(idx.max() - idx.min()))
    if len(ys) < 10:
        return {
            "cl_angle": 0.0,
            "cl_abs_angle": 0.0,
            "cl_resid": 0.0,
            "cl_curv": 0.0,
            "cl_offset": 0.0,
            "cl_width": 0.0,
            "cl_maxdev": 0.0,
        }
    y_arr, x_arr = np.array(ys), np.array(xs)
    k, b = np.polyfit(y_arr, x_arr, 1)
    resid = x_arr - (k * y_arr + b)
    quad = np.polyfit(y_arr / h, x_arr / w, 2)[0]
    angle = float(np.degrees(np.arctan(k)))
    return {
        "cl_angle": angle,
        "cl_abs_angle": abs(angle),
        "cl_resid": float(resid.std() / w),
        "cl_curv": float(quad),
        "cl_offset": float(np.mean(x_arr) / w - 0.5),
        "cl_width": float(np.median(widths) / w),
        "cl_maxdev": float(np.abs(resid).max() / w),
    }


def _thin_lines(raw: np.ndarray, exclude_center: float = 0.18) -> dict[str, float]:
    """Тонкие яркие линии: провода, косточки белья, швы, скобы.

    White top-hat убирает крупные структуры (кость) и оставляет узкие яркие детали.
    Затем ищем вытянутые компоненты — это и есть посторонние предметы.
    Центральную полосу (сам позвоночник) исключаем: в ней много «своих» контуров.
    """
    a = resize(normalize(raw), (256, 256), anti_aliasing=True)
    th = white_tophat(a, disk(3))
    mask = th > 0.10
    h, w = mask.shape
    cx0, cx1 = int(w * (0.5 - exclude_center)), int(w * (0.5 + exclude_center))
    lateral = mask.copy()
    lateral[:, cx0:cx1] = False
    lab = label(lateral)
    lengths, top_len, curvy = [], 0.0, 0
    for p in regionprops(lab):
        if p.area < 12:
            continue
        if p.axis_major_length >= 18 and p.eccentricity > 0.95:
            lengths.append(p.axis_major_length)
            if p.centroid[0] < h * 0.3:
                top_len += p.axis_major_length
            if p.solidity < 0.6:
                curvy += 1
    lengths.sort(reverse=True)
    return {
        "line_count": float(len(lengths)),
        "line_total_len": float(sum(lengths) / w),
        "line_max_len": float(lengths[0] / w) if lengths else 0.0,
        "line_top_len": float(top_len / w),
        "line_curvy": float(curvy),
        "tophat_lateral_energy": float(th[:, np.r_[0:cx0, cx1:w]].mean()),
        "tophat_top_energy": float(th[: int(h * 0.3)].mean()),
    }


def _femur_profile(raw_right: np.ndarray) -> dict[str, float]:
    """Контур бедра по строкам (снимок уже ориентирован как правое бедро: медиально = справа).

    Для каждой строки находим сегмент кости, в котором лежит диафиз, и его медиальный край.
    Малый вертел даёт выступ медиального края ниже шейки: чем он больше,
    тем сильнее бедро недоротировано внутрь. Это и есть главный признак ротации.
    """
    a = resize(normalize(raw_right), (256, 256), anti_aliasing=True)
    h, w = a.shape
    # фон почти чёрный, мягкие ткани ~0.1-0.2, кость ярче: порог от яркости кости, а не Otsu
    thr = max(0.18, 0.38 * float(np.percentile(a, 99)))
    bone = a > thr
    # диафиз ищем в нижних 15% кадра
    low = bone[int(h * 0.85) :]
    cols = low.sum(0)
    shaft_x = int(np.argmax(np.convolve(cols, np.ones(15) / 15, "same"))) if cols.any() else w // 2
    med, lat, width = [], [], []
    x = shaft_x
    for y in range(h - 1, int(h * 0.25), -1):
        row = bone[y]
        if not row[min(max(x, 0), w - 1)]:
            near = np.nonzero(row[max(0, x - 20) : min(w, x + 20)])[0]
            if near.size == 0:
                med.append(np.nan)
                lat.append(np.nan)
                width.append(np.nan)
                continue
            x = max(0, x - 20) + int(near[len(near) // 2])
        r = x
        while r + 1 < w and row[r + 1]:
            r += 1
        left = x
        while left - 1 >= 0 and row[left - 1]:
            left -= 1
        med.append(r)
        lat.append(left)
        width.append(r - left)
        x = (r + left) // 2
    med_a = np.array(med[::-1], dtype=float)  # сверху вниз, строки от 0.25h до низа
    wid_a = np.array(width[::-1], dtype=float)
    n = len(med_a)
    if n < 20 or np.isnan(med_a).all():
        return {k: 0.0 for k in ("lt_bump", "lt_bump_rel", "shaft_width", "width_ratio", "med_edge_std", "prox_width")}
    ys = np.arange(n)
    ok = ~np.isnan(med_a)
    # прямая по медиальному краю нижней части диафиза — «как было бы без вертела»
    lower = ok & (ys > n * 0.65)
    if lower.sum() > 5:
        k, b = np.polyfit(ys[lower], med_a[lower], 1)
    else:
        k, b = 0.0, float(np.nanmedian(med_a))
    base = k * ys + b
    zone = ok & (ys > n * 0.25) & (ys < n * 0.6)  # область малого вертела
    bump = float(np.nanmax(med_a[zone] - base[zone])) if zone.any() else 0.0
    shaft_w = float(np.nanmedian(wid_a[lower])) if lower.any() else 1.0
    prox_w = float(np.nanmax(wid_a[ok & (ys < n * 0.45)])) if (ok & (ys < n * 0.45)).any() else 0.0
    return {
        "lt_bump": bump / w,
        "lt_bump_rel": bump / max(shaft_w, 1.0),
        "shaft_width": shaft_w / w,
        "width_ratio": prox_w / max(shaft_w, 1.0),
        "med_edge_std": float(np.nanstd(med_a[ok & (ys > n * 0.65)]) / w) if lower.any() else 0.0,
        "prox_width": prox_w / w,
    }


def _hog_small(a: np.ndarray) -> dict[str, float]:
    h = hog(resize(a, (48, 48), anti_aliasing=True), orientations=6, pixels_per_cell=(12, 12), cells_per_block=(1, 1))
    return {f"hog{i}": float(v) for i, v in enumerate(h)}


def spine_features(raw: np.ndarray) -> dict[str, float]:
    a = normalize(raw)
    f: dict[str, float] = {}
    f.update(_intensity(a))
    f.update(_bright_blobs(raw))
    f.update(_masked_box(raw))
    f.update({f"sp_{k}": v for k, v in _centerline(a, slice(8, SIZE - 8), (0.2, 0.8)).items()})
    # отдельно верх и низ: сколиоз и наклон часто виден только в части кадра
    top = _centerline(a, slice(8, SIZE // 2), (0.2, 0.8))
    bot = _centerline(a, slice(SIZE // 2, SIZE - 8), (0.2, 0.8))
    f["sp_angle_diff"] = abs(top["cl_angle"] - bot["cl_angle"])
    f["sp_top_angle"] = top["cl_abs_angle"]
    f["sp_bot_angle"] = bot["cl_abs_angle"]
    # симметрия относительно центра: при повороте таза/смещении одна сторона ярче
    f["lr_asym"] = float(a[:, SIZE // 2 :].mean() - a[:, : SIZE // 2].mean())
    f["h_ratio"] = float(raw.shape[0] / raw.shape[1])
    f.update(_thin_lines(raw))
    f.update(_hog_small(a))
    return f


def hip_features(raw: np.ndarray, side: str) -> dict[str, float]:
    """side: 'right' | 'left'. Левое бедро зеркалим, чтобы обе стороны выглядели одинаково.

    После зеркалирования таз всегда справа вверху, диафиз — слева внизу (как правое бедро).
    Так данные двух сторон объединяются, и примеров для обучения вдвое больше.
    """
    img = raw if side == "right" else raw[:, ::-1]
    a = normalize(img)
    f: dict[str, float] = {}
    f.update(_intensity(a))
    f.update(_bright_blobs(img))
    f.update(_masked_box(img))
    shaft = _centerline(a, slice(int(SIZE * 0.6), SIZE - 4), (0.0, 0.75))
    f.update({f"shaft_{k}": v for k, v in shaft.items()})
    # малый вертел: медиальнее диафиза, чуть ниже шейки. Его видимость = маркер ротации.
    cx = int((0.5 + shaft["cl_offset"]) * SIZE)
    lt = a[int(SIZE * 0.45) : int(SIZE * 0.65), min(cx + 4, SIZE - 1) : min(cx + 30, SIZE)]
    f["lt_mean"] = float(lt.mean()) if lt.size else 0.0
    f["lt_p90"] = float(np.percentile(lt, 90)) if lt.size else 0.0
    neck = a[int(SIZE * 0.2) : int(SIZE * 0.45), int(SIZE * 0.35) : int(SIZE * 0.75)]
    f["neck_mean"] = float(neck.mean())
    f["neck_std"] = float(neck.std())
    f["top_right_mean"] = float(a[: SIZE // 3, SIZE // 2 :].mean())
    f["top_left_mean"] = float(a[: SIZE // 3, : SIZE // 2].mean())
    f["h_ratio"] = float(img.shape[0] / img.shape[1])
    f.update(_femur_profile(img))
    f.update(_thin_lines(img, exclude_center=0.0))
    f.update(_hog_small(a))
    return f
