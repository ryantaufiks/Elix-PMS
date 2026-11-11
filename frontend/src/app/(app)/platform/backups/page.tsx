"use client";

import { useState } from "react";
import useSWR from "swr";

import { ConfirmDialog, remove } from "@/components/forms";
import { Icon } from "@/components/icons";
import { Badge, Button, Card, CardHeader, Empty, IconButton, Loading, PageHeader, Select, Table, Td, Th, useToast } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { fileSize, formatDateTime } from "@/lib/format";
import { useSession } from "@/lib/session";
import type { Backup, Condominium, Page } from "@/lib/types";

const STATUS: Record<Backup["status"], { label: string; tone: "slate" | "blue" | "green" | "red" }> = {
  pending: { label: "Waiting", tone: "slate" },
  running: { label: "Running", tone: "blue" },
  ready: { label: "Ready", tone: "green" },
  failed: { label: "Failed", tone: "red" },
};

const when = (iso: string) => formatDateTime(iso);

export default function BackupsPage() {
  const { me, condo } = useSession();
  const toast = useToast();
  const [site, setSite] = useState<number>(condo.id);
  const [busy, setBusy] = useState("");
  const [removing, setRemoving] = useState<Backup | null>(null);
  // Refresh every few seconds while a backup is being made, so it turns Ready on its own.
  const { data, mutate } = useSWR<Page<Backup>>(me.is_superuser ? "/v1/backups/?page_size=100" : null, {
    refreshInterval: (latest) => (latest?.results.some((b) => b.status === "pending" || b.status === "running") ? 3000 : 0),
  });
  const { data: condos } = useSWR<Page<Condominium>>(me.is_superuser ? "/v1/condominiums/?page_size=200" : null);

  if (!me.is_superuser) return <Card><Empty>Only the platform administrator manages backups.</Empty></Card>;

  async function start(body: { kind: Backup["kind"]; condominium?: number }) {
    setBusy(body.kind);
    try {
      await api("/v1/backups/", { method: "POST", body });
      toast("success", body.kind === "platform" ? "Backup started." : "Export started.");
      mutate();
    } catch (err) {
      toast("error", err instanceof ApiError ? err.message : "Could not start.");
    } finally {
      setBusy("");
    }
  }

  async function download(backup: Backup) {
    try {
      const response = await api<Response>(`/v1/backups/${backup.id}/download/`, { raw: true });
      const url = URL.createObjectURL(await response.blob());
      Object.assign(document.createElement("a"), { href: url, download: backup.file_name }).click();
      setTimeout(() => URL.revokeObjectURL(url), 2000);
      mutate();
    } catch (err) {
      toast("error", err instanceof ApiError ? err.message : "Download failed.");
    }
  }

  const rows = (kind: Backup["kind"]) => data?.results.filter((b) => b.kind === kind) ?? [];

  const table = (kind: Backup["kind"]) => {
    const list = rows(kind);
    if (!data) return <Loading />;
    if (list.length === 0) return <Empty>{kind === "platform" ? "No backups yet. One is made every night at 02:45." : "No exports yet."}</Empty>;
    return (
      <Table>
        <thead><tr>{kind === "site" && <Th>Site</Th>}<Th>Made</Th><Th>Status</Th><Th>Size</Th><Th>By</Th><Th>Kept until</Th><Th>Downloads</Th><Th /></tr></thead>
        <tbody className="divide-y divide-line">
          {list.map((b) => (
            <tr key={b.id}>
              {kind === "site" && <Td className="font-medium text-ink">{b.condominium_name}</Td>}
              <Td className="whitespace-nowrap">{when(b.created_at)}</Td>
              <Td>
                <Badge tone={STATUS[b.status].tone}>{STATUS[b.status].label}</Badge>
                {b.error && <div className="mt-1 max-w-xs truncate text-xs text-rose-600" title={b.error}>{b.error}</div>}
              </Td>
              <Td className="whitespace-nowrap">{b.status === "ready" ? fileSize(b.size) : "—"}</Td>
              <Td>{b.automatic ? <span className="text-muted">Automatic</span> : b.created_by_name || "—"}</Td>
              <Td className="whitespace-nowrap text-xs">{when(b.expires_at)}</Td>
              <Td className="text-xs">
                {b.downloads.length === 0 ? <span className="text-muted">None</span> : (
                  <span title={b.downloads.map((d) => `${d.user_name} · ${when(d.at)}${d.ip ? ` · ${d.ip}` : ""}`).join("\n")}>
                    {b.downloads.length}× · last {b.downloads[0].user_name}, {when(b.downloads[0].at)}
                  </span>
                )}
              </Td>
              <Td className="whitespace-nowrap text-right">
                <IconButton label="Download" disabled={b.status !== "ready"} onClick={() => download(b)}><Icon name="download" className="h-4 w-4" /></IconButton>
                <IconButton label="Delete" disabled={b.status === "pending" || b.status === "running"} onClick={() => setRemoving(b)}><Icon name="trash" className="h-4 w-4" /></IconButton>
              </Td>
            </tr>
          ))}
        </tbody>
      </Table>
    );
  };

  return (
    <>
      <PageHeader title="Backups" description="Platform backups for disaster recovery, and per-site data exports. Archives hold every resident's personal data: every download is recorded." />
      <div className="space-y-6">
        <Card>
          <CardHeader
            title={<><span className="block">Platform backup</span><span className="block text-sm font-normal text-muted">The whole database and every uploaded file. Made nightly, kept 14 days. Restore on the server (see the README).</span></>}
            action={<Button variant="primary" busy={busy === "platform"} onClick={() => start({ kind: "platform" })}><Icon name="archive" className="h-4 w-4" /> Backup now</Button>}
          />
          {table("platform")}
        </Card>
        <Card>
          <CardHeader
            title={<><span className="block">Site export</span><span className="block text-sm font-normal text-muted">One site&apos;s records (JSON and CSV) with its documents and photos, for handover, audit or a PDPA request. Kept 7 days. Not for restoring.</span></>}
            action={
              <div className="flex gap-2">
                <Select value={site} onChange={(e) => setSite(Number(e.target.value))} aria-label="Site" className="sm:w-56">
                  {condos?.results.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
                </Select>
                <Button variant="primary" busy={busy === "site"} onClick={() => start({ kind: "site", condominium: site })}><Icon name="download" className="h-4 w-4" /> Export</Button>
              </div>
            }
          />
          {table("site")}
        </Card>
      </div>
      <ConfirmDialog open={!!removing} title="Delete this archive?" confirmLabel="Delete" onClose={() => setRemoving(null)}
        message={<>The archive from <strong>{removing && when(removing.created_at)}</strong> is deleted for good.</>}
        onConfirm={async () => { await remove(`/v1/backups/${removing!.id}/`); mutate(); }} />
    </>
  );
}
