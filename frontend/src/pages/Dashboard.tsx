import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../api/client";
import type { ModelInfo, Summary } from "../api/types";
import { Avatar, ErrorNote, ListRow, PageHeader, Skeleton, StatusPill } from "../components/ui";
import { CODE_LABEL, fmtDay, pct, plural } from "../lib/format";
import { Segmented } from "./Studies";

const PERIODS = [
  { key: "7", label: "Неделя" },
  { key: "30", label: "Месяц" },
  { key: "90", label: "Квартал" },
] as const;

const C = {
  quality: "#28a745",
  review: "#1565c0",
  agree: "#32ade6",
  bad: "#e5484d",
  grid: "#e5e5ea",
  axis: "#6e6e73",
};

/* ---------- Кольца ---------- */

interface RingData {
  key: string;
  label: string;
  value: number | null; // 0..1
  detail: string;
  color: string;
}

function Rings({ rings }: { rings: RingData[] }) {
  const size = 188;
  const stroke = 16;
  const gap = 3;
  // Кольца рисуются от 0 до значения один раз при появлении — главный «момент» экрана
  const [shown, setShown] = useState(false);
  useEffect(() => {
    const id = requestAnimationFrame(() => setShown(true));
    return () => cancelAnimationFrame(id);
  }, []);
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img"
      aria-label={rings.map((r) => `${r.label}: ${r.value === null ? "нет данных" : pct(r.value)}`).join("; ")}
      className="shrink-0 -rotate-90">
      {rings.map((r, i) => {
        const radius = size / 2 - stroke / 2 - i * (stroke + gap);
        const len = 2 * Math.PI * radius;
        const v = Math.min(1, Math.max(0, r.value ?? 0));
        return (
          <g key={r.key}>
            <circle cx={size / 2} cy={size / 2} r={radius} fill="none" stroke={r.color} strokeOpacity={0.16} strokeWidth={stroke} />
            <circle cx={size / 2} cy={size / 2} r={radius} fill="none" stroke={r.color} strokeWidth={stroke}
              strokeLinecap="round" strokeDasharray={len}
              strokeDashoffset={shown ? len * (1 - v) : len}
              className="ring-arc" style={{ transitionDelay: `${i * 120}ms`, opacity: v === 0 ? 0 : 1 }} />
          </g>
        );
      })}
    </svg>
  );
}

