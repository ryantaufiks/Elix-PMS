"use client";

import { useEffect, useState } from "react";
import useSWR from "swr";

import { CallStatusBadge } from "@/components/bits";
import { ActiveCall } from "@/components/IntercomCall";
import { Card, CardHeader, Empty, Loading, PageHeader, Pagination, Table, Td, Th } from "@/components/ui";
import { query } from "@/lib/api";
import { formatDateTime, formatTime, visitPurpose } from "@/lib/format";
import { useLiveEvents } from "@/lib/live";
import { useSession } from "@/lib/session";
import type { IntercomCall, LiveKitConnection, Page } from "@/lib/types";
import { ModuleGate } from "@/components/ModuleGate";

function IntercomPage() {
  const { condo } = useSession();
  const [page, setPage] = useState(1);
  const [connections, setConnections] = useState<Record<number, LiveKitConnection>>({});
  const [active, setActive] = useState<Record<number, IntercomCall>>({});

  const open = useSWR<Page<IntercomCall>>(`/v1/intercom-calls/${query({ condominium: condo.id, page_size: 20 })}`);
  const history = useSWR<Page<IntercomCall>>(`/v1/intercom-calls/${query({ condominium: condo.id, page })}`, { keepPreviousData: true });

  useEffect(() => {
    setActive(Object.fromEntries((open.data?.results ?? []).filter((c) => c.is_open).map((c) => [c.id, c])));
  }, [open.data]);

  useLiveEvents((event) => {
    if (event.type !== "intercom_call" || event.data.condominium !== condo.id) return;
    const call = event.data;
    setActive((current) => {
      const next = { ...current };
      if (call.is_open) next[call.id] = call;
      else delete next[call.id];
      return next;
    });
    if (!call.is_open) setConnections(({ [call.id]: _, ...rest }) => rest);
    history.mutate();
  });

  const done = (id: number) => {
    setConnections(({ [id]: _, ...rest }) => rest);
    open.mutate();
    history.mutate();
  };

  const calls = Object.values(active).sort((a, b) => b.created_at.localeCompare(a.created_at));

  return (
    <>
      <PageHeader title="Intercom" description="Answer kiosk calls from the guardhouse and let visitors in, including visitors who tap Call the guardhouse." />
      {!open.data ? (
        <Loading />
      ) : calls.length === 0 ? (
        <Card className="mb-6"><Empty>No calls right now. Incoming calls appear here and ring on every page.</Empty></Card>
      ) : (
        <div className="mb-6 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {calls.map((call) => (
            <ActiveCall
              key={call.id}
              call={call}
              connection={connections[call.id]}
              onAnswered={(c) => setConnections((all) => ({ ...all, [call.id]: c }))}
              onDone={() => done(call.id)}
            />
          ))}
        </div>
      )}
      <Card>
        <CardHeader title="Call history" />
        {!history.data ? (
          <Loading />
        ) : history.data.results.length === 0 ? (
          <Empty icon="phone" title="No calls yet">Calls from the kiosk are listed here with who answered and what they decided.</Empty>
        ) : (
          <Table>
            <thead>
              <tr><Th>Started</Th><Th>Unit</Th><Th>Kiosk</Th><Th>Visitor</Th><Th>Purpose</Th><Th>Status</Th><Th>Answered</Th><Th>Decided</Th></tr>
            </thead>
            <tbody className="divide-y divide-line">
              {history.data.results.map((call) => (
                <tr key={call.id}>
                  <Td className="whitespace-nowrap tabular-nums">{formatDateTime(call.created_at)}</Td>
                  <Td className="whitespace-nowrap">{call.unit_display}</Td>
                  <Td>{call.kiosk_name || "—"}</Td>
                  <Td>{call.visitor_name || "—"}</Td>
                  <Td>{visitPurpose(call.visitor_purpose, call.visitor_company) || "—"}</Td>
                  <Td><CallStatusBadge status={call.status} /></Td>
                  <Td className="tabular-nums">{call.answered_at ? formatTime(call.answered_at) : "—"}</Td>
                  <Td className="tabular-nums">{call.decided_at ? formatTime(call.decided_at) : "—"}</Td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
        {history.data && <Pagination page={page} count={history.data.count} onPage={setPage} />}
      </Card>
    </>
  );
}

export default function Page() {
  return <ModuleGate module="intercom"><IntercomPage /></ModuleGate>;
}
