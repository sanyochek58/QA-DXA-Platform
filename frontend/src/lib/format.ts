import type { Region, ReviewStatus, Role } from "../api/types";

export const ROLE_LABEL: Record<Role, string> = {
  technologist: "Лаборант",
  radiologist: "Врач-рентгенолог",
  admin: "Заведующий",
};

export const REGION_LABEL: Record<Region, string> = {
  spine: "Поясничный отдел",
  right_hip: "Правое бедро",
  left_hip: "Левое бедро",
  unknown: "Не определено",
};

export const REGION_SHORT: Record<Region, string> = {
  spine: "Позвоночник",
  right_hip: "Бедро П",
  left_hip: "Бедро Л",
  unknown: "—",
};

export const CODE_LABEL: Record<string, string> = {
  SPINE_POSITIONING: "Укладка позвоночника",
  SPINE_AXIS: "Отклонение оси",
  SPINE_ARTIFACT: "Посторонние предметы",
  SPINE_OTHER: "Позвоночник: проверить",
  HIP_ROTATION: "Ротация бедра",
  HIP_ROI: "Область интересов бедра",
  HIP_OTHER: "Бедро: проверить",
};

export const REVIEW_LABEL: Record<ReviewStatus, string> = {
  not_required: "Не требуется",
  pending: "Ждёт врача",
  confirmed: "Врач подтвердил",
  corrected: "Врач исправил",
};

export const EVIDENCE_LABEL: Record<string, { label: string; unit?: string; digits?: number }> = {
  axis_angle_deg: { label: "Наклон средней линии", unit: "°", digits: 1 },
  axis_max_deviation: { label: "Макс. отклонение линии", digits: 3 },
  center_offset: { label: "Смещение от центра", digits: 3 },
  left_right_asymmetry: { label: "Асимметрия сторон", digits: 3 },
  foreign_lines: { label: "Посторонних линий", digits: 0 },
  foreign_lines_length: { label: "Их суммарная длина", digits: 2 },
  bright_spots: { label: "Ярких включений", digits: 0 },
  shaft_angle_deg: { label: "Наклон диафиза", unit: "°", digits: 1 },
  lesser_trochanter_signal: { label: "Сигнал малого вертела", digits: 3 },
  shaft_width: { label: "Ширина диафиза", digits: 3 },
  masked_area: { label: "Закрытая зона", digits: 3 },
};

const dt = new Intl.DateTimeFormat("ru-RU", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
const d = new Intl.DateTimeFormat("ru-RU", { day: "numeric", month: "short" });

export const fmtDateTime = (s: string) => dt.format(new Date(s));
export const fmtDay = (s: string) => d.format(new Date(s));
export const pct = (x: number, digits = 0) => `${(x * 100).toFixed(digits)}%`;

export function shortId(id: string) {
  return id.slice(0, 8).toUpperCase();
}

export function plural(n: number, one: string, few: string, many: string) {
  const m10 = n % 10;
  const m100 = n % 100;
  if (m10 === 1 && m100 !== 11) return one;
  if (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) return few;
  return many;
}