function RingsCard({ data }: { data: Summary }) {
  const toReview = data.reviewed + data.review_pending;
  const rings: RingData[] = [
    {
      key: "quality",
      label: "Качественные",
      value: data.done ? data.quality_ok / data.done : null,
      detail: `${data.quality_ok} из ${data.done} исследований`,
      color: C.quality,
    },
    {
      key: "review",
      label: "Разобрано врачом",
      value: toReview ? data.reviewed / toReview : null,
      detail: toReview ? `${data.reviewed} из ${toReview} сомнительных` : "сомнительных не было",
      color: C.review,
    },
    {
      key: "agree",
      label: "Врач согласен с системой",
      value: data.review_agreement,
      detail: data.reviewed ? `по ${data.reviewed} ${plural(data.reviewed, "решению", "решениям", "решениям")}` : "решений пока нет",
      color: C.agree,
    },
  ];
  return (
    <section className="card p-6 md:p-7 flex flex-col sm:flex-row items-center gap-7 md:gap-10">
      <Rings rings={rings} />
      <ul className="flex-1 w-full grid gap-5 md:grid-cols-3">
        {rings.map((r) => (
          <li key={r.key} className="flex items-start gap-3">
            <span className="mt-1.5 size-3 rounded-full shrink-0" style={{ background: r.color }} aria-hidden />
            <div className="min-w-0">
              <div className="text-[15px] text-ink-2">{r.label}</div>
              <div className="text-[28px] leading-tight font-bold tnum tracking-[-0.02em]">
                {r.value === null ? "—" : pct(r.value)}
              </div>
              <div className="text-[13px] text-muted">{r.detail}</div>
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}

/* ---------- Остальные блоки ---------- */

function ChartTooltip({ active, payload, label }: { active?: boolean; payload?: { dataKey: string; value: number }[]; label?: string }) {
  if (!active || !payload?.length) return null;
  const total = payload.find((p) => p.dataKey === "total")?.value ?? 0;
  const bad = payload.find((p) => p.dataKey === "bad")?.value ?? 0;
  return (
    <div className="rounded-xl bg-surface px-3 py-2 text-[13px] shadow-[0_4px_16px_rgba(0,0,0,0.12)]">
      <div className="font-semibold mb-1">{label && fmtDay(label)}</div>
      <div className="flex items-center gap-2"><span className="size-2 rounded-full" style={{ background: C.review }} />Всего: <b className="tnum">{total}</b></div>
      <div className="flex items-center gap-2"><span className="size-2 rounded-full" style={{ background: C.bad }} />С нарушениями: <b className="tnum">{bad}</b></div>
    </div>
  );
}

function ByDay({ data }: { data: Summary }) {
  return (
    <section className="card p-6">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-[17px] font-semibold">По дням</h2>
        <div className="flex gap-4 text-[13px] text-ink-2">
          <span className="flex items-center gap-1.5"><span className="size-2.5 rounded-[3px]" style={{ background: C.review }} />Всего</span>
          <span className="flex items-center gap-1.5"><span className="size-2.5 rounded-[3px]" style={{ background: C.bad }} />С нарушениями</span>
        </div>
      </div>
      <div className="h-60 mt-5">
        {data.by_day.length ? (
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data.by_day} margin={{ left: -24, right: 4, top: 4 }} barGap={2} maxBarSize={24}>
              <CartesianGrid stroke={C.grid} vertical={false} />
              <XAxis dataKey="day" tickFormatter={fmtDay} tick={{ fontSize: 12, fill: C.axis }} tickLine={false} axisLine={false} minTickGap={16} />
              <YAxis allowDecimals={false} tick={{ fontSize: 12, fill: C.axis }} tickLine={false} axisLine={false} />
              <Tooltip content={<ChartTooltip />} cursor={{ fill: "#f2f2f7" }} />
              <Bar dataKey="total" fill={C.review} radius={[4, 4, 0, 0]} />
              <Bar dataKey="bad" fill={C.bad} radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        ) : (
          <div className="h-full grid place-items-center text-[15px] text-muted">За период исследований нет</div>
        )}
      </div>
    </section>
  );
}

function TopViolations({ data }: { data: Summary }) {
  const max = Math.max(1, ...data.by_code.map((c) => c.count));
  return (
    <section className="card p-6">
      <h2 className="text-[17px] font-semibold">Частые нарушения</h2>
      <ul className="mt-4 flex flex-col gap-3.5">
        {data.by_code.length ? (
          data.by_code.map((c) => (
            <li key={c.code}>
              <Link to={`/studies`} className="block">
                <div className="flex justify-between gap-3 text-[15px]">
                  <span className="truncate">{CODE_LABEL[c.code] ?? c.code}</span>
                  <span className="tnum font-semibold">{c.count}</span>
                </div>
                <div className="mt-1.5 h-1.5 rounded-full bg-fill-2">
                  <div className="h-full rounded-full bg-brand" style={{ width: `${(c.count / max) * 100}%` }} />
                </div>
              </Link>
            </li>
          ))
        ) : (
          <li className="text-[15px] text-muted">Нарушений за период нет</li>
        )}
      </ul>
    </section>
  );
}

function Operators({ data }: { data: Summary }) {
  return (
    <section>
      <h2 className="section-title">Лаборанты</h2>
      <div className="card overflow-hidden">
        {data.by_operator.length ? (
          data.by_operator.map((o) => (
            <ListRow key={o.user_id}>
              <div className="flex items-center gap-3">
                <Avatar name={o.full_name} />
                <div className="flex-1 min-w-0">
                  <div className="text-[15px] font-semibold truncate">{o.full_name}</div>
                  <div className="text-[13px] text-muted">
                    {o.total} {plural(o.total, "исследование", "исследования", "исследований")}, с нарушениями {o.bad}
                  </div>
                </div>
                {o.bad_rate > 0.4 && <span className="hidden sm:inline-flex"><StatusPill tone="warn">Нужен разбор укладки</StatusPill></span>}
                <div className="w-16 text-right">
                  <div className="text-[17px] font-bold tnum">{pct(o.bad_rate)}</div>
                  <div className="text-[12px] text-muted">нарушений</div>
                </div>
              </div>
            </ListRow>
          ))
        ) : (
          <div className="px-5 py-4 text-[15px] text-muted">Нет данных за период</div>
        )}
      </div>
    </section>
  );
}

const TARGET_LABEL: Record<string, string> = {
  spine_positioning: "Укладка позвоночника",
  spine_axis: "Ось позвоночника",
  spine_artifact: "Посторонние предметы",
  spine_total: "Позвоночник, итог",
  hip_rotation: "Ротация бедра",
  hip_roi: "Область интересов бедра",
  hip_total: "Бедро, итог",
};

function ModelQuality() {
  const { data } = useQuery({ queryKey: ["model"], queryFn: () => api<ModelInfo>("/system/model"), staleTime: 300_000 });
  const m = data?.metrics;
  if (!m) return null;
  return (
    <section>
      <h2 className="section-title">Точность проверки</h2>
      <p className="text-[15px] text-muted -mt-2 mb-3 px-1 max-w-[70ch]">
        Кросс-валидация на данных организаторов: {m.n_studies} исследований, {m.n_images} снимков.
        {m.study_level && ` По исследованию целиком система находит ${pct(m.study_level.recall_bad)} некачественных.`}
      </p>
      <div className="card overflow-x-auto">
        <table className="w-full min-w-[560px] border-separate border-spacing-0">
          <thead>
            <tr>
              <th className="th">Проверка</th>
              <th className="th text-right">ROC-AUC</th>
              <th className="th text-right">Полнота</th>
              <th className="th text-right">Точность</th>
              <th className="th text-right">С нарушением</th>
            </tr>
          </thead>
          <tbody className="[&>tr:last-child>td]:border-0">
            {Object.entries(m.targets).map(([k, t]) => (
              <tr key={k}>
                <td className="td">{TARGET_LABEL[k] ?? k}</td>
                <td className="td text-right tnum font-semibold">{t.roc_auc.toFixed(2)}</td>
                <td className="td text-right tnum">{pct(t.recall)}</td>
                <td className="td text-right tnum">{pct(t.precision)}</td>
                <td className="td text-right tnum text-muted">{t.positives} из {t.n}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export function Dashboard() {
  const navigate = useNavigate();
  const [days, setDays] = useState<"7" | "30" | "90">("30");
  const { data, isPending, error } = useQuery({
    queryKey: ["summary", days],
    queryFn: () => api<Summary>(`/stats/summary?days=${days}`),
    refetchInterval: 30_000,
  });

  return (
    <>
      <PageHeader
        title="Сводка"
        subtitle={data ? `${data.total} ${plural(data.total, "исследование", "исследования", "исследований")} за период` : undefined}
        actions={<Segmented value={days} options={[...PERIODS]} onChange={setDays} />}
      />
      {error && <ErrorNote>{(error as Error).message}</ErrorNote>}
      {isPending || !data ? (
        <div className="grid gap-5">
          <Skeleton className="h-60 rounded-[18px]" />
          <Skeleton className="h-72 rounded-[18px]" />
        </div>
      ) : (
        <div className="flex flex-col gap-10">
          <div className="flex flex-col gap-5">
            <RingsCard data={data} />
            <div className="card overflow-hidden">
              <ListRow onClick={() => navigate("/studies")}>
                <div className="flex items-center justify-between gap-3">
                  <span className="text-[15px]">С нарушениями</span>
                  <span className="text-[15px] text-muted tnum">{data.quality_bad} · {pct(data.bad_rate)}</span>
                </div>
              </ListRow>
              <ListRow onClick={() => navigate("/queue")}>
                <div className="flex items-center justify-between gap-3">
                  <span className="text-[15px]">Ждут решения врача</span>
                  <span className="text-[15px] text-muted tnum">{data.review_pending}</span>
                </div>
              </ListRow>
            </div>
          </div>
          <div className="grid gap-5 lg:grid-cols-[1.6fr_1fr]">
            <ByDay data={data} />
            <TopViolations data={data} />
          </div>
          <Operators data={data} />
          <ModelQuality />
        </div>
      )}
    </>
  );
}
