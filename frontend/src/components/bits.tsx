"use client";

import { useEffect, useState } from "react";
import useSWR from "swr";

import { api, imageUrl, query, unitSearch } from "@/lib/api";
import { CALL_STATUS_LABEL } from "@/lib/format";
import type { AccessResult, CallStatus, Gate, Page, Unit } from "@/lib/types";

import { Badge, Button, Field, Input, Modal, Spinner, Textarea, type Tone, useToast } from "./ui";

export function ResultBadge({ result }: { result: AccessResult }) {
  const tone: Tone = result === "granted" ? "green" : result === "denied" ? "red" : "amber";
  return <Badge tone={tone}>{result === "granted" ? "Granted" : result === "denied" ? "Denied" : "Error"}</Badge>;
}

const CALL_TONE: Record<CallStatus, Tone> = {
  ringing: "blue", answered: "blue", approved: "green", rejected: "red", missed: "amber", cancelled: "slate",
};

export function CallStatusBadge({ status }: { status: CallStatus }) {
  return <Badge tone={CALL_TONE[status]}>{CALL_STATUS_LABEL[status]}</Badge>;
}

/** <img> for an endpoint that needs the JWT (snapshots, QR codes). */
export function AuthImage({ path, alt, className }: { path: string; alt: string; className?: string }) {
  const [src, setSrc] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let url: string | null = null;
    let cancelled = false;
    setSrc(null);
    setFailed(false);
    imageUrl(path)
      .then((u) => {
        url = u;
        if (cancelled) URL.revokeObjectURL(u);
        else setSrc(u);
      })
      .catch(() => !cancelled && setFailed(true));
    return () => {
      cancelled = true;
      if (url) URL.revokeObjectURL(url);
    };
  }, [path]);
  if (failed) return <div className={`flex items-center justify-center bg-slate-100 text-xs text-slate-400 ${className}`}>No image</div>;
  if (!src) return <div className={`flex items-center justify-center bg-slate-100 text-slate-400 ${className}`}><Spinner className="h-4 w-4" /></div>;
  // eslint-disable-next-line @next/next/no-img-element
  return <img src={src} alt={alt} className={className} />;
}

export function useGates(condoId: number) {
  return useSWR<Page<Gate>>(`/v1/gates/${query({ condominium: condoId, page_size: 200 })}`);
}

/** Confirm + reason, then POST /gates/{id}/open/. The relay command itself runs in the background. */
export function OpenGateDialog({ gate, onClose }: { gate: Gate | null; onClose: () => void }) {
  const toast = useToast();
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => setReason(""), [gate]);
  async function open() {
    if (!gate) return;
    setBusy(true);
    try {
      await api(`/v1/gates/${gate.id}/open/`, { method: "POST", body: { reason } });
      toast("success", `Opening ${gate.name}…`);
      onClose();
    } catch (error) {
      toast("error", (error as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal
      open={!!gate}
      onClose={onClose}
      title={`Open ${gate?.name ?? "gate"}`}
      footer={
        <>
          <Button onClick={onClose}>Cancel</Button>
          <Button variant="primary" busy={busy} onClick={open}>Open now</Button>
        </>
      }
    >
      <p className="mb-4 text-sm text-slate-600">The opening is recorded in the access log under your name.</p>
      <Field label="Reason (optional)">
        <Textarea rows={2} value={reason} maxLength={255} onChange={(e) => setReason(e.target.value)} placeholder="e.g. Delivery van, resident forgot card" autoFocus />
      </Field>
    </Modal>
  );
}

/** Search-as-you-type unit selector (Block · #floor-unit). */
export function UnitPicker({ condoId, value, onChange, initialLabel }: {
  condoId: number;
  value: number | null;
  onChange: (unit: Unit | null) => void;
  initialLabel?: string;
}) {
  const [text, setText] = useState(initialLabel ?? "");
  const [open, setOpen] = useState(false);
  const { data } = useSWR<Page<Unit>>(open ? `/v1/units/${query({ condominium: condoId, is_active: true, search: unitSearch(text), page_size: 20 })}` : null);
  return (
    <div className="relative">
      <Input
        value={text}
        placeholder="Search unit, e.g. 05-12"
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
        onChange={(e) => {
          setText(e.target.value);
          if (value) onChange(null);
        }}
      />
      {open && data && (
        <ul className="absolute z-10 mt-1 max-h-56 w-full overflow-y-auto rounded-lg border border-slate-200 bg-white py-1 shadow-lg">
          {data.results.length === 0 && <li className="px-3 py-2 text-sm text-slate-500">No matching unit</li>}
          {data.results.map((unit) => (
            <li key={unit.id}>
              <button
                type="button"
                className="block w-full px-3 py-2 text-left text-sm hover:bg-slate-50"
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => {
                  setText(unit.display_name);
                  onChange(unit);
                  setOpen(false);
                }}
              >
                {unit.display_name}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function SearchInput({ value, onChange, placeholder }: { value: string; onChange: (v: string) => void; placeholder: string }) {
  const [text, setText] = useState(value);
  useEffect(() => setText(value), [value]);
  useEffect(() => {
    const id = setTimeout(() => text !== value && onChange(text), 300);
    return () => clearTimeout(id);
  }, [text, value, onChange]);
  return <Input type="search" value={text} onChange={(e) => setText(e.target.value)} placeholder={placeholder} className="sm:w-64" />;
}
