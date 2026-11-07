"use client";

import { useEffect, useState } from "react";
import useSWR from "swr";

import { AuthImage, CallStatusBadge } from "@/components/bits";
import { SwipeToUnlock } from "@/components/SwipeToUnlock";
import { VideoCall } from "@/components/VideoCall";
import { Button, Card, CardHeader, Empty, Loading, PageHeader, Pagination, Table, Td, Th, useToast } from "@/components/ui";
import { api, ApiError, query } from "@/lib/api";
import { formatDateTime, formatTime } from "@/lib/format";
import { useLiveEvents } from "@/lib/live";
import { useSession } from "@/lib/session";
import type { IntercomCall, LiveKitConnection, Page } from "@/lib/types";

function useElapsed(since: string) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);
  const seconds = Math.max(0, Math.round((now - new Date(since).getTime()) / 1000));
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}

function ActiveCall({ call, connection, onAnswered, onDone }: {
  call: IntercomCall;
  connection?: LiveKitConnection;
  onAnswered: (c: LiveKitConnection) => void;
  onDone: () => void;
}) {
  const toast = useToast();
  const elapsed = useElapsed(call.created_at);
  const [busy, setBusy] = useState<"answer" | "reject" | "hangup" | null>(null);

  async function act<T>(name: "answer" | "reject" | "hangup", fn: () => Promise<T>) {
    setBusy(name);
    try {
      return await fn();
    } catch (error) {
      const message = error instanceof ApiError && error.status === 503
        ? "Video intercom is not configured yet. You can still open the gate."
        : (error as Error).message;
      toast("error", message);
    } finally {
      setBusy(null);
    }
  }

  const answer = () => act("answer", async () => {
    const result = await api<{ call: IntercomCall; livekit: LiveKitConnection }>(`/v1/intercom-calls/${call.id}/answer/`, { method: "POST" });
    onAnswered(result.livekit);
  });
  const reject = () => act("reject", async () => {
    await api(`/v1/intercom-calls/${call.id}/reject/`, { method: "POST" });
    toast("info", "Call rejected.");
    onDone();
  });
  const hangup = () => act("hangup", async () => {
    await api(`/v1/intercom-calls/${call.id}/hangup/`, { method: "POST" });
    onDone();
  });
  const unlock = async () => {
    try {
      await api(`/v1/intercom-calls/${call.id}/unlock/`, { method: "POST" });
      toast("success", "Gate opening. Visitor approved.");
      onDone();
    } catch (error) {
      toast("error", (error as Error).message);
    }
  };

  return (
    <Card className="overflow-hidden">
      <div className="flex items-start justify-between gap-3 border-b border-line px-4 py-3">
        <div>
          <div className="text-base font-semibold text-ink">{call.unit_display}</div>
          <div className="text-sm text-muted">
            {call.kiosk_name || "Kiosk"} · {call.visitor_name || "Visitor"} · {elapsed}
          </div>
        </div>
        <CallStatusBadge status={call.status} />
      </div>
      <div className="space-y-4 p-4">
        {connection ? (
          <VideoCall connection={connection} onEnded={onDone} />
        ) : call.has_snapshot ? (
          <AuthImage path={`/v1/intercom-calls/${call.id}/snapshot/`} alt="Visitor at the kiosk" className="aspect-video w-full rounded-xl object-cover" />
        ) : (
          <div className="flex aspect-video items-center justify-center rounded-xl bg-surface-3 text-sm text-muted">No snapshot</div>
        )}
        <SwipeToUnlock onUnlock={unlock} />
        <div className="flex flex-wrap gap-2">
          {!connection && call.status === "ringing" && (
            <Button variant="primary" className="flex-1" busy={busy === "answer"} onClick={answer}>Answer with video</Button>
          )}
          <Button variant="danger" className="flex-1" busy={busy === "reject"} onClick={reject}>Reject</Button>
          {connection && <Button className="flex-1" busy={busy === "hangup"} onClick={hangup}>Hang up</Button>}
        </div>
      </div>
    </Card>
  );
}

export default function IntercomPage() {
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
      <PageHeader title="Intercom" description="Answer kiosk calls from the guardhouse and let visitors in." />
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
          <Empty>No calls yet.</Empty>
        ) : (
          <Table>
            <thead>
              <tr><Th>Started</Th><Th>Unit</Th><Th>Kiosk</Th><Th>Visitor</Th><Th>Status</Th><Th>Answered</Th><Th>Decided</Th></tr>
            </thead>
            <tbody className="divide-y divide-line">
              {history.data.results.map((call) => (
                <tr key={call.id}>
                  <Td className="whitespace-nowrap tabular-nums">{formatDateTime(call.created_at)}</Td>
                  <Td className="whitespace-nowrap">{call.unit_display}</Td>
                  <Td>{call.kiosk_name || "—"}</Td>
                  <Td>{call.visitor_name || "—"}</Td>
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
