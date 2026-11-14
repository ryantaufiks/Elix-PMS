"use client";

import { useState } from "react";

import { api, ApiError, errorMessage } from "@/lib/api";

import { Button, Checkbox, cx, ErrorNote, Field, Input, Modal, Select, Textarea, useToast } from "./ui";

export type Option = { value: string | number; label: string };
type Values = Record<string, unknown>;

export type FieldDef = {
  name: string;
  label: string;
  type?: "text" | "number" | "email" | "tel" | "url" | "password" | "secret" | "secret-text" | "textarea" | "select" | "checkbox" | "time" | "weekdays";
  options?: Option[];
  hint?: string;
  placeholder?: string;
  required?: boolean;
  /** Only show (and send) when this returns true. */
  show?: (values: Values) => boolean;
  /** Span both columns of the two-column grid. */
  wide?: boolean;
  section?: string;
  transform?: (value: string) => string;
  /** Send null instead of "" (IP addresses and other optional typed values). */
  nullable?: boolean;
};

/** Initial form values from a record (or defaults for a new one). Secrets always start blank. */
export function initialValues(fields: FieldDef[], record: Values | null, defaults: Values = {}): Values {
  const values: Values = {};
  for (const f of fields) {
    const current = record?.[f.name] ?? defaults[f.name];
    if (f.type === "secret" || f.type === "secret-text" || f.type === "password") values[f.name] = "";
    else if (f.type === "checkbox") values[f.name] = Boolean(current ?? false);
    else if (f.type === "weekdays") values[f.name] = Array.isArray(current) ? current : [];
    else values[f.name] = current ?? "";
  }
  return values;
}

/** Body for the API: hidden fields dropped, blank numbers -> null, blank secrets omitted on update
 * (kept as they are), secrets marked for removal (null) sent as null. */
function toBody(fields: FieldDef[], values: Values, isUpdate: boolean): Values {
  const body: Values = {};
  for (const f of fields) {
    if (f.show && !f.show(values)) continue;
    let value = values[f.name];
    if ((f.type === "secret" || f.type === "secret-text" || f.type === "password") && value === "" && isUpdate) continue;
    if (f.type === "number") value = value === "" || value === null ? null : Number(value);
    else if (f.type === "select") value = value === "" ? null : f.options?.find((o) => String(o.value) === String(value))?.value ?? value;
    else if (f.nullable && value === "") value = null;
    body[f.name] = value;
  }
  return body;
}

function fieldErrors(error: unknown): Record<string, string> {
  if (!(error instanceof ApiError) || !error.data || typeof error.data !== "object" || Array.isArray(error.data)) return {};
  const out: Record<string, string> = {};
  for (const [key, value] of Object.entries(error.data as Record<string, unknown>)) {
    if (key !== "detail" && key !== "non_field_errors") out[key] = errorMessage(value, "Invalid value");
  }
  return out;
}

