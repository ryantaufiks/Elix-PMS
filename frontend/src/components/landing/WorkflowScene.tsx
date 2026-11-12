"use client";

import { useEffect, useRef } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";

/** The steps of one journey as glowing tiles on a curve; a light travels to the active step.
    Click a tile to jump to it, drag to turn the scene. Loaded only on the landing page. */
export default function WorkflowScene({ labels, step, onPick, onUnsupported }: {
  labels: string[]; step: number; onPick: (i: number) => void; onUnsupported: () => void;
}) {
  const box = useRef<HTMLDivElement>(null);
  const stepRef = useRef(step);
  const pickRef = useRef(onPick);
  stepRef.current = step;
  pickRef.current = onPick;

  useEffect(() => {
    const el = box.current;
    if (!el) return;
    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    } catch {
      onUnsupported();
      return;
    }
    const still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    el.appendChild(renderer.domElement);
    renderer.domElement.style.cursor = "grab";

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(38, 1, 0.1, 100);
    camera.position.set(0, 2.6, 12);
    const controls = new OrbitControls(camera, renderer.domElement);
    Object.assign(controls, {
      enableZoom: false, enablePan: false, enableDamping: true, dampingFactor: 0.08,
      minPolarAngle: Math.PI * 0.32, maxPolarAngle: Math.PI * 0.55,
      minAzimuthAngle: -0.7, maxAzimuthAngle: 0.7, autoRotate: !still, autoRotateSpeed: 0.35,
    });

    scene.add(new THREE.AmbientLight(0x8fb8ff, 0.7));
    const key = new THREE.DirectionalLight(0xffffff, 1.4);
    key.position.set(3, 6, 8);
    scene.add(key);

    const disposables: { dispose: () => void }[] = [];
    const keep = <T extends { dispose: () => void }>(x: T) => { disposables.push(x); return x; };

    // Floor grid and a field of faint points, like the login page's grid.
    const grid = new THREE.GridHelper(40, 40, 0x1b2c55, 0x1b2c55);
    grid.position.y = -1.8;
    (grid.material as THREE.Material).transparent = true;
    (grid.material as THREE.Material).opacity = 0.55;
    keep(grid.geometry); keep(grid.material as THREE.Material);
    scene.add(grid);
    const dots = keep(new THREE.BufferGeometry());
    const pts = new Float32Array(600 * 3).map((_, i) => (i % 3 === 1 ? Math.random() * 8 - 2 : (Math.random() - 0.5) * 30));
    dots.setAttribute("position", new THREE.BufferAttribute(pts, 3));
    scene.add(new THREE.Points(dots, keep(new THREE.PointsMaterial({ color: 0x5b93ff, size: 0.04, transparent: true, opacity: 0.6 }))));

    // Steps along a gentle wave.
    const n = labels.length;
    const width = Math.min(10, 2.2 * (n - 1));
    const positions = labels.map((_, i) => new THREE.Vector3(
      n === 1 ? 0 : -width / 2 + (width * i) / (n - 1), Math.sin(i * 1.1) * 0.55, Math.cos(i * 1.4) * 0.9 - 0.4));
    const tileGeo = keep(new THREE.CylinderGeometry(0.62, 0.62, 0.2, 6));
    const haloGeo = keep(new THREE.TorusGeometry(0.85, 0.035, 8, 48));
    const tiles: THREE.Mesh[] = [];
    const halos: THREE.Mesh[] = [];
    const labelSprites: THREE.Sprite[] = [];
    positions.forEach((p, i) => {
      const tile = new THREE.Mesh(tileGeo, keep(new THREE.MeshStandardMaterial({
        color: 0x111f42, emissive: 0x2f6fff, emissiveIntensity: 0.25, metalness: 0.4, roughness: 0.35,
      })));
      tile.rotation.x = Math.PI / 2;
      tile.position.copy(p);
      tile.userData.index = i;
      scene.add(tile);
      tiles.push(tile);
      const halo = new THREE.Mesh(haloGeo, keep(new THREE.MeshBasicMaterial({ color: 0x5b93ff, transparent: true, opacity: 0 })));
      halo.position.copy(p);
      scene.add(halo);
      halos.push(halo);
      // Number and short label above the tile.
      const canvas = document.createElement("canvas");
      canvas.width = 512; canvas.height = 160;
      const ctx = canvas.getContext("2d")!;
      ctx.fillStyle = "#8fb8ff";
      ctx.font = "600 44px system-ui, -apple-system, Segoe UI, sans-serif";
      ctx.textAlign = "center";
      ctx.fillText(String(i + 1), 256, 52);
      ctx.fillStyle = "#ffffff";
      ctx.font = "600 40px system-ui, -apple-system, Segoe UI, sans-serif";
      ctx.fillText(labels[i], 256, 120, 500);
      const texture = keep(new THREE.CanvasTexture(canvas));
      texture.colorSpace = THREE.SRGBColorSpace;
      const sprite = new THREE.Sprite(keep(new THREE.SpriteMaterial({ map: texture, transparent: true })));
      sprite.scale.set(2.4, 0.75, 1);
      sprite.position.set(p.x, p.y + 1.15, p.z);
      scene.add(sprite);
      labelSprites.push(sprite);
    });

    const curve = new THREE.CatmullRomCurve3(positions.length > 1 ? positions : [positions[0], positions[0].clone().add(new THREE.Vector3(0.01, 0, 0))]);
    scene.add(new THREE.Mesh(keep(new THREE.TubeGeometry(curve, 240, 0.03, 8)),
      keep(new THREE.MeshBasicMaterial({ color: 0x2f6fff, transparent: true, opacity: 0.55 }))));
    const packet = new THREE.Mesh(keep(new THREE.SphereGeometry(0.13, 24, 16)), keep(new THREE.MeshBasicMaterial({ color: 0x9be7ff })));
    const glow = new THREE.PointLight(0x7fd4ff, 6, 4);
    packet.add(glow);
    scene.add(packet);

    // Size to the box.
    const resize = () => {
      const w = el.clientWidth, h = el.clientHeight;
      renderer.setSize(w, h);
      camera.aspect = w / Math.max(1, h);
      // Step back just far enough that every tile (and its label) stays in view while the scene turns.
      const halfFov = Math.tan(THREE.MathUtils.degToRad(camera.fov / 2));
      const distance = Math.max(10, (width / 2 + 1.9) / (halfFov * camera.aspect));
      camera.position.setLength(distance);
      labelSprites.forEach((sprite) => sprite.scale.set(2.4 * distance / 13, 0.75 * distance / 13, 1));
      camera.updateProjectionMatrix();
    };
    const ro = new ResizeObserver(resize);
    ro.observe(el);
    resize();

    // Click a tile to jump to that step.
    const ray = new THREE.Raycaster();
    const pointer = new THREE.Vector2();
    let downAt = { x: 0, y: 0 };
    const down = (e: PointerEvent) => { downAt = { x: e.clientX, y: e.clientY }; renderer.domElement.style.cursor = "grabbing"; };
    const up = (e: PointerEvent) => {
      renderer.domElement.style.cursor = "grab";
      if (Math.hypot(e.clientX - downAt.x, e.clientY - downAt.y) > 6) return; // a drag, not a click
      const r = renderer.domElement.getBoundingClientRect();
      pointer.set(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
      ray.setFromCamera(pointer, camera);
      const hit = ray.intersectObjects(tiles)[0];
      if (hit) pickRef.current(hit.object.userData.index as number);
    };
    renderer.domElement.addEventListener("pointerdown", down);
    renderer.domElement.addEventListener("pointerup", up);

    // Draw only while on screen.
    let visible = true;
    const io = new IntersectionObserver(([entry]) => { visible = entry.isIntersecting; });
    io.observe(el);

    let param = 0;
    let frame = 0;
    const clock = new THREE.Clock();
    const loop = () => {
      frame = requestAnimationFrame(loop);
      const dt = Math.min(0.05, clock.getDelta());
      if (!visible) return;
      const active = Math.min(stepRef.current, n - 1);
      const target = n > 1 ? active / (n - 1) : 0;
      // Back to the start: jump instead of running backwards along the curve.
      if (target < param - 0.01) param = target;
      param = still ? target : param + (target - param) * Math.min(1, dt * 3.2);
      packet.position.copy(curve.getPoint(param));
      const t = clock.elapsedTime;
      tiles.forEach((tile, i) => {
        const on = i === active;
        const mat = tile.material as THREE.MeshStandardMaterial;
        mat.emissiveIntensity += ((on ? 1.1 : i < active ? 0.45 : 0.2) - mat.emissiveIntensity) * Math.min(1, dt * 6);
        tile.scale.setScalar(on && !still ? 1 + Math.sin(t * 4) * 0.04 : 1);
        const halo = halos[i];
        (halo.material as THREE.MeshBasicMaterial).opacity += ((on ? 0.8 : 0) - (halo.material as THREE.MeshBasicMaterial).opacity) * Math.min(1, dt * 6);
        halo.quaternion.copy(camera.quaternion);
      });
      controls.update();
      renderer.render(scene, camera);
    };
    loop();

    return () => {
      cancelAnimationFrame(frame);
      ro.disconnect();
      io.disconnect();
      renderer.domElement.removeEventListener("pointerdown", down);
      renderer.domElement.removeEventListener("pointerup", up);
      controls.dispose();
      disposables.forEach((d) => d.dispose());
      renderer.dispose();
      renderer.domElement.remove();
    };
  }, [labels, onUnsupported]);

  return <div ref={box} className="h-full w-full" aria-hidden="true" />;
}
