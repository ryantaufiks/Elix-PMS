"use client";

import Link from "next/link";
import { useState } from "react";
import useSWR from "swr";

import { AccessTable } from "@/components/AccessTable";
import { OpenGateDialog, useGates } from "@/components/bits";
import { Icon, type IconName } from "@/components/icons";
import { Badge, Button, Card, CardHeader, cx, Loading, PageHeader } from "@/components/ui";
import { query } from "@/lib/api";
import { useLiveEvents } from "@/lib/live";
import { useSession } from "@/lib/session";
import type { AccessLog, Gate, Page, Summary } from "@/lib/types";

const RING = { blue: "#3a57e8", green: "#1aa053", red: "#c03221", amber: "#f16a1b", teal: "#08b1ba" };

/** Stat card with a progress ring around an icon. ``share`` (0-1) fills the ring; omit for a full ring. */
function Stat({ label, value, icon, color, share, href }: {
  label: string; value: React.ReactNode; icon: IconName; color: keyof typeof RING; share?: number; href?: string;
}) {
  const r = 26;
  const c = 2 * Math.PI * r;
  const filled = share === undefined ? 0.75 : Math.max(0.04, Math.min(1, share));
  const body = (
    <Card className={cx("flex items-center gap-4 p-5", href && "transition-transform hover:-translate-y-0.5")}>
      <div className="relative h-16 w-16 shrink-0">
        <svg viewBox="0 0 64 64" className="h-16 w-16 -rotate-90" aria-hidden="true">
          <circle cx="32" cy="32" r={r} fill="none" stroke="#e9ecef" strokeWidth="4" />
          <circle cx="32" cy="32" r={r} fill="none" stroke={RING[color]} strokeWidth="4" strokeLinecap="round" strokeDasharray={`${c * filled} ${c}`} />
        </svg>
        <span className="absolute inset-0 flex items-center justify-center" style={{ color: RING[color] }}>
          <Icon name={icon} className="h-6 w-6" />
        </span>
      </div>
      <div className="min-w-0">
        <div className="truncate text-sm text-muted">{label}</div>
        <div className="mt-0.5 text-2xl font-semibold tabular-nums text-ink">{value}</div>
      </div>
    </Card>
  );
  return href ? <Link href={href}>{body}</Link> : body;
}

export default function OverviewPage() {
  const { condo, isAdmin, me } = useSession();
  const [opening, setOpening] = useState<Gate | null>(null);
  const summary = useSWR<Summary>(`/v1/dashboard/summary/${query({ condominium: condo.id })}`, { refreshInterval: 60_000 });
  const logs = useSWR<Page<AccessLog>>(`/v1/access-logs/${query({ condominium: condo.id, page_size: 15 })}`);
  const gates = useGates(condo.id);
  const [fresh, setFresh] = useState<Set<number>>(new Set());

  useLiveEvents((event) => {
    if (event.data.condominium !== condo.id) return;
    summary.mutate();
    if (event.type === "access_log") {
      logs.mutate((page) => page && { ...page, results: [event.data, ...page.results.filter((l) => l.id !== event.data.id)].slice(0, 15) }, { revalidate: false });
      setFresh((s) => new Set(s).add(event.data.id));
    }
  });

  const s = summary.data;
  const deviceIssues = s ? s.relays_failing + s.cameras_offline + s.kiosks_offline : 0;
  const devicesTotal = s ? s.relays_total + s.cameras_total + s.kiosks_total : 0;
  const decided = s ? s.granted_today + s.denied_today + s.errors_today : 0;
  const hour = Number(new Intl.DateTimeFormat("en-SG", { hour: "numeric", hour12: false, timeZone: "Asia/Singapore" }).format(new Date()));
  const greeting = hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening";
  const activeGates = (gates.data?.results ?? []).filter((g) => g.is_active);

  return (
    <>
      <PageHeader title={`${greeting}, ${me.first_name || me.username}!`} description={`Here is what is happening at ${condo.name} today.`} />
      <div className="grid gap-5 sm:grid-cols-2 xl:grid-cols-3">
        <Stat label="Entries granted today" value={s?.granted_today ?? "–"} icon="arrowUp" color="blue" share={decided ? (s!.granted_today / decided) : 0} href="/access/" />
        <Stat label="Denied today" value={s?.denied_today ?? "–"} icon="arrowDown" color="red" share={decided ? (s!.denied_today / decided) : 0} href="/access/" />
        <Stat label="Invitations valid today" value={s?.invitations_today ?? "–"} icon="ticket" color="teal" href="/invitations/" />
        <Stat label="Intercom calls ringing" value={s?.open_calls ?? "–"} icon="phone" color={s?.open_calls ? "amber" : "blue"} share={s?.open_calls ? 1 : 0} href="/intercom/" />
        <Stat label="Relay errors today" value={s?.errors_today ?? "–"} icon="cpu" color={s?.errors_today ? "red" : "green"} share={decided ? (s!.errors_today / decided) : 0} href="/access/" />
        <Stat label="Devices needing attention" value={s ? `${deviceIssues} / ${devicesTotal}` : "–"} icon="shield" color={deviceIssues ? "amber" : "green"}
          share={devicesTotal ? (devicesTotal - deviceIssues) / devicesTotal : 1} href={isAdmin ? "/setup/devices/" : undefined} />
      </div>
      {s && s.lpr_enabled === false && (
        <div className="mt-5 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
          Licence-plate recognition is switched off for this site: camera events are recorded but never open a gate.
        </div>
      )}

      <div className="mt-6 grid gap-6 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardHeader title="Latest access" action={<Link href="/access/" className="text-sm font-medium text-primary-600 hover:underline">View all</Link>} />
          {logs.data ? <AccessTable logs={logs.data.results} highlight={fresh} /> : <Loading />}
        </Card>
        <Card>
          <CardHeader title="Open a gate" />
          {!gates.data ? (
            <Loading />
          ) : activeGates.length === 0 ? (
            <p className="px-5 py-6 text-sm text-muted">No active gates yet.{isAdmin && <> Add them under <Link className="font-medium text-primary-600 hover:underline" href="/setup/devices/">Gates &amp; devices</Link>.</>}</p>
          ) : (
            <ul className="divide-y divide-slate-100">
              {activeGates.map((gate) => (
                <li key={gate.id} className="flex items-center justify-between gap-3 px-5 py-3.5">
                  <div>
                    <div className="text-sm font-medium text-slate-800">{gate.name}</div>
                    <div className="mt-0.5 flex gap-1.5">
                      <Badge>{gate.gate_type}</Badge>
                      <Badge>{gate.direction}</Badge>
                    </div>
                  </div>
                  <Button variant="primary" size="sm" onClick={() => setOpening(gate)}>
                    <Icon name="unlock" className="h-4 w-4" /> Open
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
      <OpenGateDialog gate={opening} onClose={() => setOpening(null)} />
    </>
  );
}
