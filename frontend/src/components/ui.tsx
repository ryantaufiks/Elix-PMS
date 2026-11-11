"use client";

import { cloneElement, createContext, isValidElement, useCallback, useContext, useEffect, useId, useState } from "react";

const cx = (...classes: (string | false | null | undefined)[]) => classes.filter(Boolean).join(" ");
export { cx };

type ButtonProps = React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "danger" | "ghost" | "success";
  size?: "sm" | "md" | "lg";
  busy?: boolean;
};

/** A compact icon-only button; ``label`` shows as a tooltip on hover/focus and names it for screen readers. */
export function IconButton({ label, children, className, tone = "default", ...props }: React.ButtonHTMLAttributes<HTMLButtonElement> & {
  label: string; tone?: "default" | "primary";
}) {
  return (
    <button
      type="button"
      {...props}
      aria-label={label}
      className={cx(
        "group/icon relative inline-flex h-8 w-8 items-center justify-center rounded-md transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600 disabled:cursor-not-allowed disabled:opacity-50",
        tone === "primary" ? "text-primary-600 hover:bg-primary-500/10" : "text-muted hover:bg-surface-3 hover:text-ink",
        className,
      )}
    >
      {children}
      <span role="tooltip" className="pointer-events-none absolute right-full top-1/2 z-20 mr-1.5 -translate-y-1/2 whitespace-nowrap rounded-md bg-navy-950 px-2 py-1 text-xs font-medium text-white opacity-0 shadow-lg transition-opacity group-hover/icon:opacity-100 group-focus-visible/icon:opacity-100">
        {label}
      </span>
    </button>
  );
}

export function Button({ variant = "secondary", size = "md", busy, className, children, disabled, ...props }: ButtonProps) {
  return (
    <button
      {...props}
      disabled={disabled || busy}
      className={cx(
        "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md font-medium transition-all focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600 disabled:cursor-not-allowed disabled:opacity-50",
        size === "sm" && "h-8 px-3 text-sm",
        size === "md" && "h-10 px-4 text-sm",
        size === "lg" && "h-12 px-6 text-base",
        variant === "primary" && "bg-primary-500 text-white shadow-primary hover:bg-primary-600",
        variant === "success" && "bg-emerald-600 text-white hover:bg-emerald-700",
        variant === "secondary" && "border border-line bg-surface text-ink hover:bg-surface-2",
        variant === "danger" && "bg-rose-600 text-white hover:bg-rose-700",
        variant === "ghost" && "text-body hover:bg-surface-3 hover:text-ink",
        className,
      )}
    >
      {busy && <Spinner className="h-4 w-4" />}
      {children}
    </button>
  );
}

export function Spinner({ className = "h-5 w-5" }: { className?: string }) {
  return <span className={cx("inline-block animate-spin rounded-full border-2 border-current border-t-transparent", className)} />;
}

export function Card({ className, children }: { className?: string; children: React.ReactNode }) {
  return <section className={cx("rounded-xl border border-line bg-surface shadow-card", className)}>{children}</section>;
}

export function CardHeader({ title, action }: { title: React.ReactNode; action?: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3 border-b border-line px-5 py-4">
      <h2 className="text-base font-semibold text-ink">{title}</h2>
      {action}
    </div>
  );
}

const TONES = {
  green: "bg-emerald-500/10 text-emerald-700 ring-emerald-600/25 dark:text-emerald-300",
  red: "bg-rose-500/10 text-rose-700 ring-rose-600/25 dark:text-rose-300",
  amber: "bg-amber-500/10 text-amber-800 ring-amber-600/25 dark:text-amber-300",
  blue: "bg-primary-500/10 text-primary-700 ring-primary-600/25 dark:text-primary-300",
  slate: "bg-surface-3 text-body ring-slate-500/20",
};
export type Tone = keyof typeof TONES;

export function Badge({ tone = "slate", children }: { tone?: Tone; children: React.ReactNode }) {
  return (
    <span className={cx("inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium ring-1 ring-inset", TONES[tone])}>
      {children}
    </span>
  );
}

export function PageHeader({ title, description, action }: { title: string; description?: string; action?: React.ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-ink">{title}</h1>
        {description && <p className="mt-1 max-w-2xl text-sm text-muted">{description}</p>}
      </div>
      {action && <div className="flex flex-wrap gap-2">{action}</div>}
    </div>
  );
}

export function Empty({ children }: { children: React.ReactNode }) {
  return <div className="px-4 py-10 text-center text-sm text-muted">{children}</div>;
}

export function Loading() {
  return (
    <div className="flex justify-center py-10 text-muted">
      <Spinner />
    </div>
  );
}

