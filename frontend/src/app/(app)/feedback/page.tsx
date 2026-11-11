"use client";

import { useState } from "react";
import useSWR from "swr";

import { SearchInput } from "@/components/bits";
import { Icon } from "@/components/icons";
import { Badge, Button, Card, cx, Empty, ErrorNote, Field, Loading, Modal, PageHeader, Pagination, Select, Textarea, useToast } from "@/components/ui";
import { api, query } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { useLiveEvents } from "@/lib/live";
import { useSession } from "@/lib/session";
import type { Feedback, FeedbackSummary, Page } from "@/lib/types";
import { ModuleGate } from "@/components/ModuleGate";

const CATEGORIES = [
  ["security", "Security"], ["cleanliness", "Cleanliness"], ["facilities", "Facilities"], ["maintenance", "Maintenance"],
  ["management", "Management office"], ["app", "Elix app"], ["other", "Other"],
];
const STATUS_TONE = { new: "amber", in_progress: "blue", resolved: "green" } as const;

function Stars({ value, size = "h-4 w-4" }: { value: number; size?: string }) {
  return (
    <span className="inline-flex gap-0.5" aria-label={`${value} of 5 stars`}>
      {[1, 2, 3, 4, 5].map((i) => (
        <svg key={i} viewBox="0 0 24 24" className={cx(size, i <= Math.round(value) ? "fill-amber-400 text-amber-400" : "fill-none text-line")} stroke="currentColor" strokeWidth={1.5}>
          <path d="M12 3.5l2.6 5.3 5.9.9-4.3 4.1 1 5.8L12 16.9l-5.2 2.7 1-5.8-4.3-4.1 5.9-.9Z" />
        </svg>
      ))}
    </span>
  );
}

function Reply({ feedback, onClose, onSaved }: { feedback: Feedback; onClose: () => void; onSaved: () => void }) {
  const toast = useToast();
  const [reply, setReply] = useState(feedback.reply);
  const [status, setStatus] = useState<Feedback["status"]>(feedback.status === "new" ? "in_progress" : feedback.status);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  async function save() {
    setBusy(true);
    try {
      await api(`/v1/feedback/${feedback.id}/reply/`, { method: "POST", body: { reply, status } });
      toast("success", "Reply saved. The resident sees it in the app.");
      onSaved();
    } catch (err) {
      setError(err);
      setBusy(false);
    }
  }
  return (
    <Modal open onClose={onClose} title={`Reply to ${feedback.resident_name || feedback.unit_display}`}
      footer={<><Button onClick={onClose}>Cancel</Button><Button variant="primary" busy={busy} onClick={save}>Save</Button></>}>
      <div className="space-y-4">
        <ErrorNote error={error} />
        <div className="rounded-lg bg-surface-2 p-3 text-sm">
          <div className="flex items-center gap-2"><Stars value={feedback.rating} /><span className="text-muted">{feedback.category_display}</span></div>
          <p className="mt-2 whitespace-pre-wrap text-body">{feedback.comment || <span className="text-muted">No comment.</span>}</p>
        </div>
        <Field label="Reply (shown to the resident)"><Textarea rows={4} value={reply} onChange={(e) => setReply(e.target.value)} /></Field>
        <Field label="Status">
          <Select value={status} onChange={(e) => setStatus(e.target.value as Feedback["status"])}>
            <option value="new">New</option><option value="in_progress">In progress</option><option value="resolved">Resolved</option>
          </Select>
        </Field>
      </div>
    </Modal>
  );
}

