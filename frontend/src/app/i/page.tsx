"use client";

// Public visitor pass behind an invitation's share link (/i/<token>): the QR to show at the kiosk.
import { useEffect, useState } from "react";

import type { VisitorPass } from "@/lib/kiosk";
import { Credit } from "@/components/Credit";

const when = new Intl.DateTimeFormat("en-SG", {
  weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", hour12: false, timeZone: "Asia/Singapore",
});
const PURPOSE: Record<string, string> = { guest: "Guest", delivery: "Delivery", contractor: "Contractor", pickup: "Pick-up / drop-off", other: "Visit" };

export default function VisitorPassPage() {
  const [token, setToken] = useState<string | null>(null);
  const [pass, setPass] = useState<VisitorPass | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    document.documentElement.dataset.theme = "light";
    const t = window.location.pathname.split("/i/")[1]?.replace(/\/+$/, "") ?? "";
    setToken(t);
    if (!t) return setError("This link is incomplete.");
    fetch(`/v1/public/invitations/${encodeURIComponent(t)}/`)
      .then(async (r) => (r.ok ? setPass(await r.json()) : setError(r.status === 404 ? "This invitation does not exist." : "Could not load the invitation. Try again in a moment.")))
      .catch(() => setError("Could not load the invitation. Check your connection."));
  }, []);

  return (
    <div className="min-h-dvh bg-canvas">
      <div className="brand-panel px-6 pb-28 pt-8 text-white">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src="/brand/elix-logo.png" alt="Elix" className="mx-auto h-8 w-auto drop-shadow-[0_0_14px_rgba(47,111,255,0.5)]" />
        <p className="mt-6 text-center text-sm uppercase tracking-widest text-slate-300">Visitor pass</p>
      </div>
      <main className="mx-auto -mt-20 max-w-md px-4 pb-10">
        <div className="overflow-hidden rounded-2xl border border-line bg-surface shadow-card">
          {error ? (
            <p className="p-8 text-center text-body">{error}</p>
          ) : !pass ? (
            <div className="flex justify-center p-12"><span className="h-6 w-6 animate-spin rounded-full border-2 border-line border-t-primary-500" /></div>
          ) : (
            <>
              <div className="px-6 pt-6 text-center">
                <div className="text-sm text-muted">{PURPOSE[pass.purpose] ?? "Visit"} at</div>
                <h1 className="mt-1 text-xl font-semibold text-ink">{pass.condominium_name}</h1>
                {pass.condominium_address && <p className="mt-1 text-sm text-muted">{pass.condominium_address}</p>}
              </div>
              <div className="mx-6 my-5 flex justify-center rounded-xl border border-line bg-white p-4">
                {pass.usable ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={`/v1/public/invitations/${encodeURIComponent(token ?? "")}/qr/`} alt="Invitation QR code" className="h-60 w-60" />
                ) : (
                  <div className="flex h-60 w-60 flex-col items-center justify-center text-center">
                    <span className="rounded-full bg-rose-500/10 px-3 py-1 text-sm font-medium text-rose-700">Not valid</span>
                    <p className="mt-3 text-sm text-body">{pass.problem}</p>
                  </div>
                )}
              </div>
              <dl className="divide-y divide-line border-t border-line text-sm">
                {[
                  ["Visitor", pass.visitor_name],
                  ["Visiting", `${pass.unit_display}${pass.host_first_name ? ` · ${pass.host_first_name}` : ""}`],
                  ["Valid from", when.format(new Date(pass.valid_from))],
                  ["Valid until", when.format(new Date(pass.valid_until))],
                  ...(pass.vehicle_plate ? [["Vehicle", pass.vehicle_plate]] : []),
                  ...(pass.entries_left !== null ? [["Entries left", String(pass.entries_left)]] : []),
                ].map(([k, v]) => (
                  <div key={k} className="flex justify-between gap-4 px-6 py-3"><dt className="text-muted">{k}</dt><dd className="text-right font-medium text-ink">{v}</dd></div>
                ))}
              </dl>
              <div className="bg-surface-2 px-6 py-4 text-sm text-body">
                At the gate, tap <strong>“I have an invitation”</strong> on the kiosk and hold this QR code up to its camera.
                {pass.require_face && " The kiosk will also take a quick photo of you."}
                {pass.vehicle_plate && " Driving? The barrier opens automatically for your registered plate."}
              </div>
            </>
          )}
        </div>
        {pass?.privacy_notice && (
          <details className="mt-4 rounded-xl border border-line bg-surface px-4 py-3 text-sm text-body">
            <summary className="cursor-pointer font-medium text-ink">How your data is used</summary>
            <p className="mt-2 leading-relaxed">{pass.privacy_notice}</p>
          </details>
        )}
        <p className="mt-6 text-center text-xs text-muted">Keep this link private: anyone with it can use your invitation.</p>
        <Credit className="mt-8" />
      </main>
    </div>
  );
}
