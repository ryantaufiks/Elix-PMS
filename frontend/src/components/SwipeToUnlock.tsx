"use client";

import { useRef, useState } from "react";

import { Icon } from "./icons";
import { cx, Spinner } from "./ui";

/** Drag the knob to the end to confirm. Enter/Space on the knob also confirms (keyboard users). */
export function SwipeToUnlock({ onUnlock, label = "Swipe to open gate", disabled }: {
  onUnlock: () => Promise<unknown>;
  label?: string;
  disabled?: boolean;
}) {
  const track = useRef<HTMLDivElement>(null);
  const start = useRef<number | null>(null);
  const [offset, setOffset] = useState(0);
  const [busy, setBusy] = useState(false);
  const KNOB = 52;

  const max = () => (track.current ? track.current.clientWidth - KNOB - 8 : 1);

  async function fire() {
    setBusy(true);
    setOffset(max());
    try {
      await onUnlock();
    } finally {
      setBusy(false);
      setOffset(0);
    }
  }

  return (
    <div
      ref={track}
      className={cx("relative h-[60px] w-full select-none overflow-hidden rounded-full bg-emerald-600 p-1", (disabled || busy) && "opacity-60")}
    >
      <div className="pointer-events-none absolute inset-0 flex items-center justify-center pl-12 text-sm font-semibold text-white">
        {busy ? "Opening…" : label}
      </div>
      <button
        type="button"
        aria-label={label}
        disabled={disabled || busy}
        className="relative z-10 flex h-[52px] w-[52px] touch-none items-center justify-center rounded-full bg-white text-emerald-700 shadow focus-visible:outline-2 focus-visible:outline-white"
        style={{ transform: `translateX(${offset}px)`, transition: start.current === null ? "transform 200ms" : "none" }}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            fire();
          }
        }}
        onPointerDown={(e) => {
          start.current = e.clientX - offset;
          e.currentTarget.setPointerCapture(e.pointerId);
        }}
        onPointerMove={(e) => {
          if (start.current === null) return;
          setOffset(Math.max(0, Math.min(max(), e.clientX - start.current)));
        }}
        onPointerUp={() => {
          start.current = null;
          if (offset >= max() * 0.9) fire();
          else setOffset(0);
        }}
        onPointerCancel={() => {
          start.current = null;
          setOffset(0);
        }}
      >
        {busy ? <Spinner className="h-5 w-5" /> : <Icon name="unlock" className="h-6 w-6" />}
      </button>
    </div>
  );
}
