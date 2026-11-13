"use client";

// Small SVG charts for the dashboard. Colours come from CSS roles (--series-1/2, --grid, --axis)
// that swap with the theme; text always uses text tokens, never the series colour.
import { useEffect, useRef, useState } from "react";

import { cx } from "./ui";

export type HourBucket = { hour: number; granted: number; denied: number; error: number };

function useWidth<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const [width, setWidth] = useState(0);
  useEffect(() => {
    if (!ref.current) return;
    const observer = new ResizeObserver(([entry]) => setWidth(Math.floor(entry.contentRect.width)));
    observer.observe(ref.current);
    return () => observer.disconnect();
  }, []);
  return [ref, width] as const;
}

/** Round up to 1/2/5 x 10^n so the axis shows clean ticks. */
function niceMax(value: number): number {
  if (value <= 4) return 4;
  const power = 10 ** Math.floor(Math.log10(value));
  for (const step of [1, 2, 2.5, 5, 10]) if (step * power >= value) return step * power;
  return 10 * power;
}

const compact = new Intl.NumberFormat("en-SG", { notation: "compact" });

/** Rect with 4px rounded top corners and a square base, anchored at the baseline. */
function topRounded(x: number, y: number, w: number, h: number, r = 4) {
  const rr = Math.min(r, w / 2, h);
  return `M${x},${y + h}V${y + rr}Q${x},${y} ${x + rr},${y}H${x + w - rr}Q${x + w},${y} ${x + w},${y + rr}V${y + h}Z`;
}

const hourLabel = (h: number) => `${String(h).padStart(2, "0")}:00`;

