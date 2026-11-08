"use client";

// The 58 mm visitor slip, printed by the kiosk and from the guardhouse dashboard.
import { useEffect, useState } from "react";
import { createPortal } from "react-dom";

import type { WalkInSlip } from "@/lib/kiosk";

const clock = (iso: string) =>
  new Intl.DateTimeFormat("en-SG", { hour: "2-digit", minute: "2-digit", hour12: false, timeZone: "Asia/Singapore" }).format(new Date(iso));

const fullDate = (iso: string) =>
  new Intl.DateTimeFormat("en-SG", { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit", hour12: false, timeZone: "Asia/Singapore" }).format(new Date(iso));

/** The 58 mm receipt: only this is printed (the rest of the page is hidden for print). */
export function PrintSlip({ slip, onReady }: { slip: WalkInSlip; onReady: () => void }) {
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);
  if (!mounted) return null;
  const row = { display: "flex", justifyContent: "space-between", gap: "2mm" } as const;
  return createPortal(
    <div className="walkin-slip">
      <style>{`
        .walkin-slip { display: none; }
        @media print {
          @page { margin: 0; }
          html, body { background: #fff !important; min-height: 0 !important; }
          body > *:not(.walkin-slip) { display: none !important; }
          .walkin-slip { display: block; width: 48mm; margin: 0 auto; padding: 3mm 0 6mm; color: #000; background: #fff;
            font: 9pt/1.35 ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, Arial, sans-serif; }
          .walkin-slip * { color: #000 !important; }
        }
      `}</style>
      <div style={{ textAlign: "center", fontWeight: 700, fontSize: "10pt" }}>{slip.condominium_name}</div>
      <div style={{ textAlign: "center", fontSize: "7.5pt", letterSpacing: "0.12em", marginTop: "1mm" }}>VISITOR PASS</div>
      <div style={{ borderTop: "1px dashed #000", margin: "2.5mm 0" }} />
      <div style={{ textAlign: "center", fontFamily: "ui-monospace, Menlo, Consolas, monospace", fontWeight: 800, fontSize: "26pt", lineHeight: 1.1 }}>{slip.pass_number}</div>
      <div style={{ textAlign: "center", fontWeight: 600, marginTop: "1mm" }}>{slip.purpose_display}</div>
      <div style={{ borderTop: "1px dashed #000", margin: "2.5mm 0" }} />
      <div style={row}><span>Name</span><b style={{ textAlign: "right" }}>{slip.visitor_name}</b></div>
      {slip.company && <div style={row}><span>Company</span><b style={{ textAlign: "right" }}>{slip.company}</b></div>}
      {slip.vehicle_plate && <div style={row}><span>Vehicle</span><b style={{ textAlign: "right" }}>{slip.vehicle_plate}</b></div>}
      <div style={row}><span>Visiting</span><b style={{ textAlign: "right" }}>{slip.unit_display}</b></div>
      <div style={row}><span>Time in</span><b style={{ textAlign: "right" }}>{fullDate(slip.created_at)}</b></div>
      <div style={row}><span>Valid until</span><b style={{ textAlign: "right" }}>Today {clock(slip.valid_until)}</b></div>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={slip.qr} alt="" onLoad={onReady} style={{ display: "block", width: "34mm", height: "34mm", margin: "3mm auto 1mm" }} />
      <div style={{ textAlign: "center", fontSize: "8pt" }}>Show this slip to security.<br />Scan the QR at the kiosk when you leave.</div>
      <div style={{ borderTop: "1px dashed #000", margin: "2.5mm 0" }} />
      <div style={{ textAlign: "center", fontSize: "6.5pt", lineHeight: 1.4 }}>Supported by Smart City Technologies Pte Ltd<br />© 2026 Elix PMS</div>
    </div>,
    document.body,
  );
}
