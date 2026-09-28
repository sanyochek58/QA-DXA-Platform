import { ArrowClockwise, CaretLeft, CheckCircle, SpinnerGap, XCircle } from "@phosphor-icons/react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, ApiError, fetchImage } from "../api/client";
import type { ImageResult, Region, Study, Violation } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { ErrorNote, ProbabilityBar, ReviewPill, Skeleton, StatusPill } from "../components/ui";
import { EVIDENCE_LABEL, fmtDateTime, plural, REGION_LABEL, REGION_SHORT, shortId } from "../lib/format";

function useImage(studyId: string, index: number | null, enabled: boolean) {
  const { data } = useQuery({
    queryKey: ["img", studyId, index],
    queryFn: () => fetchImage(`/studies/${studyId}/images/${index}`),
    enabled: enabled && index !== null,
    staleTime: Infinity,
    gcTime: 5 * 60_000,
  });
  return data;
}

function Thumb({ study, img, active, bad, onClick }: {
  study: Study; img: ImageResult; active: boolean; bad: boolean; onClick: () => void;
}) {
  const src = useImage(study.id, img.index, !!img.preview_path);
  return (
    <button onClick={onClick} aria-label={`Снимок ${img.index + 1}: ${REGION_LABEL[img.region]}${bad ? ", есть нарушения" : ""}`} aria-pressed={active}
      className="shrink-0 w-[88px] text-left group">
      <div className={`aspect-square rounded-xl overflow-hidden bg-black ring-2 transition-all duration-150 ${
        active ? "ring-white" : "ring-transparent opacity-60 group-hover:opacity-90"}`}>
        {src && <img src={src} alt="" className="w-full h-full object-cover" />}
      </div>
      <div className={`mt-1.5 flex items-center gap-1 text-[12px] ${active ? "text-white" : "text-white/60"}`}>
        {bad ? <XCircle size={13} weight="fill" className="text-bad-fill shrink-0" /> : <CheckCircle size={13} weight="fill" className="text-ok-fill shrink-0" />}
        <span className="truncate">{REGION_SHORT[img.region]}</span>
      </div>
    </button>
  );
}

function Viewer({ study }: { study: Study }) {
  const images = study.result?.images ?? [];
  const badRegions = new Set(study.result?.regions.filter((r) => !r.quality_ok).map((r) => r.region) ?? []);
  const firstBad = images.find((i) => badRegions.has(i.region));
  const [active, setActive] = useState<number>(firstBad?.index ?? images[0]?.index ?? 0);
  const current = images.find((i) => i.index === active);
  const src = useImage(study.id, current?.index ?? null, !!current?.preview_path);

  const ordered = useMemo(() => {
    const order: Region[] = ["spine", "right_hip", "left_hip", "unknown"];
    return order.flatMap((r) => images.filter((i) => i.region === r));
  }, [images]);

  if (!images.length) return null;

  return (
    <section className="rounded-[var(--radius-card)] bg-viewer text-white overflow-hidden min-w-0">
      <div className="flex items-baseline justify-between gap-2 px-5 pt-4 pb-3">
        <h2 className="text-[17px] font-semibold">{current ? REGION_LABEL[current.region] : "Снимки"}</h2>
        <span className="text-[13px] text-white/60 tnum">{ordered.findIndex((i) => i.index === active) + 1} из {images.length}</span>
      </div>
      <div className="grid place-items-center min-h-[320px] md:min-h-[440px] bg-black">
        {src ? (
          <img key={src} src={src} alt={current ? REGION_LABEL[current.region] : ""} className="fade-in max-h-[520px] max-w-full w-auto object-contain" />
        ) : (
          <SpinnerGap size={26} className="animate-spin text-white/50" />
        )}
      </div>
      <div className="px-5 pt-3 flex flex-wrap gap-x-4 gap-y-1 text-[12px] text-white/70">
        <span className="flex items-center gap-1.5"><span className="w-4 h-0.5 rounded bg-[#5aaae6]" /> средняя линия</span>
        <span className="flex items-center gap-1.5"><span className="w-4 h-[3px] rounded bg-[#2ea078]" /> ось в норме</span>
        <span className="flex items-center gap-1.5"><span className="w-4 h-[3px] rounded bg-[#e2543c]" /> ось с нарушением</span>
        <span className="flex items-center gap-1.5"><span className="size-3 rounded-[3px] border-2 border-[#e2543c]" /> посторонний объект</span>
      </div>
      <div className="p-5 flex gap-3 overflow-x-auto">
        {ordered.map((img) => (
          <Thumb key={img.index} study={study} img={img} active={img.index === active}
            bad={badRegions.has(img.region)} onClick={() => setActive(img.index)} />
        ))}
      </div>
    </section>
  );
}