export function FormFields({ fields, values, onChange, errors, record }: {
  fields: FieldDef[];
  values: Values;
  onChange: (name: string, value: unknown) => void;
  errors: Record<string, string>;
  record?: Values | null;
}) {
  return (
    <div className="grid gap-4 sm:grid-cols-2">
      {fields.map((f) => {
        if (f.show && !f.show(values)) return null;
        const value = values[f.name];
        const secret = f.type === "secret" || f.type === "secret-text";
        const saved = Boolean(record?.[`has_${f.name}`]);
        const removing = secret && value === null;
        const secretHint = removing ? "Removed when you save." : saved ? "Leave blank to keep it." : undefined;
        let control: React.ReactNode;
        if (removing) {
          control = (
            <div className="flex items-center justify-between gap-3 rounded-md border border-dashed border-rose-400/60 bg-rose-500/5 px-3 py-2 text-sm text-rose-700 dark:text-rose-300">
              <span>Will be removed</span>
              <button type="button" className="font-medium text-ink underline-offset-2 hover:underline" onClick={() => onChange(f.name, "")}>Undo</button>
            </div>
          );
        } else if (f.type === "checkbox") {
          control = <Checkbox label={f.label} checked={Boolean(value)} onChange={(e) => onChange(f.name, e.target.checked)} />;
        } else if (f.type === "weekdays") {
          control = <WeekdayPicker value={(value as number[]) ?? []} onChange={(days) => onChange(f.name, days)} />;
        } else if (f.type === "select") {
          control = (
            <Select value={String(value ?? "")} required={f.required} onChange={(e) => onChange(f.name, e.target.value)}>
              {!f.required && <option value="">—</option>}
              {f.required && value === "" && <option value="" disabled>Choose…</option>}
              {f.options?.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </Select>
          );
        } else if (f.type === "textarea" || f.type === "secret-text") {
          control = (
            <Textarea
              rows={f.type === "secret-text" ? 5 : 3}
              value={String(value ?? "")}
              placeholder={f.type === "secret-text" && saved ? "•••••••• saved" : f.placeholder}
              required={f.required && !saved}
              className={f.type === "secret-text" ? "font-mono text-xs" : undefined}
              onChange={(e) => onChange(f.name, e.target.value)}
            />
          );
        } else {
          const type = f.type === "secret" || f.type === "password" ? "password" : f.type ?? "text";
          control = (
            <Input
              type={type}
              value={String(value ?? "")}
              placeholder={f.type === "secret" && saved ? "•••••••• saved" : f.placeholder}
              required={f.required && !(f.type === "secret" && saved)}
              autoComplete={type === "password" ? "new-password" : "off"}
              onChange={(e) => onChange(f.name, f.transform ? f.transform(e.target.value) : e.target.value)}
            />
          );
        }
        return (
          <div key={f.name} className={cx((f.wide || f.type === "textarea" || f.type === "secret-text") && "sm:col-span-2", f.type === "checkbox" && "flex flex-col justify-end")}>
            {f.section && <h3 className="mb-3 mt-2 border-t border-line pt-4 text-xs font-semibold uppercase tracking-wide text-muted">{f.section}</h3>}
            {f.type === "checkbox" ? (
              <div>
                {control}
                {f.hint && <p className="mt-1 text-xs text-muted">{f.hint}</p>}
              </div>
            ) : (
              <Field label={f.label} hint={errors[f.name] ? undefined : removing ? secretHint : f.hint ?? secretHint}>
                {control}
              </Field>
            )}
            {secret && saved && !removing && (
              <div className="mt-1 flex items-center gap-2 text-xs">
                <span className="rounded bg-emerald-500/10 px-1.5 py-0.5 font-medium text-emerald-700 dark:text-emerald-300">Saved</span>
                <button type="button" className="font-medium text-rose-600 hover:underline dark:text-rose-400" onClick={() => onChange(f.name, null)}>Remove</button>
              </div>
            )}
            {errors[f.name] && <p className="mt-1 text-xs font-medium text-rose-600 dark:text-rose-400">{errors[f.name]}</p>}
          </div>
        );
      })}
    </div>
  );
}

/** Create or edit one record in a modal. ``endpoint`` is the collection URL (POST) or item URL (PATCH). */
export function EntityModal<T>({ title, fields, record, defaults, endpoint, extra, onClose, onSaved, wide, submitLabel = "Save" }: {
  title: string;
  fields: FieldDef[];
  record: Values | null;
  defaults?: Values;
  endpoint: string;
  extra?: Values;
  onClose: () => void;
  onSaved: (saved: T) => void;
  wide?: boolean;
  submitLabel?: string;
}) {
  const toast = useToast();
  const [values, setValues] = useState(() => initialValues(fields, record, defaults));
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const errors = fieldErrors(error);
  const shownErrors = Object.keys(errors).filter((k) => fields.some((f) => f.name === k && (!f.show || f.show(values))));

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const saved = await api<T>(endpoint, { method: record ? "PATCH" : "POST", body: { ...toBody(fields, values, !!record), ...extra } });
      toast("success", record ? "Saved." : "Created.");
      onSaved(saved);
    } catch (err) {
      setError(err);
      setBusy(false);
    }
  }

  const topError = error && (!(error instanceof ApiError) || shownErrors.length === 0) ? error : null;
  return (
    <Modal
      open
      wide={wide}
      onClose={onClose}
      title={title}
      footer={<><Button onClick={onClose}>Cancel</Button><Button variant="primary" busy={busy} type="submit" form="entity-form">{submitLabel}</Button></>}
    >
      <form id="entity-form" onSubmit={submit} className="space-y-4">
        <ErrorNote error={topError} />
        <FormFields fields={fields} values={values} errors={errors} record={record} onChange={(name, value) => setValues((v) => ({ ...v, [name]: value }))} />
      </form>
    </Modal>
  );
}