export function ErrorNote({ error }: { error: unknown }) {
  if (!error) return null;
  return (
    <div className="rounded-lg bg-rose-500/10 px-3 py-2 text-sm text-rose-700 dark:text-rose-300">
      {error instanceof Error ? error.message : String(error)}
    </div>
  );
}

const inputClass =
  "block w-full rounded-md border border-line bg-surface px-3 py-2 text-sm text-ink placeholder:text-muted focus:border-primary-500 focus:outline-none focus:ring-2 focus:ring-primary-500/15 disabled:bg-surface-2";

export function Input(props: React.ComponentProps<"input">) {
  return <input {...props} className={cx(inputClass, props.className)} />;
}

export function Select(props: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return <select {...props} className={cx(inputClass, "pr-8", props.className)} />;
}

export function Textarea(props: React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea {...props} className={cx(inputClass, props.className)} />;
}

/** Label + control + hint. The label names only the control; the hint is linked as its description. */
export function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  const generated = useId();
  const child = isValidElement<{ id?: string; "aria-describedby"?: string }>(children) ? children : null;
  const id = child?.props.id ?? generated;
  const hintId = `${id}-hint`;
  return (
    <div>
      <label htmlFor={id} className="mb-1.5 block text-sm font-medium text-ink">{label}</label>
      {child ? cloneElement(child, { id, "aria-describedby": hint ? hintId : undefined }) : children}
      {hint && <span id={hintId} className="mt-1 block text-xs text-muted">{hint}</span>}
    </div>
  );
}

export function Checkbox({ label, ...props }: React.InputHTMLAttributes<HTMLInputElement> & { label: string }) {
  return (
    <label className="flex items-center gap-2 text-sm text-ink">
      <input type="checkbox" {...props} className="h-4 w-4 rounded border-line text-primary-700 focus:ring-primary-600" />
      {label}
    </label>
  );
}

export function Modal({ open, onClose, title, children, footer, wide }: {
  open: boolean;
  onClose: () => void;
  title: string;
  children: React.ReactNode;
  footer?: React.ReactNode;
  wide?: boolean;
}) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-slate-900/40 p-0 sm:items-center sm:p-4" onMouseDown={onClose}>
      <div
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onMouseDown={(e) => e.stopPropagation()}
        className={cx("max-h-[92vh] w-full overflow-y-auto rounded-t-2xl bg-surface shadow-xl sm:rounded-2xl", wide ? "sm:max-w-3xl" : "sm:max-w-lg")}
      >
        <div className="flex items-center justify-between border-b border-line px-5 py-4">
          <h2 className="text-base font-semibold text-ink">{title}</h2>
          <button onClick={onClose} className="rounded-md p-1 text-muted hover:bg-surface-3 hover:text-body" aria-label="Close">
            <svg viewBox="0 0 20 20" className="h-5 w-5" fill="currentColor"><path d="M6.28 5.22a.75.75 0 0 0-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 1 0 1.06 1.06L10 11.06l3.72 3.72a.75.75 0 1 0 1.06-1.06L11.06 10l3.72-3.72a.75.75 0 0 0-1.06-1.06L10 8.94 6.28 5.22Z" /></svg>
          </button>
        </div>
        <div className="px-5 py-4">{children}</div>
        {footer && <div className="flex justify-end gap-2 border-t border-line px-5 py-3">{footer}</div>}
      </div>
    </div>
  );
}

export function Pagination({ page, count, pageSize = 50, onPage }: { page: number; count: number; pageSize?: number; onPage: (page: number) => void }) {
  const pages = Math.max(1, Math.ceil(count / pageSize));
  if (pages <= 1) return null;
  return (
    <div className="flex items-center justify-between border-t border-line px-4 py-3 text-sm text-body">
      <span>
        Page {page} of {pages} · {count} total
      </span>
      <div className="flex gap-2">
        <Button size="sm" disabled={page <= 1} onClick={() => onPage(page - 1)}>Previous</Button>
        <Button size="sm" disabled={page >= pages} onClick={() => onPage(page + 1)}>Next</Button>
      </div>
    </div>
  );
}

export function Table({ children }: { children: React.ReactNode }) {
  return (
    <div className="overflow-x-auto">
      <table className="tbl min-w-full divide-y divide-line text-sm">{children}</table>
    </div>
  );
}

export function Th({ children, className }: { children?: React.ReactNode; className?: string }) {
  return <th className={cx("whitespace-nowrap bg-surface-2 px-5 py-3 text-left text-xs font-semibold uppercase tracking-wide text-muted", className)}>{children}</th>;
}

