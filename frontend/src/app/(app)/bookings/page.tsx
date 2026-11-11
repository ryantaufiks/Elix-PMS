"use client";

import { useState } from "react";
import useSWR from "swr";

import { SearchInput } from "@/components/bits";
import { ConfirmDialog, Tabs } from "@/components/forms";
import { Icon } from "@/components/icons";
import { Badge, Card, Empty, Field, IconButton, Input, Loading, PageHeader, Pagination, Select, Table, Td, Th, useToast } from "@/components/ui";
import { api, query } from "@/lib/api";
import { formatDateTime, formatRange } from "@/lib/format";
import { useLiveEvents } from "@/lib/live";
import { useSession } from "@/lib/session";
import type { Booking, BookingStatus, Facility, Page, PaymentStatus } from "@/lib/types";
import { ModuleGate } from "@/components/ModuleGate";

const STATUS: Record<BookingStatus, "green" | "amber" | "slate" | "red"> = {
  confirmed: "green", pending_payment: "amber", cancelled: "slate", expired: "red",
};
const PAYMENT: Record<PaymentStatus, "green" | "amber" | "slate" | "red" | "blue"> = {
  none: "slate", pending: "amber", paid: "green", failed: "red", refunded: "blue",
};
type Tab = "upcoming" | "all";

function BookingsPage() {
  const { condo, isManager } = useSession();
  const toast = useToast();
  const [tab, setTab] = useState<Tab>("upcoming");
  const [facility, setFacility] = useState("");
  const [status, setStatus] = useState("");
  const [search, setSearch] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [page, setPage] = useState(1);
  const [cancelling, setCancelling] = useState<Booking | null>(null);
  const [refunding, setRefunding] = useState<Booking | null>(null);
  const { data: facilities } = useSWR<Page<Facility>>(`/v1/facilities/?condominium=${condo.id}&page_size=100`);
  const { data, mutate } = useSWR<Page<Booking>>(`/v1/bookings/${query({
    condominium: condo.id, facility, status, search, page,
    ...(tab === "upcoming" ? { upcoming: 1 } : { ordering: "-starts_at", date_from: from, date_to: to }),
  })}`, { keepPreviousData: true });
  useLiveEvents((event) => { if (event.type === "booking") mutate(); });

  const reset = () => setPage(1);
  return (
    <>
      <PageHeader title="Bookings" description="Facility bookings made by residents in the app, with their payment status." />
      <Card>
        <div className="border-b border-line px-4 pt-3">
          <Tabs tabs={[{ key: "upcoming", label: "Upcoming" }, { key: "all", label: "All bookings" }]} active={tab} onChange={(t) => { setTab(t); reset(); }} />
        </div>
        <div className="flex flex-wrap items-end gap-3 border-b border-line p-4">
          <SearchInput value={search} onChange={(v) => { setSearch(v); reset(); }} placeholder="Facility, resident, unit, notes" />
          <Select value={facility} onChange={(e) => { setFacility(e.target.value); reset(); }} className="sm:w-48" aria-label="Facility">
            <option value="">All facilities</option>
            {facilities?.results.map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}
          </Select>
          <Select value={status} onChange={(e) => { setStatus(e.target.value); reset(); }} className="sm:w-44" aria-label="Status">
            <option value="">Any status</option>
            <option value="confirmed">Confirmed</option>
            <option value="pending_payment">Awaiting payment</option>
            <option value="cancelled">Cancelled</option>
            <option value="expired">Payment expired</option>
          </Select>
          {tab === "all" && (
            <>
              <Field label="From"><Input type="date" value={from} onChange={(e) => { setFrom(e.target.value); reset(); }} /></Field>
              <Field label="To"><Input type="date" value={to} onChange={(e) => { setTo(e.target.value); reset(); }} /></Field>
            </>
          )}
        </div>
        {!data ? <Loading /> : data.results.length === 0 ? <Empty icon="calendar" title="No bookings" >Residents book facilities from the app; bookings and their payments show up here.</Empty> : (
          <Table>
            <thead><tr><Th>Facility</Th><Th>When</Th><Th>Unit</Th><Th>Booked by</Th><Th>Amount</Th><Th>Payment</Th><Th>Status</Th><Th /></tr></thead>
            <tbody className="divide-y divide-line">
              {data.results.map((b) => (
                <tr key={b.id}>
                  <Td className="font-medium text-ink">{b.facility_name}<div className="text-xs font-normal text-muted">{b.guests} guest{b.guests === 1 ? "" : "s"}{b.notes ? ` · ${b.notes}` : ""}</div></Td>
                  <Td className="whitespace-nowrap">{formatRange(b.starts_at, b.ends_at)}</Td>
                  <Td>{b.unit_display}</Td>
                  <Td>{b.booked_by || "—"}<div className="text-xs text-muted">{formatDateTime(b.created_at)}</div></Td>
                  <Td className="whitespace-nowrap tabular-nums">{Number(b.amount) ? `${b.currency} ${b.amount}` : "Free"}{Number(b.deposit) > 0 && <div className="text-xs text-muted">incl. {b.deposit} deposit</div>}</Td>
                  <Td><Badge tone={PAYMENT[b.payment_status]}>{b.payment_status_display}</Badge>{b.paid_at && <div className="mt-1 text-xs text-muted">{formatDateTime(b.paid_at)}</div>}</Td>
                  <Td><Badge tone={STATUS[b.status]}>{b.status_display}</Badge>{b.cancel_reason && <div className="mt-1 max-w-48 text-xs text-muted">{b.cancel_reason}</div>}</Td>
                  <Td className="whitespace-nowrap text-right">
                    {isManager && (
                      <div className="inline-flex items-center gap-0.5">
                        {b.payment_status === "paid" && b.status !== "confirmed" && (
                          <IconButton label="Mark refunded" onClick={() => setRefunding(b)}><Icon name="check" className="h-[18px] w-[18px]" /></IconButton>
                        )}
                        {(b.status === "confirmed" || b.status === "pending_payment") && (
                          <IconButton label="Cancel booking" onClick={() => setCancelling(b)}><Icon name="x" className="h-[18px] w-[18px]" /></IconButton>
                        )}
                      </div>
                    )}
                  </Td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
        {data && <Pagination page={page} count={data.count} onPage={setPage} />}
      </Card>

      <ConfirmDialog open={!!cancelling} title={`Cancel ${cancelling?.facility_name} booking?`} confirmLabel="Cancel booking"
        message={<>The slot is released and the resident sees the booking as cancelled.{cancelling?.payment_status === "paid" && " The payment is not refunded automatically: refund it in HitPay, then mark it refunded here."}</>}
        onClose={() => setCancelling(null)}
        onConfirm={async () => { await api(`/v1/bookings/${cancelling!.id}/cancel/`, { method: "POST", body: { reason: "Cancelled by the management" } }); toast("success", "Booking cancelled."); mutate(); }} />
      <ConfirmDialog open={!!refunding} title="Mark as refunded?" confirmLabel="Mark refunded"
        message={<>Record that {refunding?.currency} {refunding?.amount} was refunded to {refunding?.unit_display} in the HitPay dashboard.</>}
        onClose={() => setRefunding(null)}
        onConfirm={async () => { await api(`/v1/bookings/${refunding!.id}/refunded/`, { method: "POST" }); toast("success", "Refund recorded."); mutate(); }} />
    </>
  );
}

export default function Page() {
  return <ModuleGate module="facilities"><BookingsPage /></ModuleGate>;
}