function FeedbackPage() {
  const { condo, isManager } = useSession();
  const [category, setCategory] = useState("");
  const [status, setStatus] = useState("");
  const [rating, setRating] = useState("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [replying, setReplying] = useState<Feedback | null>(null);
  const filters = { condominium: condo.id, category, status, rating, search };
  const { data, mutate } = useSWR<Page<Feedback>>(`/v1/feedback/${query({ ...filters, page })}`, { keepPreviousData: true });
  const { data: summary, mutate: refreshSummary } = useSWR<FeedbackSummary>(`/v1/feedback/summary/${query(filters)}`);
  useLiveEvents((event) => {
    if (event.type === "feedback") { mutate(); refreshSummary(); }
  });
  const max = Math.max(1, ...Object.values(summary?.by_rating ?? {}));
  const reset = () => setPage(1);

  return (
    <>
      <PageHeader title="Feedback" description="How residents rate the estate's services, from the resident app." />
      <div className="mb-5 grid gap-4 md:grid-cols-[1fr_2fr]">
        <Card className="flex items-center gap-4 p-5">
          <div className="text-4xl font-semibold tabular-nums text-ink">{summary?.average?.toFixed(1) ?? "—"}</div>
          <div>
            <Stars value={summary?.average ?? 0} size="h-5 w-5" />
            <div className="mt-1 text-sm text-muted">{summary?.count ?? 0} rating{summary?.count === 1 ? "" : "s"} · {summary?.open ?? 0} open</div>
          </div>
        </Card>
        <Card className="p-5">
          <ul className="space-y-1.5">
            {[5, 4, 3, 2, 1].map((r) => {
              const n = summary?.by_rating[String(r)] ?? 0;
              return (
                <li key={r}>
                  <button type="button" onClick={() => { setRating(rating === String(r) ? "" : String(r)); reset(); }}
                    className={cx("flex w-full items-center gap-3 rounded px-1 text-sm", rating === String(r) && "bg-primary-500/10")}>
                    <span className="w-8 text-body">{r} ★</span>
                    <span className="h-2 flex-1 rounded-full bg-surface-3"><span className="block h-2 rounded-full bg-amber-400" style={{ width: `${(n / max) * 100}%` }} /></span>
                    <span className="w-8 text-right tabular-nums text-ink">{n}</span>
                  </button>
                </li>
              );
            })}
          </ul>
        </Card>
      </div>
      <Card>
        <div className="flex flex-wrap gap-2 border-b border-line p-4">
          <SearchInput value={search} onChange={(v) => { setSearch(v); reset(); }} placeholder="Comment, reply, resident, unit" />
          <Select value={category} onChange={(e) => { setCategory(e.target.value); reset(); }} className="sm:w-48" aria-label="Category">
            <option value="">All categories</option>
            {CATEGORIES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </Select>
          <Select value={status} onChange={(e) => { setStatus(e.target.value); reset(); }} className="sm:w-40" aria-label="Status">
            <option value="">Any status</option><option value="new">New</option><option value="in_progress">In progress</option><option value="resolved">Resolved</option>
          </Select>
          {rating && <Button size="sm" variant="ghost" onClick={() => setRating("")}>{rating} ★ only ✕</Button>}
        </div>
        {!data ? <Loading /> : data.results.length === 0 ? <Empty icon="star" title="No feedback yet">Residents rate the estate&apos;s services from the app; replies go back to them there.</Empty> : (
          <ul className="divide-y divide-line">
            {data.results.map((f) => (
              <li key={f.id} className="flex flex-col gap-3 p-4 sm:flex-row sm:items-start">
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <Stars value={f.rating} />
                    <Badge>{f.category_display}</Badge>
                    <Badge tone={STATUS_TONE[f.status]}>{f.status_display}</Badge>
                    <span className="text-xs text-muted">{f.resident_name || "Resident"} · {f.unit_display || "—"} · {formatDateTime(f.created_at)}</span>
                  </div>
                  <p className="mt-2 whitespace-pre-wrap text-sm text-body">{f.comment || <span className="text-muted">No comment.</span>}</p>
                  {f.reply && (
                    <div className="mt-2 rounded-lg border-l-2 border-primary-500 bg-surface-2 px-3 py-2 text-sm">
                      <div className="text-xs text-muted">Reply by {f.replied_by_name} · {formatDateTime(f.replied_at)}</div>
                      <p className="mt-1 whitespace-pre-wrap text-body">{f.reply}</p>
                    </div>
                  )}
                </div>
                {isManager && <Button size="sm" onClick={() => setReplying(f)}><Icon name="pencil" className="h-4 w-4" /> {f.reply ? "Edit reply" : "Reply"}</Button>}
              </li>
            ))}
          </ul>
        )}
        {data && <Pagination page={page} count={data.count} onPage={setPage} />}
      </Card>
      {replying && <Reply feedback={replying} onClose={() => setReplying(null)} onSaved={() => { setReplying(null); mutate(); refreshSummary(); }} />}
    </>
  );
}

export default function Page() {
  return <ModuleGate module="resident_app"><FeedbackPage /></ModuleGate>;
}
