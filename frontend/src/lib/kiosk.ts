// Device-token API client for the web kiosk (Authorization: Kiosk <token>).
import { ApiError, errorMessage } from "./api";

const KEY = "elix.kioskToken";

export const kioskToken = {
  get: () => {
    try {
      return localStorage.getItem(KEY);
    } catch {
      return null;
    }
  },
  set: (token: string) => {
    try {
      localStorage.setItem(KEY, token);
    } catch {}
  },
  clear: () => {
    try {
      localStorage.removeItem(KEY);
    } catch {}
  },
};

export async function kioskApi<T>(path: string, options: { method?: string; body?: unknown; token?: string } = {}): Promise<T> {
  const token = options.token ?? kioskToken.get();
  const headers: Record<string, string> = { "X-App-Version": "web-kiosk/1" };
  if (token) headers.Authorization = `Kiosk ${token}`;
  let body: BodyInit | undefined;
  if (options.body instanceof FormData) body = options.body;
  else if (options.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(options.body);
  }
  const response = await fetch(path, { method: options.method ?? "GET", headers, body });
  const data = response.status === 204 ? undefined : await response.json().catch(() => undefined);
  if (!response.ok) throw new ApiError(response.status, errorMessage(data, `Request failed (HTTP ${response.status})`), data);
  return data as T;
}

export type KioskSelf = {
  id: number;
  name: string;
  condominium: number;
  condominium_name: string;
  gate: number | null;
  gate_name: string;
  ring_timeout_seconds: number;
};

export type DirectoryUnit = { id: number; block: string; floor: string; unit_number: string; label: string };

export type VisitorPass = {
  visitor_name: string;
  purpose: string;
  condominium_name: string;
  condominium_address: string;
  unit_display: string;
  host_first_name: string;
  valid_from: string;
  valid_until: string;
  status: "active" | "completed" | "cancelled" | "expired";
  vehicle_plate: string;
  require_face: boolean;
  entries_left: number | null;
  usable: boolean;
  problem: string;
};

export type CheckInResult = { result: "granted" | "denied" | "face_required"; reason: string; invitation: VisitorPass | null };
