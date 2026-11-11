"use client";

import useSWR from "swr";

import { Icon } from "./icons";
import { Badge, Card } from "./ui";
import { useSession } from "@/lib/session";
import type { ModuleCatalogue, ModuleInfo } from "@/lib/types";

/** The module catalogue (names, descriptions, the plan that includes each), cached for the session. */
export function useModuleCatalogue() {
  const { data } = useSWR<ModuleCatalogue>("/v1/modules/", { revalidateOnFocus: false, dedupingInterval: 600_000 });
  return data;
}

/** Whether the selected site's plan includes ``module``. */
export function useModule(module: string): boolean {
  const { condo } = useSession();
  return condo.modules?.includes(module) ?? false;
}

export function upsellText(info?: ModuleInfo) {
  if (!info) return "Not in your plan";
  if (!info.available) return "Coming soon";
  return info.upsell_plan ? `Available in ${info.upsell_plan}` : "Available as an add-on";
}

/** A feature the site's plan does not include: what it does, which plan has it, and who to ask. */
export function LockedFeature({ module }: { module: string }) {
  const info = useModuleCatalogue()?.modules.find((m) => m.key === module);
  return (
    <Card>
      <div className="flex flex-col items-center px-6 py-14 text-center">
        <span className="flex h-14 w-14 items-center justify-center rounded-2xl bg-primary-500/10 text-primary-500">
          <Icon name="lock" className="h-7 w-7" />
        </span>
        <h2 className="mt-5 text-lg font-semibold text-ink">{info?.name ?? "This feature"} is not in your plan</h2>
        {info?.description && <p className="mt-2 max-w-md text-sm text-body">{info.description}</p>}
        <div className="mt-4"><Badge tone="blue">{upsellText(info)}</Badge></div>
        <p className="mt-4 text-sm text-muted">Contact Elix to add it to this site.</p>
      </div>
    </Card>
  );
}

/** Renders ``children`` when the site has ``module``, otherwise the locked card. */
export function ModuleGate({ module, children }: { module: string; children: React.ReactNode }) {
  return useModule(module) ? <>{children}</> : <LockedFeature module={module} />;
}

/** A feature on the roadmap: what it will do, so sites know it is coming and can ask to be first. */
export function ComingSoon({ module, points }: { module: string; points?: string[] }) {
  const info = useModuleCatalogue()?.modules.find((m) => m.key === module);
  return (
    <Card>
      <div className="flex flex-col items-center px-6 py-14 text-center">
        <span className="flex h-14 w-14 items-center justify-center rounded-2xl bg-primary-500/10 text-primary-500">
          <Icon name="sparkle" className="h-7 w-7" />
        </span>
        <h2 className="mt-5 text-lg font-semibold text-ink">{info?.name ?? "This feature"}</h2>
        <div className="mt-2"><Badge tone="blue">Coming soon</Badge></div>
        {info?.description && <p className="mt-4 max-w-md text-sm text-body">{info.description}</p>}
        {points && (
          <ul className="mt-4 max-w-md space-y-1.5 text-left text-sm text-body">
            {points.map((p) => (
              <li key={p} className="flex gap-2"><Icon name="check" className="mt-0.5 h-4 w-4 shrink-0 text-primary-500" />{p}</li>
            ))}
          </ul>
        )}
        <p className="mt-5 text-sm text-muted">Contact Elix to be among the first sites to use it.</p>
      </div>
    </Card>
  );
}
