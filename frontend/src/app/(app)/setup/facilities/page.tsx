"use client";

import { useEffect, useState } from "react";
import useSWR from "swr";

import { AuthImage } from "@/components/bits";
import { ConfirmDialog, CopyField, FormFields, initialValues, remove, type FieldDef } from "@/components/forms";
import { Icon } from "@/components/icons";
import {
  Badge, Button, Card, CardHeader, Checkbox, cx, Empty, ErrorNote, Field, IconButton, Input, Loading, Modal, PageHeader, Select, Textarea, useToast,
} from "@/components/ui";
import { api, ApiError, errorMessage } from "@/lib/api";
import { useSession } from "@/lib/session";
import type { Facility, Page, PaymentSettings } from "@/lib/types";
import { ModuleGate } from "@/components/ModuleGate";

const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
/** Icons the resident app knows (Material icon names). */
const ICONS = [
  { value: "event", label: "General" }, { value: "outdoor_grill", label: "BBQ pit" }, { value: "meeting_room", label: "Function room" },
  { value: "sports_tennis", label: "Tennis court" }, { value: "sports_basketball", label: "Basketball court" },
  { value: "fitness_center", label: "Gym" }, { value: "pool", label: "Pool" }, { value: "celebration", label: "Party / event space" },
  { value: "spa", label: "Spa / sauna" }, { value: "sports_esports", label: "Games room" }, { value: "local_parking", label: "Visitor parking" },
];
const SLOTS = [30, 60, 90, 120, 180, 240];

const money = (v: string | number) => `$${Number(v).toFixed(2)}`;
const hhmm = (t: string) => t.slice(0, 5);

type Form = Omit<Facility, "id" | "condominium" | "has_image" | "is_paid">;
const blank: Form = {
  name: "", description: "", location: "", icon: "event", capacity: 10, opens_at: "08:00", closes_at: "22:00",
  open_days: [0, 1, 2, 3, 4, 5, 6], slot_minutes: 60, max_slots_per_booking: 2, concurrent_bookings: 1, price_per_slot: "0.00",
  deposit: "0.00", advance_days: 14, max_upcoming_per_unit: 2, cancel_hours: 24, rules: "", is_active: true,
};

