// Face templates for kiosk face check-out, computed in the kiosk's browser with face-api.js
// (SSD MobileNet detector, 68-point landmarks, 128-d recognition net). Only the 128 numbers are
// sent to the server; matching happens there against the visitors on site.
type FaceApi = typeof import("@vladmandic/face-api");

let loading: Promise<FaceApi> | null = null;

/** Load the library and models once (call early so the first check-out is quick). */
export function loadFace(): Promise<FaceApi> {
  loading ??= (async () => {
    const faceapi = await import("@vladmandic/face-api");
    const url = "/models/face";
    await Promise.all([
      faceapi.nets.ssdMobilenetv1.loadFromUri(url),
      faceapi.nets.faceLandmark68Net.loadFromUri(url),
      faceapi.nets.faceRecognitionNet.loadFromUri(url),
    ]);
    return faceapi;
  })().catch((err) => {
    loading = null;
    throw err;
  });
  return loading;
}

type Source = HTMLVideoElement | HTMLImageElement | HTMLCanvasElement;

/** Smallest face (pixels wide) worth matching: smaller ones are too far from the camera. */
const MIN_FACE = 90;

/** The template of the one clear face in ``source``, or null (no face, several faces, too small or unsure). */
export async function describe(source: Source): Promise<number[] | null> {
  const faceapi = await loadFace();
  const options = new faceapi.SsdMobilenetv1Options({ minConfidence: 0.6 });
  const faces = await faceapi.detectAllFaces(source, options).withFaceLandmarks().withFaceDescriptors();
  if (faces.length === 0) return null;
  // The visitor in front of the kiosk is the biggest face; refuse when two are equally close.
  faces.sort((a, b) => b.detection.box.area - a.detection.box.area);
  const [main, next] = faces;
  if (main.detection.score < 0.8 || main.detection.box.width < MIN_FACE) return null;
  if (next && next.detection.box.area > main.detection.box.area * 0.6) return null;
  return Array.from(main.descriptor);
}

/** Template of a photo the kiosk took (JPEG blob). */
export async function describePhoto(photo: Blob): Promise<number[] | null> {
  const url = URL.createObjectURL(photo);
  try {
    const img = new Image();
    img.src = url;
    await img.decode();
    return await describe(img);
  } finally {
    URL.revokeObjectURL(url);
  }
}

/** A steadier template from live video: the average of a few frames that each show one clear face. */
export async function describeLive(video: HTMLVideoElement, frames = 3, timeoutMs = 6000): Promise<number[] | null> {
  const found: number[][] = [];
  const until = Date.now() + timeoutMs;
  while (found.length < frames && Date.now() < until) {
    const d = await describe(video).catch(() => null);
    if (d) found.push(d);
    else await new Promise((r) => setTimeout(r, 150));
  }
  if (!found.length) return null;
  const mean = found[0].map((_, i) => found.reduce((s, d) => s + d[i], 0) / found.length);
  const norm = Math.hypot(...mean) || 1;
  const scale = Math.hypot(...found[0]) / norm; // Keep the recognition net's scale (its vectors are ~unit length).
  return mean.map((x) => x * scale);
}
