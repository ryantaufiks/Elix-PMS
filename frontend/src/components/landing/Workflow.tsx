"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useMemo, useState } from "react";

import { cx } from "@/components/ui";

const WorkflowScene = dynamic(() => import("./WorkflowScene"), { ssr: false });

type Step = { label: string; title: string; text: string };

const FLOWS: Record<string, { name: string; steps: Step[] }> = {
  call: {
    name: "Visitor calls a resident",
    steps: [
      { label: "Kiosk", title: "Visitor taps the lobby kiosk", text: "They pick the unit on a big number pad, enter their name and purpose, and the kiosk takes a photo after they accept the privacy notice." },
      { label: "Phone rings", title: "The resident's phone rings", text: "A full-screen call reaches the resident app even when it is closed, with the visitor's photo and purpose." },
      { label: "Video call", title: "Face-to-face video", text: "Resident and visitor see and hear each other. The guardhouse sees the call pop up on any dashboard page and can pick it up." },
      { label: "Swipe", title: "Swipe to open", text: "One swipe approves the visitor. Declining or not answering keeps the gate shut." },
      { label: "Gate opens", title: "The gate opens", text: "The relay on the gate motor opens the gate at the kiosk the visitor is standing at." },
      { label: "Logged", title: "Everything is logged", text: "Time, unit, visitor, photo and decision land in the access log and the reports, live on the dashboard." },
    ],
  },
  qr: {
    name: "Invited guest",
    steps: [
      { label: "Invite", title: "Resident sends an invitation", text: "From the app: visitor name, validity, number of entries and an optional vehicle plate." },
      { label: "QR pass", title: "Guest receives a QR pass", text: "A link to a personal pass page with the QR code, the address and the rules. No app needed." },
      { label: "Scan", title: "Scan at the kiosk", text: "The kiosk camera reads the QR. Sites can also ask for a quick face check on arrival." },
      { label: "Check", title: "Validity checked", text: "Date, time window, gate and remaining entries are checked in an instant." },
      { label: "Gate opens", title: "The gate opens", text: "The guest walks or drives in; with a plate on the invitation the barrier opens by itself." },
      { label: "Logged", title: "Logged and counted", text: "The entry counts against the invitation and shows up for the resident and the guardhouse." },
    ],
  },
  facility: {
    name: "Facility booking",
    steps: [
      { label: "Book", title: "Resident books in the app", text: "A slot at the BBQ pit or function room, within the estate's rules, paid with PayNow or card when it has a fee." },
      { label: "QR", title: "A check-in QR", text: "The booking carries its own QR in My bookings, valid from 15 minutes before the start." },
      { label: "Kiosk", title: "Check in at the kiosk", text: "Facilities on the kiosk shows today's free and booked slots, never who booked them, and scans the QR." },
      { label: "Door opens", title: "The door opens", text: "When the facility has a door on a relay, it opens for the resident with the booking." },
      { label: "No-show", title: "No-shows flagged", text: "Nobody checked in after the set minutes: the booking is marked no-show and can free the slot for others." },
    ],
  },
  lpr: {
    name: "Car at the barrier",
    steps: [
      { label: "Camera", title: "The camera reads the plate", text: "The licence-plate camera at the barrier sends each read to Elix." },
      { label: "Match", title: "Matched in milliseconds", text: "Against registered vehicles and season parking within their dates, and today's invitations with a plate. Unknown or lapsed plates are logged and the barrier stays shut." },
      { label: "Barrier", title: "The barrier opens", text: "Residents and invited cars drive straight in, no remote or card needed." },
      { label: "Logged", title: "Logged with a snapshot", text: "Plate, gate, decision and the camera snapshot, searchable in the access log and vehicle report." },
    ],
  },
};

/** "How it works": pick a journey, step through it in 3D (or in the list when WebGL is not available). */
export function Workflow() {
  const [flow, setFlow] = useState<keyof typeof FLOWS>("call");
  const [step, setStep] = useState(0);
  const [playing, setPlaying] = useState(true);
  const [webgl, setWebgl] = useState(true);
  const steps = FLOWS[flow].steps;
  const labels = useMemo(() => steps.map((s) => s.label), [steps]);
  const unsupported = useCallback(() => setWebgl(false), []);
  const pick = useCallback((i: number) => { setStep(i); setPlaying(false); }, []);

  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) setPlaying(false);
  }, []);
  useEffect(() => {
    if (!playing) return;
    const id = setInterval(() => setStep((s) => (s + 1) % steps.length), 2600);
    return () => clearInterval(id);
  }, [playing, steps.length]);

  return (
    <div>
      <div className="flex flex-wrap justify-center gap-2" role="tablist" aria-label="Journey">
        {Object.entries(FLOWS).map(([key, f]) => (
          <button key={key} role="tab" aria-selected={flow === key} onClick={() => { setFlow(key); setStep(0); setPlaying(true); }}
            className={cx("rounded-full border px-4 py-2 text-sm font-medium transition",
              flow === key ? "border-primary-400 bg-primary-500/25 text-white" : "border-white/15 bg-white/5 text-slate-300 hover:bg-white/10")}>
            {f.name}
          </button>
        ))}
      </div>
      <div className={cx("mt-8 grid items-stretch gap-6", webgl && "lg:grid-cols-[1.5fr_1fr]")}>
        {webgl && (
          <div className="relative h-72 overflow-hidden rounded-3xl border border-white/10 bg-navy-950/40 sm:h-96 lg:h-auto lg:min-h-[28rem]">
            <WorkflowScene key={flow} labels={labels} step={step} onPick={pick} onUnsupported={unsupported} />
            <div className="pointer-events-none absolute bottom-3 left-4 text-xs text-slate-400">Drag to turn · tap a step</div>
            <button type="button" onClick={() => setPlaying((p) => !p)}
              className="absolute bottom-3 right-3 rounded-full border border-white/15 bg-navy-950/70 px-3 py-1.5 text-xs font-medium text-slate-200 hover:bg-white/10">
              {playing ? "❚❚ Pause" : "▶ Play"}
            </button>
          </div>
        )}
        <ol className="space-y-2">
          {steps.map((s, i) => (
            <li key={s.label}>
              <button type="button" onClick={() => pick(i)} aria-current={i === step ? "step" : undefined}
                className={cx("flex w-full gap-4 rounded-2xl border p-4 text-left transition",
                  i === step ? "border-primary-400/60 bg-primary-500/15" : "border-white/10 bg-white/[0.03] hover:bg-white/[0.06]")}>
                <span className={cx("flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-sm font-semibold",
                  i === step ? "bg-primary-500 text-white" : i < step ? "bg-primary-500/30 text-primary-100" : "bg-white/10 text-slate-300")}>{i + 1}</span>
                <span className="min-w-0">
                  <span className="block font-semibold text-white">{s.title}</span>
                  {i === step && <span className="mt-1 block text-sm leading-relaxed text-slate-300">{s.text}</span>}
                </span>
              </button>
            </li>
          ))}
        </ol>
      </div>
    </div>
  );
}