function FacilityModal({ condoId, facility, onClose, onSaved }: { condoId: number; facility: Facility | null; onClose: () => void; onSaved: () => void }) {
  const toast = useToast();
  const [form, setForm] = useState<Form>(() => (facility ? { ...blank, ...facility, opens_at: hhmm(facility.opens_at), closes_at: hhmm(facility.closes_at) } : blank));
  const [photo, setPhoto] = useState<File | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const set = <K extends keyof Form>(key: K, value: Form[K]) => setForm((f) => ({ ...f, [key]: value }));
  const errors = error instanceof ApiError && error.data && typeof error.data === "object" ? error.data as Record<string, unknown> : {};
  const err = (k: string) => (errors[k] ? <p className="mt-1 text-xs text-rose-600">{errorMessage(errors[k], "Invalid")}</p> : null);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const saved = await api<Facility>(facility ? `/v1/facilities/${facility.id}/` : "/v1/facilities/", {
        method: facility ? "PATCH" : "POST", body: { ...form, condominium: condoId },
      });
      if (photo) {
        const upload = new FormData();
        upload.set("image", photo);
        await api(`/v1/facilities/${saved.id}/`, { method: "PATCH", body: upload });
      }
      toast("success", facility ? "Facility saved." : "Facility added.");
      onSaved();
    } catch (e2) {
      setError(e2);
      setBusy(false);
    }
  }

  const num = (k: keyof Form, label: string, hint?: string, step = "1") => (
    <Field label={label} hint={hint}>
      <Input type="number" min={0} step={step} value={String(form[k])} onChange={(e) => set(k, e.target.value as never)} required />
      {err(k)}
    </Field>
  );

  return (
    <Modal open wide onClose={onClose} title={facility ? `Edit ${facility.name}` : "Add facility"}
      footer={<><Button onClick={onClose}>Cancel</Button><Button variant="primary" busy={busy} type="submit" form="facility-form">Save</Button></>}>
      <form id="facility-form" onSubmit={save} className="space-y-5">
        <ErrorNote error={errors.detail || !Object.keys(errors).length ? error : null} />
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Name"><Input value={form.name} onChange={(e) => set("name", e.target.value)} required placeholder="e.g. BBQ pit 1" />{err("name")}</Field>
          <Field label="Icon in the app">
            <Select value={form.icon} onChange={(e) => set("icon", e.target.value)}>{ICONS.map((i) => <option key={i.value} value={i.value}>{i.label}</option>)}</Select>
          </Field>
          <Field label="Location"><Input value={form.location} onChange={(e) => set("location", e.target.value)} placeholder="e.g. Level 1, next to the pool" /></Field>
          {num("capacity", "People per booking")}
          <div className="sm:col-span-2"><Field label="Description"><Textarea rows={2} value={form.description} onChange={(e) => set("description", e.target.value)} /></Field></div>
        </div>

        <div>
          <div className="mb-3 text-sm font-semibold text-ink">Opening hours and slots</div>
          <div className="grid gap-4 sm:grid-cols-3">
            <Field label="Opens"><Input type="time" value={form.opens_at} onChange={(e) => set("opens_at", e.target.value)} required /></Field>
            <Field label="Closes"><Input type="time" value={form.closes_at} onChange={(e) => set("closes_at", e.target.value)} required />{err("closes_at")}</Field>
            <Field label="Slot length">
              <Select value={form.slot_minutes} onChange={(e) => set("slot_minutes", Number(e.target.value))}>
                {SLOTS.map((m) => <option key={m} value={m}>{m < 60 ? `${m} min` : `${m / 60} hour${m > 60 ? "s" : ""}`}</option>)}
              </Select>
            </Field>
          </div>
          <div className="mt-3 flex flex-wrap gap-2" role="group" aria-label="Open days">
            {DAYS.map((d, i) => {
              const on = form.open_days.includes(i);
              return (
                <button key={d} type="button" aria-pressed={on}
                  onClick={() => set("open_days", on ? form.open_days.filter((x) => x !== i) : [...form.open_days, i].sort())}
                  className={cx("h-9 w-12 rounded-md border text-sm font-medium", on ? "border-primary-500 bg-primary-500 text-white" : "border-line text-body hover:bg-surface-2")}>
                  {d}
                </button>
              );
            })}
          </div>
          {err("open_days")}
          <div className="mt-4 grid gap-4 sm:grid-cols-3">
            {num("max_slots_per_booking", "Max slots per booking")}
            {num("concurrent_bookings", "Bookings per slot", "e.g. 2 when there are two identical BBQ pits")}
            {num("advance_days", "Book up to (days ahead)")}
          </div>
        </div>

        <div>
          <div className="mb-3 text-sm font-semibold text-ink">Price and rules</div>
          <div className="grid gap-4 sm:grid-cols-3">
            {num("price_per_slot", "Price per slot (SGD)", "0 = free", "0.01")}
            {num("deposit", "Refundable deposit (SGD)", "Paid with the booking", "0.01")}
            {num("cancel_hours", "Residents can cancel until (hours before)")}
            {num("max_upcoming_per_unit", "Upcoming bookings per unit", "0 = no limit")}
          </div>
          <div className="mt-4"><Field label="Rules shown before booking"><Textarea rows={3} value={form.rules} onChange={(e) => set("rules", e.target.value)} placeholder="e.g. Clean the pit after use. No loud music after 10 pm." /></Field></div>
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Photo (optional)" hint={facility?.has_image ? "Choose a file to replace the current photo." : "Shown in the resident app."}>
            <Input type="file" accept="image/jpeg,image/png,image/webp" onChange={(e) => setPhoto(e.target.files?.[0] ?? null)} />
          </Field>
          <div className="pt-6"><Checkbox label="Residents can book it" checked={form.is_active} onChange={(e) => set("is_active", e.target.checked)} /></div>
        </div>
      </form>
    </Modal>
  );
}

const paymentFields: FieldDef[] = [
  { name: "enabled", label: "Accept online payments for bookings", type: "checkbox", wide: true },
  { name: "sandbox", label: "Sandbox (test payments only)", type: "checkbox", wide: true, hint: "Untick when you go live with your HitPay account." },
  { name: "hitpay_api_key", label: "HitPay API key", type: "secret", hint: "HitPay dashboard → Settings → Payment gateway → API keys." },
  { name: "hitpay_salt", label: "HitPay salt", type: "secret", hint: "Same page; used to verify HitPay's notifications." },
  { name: "currency", label: "Currency", placeholder: "SGD" },
  { name: "payment_minutes", label: "Hold slots while paying (minutes)", type: "number" },
];

function Payments({ condoId }: { condoId: number }) {
  const toast = useToast();
  const path = `/v1/payment-settings/?condominium=${condoId}`;
  const { data, mutate, error: loadError } = useSWR<PaymentSettings>(path);
  const [values, setValues] = useState<Record<string, unknown>>({});
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (data) setValues(initialValues(paymentFields, data)); }, [data]);
  if (loadError) return <ErrorNote error={loadError} />;
  if (!data) return <Loading />;

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const body = Object.fromEntries(Object.entries(values).filter(([k, v]) => !(k.startsWith("hitpay_") && v === "")));
      await mutate(await api<PaymentSettings>(path, { method: "PATCH", body: { ...body, payment_minutes: Number(values.payment_minutes) } }), false);
      toast("success", "Payment settings saved.");
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }
  const ready = data.enabled && data.has_hitpay_api_key;
  return (
    <Card>
      <CardHeader title="Online payments (HitPay)" action={ready ? <Badge tone={data.sandbox ? "amber" : "green"}>{data.sandbox ? "Sandbox" : "Live"}</Badge> : <Badge>Off</Badge>} />
      <form onSubmit={save} className="space-y-5 p-5">
        <p className="text-sm text-muted">
          Paid facilities are paid with the condominium&apos;s own HitPay account (PayNow, cards and the other methods enabled there).
          A booking is confirmed only after HitPay reports the payment as completed; unpaid bookings release their slots automatically.
          Refunds (cancellations, deposits) are made in the HitPay dashboard, then recorded under Bookings.
        </p>
        <ErrorNote error={error} />
        <FormFields fields={paymentFields} values={values} errors={{}} record={data as unknown as Record<string, unknown>} onChange={(n, v) => setValues((s) => ({ ...s, [n]: v }))} />
        <Field label="Webhook URL" hint="Optional in HitPay; each payment request already carries it.">
          <CopyField value={data.webhook_url} />
        </Field>
        <div className="flex justify-end border-t border-line pt-5"><Button type="submit" variant="primary" busy={busy}>Save payment settings</Button></div>
      </form>
    </Card>
  );
}

