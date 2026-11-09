"use client";

// The kiosk AI assistant. Speech-to-text mode records what the visitor says, sends it to the server and
// plays back the spoken answer; realtime mode talks to OpenAI over WebRTC with a one-minute client
// secret from the server. The conversation lives only in this component's memory.
import { useCallback, useEffect, useRef, useState } from "react";

import { Icon } from "@/components/icons";
import { type KioskAssistant, kioskApi, kioskBlob, PURPOSES } from "@/lib/kiosk";
import type { AssistantAction } from "@/lib/types";

type Phase = "starting" | "listening" | "hearing" | "thinking" | "speaking" | "idle" | "ended" | "error";
type Line = { role: "user" | "assistant"; content: string };

const SILENCE_MS = 1200;   // Pause that ends what the visitor is saying.
const WAIT_MS = 8000;      // No speech for this long: stop listening until they tap.
const LONGEST_MS = 15000;  // Longest single recording.
const IDLE_CLOSE_MS = 45000;

const clip = (v: unknown) => (typeof v === "string" ? v.trim().slice(0, 100) : "");

/** A tool call from the model, checked before the kiosk acts on it (realtime calls come straight from OpenAI). */
export function parseAction(name: string, raw: string, mapIds: number[]): AssistantAction | null {
  let args: Record<string, unknown>;
  try {
    args = JSON.parse(raw || "{}");
  } catch {
    return null;
  }
  if (!args || typeof args !== "object") return null;
  if (name === "show_map" && typeof args.map_id === "number" && mapIds.includes(args.map_id)) return { type: "show_map", map_id: args.map_id };
  if (name === "start_walk_in" && clip(args.unit)) {
    const purpose = PURPOSES.some((p) => p.value === args.purpose) ? String(args.purpose) : "";
    return { type: "start_walk_in", unit: clip(args.unit), visitor_name: clip(args.visitor_name), company: clip(args.company), purpose };
  }
  if (name === "call_resident" && clip(args.unit)) return { type: "call_resident", unit: clip(args.unit) };
  if (name === "open_screen" && (args.screen === "invitation" || args.screen === "checkout")) return { type: "open_screen", screen: args.screen };
  if (name === "end_conversation") return { type: "end_conversation" };
  return null;
}

/** Plays a spoken answer from its link. It streams, so playback starts while the rest is still being made. */
function playSpeech(url: string, audio: HTMLAudioElement): Promise<void> {
  if (!url) return Promise.resolve();
  audio.srcObject = null;
  audio.src = url;
  return new Promise((resolve) => {
    audio.onended = () => resolve();
    audio.onerror = () => resolve();
    audio.play().catch(() => resolve());
  });
}

/** Records one utterance: starts on speech, stops after a pause. Resolves null when nobody spoke. */
function recordUtterance(stream: MediaStream, onHearing: () => void, cancel: { current: boolean }): Promise<Blob | null> {
  return new Promise((resolve) => {
    const context = new AudioContext();
    const analyser = context.createAnalyser();
    analyser.fftSize = 1024;
    context.createMediaStreamSource(stream).connect(analyser);
    const samples = new Float32Array(analyser.fftSize);
    const type = MediaRecorder.isTypeSupported("audio/webm;codecs=opus") ? "audio/webm;codecs=opus" : "audio/webm";
    const recorder = new MediaRecorder(stream, { mimeType: type });
    const chunks: Blob[] = [];
    recorder.ondataavailable = (e) => e.data.size && chunks.push(e.data);
    const started = performance.now();
    let floor = 0.01, spoke = 0, lastVoice = 0, calibrated = 0;
    const finish = (keep: boolean) => {
      clearInterval(timer);
      const done = () => { context.close().catch(() => {}); resolve(keep && chunks.length ? new Blob(chunks, { type }) : null); };
      if (recorder.state === "inactive") return done();
      recorder.onstop = done;
      recorder.stop();
    };
    recorder.start(250);
    const timer = window.setInterval(() => {
      if (cancel.current) return finish(false);
      analyser.getFloatTimeDomainData(samples);
      const rms = Math.sqrt(samples.reduce((sum, x) => sum + x * x, 0) / samples.length);
      const now = performance.now();
      if (now - started < 300) { floor = Math.max(floor, rms); calibrated = now; return; }  // Room noise.
      const voice = rms > Math.max(0.02, floor * 2.5);
      if (voice) {
        if (!spoke) { spoke = now; onHearing(); }
        lastVoice = now;
      }
      if (spoke && now - lastVoice > SILENCE_MS) return finish(true);
      if (!spoke && now - calibrated > WAIT_MS) return finish(false);
      if (now - started > LONGEST_MS) return finish(!!spoke);
    }, 100);
  });
}

