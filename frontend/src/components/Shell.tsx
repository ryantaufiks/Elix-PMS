"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import useSWR from "swr";

import { query } from "@/lib/api";
import { ROLE_LABEL, visitPurpose } from "@/lib/format";
import { useLiveEvents, useLiveStatus } from "@/lib/live";
import { useSession } from "@/lib/session";
import type { IntercomCall, LiveKitConnection, Page } from "@/lib/types";

import { Icon, type IconName } from "./icons";
import { ActiveCall } from "./IntercomCall";
import { NotificationBell } from "./Notifications";
import { useTheme } from "@/lib/theme";

import { cx, useToast } from "./ui";
import { Credit } from "./Credit";
import { SitePicker } from "./SitePicker";
import { SubscriptionBanner } from "./SubscriptionBanner";

type NavItem = { href: string; label: string; icon: IconName; admin?: boolean; superuser?: boolean; module?: string };
const NAV: { title: string; items: NavItem[] }[] = [
  {
    title: "Operations",
    items: [
      { href: "/dashboard/", label: "Dashboard", icon: "home" },
      { href: "/access/", label: "Access log", icon: "list" },
      { href: "/intercom/", label: "Intercom", icon: "phone", module: "intercom" },
      { href: "/visits/", label: "Visitor list", icon: "clipboard" },
      { href: "/gates/", label: "Open gates", icon: "unlock" },
      { href: "/invitations/", label: "Invitations", icon: "ticket" },
      { href: "/bookings/", label: "Bookings", icon: "calendar", module: "facilities" },
      { href: "/reports/", label: "Reports", icon: "report" },
    ],
  },
  {
    title: "Community",
    items: [
      { href: "/residents/", label: "Residents", icon: "users" },
      { href: "/vehicles/", label: "Vehicles", icon: "car" },
      { href: "/feedback/", label: "Feedback", icon: "star", module: "resident_app" },
      { href: "/staff/", label: "Staff", icon: "shield", admin: true },
    ],
  },
  {
    title: "Site setup",
    items: [
      { href: "/setup/site/", label: "Site settings", icon: "sliders", admin: true },
      { href: "/setup/units/", label: "Blocks & units", icon: "grid", admin: true },
      { href: "/setup/devices/", label: "Gates & devices", icon: "cpu", admin: true },
      { href: "/setup/facilities/", label: "Facilities & payments", icon: "calendar", admin: true, module: "facilities" },
      { href: "/setup/assistant/", label: "AI Assistant", icon: "sparkle", admin: true, module: "ai_concierge" },
    ],
  },
  {
    title: "Platform",
    items: [
      { href: "/platform/condominiums/", label: "Condominiums", icon: "building", superuser: true },
      { href: "/platform/plans/", label: "Plans", icon: "tag", superuser: true },
      { href: "/platform/usage/", label: "Usage", icon: "report", superuser: true },
      { href: "/platform/system/", label: "System settings", icon: "settings", superuser: true },
      { href: "/platform/backups/", label: "Backups", icon: "archive", superuser: true },
    ],
  },
];

const CLOSED_KEY = "elix.sidebar-closed";

/** Sidebar groups the user folded away; remembered per browser. */
function useClosedGroups(): [Set<string>, (title: string, closed: boolean) => void] {
  const [closed, setClosed] = useState<Set<string>>(new Set());
  useEffect(() => {
    try {
      setClosed(new Set(JSON.parse(localStorage.getItem(CLOSED_KEY) ?? "[]")));
    } catch {}
  }, []);
  const set = (title: string, close: boolean) => setClosed((current) => {
    if (current.has(title) === close) return current;
    const next = new Set(current);
    if (close) next.add(title);
    else next.delete(title);
    try {
      localStorage.setItem(CLOSED_KEY, JSON.stringify([...next]));
    } catch {}
    return next;
  });
  return [closed, set];
}

