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

/** An authenticated file (an assistant map) as a Blob. */
export async function kioskBlob(path: string): Promise<Blob> {
  const token = kioskToken.get();
  const response = await fetch(path, { headers: token ? { Authorization: `Kiosk ${token}` } : {} });
  if (!response.ok) throw new ApiError(response.status, `Request failed (HTTP ${response.status})`, undefined);
  return response.blob();
}

/** The site's AI assistant as this kiosk offers it. */
export type KioskAssistant = {
  enabled: boolean;
  name: string;
  greeting: string;
  mode: "pipeline" | "realtime";
  max_session_seconds: number;
  maps: { id: number; name: string }[];
};

export type Weather = {
  temperature: number | null;
  humidity: number | null;
  forecast: string;
  area: string;
  station: string;
  valid: string;
  updated_at: string;
};

/** Icon for an NEA 2-hour outlook ("Thundery Showers", "Partly Cloudy (Night)"…). */
export function weatherIcon(forecast: string): "storm" | "rain" | "cloud" | "moon" | "sun" {
  const f = forecast.toLowerCase();
  if (f.includes("thunder")) return "storm";
  if (f.includes("rain") || f.includes("shower")) return "rain";
  if (["cloud", "haz", "mist", "fog", "wind"].some((w) => f.includes(w))) return "cloud";
  return f.includes("night") ? "moon" : "sun";
}

export type KioskSelf = {
  id: number;
  name: string;
  condominium: number;
  condominium_name: string;
  gate: number | null;
  gate_name: string;
  ring_timeout_seconds: number;
  visitor_form: boolean;
  photo_required: boolean;
  privacy_notice: string;
  walk_in: boolean;
  walk_in_photo: boolean;
  checkout: boolean;
  /** The site has the video intercom, so the kiosk can call units. */
  call_resident: boolean;
  /** The site takes video calls at the guardhouse (the dashboard's Intercom page). */
  call_guardhouse: boolean;
  /** Offer Facilities: today's schedule and check-in to a booking. */
  facilities: boolean;
  /** Modules of the site's plan. */
  modules: string[];
  /** Visitors whose photo the kiosk takes can check out by face. */
  face_checkout: boolean;
  prints_slips: boolean;
};

/** A visit as printed on the slip. ``qr`` is a PNG data URI; ``pin`` also checks the visitor out. */
export type WalkInSlip = {
  pass_number: string;
  pin: string;
  visitor_name: string;
  purpose: string;
  purpose_display: string;
  company: string;
  vehicle_plate: string;
  unit_display: string;
  condominium_name: string;
  created_at: string;
  valid_until: string;
  state: "on_site" | "checked_out" | "expired";
  checked_out_at: string | null;
  qr: string;
};

export type WalkInCheckOut = { result: "checked_out" | "already_checked_out"; walk_in: WalkInSlip };

export const isWalkInCode = (code: string) => code.trim().startsWith("ELIX-WALKIN:");
export const isBookingCode = (code: string) => code.trim().startsWith("ELIX-BOOKING:");

/** A facility's remaining slots today (no names: anyone in the lobby can read it). */
export type KioskFacility = {
  id: number; name: string; location: string; icon: string; opens_at: string; closes_at: string; open_today: boolean;
  slots: { starts_at: string; ends_at: string; booked: boolean; left: number; now: boolean }[];
};

export type BookingCheckIn = {
  result: "granted" | "denied"; reason: string; facility: string; unit: string;
  starts_at: string | null; ends_at: string | null; door_opened: boolean;
};

export type VisitorLookup = { found: boolean; blocked: boolean; ref: string; masked_name: string; company: string; purpose: string };

/** What the visitor told the kiosk before ringing a unit. */
export type VisitorDetails = {
  ref: string;
  maskedName: string;
  name: string;
  phone: string;
  idPartial: string;
  purpose: string;
  company: string;
  consent: boolean;
  photo: Blob | null;
  /** Face template of ``photo`` for face check-out (only when the site uses it). */
  face?: number[] | null;
};

export const PURPOSES: { value: string; label: string; company?: string }[] = [
  { value: "guest", label: "Visiting a resident" },
  { value: "delivery", label: "Parcel delivery", company: "Courier company, e.g. Ninja Van" },
  { value: "food", label: "Food delivery", company: "e.g. GrabFood, foodpanda, Deliveroo" },
  { value: "contractor", label: "Contractor / service", company: "Company name" },
  { value: "pickup", label: "Pick-up / drop-off", company: "e.g. Grab, Gojek, taxi" },
  { value: "other", label: "Other" },
];

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
  privacy_notice: string;
  /** For a booking's guests: the facility booked. */
  facility: string;
  /** Vendor passes. */
  company: string;
  schedule: string;
};

export type CheckInResult = { result: "granted" | "denied" | "face_required"; reason: string; invitation: VisitorPass | null };
