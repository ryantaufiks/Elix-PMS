"use client";

import { useRef, useState } from "react";
import useSWR from "swr";

import { ConfirmDialog, remove } from "@/components/forms";
import { Icon } from "@/components/icons";
import { Button, Empty, ErrorNote, Field, IconButton, Input, Loading, Modal, Select, useToast } from "@/components/ui";
import { api, ApiError, query } from "@/lib/api";
import { DOCUMENT_KIND_LABEL, fileSize, formatDateTime } from "@/lib/format";
import type { Page, ResidentDocument } from "@/lib/types";

const KIND_OPTIONS = Object.entries(DOCUMENT_KIND_LABEL).map(([value, label]) => ({ value, label }));

/** Download a document through the API (files are never public) under its original name. */
export async function downloadDocument(doc: ResidentDocument) {
  const response = await api<Response>(`/v1/resident-documents/${doc.id}/download/`, { raw: true });
  const url = URL.createObjectURL(await response.blob());
  Object.assign(document.createElement("a"), { href: url, download: doc.file_name }).click();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}

/** The documents the management keeps for one resident at a unit (ownership, tenancy…), with upload. */
export function ResidentDocuments({ residency, title, onClose }: { residency: number; title: string; onClose: () => void }) {
  const toast = useToast();
  const { data, mutate } = useSWR<Page<ResidentDocument>>(`/v1/resident-documents/${query({ residency, page_size: 100 })}`);
  const [removing, setRemoving] = useState<ResidentDocument | null>(null);

  async function download(doc: ResidentDocument) {
    try {
      await downloadDocument(doc);
    } catch (err) {
      toast("error", err instanceof ApiError ? err.message : "Download failed.");
    }
  }

  return (
    <Modal open wide onClose={onClose} title={`Documents · ${title}`} footer={<Button onClick={onClose}>Close</Button>}>
      <div className="space-y-5">
        <Upload residency={residency} onDone={() => mutate()} />
        {!data ? <Loading /> : data.results.length === 0 ? <Empty icon="file" title="No documents yet">Proof of ownership, tenancy agreements and the like, kept with the resident.</Empty> : (
          <ul className="divide-y divide-line rounded-lg border border-line">
            {data.results.map((doc) => (
              <li key={doc.id} className="flex items-center gap-3 px-3 py-2.5">
                <Icon name="file" className="h-5 w-5 shrink-0 text-muted" />
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm font-medium text-ink">{doc.title}</div>
                  <div className="truncate text-xs text-muted">
                    {DOCUMENT_KIND_LABEL[doc.kind]} · {doc.file_name} · {fileSize(doc.size)} · {formatDateTime(doc.created_at)}
                    {doc.uploaded_by_name && ` · ${doc.uploaded_by_name}`}
                  </div>
                </div>
                <IconButton label="Download" onClick={() => download(doc)}><Icon name="download" className="h-4 w-4" /></IconButton>
                <IconButton label="Delete" onClick={() => setRemoving(doc)}><Icon name="trash" className="h-4 w-4" /></IconButton>
              </li>
            ))}
          </ul>
        )}
      </div>
      <ConfirmDialog open={!!removing} title="Delete document?" confirmLabel="Delete" onClose={() => setRemoving(null)}
        message={<>Delete <strong>{removing?.title}</strong>? The file is removed for good and the resident no longer sees it in the app.</>}
        onConfirm={async () => { await remove(`/v1/resident-documents/${removing!.id}/`); mutate(); }} />
    </Modal>
  );
}

function Upload({ residency, onDone }: { residency: number; onDone: () => void }) {
  const toast = useToast();
  const input = useRef<HTMLInputElement>(null);
  const [title, setTitle] = useState("");
  const [kind, setKind] = useState("ownership");
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!file) return setError(new Error("Choose a PDF, JPG or PNG file."));
    setBusy(true);
    setError(null);
    const body = new FormData();
    body.append("residency", String(residency));
    body.append("kind", kind);
    body.append("title", title.trim() || DOCUMENT_KIND_LABEL[kind]);
    body.append("file", file);
    try {
      await api("/v1/resident-documents/", { method: "POST", body });
      toast("success", "Document uploaded.");
      setTitle("");
      setFile(null);
      if (input.current) input.current.value = "";
      onDone();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="space-y-3 rounded-lg border border-dashed border-line p-4">
      <ErrorNote error={error} />
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Type">
          <Select value={kind} onChange={(e) => setKind(e.target.value)}>
            {KIND_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
          </Select>
        </Field>
        <Field label="Title" hint="Optional; the type is used when blank.">
          <Input value={title} maxLength={150} onChange={(e) => setTitle(e.target.value)} placeholder="e.g. Sale & purchase agreement" />
        </Field>
      </div>
      <Field label="File" hint="PDF, JPG or PNG, up to 8 MB.">
        <Input ref={input} type="file" accept="application/pdf,image/jpeg,image/png" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
      </Field>
      <div className="flex justify-end">
        <Button variant="primary" type="submit" busy={busy}><Icon name="plus" className="h-4 w-4" /> Upload</Button>
      </div>
    </form>
  );
}