export function ConfirmDialog({ open, title, message, confirmLabel, onConfirm, onClose }: {
  open: boolean;
  title: string;
  message: React.ReactNode;
  confirmLabel: string;
  onConfirm: () => Promise<unknown>;
  onClose: () => void;
}) {
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  async function confirm() {
    setBusy(true);
    try {
      await onConfirm();
      onClose();
    } catch (error) {
      toast("error", (error as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal open={open} onClose={onClose} title={title} footer={<><Button onClick={onClose}>Cancel</Button><Button variant="danger" busy={busy} onClick={confirm}>{confirmLabel}</Button></>}>
      <div className="text-sm text-body">{message}</div>
    </Modal>
  );
}

const WEEKDAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

/** Seven toggles, Monday = 0 (as the API stores weekdays). */
export function WeekdayPicker({ value, onChange }: { value: number[]; onChange: (days: number[]) => void }) {
  return (
    <div className="flex flex-wrap gap-1.5" role="group" aria-label="Days">
      {WEEKDAY_LABELS.map((label, day) => {
        const on = value.includes(day);
        return (
          <button key={day} type="button" aria-pressed={on}
            onClick={() => onChange(on ? value.filter((d) => d !== day) : [...value, day].sort())}
            className={cx("min-w-11 rounded-md border px-2.5 py-1.5 text-sm font-medium transition-colors",
              on ? "border-primary-500 bg-primary-500/10 text-primary-700 dark:text-primary-300" : "border-line text-muted hover:text-ink")}>
            {label}
          </button>
        );
      })}
    </div>
  );
}

export function Tabs<K extends string>({ tabs, active, onChange }: { tabs: { key: K; label: string; count?: number }[]; active: K; onChange: (key: K) => void }) {
  return (
    <div className="flex gap-1 overflow-x-auto border-b border-line px-3">
      {tabs.map((t) => (
        <button
          key={t.key}
          onClick={() => onChange(t.key)}
          className={cx(
            "-mb-px whitespace-nowrap border-b-2 px-4 py-3.5 text-sm font-medium transition-colors",
            active === t.key ? "border-primary-500 text-primary-600 dark:text-primary-300" : "border-transparent text-muted hover:text-ink",
          )}
        >
          {t.label}
          {t.count !== undefined && <span className="ml-2 rounded-full bg-surface-3 px-2 py-0.5 text-xs text-muted">{t.count}</span>}
        </button>
      ))}
    </div>
  );
}

/** Text that is easy to copy (webhook URLs, usernames, tokens). */
export function CopyField({ value, mono = true }: { value: string; mono?: boolean }) {
  const toast = useToast();
  return (
    <div className="flex gap-2">
      <Input readOnly value={value} className={mono ? "font-mono text-xs" : undefined} onFocus={(e) => e.target.select()} />
      <Button onClick={() => navigator.clipboard?.writeText(value).then(() => toast("success", "Copied."), () => toast("error", "Copy failed; select the text instead."))}>
        Copy
      </Button>
    </div>
  );
}

export async function remove(endpoint: string) {
  await api(endpoint, { method: "DELETE" });
}
