import { SpinnerGap, WarningCircle } from "@phosphor-icons/react";
import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api, ApiError } from "../api/client";
import { homeFor, useAuth } from "../auth/AuthContext";
import { esiaRedirectUri, takeSavedState } from "../auth/esia";

/** Сюда ЕСИА возвращает браузер с code и state. Меняем их на токен приложения. */
export function EsiaCallback() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const { loginWithToken } = useAuth();
  const [error, setError] = useState<string | null>(null);
  const started = useRef(false); // StrictMode вызывает эффект дважды, а code одноразовый

  useEffect(() => {
    if (started.current) return;
    started.current = true;

    const code = params.get("code");
    // mock возвращает наш state в state, настоящая ЕСИА — в app_state (свой state у неё UUID)
    const state = params.get("app_state") ?? params.get("state");
    const esiaError = params.get("error_description") ?? params.get("error");
    if (esiaError) return setError(`Госуслуги отклонили вход: ${esiaError}`);
    if (!code || !state) return setError("В ответе Госуслуг нет кода авторизации.");
    const saved = takeSavedState();
    if (saved && saved !== state) return setError("Ответ не совпадает с начатым входом. Начните вход заново.");

    api<{ access_token: string }>("/auth/esia/callback", {
      method: "POST",
      body: JSON.stringify({ code, state, redirect_uri: esiaRedirectUri() }),
    })
      .then(({ access_token }) => loginWithToken(access_token))
      .then((u) => navigate(homeFor(u.role), { replace: true }))
      .catch((e) => setError(e instanceof ApiError ? e.message : "Не удалось завершить вход"));
  }, [params, navigate, loginWithToken]);

  return (
    <main className="min-h-[100dvh] grid place-items-center px-4">
      {error ? (
        <div className="card w-full max-w-[420px] p-7 text-center page-in">
          <WarningCircle size={44} weight="fill" className="mx-auto text-bad-fill" />
          <h1 className="mt-3 text-[22px] font-bold">Не удалось войти</h1>
          <p className="mt-2 text-[15px] text-muted">{error}</p>
          <Link to="/login" replace className="btn-primary w-full mt-6">Вернуться ко входу</Link>
        </div>
      ) : (
        <div className="flex flex-col items-center gap-3 text-muted text-[15px]">
          <SpinnerGap size={28} className="animate-spin text-brand" />
          Завершаем вход через Госуслуги
        </div>
      )}
    </main>
  );
}
