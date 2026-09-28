import { IdentificationCard, Plus, X } from "@phosphor-icons/react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { api, ApiError } from "../api/client";
import type { Role, User } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { Avatar, ErrorNote, ListRow, PageHeader, StatusPill } from "../components/ui";
import { fmtDateTime, ROLE_LABEL } from "../lib/format";
import { ListSkeleton } from "./Studies";

/** 11 цифр → «123-456-789 01» по мере ввода. */
function formatSnilsInput(raw: string) {
  const d = raw.replace(/\D/g, "").slice(0, 11);
  let out = d.slice(0, 3);
  if (d.length > 3) out += "-" + d.slice(3, 6);
  if (d.length > 6) out += "-" + d.slice(6, 9);
  if (d.length > 9) out += " " + d.slice(9, 11);
  return out;
}

/** Модальная шторка: снизу на телефоне, по центру на десктопе. Закрывается по Esc и тапу мимо. */
function Sheet({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  // Portal в body: иначе transform анимации страницы запирает z-index шторки под таб-баром
  return createPortal(
    <div className="fixed inset-0 z-50 bg-black/30 flex items-end sm:items-center justify-center fade-in" onClick={onClose}>
      <div role="dialog" aria-modal="true" aria-label={title} onClick={(e) => e.stopPropagation()}
        className="sheet-in w-full sm:max-w-[460px] max-h-[92dvh] overflow-y-auto bg-paper rounded-t-[22px] sm:rounded-[22px] p-5 pb-[calc(20px+env(safe-area-inset-bottom))]">
        <div className="sm:hidden mx-auto mb-3 h-1.5 w-10 rounded-full bg-line-strong" aria-hidden />
        <div className="flex items-center justify-between mb-5">
          <h2 className="text-[20px] font-bold">{title}</h2>
          <button type="button" onClick={onClose} className="size-8 grid place-items-center rounded-full bg-fill-2 text-muted hover:text-ink" aria-label="Закрыть">
            <X size={14} weight="bold" />
          </button>
        </div>
        {children}
      </div>
    </div>,
    document.body,
  );
}

function UserSheet({ user, onClose }: { user: User | null; onClose: () => void }) {
  const qc = useQueryClient();
  const { user: me } = useAuth();
  const editing = user !== null;
  const [form, setForm] = useState({
    email: user?.email ?? "",
    full_name: user?.full_name ?? "",
    password: "",
    role: (user?.role ?? "technologist") as Role,
    snils: user?.snils ? formatSnilsInput(user.snils) : "",
  });
  const [error, setError] = useState<string | null>(null);

  const save = useMutation({
    mutationFn: () => {
      const snils = form.snils.replace(/\D/g, "") || null;
      if (editing) {
        const body: Record<string, unknown> = { full_name: form.full_name, role: form.role, snils };
        if (form.password) body.password = form.password;
        return api<User>(`/users/${user.id}`, { method: "PATCH", body: JSON.stringify(body) });
      }
      return api<User>("/users", { method: "POST", body: JSON.stringify({ ...form, snils }) });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["users"] });
      onClose();
    },
    onError: (e) => setError(e instanceof ApiError ? e.message : "Не удалось сохранить"),
  });

  function submit(e: FormEvent) {
    e.preventDefault();
    if (!form.full_name.trim() || (!editing && !form.email.trim())) return setError("Заполните имя и email");
    if ((!editing || form.password) && form.password.length < 8) return setError("Пароль должен быть не короче 8 символов");
    const digits = form.snils.replace(/\D/g, "");
    if (digits && digits.length !== 11) return setError("СНИЛС должен содержать 11 цифр");
    setError(null);
    save.mutate();
  }

  const set = (k: keyof typeof form) => (e: { target: { value: string } }) => {
    setForm({ ...form, [k]: k === "snils" ? formatSnilsInput(e.target.value) : e.target.value });
    setError(null);
  };

  return (
    <Sheet title={editing ? "Сотрудник" : "Новый сотрудник"} onClose={onClose}>
      <form onSubmit={submit} className="flex flex-col gap-4" noValidate>
        <div>
          <label className="label" htmlFor="fn">Имя и фамилия</label>
          <input id="fn" className="input bg-surface" value={form.full_name} onChange={set("full_name")} />
        </div>
        <div>
          <label className="label" htmlFor="em">Email</label>
          <input id="em" type="email" className="input bg-surface disabled:text-muted" value={form.email} onChange={set("email")} disabled={editing} />
        </div>
        <div>
          <label className="label" htmlFor="sn">СНИЛС</label>
          <input id="sn" inputMode="numeric" className="input bg-surface tnum" placeholder="000-000-000 00" value={form.snils} onChange={set("snils")} />
          <p className="mt-1.5 px-1 text-[13px] text-muted">Нужен для входа через Госуслуги. Без СНИЛС сотрудник входит только по паролю.</p>
        </div>
        <div>
          <label className="label" htmlFor="pw">{editing ? "Новый пароль" : "Временный пароль"}</label>
          <input id="pw" type="text" className="input bg-surface" value={form.password} onChange={set("password")}
            placeholder={editing ? "Оставьте пустым, чтобы не менять" : "Не короче 8 символов"} />
        </div>
        <div>
          <label className="label" htmlFor="rl">Роль</label>
          <select id="rl" className="input bg-surface" value={form.role} onChange={set("role")} disabled={editing && user.id === me?.id}>
            {(Object.keys(ROLE_LABEL) as Role[]).map((r) => (
              <option key={r} value={r}>{ROLE_LABEL[r]}</option>
            ))}
          </select>
        </div>
        {error && <ErrorNote>{error}</ErrorNote>}
        <button className="btn-primary h-12 mt-1" disabled={save.isPending}>{editing ? "Сохранить" : "Добавить сотрудника"}</button>
      </form>
    </Sheet>
  );
}

