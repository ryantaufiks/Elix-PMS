"use client";

import { useState } from "react";

import { api, ApiError } from "@/lib/api";
import { condoDefaults, condoFields } from "@/lib/fields";
import type { Condominium } from "@/lib/types";

import { FormFields, initialValues } from "./forms";
import { Button, ErrorNote } from "./ui";

/** First run for the platform administrator: create the first condominium without leaving the dashboard. */
export function Onboarding({ onCreated, onLogout }: { onCreated: (id: number) => void; onLogout: () => void }) {
  const fields = condoFields({ superuser: true, creating: true });
  const [values, setValues] = useState(() => initialValues(fields, null, condoDefaults));
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const errors = error instanceof ApiError && error.data && typeof error.data === "object"
    ? Object.fromEntries(Object.entries(error.data as Record<string, unknown>).map(([k, v]) => [k, Array.isArray(v) ? String(v[0]) : String(v)]))
    : {};

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const condo = await api<Condominium>("/v1/condominiums/", { method: "POST", body: values });
      onCreated(condo.id);
    } catch (err) {
      setError(err);
      setBusy(false);
    }
  }

  return (
    <div className="min-h-screen bg-canvas">
      <div className="hero-band px-4 pb-32 pt-12 text-white sm:px-8">
        <div className="mx-auto max-w-3xl">
          <div className="mb-8 flex items-center gap-2.5">
            <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-white text-base font-bold text-primary-600">E</span>
            <span className="text-xl font-semibold">Elix PMS</span>
          </div>
          <h1 className="text-3xl font-semibold tracking-tight">Welcome! Let&apos;s set up your first site</h1>
          <p className="mt-2 text-white/80">Add the condominium now. Blocks, units, gates, devices and staff come next, all from this dashboard.</p>
        </div>
      </div>
      <div className="mx-auto -mt-24 max-w-3xl px-4 pb-12 sm:px-8">
        <form onSubmit={submit} className="space-y-5 rounded-lg bg-white p-6 shadow-card sm:p-8">
          <ErrorNote error={Object.keys(errors).length ? null : error} />
          <FormFields fields={fields} values={values} errors={errors} onChange={(n, v) => setValues((s) => ({ ...s, [n]: v }))} />
          <div className="flex items-center justify-between border-t border-slate-100 pt-5">
            <button type="button" onClick={onLogout} className="text-sm text-muted hover:text-ink">Sign out</button>
            <Button type="submit" variant="primary" busy={busy}>Create condominium</Button>
          </div>
        </form>
      </div>
    </div>
  );
}
