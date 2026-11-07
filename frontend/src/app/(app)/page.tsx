"use client";

import Link from "next/link";
import { useState } from "react";
import useSWR from "swr";

import { AccessTable } from "@/components/AccessTable";
import { OpenGateDialog, useGates } from "@/components/bits";
import { Icon } from "@/components/icons";
import { Badge, Button, Card, CardHeader, cx, Loading, PageHeader } from "@/components/ui";
import { query } from "@/lib/api";
import { useLiveEvents } from "@/lib/live";
import { useSession } from "@/lib/session";
import type { AccessLog, Gate, Page, Summary } from "@/lib/types";

function Stat({ label, value, tone, href }: { label: string; value: React.ReactNode; tone?: "red" | "amber" | "green"; href?: string }) {
  const body = (
    <Card className={cx("px-4 py-4", href && "transition-colors hover:border-teal-300")}>
      <div className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</div>
      <div className={cx("mt-1 text-2xl font-semibold tabular-nums", tone === "red" ? "text-rose-600" : tone === "amber" ? "text-amber-600" : tone === "green" ? "text-emerald-700" : "text-slate-900")}>
        {value}
      </div>
    </Card>
  );
  return href ? <Link href={href}>{body}</Link> : body;
}

export default function OverviewPage() {
  const { condo, isAdmin } = useSession();
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
  const activeGates = (gates.data?.results ?? []).filter((g) => g.is_active);

  return (
    <>
      <PageHeader title="Overview" description={`Today at ${condo.name}`} />
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        <Stat label="Entries granted" value={s?.granted_today ?? "–"} tone="green" href="/access/" />
        <Stat label="Denied" value={s?.denied_today ?? "–"} tone={s?.denied_today ? "red" : undefined} href="/access/" />
        <Stat label="Relay errors" value={s?.errors_today ?? "–"} tone={s?.errors_today ? "amber" : undefined} href="/access/" />
        <Stat label="Invitations today" value={s?.invitations_today ?? "–"} href="/invitations/" />
        <Stat label="Calls ringing" value={s?.open_calls ?? "–"} href="/intercom/" />
        <Stat label="Device issues" value={s ? deviceIssues : "–"} tone={deviceIssues ? "amber" : undefined} href={isAdmin ? "/devices/" : undefined} />
      </div>
      {s && s.lpr_enabled === false && (
        <div className="mt-4 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
          Licence-plate recognition is switched off for this site: camera events are recorded but never open a gate.
        </div>
      )}

      <div className="mt-6 grid gap-6 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardHeader title="Latest access" action={<Link href="/access/" className="text-sm font-medium text-teal-700 hover:underline">View all</Link>} />
          {logs.data ? <AccessTable logs={logs.data.results} highlight={fresh} /> : <Loading />}
        </Card>
        <Card>
          <CardHeader title="Open a gate" />
          {!gates.data ? (
            <Loading />
          ) : activeGates.length === 0 ? (
            <p className="px-4 py-6 text-sm text-slate-500">No active gates configured.</p>
          ) : (
            <ul className="divide-y divide-slate-100">
              {activeGates.map((gate) => (
                <li key={gate.id} className="flex items-center justify-between gap-3 px-4 py-3">
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
