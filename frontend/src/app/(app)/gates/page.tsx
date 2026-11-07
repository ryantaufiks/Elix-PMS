"use client";

import { useState } from "react";

import { OpenGateDialog, useGates } from "@/components/bits";
import { Icon } from "@/components/icons";
import { Badge, Button, Card, Empty, Loading, PageHeader } from "@/components/ui";
import { useSession } from "@/lib/session";
import type { Gate } from "@/lib/types";

const TYPE_LABEL = { vehicle: "Vehicle barrier", pedestrian: "Pedestrian gate", door: "Door" };
const DIRECTION_LABEL = { entry: "Entry", exit: "Exit", both: "Entry & exit" };

export default function GatesPage() {
  const { condo, me } = useSession();
  const { data } = useGates(condo.id);
  const [opening, setOpening] = useState<Gate | null>(null);

  return (
    <>
      <PageHeader title="Gates" description="Open a gate manually. Every opening is logged under your name." />
      {!data ? (
        <Loading />
      ) : data.results.length === 0 ? (
        <Card><Empty>No gates configured for this site{me.is_superuser && " — add them in Django admin"}.</Empty></Card>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {data.results.map((gate) => (
            <Card key={gate.id} className="flex flex-col p-5">
              <div className="flex items-start justify-between gap-3">
                <h2 className="text-base font-semibold text-ink">{gate.name}</h2>
                {gate.is_active ? <Badge tone="green">Active</Badge> : <Badge>Disabled</Badge>}
              </div>
              <dl className="mt-3 space-y-1 text-sm text-body">
                <div>{TYPE_LABEL[gate.gate_type]} · {DIRECTION_LABEL[gate.direction]}</div>
                <div>
                  Plate auto-open: {[gate.lpr_auto_open_residents && "residents", gate.lpr_auto_open_invited && "invited visitors"].filter(Boolean).join(", ") || "off"}
                </div>
              </dl>
              <Button variant="primary" size="lg" className="mt-5 w-full" disabled={!gate.is_active} onClick={() => setOpening(gate)}>
                <Icon name="unlock" /> Open gate
              </Button>
            </Card>
          ))}
        </div>
      )}
      <OpenGateDialog gate={opening} onClose={() => setOpening(null)} />
    </>
  );
}
