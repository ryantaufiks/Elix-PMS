"use client";

// Web kiosk for a tablet at the gate: call a resident (LiveKit video) or check in with an invitation QR.
import { useCallback, useEffect, useRef, useState } from "react";
import jsQR from "jsqr";
import { Room, RoomEvent, Track, type RemoteTrack } from "livekit-client";

import { ApiError, wsUrl } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import {
  type CheckInResult, type DirectoryUnit, kioskApi, type KioskSelf, kioskToken, PURPOSES, type VisitorDetails, type VisitorLookup,
  type VisitorPass,
} from "@/lib/kiosk";
import type { IntercomCall, LiveKitConnection } from "@/lib/types";

type Outcome = { tone: "good" | "bad" | "info"; title: string; detail?: string };
type Screen =
  | { name: "setup" }
  | { name: "home" }
  | { name: "directory" }
  | { name: "identify"; unit: DirectoryUnit }
  | { name: "details"; unit: DirectoryUnit; details: VisitorDetails }
  | { name: "photo"; unit: DirectoryUnit; details: VisitorDetails }
  | { name: "calling"; unit: DirectoryUnit; details: VisitorDetails }
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
      {onBack && (
        <footer className="px-8 pb-8">
          <button onClick={onBack} className="rounded-xl border border-white/15 px-6 py-3 text-lg text-slate-300 hover:bg-white/5">← Back</button>
        </footer>
      )}
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

