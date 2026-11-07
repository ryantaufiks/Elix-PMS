// Singapore has no DST, so every timestamp is shown (and entered) in SGT, UTC+08:00.
export const TIME_ZONE = "Asia/Singapore";

const dateTime = new Intl.DateTimeFormat("en-SG", {
  timeZone: TIME_ZONE, day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit", hour12: false,
});
const time = new Intl.DateTimeFormat("en-SG", {
  timeZone: TIME_ZONE, hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false,
});

export const formatDateTime = (iso?: string | null) => (iso ? dateTime.format(new Date(iso)) : "—");
export const formatTime = (iso?: string | null) => (iso ? time.format(new Date(iso)) : "—");

export function timeAgo(iso?: string | null): string {
  if (!iso) return "never";
  const seconds = Math.round((Date.now() - new Date(iso).getTime()) / 1000);
  if (seconds < 60) return "just now";
  if (seconds < 3600) return `${Math.floor(seconds / 60)} min ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)} h ago`;
  return `${Math.floor(seconds / 86400)} d ago`;
}

/** Value for <input type="datetime-local"> showing ``iso`` in SGT. */
export function toLocalInput(iso: string | Date): string {
  const shifted = new Date(new Date(iso).getTime() + 8 * 3600 * 1000);
  return shifted.toISOString().slice(0, 16);
}

/** <input type="datetime-local"> value (read as SGT) to ISO with offset. */
export const fromLocalInput = (value: string) => (value ? `${value}:00+08:00` : "");

/** Start of today in SGT as ISO, for "today" filters. */
export function startOfTodayIso(): string {
  return `${toLocalInput(new Date()).slice(0, 10)}T00:00:00+08:00`;
}

export const METHOD_LABEL: Record<string, string> = {
  lpr: "Licence plate", qr: "Invitation QR", intercom: "Intercom", app: "Resident app", manual: "Manual",
};

export const CALL_STATUS_LABEL: Record<string, string> = {
  ringing: "Ringing", answered: "Answered", approved: "Gate opened", rejected: "Rejected", missed: "Missed",
  cancelled: "Cancelled",
};

export const PURPOSE_LABEL: Record<string, string> = {
  guest: "Guest", delivery: "Delivery", contractor: "Contractor", pickup: "Pick-up / drop-off", other: "Other",
};

/** Purpose a visitor chose at the kiosk (intercom calls). */
export const VISIT_PURPOSE_LABEL: Record<string, string> = {
  guest: "Guest", delivery: "Parcel delivery", food: "Food delivery", contractor: "Contractor",
  pickup: "Pick-up / drop-off", other: "Other",
};

/** "Parcel delivery · Ninja Van" */
export const visitPurpose = (purpose?: string, company?: string) =>
  [purpose ? VISIT_PURPOSE_LABEL[purpose] ?? purpose : "", company ?? ""].filter(Boolean).join(" · ");

export const RESIDENT_TYPE_LABEL: Record<string, string> = {
  owner: "Owner", tenant: "Tenant", family: "Family", helper: "Helper",
};

export const userName = (u?: { first_name: string; last_name: string; username: string } | null) =>
  u ? [u.first_name, u.last_name].filter(Boolean).join(" ") || u.username : "";
