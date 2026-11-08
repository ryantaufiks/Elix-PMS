"use client";

// One WebSocket per tab to /ws/events/, fanned out to subscribers. Reconnects with backoff and
// refreshes the JWT first when it has expired.
import { createContext, useContext, useEffect, useRef, useState } from "react";

import { refreshAccess, tokens, wsUrl } from "./api";
import type { AccessLog, Booking, Feedback, IntercomCall, Visit } from "./types";

export type LiveEvent =
  | { type: "access_log"; data: AccessLog }
  | { type: "intercom_call"; data: IntercomCall }
  | { type: "visit"; data: Visit }
  | { type: "booking"; data: Booking }
  | { type: "feedback"; data: Feedback };
type Listener = (event: LiveEvent) => void;

const LiveContext = createContext<{ connected: boolean; listeners: Set<Listener> } | null>(null);

function expiresSoon(token: string): boolean {
  try {
    const { exp } = JSON.parse(atob(token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/")));
    return exp * 1000 < Date.now() + 30_000;
  } catch {
    return true;
  }
}

export function LiveProvider({ children }: { children: React.ReactNode }) {
  const [connected, setConnected] = useState(false);
  const listeners = useRef(new Set<Listener>()).current;

  useEffect(() => {
    let socket: WebSocket | null = null;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let attempt = 0;
    let stopped = false;

    async function connect() {
      let token = tokens.access();
      if (!token || expiresSoon(token)) {
        await refreshAccess();
        token = tokens.access();
      }
      if (stopped || !token) return;
      socket = new WebSocket(wsUrl(`/ws/events/?token=${encodeURIComponent(token)}`));
      socket.onopen = () => {
        attempt = 0;
        setConnected(true);
      };
      socket.onmessage = (message) => {
        try {
          const event = JSON.parse(message.data) as LiveEvent;
          listeners.forEach((listener) => listener(event));
        } catch {}
      };
      socket.onclose = () => {
        setConnected(false);
        if (stopped) return;
        attempt += 1;
        timer = setTimeout(connect, Math.min(30_000, 1000 * 2 ** Math.min(attempt, 5)));
      };
    }

    connect();
    return () => {
      stopped = true;
      clearTimeout(timer);
      socket?.close();
    };
  }, [listeners]);

  return <LiveContext.Provider value={{ connected, listeners }}>{children}</LiveContext.Provider>;
}

export function useLiveStatus(): boolean {
  return useContext(LiveContext)?.connected ?? false;
}

/** Calls ``handler`` for every live event; the latest handler is always used. */
export function useLiveEvents(handler: Listener) {
  const context = useContext(LiveContext);
  const ref = useRef(handler);
  ref.current = handler;
  useEffect(() => {
    if (!context) return;
    const listener: Listener = (event) => ref.current(event);
    context.listeners.add(listener);
    return () => {
      context.listeners.delete(listener);
    };
  }, [context]);
}
