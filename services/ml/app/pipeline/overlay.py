"""Превью снимка с наглядной разметкой: ось позвоночника, ось диафиза, найденные артефакты.

Врач и лаборант видят не только «модель сказала плохо», но и на что она смотрела.
"""

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from skimage.measure import label, regionprops
from skimage.morphology import disk, white_tophat
from skimage.transform import resize

OK = (46, 160, 120)
BAD = (226, 84, 60)
INFO = (90, 170, 230)


def _centerline_points(a: np.ndarray, y0: float, y1: float, x0: float, x1: float) -> list[tuple[float, float]]:
    h, w = a.shape
    pts = []
    for y in range(int(h * y0), int(h * y1), 2):
        row = a[y, int(w * x0) : int(w * x1)]
        if row.size == 0:
            continue
        thr = max(np.percentile(row, 70), 0.15)
        idx = np.nonzero(row > thr)[0]
        if idx.size < 3:
            continue
        wgt = row[idx]
        pts.append((int(w * x0) + float((idx * wgt).sum() / wgt.sum()), float(y)))
    return pts


def render(img: np.ndarray, region: str, bad: bool, out: Path, scale: int = 2) -> None:
    h, w = img.shape
    a = img.astype(np.float32) / 255.0
    base = Image.fromarray(img).convert("RGB").resize((w * scale, h * scale), Image.Resampling.LANCZOS)
    draw = ImageDraw.Draw(base, "RGBA")
    color = BAD if bad else OK

    if region == "spine":
        pts = _centerline_points(a, 0.06, 0.94, 0.2, 0.8)
    elif region in ("right_hip", "left_hip"):
        # диафиз — нижняя часть кадра; у левого бедра он справа
        x0, x1 = (0.0, 0.75) if region == "right_hip" else (0.25, 1.0)
        pts = _centerline_points(a, 0.6, 0.97, x0, x1)
    else:
        pts = []

    if len(pts) >= 6:
        ys = np.array([p[1] for p in pts])
        xs = np.array([p[0] for p in pts])
        k, b = np.polyfit(ys, xs, 1)
        yt, yb = ys.min(), ys.max()
        # фактическая средняя линия (тонко) и аппроксимирующая ось (толще)
        draw.line([(x * scale, y * scale) for x, y in pts], fill=(*INFO, 150), width=2)
        draw.line([((k * yt + b) * scale, yt * scale), ((k * yb + b) * scale, yb * scale)], fill=(*color, 230), width=3)
        # вертикаль для сравнения угла
        xm = (k * (yt + yb) / 2 + b) * scale
        draw.line([(xm, yt * scale), (xm, yb * scale)], fill=(255, 255, 255, 70), width=1)

    # тонкие яркие структуры вне кости — кандидаты в посторонние предметы
    th = white_tophat(resize(a, (256, 256), anti_aliasing=True), disk(3))
    lab = label(th > 0.10)
    sx, sy = w * scale / 256, h * scale / 256
    for p in regionprops(lab):
        if p.area >= 12 and p.axis_major_length >= 18 and p.eccentricity > 0.95:
            cx = p.centroid[1]
            if region == "spine" and 256 * 0.32 < cx < 256 * 0.68:
                continue
            r0, c0, r1, c1 = p.bbox
            draw.rectangle([c0 * sx - 3, r0 * sy - 3, c1 * sx + 3, r1 * sy + 3], outline=(*BAD, 200), width=2)

    out.parent.mkdir(parents=True, exist_ok=True)
    base.save(out, optimize=True)
