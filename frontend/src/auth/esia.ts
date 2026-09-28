// Вход через Госуслуги (ЕСИА), сторона браузера.
// 1) просим у core URL авторизации и подписанный state; 2) запоминаем state в sessionStorage;
// 3) уходим на ЕСИА; 4) на /auth/esia/callback сверяем state и меняем code на наш JWT.

import { api } from "../api/client";

const STATE_KEY = "osteo.esia.state";

export const esiaRedirectUri = () => `${window.location.origin}/auth/esia/callback`;

export async function startEsiaLogin() {
  const { url, state } = await api<{ url: string; state: string }>(
    `/auth/esia/start?redirect_uri=${encodeURIComponent(esiaRedirectUri())}`,
  );
  try {
    sessionStorage.setItem(STATE_KEY, state);
  } catch {
    /* без sessionStorage проверку state сделает только сервер */
  }
  window.location.assign(url);
}

/** Сравнить state из адреса с сохранённым: защита от подмены ответа (CSRF). */
export function takeSavedState(): string | null {
  try {
    const s = sessionStorage.getItem(STATE_KEY);
    sessionStorage.removeItem(STATE_KEY);
    return s;
  } catch {
    return null;
  }
}