function initials(name: string) {
  return name.split(/\s+/).filter(Boolean).slice(0, 2).map((p) => p[0]?.toUpperCase()).join("") || "?";
}

export function Shell({ children }: { children: React.ReactNode }) {
  const { me, condo, role, isAdmin, logout } = useSession();
  const pathname = usePathname();
  const live = useLiveStatus();
  const [theme, toggleTheme] = useTheme();
  const [menuOpen, setMenuOpen] = useState(false);
  const [userOpen, setUserOpen] = useState(false);
  const [closed, setGroupClosed] = useClosedGroups();
  useEffect(() => {
    setMenuOpen(false);
    setUserOpen(false);
  }, [pathname]);

  const isActive = (href: string) => pathname.startsWith(href);
  const groups = NAV.map((g) => ({
    ...g,
    items: g.items.filter((i) => (!i.admin || isAdmin) && (!i.superuser || me.is_superuser)),
  })).filter((g) => g.items.length);
  const current = groups.flatMap((g) => g.items.map((i) => ({ ...i, group: g.title }))).find((i) => isActive(i.href));
  // Reaching a page in a folded group (e.g. from a notification) unfolds it.
  useEffect(() => {
    if (current) setGroupClosed(current.group, false);
  }, [current?.group]); // eslint-disable-line react-hooks/exhaustive-deps
  const name = [me.first_name, me.last_name].filter(Boolean).join(" ") || me.username;
  const roleLabel = me.is_superuser ? "Platform admin" : ROLE_LABEL[role];
  // Short screens (tablets) hide the Platform group below the fold: show a fade while there is more to scroll.
  const navScroll = useRef<HTMLDivElement>(null);
  const [navMore, setNavMore] = useState(false);
  const checkNavScroll = useCallback(() => {
    const el = navScroll.current;
    if (el) setNavMore(el.scrollHeight - el.scrollTop - el.clientHeight > 8);
  }, []);
  useEffect(() => {
    checkNavScroll();
    window.addEventListener("resize", checkNavScroll);
    return () => window.removeEventListener("resize", checkNavScroll);
  }, [checkNavScroll, closed, menuOpen]);

  const sidebar = (
    <nav className="sidebar-bg flex h-full flex-col text-slate-300">
      <div className="flex h-16 shrink-0 items-center px-6">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src="/brand/elix-logo.png" alt="Elix" className="h-7 w-auto drop-shadow-[0_0_12px_rgba(47,111,255,0.45)]" />
        <span className="ml-2.5 mt-1 rounded border border-white/15 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-widest text-slate-400">PMS</span>
      </div>
      <div className="mx-4 mb-2 rounded-lg border border-white/10 bg-white/5 p-1">
        <SitePicker />
      </div>
      <div className="relative min-h-0 flex-1">
      <div ref={navScroll} onScroll={checkNavScroll} className="h-full overflow-y-auto px-3 py-3">
        {groups.map((group) => {
          const open = !closed.has(group.title);
          return (
            <div key={group.title} className="mb-3">
              <button
                onClick={() => setGroupClosed(group.title, open)}
                aria-expanded={open}
                className="flex w-full items-center justify-between rounded-md px-3 py-1.5 text-[11px] font-semibold uppercase tracking-wider text-slate-500 hover:text-slate-300"
              >
                {group.title}
                <Icon name="chevron" className={cx("h-3.5 w-3.5 transition-transform", open && "rotate-90")} />
              </button>
              {open && (
                <ul className="mt-0.5 space-y-0.5">
                  {group.items.map((item) => {
                    const active = isActive(item.href);
                    const locked = item.module ? !condo.modules?.includes(item.module) : false;
                    return (
                      <li key={item.href}>
                        <Link
                          href={item.href}
                          aria-current={active ? "page" : undefined}
                          className={cx(
                            "relative flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                            active ? "bg-primary-500/15 text-white" : "text-slate-400 hover:bg-white/5 hover:text-white",
                          )}
                        >
                          {active && <span className="absolute inset-y-1.5 left-0 w-[3px] rounded-r bg-primary-400 shadow-[0_0_10px_rgba(91,147,255,0.9)]" />}
                          <Icon name={item.icon} className={cx("h-[18px] w-[18px] shrink-0", active ? "text-primary-300" : "text-slate-500")} />
                          {item.label}
                          {locked && <Icon name="lock" className="ml-auto h-3.5 w-3.5 text-slate-500" />}
                        </Link>
                      </li>
                    );
                  })}
                </ul>
              )}
            </div>
          );
        })}
      </div>
      {navMore && (
        <div className="pointer-events-none absolute inset-x-0 bottom-0 flex h-12 items-end justify-center bg-gradient-to-t from-navy-900 to-transparent pb-1 text-slate-400" aria-hidden="true">
          <Icon name="chevron" className="h-4 w-4 rotate-90" />
        </div>
      )}
      </div>
      <div className="border-t border-white/10 px-6 py-4 text-xs text-slate-500">
        Elix PMS · Singapore
      </div>
    </nav>
  );

  return (
    <div className="min-h-screen bg-canvas">
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-64 lg:block">{sidebar}</aside>
      {menuOpen && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 bg-slate-950/50" onClick={() => setMenuOpen(false)} />
          <aside className="absolute inset-y-0 left-0 w-72 shadow-xl">{sidebar}</aside>
        </div>
      )}
      <div className="lg:pl-64">
        <header className="sticky top-0 z-20 flex h-16 items-center gap-3 border-b border-line bg-surface/85 px-4 backdrop-blur sm:px-8">
          <button className="rounded-md p-1.5 text-muted hover:bg-surface-3 lg:hidden" onClick={() => setMenuOpen(true)} aria-label="Open menu">
            <Icon name="menu" />
          </button>
          {/* Where you are, as a breadcrumb: the page's own heading sits just below, so this stays quiet. */}
          <div className="flex min-w-0 items-center gap-1.5 text-sm">
            {current?.group && <><span className="hidden text-muted sm:inline">{current.group}</span><span className="hidden text-muted/60 sm:inline">›</span></>}
            <span className="truncate font-medium text-body">{current?.label ?? condo.name}</span>
          </div>
          <div className="ml-auto flex items-center gap-1.5 sm:gap-2">
            <span
              className={cx(
                "hidden items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium sm:inline-flex",
                live ? "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300" : "bg-amber-500/10 text-amber-700 dark:text-amber-300",
              )}
              title={live ? "Receiving live events" : "Reconnecting to live events"}
            >
              <span className={cx("h-1.5 w-1.5 rounded-full", live ? "bg-emerald-500" : "animate-pulse bg-amber-500")} />
              {live ? "Live" : "Reconnecting"}
            </span>
            <NotificationBell />
            <button
              onClick={toggleTheme}
              className="rounded-md p-2 text-muted hover:bg-surface-3 hover:text-ink"
              aria-label={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
              title={theme === "dark" ? "Light mode" : "Dark mode"}
            >
              <Icon name={theme === "dark" ? "sun" : "moon"} className="h-5 w-5" />
            </button>
            <div className="relative">
              <button onClick={() => setUserOpen((o) => !o)} className="flex items-center gap-2.5 rounded-lg py-1 pl-1 pr-2 hover:bg-surface-3" aria-haspopup="menu" aria-expanded={userOpen}>
                <span className="flex h-8 w-8 items-center justify-center rounded-full bg-gradient-to-br from-primary-400 to-primary-700 text-xs font-semibold text-white">{initials(name)}</span>
                <span className="hidden text-left md:block">
                  <span className="block text-sm font-medium leading-tight text-ink">{name}</span>
                  <span className="block text-xs leading-tight text-muted">{roleLabel}</span>
                </span>
              </button>
              {userOpen && (
                <>
                  <div className="fixed inset-0 z-10" onClick={() => setUserOpen(false)} />
                  <div role="menu" className="absolute right-0 z-20 mt-2 w-60 rounded-lg border border-line bg-surface py-1.5 shadow-card">
                    <div className="border-b border-line px-4 pb-2.5 pt-1.5">
                      <div className="truncate text-sm font-medium text-ink">{name}</div>
                      <div className="truncate text-xs text-muted">{me.email || me.username}</div>
                    </div>
                    {me.is_superuser && (
                      <a href="/v1/admin/" className="flex items-center gap-3 px-4 py-2 text-sm text-body hover:bg-surface-2">
                        <Icon name="external" className="h-4 w-4" /> Django admin (advanced)
                      </a>
                    )}
                    <button onClick={logout} className="flex w-full items-center gap-3 px-4 py-2 text-sm text-body hover:bg-surface-2">
                      <Icon name="logout" className="h-4 w-4" /> Sign out
                    </button>
                  </div>
                </>
              )}
            </div>
          </div>
        </header>
        <IncomingCalls />
        <WalkInAlerts />
        <SubscriptionBanner />
        <main className="mx-auto max-w-7xl px-4 pb-10 pt-6 sm:px-8 sm:pt-8">{children}</main>
        <Credit className="border-t border-line px-4 py-5" />
      </div>
    </div>
  );
}

