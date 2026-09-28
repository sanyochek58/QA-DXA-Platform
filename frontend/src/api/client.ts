// Тонкая обёртка над fetch: подставляет токен, разбирает ошибки FastAPI в читаемый текст.

const TOKEN_KEY = "osteo.token";

export const tokenStore = {
  get: () => {
    try {
      return localStorage.getItem(TOKEN_KEY);
    } catch {
      return null;
    }
  },
  set: (t: string) => {
    try {
      localStorage.setItem(TOKEN_KEY, t);
    } catch {
      /* приватный режим браузера — живём без сохранения */
    }
  },
  clear: () => {
    try {
      localStorage.removeItem(TOKEN_KEY);
    } catch {
      /* нечего чистить */
    }
  },
};

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

type Detail = string | { msg: string; loc?: (string | number)[] }[];

function readableDetail(detail: Detail | undefined, status: number): string {
  if (!detail) return `Ошибка сервера (${status})`;
  if (typeof detail === "string") return detail;
  return detail.map((d) => d.msg).join("; ");
}

let onUnauthorized: (() => void) | null = null;
export const setUnauthorizedHandler = (fn: () => void) => {
  onUnauthorized = fn;
};

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  const token = tokenStore.get();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init.body && !(init.body instanceof FormData) && !(init.body instanceof URLSearchParams)) {
    headers.set("Content-Type", "application/json");
  }
  let resp: Response;
  try {
    resp = await fetch(`/api/v1${path}`, { ...init, headers });
  } catch {
    throw new ApiError(0, "Нет связи с сервером. Проверьте, что бэкенд запущен.");
  }
  if (resp.status === 401 && path !== "/auth/login") {
    tokenStore.clear();
    onUnauthorized?.();
  }
  if (!resp.ok) {
    let detail: Detail | undefined;
    try {
      detail = (await resp.json()).detail;
    } catch {
      /* тело не JSON */
    }
    throw new ApiError(resp.status, readableDetail(detail, resp.status));
  }
  if (resp.status === 204) return undefined as T;
  return resp.json() as Promise<T>;
}

/** Изображения защищены токеном, поэтому <img src> напрямую нельзя: грузим blob и делаем objectURL. */
export async function fetchImage(path: string): Promise<string> {
  const token = tokenStore.get();
  const resp = await fetch(`/api/v1${path}`, { headers: token ? { Authorization: `Bearer ${token}` } : {} });
  if (!resp.ok) throw new ApiError(resp.status, "Изображение недоступно");
  return URL.createObjectURL(await resp.blob());
}