function ViolationCard({ v }: { v: Violation }) {
  const ev = Object.entries(v.evidence);
  return (
    <article className="card p-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-[13px] text-muted">{REGION_LABEL[v.region]}</span>
        {v.severity === "critical" ? <StatusPill tone="bad">Нужна пересъёмка</StatusPill> : <StatusPill tone="warn">Нужна проверка</StatusPill>}
      </div>
      <h3 className="mt-1.5 text-[19px] font-semibold leading-snug">{v.title_ru}</h3>
      <p className="mt-1.5 text-[15px] text-ink-2 leading-relaxed">{v.message_ru}</p>

      <div className="mt-4">
        <div className="text-[13px] text-muted mb-1.5">Вероятность нарушения · черта — порог</div>
        <ProbabilityBar value={v.probability} threshold={v.threshold} />
      </div>

      {ev.length > 0 && (
        <dl className="mt-4 rounded-xl bg-fill px-4">
          {ev.map(([k, val]) => {
            const meta = EVIDENCE_LABEL[k] ?? { label: k, digits: 3 };
            return (
              <div key={k} className="flex justify-between gap-3 py-2.5 border-b border-line last:border-0 text-[14px]">
                <dt className="text-ink-2">{meta.label}</dt>
                <dd className="font-semibold tnum">{val.toFixed(meta.digits ?? 2)}{meta.unit ?? ""}</dd>
              </div>
            );
          })}
        </dl>
      )}

      <div className="mt-4 rounded-xl bg-brand-soft px-4 py-3">
        <div className="text-[13px] font-semibold text-brand-dark">Как исправить</div>
        <p className="mt-0.5 text-[15px] text-ink leading-relaxed">{v.how_to_fix_ru}</p>
      </div>
    </article>
  );
}

function ReviewPanel({ study }: { study: Study }) {
  const qc = useQueryClient();
  const [comment, setComment] = useState("");
  const [error, setError] = useState<string | null>(null);
  const mutation = useMutation({
    mutationFn: (quality_ok: boolean) =>
      api<Study>(`/studies/${study.id}/review`, { method: "POST", body: JSON.stringify({ quality_ok, comment: comment || null }) }),
    onSuccess: (s) => {
      qc.setQueryData(["study", study.id], s);
      qc.invalidateQueries({ queryKey: ["queue"] });
      qc.invalidateQueries({ queryKey: ["queue-count"] });
      qc.invalidateQueries({ queryKey: ["studies"] });
    },
    onError: (e) => setError(e instanceof ApiError ? e.message : "Не удалось сохранить решение"),
  });

  if (study.review_status === "confirmed" || study.review_status === "corrected") {
    return (
      <section className="card p-5">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 className="text-[17px] font-semibold">Заключение врача</h3>
          <ReviewPill status={study.review_status} />
        </div>
        <p className="mt-2 text-[15px]">
          {study.review_quality_ok ? "Исследование выполнено качественно." : "Исследование выполнено с нарушениями."}
        </p>
        {study.review_comment && <p className="mt-1 text-[15px] text-ink-2">«{study.review_comment}»</p>}
        <p className="mt-2 text-[13px] text-muted">
          {study.reviewed_by?.full_name}, {study.reviewed_at && fmtDateTime(study.reviewed_at)}
        </p>
      </section>
    );
  }

  return (
    <section className="card p-5">
      <h3 className="text-[17px] font-semibold">Заключение врача</h3>
      <p className="mt-0.5 text-[13px] text-muted">Ваше решение становится итоговым.</p>
      <label className="sr-only" htmlFor="comment">Комментарий</label>
      <textarea id="comment" rows={2} maxLength={2000} value={comment} onChange={(e) => setComment(e.target.value)}
        className="input h-auto py-3 mt-4 resize-y" placeholder="Комментарий, например: сколиоз, разметка L1–L4 корректна" />
      {error && <div className="mt-3"><ErrorNote>{error}</ErrorNote></div>}
      <div className="mt-4 grid grid-cols-1 sm:grid-cols-2 gap-2">
        <button className="btn-plain text-ok" disabled={mutation.isPending} onClick={() => mutation.mutate(true)}>
          <CheckCircle size={20} weight="fill" /> Качество в норме
        </button>
        <button className="btn-plain text-bad" disabled={mutation.isPending} onClick={() => mutation.mutate(false)}>
          <XCircle size={20} weight="fill" /> Есть нарушения
        </button>
      </div>
    </section>
  );
}

