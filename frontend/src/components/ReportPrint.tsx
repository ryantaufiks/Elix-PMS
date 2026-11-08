"use client";

// The A4 print layout of a report (Print / Save as PDF): letterhead, period and filters, key figures,
// daily trend, breakdowns, every detail row and a sign-off block. Only this is printed.
import { useEffect, useState } from "react";
import { createPortal } from "react-dom";

import { SUPPORTED_BY } from "./Credit";
import { badgeTone, dayLabel, formatCell, formatKpi, type ReportData } from "@/lib/reports";

const INK = "#0b1b3f";
const MUTED = "#5b6478";
const LINE = "#d5dbe7";
const SERIES = ["#2a78d6", "#eb6834", "#8e99ad"];
const TONE: Record<string, string> = { green: "#047857", red: "#be123c", amber: "#b45309", blue: "#1d4ed8", slate: "#475569" };

function Trend({ data }: { data: ReportData }) {
  const { points, series } = data.summary.trend;
  const W = 640, H = 150, left = 30, bottom = 18, top = 8;
  const total = (p: Record<string, number | string>) => series.reduce((s, x) => s + Number(p[x.key] || 0), 0);
  const max = Math.max(4, ...points.map(total));
  const band = (W - left) / Math.max(1, points.length);
  const barW = Math.max(2, Math.min(22, band * 0.64));
  const y = (v: number) => top + (H - top - bottom) * (1 - v / max);
  const every = Math.max(1, Math.ceil(points.length / 14));
  return (
    <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", height: "auto", display: "block" }}>
      {[0, max / 2, max].map((t) => (
        <g key={t}>
          <line x1={left} x2={W} y1={y(t)} y2={y(t)} stroke={t ? "#e9ecf2" : "#c5ccd8"} strokeWidth={0.8} />
          <text x={left - 5} y={y(t) + 3} textAnchor="end" fontSize={8} fill={MUTED}>{Math.round(t)}</text>
        </g>
      ))}
      {points.map((p, i) => {
        let base = 0;
        const x = left + i * band + (band - barW) / 2;
        return (
          <g key={p.date}>
            {series.map((s, si) => {
              const v = Number(p[s.key] || 0);
              if (!v) return null;
              const rect = <rect key={s.key} x={x} y={y(base + v)} width={barW} height={y(base) - y(base + v)} fill={SERIES[si]} />;
              base += v;
              return rect;
            })}
            {i % every === 0 && <text x={x + barW / 2} y={H - 5} textAnchor="middle" fontSize={8} fill={MUTED}>{dayLabel(p.date)}</text>}
          </g>
        );
      })}
    </svg>
  );
}

