import { CaretDown, IdentificationCard } from "@phosphor-icons/react";
import { useQuery } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Navigate, useNavigate, useSearchParams } from "react-router-dom";
import { api, ApiError } from "../api/client";
import type { EsiaConfig } from "../api/types";
import { homeFor, useAuth } from "../auth/AuthContext";
import { startEsiaLogin } from "../auth/esia";
import { AppIcon } from "../components/Layout";
import { ErrorNote } from "../components/ui";

const TEST_ACCOUNTS = [
  { email: "lab@dxa-qa.ru", password: "lab12345", role: "Лаборант", name: "Ирина Садыкова" },
  { email: "doctor@dxa-qa.ru", password: "doctor12345", role: "Врач-рентгенолог", name: "Мария Лебедева" },
  { email: "admin@dxa-qa.ru", password: "admin12345", role: "Заведующий", name: "Андрей Корнилов" },
];

export function Login() {
  const { user, login } = useAuth();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(params.get("error"));
  const [busy, setBusy] = useState<"password" | "esia" | null>(null);
  const [showTest, setShowTest] = useState(false);

  const esia = useQuery({
    queryKey: ["esia-config"],
    queryFn: () => api<EsiaConfig>("/auth/esia/config"),
    staleTime: Infinity,
  });

  if (user) return <Navigate to={homeFor(user.role)} replace />;

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!email.trim() || !password) {
      setError("Введите email и пароль");
      return;
    }
    setBusy("password");
    setError(null);
    try {
      const u = await login(email.trim(), password);
      navigate(homeFor(u.role), { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось войти");
      setBusy(null);
    }
  }

  async function esiaLogin() {
    setBusy("esia");
    setError(null);
    try {
      await startEsiaLogin(); // уводит браузер со страницы
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Вход через Госуслуги сейчас недоступен");
      setBusy(null);
    }
  }

  return (
    <main className="min-h-[100dvh] flex items-start sm:items-center justify-center px-4 py-12">
      <div className="w-full max-w-[400px] page-in">
        <div className="flex flex-col items-center text-center">
          <AppIcon size={64} />
          <h1 className="mt-5 text-[30px] font-bold leading-tight">Остеоконтроль</h1>
          <p className="mt-2 text-[15px] text-muted max-w-[34ch]">
            Проверка качества снимков денситометрии до того, как пациент ушёл из кабинета.
          </p>
        </div>

        <div className="mt-9 flex flex-col gap-3">
          {esia.data?.enabled && (
            <>
              <button type="button" className="btn-primary h-12 w-full" onClick={esiaLogin} disabled={busy !== null}>
                <IdentificationCard size={22} weight="fill" />
                {busy === "esia" ? "Переходим на Госуслуги" : "Войти через Госуслуги"}
              </button>
              {esia.data.mode === "mock" && (
                <p className="text-center text-[13px] text-muted -mt-0.5">Тестовый контур ЕСИА, реальные данные не нужны</p>
              )}
              <div className="flex items-center gap-3 my-3 text-[13px] text-muted">
                <span className="h-px flex-1 bg-line-strong" />
                или по почте
                <span className="h-px flex-1 bg-line-strong" />
              </div>
            </>
          )}

          <form onSubmit={submit} noValidate className="flex flex-col gap-3">
            {/* Два поля в одной группе — как форма входа в Apple ID */}
            <div className="card overflow-hidden">
              <label className="sr-only" htmlFor="email">Email</label>
              <input id="email" type="email" autoComplete="username" placeholder="Email" value={email}
                onChange={(e) => { setEmail(e.target.value); setError(null); }}
                className="w-full h-12 px-4 text-[16px] bg-transparent focus:outline-none border-b border-line" />
              <label className="sr-only" htmlFor="password">Пароль</label>
              <input id="password" type="password" autoComplete="current-password" placeholder="Пароль" value={password}
                onChange={(e) => { setPassword(e.target.value); setError(null); }}
                className="w-full h-12 px-4 text-[16px] bg-transparent focus:outline-none" />
            </div>
            {error && <ErrorNote>{error}</ErrorNote>}
            <button className={`${esia.data?.enabled ? "btn-secondary" : "btn-primary"} h-12 w-full`} disabled={busy !== null}>
              {busy === "password" ? "Выполняется вход" : "Войти"}
            </button>
          </form>
        </div>

        <div className="mt-8">
          <button type="button" onClick={() => setShowTest(!showTest)} aria-expanded={showTest}
            className="mx-auto flex items-center gap-1.5 text-[15px] text-brand font-medium h-10 px-3 rounded-full hover:bg-brand-soft">
            Тестовые учётные записи
            <CaretDown size={14} weight="bold" className={`transition-transform duration-200 ${showTest ? "rotate-180" : ""}`} />
          </button>
          {showTest && (
            <div className="card mt-2 overflow-hidden fade-in">
              {TEST_ACCOUNTS.map((a) => (
                <button key={a.email} type="button"
                  onClick={() => { setEmail(a.email); setPassword(a.password); setError(null); }}
                  className="w-full text-left px-4 py-3 flex items-center justify-between gap-3 hover:bg-fill/60 border-b border-line last:border-0">
                  <span className="min-w-0">
                    <span className="block text-[15px] font-medium">{a.role}</span>
                    <span className="block text-[13px] text-muted truncate">{a.name} · {a.email}</span>
                  </span>
                  <span className="text-[13px] text-brand font-medium shrink-0">Подставить</span>
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
    </main>
  );
}