function Home({ kiosk, onCall, onScan, onAdmin }: { kiosk: KioskSelf; onCall: () => void; onScan: () => void; onAdmin: () => void }) {
  const taps = useRef<number[]>([]);
  return (
    <Frame kiosk={kiosk}>
      <h1 className="text-center text-4xl font-semibold tracking-tight sm:text-5xl">Welcome</h1>
      <p className="mt-3 text-center text-lg text-slate-300">How would you like to enter{kiosk.gate_name ? ` through ${kiosk.gate_name}` : ""}?</p>
      <div className="mt-12 grid w-full max-w-3xl gap-6 sm:grid-cols-2">
        <button onClick={onCall} className="group rounded-3xl border border-white/10 bg-white/5 p-8 text-left transition hover:border-primary-400/60 hover:bg-white/10">
          <div className="mb-6 flex h-16 w-16 items-center justify-center rounded-2xl bg-primary-500 shadow-primary">
            <svg viewBox="0 0 24 24" className="h-8 w-8" fill="none" stroke="currentColor" strokeWidth={1.8}><path d="M5 4h4l2 5-2.5 1.5a11 11 0 0 0 5 5L15 13l5 2v4a2 2 0 0 1-2 2A16 16 0 0 1 3 6a2 2 0 0 1 2-2Z" /></svg>
          </div>
          <div className="text-2xl font-semibold">Call a resident</div>
          <div className="mt-2 text-slate-400">Video call the unit you are visiting.</div>
        </button>
        <button onClick={onScan} className="group rounded-3xl border border-white/10 bg-white/5 p-8 text-left transition hover:border-primary-400/60 hover:bg-white/10">
          <div className="mb-6 flex h-16 w-16 items-center justify-center rounded-2xl bg-white/10">
            <svg viewBox="0 0 24 24" className="h-8 w-8" fill="none" stroke="currentColor" strokeWidth={1.8}><path d="M4 4h6v6H4zM14 4h6v6h-6zM4 14h6v6H4zM14 14h2v2h-2zM18 14h2v2h-2zM14 18h2v2h-2zM18 18h2v2h-2z" /></svg>
          </div>
          <div className="text-2xl font-semibold">I have an invitation</div>
          <div className="mt-2 text-slate-400">Show the QR code from your invitation.</div>
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

function Directory({ kiosk, onPick, onBack }: { kiosk: KioskSelf; onPick: (unit: DirectoryUnit) => void; onBack: () => void }) {
  const [q, setQ] = useState("");
  const [units, setUnits] = useState<DirectoryUnit[] | null>(null);
  useEffect(() => {
    const id = setTimeout(() => {
      kioskApi<DirectoryUnit[]>(`/v1/kiosk/directory/?q=${encodeURIComponent(q)}`).then(setUnits).catch(() => setUnits([]));
    }, 250);
    return () => clearTimeout(id);
  }, [q]);
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
function Details({ kiosk, unit, initial, onNext, onBack }: {
  kiosk: KioskSelf; unit: DirectoryUnit; initial: VisitorDetails; onNext: (d: VisitorDetails) => void; onBack: () => void;
}) {
  const [d, setD] = useState(initial);
  const set = (patch: Partial<VisitorDetails>) => setD((cur) => ({ ...cur, ...patch }));
  const purpose = PURPOSES.find((p) => p.value === d.purpose);
  const finalStep = !kiosk.photo_required;
  const ready = (d.ref || d.name.trim()) && d.purpose;
  return (
    <Frame kiosk={kiosk} onBack={onBack}>
      <div className="w-full max-w-4xl">
        <h1 className="text-3xl font-semibold">{d.ref ? `Hi ${d.maskedName}` : "Tell the resident who you are"}</h1>
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
            {finalStep ? "Agree & call" : "Next: photo"}
          </BigButton>
        </div>
      </div>
    </Frame>
  );
}

/** Explicit photo with preview and retake, then the privacy notice and consent. */
function PhotoConsent({ kiosk, onNext, onBack }: { kiosk: KioskSelf; onNext: (photo: Blob) => void; onBack: () => void }) {
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
          <p className="mt-2 text-lg text-slate-300">The resident sees it before answering.</p>
          <div className="mt-6"><Notice kiosk={kiosk} /></div>
          <div className="mt-8 flex flex-wrap gap-4">
            {photo ? (
              <>
                <BigButton tone="ghost" onClick={() => setPhoto(null)}>Retake</BigButton>
                <BigButton onClick={() => onNext(photo.blob)}>Agree &amp; call</BigButton>
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
      <h1 className="text-3xl font-semibold">Show your invitation QR code</h1>
      <p className="mt-2 text-lg text-slate-300">Hold your phone up to the camera.</p>
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
          onCall={() => { document.documentElement.requestFullscreen?.().catch(() => {}); setScreen({ name: "directory" }); }}
          onScan={() => { document.documentElement.requestFullscreen?.().catch(() => {}); setScreen({ name: "scan" }); }}
          onAdmin={() => { if (window.confirm("Sign this kiosk out?")) { kioskToken.clear(); setKiosk(null); setScreen({ name: "setup" }); } }} />
      );
    case "directory":
      return <Directory kiosk={kiosk} onBack={home} onPick={(unit) => {
        if (kiosk.visitor_form) setScreen({ name: "identify", unit });
        else if (kiosk.photo_required) setScreen({ name: "photo", unit, details: { ...emptyDetails(), consent: true } });
        else setScreen({ name: "calling", unit, details: emptyDetails() });
      }} />;
    case "identify":
      return <Identify kiosk={kiosk} onBack={() => setScreen({ name: "directory" })}
        onBlocked={() => setScreen({ name: "result", outcome: { tone: "bad", title: "Please see the guardhouse", detail: "The security team will help you." } })}
        onFound={(details) => setScreen({ name: "details", unit: screen.unit, details })}
        onNew={(details) => setScreen({ name: "details", unit: screen.unit, details })} />;
    case "details":
      return <Details kiosk={kiosk} unit={screen.unit} initial={screen.details} onBack={() => setScreen({ name: "identify", unit: screen.unit })}
        onNext={(details) => setScreen(kiosk.photo_required ? { name: "photo", unit: screen.unit, details } : { name: "calling", unit: screen.unit, details })} />;
    case "photo":
      return <PhotoConsent kiosk={kiosk} onBack={() => setScreen(kiosk.visitor_form ? { name: "details", unit: screen.unit, details: screen.details } : { name: "directory" })}
        onNext={(photo) => setScreen({ name: "calling", unit: screen.unit, details: { ...screen.details, photo, consent: true } })} />;
    case "calling":
      return <Calling kiosk={kiosk} unit={screen.unit} details={screen.details} onDone={(outcome) => setScreen({ name: "result", outcome })} />;
    case "scan":
      return <Scan kiosk={kiosk} onBack={home} onCode={(code) => checkIn(code)} />;
    case "face":
      return <Face kiosk={kiosk} pass={screen.pass} onBack={home} onCapture={(photo) => checkIn(screen.code, photo)} />;
    case "result":
      return <Result kiosk={kiosk} outcome={screen.outcome} onDone={home} />;
  }
}
