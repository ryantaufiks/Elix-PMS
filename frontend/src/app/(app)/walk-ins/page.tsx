"use client";

import { useState } from "react";
import useSWR from "swr";

import { AuthImage, SearchInput } from "@/components/bits";
import { ConfirmDialog, Tabs } from "@/components/forms";
import { Badge, Button, Card, Empty, Loading, Modal, PageHeader, Pagination, Table, Td, Th, useToast } from "@/components/ui";
import { api, query } from "@/lib/api";
import { formatDateTime, visitPurpose } from "@/lib/format";
import { useLiveEvents } from "@/lib/live";
import { useSession } from "@/lib/session";
import type { Page, WalkInPass, WalkInState } from "@/lib/types";

type Tab = "on_site" | "today" | "all";

const STATE: Record<WalkInState, { label: string; tone: "green" | "slate" | "amber" }> = {
  on_site: { label: "On site", tone: "green" },
  checked_out: { label: "Checked out", tone: "slate" },
  expired: { label: "Not checked out", tone: "amber" },
};

function today() {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Singapore" }).format(new Date());
}

const time = (iso: string) =>
  new Intl.DateTimeFormat("en-SG", { hour: "2-digit", minute: "2-digit", hour12: false, timeZone: "Asia/Singapore" }).format(new Date(iso));

export default function WalkInsPage() {
  const { condo } = useSession();
  const toast = useToast();
  const [tab, setTab] = useState<Tab>("on_site");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [photo, setPhoto] = useState<WalkInPass | null>(null);
  const [leaving, setLeaving] = useState<WalkInPass | null>(null);
  const filters = tab === "on_site" ? { state: "on_site" } : tab === "today" ? { issued_on: today() } : {};
  const { data, mutate } = useSWR<Page<WalkInPass>>(
    `/v1/walk-ins/${query({ condominium: condo.id, search, page, ...filters })}`,
    { keepPreviousData: true },
  );
  const onSite = useSWR<Page<WalkInPass>>(`/v1/walk-ins/${query({ condominium: condo.id, state: "on_site", page_size: 1 })}`);

  useLiveEvents((event) => {
    if (event.type !== "walk_in" || event.data.condominium !== condo.id) return;
    mutate();
    onSite.mutate();
  });

  return (
    <>
      <PageHeader
        title="Walk-ins"
        description="Visitors who registered at the kiosk and received a printed slip. Check the slip's pass number and photo; they scan the slip's QR at the kiosk when leaving."
      />
      <Card>
        <Tabs
          active={tab}
          onChange={(t) => { setTab(t); setPage(1); }}
          tabs={[
            { key: "on_site", label: "On site", count: onSite.data?.count },
            { key: "today", label: "Today" },
            { key: "all", label: "All" },
          ]}
        />
        <div className="flex flex-wrap gap-2 border-b border-line p-4">
          <SearchInput value={search} onChange={(v) => { setSearch(v); setPage(1); }} placeholder="Pass number, name or company" />
        </div>
        {!data ? <Loading /> : data.results.length === 0 ? (
          <Empty>{tab === "on_site" ? "No walk-in visitors on site." : "No walk-in registrations yet."}</Empty>
        ) : (
          <Table>
            <thead><tr><Th>Pass</Th><Th>Visitor</Th><Th>Visiting</Th><Th>In</Th><Th>Out</Th><Th>Status</Th><Th /></tr></thead>
            <tbody className="divide-y divide-line">
              {data.results.map((w) => (
                <tr key={w.id}>
                  <Td className="font-mono text-base font-semibold text-ink">{w.pass_number}</Td>
                  <Td>
                    <div className="flex items-center gap-3">
                      {w.has_snapshot ? (
                        <button onClick={() => setPhoto(w)} className="shrink-0 overflow-hidden rounded-md" aria-label={`Photo of ${w.visitor_name}`}>
                          <AuthImage path={`/v1/walk-ins/${w.id}/snapshot/`} alt="" className="h-10 w-10 object-cover" />
                        </button>
                      ) : <span className="h-10 w-10 shrink-0 rounded-md bg-surface-3" />}
                      <div>
                        <div className="font-medium text-ink">{w.visitor_name}</div>
                        <div className="text-xs text-muted">{[visitPurpose(w.purpose, w.company), w.visitor_phone].filter(Boolean).join(" · ")}</div>
                      </div>
                    </div>
                  </Td>
                  <Td>{w.unit_display}</Td>
                  <Td className="whitespace-nowrap">{tab === "all" ? formatDateTime(w.created_at) : time(w.created_at)}<div className="text-xs text-muted">{w.kiosk_name}</div></Td>
                  <Td className="whitespace-nowrap">{w.checked_out_at ? time(w.checked_out_at) : "—"}</Td>
                  <Td><Badge tone={STATE[w.state].tone}>{STATE[w.state].label}</Badge></Td>
                  <Td className="text-right">
                    {!w.checked_out_at && <Button size="sm" variant="ghost" onClick={() => setLeaving(w)}>Check out</Button>}
                  </Td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
        {data && <Pagination page={page} count={data.count} onPage={setPage} />}
      </Card>

      <Modal open={!!photo} onClose={() => setPhoto(null)} title={photo ? `${photo.pass_number} · ${photo.visitor_name}` : ""}>
        {photo && <AuthImage path={`/v1/walk-ins/${photo.id}/snapshot/`} alt={`Photo of ${photo.visitor_name}`} className="w-full rounded-lg" />}
      </Modal>
      <ConfirmDialog
        open={!!leaving}
        title={`Check out ${leaving?.pass_number}?`}
        confirmLabel="Check out"
        onClose={() => setLeaving(null)}
        message={<>Record that <strong>{leaving?.visitor_name}</strong> has left. Use this when the visitor leaves without scanning their slip.</>}
        onConfirm={async () => {
          try {
            await api(`/v1/walk-ins/${leaving!.id}/check_out/`, { method: "POST" });
            toast("success", `${leaving!.pass_number} checked out.`);
          } catch (error) {
            toast("error", (error as Error).message);
          }
          mutate();
          onSite.mutate();
        }}
      />
    </>
  );
}
