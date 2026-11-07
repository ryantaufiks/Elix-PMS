"use client";

import { useEffect, useRef, useState } from "react";
import { Room, RoomEvent, Track, type RemoteTrack } from "livekit-client";

import type { LiveKitConnection } from "@/lib/types";

import { Icon } from "./icons";
import { Button, cx } from "./ui";

/** Joins the LiveKit room: shows the kiosk's video, sends the guard's microphone (camera optional). */
export function VideoCall({ connection, onEnded }: { connection: LiveKitConnection; onEnded: () => void }) {
  const video = useRef<HTMLVideoElement>(null);
  const audio = useRef<HTMLDivElement>(null);
  const [room] = useState(() => new Room({ adaptiveStream: true, dynacast: true }));
  const [state, setState] = useState<"connecting" | "connected" | "failed">("connecting");
  const [hasVideo, setHasVideo] = useState(false);
  const [mic, setMic] = useState(true);
  const [camera, setCamera] = useState(false);
  const ended = useRef(onEnded);
  ended.current = onEnded;

  useEffect(() => {
    const attach = (track: RemoteTrack) => {
      if (track.kind === Track.Kind.Video && video.current) {
        track.attach(video.current);
        setHasVideo(true);
      } else if (track.kind === Track.Kind.Audio && audio.current) {
        audio.current.appendChild(track.attach());
      }
    };
    room
      .on(RoomEvent.TrackSubscribed, attach)
      .on(RoomEvent.TrackUnsubscribed, (track) => {
        track.detach().forEach((el) => el !== video.current && el.remove());
        if (track.kind === Track.Kind.Video) setHasVideo(false);
      })
      .on(RoomEvent.Disconnected, () => ended.current());

    let cancelled = false;
    room
      .connect(connection.url, connection.token)
      .then(async () => {
        if (cancelled) return;
        setState("connected");
        room.remoteParticipants.forEach((p) => p.trackPublications.forEach((pub) => pub.track && attach(pub.track as RemoteTrack)));
        await room.localParticipant.setMicrophoneEnabled(true).catch(() => setMic(false));
      })
      .catch(() => !cancelled && setState("failed"));
    return () => {
      cancelled = true;
      room.removeAllListeners();
      room.disconnect();
    };
  }, [room, connection.url, connection.token]);

  async function toggleMic() {
    await room.localParticipant.setMicrophoneEnabled(!mic);
    setMic(!mic);
  }
  async function toggleCamera() {
    await room.localParticipant.setCameraEnabled(!camera);
    setCamera(!camera);
  }

  return (
    <div className="overflow-hidden rounded-xl bg-slate-900">
      <div className="relative aspect-video">
        <video ref={video} autoPlay playsInline className={cx("h-full w-full object-cover", !hasVideo && "invisible")} />
        {!hasVideo && (
          <div className="absolute inset-0 flex items-center justify-center text-sm text-slate-300">
            {state === "connecting" ? "Connecting…" : state === "failed" ? "Could not connect to the video room." : "Waiting for the kiosk camera…"}
          </div>
        )}
        <div ref={audio} hidden />
      </div>
      <div className="flex items-center justify-center gap-2 p-3">
        <Button size="sm" variant={mic ? "secondary" : "danger"} onClick={toggleMic} disabled={state !== "connected"}>
          <Icon name="mic" className="h-4 w-4" /> {mic ? "Mute" : "Unmute"}
        </Button>
        <Button size="sm" variant="secondary" onClick={toggleCamera} disabled={state !== "connected"}>
          <Icon name="video" className="h-4 w-4" /> {camera ? "Stop camera" : "Show my camera"}
        </Button>
      </div>
    </div>
  );
}
