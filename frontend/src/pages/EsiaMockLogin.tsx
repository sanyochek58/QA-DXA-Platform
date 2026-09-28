import { Flask } from "@phosphor-icons/react";
import { useQuery } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, ApiError } from "../api/client";
import type { MockEsiaPerson } from "../api/types";
import { ErrorNote } from "../components/ui";

/**
 * Тестовый контур ЕСИА. Заменяет страницу входа Госуслуг, пока у системы нет регистрации в ЕСИА.
 * Намеренно не повторяет оформление Госуслуг: это стенд разработчика, и он так и подписан.
 */
export function EsiaMockLogin() {
  const [params] = useSearchParams();
  const state = params.get("state") ?? "";
  const redirectUri = params.get("redirect_uri") ?? "";
  const [login, setLogin] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const persons = useQuery({
    queryKey: ["esia-persons"],
    queryFn: () => api<MockEsiaPerson[]>("/esia-test/persons"),
  });

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!login.trim() || !password) return setError("Введите СНИЛС, телефон или почту и пароль");
    setBusy(true);
    setError(null);
    try {
      const { redirect } = await api<{ redirect: string }>("/esia-test/authorize", {
        method: "POST",
        body: JSON.stringify({ login: login.trim(), password, state, redirect_uri: redirectUri }),
      });
      window.location.assign(redirect);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось войти");
      setBusy(false);
    }
  }

  const broken = !state || !redirectUri;

  return (
    <main className="min-h-[100dvh] flex items-start sm:items-center justify-center px-4 py-12">
      <div className="w-full max-w-[440px] page-in">
        <div className="flex items-center justify-center gap-2 text-[13px] font-semibold text-warn bg-warn-soft rounded-full h-8 px-3 w-fit mx-auto">
          <Flask size={16} weight="fill" /> Тестовый контур ЕСИА
        </div>
        <h1 className="mt-5 text-center text-[28px] font-bold leading-tight">Вход в учётную запись</h1>
        <p className="mt-2 text-center text-[15px] text-muted">
          Здесь вместо Госуслуг работает стенд. Выберите тестового человека или введите данные вручную.
        </p>

        {broken ? (
          <div className="mt-8"><ErrorNote>Страница открыта без параметров входа. Начните со страницы приложения.</ErrorNote></div>
        ) : (
          <form onSubmit={submit} noValidate className="mt-8 flex flex-col gap-3">
            <div className="card overflow-hidden">
              <label className="sr-only" htmlFor="esia-login">СНИЛС, телефон или почта</label>
              <input id="esia-login" autoComplete="off" placeholder="СНИЛС, телефон или почта" value={login}
                onChange={(e) => { setLogin(e.target.value); setError(null); }}
                className="w-full h-12 px-4 text-[16px] bg-transparent focus:outline-none border-b border-line" />
              <label className="sr-only" htmlFor="esia-password">Пароль</label>
              <input id="esia-password" type="password" autoComplete="off" placeholder="Пароль" value={password}
                onChange={(e) => { setPassword(e.target.value); setError(null); }}
                className="w-full h-12 px-4 text-[16px] bg-transparent focus:outline-none" />
            </div>
            {error && <ErrorNote>{error}</ErrorNote>}
            <button className="btn-primary h-12 w-full" disabled={busy}>{busy ? "Проверяем" : "Войти"}</button>
            <Link to="/login" replace className="btn-ghost h-11 w-full">Отмена</Link>
          </form>
        )}

        {!broken && (
          <section className="mt-8">
            <h2 className="text-[13px] font-medium text-muted px-1 mb-2">Тестовые люди · пароль у всех esia12345</h2>
            <div className="card overflow-hidden">
              {persons.data?.map((p) => (
                <button key={p.snils} type="button"
                  onClick={() => { setLogin(p.snils); setPassword("esia12345"); setError(null); }}
                  className="w-full text-left px-4 py-3 flex items-center justify-between gap-3 hover:bg-fill/60 border-b border-line last:border-0">
                  <span className="min-w-0">
                    <span className="block text-[15px] font-medium truncate">{p.full_name}</span>
                    <span className="block text-[13px] text-muted tnum">СНИЛС {p.snils}</span>
                  </span>
                  <span className="text-[13px] text-brand font-medium shrink-0">Подставить</span>
                </button>
              ))}
              {persons.isPending && <div className="px-4 py-3 text-[14px] text-muted">Загружаем список</div>}
            </div>
          </section>
        )}
      </div>
    </main>
  );
}
