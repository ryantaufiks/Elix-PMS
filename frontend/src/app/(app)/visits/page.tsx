"use client";

import { useEffect, useRef, useState } from "react";
import useSWR from "swr";

import { AuthImage, SearchInput, UnitPicker } from "@/components/bits";
import { ConfirmDialog, EntityModal, remove, Tabs } from "@/components/forms";
import { Icon } from "@/components/icons";
import { PrintSlip } from "@/components/PrintSlip";
import {
  Badge, Button, Card, Checkbox, Empty, ErrorNote, Field, IconButton, Input, Loading, Modal, PageHeader, Pagination, Select, Table, Td,
  Textarea, Th, useToast,
} from "@/components/ui";
import { api, query } from "@/lib/api";
import { formatDateTime, VISIT_PURPOSE_LABEL, visitPurpose } from "@/lib/format";
import type { WalkInSlip } from "@/lib/kiosk";
import { useLiveEvents } from "@/lib/live";
import { useSession } from "@/lib/session";
import type { Page, Visit, VisitState } from "@/lib/types";

type Tab = "on_site" | "today" | "history";

const STATE: Record<VisitState, { label: string; tone: "green" | "slate" | "amber" }> = {
  on_site: { label: "On site", tone: "green" },
  checked_out: { label: "Checked out", tone: "slate" },
  expired: { label: "Not checked out", tone: "amber" },
};

const SOURCES = [
  { value: "", label: "All entries" },
  { value: "kiosk", label: "Walk-in (kiosk)" },
  { value: "staff", label: "Walk-in (security)" },
  { value: "invitation", label: "Invitation" },
  { value: "intercom", label: "Intercom" },
];

const today = () => new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Singapore" }).format(new Date());