function Verdict({ study }: { study: Study }) {
  if (study.status === "processing")
    return (
      <section className="card p-5 flex items-center gap-4">
        <SpinnerGap size={30} className="animate-spin text-brand shrink-0" />
        <div>
          <p className="text-[17px] font-semibold">Идёт проверка</p>
          <p className="text-[15px] text-muted">Результат появится здесь сам, обычно через несколько секунд.</p>
        </div>
      </section>
    );
  if (study.status === "failed")
    return (
      <section className="card p-5">
        <p className="text-[17px] font-semibold">Проверка не выполнена</p>
        <p className="mt-1 text-[15px] text-ink-2">{study.error}</p>
        <p className="mt-2 text-[13px] text-muted">Повторите проверку позже. Если ошибка повторяется, обратитесь к администратору.</p>
      </section>
    );
  const n = study.result?.violations.length ?? 0;
  const ok = study.quality_ok;
  return (
    <section className="card p-5 flex flex-col md:flex-row md:items-center gap-4">
      {ok ? <CheckCircle size={44} weight="fill" className="text-ok-fill shrink-0" /> : <XCircle size={44} weight="fill" className="text-bad-fill shrink-0" />}
      <div className="flex-1">
        <p className="text-[20px] font-bold leading-tight">
          {ok ? "Выполнено качественно" : `${n} ${plural(n, "нарушение", "нарушения", "нарушений")}`}
        </p>
        <p className="text-[15px] text-muted mt-0.5">
          {ok ? "Можно передавать врачу на описание." : "Посмотрите рекомендации и при необходимости повторите сканирование."}
        </p>
      </div>
      <div className="flex flex-wrap gap-1.5">
        {study.result?.regions.map((r) => (
          <StatusPill key={r.region} tone={r.quality_ok ? "ok" : "bad"}>{REGION_SHORT[r.region]}</StatusPill>
        ))}
      </div>
    </section>
  );
}

export function StudyDetail() {
  const { id = "" } = useParams();
  const { can } = useAuth();
  const qc = useQueryClient();
  const { data: study, isPending, error } = useQuery({
    queryKey: ["study", id],
    queryFn: () => api<Study>(`/studies/${id}`),
    refetchInterval: (q) => (q.state.data?.status === "processing" ? 1500 : false),
  });

  useEffect(() => {
    if (study?.status === "done") qc.invalidateQueries({ queryKey: ["queue-count"] });
  }, [study?.status, qc]);

  const reanalyze = useMutation({
    mutationFn: () => api<Study>(`/studies/${id}/reanalyze`, { method: "POST" }),
    onSuccess: (s) => qc.setQueryData(["study", id], s),
  });

  if (error) return <ErrorNote>{(error as Error).message}</ErrorNote>;
  if (isPending || !study)
    return (
      <div className="flex flex-col gap-4">
        <Skeleton className="h-9 w-72" />
        <Skeleton className="h-24 rounded-[18px]" />
        <div className="grid lg:grid-cols-[1.25fr_1fr] gap-5">
          <Skeleton className="h-[480px] rounded-[18px]" />
          <Skeleton className="h-[480px] rounded-[18px]" />
        </div>
      </div>
    );

  const res = study.result;
  const violations = res?.violations ?? [];

  return (
    <>
      <Link to="/studies" className="inline-flex items-center gap-0.5 -ml-1.5 mb-3 h-8 pr-2 text-[15px] text-brand rounded-full hover:bg-brand-soft">
        <CaretLeft size={18} weight="bold" /> Исследования
      </Link>
      <div className="flex flex-col md:flex-row md:items-end md:justify-between gap-4 mb-6">
        <div className="min-w-0">
          <h1 className="text-[28px] md:text-[34px] leading-[1.15] font-bold">{study.title ?? `Исследование ${shortId(study.id)}`}</h1>
          <p className="mt-1.5 text-[15px] text-muted">
            {fmtDateTime(study.created_at)} · {study.uploaded_by.full_name} · {study.n_images} {plural(study.n_images, "снимок", "снимка", "снимков")}
          </p>
        </div>
        {study.status !== "processing" && (
          <button className="btn-secondary shrink-0" onClick={() => reanalyze.mutate()} disabled={reanalyze.isPending}>
            <ArrowClockwise size={18} weight="bold" /> Проверить заново
          </button>
        )}
      </div>

      <Verdict study={study} />

      {study.status === "done" && res && (
        <div className="mt-5 grid gap-5 lg:grid-cols-[1.25fr_1fr] items-start [&>*]:min-w-0">
          <div className="lg:sticky lg:top-8">
            <Viewer study={study} />
          </div>

          <div className="flex flex-col gap-5">
            {res.needs_review && res.review_reasons.length > 0 && (
              <section className="card p-5">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <h3 className="text-[17px] font-semibold">Передано врачу</h3>
                  <ReviewPill status={study.review_status} />
                </div>
                <ul className="mt-2 flex flex-col gap-1.5 text-[14px] text-ink-2">
                  {res.review_reasons.slice(0, 5).map((r) => (
                    <li key={r} className="flex gap-2"><span className="mt-2 size-1 rounded-full bg-faint shrink-0" />{r}</li>
                  ))}
                </ul>
              </section>
            )}

            {violations.map((v) => <ViolationCard key={`${v.code}-${v.region}`} v={v} />)}

            {violations.length === 0 && (
              <section className="card p-5 text-[15px] text-ink-2">
                Укладка, ось и ротация в норме, посторонних предметов нет.
              </section>
            )}

            {can("radiologist", "admin") && (study.review_status !== "not_required" || !study.quality_ok) && <ReviewPanel study={study} />}
          </div>
        </div>
      )}
    </>
  );
}
