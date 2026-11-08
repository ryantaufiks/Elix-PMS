"use client";

// Header bell: every live event becomes a notification, kept in this browser (last 50 across condos).
import Link from "next/link";
import { useEffect, useState } from "react";

import { formatDateTime, METHOD_LABEL, timeAgo } from "@/lib/format";
import { type LiveEvent, useLiveEvents } from "@/lib/live";
import { useSession } from "@/lib/session";

import { Icon } from "./icons";
import { cx } from "./ui";

type Tone = "green" | "red" | "amber" | "blue" | "slate";
type Note = { key: string; condo: number; at: string; title: string; body: string; href: string; tone: Tone };
type Stored = { items: Note[]; readAt: string };

const KEY = "elix.notifications";
const LIMIT = 50;
const DOT: Record<Tone, string> = {
  green: "bg-emerald-500", red: "bg-rose-500", amber: "bg-amber-500", blue: "bg-primary-500", slate: "bg-slate-400",
};

const join = (...parts: (string | null | undefined)[]) => parts.filter(Boolean).join(" · ");

/** What an event means to the guardhouse, or null when it is not news (e.g. a call's later updates). */
function describe(event: LiveEvent): Omit<Note, "at" | "condo"> | null {
  switch (event.type) {
    case "access_log": {
      const a = event.data;
      const who = a.unit_display || a.visitor_name || a.actor_name || a.plate_number;
      const how = METHOD_LABEL[a.method] ?? a.method;
      return a.result === "granted"
        ? { key: `access:${a.id}`, title: `Gate opened · ${a.gate_name || "gate"}`, body: join(how, who), href: "/access/", tone: "green" }
        : { key: `access:${a.id}`, title: `Access ${a.result === "error" ? "error" : "denied"} · ${a.gate_name || "gate"}`, body: join(how, who, a.reason), href: "/access/", tone: "red" };
    }
    case "intercom_call": {
      const c = event.data;
      const visitor = join(c.visitor_name, c.kiosk_name);
      if (c.status === "ringing") return { key: `call:${c.id}:ringing`, title: `Calling ${c.unit_display}`, body: visitor, href: "/intercom/", tone: "blue" };
      if (c.status === "approved") return { key: `call:${c.id}:approved`, title: `${c.unit_display} let the visitor in`, body: visitor, href: "/intercom/", tone: "green" };
      if (c.status === "rejected") return { key: `call:${c.id}:rejected`, title: `${c.unit_display} turned the visitor away`, body: visitor, href: "/intercom/", tone: "red" };
      if (c.status === "missed") return { key: `call:${c.id}:missed`, title: `Missed call to ${c.unit_display}`, body: visitor, href: "/intercom/", tone: "amber" };
      return null;
    }
    case "visit": {
      const v = event.data;
      return v.checked_out_at
        ? { key: `visit:${v.id}:out`, title: `Checked out · ${v.pass_number}`, body: join(v.visitor_name, v.unit_display), href: "/visits/", tone: "slate" }
        : { key: `visit:${v.id}:in`, title: `Visitor in · ${v.pass_number}`, body: join(v.visitor_name, v.unit_display, v.source_display), href: "/visits/", tone: "blue" };
    }
    case "booking": {
      const b = event.data;
      const body = join(b.facility_name, b.unit_display, formatDateTime(b.starts_at));
      const title = { confirmed: "Booking confirmed", pending_payment: "New booking, awaiting payment", cancelled: "Booking cancelled", expired: "Booking payment expired" }[b.status];
      return { key: `booking:${b.id}:${b.status}`, title, body, href: "/bookings/", tone: b.status === "confirmed" ? "green" : b.status === "pending_payment" ? "amber" : "slate" };
    }
    case "feedback": {
      const f = event.data;
      return { key: `feedback:${f.id}`, title: `New feedback · ${f.rating} ★`, body: join(f.unit_display, f.comment), href: "/feedback/", tone: f.rating <= 2 ? "red" : "amber" };
    }
  }
}

function load(): Stored {
  try {
    const stored = JSON.parse(localStorage.getItem(KEY) ?? "") as Stored;
    if (Array.isArray(stored.items)) return stored;
  } catch {}
  return { items: [], readAt: new Date().toISOString() };
}

function save(stored: Stored) {
  try {
    localStorage.setItem(KEY, JSON.stringify(stored));
  } catch {}
}

export function NotificationBell() {
  const { condo } = useSession();
  const [stored, setStored] = useState<Stored | null>(null);
  const [open, setOpen] = useState(false);
  useEffect(() => setStored(load()), []);

  const update = (change: (s: Stored) => Stored) => setStored((current) => {
    const next = change(current ?? load());
    save(next);
    return next;
  });

  useLiveEvents((event) => {
    const note = describe(event);
    if (!note) return;
    update((s) => s.items.some((n) => n.key === note.key) ? s : {
      ...s,
      items: [{ ...note, condo: event.data.condominium, at: new Date().toISOString() }, ...s.items].slice(0, LIMIT),
    });
  });

  const items = (stored?.items ?? []).filter((n) => n.condo === condo.id);
  const unread = stored ? items.filter((n) => n.at > stored.readAt).length : 0;
  const toggle = () => {
    // Opening marks everything read; the dots stay until the panel closes.
    if (open) update((s) => ({ ...s, readAt: new Date().toISOString() }));
    setOpen(!open);
  };
  const close = () => {
    update((s) => ({ ...s, readAt: new Date().toISOString() }));
    setOpen(false);
  };

  return (
    <div className="relative">
      <button
        onClick={toggle}
        className="relative rounded-md p-2 text-muted hover:bg-surface-3 hover:text-ink"
        aria-label={unread ? `Notifications, ${unread} new` : "Notifications"}
        aria-haspopup="menu"
        aria-expanded={open}
        title="Notifications"
      >
        <Icon name="bell" className="h-5 w-5" />
        {unread > 0 && (
          <span className="absolute right-1 top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-rose-500 px-1 text-[10px] font-semibold leading-none text-white">
            {unread > 9 ? "9+" : unread}
          </span>
        )}
      </button>
      {open && (
        <>
          <div className="fixed inset-0 z-10" onClick={close} />
          <div role="menu" className="absolute right-0 z-20 mt-2 w-[min(22rem,calc(100vw-2rem))] rounded-lg border border-line bg-surface shadow-card">
            <div className="flex items-center justify-between border-b border-line px-4 py-2.5">
              <span className="text-sm font-semibold text-ink">Notifications</span>
              {items.length > 0 && (
                <button className="text-xs text-muted hover:text-ink" onClick={() => update((s) => ({ ...s, items: s.items.filter((n) => n.condo !== condo.id) }))}>
                  Clear
                </button>
              )}
            </div>
            {items.length === 0 ? (
              <p className="px-4 py-8 text-center text-sm text-muted">No activity yet. Check-ins, calls, gate openings, bookings and feedback appear here as they happen.</p>
            ) : (
              <ul className="max-h-[26rem] divide-y divide-line overflow-y-auto">
                {items.map((n) => (
                  <li key={n.key}>
                    <Link href={n.href} onClick={close} className="flex gap-3 px-4 py-2.5 hover:bg-surface-2">
                      <span className={cx("mt-1.5 h-2 w-2 shrink-0 rounded-full", DOT[n.tone], stored && n.at <= stored.readAt && "opacity-30")} />
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-sm font-medium text-ink">{n.title}</span>
                        {n.body && <span className="block truncate text-xs text-muted">{n.body}</span>}
                      </span>
                      <span className="shrink-0 text-[11px] text-muted">{timeAgo(n.at)}</span>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </>
      )}
    </div>
  );
}