function FacilitiesPage() {
  const { condo, isAdmin } = useSession();
  const { data, mutate } = useSWR<Page<Facility>>(isAdmin ? `/v1/facilities/?condominium=${condo.id}&page_size=100` : null);
  const [editing, setEditing] = useState<Facility | "new" | null>(null);
  const [deleting, setDeleting] = useState<Facility | null>(null);
  if (!isAdmin) return <Card><Empty>Facilities are managed by the site admin.</Empty></Card>;

  return (
    <>
      <PageHeader title="Facilities & payments" description="What residents can book in the app, when, and at what price."
        action={<Button variant="primary" onClick={() => setEditing("new")}><Icon name="plus" className="h-4 w-4" /> Add facility</Button>} />
      <div className="grid gap-5 xl:grid-cols-[1.6fr_1fr]">
        <div>
          {!data ? <Loading /> : data.results.length === 0 ? (
            <Card><Empty>No facilities yet. Add your BBQ pits, function rooms or courts so residents can book them.</Empty></Card>
          ) : (
            <div className="grid gap-4 md:grid-cols-2">
              {data.results.map((f) => (
                <Card key={f.id} className="overflow-hidden">
                  {f.has_image
                    ? <AuthImage path={`/v1/facilities/${f.id}/photo/`} alt={f.name} className="h-32 w-full object-cover" />
                    : <div className="flex h-20 items-center justify-center bg-surface-2 text-muted"><Icon name="calendar" className="h-7 w-7" /></div>}
                  <div className="p-4">
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <div className="font-semibold text-ink">{f.name}</div>
                        <div className="text-xs text-muted">{f.location || "—"}</div>
                      </div>
                      <div className="flex items-center gap-0.5">
                        <IconButton label="Edit" onClick={() => setEditing(f)}><Icon name="pencil" className="h-[18px] w-[18px]" /></IconButton>
                        <IconButton label="Delete" onClick={() => setDeleting(f)}><Icon name="x" className="h-[18px] w-[18px]" /></IconButton>
                      </div>
                    </div>
                    <div className="mt-3 flex flex-wrap gap-1.5">
                      {f.is_active ? <Badge tone="green">Bookable</Badge> : <Badge>Hidden</Badge>}
                      <Badge tone={f.is_paid ? "blue" : "slate"}>{f.is_paid ? `${money(f.price_per_slot)} / slot${Number(f.deposit) ? ` + ${money(f.deposit)} deposit` : ""}` : "Free"}</Badge>
                    </div>
                    <dl className="mt-3 grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
                      <dt className="text-muted">Hours</dt><dd className="text-body">{hhmm(f.opens_at)}–{hhmm(f.closes_at)}</dd>
                      <dt className="text-muted">Days</dt><dd className="text-body">{f.open_days.length === 7 ? "Every day" : f.open_days.map((d) => DAYS[d]).join(", ") || "Closed"}</dd>
                      <dt className="text-muted">Slots</dt><dd className="text-body">{f.slot_minutes} min, up to {f.max_slots_per_booking}</dd>
                      <dt className="text-muted">Ahead</dt><dd className="text-body">{f.advance_days} days · cancel {f.cancel_hours} h before</dd>
                    </dl>
                  </div>
                </Card>
              ))}
            </div>
          )}
        </div>
        <Payments condoId={condo.id} />
      </div>

      {editing && <FacilityModal condoId={condo.id} facility={editing === "new" ? null : editing} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); mutate(); }} />}
      <ConfirmDialog open={!!deleting} title={`Delete ${deleting?.name}?`} confirmLabel="Delete"
        message="Facilities with bookings cannot be deleted; untick “Residents can book it” to hide them instead."
        onClose={() => setDeleting(null)} onConfirm={async () => { await remove(`/v1/facilities/${deleting!.id}/`); mutate(); }} />
    </>
  );
}

export default function Page() {
  return <ModuleGate module="facilities"><FacilitiesPage /></ModuleGate>;
}
