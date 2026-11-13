"use client";

import { useEffect, useState } from "react";

import { AuthImage, CallStatusBadge } from "./bits";
import { SwipeToUnlock } from "./SwipeToUnlock";
import { VideoCall } from "./VideoCall";
import { Button, Card, useToast } from "./ui";
import { api, ApiError } from "@/lib/api";
import { visitPurpose } from "@/lib/format";
import type { IntercomCall, LiveKitConnection } from "@/lib/types";

function useElapsed(since: string) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);
  const seconds = Math.max(0, Math.round((now - new Date(since).getTime()) / 1000));
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}

/** One open kiosk call: snapshot or live video, swipe to open the gate, answer / reject / hang up.
    Used on the Intercom page and in the incoming-call pop-up. */
export function ActiveCall({ call, connection, onAnswered, onDone }: {
  call: IntercomCall;
  connection?: LiveKitConnection;
  onAnswered: (c: LiveKitConnection) => void;
  onDone: () => void;
}) {
  const toast = useToast();
  const elapsed = useElapsed(call.created_at);
  const [busy, setBusy] = useState<"answer" | "reject" | "hangup" | null>(null);

  async function act<T>(name: "answer" | "reject" | "hangup", fn: () => Promise<T>) {
    setBusy(name);
    try {
      return await fn();
    } catch (error) {
      const message = error instanceof ApiError && error.status === 503
        ? "Video intercom is not configured yet. You can still open the gate."
        : (error as Error).message;
      toast("error", message);
    } finally {
      setBusy(null);
    }
  }

  const answer = () => act("answer", async () => {
    const result = await api<{ call: IntercomCall; livekit: LiveKitConnection }>(`/v1/intercom-calls/${call.id}/answer/`, { method: "POST" });
    onAnswered(result.livekit);
  });
  const reject = () => act("reject", async () => {
    await api(`/v1/intercom-calls/${call.id}/reject/`, { method: "POST" });
    toast("info", "Call rejected.");
    onDone();
  });
  const hangup = () => act("hangup", async () => {
    await api(`/v1/intercom-calls/${call.id}/hangup/`, { method: "POST" });
    onDone();
  });
  const unlock = async () => {
    try {
      await api(`/v1/intercom-calls/${call.id}/unlock/`, { method: "POST" });
      toast("success", "Gate opening. Visitor approved.");
      onDone();
    } catch (error) {
      toast("error", (error as Error).message);
    }
  };

  return (
    <Card className="overflow-hidden">
      <div className="flex items-start justify-between gap-3 border-b border-line px-4 py-3">
        <div>
          <div className="text-base font-semibold text-ink">{call.unit === null ? "Call to the guardhouse" : call.unit_display}</div>
          <div className="text-sm text-muted">{call.kiosk_name || "Kiosk"} · {elapsed}</div>
          <div className="mt-1 text-sm font-medium text-ink">{call.visitor_name || "Visitor"}</div>
          {visitPurpose(call.visitor_purpose, call.visitor_company) && <div className="text-sm text-body">{visitPurpose(call.visitor_purpose, call.visitor_company)}</div>}
          {call.visitor_phone && <div className="text-sm text-muted">{call.visitor_phone}</div>}
        </div>
        <CallStatusBadge status={call.status} />
      </div>
      <div className="space-y-4 p-4">
        {connection ? (
          <VideoCall connection={connection} onEnded={onDone} />
        ) : call.has_snapshot ? (
          <AuthImage path={`/v1/intercom-calls/${call.id}/snapshot/`} alt="Visitor at the kiosk" className="aspect-video w-full rounded-xl object-cover" />
        ) : (
          <div className="flex aspect-video items-center justify-center rounded-xl bg-surface-3 text-sm text-muted">{call.unit === null ? "Answer to see who is at the kiosk" : "No snapshot"}</div>
        )}
        <SwipeToUnlock onUnlock={unlock} />
        <div className="flex flex-wrap gap-2">
          {!connection && call.status === "ringing" && (
            <Button variant="primary" className="flex-1" busy={busy === "answer"} onClick={answer}>Answer with video</Button>
          )}
          <Button variant="danger" className="flex-1" busy={busy === "reject"} onClick={reject}>Reject</Button>
          {connection && <Button className="flex-1" busy={busy === "hangup"} onClick={hangup}>Hang up</Button>}
        </div>
      </div>
    </Card>
  );
}
