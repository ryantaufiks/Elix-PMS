"use client";

// Web kiosk for a tablet at the gate: call a resident (LiveKit video) or check in with an invitation QR.
import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import jsQR from "jsqr";
import { Room, RoomEvent, Track, type RemoteTrack } from "livekit-client";

import { ApiError, wsUrl } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import {
  type CheckInResult, type DirectoryUnit, isWalkInCode, kioskApi, type KioskSelf, kioskToken, PURPOSES, type VisitorDetails,
  type VisitorLookup, type VisitorPass, type WalkInCheckOut, type WalkInSlip,
} from "@/lib/kiosk";
import type { IntercomCall, LiveKitConnection } from "@/lib/types";
import { Credit } from "@/components/Credit";

type Outcome = { tone: "good" | "bad" | "info"; title: string; detail?: string };
/** Call a resident, or register as a walk-in (printed slip, no call). */
type Mode = "call" | "walkin";
type Screen =
  | { name: "setup" }
  | { name: "home" }
  | { name: "directory"; mode: Mode }
  | { name: "identify"; mode: Mode; unit: DirectoryUnit }
  | { name: "details"; mode: Mode; unit: DirectoryUnit; details: VisitorDetails }
  | { name: "photo"; mode: Mode; unit: DirectoryUnit; details: VisitorDetails }
  | { name: "calling" | "walkin"; unit: DirectoryUnit; details: VisitorDetails }
  | { name: "scan" }
  | { name: "face"; code: string; pass: VisitorPass }
  | { name: "result"; outcome: Outcome };

const IDLE_MS = 90_000;

// --- Camera helpers ----------------------------------------------------------

function useCamera(active: boolean) {
  const video = useRef<HTMLVideoElement>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (!active) return;
    let stream: MediaStream | null = null;
    let cancelled = false;
    navigator.mediaDevices?.getUserMedia({ video: { facingMode: "user", width: { ideal: 1280 } }, audio: false })
      .then((s) => {
        if (cancelled) return s.getTracks().forEach((t) => t.stop());
        stream = s;
        if (video.current) {
          video.current.srcObject = s;
          video.current.play().catch(() => {});
        }
      })
      .catch(() => setError("Camera not available. Allow camera access for this site."));
    return () => {
      cancelled = true;
      stream?.getTracks().forEach((t) => t.stop());
    };
  }, [active]);
  return { video, error };
}

function snapshot(video: HTMLVideoElement | null): Promise<Blob | null> {
  if (!video || !video.videoWidth) return Promise.resolve(null);
  const canvas = document.createElement("canvas");
  const scale = Math.min(1, 960 / video.videoWidth);
  canvas.width = Math.round(video.videoWidth * scale);
  canvas.height = Math.round(video.videoHeight * scale);
  canvas.getContext("2d")!.drawImage(video, 0, 0, canvas.width, canvas.height);
  return new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.85));
}

type Detector = { detect: (source: CanvasImageSource) => Promise<{ rawValue: string }[]> };

function useQrScanner(video: React.RefObject<HTMLVideoElement | null>, active: boolean, onCode: (code: string) => void) {
  const handler = useRef(onCode);
  handler.current = onCode;
  useEffect(() => {
    if (!active) return;
    let stopped = false;
    const BarcodeDetector = (window as unknown as { BarcodeDetector?: new (o: { formats: string[] }) => Detector }).BarcodeDetector;
    const detector = BarcodeDetector ? new BarcodeDetector({ formats: ["qr_code"] }) : null;
    const canvas = document.createElement("canvas");
    async function tick() {
      if (stopped) return;
      const v = video.current;
      if (v && v.videoWidth) {
        try {
          let value: string | undefined;
          if (detector) {
            value = (await detector.detect(v))[0]?.rawValue;
          } else {
            const scale = Math.min(1, 640 / v.videoWidth);
            canvas.width = Math.round(v.videoWidth * scale);
            canvas.height = Math.round(v.videoHeight * scale);
            const ctx = canvas.getContext("2d", { willReadFrequently: true })!;
            ctx.drawImage(v, 0, 0, canvas.width, canvas.height);
            value = jsQR(ctx.getImageData(0, 0, canvas.width, canvas.height).data, canvas.width, canvas.height)?.data;
          }
          if (value && !stopped) {
            stopped = true;
            handler.current(value);
            return;
          }
        } catch {}
      }
      setTimeout(tick, 200);
    }
    tick();
    return () => {
      stopped = true;
    };
  }, [video, active]);
}

// --- UI pieces ---------------------------------------------------------------

function BigButton({ onClick, children, tone = "primary", disabled }: { onClick: () => void; children: React.ReactNode; tone?: "primary" | "ghost" | "danger" | "success"; disabled?: boolean }) {
  const tones = {
    primary: "bg-primary-500 text-white shadow-primary hover:bg-primary-600",
    success: "bg-emerald-600 text-white hover:bg-emerald-700",
    danger: "bg-rose-600 text-white hover:bg-rose-700",
    ghost: "border border-white/20 bg-white/5 text-white hover:bg-white/10",
  };
  return (
    <button onClick={onClick} disabled={disabled} className={`rounded-2xl px-8 py-5 text-xl font-semibold transition-colors disabled:opacity-50 ${tones[tone]}`}>
      {children}
    </button>
  );
}

