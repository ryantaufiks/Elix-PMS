"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import useSWR from "swr";

import { query } from "@/lib/api";
import { useLiveEvents, useLiveStatus } from "@/lib/live";
import { useSession } from "@/lib/session";
import type { IntercomCall, Page } from "@/lib/types";

import { Icon, type IconName } from "./icons";
import { cx, Select } from "./ui";

const NAV: { href: string; label: string; icon: IconName; adminOnly?: boolean }[] = [
  { href: "/", label: "Overview", icon: "home" },
  { href: "/access/", label: "Access log", icon: "list" },
  { href: "/intercom/", label: "Intercom", icon: "phone" },
  { href: "/gates/", label: "Gates", icon: "gate" },
  { href: "/invitations/", label: "Invitations", icon: "ticket" },
  { href: "/vehicles/", label: "Vehicles", icon: "car" },
  { href: "/residents/", label: "Residents", icon: "users" },
  { href: "/devices/", label: "Devices", icon: "cpu", adminOnly: true },
];

export function Shell({ children }: { children: React.ReactNode }) {
  const { me, condos, condo, role, isAdmin, selectCondo, logout } = useSession();
  const pathname = usePathname();
  const live = useLiveStatus();
  const [menuOpen, setMenuOpen] = useState(false);
  useEffect(() => setMenuOpen(false), [pathname]);

  const nav = NAV.filter((item) => !item.adminOnly || isAdmin);
  const isActive = (href: string) => (href === "/" ? pathname === "/" : pathname.startsWith(href));

  const sidebar = (
    <nav className="flex h-full flex-col">
      <div className="flex h-16 items-center gap-2 px-5">
        <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-teal-700 text-sm font-bold text-white">E</span>
        <span className="text-base font-semibold text-slate-900">Elix PMS</span>
      </div>
      <div className="px-3 pb-4">
        {condos.length > 1 ? (
          <Select value={condo.id} onChange={(e) => selectCondo(Number(e.target.value))} aria-label="Condominium">
            {condos.map((c) => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
          </Select>
        ) : (
          <div className="rounded-lg bg-slate-100 px-3 py-2 text-sm font-medium text-slate-700">{condo.name}</div>
        )}
      </div>
      <ul className="flex-1 space-y-0.5 px-3">
        {nav.map((item) => (
          <li key={item.href}>
            <Link
              href={item.href}
              className={cx(
                "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium",
                isActive(item.href) ? "bg-teal-50 text-teal-800" : "text-slate-600 hover:bg-slate-100 hover:text-slate-900",
              )}
            >
              <Icon name={item.icon} className="h-5 w-5 shrink-0" />
              {item.label}
            </Link>
          </li>
        ))}
      </ul>
      <div className="border-t border-slate-200 p-3">
        <div className="px-3 py-2">
          <div className="truncate text-sm font-medium text-slate-800">{[me.first_name, me.last_name].filter(Boolean).join(" ") || me.username}</div>
          <div className="text-xs text-slate-500">{me.is_superuser ? "Superuser" : role === "admin" ? "Condo admin" : "Security"}</div>
        </div>
        {me.is_superuser && (
          <a href="/v1/admin/" className="flex items-center gap-3 rounded-lg px-3 py-2 text-sm text-slate-600 hover:bg-slate-100">
            <Icon name="external" className="h-4 w-4" /> Django admin
          </a>
        )}
        <button onClick={logout} className="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm text-slate-600 hover:bg-slate-100">
          <Icon name="logout" className="h-4 w-4" /> Sign out
        </button>
      </div>
    </nav>
  );

  return (
    <div className="min-h-screen bg-slate-50">
      <aside className="fixed inset-y-0 left-0 hidden w-64 border-r border-slate-200 bg-white lg:block">{sidebar}</aside>
      {menuOpen && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 bg-slate-900/40" onClick={() => setMenuOpen(false)} />
          <aside className="absolute inset-y-0 left-0 w-72 bg-white shadow-xl">{sidebar}</aside>
        </div>
      )}
      <div className="lg:pl-64">
        <header className="sticky top-0 z-30 flex h-14 items-center gap-3 border-b border-slate-200 bg-white/90 px-4 backdrop-blur sm:px-6">
          <button className="rounded-md p-1.5 text-slate-600 hover:bg-slate-100 lg:hidden" onClick={() => setMenuOpen(true)} aria-label="Open menu">
            <Icon name="menu" />
          </button>
          <span className="truncate text-sm font-medium text-slate-700 lg:hidden">{condo.name}</span>
          <div className="ml-auto flex items-center gap-2 text-xs text-slate-500" title={live ? "Receiving live events" : "Reconnecting to live events…"}>
            <span className={cx("h-2 w-2 rounded-full", live ? "bg-emerald-500" : "animate-pulse bg-amber-500")} />
            {live ? "Live" : "Reconnecting"}
          </div>
        </header>
        <IncomingCalls />
        <main className="mx-auto max-w-7xl px-4 py-6 sm:px-6">{children}</main>
      </div>
    </div>
  );
}

/** Banner + ringtone while a kiosk at this condo is ringing. */
function IncomingCalls() {
  const { condo } = useSession();
  const pathname = usePathname();
  const [calls, setCalls] = useState<Record<number, IntercomCall>>({});
  const [muted, setMuted] = useState(false);

  const { data } = useSWR<Page<IntercomCall>>(`/v1/intercom-calls/${query({ condominium: condo.id, status: "ringing" })}`);
  useEffect(() => {
    setCalls(Object.fromEntries((data?.results ?? []).filter((c) => c.is_open).map((c) => [c.id, c])));
  }, [data]);

  useLiveEvents((event) => {
    if (event.type !== "intercom_call" || event.data.condominium !== condo.id) return;
    setCalls((current) => {
      const next = { ...current };
      if (event.data.status === "ringing" && event.data.is_open) next[event.data.id] = event.data;
      else delete next[event.data.id];
      return next;
    });
  });

  const ringing = Object.values(calls);
  useRingtone(ringing.length > 0 && !muted);
  useEffect(() => {
    if (ringing.length === 0) setMuted(false);
  }, [ringing.length]);

  if (ringing.length === 0) return null;
  return (
    <div className="border-b border-sky-200 bg-sky-50 px-4 py-3 sm:px-6">
      <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-3">
        <Icon name="bell" className="h-5 w-5 animate-pulse text-sky-700" />
        <div className="flex-1 text-sm text-sky-900">
          {ringing.map((call) => (
            <div key={call.id}>
              <strong>{call.unit_display}</strong> is being called from {call.kiosk_name || "a kiosk"}
              {call.visitor_name && <> · visitor {call.visitor_name}</>}
            </div>
          ))}
        </div>
        <button className="text-sm text-sky-700 hover:underline" onClick={() => setMuted(true)}>{muted ? "Muted" : "Mute"}</button>
        {!pathname.startsWith("/intercom") && (
          <Link href="/intercom/" className="rounded-lg bg-sky-700 px-3 py-1.5 text-sm font-medium text-white hover:bg-sky-800">
            Go to intercom
          </Link>
        )}
      </div>
    </div>
  );
}

function useRingtone(active: boolean) {
  const context = useRef<AudioContext | null>(null);
  useEffect(() => {
    if (!active) return;
    const beep = () => {
      try {
        context.current ??= new AudioContext();
        const ctx = context.current;
        for (const offset of [0, 0.25]) {
          const osc = ctx.createOscillator();
          const gain = ctx.createGain();
          osc.frequency.value = 880;
          gain.gain.setValueAtTime(0.0001, ctx.currentTime + offset);
          gain.gain.exponentialRampToValueAtTime(0.2, ctx.currentTime + offset + 0.02);
          gain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + offset + 0.2);
          osc.connect(gain).connect(ctx.destination);
          osc.start(ctx.currentTime + offset);
          osc.stop(ctx.currentTime + offset + 0.22);
        }
      } catch {}
    };
    beep();
    const id = setInterval(beep, 2000);
    return () => clearInterval(id);
  }, [active]);
}
