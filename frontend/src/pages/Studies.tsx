import { CaretDown, Files } from "@phosphor-icons/react";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import type { StudyListItem, StudyPage } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { EmptyState, ErrorNote, ListRow, PageHeader, ReviewPill, Skeleton, StatusPill, VerdictPill } from "../components/ui";
import { CODE_LABEL, fmtDateTime, plural, shortId } from "../lib/format";

type Filter = "all" | "bad" | "ok" | "pending";

const FILTERS: { key: Filter; label: string; short: string; query: string }[] = [
  { key: "all", label: "Все", short: "Все", query: "" },
  { key: "bad", label: "С нарушениями", short: "Нарушения", query: "&quality_ok=false" },
  { key: "ok", label: "Качественные", short: "Норма", query: "&quality_ok=true" },
  { key: "pending", label: "Ждут врача", short: "Врачу", query: "&review_status=pending" },
];

/** Сегментированный переключатель в стиле iOS. */
export function Segmented<T extends string>({
  value,
  options,
  onChange,
}: {
  value: T;
  options: { key: T; label: string; short?: string }[];
  onChange: (v: T) => void;
}) {
  return (
    <div className="flex p-0.5 rounded-[10px] bg-fill-2 w-full sm:w-fit overflow-x-auto" role="tablist">
      {options.map((o) => (
        <button
          key={o.key}
          role="tab"
          aria-selected={value === o.key}
          onClick={() => onChange(o.key)}
          className={`flex-1 sm:flex-none h-8 px-3.5 rounded-[8px] text-[13px] whitespace-nowrap transition-all duration-200 ${
            value === o.key ? "bg-surface text-ink font-semibold shadow-[0_1px_3px_rgba(0,0,0,0.12)]" : "text-ink-2 hover:text-ink"
          }`}
        >
          {o.short ? (
            <>
              <span className="sm:hidden">{o.short}</span>
              <span className="hidden sm:inline">{o.label}</span>
            </>
          ) : (
            o.label
          )}
        </button>
      ))}
    </div>
  );
}

export function StudyList({ items, showOperator }: { items: StudyListItem[]; showOperator: boolean }) {
  const navigate = useNavigate();
  return (
    <div className="card overflow-hidden">
      {items.map((s) => (
        <ListRow key={s.id} onClick={() => navigate(`/studies/${s.id}`)}>
          <div className="flex flex-col md:flex-row md:items-center gap-2 md:gap-4">
            <div className="flex-1 min-w-0">
              <div className="text-[15px] font-semibold truncate">{s.title ?? `Исследование ${shortId(s.id)}`}</div>
              <div className="text-[13px] text-muted mt-0.5 truncate">
                {fmtDateTime(s.created_at)}
                {showOperator && ` · ${s.uploaded_by.full_name}`}
                {` · ${s.n_images} ${plural(s.n_images, "снимок", "снимка", "снимков")}`}
              </div>
              {s.violation_codes.length > 0 && (
                <div className="flex flex-wrap gap-1.5 mt-2">
                  {s.violation_codes.map((c) => (
                    <StatusPill key={c} tone="neutral">{CODE_LABEL[c] ?? c}</StatusPill>
                  ))}
                </div>
              )}
            </div>
            <div className="flex flex-wrap md:flex-nowrap gap-1.5 md:justify-end md:w-[310px] shrink-0">
              <VerdictPill study={s} />
              <ReviewPill status={s.review_status} />
            </div>
          </div>
        </ListRow>
      ))}
    </div>
  );
}

export function ListSkeleton() {
  return (
    <div className="card p-5 flex flex-col gap-4">
      {Array.from({ length: 6 }).map((_, i) => (
        <div key={i} className="flex flex-col gap-2">
          <Skeleton className="h-4 w-1/3" />
          <Skeleton className="h-3 w-1/2" />
        </div>
      ))}
    </div>
  );
}

export function Studies() {
  const { user } = useAuth();
  const [filter, setFilter] = useState<Filter>("all");
  const [code, setCode] = useState("");
  const q = FILTERS.find((f) => f.key === filter)!.query + (code ? `&code=${code}` : "");
  const { data, isPending, error } = useQuery({
    queryKey: ["studies", q],
    queryFn: () => api<StudyPage>(`/studies?limit=200${q}`),
    refetchInterval: (query) => (query.state.data?.items.some((s) => s.status === "processing") ? 3000 : false),
  });

  const isTech = user?.role === "technologist";

  return (
    <>
      <PageHeader
        title={isTech ? "Мои исследования" : "Исследования"}
        subtitle={data ? `${data.total} ${plural(data.total, "исследование", "исследования", "исследований")}` : undefined}
        actions={<Link to="/upload" className="btn-primary">Загрузить</Link>}
      />
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-4">
        <Segmented value={filter} options={FILTERS} onChange={setFilter} />
        <label className="relative w-full sm:w-60">
          <span className="sr-only">Тип нарушения</span>
          <select value={code} onChange={(e) => setCode(e.target.value)}
            className="w-full h-9 pl-4 pr-9 rounded-full bg-surface text-[14px] font-medium text-ink appearance-none focus:outline-none">
            <option value="">Любое нарушение</option>
            {Object.entries(CODE_LABEL).map(([k, v]) => (
              <option key={k} value={k}>{v}</option>
            ))}
          </select>
          <CaretDown size={14} weight="bold" className="absolute right-3.5 top-1/2 -translate-y-1/2 text-muted pointer-events-none" />
        </label>
      </div>
      {error && <div className="mb-4"><ErrorNote>{(error as Error).message}</ErrorNote></div>}
      {isPending ? (
        <ListSkeleton />
      ) : data && data.items.length ? (
        <StudyList items={data.items} showOperator={!isTech} />
      ) : (
        <div className="card">
          <EmptyState icon={<Files size={40} />} title="Ничего не найдено"
            text={filter === "all" && !code ? "Загрузите первое исследование, и оно появится здесь." : "Под выбранные условия исследований нет."}
            action={filter === "all" && !code ? <Link to="/upload" className="btn-primary">Загрузить исследование</Link> : undefined} />
        </div>
      )}
    </>
  );
}