/** ``label`` names the column on phones, where the table turns into cards (see globals.css). */
export function Td({ children, className, label }: { children?: React.ReactNode; className?: string; label?: string }) {
  // One wrapper per cell, so on phones the whole value sits as a block beside its label.
  return <td data-label={label} className={cx("px-5 py-3.5 align-top text-body", className)}><div className="min-w-0">{children}</div></td>;
}

// --- Row actions -------------------------------------------------------------

export type MenuItem = { label: string; onClick?: () => void; href?: string; danger?: boolean; hidden?: boolean };

/** The actions of a table row: an optional visible ``primary`` action and a "⋯" menu with the rest.
    Destructive items sit last, after a divider, in red, so they are not clicked by accident. */
export function RowMenu({ items, primary, label = "More actions" }: { items: MenuItem[]; primary?: MenuItem; label?: string }) {
  const [open, setOpen] = useState<{ top: number; right: number } | null>(null);
  const id = useId();
  const visible = items.filter((i) => !i.hidden);
  const plain = visible.filter((i) => !i.danger);
  const danger = visible.filter((i) => i.danger);

  useEffect(() => {
    if (!open) return;
    const close = () => setOpen(null);
    const onDown = (e: MouseEvent) => { if (!(e.target as Element).closest(`[data-menu="${id}"]`)) close(); };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && close();
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    window.addEventListener("scroll", close, true);
    window.addEventListener("resize", close);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
      window.removeEventListener("scroll", close, true);
      window.removeEventListener("resize", close);
    };
  }, [open, id]);

  function toggle(e: React.MouseEvent<HTMLButtonElement>) {
    if (open) return setOpen(null);
    const r = e.currentTarget.getBoundingClientRect();
    setOpen({ top: r.bottom + 4, right: Math.max(8, window.innerWidth - r.right) });
  }

  const item = (i: MenuItem) => {
    const className = cx("block w-full rounded-md px-3 py-2 text-left text-sm", i.danger ? "text-rose-600 hover:bg-rose-500/10" : "text-ink hover:bg-surface-2");
    return i.href
      ? <a key={i.label} href={i.href} role="menuitem" className={className}>{i.label}</a>
      : <button key={i.label} type="button" role="menuitem" className={className} onClick={() => { setOpen(null); i.onClick?.(); }}>{i.label}</button>;
  };

  return (
    <span className="inline-flex items-center gap-1" data-menu={id}>
      {primary && !primary.hidden && (primary.href
        ? <a href={primary.href}><Button size="sm" variant="ghost">{primary.label}</Button></a>
        : <Button size="sm" variant="ghost" onClick={primary.onClick}>{primary.label}</Button>)}
      {visible.length > 0 && (
        <>
          <IconButton label={label} onClick={toggle} aria-haspopup="menu" aria-expanded={!!open}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.5} strokeLinecap="round" className="h-5 w-5" aria-hidden="true"><path d="M4.5 12h.6M11.7 12h.6M18.9 12h.6" /></svg>
          </IconButton>
          {open && (
            <div role="menu" style={{ position: "fixed", top: open.top, right: open.right }}
              className="z-50 min-w-44 rounded-xl border border-line bg-surface p-1 shadow-lg">
              {plain.map(item)}
              {plain.length > 0 && danger.length > 0 && <div className="my-1 border-t border-line" />}
              {danger.map(item)}
            </div>
          )}
        </>
      )}
    </span>
  );
}

// --- Toasts ------------------------------------------------------------------

type Toast = { id: number; tone: "success" | "error" | "info"; message: string };
const ToastContext = createContext<(tone: Toast["tone"], message: string) => void>(() => {});

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const push = useCallback((tone: Toast["tone"], message: string) => {
    const id = Date.now() + Math.random();
    setToasts((list) => [...list, { id, tone, message }]);
    setTimeout(() => setToasts((list) => list.filter((t) => t.id !== id)), 5000);
  }, []);
  return (
    <ToastContext.Provider value={push}>
      {children}
      <div className="pointer-events-none fixed inset-x-0 bottom-4 z-[60] flex flex-col items-center gap-2 px-4 sm:items-end sm:px-6" aria-live="polite">
        {toasts.map((t) => (
          <div
            key={t.id}
            className={cx(
              "pointer-events-auto max-w-md rounded-lg px-4 py-3 text-sm font-medium shadow-lg",
              t.tone === "success" && "bg-emerald-700 text-white",
              t.tone === "error" && "bg-rose-700 text-white",
              t.tone === "info" && "bg-slate-800 text-white",
            )}
          >
            {t.message}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export const useToast = () => useContext(ToastContext);
