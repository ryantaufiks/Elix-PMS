// Copies the face-api.js models the kiosk uses (detector, landmarks, recognition) into public/models/face,
// so they are served from our own origin. Runs before every build.
import { copyFileSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const from = join(root, "node_modules/@vladmandic/face-api/model");
const to = join(root, "public/models/face");
mkdirSync(to, { recursive: true });
for (const name of ["ssd_mobilenetv1_model", "face_landmark_68_model", "face_recognition_model"]) {
  for (const ext of ["-weights_manifest.json", ".bin"]) copyFileSync(join(from, name + ext), join(to, name + ext));
}
