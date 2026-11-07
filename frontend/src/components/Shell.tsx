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

type NavItem = { href: string; label: string; icon: IconName; admin?: boolean; superuser?: boolean };
const NAV: { title: string; items: NavItem[] }[] = [
  {
    title: "Operations",
    items: [
      { href: "/", label: "Dashboard", icon: "home" },
      { href: "/access/", label: "Access log", icon: "list" },
      { href: "/intercom/", label: "Intercom", icon: "phone" },
      { href: "/gates/", label: "Open gates", icon: "unlock" },
      { href: "/invitations/", label: "Invitations", icon: "ticket" },
    ],
  },
  {
    title: "Community",
    items: [
      { href: "/residents/", label: "Residents", icon: "users" },
      { href: "/vehicles/", label: "Vehicles", icon: "car" },
      { href: "/staff/", label: "Staff", icon: "shield", admin: true },
    ],
  },
  {
    title: "Site setup",
    items: [
      { href: "/setup/site/", label: "Site settings", icon: "sliders", admin: true },
      { href: "/setup/units/", label: "Blocks & units", icon: "grid", admin: true },
      { href: "/setup/devices/", label: "Gates & devices", icon: "cpu", admin: true },
    ],
  },
  {
    title: "Platform",
    items: [
      { href: "/platform/condominiums/", label: "Condominiums", icon: "building", superuser: true },
      { href: "/platform/system/", label: "System settings", icon: "settings", superuser: true },
    ],
  },
];

function initials(name: string) {
  return name.split(/\s+/).filter(Boolean).slice(0, 2).map((p) => p[0]?.toUpperCase()).join("") || "?";
}

export function Shell({ children }: { children: React.ReactNode }) {
  const { me, condos, condo, role, isAdmin, selectCondo, logout } = useSession();
  const pathname = usePathname();
  const live = useLiveStatus();
  const [menuOpen, setMenuOpen] = useState(false);
  const [userOpen, setUserOpen] = useState(false);
  useEffect(() => {
    setMenuOpen(false);
    setUserOpen(false);
  }, [pathname]);

  const isActive = (href: string) => (href === "/" ? pathname === "/" : pathname.startsWith(href));
  const groups = NAV.map((g) => ({
    ...g,
    items: g.items.filter((i) => (!i.admin || isAdmin) && (!i.superuser || me.is_superuser)),
  })).filter((g) => g.items.length);
  const name = [me.first_name, me.last_name].filter(Boolean).join(" ") || me.username;
  const roleLabel = me.is_superuser ? "Platform admin" : role === "admin" ? "Condo admin" : "Security";

  const sidebar = (
    <nav className="flex h-full flex-col">
      <div className="flex h-[70px] shrink-0 items-center gap-2.5 border-b border-slate-100 px-6">
        <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary-500 text-base font-bold text-white shadow-primary">E</span>
        <span className="text-xl font-semibold tracking-tight text-ink">Elix PMS</span>
      </div>
      <div className="flex-1 overflow-y-auto px-4 py-4">
        {groups.map((group) => (
          <div key={group.title} className="mb-5">
            <div className="mb-2 px-3 text-xs font-semibold uppercase tracking-wider text-muted">{group.title}</div>
            <ul className="space-y-1">
              {group.items.map((item) => (
                <li key={item.href}>
                  <Link
                    href={item.href}
                    className={cx(
                      "flex items-center gap-3 rounded-md px-3 py-2.5 text-sm font-medium transition-all",
                      isActive(item.href) ? "bg-primary-500 text-white shadow-primary" : "text-slate-500 hover:bg-primary-50 hover:text-primary-600",
                    )}
                  >
                    <Icon name={item.icon} className="h-5 w-5 shrink-0" />
                    {item.label}
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
      <div className="border-t border-slate-100 px-6 py-4 text-xs text-muted">
        <span className={cx("mr-2 inline-block h-2 w-2 rounded-full", live ? "bg-emerald-500" : "animate-pulse bg-amber-500")} />
        {live ? "Live events connected" : "Reconnecting to live events…"}
      </div>
    </nav>
  );

  return (
    <div className="min-h-screen bg-canvas">
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-64 bg-white shadow-[0_0_30px_0_rgb(58_87_232/0.05)] lg:block">{sidebar}</aside>
      {menuOpen && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 bg-slate-900/40" onClick={() => setMenuOpen(false)} />
          <aside className="absolute inset-y-0 left-0 w-72 bg-white shadow-xl">{sidebar}</aside>
        </div>
      )}
      <div className="lg:pl-64">
        <header className="sticky top-0 z-20 flex h-[70px] items-center gap-3 bg-white px-4 shadow-[0_0_30px_0_rgb(58_87_232/0.05)] sm:px-8">
          <button className="rounded-md p-1.5 text-slate-500 hover:bg-slate-100 lg:hidden" onClick={() => setMenuOpen(true)} aria-label="Open menu">
            <Icon name="menu" />
          </button>
          <div className="flex min-w-0 items-center gap-2">
            <Icon name="building" className="hidden h-5 w-5 shrink-0 text-muted sm:block" />
            {condos.length > 1 ? (
              <Select value={condo.id} onChange={(e) => selectCondo(Number(e.target.value))} aria-label="Condominium" className="max-w-[16rem] border-transparent bg-slate-50 font-medium">
                {condos.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
              </Select>
            ) : (
              <span className="truncate text-sm font-medium text-ink">{condo.name}</span>
            )}
          </div>
          <div className="relative ml-auto">
            <button onClick={() => setUserOpen((o) => !o)} className="flex items-center gap-3 rounded-lg px-2 py-1.5 hover:bg-slate-50">
              <span className="flex h-10 w-10 items-center justify-center rounded-full bg-primary-100 text-sm font-semibold text-primary-600">{initials(name)}</span>
              <span className="hidden text-left sm:block">
                <span className="block text-sm font-medium text-ink">{name}</span>
                <span className="block text-xs text-muted">{roleLabel}</span>
              </span>
            </button>
            {userOpen && (
              <>
                <div className="fixed inset-0 z-10" onClick={() => setUserOpen(false)} />
                <div className="absolute right-0 z-20 mt-2 w-56 rounded-lg bg-white py-2 shadow-lg ring-1 ring-slate-100">
                  {me.is_superuser && (
                    <a href="/v1/admin/" className="flex items-center gap-3 px-4 py-2 text-sm text-slate-600 hover:bg-slate-50">
                      <Icon name="external" className="h-4 w-4" /> Django admin (advanced)
                    </a>
                  )}
                  <button onClick={logout} className="flex w-full items-center gap-3 px-4 py-2 text-sm text-slate-600 hover:bg-slate-50">
                    <Icon name="logout" className="h-4 w-4" /> Sign out
                  </button>
                </div>
              </>
            )}
          </div>
        </header>
        <IncomingCalls />
        <div className="relative">
          <div className="hero-band absolute inset-x-0 top-0 h-60" aria-hidden="true" />
          <main className="relative mx-auto max-w-7xl px-4 pb-10 pt-8 sm:px-8">{children}</main>
        </div>
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
    <div className="border-b border-sky-200 bg-sky-50 px-4 py-3 sm:px-8">
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