export function Users() {
  const qc = useQueryClient();
  const { user: me } = useAuth();
  const [sheet, setSheet] = useState<User | "new" | null>(null);
  const { data, isPending, error } = useQuery({ queryKey: ["users"], queryFn: () => api<User[]>("/users") });
  const toggle = useMutation({
    mutationFn: (u: User) => api<User>(`/users/${u.id}`, { method: "PATCH", body: JSON.stringify({ is_active: !u.is_active }) }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["users"] }),
  });

  return (
    <>
      <PageHeader
        title="Сотрудники"
        subtitle="Заблокированный сотрудник сразу теряет доступ, в том числе через Госуслуги."
        actions={
          <button className="btn-primary" onClick={() => setSheet("new")}>
            <Plus size={18} weight="bold" /> Добавить
          </button>
        }
      />
      {error && <ErrorNote>{(error as Error).message}</ErrorNote>}
      {toggle.error && <div className="mb-4"><ErrorNote>{(toggle.error as Error).message}</ErrorNote></div>}
      {isPending ? (
        <ListSkeleton />
      ) : (
        <div className="card overflow-hidden">
          {data?.map((u) => (
            <ListRow key={u.id} onClick={() => setSheet(u)} chevron={false}>
              <div className="flex flex-col sm:flex-row sm:items-center gap-3">
                <div className="flex items-center gap-3 flex-1 min-w-0">
                  <Avatar name={u.full_name} size={40} />
                  <div className="min-w-0">
                    <div className={`text-[15px] font-semibold truncate ${u.is_active ? "" : "text-muted"}`}>{u.full_name}</div>
                    <div className="text-[13px] text-muted truncate">
                      {ROLE_LABEL[u.role]} · {u.email}
                    </div>
                    <div className="text-[13px] text-muted">
                      {u.last_login_at ? `Входил(а) ${fmtDateTime(u.last_login_at)}` : "Ещё не входил(а)"}
                    </div>
                  </div>
                </div>
                <div className="flex flex-wrap items-center gap-1.5 sm:justify-end pl-[52px] sm:pl-0">
                  {u.esia_linked ? (
                    <StatusPill tone="info" icon={<IdentificationCard size={15} weight="fill" />}>Госуслуги</StatusPill>
                  ) : u.snils ? (
                    <StatusPill tone="neutral" icon={<IdentificationCard size={15} weight="fill" />}>СНИЛС указан</StatusPill>
                  ) : null}
                  {u.is_active ? <StatusPill tone="ok">Активен</StatusPill> : <StatusPill tone="bad">Заблокирован</StatusPill>}
                  {u.id !== me?.id && (
                    <button className="btn-ghost h-8 px-3 text-[14px]" disabled={toggle.isPending}
                      onClick={(e) => { e.stopPropagation(); toggle.mutate(u); }}>
                      {u.is_active ? "Заблокировать" : "Разблокировать"}
                    </button>
                  )}
                </div>
              </div>
            </ListRow>
          ))}
        </div>
      )}
      {sheet && <UserSheet user={sheet === "new" ? null : sheet} onClose={() => setSheet(null)} />}
    </>
  );
}
