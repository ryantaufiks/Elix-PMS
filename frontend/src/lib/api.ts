// Thin fetch wrapper for the Django API: JWT bearer auth with one shared refresh in flight.
const BASE = process.env.NEXT_PUBLIC_API_BASE ?? "";
const ACCESS = "elix.access";
const REFRESH = "elix.refresh";
export const LOGOUT_EVENT = "elix:logout";

export class ApiError extends Error {
  constructor(public status: number, message: string, public data?: unknown) {
    super(message);
  }
}

function storage(): Storage | null {
  try {
    return typeof window === "undefined" ? null : window.localStorage;
  } catch {
    return null;
  }
}

export const tokens = {
  access: () => storage()?.getItem(ACCESS) ?? null,
  refresh: () => storage()?.getItem(REFRESH) ?? null,
  set(access: string, refresh?: string) {
    storage()?.setItem(ACCESS, access);
    if (refresh) storage()?.setItem(REFRESH, refresh);
  },
  clear() {
    storage()?.removeItem(ACCESS);
    storage()?.removeItem(REFRESH);
  },
};

let refreshing: Promise<boolean> | null = null;

export function refreshAccess(): Promise<boolean> {
  const refresh = tokens.refresh();
  if (!refresh) return Promise.resolve(false);
  refreshing ??= fetch(`${BASE}/v1/auth/token/refresh/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh }),
  })
    .then(async (response) => {
      if (!response.ok) return false;
      const data = await response.json();
      tokens.set(data.access, data.refresh);
      return true;
    })
    .catch(() => false)
    .finally(() => {
      refreshing = null;
    });
  return refreshing;
}

function signOut() {
  tokens.clear();
  window.dispatchEvent(new Event(LOGOUT_EVENT));
}

/** First readable message from a DRF error body ({detail}, {field: [msg]} or [msg]). */
export function errorMessage(data: unknown, fallback: string): string {
  if (!data) return fallback;
  if (typeof data === "string") return data;
  if (Array.isArray(data)) return data.length ? errorMessage(data[0], fallback) : fallback;
  if (typeof data === "object") {
    const record = data as Record<string, unknown>;
    if (record.detail) return errorMessage(record.detail, fallback);
    const [field, value] = Object.entries(record)[0] ?? [];
    if (field) {
      const message = errorMessage(value, fallback);
      return field === "non_field_errors" ? message : `${field.replaceAll("_", " ")}: ${message}`;
    }
  }
  return fallback;
}

type Options = { method?: string; body?: unknown; raw?: boolean };

async function request(path: string, options: Options, retry = true): Promise<Response> {
  const headers: Record<string, string> = {};
  const access = tokens.access();
  if (access) headers.Authorization = `Bearer ${access}`;
  let body: BodyInit | undefined;
  if (options.body instanceof FormData) body = options.body;
  else if (options.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(options.body);
  }
  const response = await fetch(`${BASE}${path}`, { method: options.method ?? "GET", headers, body });
  if (response.status === 401 && retry && tokens.refresh()) {
    if (await refreshAccess()) return request(path, options, false);
    signOut();
  }
  return response;
}

export async function api<T = unknown>(path: string, options: Options = {}): Promise<T> {
  const response = await request(path, options);
  if (!response.ok) {
    const data = await response.json().catch(() => undefined);
    throw new ApiError(response.status, errorMessage(data, `Request failed (HTTP ${response.status})`), data);
  }
  if (options.raw) return response as unknown as T;
  if (response.status === 204) return undefined as T;
  return response.json();
}

export const fetcher = <T,>(path: string) => api<T>(path);

/** Fetch an authenticated image (snapshots, QR codes) as an object URL; revoke it when done. */
export async function imageUrl(path: string): Promise<string> {
  const response = await api<Response>(path, { raw: true });
  return URL.createObjectURL(await response.blob());
}

export async function login(username: string, password: string) {
  const response = await fetch(`${BASE}/v1/auth/token/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  const data = await response.json().catch(() => undefined);
  if (!response.ok) {
    throw new ApiError(response.status, response.status === 401 ? "Wrong username or password." : errorMessage(data, "Login failed."));
  }
  tokens.set(data.access, data.refresh);
}

export function logout() {
  signOut();
}

export function query(params: Record<string, string | number | boolean | undefined | null>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") search.set(key, String(value));
  }
  const text = search.toString();
  return text ? `?${text}` : "";
}

export function wsUrl(path: string): string {
  const base = process.env.NEXT_PUBLIC_WS_BASE;
  if (base) return `${base}${path}`;
  const { protocol, host } = window.location;
  return `${protocol === "https:" ? "wss" : "ws"}://${host}${path}`;
}

/** "#05-12" -> "05 12": the API searches floor and unit number as separate terms that must all match. */
export const unitSearch = (text: string) => text.replace(/[#-]/g, " ").trim();
