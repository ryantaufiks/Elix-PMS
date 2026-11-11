"use client";

import { useEffect, useRef, useState } from "react";

import { useSession } from "@/lib/session";
import { Icon } from "./icons";
import { STATUS } from "./PlanSummary";
import { cx } from "./ui";

/** The site switcher at the top of the sidebar: a navy list in the sidebar's own style, with search when there are many sites. */
export function SitePicker() {
  const { condos, condo, me, selectCondo } = useSession();
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => box.current && !box.current.contains(e.target as Node) && setOpen(false);
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => { document.removeEventListener("mousedown", onDown); document.removeEventListener("keydown", onKey); };
  }, [open]);

  if (condos.length < 2) return <div className="truncate px-3 py-2 text-sm font-medium text-white">{condo.name}</div>;

  const term = search.trim().toLowerCase();
  const shown = condos.filter((c) => !term || c.name.toLowerCase().includes(term) || c.code.includes(term));

  return (
    <div ref={box} className="relative">
      <button onClick={() => { setOpen(!open); setSearch(""); }} aria-haspopup="listbox" aria-expanded={open} aria-label={`Site: ${condo.name}. Change site`}
        className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-sm font-medium text-white transition hover:bg-white/5">
        <Icon name="building" className="h-4 w-4 shrink-0 text-slate-400" />
        <span className="min-w-0 flex-1 truncate">{condo.name}</span>
        <Icon name="chevron" className={cx("h-4 w-4 shrink-0 text-slate-400 transition-transform", open ? "-rotate-90" : "rotate-90")} />
      </button>
      {open && (
        <div className="absolute inset-x-0 top-full z-40 mt-2 overflow-hidden rounded-xl border border-white/10 bg-[#0b1631] shadow-2xl shadow-black/40">
          {condos.length > 6 && (
            <div className="border-b border-white/10 p-2">
              <input autoFocus value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search sites…" aria-label="Search sites"
                className="w-full rounded-md border border-white/10 bg-white/5 px-3 py-2 text-sm text-white placeholder:text-slate-500 focus:border-primary-400 focus:outline-none" />
            </div>
          )}
          <ul role="listbox" aria-label="Sites" className="max-h-80 overflow-y-auto py-1">
            {shown.map((c) => {
              const current = c.id === condo.id;
              const status = c.subscription_status ? STATUS[c.subscription_status] : null;
              return (
                <li key={c.id} role="option" aria-selected={current}>
                  <button onClick={() => { setOpen(false); if (!current) selectCondo(c.id); }}
                    className={cx("flex w-full items-center gap-3 px-3 py-2.5 text-left text-sm transition",
                      current ? "bg-primary-500/15 text-white" : "text-slate-300 hover:bg-white/5 hover:text-white")}>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate font-medium">{c.name}</span>
                      {me.is_superuser && (c.plan_name || status) && (
                        <span className="block truncate text-xs text-slate-500">{[c.plan_name, status?.label].filter(Boolean).join(" · ")}</span>
                      )}
                    </span>
                    {current && <Icon name="check" className="h-4 w-4 shrink-0 text-primary-300" />}
                  </button>
                </li>
              );
            })}
            {shown.length === 0 && <li className="px-3 py-3 text-sm text-slate-500">No site matches.</li>}
          </ul>
        </div>
      )}
    </div>
  );
}