/** Renders ``data`` into a print-only portal and calls ``onReady`` once it is in the page. */
export function ReportPrint({ data, onReady }: { data: ReportData; onReady: () => void }) {
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);
  useEffect(() => {
    if (!mounted) return;
    const id = requestAnimationFrame(() => requestAnimationFrame(onReady));
    return () => cancelAnimationFrame(id);
  }, [mounted, onReady]);
  if (!mounted) return null;

  const { summary } = data;
  const breakdowns = summary.breakdowns.filter((b) => b.rows.length);
  const generated = new Intl.DateTimeFormat("en-SG", { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit", hour12: false, timeZone: "Asia/Singapore" }).format(new Date(data.generated_at));
  const numeric = (kind: string) => kind === "number";

  return createPortal(
    <div className="report-print">
      <style>{`
        .report-print { display: none; }
        @media print {
          @page {
            size: A4 ${data.landscape ? "landscape" : "portrait"};
            margin: 12mm 11mm 15mm;
            @bottom-left { content: "Elix PMS · ${data.title} · ${data.period.label} · Confidential: contains personal data (PDPA)"; font: 7pt Arial, sans-serif; color: ${MUTED}; }
            @bottom-right { content: "Page " counter(page) " of " counter(pages); font: 7pt Arial, sans-serif; color: ${MUTED}; }
          }
          html, body { background: #fff !important; min-height: 0 !important; }
          body > *:not(.report-print) { display: none !important; }
          .report-print { display: block; color: ${INK}; font: 8.5pt/1.4 Arial, "Helvetica Neue", Helvetica, sans-serif;
            -webkit-print-color-adjust: exact; print-color-adjust: exact; }
          .report-print table { border-collapse: collapse; width: 100%; }
          .report-print thead { display: table-header-group; }
          .report-print tr { break-inside: avoid; }
          .rp-section { break-inside: avoid; }
          .rp-h { font-size: 9pt; font-weight: 700; text-transform: uppercase; letter-spacing: 0.06em; color: ${INK}; margin: 0 0 2mm; }
          .rp-details th { background: ${INK}; color: #fff; font-weight: 700; text-align: left; padding: 1.6mm 1.8mm; font-size: 7.5pt; }
          .rp-details td { padding: 1.3mm 1.8mm; border-bottom: 0.6pt solid ${LINE}; font-size: 7.5pt; vertical-align: top; }
          .rp-details tbody tr:nth-child(even) td { background: #f4f6fb; }
          .rp-mini td { padding: 1mm 0; border-bottom: 0.5pt solid ${LINE}; font-size: 8pt; }
        }
      `}</style>

      {/* Letterhead */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", borderBottom: `2pt solid ${INK}`, paddingBottom: "3mm" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "3mm" }}>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/brand/elix-icon-64.png" alt="" style={{ width: "11mm", height: "11mm", borderRadius: "2mm" }} />
          <div>
            <div style={{ fontSize: "14pt", fontWeight: 800, letterSpacing: "0.08em" }}>ELIX PMS</div>
            <div style={{ fontSize: "7pt", color: MUTED }}>Property management · Supported by {SUPPORTED_BY}</div>
          </div>
        </div>
        <div style={{ textAlign: "right" }}>
          <div style={{ fontSize: "16pt", fontWeight: 700 }}>{data.title}</div>
          <div style={{ fontSize: "9pt", color: MUTED }}>{data.sites.join(" · ")}</div>
        </div>
      </div>

      {/* Report information */}
      <table style={{ margin: "3mm 0 4mm", fontSize: "8pt" }}>
        <tbody>
          <tr>
            <td style={{ width: "25%" }}><span style={{ color: MUTED }}>Period</span><br /><b>{data.period.label}</b></td>
            <td style={{ width: "25%" }}><span style={{ color: MUTED }}>Site{data.sites.length > 1 ? `s (${data.sites.length})` : ""}</span><br /><b>{data.sites.length > 3 ? `${data.sites.slice(0, 3).join(", ")} +${data.sites.length - 3}` : data.sites.join(", ")}</b></td>
            <td style={{ width: "25%" }}><span style={{ color: MUTED }}>Generated</span><br /><b>{generated}</b> by {data.generated_by}</td>
            <td style={{ width: "25%" }}><span style={{ color: MUTED }}>Filters</span><br /><b>{data.filters.length ? data.filters.map((f) => `${f.label}: ${f.value}`).join(" · ") : "None"}</b></td>
          </tr>
        </tbody>
      </table>

      {/* Key figures */}
      <div className="rp-section" style={{ display: "grid", gridTemplateColumns: `repeat(${summary.kpis.length}, 1fr)`, gap: "2.5mm", marginBottom: "4mm" }}>
        {summary.kpis.map((k) => (
          <div key={k.key} style={{ border: `0.8pt solid ${LINE}`, borderTop: `2pt solid ${INK}`, borderRadius: "1.5mm", padding: "2mm 2.5mm" }}>
            <div style={{ fontSize: "7pt", color: MUTED, textTransform: "uppercase", letterSpacing: "0.04em" }}>{k.label}</div>
            <div style={{ fontSize: "15pt", fontWeight: 700, marginTop: "0.5mm" }}>{formatKpi(k)}</div>
          </div>
        ))}
      </div>

      {/* Trend and breakdowns */}
      <div className="rp-section" style={{ display: "grid", gridTemplateColumns: "1.25fr 1fr", gap: "6mm", marginBottom: "5mm" }}>
        <div>
          <div className="rp-h">Daily trend</div>
          <div style={{ display: "flex", gap: "4mm", fontSize: "7.5pt", marginBottom: "1.5mm" }}>
            {summary.trend.series.map((s, i) => (
              <span key={s.key} style={{ display: "inline-flex", alignItems: "center", gap: "1mm" }}>
                <span style={{ width: "2.5mm", height: "2.5mm", background: SERIES[i], display: "inline-block" }} />{s.label}
              </span>
            ))}
          </div>
          <Trend data={data} />
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "4mm", alignContent: "start" }}>
          {breakdowns.slice(0, 4).map((b) => (
            <div key={b.key}>
              <div className="rp-h" style={{ fontSize: "7.5pt" }}>{b.title}</div>
              <table className="rp-mini">
                <tbody>
                  {b.rows.slice(0, 8).map((r) => (
                    <tr key={r.label}><td>{r.label}</td><td style={{ textAlign: "right", fontWeight: 700 }}>{r.value.toLocaleString("en-SG")}</td></tr>
                  ))}
                </tbody>
              </table>
            </div>
          ))}
        </div>
      </div>

      {/* Details */}
      <div className="rp-h">Details · {data.count.toLocaleString("en-SG")} record{data.count === 1 ? "" : "s"}{data.truncated ? ` (first ${data.rows.length.toLocaleString("en-SG")} shown; export to Excel for all)` : ""}</div>
      {data.rows.length === 0 ? (
        <p style={{ color: MUTED }}>No records for this period and filters.</p>
      ) : (
        <table className="rp-details">
          <thead>
            <tr>
              <th style={{ width: "6mm" }}>#</th>
              {data.columns.map((c) => <th key={c.key} style={{ textAlign: numeric(c.kind) ? "right" : "left" }}>{c.label}</th>)}
            </tr>
          </thead>
          <tbody>
            {data.rows.map((row, i) => (
              <tr key={i}>
                <td style={{ color: MUTED }}>{i + 1}</td>
                {data.columns.map((c) => {
                  const text = formatCell(row[c.key], c.kind);
                  return (
                    <td key={c.key} style={{
                      textAlign: numeric(c.kind) ? "right" : "left",
                      whiteSpace: c.kind === "datetime" || c.kind === "date" ? "nowrap" : undefined,
                      color: c.kind === "badge" && text !== "—" ? TONE[badgeTone(text)] : undefined,
                      fontWeight: c.kind === "badge" ? 700 : undefined,
                    }}>{text}</td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {/* Sign-off */}
      <div className="rp-section" style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "10mm", marginTop: "10mm" }}>
        {[["Prepared by", data.generated_by], ["Reviewed by", ""], ["Approved by", ""]].map(([label, name]) => (
          <div key={label}>
            <div style={{ fontSize: "7.5pt", color: MUTED }}>{label}</div>
            <div style={{ borderBottom: `0.8pt solid ${INK}`, height: "12mm" }} />
            <div style={{ fontSize: "8pt", marginTop: "1mm" }}>Name: {name}</div>
            <div style={{ fontSize: "8pt" }}>Date:</div>
          </div>
        ))}
      </div>
    </div>,
    document.body,
  );
}