function Frame({ kiosk, children, onBack }: { kiosk: KioskSelf | null; children: React.ReactNode; onBack?: () => void }) {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 15_000);
    return () => clearInterval(id);
  }, []);
  return (
    <div className="brand-panel flex min-h-dvh flex-col text-white">
      <header className="flex items-center justify-between px-8 py-6">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src="/brand/elix-logo.png" alt="Elix" className="h-9 w-auto drop-shadow-[0_0_16px_rgba(47,111,255,0.5)]" />
        <div className="text-right">
          <div className="text-lg font-medium">{kiosk?.condominium_name}</div>
          <div className="text-sm text-slate-400">
            {new Intl.DateTimeFormat("en-SG", { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", hour12: false, timeZone: "Asia/Singapore" }).format(now)}
          </div>
        </div>
      </header>
      <main className="flex flex-1 flex-col items-center justify-center px-8 pb-10">{children}</main>
      <div className="flex items-end justify-between gap-6 px-8 pb-6">
        <div className="min-w-0 flex-1">
          {onBack && <button onClick={onBack} className="rounded-xl border border-white/15 px-6 py-3 text-lg text-slate-300 hover:bg-white/5">← Back</button>}
        </div>
        <Credit tone="dark" className="shrink-0" />
        <div className="flex-1" />
      </div>
    </div>
  );
}

// --- Screens -----------------------------------------------------------------

function Setup({ onReady }: { onReady: (kiosk: KioskSelf, token: string) => void }) {
  const [token, setToken] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const kiosk = await kioskApi<KioskSelf>("/v1/kiosk/me/", { token: token.trim() });
      onReady(kiosk, token.trim());
    } catch (err) {
      setError(err instanceof ApiError && err.status === 401 ? "That device token is not valid." : (err as Error).message);
      setBusy(false);
    }
  }
  return (
    <Frame kiosk={null}>
      <form onSubmit={submit} className="w-full max-w-lg space-y-5 rounded-2xl border border-white/10 bg-white/5 p-8">
        <h1 className="text-2xl font-semibold">Set up this kiosk</h1>
        <p className="text-slate-300">Enter the device token shown when the kiosk was added in the dashboard (Gates &amp; devices → Kiosks).</p>
        <input value={token} onChange={(e) => setToken(e.target.value)} autoFocus placeholder="Device token"
          className="w-full rounded-xl border border-white/20 bg-navy-950/60 px-4 py-4 font-mono text-lg text-white placeholder:text-slate-500 focus:border-primary-400 focus:outline-none" />
        {error && <p className="text-rose-300">{error}</p>}
        <BigButton onClick={() => {}} disabled={busy || !token.trim()}>{busy ? "Checking…" : "Activate kiosk"}</BigButton>
      </form>
    </Frame>
  );
}

function Home({ kiosk, onCall, onWalkIn, onScan, onAdmin }: { kiosk: KioskSelf; onCall: () => void; onWalkIn: () => void; onScan: () => void; onAdmin: () => void }) {
  const taps = useRef<number[]>([]);
  return (
    <Frame kiosk={kiosk}>
      <h1 className="text-center text-4xl font-semibold tracking-tight sm:text-5xl">Welcome</h1>
      <p className="mt-3 text-center text-lg text-slate-300">How would you like to enter{kiosk.gate_name ? ` through ${kiosk.gate_name}` : ""}?</p>
      <div className={`mt-12 grid w-full gap-6 ${kiosk.walk_in ? "max-w-5xl sm:grid-cols-3" : "max-w-3xl sm:grid-cols-2"}`}>
        <button onClick={onCall} className="group rounded-3xl border border-white/10 bg-white/5 p-8 text-left transition hover:border-primary-400/60 hover:bg-white/10">
          <div className="mb-6 flex h-16 w-16 items-center justify-center rounded-2xl bg-white/10">
            <svg viewBox="0 0 24 24" className="h-8 w-8" fill="none" stroke="currentColor" strokeWidth={1.8}><path d="M5 4h4l2 5-2.5 1.5a11 11 0 0 0 5 5L15 13l5 2v4a2 2 0 0 1-2 2A16 16 0 0 1 3 6a2 2 0 0 1 2-2Z" /></svg>
          </div>
          <div className="text-2xl font-semibold">Call a resident</div>
          <div className="mt-2 text-slate-400">Video call the unit you are visiting.</div>
        </button>
        {kiosk.walk_in && (
          <button onClick={onWalkIn} className="group rounded-3xl border border-white/10 bg-white/5 p-8 text-left transition hover:border-primary-400/60 hover:bg-white/10">
            <div className="mb-6 flex h-16 w-16 items-center justify-center rounded-2xl bg-white/10">
              <svg viewBox="0 0 24 24" className="h-8 w-8" fill="none" stroke="currentColor" strokeWidth={1.8}><path d="M9 3h6v3H9zM7 4.5H5v16.5h14V4.5h-2M8.5 11h7M8.5 15h4.5" /></svg>
            </div>
            <div className="text-2xl font-semibold">Walk in</div>
            <div className="mt-2 text-slate-400">Register your visit and get a pass slip for security.</div>
          </button>
        )}
        <button onClick={onScan} className="group rounded-3xl border border-white/10 bg-white/5 p-8 text-left transition hover:border-primary-400/60 hover:bg-white/10">
          <div className="mb-6 flex h-16 w-16 items-center justify-center rounded-2xl bg-white/10">
            <svg viewBox="0 0 24 24" className="h-8 w-8" fill="none" stroke="currentColor" strokeWidth={1.8}><path d="M4 4h6v6H4zM14 4h6v6h-6zM4 14h6v6H4zM14 14h2v2h-2zM18 14h2v2h-2zM14 18h2v2h-2zM18 18h2v2h-2z" /></svg>
          </div>
          <div className="text-2xl font-semibold">I have an invitation</div>
          <div className="mt-2 text-slate-400">{kiosk.walk_in ? "Show your invitation QR, or scan your walk-in slip when you leave." : "Show the QR code from your invitation."}</div>
        </button>
      </div>
      <button
        aria-label="Kiosk settings"
        className="mt-16 h-10 w-24 opacity-0"
        onClick={() => {
          const now = Date.now();
          taps.current = [...taps.current.filter((t) => now - t < 3000), now];
          if (taps.current.length >= 5) onAdmin();
        }}
      />
    </Frame>
  );
}

