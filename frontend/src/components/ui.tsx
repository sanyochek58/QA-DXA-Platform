import {
  CaretRight,
  CheckCircle,
  Clock,
  ProhibitInset,
  SpinnerGap,
  WarningCircle,
  XCircle,
} from "@phosphor-icons/react";
import type { ReactNode } from "react";
import type { ReviewStatus, StudyListItem } from "../api/types";
import { REVIEW_LABEL } from "../lib/format";

/* ---------- Единая плашка статуса ----------
   Везде одна форма: капсула 26px, иконка + подпись, фон — цвет статуса 10–12%.
   Цвет никогда не несёт смысл один: всегда есть иконка и текст. */

export type Tone = "ok" | "bad" | "warn" | "info" | "neutral";

const TONE: Record<Tone, string> = {
  ok: "bg-ok-soft text-ok",
  bad: "bg-bad-soft text-bad",
  warn: "bg-warn-soft text-warn",
  info: "bg-brand-soft text-brand-dark",
  neutral: "bg-fill text-ink-2",
};

const TONE_ICON: Record<Tone, ReactNode> = {
  ok: <CheckCircle size={15} weight="fill" />,
  bad: <XCircle size={15} weight="fill" />,
  warn: <WarningCircle size={15} weight="fill" />,
  info: <Clock size={15} weight="fill" />,
  neutral: null,
};

export function StatusPill({
  tone = "neutral",
  children,
  icon,
}: {
  tone?: Tone;
  children: ReactNode;
  icon?: ReactNode | false;
}) {
  const i = icon === false ? null : (icon ?? TONE_ICON[tone]);
  return (
    <span
      className={`inline-flex items-center gap-1 h-[26px] pl-2 pr-2.5 rounded-full text-[13px] font-semibold whitespace-nowrap ${TONE[tone]} ${i ? "" : "pl-2.5"}`}
    >
      {i}
      {children}
    </span>
  );
}

export function VerdictPill({ study }: { study: Pick<StudyListItem, "status" | "quality_ok"> }) {
  if (study.status === "processing")
    return (
      <StatusPill tone="info" icon={<SpinnerGap size={15} weight="bold" className="animate-spin" />}>
        Анализ
      </StatusPill>
    );
  if (study.status === "failed")
    return (
      <StatusPill tone="neutral" icon={<ProhibitInset size={15} weight="fill" />}>
        Ошибка
      </StatusPill>
    );
  return study.quality_ok ? (
    <StatusPill tone="ok">Качественное</StatusPill>
  ) : (
    <StatusPill tone="bad">Есть нарушения</StatusPill>
  );
}

export function ReviewPill({ status }: { status: ReviewStatus }) {
  if (status === "not_required") return null;
  const tone: Tone = status === "pending" ? "warn" : status === "confirmed" ? "ok" : "info";
  const icon = status === "pending" ? <Clock size={15} weight="fill" /> : undefined;
  return (
    <StatusPill tone={tone} icon={icon}>
      {REVIEW_LABEL[status]}
    </StatusPill>
  );
}

/* ---------- Каркас страниц ---------- */

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between mb-8">
      <div className="min-w-0">
        <h1 className="text-[30px] md:text-[34px] leading-[1.15] font-bold text-ink">{title}</h1>
        {subtitle && <p className="mt-1.5 text-[15px] text-muted max-w-[62ch]">{subtitle}</p>}
      </div>
      {actions && <div className="flex items-center gap-2 shrink-0">{actions}</div>}
    </div>
  );
}

export function Skeleton({ className = "" }: { className?: string }) {
  return <div className={`skeleton ${className}`} />;
}

export function EmptyState({ icon, title, text, action }: { icon: ReactNode; title: string; text: string; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center text-center py-16 px-6">
      <div className="text-faint mb-3">{icon}</div>
      <p className="text-[17px] font-semibold text-ink">{title}</p>
      <p className="mt-1 text-[15px] text-muted max-w-[42ch]">{text}</p>
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}

export function ErrorNote({ children }: { children: ReactNode }) {
  return (
    <div role="alert" className="flex gap-2 items-start rounded-xl bg-bad-soft text-bad text-[14px] px-3.5 py-2.5">
      <WarningCircle size={18} weight="fill" className="shrink-0 mt-px" />
      <span>{children}</span>
    </div>
  );
}

/** Строка сгруппированного списка (inset grouped) со стрелкой. */
export function ListRow({ children, onClick, chevron = true }: { children: ReactNode; onClick?: () => void; chevron?: boolean }) {
  // div с role=button, а не <button>: внутри строки бывают свои кнопки, а вложенные кнопки — невалидный HTML
  return (
    <div
      role={onClick ? "button" : undefined}
      tabIndex={onClick ? 0 : undefined}
      onClick={onClick}
      onKeyDown={onClick ? (e) => { if (e.target === e.currentTarget && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); onClick(); } } : undefined}
      className={`w-full text-left flex items-center gap-3 px-5 py-3.5 relative after:absolute after:bottom-0 after:left-5 after:right-0 after:h-px after:bg-line last:after:hidden ${
        onClick ? "cursor-pointer hover:bg-fill/60 active:bg-fill transition-colors" : ""
      }`}
    >
      <div className="flex-1 min-w-0">{children}</div>
      {onClick && chevron && <CaretRight size={16} weight="bold" className="text-line-strong shrink-0" />}
    </div>
  );
}

/** Вероятность нарушения: тонкая шкала с отметкой порога. */
export function ProbabilityBar({ value, threshold }: { value: number; threshold: number }) {
  const over = value >= threshold;
  return (
    <div className="flex items-center gap-3">
      <div className="relative h-1.5 flex-1 rounded-full bg-fill-2">
        <div
          className={`absolute inset-y-0 left-0 rounded-full ${over ? "bg-bad-fill" : "bg-ok-fill"}`}
          style={{ width: `${Math.round(value * 100)}%` }}
        />
        <div
          className="absolute -top-1 -bottom-1 w-0.5 rounded-full bg-ink/70"
          style={{ left: `${Math.round(threshold * 100)}%` }}
          title={`Порог ${Math.round(threshold * 100)}%`}
        />
      </div>
      <span className="text-[14px] tnum font-semibold text-ink w-11 text-right">{Math.round(value * 100)}%</span>
    </div>
  );
}

/** Инициалы в круге — аватар сотрудника. */
export function Avatar({ name, size = 36 }: { name: string; size?: number }) {
  const initials = name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase())
    .join("");
  return (
    <span
      className="shrink-0 rounded-full bg-fill-2 text-ink-2 font-semibold grid place-items-center"
      style={{ width: size, height: size, fontSize: size * 0.38 }}
      aria-hidden
    >
      {initials}
    </span>
  );
}