export default function VisitsPage() {
  const { condo, isAdmin } = useSession();
  const toast = useToast();
  const [tab, setTab] = useState<Tab>("on_site");
  const [search, setSearch] = useState("");
  const [source, setSource] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [photo, setPhoto] = useState<Visit | null>(null);
  const [editing, setEditing] = useState<Visit | null>(null);
  const [leaving, setLeaving] = useState<Visit[] | null>(null);
  const [blocking, setBlocking] = useState<Visit | null>(null);
  const [erasing, setErasing] = useState<Visit | null>(null);
  const [registering, setRegistering] = useState(false);
  const [slip, setSlip] = useState<WalkInSlip | null>(null);

  const filters = tab === "on_site" ? { state: "on_site" } : tab === "today" ? { issued_on: today() } : { date_from: from, date_to: to };
  const { data, mutate } = useSWR<Page<Visit>>(
    `/v1/visits/${query({ condominium: condo.id, search, source, page, ...filters })}`,
    { keepPreviousData: true },
  );
  const onSite = useSWR<Page<Visit>>(`/v1/visits/${query({ condominium: condo.id, state: "on_site", page_size: 1 })}`);
  const refresh = () => {
    mutate();
    onSite.mutate();
  };

  useLiveEvents((event) => {
    if (event.type === "visit" && event.data.condominium === condo.id) refresh();
  });
  useEffect(() => setSelected(new Set()), [tab, search, source, page, from, to]);

  const rows = data?.results ?? [];
  const selectable = rows.filter((v) => !v.checked_out_at);
  const allSelected = selectable.length > 0 && selectable.every((v) => selected.has(v.id));
  const toggle = (id: number) => setSelected((cur) => {
    const next = new Set(cur);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    return next;
  });

  async function print(visit: Visit) {
    try {
      setSlip(await api<WalkInSlip>(`/v1/visits/${visit.id}/slip/`));
    } catch (error) {
      toast("error", (error as Error).message);
    }
  }

  return (
    <>
      <PageHeader
        title="Visitor list"
        description={`Everyone who came in: kiosk and guardhouse walk-ins, invitations and intercom. Visitor details are deleted ${condo.visitor_data_retention_days} days after their last visit (PDPA), except blocked visitors.`}
        action={<Button variant="primary" onClick={() => setRegistering(true)}>Register visitor</Button>}
      />
      <Card>
        <Tabs
          active={tab}
          onChange={(t) => { setTab(t); setPage(1); }}
          tabs={[
            { key: "on_site", label: "On site", count: onSite.data?.count },
            { key: "today", label: "Today" },
            { key: "history", label: "History" },
          ]}
        />
        <div className="flex flex-wrap items-center gap-2 border-b border-line p-4">
          <SearchInput value={search} onChange={(v) => { setSearch(v); setPage(1); }} placeholder="Pass number, PIN, name, company, plate, notes" />
          <Select value={source} onChange={(e) => { setSource(e.target.value); setPage(1); }} className="sm:w-48" aria-label="Entry">
            {SOURCES.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
          </Select>
          {tab === "history" && (
            <>
              <Input type="date" value={from} onChange={(e) => { setFrom(e.target.value); setPage(1); }} className="sm:w-40" aria-label="From date" />
              <span className="text-sm text-muted">to</span>
              <Input type="date" value={to} onChange={(e) => { setTo(e.target.value); setPage(1); }} className="sm:w-40" aria-label="To date" />
            </>
          )}
        </div>
        {selected.size > 0 && (
          <div className="flex flex-wrap items-center gap-3 border-b border-line bg-primary-500/5 px-4 py-2.5 text-sm">
            <span className="font-medium text-ink">{selected.size} selected</span>
            <Button size="sm" variant="primary" onClick={() => setLeaving(rows.filter((v) => selected.has(v.id)))}>Check out selected</Button>
            <Button size="sm" variant="ghost" onClick={() => setSelected(new Set())}>Clear</Button>
          </div>
        )}
        {!data ? <Loading /> : rows.length === 0 ? (
          <Empty>{tab === "on_site" ? "No visitors on site." : "No visits found."}</Empty>
        ) : (
          <Table>
            <thead>
              <tr>
                <Th className="w-10">
                  <input type="checkbox" aria-label="Select all on this page" checked={allSelected} disabled={selectable.length === 0}
                    onChange={() => setSelected(allSelected ? new Set() : new Set(selectable.map((v) => v.id)))} className="h-4 w-4 rounded border-line" />
                </Th>
                <Th>Pass</Th><Th>Visitor</Th><Th>Visiting</Th><Th>Entry</Th><Th>Check-in</Th><Th>Check-out</Th><Th>Status</Th><Th />
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {rows.map((v) => (
                <tr key={v.id} className={selected.has(v.id) ? "bg-primary-500/5" : undefined}>
                  <Td>
                    {!v.checked_out_at && (
                      <input type="checkbox" aria-label={`Select ${v.pass_number}`} checked={selected.has(v.id)} onChange={() => toggle(v.id)} className="h-4 w-4 rounded border-line" />
                    )}
                  </Td>
                  <Td className="font-mono text-base font-semibold text-ink">
                    {v.pass_number}
                    {v.pin && v.state === "on_site" && <div className="text-xs font-normal text-muted">PIN {v.pin}</div>}
                  </Td>
                  <Td>
                    <div className="flex items-start gap-3">
                      {v.has_snapshot ? (
                        <button onClick={() => setPhoto(v)} className="shrink-0 overflow-hidden rounded-md" aria-label={`Photo of ${v.visitor_name}`}>
                          <AuthImage path={`/v1/visits/${v.id}/snapshot/`} alt="" className="h-10 w-10 object-cover" />
                        </button>
                      ) : <span className="h-10 w-10 shrink-0 rounded-md bg-surface-3" />}
                      <div className="min-w-0">
                        <div className="font-medium text-ink">{v.visitor_name}{v.visitor_blocked && <span className="ml-2"><Badge tone="red">Blocked</Badge></span>}</div>
                        <div className="text-xs text-muted">{[visitPurpose(v.purpose, v.company), v.visitor_phone, v.vehicle_plate].filter(Boolean).join(" · ")}</div>
                        {v.notes && <div className="mt-1 max-w-xs whitespace-pre-line text-xs italic text-body">{v.notes}</div>}
                      </div>
                    </div>
                  </Td>
                  <Td className="whitespace-nowrap">{v.unit_display}</Td>
                  <Td>
                    <div className="whitespace-nowrap">{v.source_display}</div>
                    <div className="text-xs text-muted">{v.created_by_name ? `by ${v.created_by_name}` : v.kiosk_name || v.gate_name}</div>
                  </Td>
                  <Td className="whitespace-nowrap">{formatDateTime(v.created_at)}</Td>
                  <Td className="whitespace-nowrap">
                    {v.checked_out_at ? (
                      <>
                        {formatDateTime(v.checked_out_at)}
                        <div className="text-xs text-muted">{v.checked_out_by_name ? `by ${v.checked_out_by_name}` : "Self / exit camera"}</div>
                      </>
                    ) : "—"}
                  </Td>
                  <Td><Badge tone={STATE[v.state].tone}>{STATE[v.state].label}</Badge></Td>
                  <Td className="whitespace-nowrap text-right">
                    <div className="inline-flex items-center gap-0.5">
                      <IconButton label="Print slip" onClick={() => print(v)}><Icon name="printer" className="h-[18px] w-[18px]" /></IconButton>
                      <IconButton label="Edit notes" onClick={() => setEditing(v)}><Icon name="pencil" className="h-[18px] w-[18px]" /></IconButton>
                      {v.visitor && (
                        <IconButton label={v.visitor_blocked ? "Unblock visitor" : "Block visitor"} onClick={() => setBlocking(v)}><Icon name="ban" className="h-[18px] w-[18px]" /></IconButton>
                      )}
                      {v.visitor && isAdmin && (
                        <IconButton label="Erase visitor data" onClick={() => setErasing(v)}><Icon name="trash" className="h-[18px] w-[18px]" /></IconButton>
                      )}
                      {!v.checked_out_at && (
                        <IconButton label="Check out" tone="primary" onClick={() => setLeaving([v])}><Icon name="checkout" className="h-[18px] w-[18px]" /></IconButton>
                      )}
                    </div>
                  </Td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
        {data && <Pagination page={page} count={data.count} onPage={setPage} />}
      </Card>

      <Modal open={!!photo} onClose={() => setPhoto(null)} title={photo ? `${photo.pass_number} · ${photo.visitor_name}` : ""}>
        {photo && <AuthImage path={`/v1/visits/${photo.id}/snapshot/`} alt={`Photo of ${photo.visitor_name}`} className="w-full rounded-lg" />}
      </Modal>
      {editing && (
        <EntityModal<Visit>
          title={`Edit ${editing.pass_number}`}
          record={editing}
          endpoint={`/v1/visits/${editing.id}/`}
          fields={[
            { name: "visitor_name", label: "Visitor name", required: true },
            { name: "company", label: "Company" },
            { name: "notes", label: "Notes", type: "textarea", wide: true, hint: "For security only, e.g. items carried, where the vehicle is parked, who escorted the visitor." },
          ]}
          onClose={() => setEditing(null)}
          onSaved={() => { setEditing(null); refresh(); }}
        />
      )}
      {blocking && (
        <EntityModal
          title={blocking.visitor_blocked ? `Unblock ${blocking.visitor_name}?` : `Block ${blocking.visitor_name}`}
          submitLabel={blocking.visitor_blocked ? "Unblock" : "Block visitor"}
          fields={blocking.visitor_blocked ? [] : [{ name: "blacklist_reason", label: "Reason (staff only)", type: "textarea", required: true }]}
          record={{}}
          endpoint={`/v1/visitors/${blocking.visitor}/`}
          extra={{ is_blacklisted: !blocking.visitor_blocked, ...(blocking.visitor_blocked ? { blacklist_reason: "" } : {}) }}
          onClose={() => setBlocking(null)}
          onSaved={() => { setBlocking(null); refresh(); }}
        />
      )}
      <ConfirmDialog
        open={!!erasing}
        title="Erase this visitor's data?"
        confirmLabel="Erase permanently"
        onClose={() => setErasing(null)}
        message={<>For a PDPA deletion request: removes <strong>{erasing?.visitor_name}</strong>, their photos and their details from calls and invitations. Access-log entries remain without personal details. This cannot be undone.</>}
        onConfirm={async () => { await remove(`/v1/visitors/${erasing!.visitor}/`); refresh(); }}
      />
      <ConfirmDialog
        open={!!leaving}
        title={leaving && leaving.length > 1 ? `Check out ${leaving.length} visitors?` : `Check out ${leaving?.[0]?.pass_number}?`}
        confirmLabel="Check out"
        onClose={() => setLeaving(null)}
        message={leaving && leaving.length > 1
          ? <>Record that these visitors have left: {leaving.map((v) => v.pass_number).join(", ")}.</>
          : <>Record that <strong>{leaving?.[0]?.visitor_name}</strong> has left now.</>}
        onConfirm={async () => {
          try {
            if (leaving!.length === 1) await api(`/v1/visits/${leaving![0].id}/check_out/`, { method: "POST" });
            else {
              const r = await api<{ checked_out: number }>("/v1/visits/bulk_check_out/", { method: "POST", body: { ids: leaving!.map((v) => v.id) } });
              toast("success", `${r.checked_out} visitor${r.checked_out === 1 ? "" : "s"} checked out.`);
            }
            setSelected(new Set());
          } catch (error) {
            toast("error", (error as Error).message);
          }
          refresh();
        }}
      />
      {registering && (
        <RegisterVisitor
          condoId={condo.id}
          onClose={() => setRegistering(false)}
          onSaved={(visit, printNow) => {
            setRegistering(false);
            refresh();
            toast("success", `${visit.pass_number} registered for ${visit.unit_display}.`);
            if (printNow) print(visit);
          }}
        />
      )}
      {slip && <PrintSlip slip={slip} onReady={() => { window.print(); setSlip(null); }} />}
    </>
  );
}

/** A walk-in registered at the guardhouse, with an optional webcam photo. */
function RegisterVisitor({ condoId, onClose, onSaved }: { condoId: number; onClose: () => void; onSaved: (visit: Visit, print: boolean) => void }) {
  const [unit, setUnit] = useState<number | null>(null);
  const [form, setForm] = useState({ visitor_name: "", purpose: "guest", company: "", visitor_phone: "", visitor_id_partial: "", vehicle_plate: "", notes: "" });
  const [photo, setPhoto] = useState<Blob | null>(null);
  const [consent, setConsent] = useState(false);
  const [printNow, setPrintNow] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const set = (name: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) =>
    setForm((f) => ({ ...f, [name]: e.target.value }));

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const body = new FormData();
    body.set("unit", String(unit ?? ""));
    Object.entries(form).forEach(([k, v]) => body.set(k, v.trim()));
    body.set("consent", consent ? "true" : "false");
    if (photo) body.set("snapshot", photo, "visitor.jpg");
    try {
      onSaved(await api<Visit>("/v1/visits/", { method: "POST", body }), printNow);
    } catch (err) {
      setError(err);
      setBusy(false);
    }
  }

  return (
    <Modal open onClose={onClose} title="Register visitor" wide
      footer={<>
        <Button onClick={onClose}>Cancel</Button>
        <Button type="submit" form="register-visitor" variant="primary" busy={busy} disabled={!unit || !form.visitor_name.trim() || !consent}>Register</Button>
      </>}>
      <form id="register-visitor" onSubmit={submit} className="space-y-4">
        <ErrorNote error={error} />
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Visiting unit"><UnitPicker condoId={condoId} value={unit} onChange={(u) => setUnit(u?.id ?? null)} /></Field>
          <Field label="Purpose">
            <Select value={form.purpose} onChange={set("purpose")}>
              {Object.entries(VISIT_PURPOSE_LABEL).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </Select>
          </Field>
          <Field label="Visitor name"><Input value={form.visitor_name} onChange={set("visitor_name")} maxLength={150} required /></Field>
          <Field label="Company (optional)"><Input value={form.company} onChange={set("company")} maxLength={100} /></Field>
          <Field label="Mobile (optional)"><Input type="tel" value={form.visitor_phone} onChange={set("visitor_phone")} placeholder="9123 4567" /></Field>
          <Field label="Last 4 of NRIC/FIN (optional)">
            <Input value={form.visitor_id_partial} onChange={(e) => setForm((f) => ({ ...f, visitor_id_partial: e.target.value.toUpperCase().slice(0, 4) }))} placeholder="567A" />
          </Field>
          <Field label="Vehicle plate (optional)"><Input value={form.vehicle_plate} onChange={set("vehicle_plate")} placeholder="SGX 1234 A" /></Field>
          <Field label="Photo (optional)"><WebcamPhoto value={photo} onChange={setPhoto} /></Field>
        </div>
        <Field label="Notes (optional)"><Textarea rows={2} value={form.notes} onChange={set("notes")} /></Field>
        <Checkbox label="The visitor has seen the privacy notice and agrees to their details being recorded." checked={consent} onChange={(e) => setConsent(e.target.checked)} />
        <Checkbox label="Print the slip after registering" checked={printNow} onChange={(e) => setPrintNow(e.target.checked)} />
      </form>
    </Modal>
  );
}

function WebcamPhoto({ value, onChange }: { value: Blob | null; onChange: (b: Blob | null) => void }) {
  const video = useRef<HTMLVideoElement>(null);
  const [live, setLive] = useState(false);
  const [error, setError] = useState("");
  const [preview, setPreview] = useState<string | null>(null);
  const stream = useRef<MediaStream | null>(null);

  useEffect(() => {
    if (!value) return setPreview(null);
    const url = URL.createObjectURL(value);
    setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [value]);
  const stop = () => {
    stream.current?.getTracks().forEach((t) => t.stop());
    stream.current = null;
    setLive(false);
  };
  useEffect(() => stop, []);

  async function start() {
    setError("");
    try {
      stream.current = await navigator.mediaDevices.getUserMedia({ video: { width: { ideal: 1280 } }, audio: false });
      setLive(true);
      requestAnimationFrame(() => {
        if (video.current && stream.current) {
          video.current.srcObject = stream.current;
          video.current.play().catch(() => {});
        }
      });
    } catch {
      setError("No camera available. Allow camera access for this site.");
    }
  }
  function capture() {
    const v = video.current;
    if (!v || !v.videoWidth) return;
    const canvas = document.createElement("canvas");
    const scale = Math.min(1, 960 / v.videoWidth);
    canvas.width = Math.round(v.videoWidth * scale);
    canvas.height = Math.round(v.videoHeight * scale);
    canvas.getContext("2d")!.drawImage(v, 0, 0, canvas.width, canvas.height);
    canvas.toBlob((b) => b && onChange(b), "image/jpeg", 0.85);
    stop();
  }

  return (
    <div className="space-y-2">
      {live ? (
        <video ref={video} autoPlay playsInline muted className="aspect-video w-full rounded-lg bg-surface-3 object-cover" />
      ) : preview ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={preview} alt="Visitor" className="aspect-video w-full rounded-lg object-cover" />
      ) : null}
      <div className="flex gap-2">
        {live ? (
          <><Button type="button" size="sm" variant="primary" onClick={capture}>Capture</Button><Button type="button" size="sm" onClick={stop}>Cancel</Button></>
        ) : (
          <><Button type="button" size="sm" onClick={start}>{preview ? "Retake" : "Take photo"}</Button>{preview && <Button type="button" size="sm" variant="ghost" onClick={() => onChange(null)}>Remove</Button>}</>
        )}
      </div>
      {error && <p className="text-xs text-rose-600">{error}</p>}
    </div>
  );
}