export function TrafficChart({ data, nowHour, height = 300 }: { data: HourBucket[]; nowHour: number; height?: number }) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const [active, setActive] = useState<number | null>(null);
  const [table, setTable] = useState(false);
  const pad = { top: 18, right: 4, bottom: 22, left: 30 };
  const innerW = Math.max(0, width - pad.left - pad.right);
  const innerH = height - pad.top - pad.bottom;
  const max = niceMax(Math.max(0, ...data.map((d) => d.granted + d.denied)));
  const ticks = [0, max / 2, max];
  const band = innerW / 24;
  const barW = Math.max(2, Math.min(24, band * 0.62));
  const y = (v: number) => pad.top + innerH - (v / max) * innerH;
  const peak = data.reduce((best, d) => (d.granted + d.denied > best.granted + best.denied ? d : best), data[0]);
  const total = (d: HourBucket) => d.granted + d.denied;
  const hovered = active !== null ? data[active] : null;

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center gap-x-5 gap-y-2 text-xs text-body">
        <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm" style={{ background: "var(--series-1)" }} />Granted</span>
        <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm" style={{ background: "var(--series-2)" }} />Denied</span>
        <button onClick={() => setTable((t) => !t)} className="ml-auto rounded px-2 py-1 font-medium text-muted hover:bg-surface-3 hover:text-ink">
          {table ? "Show chart" : "View as table"}
        </button>
      </div>
      {data.every((d) => total(d) === 0) && !table ? (
        <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-line py-10 text-center" style={{ minHeight: height / 2 }}>
          <svg viewBox="0 0 24 24" className="h-8 w-8 text-muted" fill="none" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round"><path d="M4 20V10M10 20V4M16 20v-8M22 20H2" /></svg>
          <p className="mt-3 text-sm font-medium text-ink">No gate activity yet today</p>
          <p className="mt-1 text-xs text-muted">The chart fills in hour by hour as the gates are used.</p>
        </div>
      ) : table ? (
        <div className="overflow-y-auto" style={{ maxHeight: height }}>
          <table className="w-full text-sm">
            <thead><tr className="text-left text-xs text-muted"><th className="py-1.5 font-medium">Hour</th><th className="py-1.5 text-right font-medium">Granted</th><th className="py-1.5 text-right font-medium">Denied</th><th className="py-1.5 text-right font-medium">Relay errors</th></tr></thead>
            <tbody className="divide-y divide-line tabular-nums">
              {data.filter((d) => d.hour <= nowHour).map((d) => (
                <tr key={d.hour}><td className="py-1.5 text-body">{hourLabel(d.hour)}</td><td className="py-1.5 text-right text-ink">{d.granted}</td><td className="py-1.5 text-right text-ink">{d.denied}</td><td className="py-1.5 text-right text-ink">{d.error}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div ref={ref} className="relative" style={{ height }} onPointerLeave={() => setActive(null)}>
          {width > 0 && (
            <svg width={width} height={height} role="group" aria-label="Gate decisions per hour today">
              {ticks.map((t) => (
                <g key={t}>
                  <line x1={pad.left} x2={width - pad.right} y1={y(t)} y2={y(t)} stroke={t === 0 ? "var(--axis)" : "var(--grid)"} strokeWidth={1} shapeRendering="crispEdges" />
                  <text x={pad.left - 8} y={y(t)} dy="0.32em" textAnchor="end" className="fill-muted text-[11px] tabular-nums">{compact.format(t)}</text>
                </g>
              ))}
              {data.map((d, i) => {
                const x = pad.left + i * band + (band - barW) / 2;
                const gH = (d.granted / max) * innerH;
                const dH = (d.denied / max) * innerH;
                const gap = d.granted && d.denied ? 2 : 0;
                const dim = active !== null && active !== i;
                return (
                  <g key={d.hour} opacity={dim ? 0.45 : 1} style={{ transition: "opacity 120ms" }}>
                    {d.granted > 0 && (d.denied > 0
                      ? <rect x={x} y={y(d.granted)} width={barW} height={gH} fill="var(--series-1)" />
                      : <path d={topRounded(x, y(d.granted), barW, gH)} fill="var(--series-1)" />)}
                    {d.denied > 0 && <path d={topRounded(x, y(d.granted) - dH - gap, barW, dH)} fill="var(--series-2)" />}
                    <rect
                      x={pad.left + i * band} y={pad.top} width={band} height={innerH} fill="transparent"
                      tabIndex={d.hour <= nowHour ? 0 : -1} role="img"
                      aria-label={`${hourLabel(d.hour)}: ${d.granted} granted, ${d.denied} denied`}
                      onPointerEnter={() => setActive(i)} onFocus={() => setActive(i)} onBlur={() => setActive(null)}
                      className="outline-none"
                    />
                    {i % 3 === 0 && (
                      <text x={pad.left + i * band + band / 2} y={height - 6} textAnchor="middle" className="fill-muted text-[11px] tabular-nums">{String(d.hour).padStart(2, "0")}</text>
                    )}
                  </g>
                );
              })}
              {peak && total(peak) > 0 && active === null && (
                <text x={pad.left + peak.hour * band + band / 2} y={y(total(peak)) - 6} textAnchor="middle" className="fill-ink text-[11px] font-semibold tabular-nums">{total(peak)}</text>
              )}
              <line x1={pad.left + (nowHour + 1) * band} x2={pad.left + (nowHour + 1) * band} y1={pad.top} y2={pad.top + innerH} stroke="var(--axis)" strokeWidth={1} strokeDasharray="0" opacity={0.6} />
            </svg>
          )}
          {hovered && width > 0 && (
            <div
              className="pointer-events-none absolute z-10 min-w-36 rounded-lg border border-line bg-surface px-3 py-2 text-xs shadow-card"
              style={{ left: Math.min(width - 150, Math.max(0, pad.left + hovered.hour * band + band / 2 - 72)), top: 0 }}
            >
              <div className="mb-1 text-muted">{hourLabel(hovered.hour)} – {hourLabel((hovered.hour + 1) % 24)}</div>
              <div className="flex items-center gap-2"><span className="h-0.5 w-3 rounded" style={{ background: "var(--series-1)" }} /><span className="font-semibold text-ink tabular-nums">{hovered.granted}</span><span className="text-muted">granted</span></div>
              <div className="flex items-center gap-2"><span className="h-0.5 w-3 rounded" style={{ background: "var(--series-2)" }} /><span className="font-semibold text-ink tabular-nums">{hovered.denied}</span><span className="text-muted">denied</span></div>
              {hovered.error > 0 && <div className="mt-1 text-muted">{hovered.error} relay error{hovered.error > 1 ? "s" : ""}</div>}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/** Tiny trend line for a stat tile (single series: no legend, no hover). */
export function Sparkline({ values, className }: { values: number[]; className?: string }) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const height = 36;
  const max = Math.max(1, ...values);
  const step = values.length > 1 ? (width - 8) / (values.length - 1) : 0;
  const pts = values.map((v, i) => [4 + i * step, 4 + (height - 8) * (1 - v / max)] as const);
  const line = pts.map(([x, y], i) => `${i ? "L" : "M"}${x},${y}`).join("");
  const last = pts[pts.length - 1];
  return (
    <div ref={ref} className={cx("h-9", className)} aria-hidden="true">
      {width > 0 && values.length > 1 && (
        <svg width={width} height={height}>
          <path d={`${line}L${last[0]},${height}L${pts[0][0]},${height}Z`} fill="var(--series-1)" opacity={0.1} />
          <path d={line} fill="none" stroke="var(--series-1)" strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
          <circle cx={last[0]} cy={last[1]} r={4} fill="var(--series-1)" stroke="var(--c-surface)" strokeWidth={2} />
        </svg>
      )}
    </div>
  );
}

/** Horizontal bars, one hue (magnitude). Values at the bar tip in text ink. */
export function BarList({ rows }: { rows: { label: string; value: number }[] }) {
  const max = Math.max(1, ...rows.map((r) => r.value));
  return (
    <ul className="space-y-3">
      {rows.map((r) => (
        <li key={r.label} title={`${r.label}: ${r.value}`}>
          <div className="mb-1 flex justify-between text-sm"><span className="text-body">{r.label}</span><span className="font-medium tabular-nums text-ink">{r.value}</span></div>
          <div className="h-2 rounded-full bg-surface-3">
            <div className="h-2 rounded-r-full rounded-l-sm transition-[width] duration-500" style={{ width: `${(r.value / max) * 100}%`, background: "var(--series-1)", minWidth: r.value ? 6 : 0 }} />
          </div>
        </li>
      ))}
    </ul>
  );
}

const SERIES = ["var(--series-1)", "var(--series-2)", "var(--series-3)"];

/** Stacked bars per day (up to 3 series), with legend and hover readout. ``label`` formats a date key. */
export function DailyChart({ points, series, label, height = 240 }: {
  points: ({ date: string } & Record<string, number | string>)[];
  series: { key: string; label: string }[];
  label: (date: string) => string;
  height?: number;
}) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const [active, setActive] = useState<number | null>(null);
  const pad = { top: 14, right: 4, bottom: 22, left: 34 };
  const innerW = Math.max(0, width - pad.left - pad.right);
  const innerH = height - pad.top - pad.bottom;
  const total = (p: Record<string, number | string>) => series.reduce((sum, s) => sum + Number(p[s.key] || 0), 0);
  const max = niceMax(Math.max(0, ...points.map(total)));
  const band = points.length ? innerW / points.length : 0;
  const barW = Math.max(2, Math.min(28, band * 0.64));
  const y = (v: number) => pad.top + innerH - (v / max) * innerH;
  const every = Math.max(1, Math.ceil(points.length / Math.max(1, Math.floor(innerW / 56))));
  const hovered = active !== null ? points[active] : null;
  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center gap-x-5 gap-y-2 text-xs text-body">
        {series.map((s, i) => (
          <span key={s.key} className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm" style={{ background: SERIES[i] }} />{s.label}</span>
        ))}
      </div>
      <div ref={ref} className="relative" style={{ height }} onPointerLeave={() => setActive(null)}>
        {width > 0 && (
          <svg width={width} height={height} role="group" aria-label="Daily trend">
            {[0, max / 2, max].map((t) => (
              <g key={t}>
                <line x1={pad.left} x2={width - pad.right} y1={y(t)} y2={y(t)} stroke={t === 0 ? "var(--axis)" : "var(--grid)"} strokeWidth={1} shapeRendering="crispEdges" />
                <text x={pad.left - 8} y={y(t)} dy="0.32em" textAnchor="end" className="fill-muted text-[11px] tabular-nums">{compact.format(t)}</text>
              </g>
            ))}
            {points.map((p, i) => {
              const x = pad.left + i * band + (band - barW) / 2;
              let base = 0;
              const parts = series.map((s, si) => ({ v: Number(p[s.key] || 0), fill: SERIES[si] })).filter((part) => part.v > 0);
              return (
                <g key={p.date} opacity={active !== null && active !== i ? 0.45 : 1} style={{ transition: "opacity 120ms" }}>
                  {parts.map((part, pi) => {
                    const h = (part.v / max) * innerH;
                    const top = y(base + part.v) - 2 * pi; // 2px gap between stacked segments
                    base += part.v;
                    return pi === parts.length - 1
                      ? <path key={pi} d={topRounded(x, top, barW, Math.max(1, h))} fill={part.fill} />
                      : <rect key={pi} x={x} y={top} width={barW} height={h} fill={part.fill} />;
                  })}
                  <rect x={pad.left + i * band} y={pad.top} width={band} height={innerH} fill="transparent" tabIndex={0} role="img"
                    aria-label={`${label(p.date)}: ${series.map((s) => `${p[s.key] || 0} ${s.label}`).join(", ")}`}
                    onPointerEnter={() => setActive(i)} onFocus={() => setActive(i)} onBlur={() => setActive(null)} className="outline-none" />
                  {i % every === 0 && (
                    <text x={pad.left + i * band + band / 2} y={height - 6} textAnchor="middle" className="fill-muted text-[11px] tabular-nums">{label(p.date)}</text>
                  )}
                </g>
              );
            })}
          </svg>
        )}
        {hovered && width > 0 && active !== null && (
          <div className="pointer-events-none absolute z-10 min-w-36 rounded-lg border border-line bg-surface px-3 py-2 text-xs shadow-card"
            style={{ left: Math.min(width - 150, Math.max(0, pad.left + active * band + band / 2 - 72)), top: 0 }}>
            <div className="mb-1 text-muted">{label(hovered.date)}</div>
            {series.map((s, i) => (
              <div key={s.key} className="flex items-center gap-2">
                <span className="h-0.5 w-3 rounded" style={{ background: SERIES[i] }} />
                <span className="font-semibold text-ink tabular-nums">{Number(hovered[s.key] || 0)}</span><span className="text-muted">{s.label}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