function Directory({ kiosk, walkIn, onPick, onBack }: { kiosk: KioskSelf; walkIn: boolean; onPick: (unit: DirectoryUnit) => void; onBack: () => void }) {
  const [q, setQ] = useState("");
  const [units, setUnits] = useState<DirectoryUnit[] | null>(null);
  useEffect(() => {
    const id = setTimeout(() => {
      kioskApi<DirectoryUnit[]>(`/v1/kiosk/directory/?q=${encodeURIComponent(q)}${walkIn ? "&walk_in=1" : ""}`).then(setUnits).catch(() => setUnits([]));
    }, 250);
    return () => clearTimeout(id);
  }, [q, walkIn]);
  return (
    <Frame kiosk={kiosk} onBack={onBack}>
      <div className="w-full max-w-4xl">
        <h1 className="text-3xl font-semibold">Which unit are you visiting?</h1>
        <div className="mt-6">
          <input value={q} onChange={(e) => setQ(e.target.value)} autoFocus inputMode="text" placeholder="Unit number, e.g. 05-12"
            className={INPUT} />
        </div>
        <div className="mt-6 grid max-h-[50vh] grid-cols-2 gap-3 overflow-y-auto sm:grid-cols-4">
          {units === null ? <p className="col-span-full text-slate-400">Loading…</p>
            : units.length === 0 ? <p className="col-span-full text-slate-400">No unit found. Check the number, or call the guardhouse.</p>
            : units.map((u) => (
              <button key={u.id} onClick={() => onPick(u)} className="rounded-2xl border border-white/10 bg-white/5 px-4 py-5 text-left hover:border-primary-400/60 hover:bg-white/10">
                <div className="text-sm text-slate-400">{u.block || "Unit"}</div>
                <div className="text-2xl font-semibold">{u.label}</div>
              </button>
            ))}
        </div>
      </div>
    </Frame>
  );
}

function Calling({ kiosk, unit, details, onDone }: { kiosk: KioskSelf; unit: DirectoryUnit; details: VisitorDetails; onDone: (o: Outcome) => void }) {
  const remote = useRef<HTMLVideoElement>(null);
  const self = useRef<HTMLVideoElement>(null);
  const audio = useRef<HTMLDivElement>(null);
  const [call, setCall] = useState<IntercomCall | null>(null);
  const [hasRemoteVideo, setHasRemoteVideo] = useState(false);
  const [seconds, setSeconds] = useState(kiosk.ring_timeout_seconds);
  const room = useRef<Room | null>(null);
  const finished = useRef(false);
  const done = useRef(onDone);
  done.current = onDone;

  const finish = useCallback((outcome: Outcome) => {
    if (finished.current) return;
    finished.current = true;
    room.current?.disconnect();
    done.current(outcome);
  }, []);

  // Ring the unit with the visitor's details, then join the LiveKit room.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      const form = new FormData();
      form.set("unit", String(unit.id));
      form.set("visitor_ref", details.ref);
      form.set("visitor_name", details.name);
      form.set("visitor_phone", details.phone);
      form.set("visitor_id_partial", details.idPartial);
      form.set("purpose", details.purpose);
      form.set("company", details.company);
      form.set("consent", details.consent ? "true" : "false");
      if (details.photo) form.set("snapshot", details.photo, "visitor.jpg");
      let started: { call: IntercomCall; livekit: LiveKitConnection };
      try {
        started = await kioskApi("/v1/kiosk/calls/", { method: "POST", body: form });
      } catch (err) {
        if (err instanceof ApiError && err.status === 403) return finish({ tone: "bad", title: "Please see the guardhouse", detail: "The security team will help you." });
        const msg = err instanceof ApiError && err.status === 503 ? "Video intercom is not available right now." : (err as Error).message;
        return finish({ tone: "bad", title: "Could not place the call", detail: msg });
      }
      if (cancelled) return;
      setCall(started.call);
      const r = new Room({ adaptiveStream: true, dynacast: true });
      room.current = r;
      r.on(RoomEvent.TrackSubscribed, (track: RemoteTrack) => {
        if (track.kind === Track.Kind.Video && remote.current) {
          track.attach(remote.current);
          setHasRemoteVideo(true);
        } else if (track.kind === Track.Kind.Audio && audio.current) {
          audio.current.appendChild(track.attach());
        }
      });
      r.on(RoomEvent.TrackUnsubscribed, (track) => {
        if (track.kind === Track.Kind.Video) setHasRemoteVideo(false);
      });
      // If the resident's phone drops out of the room (app closed, signal lost) and nobody is left,
      // end the call instead of waiting for a hang-up that will never come.
      let leftTimer: ReturnType<typeof setTimeout> | undefined;
      r.on(RoomEvent.ParticipantConnected, () => clearTimeout(leftTimer));
      r.on(RoomEvent.ParticipantDisconnected, () => {
        clearTimeout(leftTimer);
        if (r.remoteParticipants.size > 0) return;
        leftTimer = setTimeout(async () => {
          if (r.remoteParticipants.size > 0) return;
          await kioskApi(`/v1/kiosk/calls/${started.call.id}/hangup/`, { method: "POST" }).catch(() => {});
          finish({ tone: "info", title: "Call ended", detail: "The resident left the call." });
        }, 8000);
      });
      try {
        await r.connect(started.livekit.url, started.livekit.token);
        await r.localParticipant.enableCameraAndMicrophone();
        const cam = r.localParticipant.getTrackPublication(Track.Source.Camera)?.track;
        if (cam && self.current) cam.attach(self.current);
      } catch {
        // Audio/video may fail on some tablets; the call itself (and the resident's unlock) still works.
      }
    })();
    return () => {
      cancelled = true;
      room.current?.disconnect();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Follow the call: WebSocket pushes, polling as a fallback.
  const apply = useCallback((c: IntercomCall) => {
    setCall(c);
    if (c.status === "approved") finish({ tone: "good", title: "Welcome!", detail: `${unit.label} has opened the gate for you.` });
    else if (c.status === "rejected") finish({ tone: "bad", title: "The resident declined", detail: "Please contact the guardhouse if you need help." });
    else if (c.status === "missed") finish({ tone: "info", title: "No answer", detail: "Nobody picked up. You can try again or call the guardhouse." });
    else if (c.status === "cancelled" && c.ended_at) finish({ tone: "info", title: "Call ended" });
  }, [finish, unit.label]);

  useEffect(() => {
    if (!call) return;
    const token = kioskToken.get();
    const ws = new WebSocket(wsUrl(`/ws/events/?kiosk_token=${encodeURIComponent(token ?? "")}`));
    ws.onmessage = (m) => {
      try {
        const event = JSON.parse(m.data);
        if (event.type === "intercom_call" && event.data.id === call.id) apply(event.data);
      } catch {}
    };
    const poll = setInterval(() => kioskApi<IntercomCall>(`/v1/kiosk/calls/${call.id}/`).then(apply).catch(() => {}), 3000);
    return () => {
      ws.close();
      clearInterval(poll);
    };
  }, [call?.id, apply]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const id = setInterval(() => setSeconds((s) => Math.max(0, s - 1)), 1000);
    return () => clearInterval(id);
  }, []);

  async function hangUp() {
    if (call) await kioskApi(`/v1/kiosk/calls/${call.id}/hangup/`, { method: "POST" }).catch(() => {});
    finish({ tone: "info", title: "Call ended" });
  }

  const answered = call?.status === "answered";
  return (
    <Frame kiosk={kiosk}>
      <div className="grid w-full max-w-5xl items-center gap-8 lg:grid-cols-[1.4fr_1fr]">
        <div className="relative aspect-video overflow-hidden rounded-3xl border border-white/10 bg-navy-950">
          <video ref={remote} autoPlay playsInline className={hasRemoteVideo ? "h-full w-full object-cover" : "hidden"} />
          {!hasRemoteVideo && (
            <div className="flex h-full flex-col items-center justify-center gap-4">
              <span className="relative flex h-24 w-24 items-center justify-center rounded-full bg-primary-500/20">
                {!answered && <span className="absolute inset-0 animate-ping rounded-full bg-primary-500/30" />}
                <svg viewBox="0 0 24 24" className="h-10 w-10 text-primary-300" fill="none" stroke="currentColor" strokeWidth={1.8}><path d="M5 4h4l2 5-2.5 1.5a11 11 0 0 0 5 5L15 13l5 2v4a2 2 0 0 1-2 2A16 16 0 0 1 3 6a2 2 0 0 1 2-2Z" /></svg>
              </span>
              <span className="text-slate-300">{answered ? "Connected. The resident can see and hear you." : "Ringing…"}</span>
            </div>
          )}
          <video ref={self} autoPlay playsInline muted className={call ? "absolute right-4 top-4 h-24 rounded-xl border border-white/20 object-cover" : "hidden"} />
          <div ref={audio} hidden />
        </div>
        <div>
          <div className="text-slate-400">{answered ? "Talking to" : "Calling"}</div>
          <div className="mt-1 text-5xl font-semibold tracking-tight">{unit.label}</div>
          <div className="mt-1 text-xl text-slate-300">{unit.block}</div>
          {!answered && <div className="mt-6 text-slate-400">Waiting for an answer · {seconds}s</div>}
          <div className="mt-10"><BigButton tone="danger" onClick={hangUp}>End call</BigButton></div>
        </div>
      </div>
    </Frame>
  );
}