export function AssistantPanel({ info, onAction, onClose }: {
  info: KioskAssistant;
  /** Kiosk screens the assistant may open (walk-in, call, scan, check-out). */
  onAction: (action: AssistantAction) => void;
  onClose: () => void;
}) {
  const [phase, setPhase] = useState<Phase>("starting");
  const [mode, setMode] = useState<"pipeline" | "realtime">("pipeline");
  // Latest callbacks for the recording loop and WebRTC handlers, which outlive a render.
  const props = useRef({ onAction, onClose });
  props.current = { onAction, onClose };
  const turnRef = useRef<(input: { audio?: Blob; text?: string }) => Promise<void>>(async () => {});
  const [lines, setLines] = useState<Line[]>([]);
  const [map, setMap] = useState<{ id: number; url: string } | null>(null);
  const [typed, setTyped] = useState("");
  const [problem, setProblem] = useState("");
  const session = useRef<number | null>(null);
  const stream = useRef<MediaStream | null>(null);
  const audio = useRef<HTMLAudioElement | null>(null);
  const cancel = useRef(false);
  const linesRef = useRef<Line[]>([]);
  const pending = useRef<AssistantAction | null>(null);
  const realtime = useRef<{ pc: RTCPeerConnection; dc: RTCDataChannel } | null>(null);
  const lastActivity = useRef(Date.now());
  const busy = useRef(false);
  const scroller = useRef<HTMLDivElement>(null);
  const mapIds = info.maps.map((m) => m.id);

  const say = useCallback((line: Line) => {
    linesRef.current = [...linesRef.current, line];
    setLines(linesRef.current);
    lastActivity.current = Date.now();
  }, []);

  const showMap = useCallback(async (id: number) => {
    try {
      const url = URL.createObjectURL(await kioskBlob(`/v1/kiosk/assistant/maps/${id}/`));
      setMap((old) => { if (old) URL.revokeObjectURL(old.url); return { id, url }; });
    } catch { /* The answer still describes the way. */ }
  }, []);

  const finish = useCallback(() => {
    cancel.current = true;
    audio.current?.pause();
    realtime.current?.pc.close();
    realtime.current = null;
    stream.current?.getTracks().forEach((t) => t.stop());
    stream.current = null;
    if (session.current) kioskApi(`/v1/kiosk/assistant/sessions/${session.current}/end/`, { method: "POST" }).catch(() => {});
    session.current = null;
  }, []);

  /** After the assistant finished speaking: carry out a screen action it chose. */
  const settle = useCallback(() => {
    const action = pending.current;
    pending.current = null;
    if (!action) return false;
    finish();
    if (action.type === "end_conversation") props.current.onClose();
    else props.current.onAction(action);
    return true;
  }, [finish]);

  const act = useCallback((actions: AssistantAction[]) => {
    for (const a of actions) {
      if (a.type === "show_map") showMap(a.map_id);
      else if (!pending.current) pending.current = a;  // One screen at a time: the first one wins.
    }
  }, [showMap]);

  // --- Speech-to-text mode ---
  const listen = useCallback(async () => {
    if (!stream.current || busy.current || cancel.current) return;
    busy.current = true;
    setPhase("listening");
    const blob = await recordUtterance(stream.current, () => setPhase("hearing"), cancel);
    busy.current = false;
    if (cancel.current) return;
    if (!blob) return setPhase("idle");
    await turnRef.current({ audio: blob });
  }, []);

  const turn = useCallback(async (input: { audio?: Blob; text?: string }) => {
    if (!session.current) return;
    busy.current = true;
    setPhase("thinking");
    const form = new FormData();
    if (input.audio) form.set("audio", input.audio, "speech.webm");
    if (input.text) form.set("text", input.text);
    form.set("history", JSON.stringify(linesRef.current.slice(-12)));
    try {
      const r = await kioskApi<{ heard: string; reply: string; speech: string; actions: AssistantAction[] }>(
        `/v1/kiosk/assistant/sessions/${session.current}/turns/`, { method: "POST", body: form });
      busy.current = false;
      if (cancel.current) return;
      if (!r.heard) return setPhase("idle");
      say({ role: "user", content: r.heard });
      if (r.reply) say({ role: "assistant", content: r.reply });
      act(r.actions);
      setPhase("speaking");
      await playSpeech(r.speech, audio.current!);
      if (cancel.current || settle()) return;
      listen();
    } catch (err) {
      busy.current = false;
      setProblem((err as Error).message);
      setPhase("error");
    }
  }, [act, listen, say, settle]);
  turnRef.current = turn;

  // --- Realtime mode ---
  const connectRealtime = useCallback(async (secret: string, mic: MediaStream) => {
    const pc = new RTCPeerConnection();
    pc.ontrack = (e) => { if (audio.current) { audio.current.srcObject = e.streams[0]; audio.current.play().catch(() => {}); } };
    mic.getTracks().forEach((t) => pc.addTrack(t, mic));
    const dc = pc.createDataChannel("oai-events");
    realtime.current = { pc, dc };
    const send = (event: object) => dc.readyState === "open" && dc.send(JSON.stringify(event));
    dc.onopen = () => {
      send({ type: "response.create", response: { instructions: `Greet the visitor in one sentence, starting with: "${info.greeting || "Hello"}"` } });
    };
    dc.onmessage = (e) => {
      let event: { type: string; [k: string]: unknown };
      try { event = JSON.parse(e.data); } catch { return; }
      lastActivity.current = Date.now();
      switch (event.type) {
        case "input_audio_buffer.speech_started": setPhase("hearing"); break;
        case "input_audio_buffer.speech_stopped": setPhase("thinking"); break;
        case "output_audio_buffer.started": setPhase("speaking"); break;
        case "output_audio_buffer.stopped": if (!settle()) setPhase("listening"); break;
        case "conversation.item.input_audio_transcription.completed":
          if (typeof event.transcript === "string" && event.transcript.trim()) say({ role: "user", content: event.transcript.trim() });
          break;
        case "response.output_audio_transcript.done":
          if (typeof event.transcript === "string" && event.transcript.trim()) say({ role: "assistant", content: event.transcript.trim() });
          break;
        case "response.function_call_arguments.done": {
          const action = parseAction(String(event.name), String(event.arguments ?? ""), mapIds);
          if (action) act([action]);
          send({ type: "conversation.item.create", item: { type: "function_call_output", call_id: event.call_id, output: JSON.stringify({ done: !!action }) } });
          send({ type: "response.create" });
          break;
        }
        case "error": console.warn("Assistant:", event.error); break;
      }
    };
    const offer = await pc.createOffer();
    await pc.setLocalDescription(offer);
    const answer = await fetch("https://api.openai.com/v1/realtime/calls", {
      method: "POST", body: offer.sdp, headers: { Authorization: `Bearer ${secret}`, "Content-Type": "application/sdp" },
    });
    if (!answer.ok) throw new Error("The assistant could not connect.");
    await pc.setRemoteDescription({ type: "answer", sdp: await answer.text() });
    setPhase("listening");
  }, [act, info.greeting, mapIds, say, settle]);

  // Start: microphone, then the conversation.
  useEffect(() => {
    cancel.current = false;
    (async () => {
      try {
        stream.current = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true } });
        const r = await kioskApi<{ session: number; mode: string; greeting: string; greeting_speech: string; client_secret: string }>(
          "/v1/kiosk/assistant/sessions/", { method: "POST" });
        if (cancel.current) return finish();
        session.current = r.session;
        if (r.mode === "realtime") {
          setMode("realtime");
          return connectRealtime(r.client_secret, stream.current);
        }
        if (r.greeting) say({ role: "assistant", content: r.greeting });
        setPhase("speaking");
        await playSpeech(r.greeting_speech, audio.current!);
        listen();
      } catch (err) {
        setProblem(err instanceof DOMException ? "The microphone is not available." : (err as Error).message);
        setPhase("error");
      }
    })();
    return finish;
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Close when nobody talks for a while, and at the conversation's time limit.
  useEffect(() => {
    const opened = Date.now();
    const id = setInterval(() => {
      const quiet = Date.now() - lastActivity.current > IDLE_CLOSE_MS;
      const over = Date.now() - opened > info.max_session_seconds * 1000;
      if ((quiet && !busy.current) || over) { finish(); props.current.onClose(); }
    }, 2000);
    return () => clearInterval(id);
  }, [finish, info.max_session_seconds]);

  useEffect(() => { scroller.current?.scrollTo({ top: scroller.current.scrollHeight, behavior: "smooth" }); }, [lines]);
  useEffect(() => () => { if (map) URL.revokeObjectURL(map.url); }, [map]);

  const realtimeMode = mode === "realtime";
  const label: Record<Phase, string> = {
    starting: "Starting…", listening: "Listening… just speak", hearing: "I'm listening", thinking: "Thinking…",
    speaking: "Speaking", idle: "Tap the microphone to talk", ended: "Goodbye", error: problem || "Something went wrong",
  };
  const active = phase === "hearing" || phase === "speaking";

  return (
    <div className="flex w-full max-w-6xl flex-1 flex-col gap-6 lg:flex-row" onPointerDown={() => { lastActivity.current = Date.now(); }}>
      <audio ref={audio} hidden />
      <section className="flex min-h-0 flex-1 flex-col">
        <div className="flex items-center gap-4">
          <div className="relative flex h-24 w-24 shrink-0 items-center justify-center">
            <span className={`absolute inset-0 rounded-full bg-primary-500/30 ${active ? "animate-ping" : ""}`} />
            <span className={`absolute inset-2 rounded-full bg-gradient-to-br from-primary-400 to-cyan-400 shadow-[0_0_40px_rgba(47,140,255,0.6)] transition-transform ${phase === "speaking" ? "scale-110" : ""}`} />
            <Icon name="sparkle" className="relative h-10 w-10 text-white" />
          </div>
          <div>
            <h1 className="text-3xl font-semibold">{info.name}</h1>
            <p className={`mt-1 text-lg ${phase === "error" ? "text-rose-300" : "text-slate-300"}`}>{label[phase]}</p>
          </div>
        </div>

        <div ref={scroller} className="mt-6 max-h-[42vh] min-h-[180px] flex-1 space-y-3 overflow-y-auto rounded-3xl border border-white/10 bg-white/5 p-5">
          {lines.length === 0 && <p className="text-lg text-slate-400">Ask about directions, facilities, parking, deliveries, or registering your visit.</p>}
          {lines.map((l, i) => (
            <div key={i} className={l.role === "user" ? "flex justify-end" : ""}>
              <div className={`max-w-[85%] rounded-3xl px-5 py-3 text-xl ${l.role === "user" ? "rounded-br-md bg-primary-600 text-white" : "rounded-bl-md bg-white/10 text-white"}`}>{l.content}</div>
            </div>
          ))}
        </div>

        <div className="mt-5 flex items-center gap-3">
          {!realtimeMode && (
            <button aria-label="Talk" onClick={() => { cancel.current = false; listen(); }} disabled={phase !== "idle" && phase !== "error"}
              className="flex h-16 w-16 shrink-0 items-center justify-center rounded-full bg-primary-500 text-white shadow-primary disabled:opacity-40">
              <Icon name="mic" className="h-7 w-7" />
            </button>
          )}
          {!realtimeMode && (
            <form className="flex flex-1 gap-3" onSubmit={(e) => {
              e.preventDefault();
              const text = typed.trim();
              if (!text || phase === "thinking" || phase === "speaking" || phase === "starting") return;
              setTyped("");
              cancel.current = true;  // Stop listening; the typed question goes instead.
              setTimeout(() => { cancel.current = false; turn({ text }); }, 150);
            }}>
              <input value={typed} onChange={(e) => setTyped(e.target.value)} placeholder="Or type your question"
                className="w-full rounded-2xl border border-white/20 bg-navy-950/60 px-5 py-4 text-xl text-white placeholder:text-slate-500 focus:border-primary-400 focus:outline-none" />
              <button type="submit" aria-label="Send" className="rounded-2xl bg-white/10 px-5 text-white hover:bg-white/20"><Icon name="send" className="h-6 w-6" /></button>
            </form>
          )}
          <button onClick={() => { finish(); onClose(); }} className="ml-auto rounded-2xl border border-white/15 px-6 py-4 text-lg text-slate-300 hover:bg-white/5">Close</button>
        </div>
        <p className="mt-3 text-sm text-slate-500">Answers come from an AI (OpenAI) and may be imperfect. Your voice is processed only to answer you; the conversation is not stored.</p>
      </section>

      {map && (
        <aside className="flex flex-col overflow-hidden rounded-3xl border border-white/10 bg-white lg:w-[46%]">
          <div className="flex items-center justify-between bg-navy-950 px-5 py-3 text-white">
            <span className="text-lg font-medium">{info.maps.find((m) => m.id === map.id)?.name ?? "Map"}</span>
            <button onClick={() => setMap(null)} className="rounded-lg px-3 py-1 text-slate-300 hover:bg-white/10" aria-label="Hide map">✕</button>
          </div>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={map.url} alt="Map" className="max-h-[60vh] w-full flex-1 object-contain" />
        </aside>
      )}
    </div>
  );
}
