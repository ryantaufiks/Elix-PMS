"use client";

import { useState } from "react";

import { formatDateTime, METHOD_LABEL } from "@/lib/format";
import type { AccessLog } from "@/lib/types";

import { AuthImage, ResultBadge } from "./bits";
import { Button, Empty, Modal, Table, Td, Th } from "./ui";

function subject(log: AccessLog) {
  return [log.unit_display, log.plate_number, log.visitor_name].filter(Boolean).join(" · ") || "—";
}

export function AccessTable({ logs, highlight }: { logs: AccessLog[]; highlight?: Set<number> }) {
  const [snapshot, setSnapshot] = useState<AccessLog | null>(null);
  if (logs.length === 0) return <Empty>No access events yet.</Empty>;
  return (
    <>
      <Table>
        <thead>
          <tr>
            <Th>Time</Th>
            <Th>Gate</Th>
            <Th>Method</Th>
            <Th>Result</Th>
            <Th>Unit · plate · visitor</Th>
            <Th>By / reason</Th>
            <Th />
          </tr>
        </thead>
        <tbody className="divide-y divide-line">
          {logs.map((log) => (
            <tr key={log.id} className={highlight?.has(log.id) ? "bg-primary-50/60 transition-colors" : undefined}>
              <Td label="Time" className="whitespace-nowrap tabular-nums">{formatDateTime(log.occurred_at)}</Td>
              <Td label="Gate" className="whitespace-nowrap">{log.gate_name || "—"}</Td>
              <Td label="Method" className="whitespace-nowrap">{METHOD_LABEL[log.method] ?? log.method}</Td>
              <Td label="Result"><ResultBadge result={log.result} /></Td>
              <Td label="Unit · plate" className="min-w-48">{subject(log)}</Td>
              <Td label="By / reason" className="min-w-48 text-muted">
                {log.actor_name && <span className="text-ink">{log.actor_name}</span>}
                {log.actor_name && log.reason && " · "}
                {log.reason}
              </Td>
              <Td className="text-right">
                {log.has_snapshot && <Button size="sm" variant="ghost" onClick={() => setSnapshot(log)}>Photo</Button>}
              </Td>
            </tr>
          ))}
        </tbody>
      </Table>
      <Modal open={!!snapshot} onClose={() => setSnapshot(null)} title={snapshot ? `${snapshot.gate_name} · ${formatDateTime(snapshot.occurred_at)}` : ""} wide>
        {snapshot && <AuthImage path={`/v1/access-logs/${snapshot.id}/snapshot/`} alt="Camera snapshot" className="w-full rounded-lg" />}
      </Modal>
    </>
  );
}