const INPUT = "w-full rounded-2xl border border-white/20 bg-navy-950/60 px-5 py-4 text-2xl text-white placeholder:text-slate-500 focus:border-primary-400 focus:outline-none";
const ID_PARTIAL = /^\d{3}[A-Za-z]$/;

const emptyDetails = (): VisitorDetails => ({ ref: "", maskedName: "", name: "", phone: "", idPartial: "", purpose: "", company: "", consent: false, photo: null });

/** "Been here before?" Mobile number or the last 4 characters of NRIC/FIN; only a masked name comes back. */
function Identify({ kiosk, onFound, onNew, onBlocked, onBack }: {
  kiosk: KioskSelf;
  onFound: (d: VisitorDetails) => void;
  onNew: (d: VisitorDetails) => void;
  onBlocked: () => void;
  onBack: () => void;
}) {
  const [value, setValue] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [match, setMatch] = useState<{ lookup: VisitorLookup; details: VisitorDetails } | null>(null);

  async function find() {
    const v = value.trim();
    const details = { ...emptyDetails(), ...(ID_PARTIAL.test(v) ? { idPartial: v.toUpperCase() } : { phone: v }) };
    setBusy(true);
    setError("");
    try {
      const lookup = await kioskApi<VisitorLookup>("/v1/kiosk/visitors/lookup/", {
        method: "POST", body: ID_PARTIAL.test(v) ? { id_partial: v } : { phone: v },
      });
      if (lookup.blocked) return onBlocked();
      if (!lookup.found) return onNew(details);
      setMatch({ lookup, details: { ...details, ref: lookup.ref, maskedName: lookup.masked_name, company: lookup.company, purpose: lookup.purpose } });
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if (match) {
    return (
      <Frame kiosk={kiosk} onBack={() => setMatch(null)}>
        <h1 className="text-center text-4xl font-semibold">Welcome back</h1>
        <p className="mt-4 text-center text-3xl tracking-wide text-primary-200">{match.lookup.masked_name}</p>
        <p className="mt-3 text-center text-lg text-slate-300">Is this you?</p>
        <div className="mt-10 flex flex-wrap justify-center gap-4">
          <BigButton tone="ghost" onClick={() => onNew({ ...emptyDetails(), phone: match.details.phone, idPartial: match.details.idPartial })}>No, it&apos;s not me</BigButton>
          <BigButton onClick={() => onFound(match.details)}>Yes, continue</BigButton>
        </div>
      </Frame>
    );
  }
  return (
    <Frame kiosk={kiosk} onBack={onBack}>
      <div className="w-full max-w-2xl">
        <h1 className="text-3xl font-semibold">Been here before?</h1>
        <p className="mt-2 text-lg text-slate-300">Enter your mobile number or the last 4 characters of your NRIC/FIN to skip the form.</p>
        <input value={value} onChange={(e) => setValue(e.target.value)} autoFocus inputMode="text" placeholder="9123 4567 or 567A"
          onKeyDown={(e) => e.key === "Enter" && value.trim() && find()} className={`${INPUT} mt-6`} />
        {error && <p className="mt-3 text-rose-300">{error}</p>}
        <div className="mt-8 flex flex-wrap gap-4">
          <BigButton onClick={find} disabled={busy || !value.trim()}>{busy ? "Checking…" : "Continue"}</BigButton>
          <BigButton tone="ghost" onClick={() => onNew(emptyDetails())}>First time here</BigButton>
        </div>
      </div>
    </Frame>
  );
}

function Notice({ kiosk }: { kiosk: KioskSelf }) {
  return (
    <div className="max-h-40 overflow-y-auto rounded-2xl border border-white/10 bg-white/5 p-4 text-sm leading-relaxed text-slate-300">
      <div className="mb-1 font-semibold text-white">How we use your data</div>
      {kiosk.privacy_notice}
    </div>
  );
}

/** Name, purpose and (optionally) contact details. Consent is asked here when no photo step follows. */
function Details({ kiosk, walkIn, unit, initial, onNext, onBack }: {
  kiosk: KioskSelf; walkIn: boolean; unit: DirectoryUnit; initial: VisitorDetails; onNext: (d: VisitorDetails) => void; onBack: () => void;
}) {
  const [d, setD] = useState(initial);
  const set = (patch: Partial<VisitorDetails>) => setD((cur) => ({ ...cur, ...patch }));
  const purpose = PURPOSES.find((p) => p.value === d.purpose);
  const finalStep = walkIn ? !kiosk.walk_in_photo : !kiosk.photo_required;
  const ready = (d.ref || d.name.trim()) && d.purpose;
  return (
    <Frame kiosk={kiosk} onBack={onBack}>
      <div className="w-full max-w-4xl">
        <h1 className="text-3xl font-semibold">{d.ref ? `Hi ${d.maskedName}` : walkIn ? "Register your visit" : "Tell the resident who you are"}</h1>
        <p className="mt-1 text-lg text-slate-300">Visiting {unit.label}{unit.block ? `, ${unit.block}` : ""}</p>
        {!d.ref && (
          <input value={d.name} onChange={(e) => set({ name: e.target.value })} autoFocus placeholder="Your name" maxLength={150} className={`${INPUT} mt-6`} />
        )}
        <div className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-3">
          {PURPOSES.map((p) => (
            <button key={p.value} onClick={() => set({ purpose: p.value })}
              className={`rounded-2xl border px-4 py-4 text-left text-lg font-medium transition ${d.purpose === p.value ? "border-primary-400 bg-primary-500/25 text-white" : "border-white/10 bg-white/5 text-slate-200 hover:bg-white/10"}`}>
              {p.label}
            </button>
          ))}
        </div>
        {purpose?.company && (
          <input value={d.company} onChange={(e) => set({ company: e.target.value })} placeholder={purpose.company} maxLength={100} className={`${INPUT} mt-4 text-xl`} />
        )}
        {!d.ref && (
          <div className="mt-4 grid gap-4 sm:grid-cols-2">
            <input value={d.phone} onChange={(e) => set({ phone: e.target.value })} inputMode="tel" placeholder="Mobile (optional)" className={`${INPUT} text-xl`} />
            <input value={d.idPartial} onChange={(e) => set({ idPartial: e.target.value.toUpperCase().slice(0, 4) })} placeholder="Last 4 of NRIC/FIN (optional)" className={`${INPUT} text-xl`} />
            <p className="text-sm text-slate-400 sm:col-span-2">Optional: lets you skip this form on your next visit. Only the last 4 characters of your NRIC/FIN are kept.</p>
          </div>
        )}
        {finalStep && <div className="mt-6"><Notice kiosk={kiosk} /></div>}
        <div className="mt-8">
          <BigButton onClick={() => onNext({ ...d, name: d.name.trim(), company: purpose?.company ? d.company.trim() : "", consent: finalStep || d.consent })} disabled={!ready}>
            {finalStep ? (walkIn ? "Agree & get my pass" : "Agree & call") : "Next: photo"}
          </BigButton>
        </div>
      </div>
    </Frame>
  );
}

/** Explicit photo with preview and retake, then the privacy notice and consent. */
function PhotoConsent({ kiosk, walkIn, onNext, onBack }: { kiosk: KioskSelf; walkIn: boolean; onNext: (photo: Blob) => void; onBack: () => void }) {
  const [photo, setPhoto] = useState<{ blob: Blob; url: string } | null>(null);
  const { video, error } = useCamera(!photo);
  const [count, setCount] = useState<number | null>(null);
  useEffect(() => () => { if (photo) URL.revokeObjectURL(photo.url); }, [photo]);
  useEffect(() => {
    if (count === null) return;
    if (count === 0) {
      snapshot(video.current).then((b) => b && setPhoto({ blob: b, url: URL.createObjectURL(b) }));
      setCount(null);
      return;
    }
    const id = setTimeout(() => setCount(count - 1), 1000);
    return () => clearTimeout(id);
  }, [count, video]);
  return (
    <Frame kiosk={kiosk} onBack={onBack}>
      <div className="grid w-full max-w-5xl items-start gap-8 lg:grid-cols-[1.2fr_1fr]">
        <div className="relative aspect-[4/3] overflow-hidden rounded-3xl border border-white/10 bg-navy-950">
          {photo ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={photo.url} alt="Your photo" className="h-full w-full scale-x-[-1] object-cover" />
          ) : (
            <video ref={video} autoPlay playsInline muted className="h-full w-full scale-x-[-1] object-cover" />
          )}
          {count !== null && count > 0 && <div className="absolute inset-0 flex items-center justify-center text-8xl font-bold">{count}</div>}
          {error && <div className="absolute inset-0 flex items-center justify-center p-6 text-center text-rose-300">{error}</div>}
        </div>
        <div>
          <h1 className="text-3xl font-semibold">{photo ? "Happy with this photo?" : "A quick photo please"}</h1>
          <p className="mt-2 text-lg text-slate-300">{walkIn ? "Security uses it to check your pass." : "The resident sees it before answering."}</p>
          <div className="mt-6"><Notice kiosk={kiosk} /></div>
          <div className="mt-8 flex flex-wrap gap-4">
            {photo ? (
              <>
                <BigButton tone="ghost" onClick={() => setPhoto(null)}>Retake</BigButton>
                <BigButton onClick={() => onNext(photo.blob)}>{walkIn ? "Agree & get my pass" : "Agree & call"}</BigButton>
              </>
            ) : (
              <BigButton onClick={() => setCount(3)} disabled={count !== null || !!error}>Take photo</BigButton>
            )}
          </div>
        </div>
      </div>
    </Frame>
  );
}

function Scan({ kiosk, onCode, onBack }: { kiosk: KioskSelf; onCode: (code: string) => void; onBack: () => void }) {
  const { video, error } = useCamera(true);
  useQrScanner(video, true, onCode);
  return (
    <Frame kiosk={kiosk} onBack={onBack}>
      <h1 className="text-3xl font-semibold">{kiosk.walk_in ? "Show your invitation or slip QR code" : "Show your invitation QR code"}</h1>
      <p className="mt-2 text-lg text-slate-300">{kiosk.walk_in ? "Hold your phone or your walk-in slip up to the camera." : "Hold your phone up to the camera."}</p>
      <div className="relative mt-8 aspect-[4/3] w-full max-w-xl overflow-hidden rounded-3xl border border-white/10 bg-navy-950">
        <video ref={video} autoPlay playsInline muted className="h-full w-full scale-x-[-1] object-cover" />
        <div className="pointer-events-none absolute inset-[18%] rounded-2xl border-4 border-primary-400/80 shadow-[0_0_0_9999px_rgba(7,15,36,0.45)]" />
        {error && <div className="absolute inset-0 flex items-center justify-center p-6 text-center text-rose-300">{error}</div>}
      </div>
    </Frame>
  );
}

function Face({ kiosk, pass, onCapture, onBack }: { kiosk: KioskSelf; pass: VisitorPass; onCapture: (photo: Blob) => void; onBack: () => void }) {
  const { video, error } = useCamera(true);
  const [count, setCount] = useState<number | null>(null);
  useEffect(() => {
    if (count === null) return;
    if (count === 0) {
      snapshot(video.current).then((b) => b && onCapture(b));
      return;
    }
    const id = setTimeout(() => setCount(count - 1), 1000);
    return () => clearTimeout(id);
  }, [count, video, onCapture]);
  return (
    <Frame kiosk={kiosk} onBack={onBack}>
      <h1 className="text-3xl font-semibold">Hi {pass.visitor_name}, a quick photo please</h1>
      <p className="mt-2 text-lg text-slate-300">This invitation asks for a face photo. It is kept with the entry record for security.</p>
      <div className="relative mt-8 aspect-[4/3] w-full max-w-xl overflow-hidden rounded-3xl border border-white/10 bg-navy-950">
        <video ref={video} autoPlay playsInline muted className="h-full w-full scale-x-[-1] object-cover" />
        {count !== null && count > 0 && <div className="absolute inset-0 flex items-center justify-center text-8xl font-bold">{count}</div>}
        {error && <div className="absolute inset-0 flex items-center justify-center p-6 text-center text-rose-300">{error}</div>}
      </div>
      <div className="mt-8"><BigButton onClick={() => setCount(3)} disabled={count !== null || !!error}>Take photo</BigButton></div>
    </Frame>
  );
}

function Result({ kiosk, outcome, onDone }: { kiosk: KioskSelf; outcome: Outcome; onDone: () => void }) {
  useEffect(() => {
    const id = setTimeout(onDone, 7000);
    return () => clearTimeout(id);
  }, [onDone]);
  const ring = outcome.tone === "good" ? "bg-emerald-500/20 text-emerald-300" : outcome.tone === "bad" ? "bg-rose-500/20 text-rose-300" : "bg-white/10 text-slate-200";
  return (
    <Frame kiosk={kiosk}>
      <span className={`flex h-28 w-28 items-center justify-center rounded-full ${ring}`}>
        <svg viewBox="0 0 24 24" className="h-14 w-14" fill="none" stroke="currentColor" strokeWidth={2.2} strokeLinecap="round">
          <path d={outcome.tone === "good" ? "M5 12l5 5L20 7" : outcome.tone === "bad" ? "M6 6l12 12M18 6 6 18" : "M12 8v5M12 16h.01"} />
        </svg>
      </span>
      <h1 className="mt-8 text-center text-4xl font-semibold">{outcome.title}</h1>
      {outcome.detail && <p className="mt-3 max-w-xl text-center text-xl text-slate-300">{outcome.detail}</p>}
      <div className="mt-12"><BigButton tone="ghost" onClick={onDone}>Done</BigButton></div>
    </Frame>
  );
}

const clock = (iso: string) =>
  new Intl.DateTimeFormat("en-SG", { hour: "2-digit", minute: "2-digit", hour12: false, timeZone: "Asia/Singapore" }).format(new Date(iso));

/** Register the walk-in, then print the slip (or show the pass on screen when the kiosk has no printer). */
function WalkIn({ kiosk, unit, details, onDone, onFail }: {
  kiosk: KioskSelf; unit: DirectoryUnit; details: VisitorDetails; onDone: () => void; onFail: (o: Outcome) => void;
}) {
  const [slip, setSlip] = useState<WalkInSlip | null>(null);
  const printed = useRef(false);
  const fail = useRef(onFail);
  fail.current = onFail;

  useEffect(() => {
    const form = new FormData();
    form.set("unit", String(unit.id));
    form.set("visitor_ref", details.ref);
    form.set("visitor_name", details.name);
    form.set("visitor_phone", details.phone);
    form.set("visitor_id_partial", details.idPartial);
    form.set("purpose", details.purpose);
    form.set("company", details.company);
    form.set("consent", "true");
    if (details.photo) form.set("snapshot", details.photo, "visitor.jpg");
    kioskApi<WalkInSlip>("/v1/kiosk/walk-ins/", { method: "POST", body: form })
      .then(setSlip)
      .catch((err) => fail.current(err instanceof ApiError && err.status === 403
        ? { tone: "bad", title: "Please see the guardhouse", detail: "The security team will help you." }
        : { tone: "bad", title: "Could not register your visit", detail: (err as Error).message }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Back to the welcome screen on its own; longer without a printer so the visitor can photograph the QR.
  useEffect(() => {
    if (!slip) return;
    const id = setTimeout(onDone, kiosk.prints_slips ? 25_000 : 60_000);
    return () => clearTimeout(id);
  }, [slip, kiosk.prints_slips, onDone]);

  const print = () => window.print();

  if (!slip) {
    return (
      <Frame kiosk={kiosk}>
        <span className="h-14 w-14 animate-spin rounded-full border-4 border-white/15 border-t-primary-400" />
        <p className="mt-6 text-xl text-slate-300">Registering your visit…</p>
      </Frame>
    );
  }
  return (
    <Frame kiosk={kiosk}>
      {kiosk.prints_slips && <PrintSlip slip={slip} onReady={() => { if (!printed.current) { printed.current = true; print(); } }} />}
      <div className={`grid w-full items-center gap-10 ${kiosk.prints_slips ? "max-w-2xl" : "max-w-5xl lg:grid-cols-[1fr_auto]"}`}>
        <div className={kiosk.prints_slips ? "text-center" : ""}>
          <div className="text-lg text-slate-400">Your pass number</div>
          <div className="mt-2 font-mono text-8xl font-bold tracking-wider text-white">{slip.pass_number}</div>
          <div className="mt-4 text-2xl font-medium">{slip.visitor_name}</div>
          <div className="mt-1 text-lg text-slate-300">{[slip.purpose_display, slip.company].filter(Boolean).join(" · ")} · Visiting {slip.unit_display}</div>
          <p className="mt-8 text-xl text-slate-200">
            {kiosk.prints_slips
              ? "Please take your slip from the printer and show it to security."
              : "Please show this pass to security, and take a photo of the QR code."}
          </p>
          <p className="mt-2 text-lg text-slate-400">When you leave, scan the QR code here under “I have an invitation”. Valid today until {clock(slip.valid_until)}.</p>
          <div className={`mt-10 flex flex-wrap gap-4 ${kiosk.prints_slips ? "justify-center" : ""}`}>
            {kiosk.prints_slips && <BigButton tone="ghost" onClick={print}>Print again</BigButton>}
            <BigButton onClick={onDone}>Done</BigButton>
          </div>
        </div>
        {!kiosk.prints_slips && (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={slip.qr} alt={`QR code for pass ${slip.pass_number}`} className="h-72 w-72 rounded-2xl bg-white p-3" />
        )}
      </div>
    </Frame>
  );
}

const fullDate = (iso: string) =>
  new Intl.DateTimeFormat("en-SG", { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit", hour12: false, timeZone: "Asia/Singapore" }).format(new Date(iso));

/** The 58 mm receipt: only this is printed (the rest of the page is hidden for print). */
function PrintSlip({ slip, onReady }: { slip: WalkInSlip; onReady: () => void }) {
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
      <div style={{ textAlign: "center", fontSize: "7.5pt", letterSpacing: "0.12em", marginTop: "1mm" }}>WALK-IN VISITOR PASS</div>
      <div style={{ borderTop: "1px dashed #000", margin: "2.5mm 0" }} />
      <div style={{ textAlign: "center", fontFamily: "ui-monospace, Menlo, Consolas, monospace", fontWeight: 800, fontSize: "26pt", lineHeight: 1.1 }}>{slip.pass_number}</div>
      <div style={{ textAlign: "center", fontWeight: 600, marginTop: "1mm" }}>{slip.purpose_display}</div>
      <div style={{ borderTop: "1px dashed #000", margin: "2.5mm 0" }} />
      <div style={row}><span>Name</span><b style={{ textAlign: "right" }}>{slip.visitor_name}</b></div>
      {slip.company && <div style={row}><span>Company</span><b style={{ textAlign: "right" }}>{slip.company}</b></div>}
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

// --- App ---------------------------------------------------------------------

export default function KioskPage() {
  const [kiosk, setKiosk] = useState<KioskSelf | null>(null);
  const [screen, setScreen] = useState<Screen>({ name: "home" });
  const [booted, setBooted] = useState(false);
  const home = useCallback(() => setScreen({ name: "home" }), []);

  useEffect(() => {
    document.documentElement.dataset.theme = "dark";
    if (!kioskToken.get()) {
      setScreen({ name: "setup" });
      setBooted(true);
      return;
    }
    kioskApi<KioskSelf>("/v1/kiosk/me/")
      .then((k) => setKiosk(k))
      .catch((err) => {
        if (err instanceof ApiError && err.status === 401) {
          kioskToken.clear();
          setScreen({ name: "setup" });
        }
      })
      .finally(() => setBooted(true));
  }, []);

  // Heartbeat so the dashboard shows this kiosk online.
  useEffect(() => {
    if (!kiosk) return;
    const id = setInterval(() => kioskApi<KioskSelf>("/v1/kiosk/me/").then(setKiosk).catch(() => {}), 60_000);
    return () => clearInterval(id);
  }, [kiosk?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  // Return to the welcome screen when left idle (never mid-call).
  useEffect(() => {
    if (screen.name === "home" || screen.name === "setup" || screen.name === "calling") return;
    let timer = setTimeout(home, IDLE_MS);
    const reset = () => {
      clearTimeout(timer);
      timer = setTimeout(home, IDLE_MS);
    };
    window.addEventListener("pointerdown", reset);
    window.addEventListener("keydown", reset);
    return () => {
      clearTimeout(timer);
      window.removeEventListener("pointerdown", reset);
      window.removeEventListener("keydown", reset);
    };
  }, [screen.name, home]);

  const checkIn = useCallback(async (code: string, photo?: Blob) => {
    if (isWalkInCode(code)) {
      try {
        const r = await kioskApi<WalkInCheckOut>("/v1/kiosk/walk-ins/checkout/", { method: "POST", body: { code } });
        const at = clock(r.walk_in.checked_out_at ?? new Date().toISOString());
        setScreen({ name: "result", outcome: r.result === "checked_out"
          ? { tone: "good", title: `Goodbye, ${r.walk_in.visitor_name}!`, detail: `Pass ${r.walk_in.pass_number} checked out at ${at}. Thank you for visiting.` }
          : { tone: "info", title: "Already checked out", detail: `Pass ${r.walk_in.pass_number} was checked out at ${at}.` } });
      } catch (err) {
        setScreen({ name: "result", outcome: { tone: "bad", title: err instanceof ApiError && err.status === 404 ? "Unknown pass" : "Something went wrong", detail: err instanceof ApiError && err.status === 404 ? "Please see the guardhouse." : (err as Error).message } });
      }
      return;
    }
    const form = new FormData();
    form.set("code", code);
    if (photo) form.set("face_photo", photo, "face.jpg");
    try {
      const r = await kioskApi<CheckInResult>("/v1/kiosk/checkin/", { method: "POST", body: form });
      if (r.result === "face_required" && r.invitation) setScreen({ name: "face", code, pass: r.invitation });
      else if (r.result === "granted") setScreen({ name: "result", outcome: { tone: "good", title: `Welcome, ${r.invitation?.visitor_name ?? "visitor"}!`, detail: `The gate is opening. You are visiting ${r.invitation?.unit_display ?? ""}.` } });
      else setScreen({ name: "result", outcome: { tone: "bad", title: "Entry not allowed", detail: r.reason } });
    } catch (err) {
      setScreen({ name: "result", outcome: { tone: "bad", title: "Something went wrong", detail: (err as Error).message } });
    }
  }, []);

  if (!booted) return <div className="brand-panel min-h-dvh" />;
  if (screen.name === "setup" || !kiosk) {
    return <Setup onReady={(k, token) => { kioskToken.set(token); setKiosk(k); setScreen({ name: "home" }); }} />;
  }
  switch (screen.name) {
    case "home":
      return (
        <Home kiosk={kiosk}
          onCall={() => { document.documentElement.requestFullscreen?.().catch(() => {}); setScreen({ name: "directory", mode: "call" }); }}
          onWalkIn={() => { document.documentElement.requestFullscreen?.().catch(() => {}); setScreen({ name: "directory", mode: "walkin" }); }}
          onScan={() => { document.documentElement.requestFullscreen?.().catch(() => {}); setScreen({ name: "scan" }); }}
          onAdmin={() => { if (window.confirm("Sign this kiosk out?")) { kioskToken.clear(); setKiosk(null); setScreen({ name: "setup" }); } }} />
      );
    case "directory": {
      const mode = screen.mode;
      return <Directory kiosk={kiosk} walkIn={mode === "walkin"} onBack={home} onPick={(unit) => {
        if (mode === "walkin" || kiosk.visitor_form) setScreen({ name: "identify", mode, unit });
        else if (kiosk.photo_required) setScreen({ name: "photo", mode, unit, details: { ...emptyDetails(), consent: true } });
        else setScreen({ name: "calling", unit, details: emptyDetails() });
      }} />;
    }
    case "identify":
      return <Identify kiosk={kiosk} onBack={() => setScreen({ name: "directory", mode: screen.mode })}
        onBlocked={() => setScreen({ name: "result", outcome: { tone: "bad", title: "Please see the guardhouse", detail: "The security team will help you." } })}
        onFound={(details) => setScreen({ name: "details", mode: screen.mode, unit: screen.unit, details })}
        onNew={(details) => setScreen({ name: "details", mode: screen.mode, unit: screen.unit, details })} />;
    case "details": {
      const { mode, unit } = screen;
      const photo = mode === "walkin" ? kiosk.walk_in_photo : kiosk.photo_required;
      return <Details kiosk={kiosk} walkIn={mode === "walkin"} unit={unit} initial={screen.details} onBack={() => setScreen({ name: "identify", mode, unit })}
        onNext={(details) => setScreen(photo ? { name: "photo", mode, unit, details } : { name: mode === "walkin" ? "walkin" : "calling", unit, details })} />;
    }
    case "photo": {
      const { mode, unit, details } = screen;
      return <PhotoConsent kiosk={kiosk} walkIn={mode === "walkin"}
        onBack={() => setScreen(mode === "walkin" || kiosk.visitor_form ? { name: "details", mode, unit, details } : { name: "directory", mode })}
        onNext={(photo) => setScreen({ name: mode === "walkin" ? "walkin" : "calling", unit, details: { ...details, photo, consent: true } })} />;
    }
    case "calling":
      return <Calling kiosk={kiosk} unit={screen.unit} details={screen.details} onDone={(outcome) => setScreen({ name: "result", outcome })} />;
    case "walkin":
      return <WalkIn kiosk={kiosk} unit={screen.unit} details={screen.details} onDone={home} onFail={(outcome) => setScreen({ name: "result", outcome })} />;
    case "scan":
      return <Scan kiosk={kiosk} onBack={home} onCode={(code) => checkIn(code)} />;
    case "face":
      return <Face kiosk={kiosk} pass={screen.pass} onBack={home} onCapture={(photo) => checkIn(screen.code, photo)} />;
    case "result":
      return <Result kiosk={kiosk} outcome={screen.outcome} onDone={home} />;
  }
}
