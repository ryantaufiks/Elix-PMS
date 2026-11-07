"use client";

import useSWR from "swr";

import { useGates } from "@/components/bits";
import { Badge, Card, CardHeader, Empty, Loading, PageHeader, Table, Td, Th } from "@/components/ui";
import { query } from "@/lib/api";
import { timeAgo } from "@/lib/format";
import { useSession } from "@/lib/session";
import type { Camera, Kiosk, Page, Relay } from "@/lib/types";

const MODE_LABEL = { cloud: "Cloud", local: "Local LAN", local_then_cloud: "LAN → cloud" };
const online = (iso: string | null, minutes: number) => !!iso && Date.now() - new Date(iso).getTime() < minutes * 60_000;

export default function DevicesPage() {
  const { condo, isAdmin, me } = useSession();
  const gates = useGates(condo.id);
  const relays = useSWR<Page<Relay>>(isAdmin ? `/v1/relays/${query({ gate__condominium: condo.id, page_size: 200 })}` : null, { refreshInterval: 30_000 });
  const cameras = useSWR<Page<Camera>>(isAdmin ? `/v1/cameras/${query({ gate__condominium: condo.id, page_size: 200 })}` : null, { refreshInterval: 30_000 });
  const kiosks = useSWR<Page<Kiosk>>(isAdmin ? `/v1/kiosks/${query({ condominium: condo.id, page_size: 200 })}` : null, { refreshInterval: 30_000 });
  const gateName = (id: number | null) => gates.data?.results.find((g) => g.id === id)?.name ?? "—";

  if (!isAdmin) return <Card><Empty>Device status is available to condo admins.</Empty></Card>;

  return (
    <>
      <PageHeader title="Devices" description={`Health of relays, cameras and kiosks.${me.is_superuser ? " Configure them in Django admin." : ""}`} />
      <div className="space-y-6">
        <Card>
          <CardHeader title="Gate relays" />
          {!relays.data ? <Loading /> : relays.data.results.length === 0 ? <Empty>No relays.</Empty> : (
            <Table>
              <thead><tr><Th>Name</Th><Th>Gate</Th><Th>Provider</Th><Th>Mode</Th><Th>Last triggered</Th><Th>Status</Th></tr></thead>
              <tbody className="divide-y divide-slate-100">
                {relays.data.results.map((r) => (
                  <tr key={r.id}>
                    <Td className="font-medium text-slate-800">{r.name}</Td>
                    <Td>{gateName(r.gate)}</Td>
                    <Td>{r.provider === "shelly" ? "Shelly" : "eWeLink"}</Td>
                    <Td>{MODE_LABEL[r.control_mode]}</Td>
                    <Td>{timeAgo(r.last_triggered_at)}</Td>
                    <Td>
                      {!r.is_active ? <Badge>Disabled</Badge> : r.last_error ? (
                        <span title={r.last_error}><Badge tone="red">Error</Badge><div className="mt-1 max-w-xs text-xs text-rose-700">{r.last_error}</div></span>
                      ) : <Badge tone="green">OK</Badge>}
                    </Td>
                  </tr>
                ))}
              </tbody>
            </Table>
          )}
        </Card>
        <Card>
          <CardHeader title="LPR cameras" />
          {!cameras.data ? <Loading /> : cameras.data.results.length === 0 ? <Empty>No cameras.</Empty> : (
            <Table>
              <thead><tr><Th>Name</Th><Th>Gate</Th><Th>Device ID</Th><Th>Direction</Th><Th>Last event</Th><Th>Status</Th></tr></thead>
              <tbody className="divide-y divide-slate-100">
                {cameras.data.results.map((c) => (
                  <tr key={c.id}>
                    <Td className="font-medium text-slate-800">{c.name}</Td>
                    <Td>{gateName(c.gate)}</Td>
                    <Td className="font-mono text-xs">{c.device_id}</Td>
                    <Td className="capitalize">{c.direction}</Td>
                    <Td>{timeAgo(c.last_seen_at)}</Td>
                    <Td>{!c.is_active ? <Badge>Disabled</Badge> : online(c.last_seen_at, 24 * 60) ? <Badge tone="green">Seen today</Badge> : <Badge tone="amber">No events 24 h</Badge>}</Td>
                  </tr>
                ))}
              </tbody>
            </Table>
          )}
        </Card>
        <Card>
          <CardHeader title="Kiosks" />
          {!kiosks.data ? <Loading /> : kiosks.data.results.length === 0 ? <Empty>No kiosks.</Empty> : (
            <Table>
              <thead><tr><Th>Name</Th><Th>Gate</Th><Th>App version</Th><Th>Last seen</Th><Th>Status</Th></tr></thead>
              <tbody className="divide-y divide-slate-100">
                {kiosks.data.results.map((k) => (
                  <tr key={k.id}>
                    <Td className="font-medium text-slate-800">{k.name}</Td>
                    <Td>{gateName(k.gate)}</Td>
                    <Td>{k.app_version || "—"}</Td>
                    <Td>{timeAgo(k.last_seen_at)}</Td>
                    <Td>{!k.is_active ? <Badge>Disabled</Badge> : online(k.last_seen_at, 5) ? <Badge tone="green">Online</Badge> : <Badge tone="red">Offline</Badge>}</Td>
                  </tr>
                ))}
              </tbody>
            </Table>
          )}
        </Card>
      </div>
    </>
  );
}