/** Toast for security when a visitor registers as a walk-in at a kiosk. */
function WalkInAlerts() {
  const { condo } = useSession();
  const toast = useToast();
  const seen = useRef(new Set<number>());
  useLiveEvents((event) => {
    if (event.type !== "visit" || event.data.source !== "kiosk" || event.data.condominium !== condo.id || event.data.checked_out_at) return;
    if (seen.current.has(event.data.id)) return;
    seen.current.add(event.data.id);
    const w = event.data;
    toast("info", `Walk-in ${w.pass_number}: ${w.visitor_name}${visitPurpose(w.purpose, w.company) ? ` (${visitPurpose(w.purpose, w.company)})` : ""} for ${w.unit_display}`);
  });
  return null;
}

/** Pop-up + ringtone while a kiosk at this condo is ringing, on every page: answer, reject or open the gate
    right there. "Later" folds it into a banner; a call answered here stays in the pop-up until it ends.
    On the Intercom page the cards are already on screen, so only the banner shows there. */
function IncomingCalls() {
  const { condo } = useSession();
  const pathname = usePathname();
  const [calls, setCalls] = useState<Record<number, IntercomCall>>({});
  const [held, setHeld] = useState<Record<number, { call: IntercomCall; connection: LiveKitConnection }>>({});
  const [muted, setMuted] = useState(false);
  const [later, setLater] = useState<number[]>([]);

  const hasIntercom = condo.modules?.includes("intercom") ?? false;
  const { data } = useSWR<Page<IntercomCall>>(hasIntercom ? `/v1/intercom-calls/${query({ condominium: condo.id, status: "ringing" })}` : null);
  useEffect(() => {
    setCalls(Object.fromEntries((data?.results ?? []).filter((c) => c.is_open).map((c) => [c.id, c])));
  }, [data]);

  useLiveEvents((event) => {
    if (event.type !== "intercom_call" || event.data.condominium !== condo.id) return;
    const call = event.data;
    setCalls((current) => {
      const next = { ...current };
      if (call.status === "ringing" && call.is_open) next[call.id] = call;
      else delete next[call.id];
      return next;
    });
    setHeld((current) => {
      if (!current[call.id]) return current;
      const { [call.id]: mine, ...rest } = current;
      return call.is_open ? { ...rest, [call.id]: { ...mine, call } } : rest;
    });
  });

  const done = (id: number) => {
    setCalls(({ [id]: _, ...rest }) => rest);
    setHeld(({ [id]: _, ...rest }) => rest);
  };

  const ringing = Object.values(calls).filter((c) => !held[c.id]);
  useRingtone(ringing.length > 0 && !muted);
  useEffect(() => {
    if (ringing.length === 0) setMuted(false);
  }, [ringing.length]);

  const onIntercom = pathname.startsWith("/intercom");
  const shown = [...Object.values(held).map((h) => h.call), ...(onIntercom ? [] : ringing.filter((c) => !later.includes(c.id)))]
    .sort((a, b) => a.created_at.localeCompare(b.created_at));
  const folded = ringing.filter((c) => !shown.includes(c));

  return (
    <>
      {folded.length > 0 && (
        <div className="border-b border-primary-500/20 bg-primary-500/10 px-4 py-3 sm:px-8">
          <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-3">
            <Icon name="bell" className="h-5 w-5 animate-pulse text-primary-600 dark:text-primary-300" />
            <div className="flex-1 text-sm text-ink">
              {folded.map((call) => <div key={call.id}><CallLine call={call} /></div>)}
            </div>
            <button className="text-sm text-primary-600 hover:underline dark:text-primary-300" onClick={() => setMuted(true)}>{muted ? "Muted" : "Mute"}</button>
            {!onIntercom && (
              <button className="rounded-md bg-primary-500 px-3 py-1.5 text-sm font-medium text-white shadow-primary hover:bg-primary-600"
                onClick={() => setLater((ids) => ids.filter((id) => !folded.some((c) => c.id === id)))}>
                Show call
              </button>
            )}
          </div>
        </div>
      )}
      {shown.length > 0 && (
        // No close on a click outside: a ringing call should not vanish by accident.
        <div className="fixed inset-0 z-50 flex items-end justify-center bg-slate-900/50 sm:items-center sm:p-4">
          <div role="dialog" aria-modal="true" aria-label="Incoming call"
            className="max-h-[94vh] w-full overflow-y-auto rounded-t-2xl bg-surface-2 shadow-xl sm:max-w-fit sm:rounded-2xl">
            <div className="flex items-center gap-3 border-b border-line bg-surface px-5 py-3">
              <Icon name="bell" className={cx("h-5 w-5 text-primary-600 dark:text-primary-300", ringing.length > 0 && "animate-pulse")} />
              <h2 className="flex-1 text-base font-semibold text-ink">{shown.length > 1 ? `${shown.length} kiosk calls` : "Kiosk call"}</h2>
              {ringing.length > 0 && (
                <button className="text-sm text-primary-600 hover:underline dark:text-primary-300" onClick={() => setMuted(true)}>{muted ? "Muted" : "Mute"}</button>
              )}
              {shown.some((c) => !held[c.id]) && (
                <button className="rounded-md px-2 py-1 text-sm text-muted hover:bg-surface-3 hover:text-body"
                  onClick={() => setLater((ids) => [...ids, ...shown.filter((c) => !held[c.id]).map((c) => c.id)])}>
                  Later
                </button>
              )}
            </div>
            <div className={cx("grid gap-4 p-4", shown.length > 1 && "md:grid-cols-2")}>
              {shown.map((call) => (
                <div key={call.id} className="w-full sm:w-[26rem]">
                  <ActiveCall
                    call={call}
                    connection={held[call.id]?.connection}
                    onAnswered={(connection) => setHeld((all) => ({ ...all, [call.id]: { call: { ...call, status: "answered" }, connection } }))}
                    onDone={() => done(call.id)}
                  />
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </>
  );
}

function CallLine({ call }: { call: IntercomCall }) {
  const purpose = visitPurpose(call.visitor_purpose, call.visitor_company);
  return (
    <>
      {call.unit === null
        ? <><strong>A visitor is calling the guardhouse</strong> from {call.kiosk_name || "a kiosk"}</>
        : <><strong>{call.unit_display}</strong> is being called from {call.kiosk_name || "a kiosk"}</>}
      {call.visitor_name && <> · {call.visitor_name}</>}
      {purpose && <> ({purpose})</>}
    </>
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
