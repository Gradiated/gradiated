'use strict';
gsap.registerPlugin(ScrollTrigger);

const TAU = Math.PI * 2;
const DEG = Math.PI / 180;
const clamp = (x, a, b) => Math.max(a, Math.min(b, x));
const lerp = (a, b, t) => a + (b - a) * t;
const smooth = (x) => { x = clamp(x, 0, 1); return x * x * (3 - 2 * x); };
const remap = (t, a, b) => clamp((t - a) / (b - a), 0, 1);

/* ------------------------------------------------------------------ */
/* 1. Profiles                                                         */
/*                                                                     */
/* A profile describes a closed surface by azimuth u (0..TAU) and      */
/* height fraction v (0..1) along its own axis, returning cylindrical  */
/* {r, y}. Every state of a part uses the same grid, so moving from    */
/* one state to the next is a per-vertex lerp.                         */
/* ------------------------------------------------------------------ */

function hexRadius(u) {
  const s = Math.PI / 3;
  const m = ((u % s) + s) % s;
  return Math.cos(Math.PI / 6) / Math.cos(m - Math.PI / 6);
}
// Hexagonal prism with a pyramid tip. J = height fraction where the tip starts (sits on a grid ring).
const hexPoint = (R, H, J) => (u, v) => ({ r: R * hexRadius(u) * (v < J ? 1 : (1 - v) / (1 - J)), y: H * v });
// Cylinder with flat ends and a small chamfer, one grid ring deep (ch = 1 / nV). The last ring
// sits at the full length so the top fan is flat rather than a shallow cone.
const cylinder = (R, L, ch = 0.04, k = 0.08, flat = 0) => (u, v) => {
  let r = R * (1 - k * Math.max(0, 1 - v / ch) - k * Math.max(0, 1 - (1 - ch - v) / ch));
  if (flat) { const a = Math.abs(((u - Math.PI) % TAU + TAU) % TAU - Math.PI); if (Math.cos(a) * R > flat) r = Math.min(r, flat / Math.cos(a)); }
  return { r, y: L * Math.min(v, 1 - ch) / (1 - ch) };
};
// Something to shrink into and vanish.
const stub = (u, v) => ({ r: 0.05, y: 0.08 * v });

/* ------------------------------------------------------------------ */
/* 2. Parts and their states, one state per paragraph                  */
/*                                                                     */
/* pose: x/y/z in model units (floor is y = 0), tilt/pitch/yaw in      */
/* degrees about the part's own z/x/y axes. choreo(t, A, B) overrides  */
/* the default pose/opacity lerp while entering that state.            */
/* ------------------------------------------------------------------ */

const POSE = (o) => Object.assign({ x: 0, y: 0, z: 0, tilt: 0, pitch: 0, yaw: 0, scale: 1 }, o);
const lerpPose = (a, b, t) => ({
  x: lerp(a.x, b.x, t), y: lerp(a.y, b.y, t), z: lerp(a.z, b.z, t),
  tilt: lerp(a.tilt, b.tilt, t), pitch: lerp(a.pitch, b.pitch, t), yaw: lerp(a.yaw, b.yaw, t),
  scale: lerp(a.scale, b.scale, t),
});

const INGOT = cylinder(0.75, 3.0);
const WAFER = cylinder(0.72, 0.1, 0.2, 0.04, 0.64);   // 0.64 = distance of the wafer flat from centre
const ZOOM = (100 / 84) / 0.1;   // magnification at which the wafer's thickness fills the slab's 100 units
const WAFER_PLAIN = cylinder(0.72, 0.1, 0.2, 0, 0.64);   // same wafer without the edge chamfer, for the zoom

const PARTS = [
  {
    name: 'main', nU: 48, nV: 25, shadow: 'body',
    // faint horizontal striations on the prism faces: ring j, columns i0..i1
    details: [{ j: 5, i0: 9, i1: 14 }, { j: 9, i0: 18, i1: 22 }, { j: 13, i0: 10, i1: 13 }, { j: 3, i0: 42, i1: 46 }],
    states: [
      { profile: hexPoint(0.6, 2.6, 0.72), pose: POSE({ x: -0.3, y: 0.35 }), detail: 1 },
      {
        profile: INGOT, pose: POSE({ x: 1.5, y: 1.35, tilt: 90 }), hatch: 1, sag: 0.8,
      },
      {
        profile: INGOT, pose: POSE({ x: -5.5, y: 1.35, tilt: 90 }), hatch: 1, opacity: 0,
        // the rest of the ingot slides off to the left once the slice is free
        choreo: (t, A, B) => ({
          pose: lerpPose(A.pose, B.pose, smooth(remap(t, 0.3, 0.72))),
          opacity: 1 - smooth(remap(t, 0.5, 0.74)),
        }),
      },
      { profile: INGOT, pose: POSE({ x: -5.5, y: 1.35, tilt: 90 }), opacity: 0 },
    ],
  },
  {
    name: 'branch', nU: 36, nV: 20, shadow: 'body',
    details: [{ j: 6, i0: 7, i1: 11 }],
    states: [
      { profile: hexPoint(0.4, 1.6, 0.7), pose: POSE({ x: -0.1, y: 0.8, tilt: -36 }), detail: 1 },
      {
        profile: stub, pose: POSE({ x: 0.6, y: 1.35, tilt: -36 }), opacity: 0, sag: 0.5,
        choreo: (t, A, B) => ({ pose: lerpPose(A.pose, B.pose, smooth(t)), opacity: 1 - smooth(remap(t, 0.4, 0.78)) }),
      },
      { profile: stub, pose: POSE({ x: 0.6, y: 1.35, tilt: -36 }), opacity: 0 },
      { profile: stub, pose: POSE({ x: 0.6, y: 1.35, tilt: -36 }), opacity: 0 },
    ],
  },
  {
    name: 'wafer', nU: 48, nV: 5, shadow: 'wafer',
    states: [
      { profile: WAFER, pose: POSE({ x: -0.3, y: 0.6 }), opacity: 0 },
      {
        // tucked just inside the right end of the ingot, so hidden-line removal hides it
        profile: WAFER, pose: POSE({ x: 1.47, y: 1.35, tilt: 90 }), opacity: 0,
        choreo: (t, A, B) => ({ pose: B.pose, opacity: 0 }),
      },
      {
        profile: WAFER, pose: POSE({ x: 0, y: 1.35, tilt: 90, yaw: 90 }), hatch: 0.5,
        // slide the slice free, wait for the ingot to leave, then glide to centre and turn to face us
        choreo: (t, A, B) => {
          const free = smooth(remap(t, 0, 0.28));
          const glide = smooth(remap(t, 0.62, 1));
          const mid = Object.assign({}, A.pose, { x: A.pose.x + 0.7 * free });
          // the slice only exists once this scene starts: it is fully inside the settled ingot
          // at t = 0, so hidden-line removal keeps it invisible until it slides free
          // its shadow is the only thing that could pop, so that fades in as the slice emerges
          return { pose: lerpPose(mid, B.pose, glide), opacity: 1, shadow: smooth(remap(t, 0.04, 0.3)) };
        },
      },
      {
        // hand-off: lay the wafer flat, level the camera to look exactly at its edge, then zoom in
        // until its thin rim fills the slab rectangle; the view crops to a small piece and the
        // 2D cross-section fades in exactly on top of it
        profile: WAFER_PLAIN, pose: POSE({ x: 0, y: (348 - 300) / 84, tilt: 0, yaw: 0, scale: ZOOM }), opacity: 0,
        morph: (t) => remap(t, 0, 0.3),   // lose the chamfer before the zoom would magnify it into stripes
        choreo: (t, A, B) => {
          const pose = lerpPose(A.pose, B.pose, smooth(remap(t, 0, 0.5)));
          pose.scale = Math.exp(Math.log(ZOOM) * smooth(remap(t, 0.3, 0.8)));   // geometric zoom
          return { pose, opacity: 1 - smooth(remap(t, 0.84, 0.96)) };
        },
      },
    ],
  },
];

for (const part of PARTS) for (const s of part.states) {
  if (s.hatch === undefined) s.hatch = 0;
  if (s.detail === undefined) s.detail = 0;
  if (s.opacity === undefined) s.opacity = 1;
  if (s.sag === undefined) s.sag = 0;
}
const N3D = PARTS[0].states.length;   // scenes with 3D content (the rest hold the last state)

/* ------------------------------------------------------------------ */
/* 3. Shared mesh: every part's grid lives in one global vertex list,  */
/*    so occlusion between parts falls out of the same test.           */
/* ------------------------------------------------------------------ */

let NVERT = 0;
for (const part of PARTS) {
  part.v0 = NVERT;
  part.nRing = part.nU * part.nV;
  part.iBase = NVERT + part.nRing;
  part.iApex = NVERT + part.nRing + 1;
  part.nVert = part.nRing + 2;
  NVERT += part.nVert;
}

const U = new Float64Array(NVERT), V = new Float64Array(NVERT);
const PART = new Uint8Array(NVERT);
PARTS.forEach((part, pi) => {
  for (let j = 0; j < part.nV; j++) for (let i = 0; i < part.nU; i++) {
    const n = part.v0 + j * part.nU + i;
    U[n] = TAU * i / part.nU; V[n] = j / part.nV; PART[n] = pi;
  }
  V[part.iBase] = 0; V[part.iApex] = 1; PART[part.iBase] = pi; PART[part.iApex] = pi;
  for (const s of part.states) {
    s.R = new Float64Array(part.nVert); s.Y = new Float64Array(part.nVert);
    for (let k = 0; k < part.nRing; k++) { const p = s.profile(U[part.v0 + k], V[part.v0 + k]); s.R[k] = p.r; s.Y[k] = p.y; }
    s.R[part.nRing] = 0; s.Y[part.nRing] = 0;
    s.R[part.nRing + 1] = 0; s.Y[part.nRing + 1] = s.profile(0, 1).y;
  }
});

const tris = [];
for (const part of PARTS) {
  const { v0, nU, nV, iBase, iApex } = part;
  for (let j = 0; j < nV - 1; j++) for (let i = 0; i < nU; i++) {
    const a = v0 + j * nU + i, b = v0 + j * nU + (i + 1) % nU;
    const c = v0 + (j + 1) * nU + (i + 1) % nU, d = v0 + (j + 1) * nU + i;
    tris.push([a, b, c], [a, c, d]);
  }
  for (let i = 0; i < nU; i++) tris.push([v0 + (nV - 1) * nU + i, v0 + (nV - 1) * nU + (i + 1) % nU, iApex]);
  for (let i = 0; i < nU; i++) tris.push([v0 + (i + 1) % nU, v0 + i, iBase]);
  // Make every triangle wind outward, judged on the part's first state.
  const s = part.states[0];
  const P = (n) => { const k = n - v0; return [s.R[k] * Math.cos(U[n]), s.Y[k], s.R[k] * Math.sin(U[n])]; };
  const mid = s.Y[part.nRing + 1] / 2;
  for (const t of tris) {
    if (PART[t[0]] !== PARTS.indexOf(part)) continue;
    const p0 = P(t[0]), p1 = P(t[1]), p2 = P(t[2]);
    const e1 = [p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2]];
    const e2 = [p2[0] - p0[0], p2[1] - p0[1], p2[2] - p0[2]];
    const n = [e1[1] * e2[2] - e1[2] * e2[1], e1[2] * e2[0] - e1[0] * e2[2], e1[0] * e2[1] - e1[1] * e2[0]];
    const c = [(p0[0] + p1[0] + p2[0]) / 3, (p0[1] + p1[1] + p2[1]) / 3 - mid, (p0[2] + p1[2] + p2[2]) / 3];
    if (n[0] * c[0] + n[1] * c[1] + n[2] * c[2] < 0) { const tmp = t[1]; t[1] = t[2]; t[2] = tmp; }
  }
}

const edges = [];
{
  const map = new Map();
  tris.forEach((t, ti) => {
    for (let k = 0; k < 3; k++) {
      const a = t[k], b = t[(k + 1) % 3];
      const key = a < b ? a * NVERT + b : b * NVERT + a;
      let e = map.get(key);
      if (!e) { e = { a: Math.min(a, b), b: Math.max(a, b), t0: ti, t1: -1, part: PART[a] }; map.set(key, e); edges.push(e); }
      else e.t1 = ti;
    }
  });
}

const NT = tris.length;
const T0 = new Int32Array(NT), T1 = new Int32Array(NT), T2 = new Int32Array(NT), TPART = new Uint8Array(NT);
tris.forEach((t, i) => { T0[i] = t[0]; T1[i] = t[1]; T2[i] = t[2]; TPART[i] = PART[t[0]]; });

/* ------------------------------------------------------------------ */
/* 4. Per-frame buffers and constants                                  */
/* ------------------------------------------------------------------ */

const SX = new Float64Array(NVERT), SY = new Float64Array(NVERT);
const VX = new Float64Array(NVERT), VY = new Float64Array(NVERT), VZ = new Float64Array(NVERT);
const NX = new Float64Array(NT), NY = new Float64Array(NT), NZ = new Float64Array(NT);
const FRONT = new Uint8Array(NT);
const VNX = new Float64Array(NVERT), VNY = new Float64Array(NVERT), VNZ = new Float64Array(NVERT);
const SHADE = new Float64Array(NVERT);

const GRID = 22;
const CELL = 440 / GRID;
const cells = Array.from({ length: GRID * GRID }, () => []);

const SCALE = 84;                 // viewBox px per model unit
const CX = 220, CY = 348;         // where the floor's centre lands in the viewBox
const CREASE_LO = 12 * DEG, CREASE_HI = 34 * DEG;
const HATCH_THR = 0.36;
const NBUCKET = 10;   // opacity steps for creases, hatching and striations

/* ------------------------------------------------------------------ */
/* 5. DOM                                                              */
/* ------------------------------------------------------------------ */

const NS = 'http://www.w3.org/2000/svg';
const $ = (id) => document.getElementById(id);
const el = { art: $('art'), shadow: $('shadow'), mesh: $('mesh'), parts: $('parts'), crop: $('crop-rect'), readout: $('readout') };
el.shadows = {};
for (const part of PARTS) {
  const name = part.shadow || part.name;
  if (el.shadows[name]) continue;
  const e = Object.keys(el.shadows).length ? el.shadow.cloneNode(false) : el.shadow;
  if (e !== el.shadow) { e.removeAttribute('id'); el.shadow.after(e); }
  e.setAttribute('class', 'shadow');
  el.shadows[name] = e;
}
for (const part of PARTS) {
  const g = document.createElementNS(NS, 'g');
  g.setAttribute('class', 'part');
  g.dataset.part = part.name;
  const mk = (cls) => { const p = document.createElementNS(NS, 'path'); p.setAttribute('class', cls); g.appendChild(p); return p; };
  part.elHatchG = document.createElementNS(NS, 'g');
  g.appendChild(part.elHatchG);
  part.elHatches = [];
  for (let b = 0; b < NBUCKET; b++) {
    const p = document.createElementNS(NS, 'path');
    p.setAttribute('class', 'hatch');
    p.setAttribute('opacity', ((b + 0.5) / NBUCKET).toFixed(2));
    part.elHatchG.appendChild(p);
    part.elHatches.push(p);
  }
  part.elCreases = [];
  for (let b = 0; b < NBUCKET; b++) { const p = mk('crease'); p.setAttribute('opacity', ((b + 0.5) / NBUCKET).toFixed(2)); part.elCreases.push(p); }
  part.elDetailG = document.createElementNS(NS, 'g');
  g.appendChild(part.elDetailG);
  part.elDetails = [];
  for (let b = 0; b < NBUCKET; b++) {
    const p = document.createElementNS(NS, 'path');
    p.setAttribute('class', 'detail');
    p.setAttribute('opacity', ((b + 0.5) / NBUCKET).toFixed(2));
    part.elDetailG.appendChild(p);
    part.elDetails.push(p);
  }
  part.elSil = mk('silhouette');
  part.el = g;
  el.parts.appendChild(g);
}

let d2 = null, builtHold = null;   // 2D diagram timeline, built once the controls are read
const ctl = { spin: 0.45, elev: 18, weight: 1.8, hold: 0.18, light: 135, hatch: true, wobble: false, mesh: false };
document.querySelectorAll('[data-ctl]').forEach((input) => {
  const key = input.dataset.ctl;
  const read = () => { ctl[key] = input.type === 'checkbox' ? input.checked : parseFloat(input.value); applyCtl(); };
  input.addEventListener('input', read);
  read();
});
function applyCtl() {
  if (d2 && ctl.hold !== builtHold) { d2.tl.kill(); d2 = SCENES2D.build($('d2'), ctl.hold); builtHold = ctl.hold; prime(d2.tl); }
  el.art.style.setProperty('--w', ctl.weight);
  el.art.setAttribute('filter', ctl.wobble ? 'url(#wobble)' : '');
  el.mesh.style.display = ctl.mesh ? 'block' : 'none';
}

/* ------------------------------------------------------------------ */
/* 6. Scroll → progress (0 .. NSCENE - 1)                              */
/* ------------------------------------------------------------------ */

const sections = Array.from(document.querySelectorAll('.scene-text'));
const NSCENE = sections.length;
const state = { progress: 0 };

// 2D diagram scenes live in their own scrubbed timeline (see scenes2d.js)
d2 = SCENES2D.build($('d2'), ctl.hold);
builtHold = ctl.hold;
prime(d2.tl);

// A paused timeline sitting at 0 never renders its "hide everything" sets until it first moves,
// so nudge it forward and back once; otherwise every diagram shows at once before the first scroll.
function prime(tl) { tl.time(0.001, true); tl.time(0, true); }
const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;

// A paragraph is "at the centre" when its middle crosses this viewport line. On narrow
// screens the drawing is pinned across the top, so the line moves down into the text area.
gsap.matchMedia().add({ wide: '(min-width: 641px)', narrow: '(max-width: 640px)' }, (ctx) => {
  const line = ctx.conditions.narrow ? '72%' : 'center';
  gsap.fromTo(state, { progress: 0 }, {
    progress: sections.length - 1,
    ease: 'none',
    scrollTrigger: {
      trigger: sections[0],
      start: 'center ' + line,
      endTrigger: sections[sections.length - 1],
      end: 'center ' + line,
      scrub: reduced ? true : 0.8,
    },
    immediateRender: false,   // a breakpoint change re-runs this; don't snap progress back to 0
  });
});

let lastScrollAt = -1e9;
addEventListener('scroll', () => { lastScrollAt = performance.now(); }, { passive: true });

/* ------------------------------------------------------------------ */
/* 7. Render loop                                                      */
/* ------------------------------------------------------------------ */

const THETA_HOME = 0.35;  // angle transformations happen at
let theta = 0.5;          // turntable angle
let spinVel = 0;
let lastProgress = 0;
let activeIdx = -1;

const pt = (x, y) => x.toFixed(1) + ' ' + y.toFixed(1);
const rotX = (a) => { const c = Math.cos(a), s = Math.sin(a); return [1, 0, 0, 0, c, -s, 0, s, c]; };
const rotY = (a) => { const c = Math.cos(a), s = Math.sin(a); return [c, 0, s, 0, 1, 0, -s, 0, c]; };
const rotZ = (a) => { const c = Math.cos(a), s = Math.sin(a); return [c, -s, 0, s, c, 0, 0, 0, 1]; };
const mul = (A, B) => {
  const M = new Array(9);
  for (let r = 0; r < 3; r++) for (let c = 0; c < 3; c++)
    M[r * 3 + c] = A[r * 3] * B[c] + A[r * 3 + 1] * B[3 + c] + A[r * 3 + 2] * B[6 + c];
  return M;
};

function frame(time, dtMs) {
  const dt = Math.min(dtMs, 50) / 1000;
  const now = performance.now();

  // Which two scenes, and how far between them (with a hold zone around each paragraph).
  const p = clamp(state.progress, 0, NSCENE - 1);
  const ia = Math.min(Math.floor(p), NSCENE - 2);
  const t = clamp((p - ia - ctl.hold) / (1 - 2 * ctl.hold), 0, 1);
  const inTransition = t > 0 && t < 1;
  // the 3D parts only have states for the first few scenes; beyond that they hold their last state
  const ia3 = Math.min(ia, N3D - 2);
  const t3 = ia > N3D - 2 ? 1 : t;
  const ty = smooth(t3);

  d2.tl.time(p, true);
  for (const fn of d2.afterRender) fn();
  for (const l of d2.loops) {
    const on = Math.round(p) === l.scene && !inTransition;
    if (on && l.tween.paused()) l.tween.restart(true);
    else if (!on && !l.tween.paused()) { l.tween.pause(); if (l.reset) l.reset(); else l.tween.pause(0); }
  }

  const idx = Math.round(p);
  if (idx !== activeIdx) { sections.forEach((s, i) => s.classList.toggle('is-active', i === idx)); activeIdx = idx; }

  // Entering the cross-section: level the camera so the wafer's rim reads as a flat slab,
  // lose the floor shadow, and crop the view down to the piece the cross-section will show.
  const handoff = ia === N3D - 2;
  const level = handoff ? smooth(remap(t3, 0.3, 0.7)) : (ia > N3D - 2 ? 1 : 0);
  const shadowFade = handoff ? 1 - smooth(remap(t3, 0.2, 0.45)) : (ia > N3D - 2 ? 0 : 1);
  const crop = handoff ? smooth(remap(t3, 0.6, 0.82)) : (ia > N3D - 2 ? 1 : 0);
  el.crop.setAttribute('x', lerp(0, 70, crop).toFixed(1));
  el.crop.setAttribute('width', lerp(440, 300, crop).toFixed(1));
  const elev = ctl.elev * (1 - level);
  const home = ia >= N3D - 2 ? 0 : THETA_HOME;   // that hand-off wants exactly edge-on

  // Spin only when nothing else is happening; during a transformation, ease back to face front.
  const animating = Math.abs(state.progress - lastProgress) > 1e-5;
  lastProgress = state.progress;
  const idle = !animating && !inTransition && now - lastScrollAt > 260;
  const target = idle && !reduced ? ctl.spin : 0;
  spinVel += (target - spinVel) * (1 - Math.exp(-dt * 4));
  theta += spinVel * dt;
  if (inTransition) {
    // ease the turntable to a home angle so transformations read clearly (slightly off side-on)
    const d = ((theta - home + Math.PI) % TAU + TAU) % TAU - Math.PI;
    theta = home + d * Math.exp(-dt * 5);
  }

  // Camera: turntable about Y, then tilt the whole scene so we look slightly down on it.
  const CAM = mul(rotX(elev * DEG), rotY(-theta));

  // Positions per part: blend profiles, place with the pose, spin, tilt, project.
  for (const part of PARTS) {
    const A = part.states[ia3], B = part.states[ia3 + 1];
    let pose, opacity, shadow;
    if (B.choreo) ({ pose, opacity, shadow } = B.choreo(t3, A, B));
    else { pose = lerpPose(A.pose, B.pose, ty); opacity = lerp(A.opacity, B.opacity, ty); }
    part.opacity = opacity;
    part.shadowOp = shadow === undefined ? opacity : shadow;   // a choreo may fade the shadow separately
    const tmS = smooth(B.morph ? B.morph(t3) : t3);   // shading follows the shape blend's timing
    part.hatch = lerp(A.hatch, B.hatch, tmS) * (ctl.hatch ? 1 : 0);
    part.detail = lerp(A.detail, B.detail, tmS);
    part.visible = opacity > 0.02;
    part.el.setAttribute('opacity', opacity.toFixed(2));
    if (!part.visible) continue;

    const M = mul(CAM, mul(rotY(pose.yaw * DEG), mul(rotZ(pose.tilt * DEG), rotX(pose.pitch * DEG))));
    const tx = CAM[0] * pose.x + CAM[1] * pose.y + CAM[2] * pose.z;
    const tyy = CAM[3] * pose.x + CAM[4] * pose.y + CAM[5] * pose.z;
    const tz = CAM[6] * pose.x + CAM[7] * pose.y + CAM[8] * pose.z;
    const k = B.sag;
    const tm = B.morph ? B.morph(t3) : t3;     // optional retiming of the shape blend
    const tyP = smooth(tm);
    for (let kk = 0; kk < part.nVert; kk++) {
      const n = part.v0 + kk;
      const tr = smooth(tm * (1 + k) - V[n] * k);
      const r = lerp(A.R[kk], B.R[kk], tr), y = lerp(A.Y[kk], B.Y[kk], tyP);
      const sc = pose.scale;
      const lx = sc * r * Math.cos(U[n]), ly = sc * y, lz = sc * r * Math.sin(U[n]);
      VX[n] = M[0] * lx + M[1] * ly + M[2] * lz + tx;
      VY[n] = M[3] * lx + M[4] * ly + M[5] * lz + tyy;
      VZ[n] = M[6] * lx + M[7] * ly + M[8] * lz + tz;
      SX[n] = CX + SCALE * VX[n]; SY[n] = CY - SCALE * VY[n];
    }
  }

  // Triangle normals, facing, vertex normals, lighting.
  const la = ctl.light * DEG;
  const LX = Math.cos(la) * 0.85, LY = Math.sin(la) * 0.85, LZ = 0.4;
  const LL = Math.hypot(LX, LY, LZ);
  VNX.fill(0); VNY.fill(0); VNZ.fill(0);
  for (let i = 0; i < NT; i++) {
    if (!PARTS[TPART[i]].visible) { FRONT[i] = 0; continue; }
    const a = T0[i], b = T1[i], c = T2[i];
    const e1x = VX[b] - VX[a], e1y = VY[b] - VY[a], e1z = VZ[b] - VZ[a];
    const e2x = VX[c] - VX[a], e2y = VY[c] - VY[a], e2z = VZ[c] - VZ[a];
    let nx = e1y * e2z - e1z * e2y, ny = e1z * e2x - e1x * e2z, nz = e1x * e2y - e1y * e2x;
    const len = Math.hypot(nx, ny, nz) || 1;
    nx /= len; ny /= len; nz /= len;
    NX[i] = nx; NY[i] = ny; NZ[i] = nz;
    FRONT[i] = nz > 1e-6 ? 1 : 0;
    VNX[a] += nx; VNY[a] += ny; VNZ[a] += nz;
    VNX[b] += nx; VNY[b] += ny; VNZ[b] += nz;
    VNX[c] += nx; VNY[c] += ny; VNZ[c] += nz;
  }
  for (let n = 0; n < NVERT; n++) {
    const len = Math.hypot(VNX[n], VNY[n], VNZ[n]) || 1;
    VNX[n] /= len; VNY[n] /= len; VNZ[n] /= len;
    SHADE[n] = Math.max(0, (VNX[n] * LX + VNY[n] * LY + VNZ[n] * LZ) / LL);
  }

  // Bin front-facing triangles into screen cells so hidden lines can be tested cheaply.
  for (const c of cells) c.length = 0;
  for (let i = 0; i < NT; i++) {
    if (!FRONT[i]) continue;
    const a = T0[i], b = T1[i], c = T2[i];
    const x0 = clamp(Math.floor(Math.min(SX[a], SX[b], SX[c]) / CELL), 0, GRID - 1);
    const x1 = clamp(Math.floor(Math.max(SX[a], SX[b], SX[c]) / CELL), 0, GRID - 1);
    const y0 = clamp(Math.floor(Math.min(SY[a], SY[b], SY[c]) / CELL), 0, GRID - 1);
    const y1 = clamp(Math.floor(Math.max(SY[a], SY[b], SY[c]) / CELL), 0, GRID - 1);
    for (let gy = y0; gy <= y1; gy++) for (let gx = x0; gx <= x1; gx++) cells[gy * GRID + gx].push(i);
  }

  // Classify edges: silhouette (front meets back) or crease (sharp bend between two front faces).
  for (const part of PARTS) { part.sil = []; part.buckets = new Array(NBUCKET).fill(''); }
  let meshD = '';
  for (const e of edges) {
    const part = PARTS[e.part];
    if (!part.visible) continue;
    const f0 = FRONT[e.t0], f1 = e.t1 >= 0 ? FRONT[e.t1] : 0;
    if (ctl.mesh) meshD += 'M' + pt(SX[e.a], SY[e.a]) + 'L' + pt(SX[e.b], SY[e.b]);
    if (!f0 && !f1) continue;
    if (occluded((SX[e.a] + SX[e.b]) / 2, (SY[e.a] + SY[e.b]) / 2, (VZ[e.a] + VZ[e.b]) / 2, e.t0, e.t1)) continue;
    if (f0 !== f1) { part.sil.push(e); continue; }
    const d = clamp(NX[e.t0] * NX[e.t1] + NY[e.t0] * NY[e.t1] + NZ[e.t0] * NZ[e.t1], -1, 1);
    const ang = Math.acos(d);
    if (ang < CREASE_LO) continue;
    const o = smooth((ang - CREASE_LO) / (CREASE_HI - CREASE_LO));
    const b = Math.min(NBUCKET - 1, Math.floor(o * NBUCKET));
    part.buckets[b] += 'M' + pt(SX[e.a], SY[e.a]) + 'L' + pt(SX[e.b], SY[e.b]);
  }
  if (ctl.mesh) el.mesh.setAttribute('d', meshD);

  for (const part of PARTS) {
    if (!part.visible) continue;
    for (let b = 0; b < NBUCKET; b++) part.elCreases[b].setAttribute('d', part.buckets[b]);
    part.elSil.setAttribute('d', chain(part.sil));
    const hd = part.hatch > 0.01 ? hatch(part) : new Array(NBUCKET).fill('');
    for (let b = 0; b < NBUCKET; b++) part.elHatches[b].setAttribute('d', hd[b]);
    part.elHatchG.setAttribute('opacity', (0.8 * part.hatch).toFixed(2));
    const dd = part.detail > 0.01 && part.details ? details(part) : new Array(NBUCKET).fill('');
    for (let b = 0; b < NBUCKET; b++) part.elDetails[b].setAttribute('d', dd[b]);
    part.elDetailG.setAttribute('opacity', (0.45 * part.detail).toFixed(2));
  }

  // Ground shadows: one per shadow group, the footprint of its visible parts projected straight
  // down onto the floor, fading with the parts that cast it.
  const sphi = Math.sin(elev * DEG), cphi = Math.cos(elev * DEG);
  const groups = {};
  for (const part of PARTS) {
    if (!part.visible) continue;
    const name = part.shadow || part.name;
    const g = groups[name] || (groups[name] = { minX: Infinity, maxX: -Infinity, minY: Infinity, maxY: -Infinity, op: 0 });
    g.op = Math.max(g.op, part.shadowOp);
    for (let kk = 0; kk < part.nVert; kk++) {
      const n = part.v0 + kk;
      // undo the camera tilt on y to recover world z, then drop the point to y = 0
      const wz = VZ[n] * cphi - VY[n] * sphi;
      const fy = CY + SCALE * wz * sphi;
      g.minX = Math.min(g.minX, SX[n]); g.maxX = Math.max(g.maxX, SX[n]);
      g.minY = Math.min(g.minY, fy); g.maxY = Math.max(g.maxY, fy);
    }
  }
  for (const name in el.shadows) {
    const e = el.shadows[name], g = groups[name];
    if (!g) { e.setAttribute('opacity', '0'); continue; }
    e.setAttribute('cx', ((g.minX + g.maxX) / 2).toFixed(1));
    e.setAttribute('cy', ((g.minY + g.maxY) / 2).toFixed(1));
    e.setAttribute('rx', ((g.maxX - g.minX) / 2 * 0.92 + 4).toFixed(1));
    e.setAttribute('ry', ((g.maxY - g.minY) / 2 * 0.92 + 4).toFixed(1));
    e.setAttribute('opacity', (g.op * shadowFade).toFixed(2));
  }

  el.readout.value = `scene ${ia} → ${ia + 1}  t=${t.toFixed(2)}  progress=${p.toFixed(2)}`;
}

// Is the screen point (x, y) at view depth z covered by a nearer front-facing triangle?
function occluded(x, y, z, skipA, skipB) {
  const gx = clamp(Math.floor(x / CELL), 0, GRID - 1), gy = clamp(Math.floor(y / CELL), 0, GRID - 1);
  const list = cells[gy * GRID + gx];
  for (let k = 0; k < list.length; k++) {
    const i = list[k];
    if (i === skipA || i === skipB) continue;
    const a = T0[i], b = T1[i], c = T2[i];
    const x0 = SX[a], y0 = SY[a];
    const dx1 = SX[b] - x0, dy1 = SY[b] - y0, dx2 = SX[c] - x0, dy2 = SY[c] - y0;
    const det = dx1 * dy2 - dx2 * dy1;
    if (Math.abs(det) < 1e-9) continue;
    const px = x - x0, py = y - y0;
    const l1 = (px * dy2 - dx2 * py) / det;
    const l2 = (dx1 * py - px * dy1) / det;
    if (l1 < -1e-4 || l2 < -1e-4 || l1 + l2 > 1 + 1e-4) continue;
    const zt = VZ[a] + l1 * (VZ[b] - VZ[a]) + l2 * (VZ[c] - VZ[a]);
    if (zt > z + 0.01) return true;
  }
  return false;
}

// Hatching: runs along the part's own meridians wherever the visible surface faces away from the
// light. A run's opacity grows with its length, so strokes ease in and out as the object turns
// rather than popping once they clear a minimum size.
function hatch(part) {
  const buckets = new Array(NBUCKET).fill('');
  for (let i = 0; i < part.nU; i += 4) {
    let run = [], runLen = 0, lx = 0, ly = 0, shadeSum = 0, facingSum = 0, nIn = 0;
    const push = (x, y) => { if (run.length) runLen += Math.hypot(x - lx, y - ly); lx = x; ly = y; run.push(pt(x, y)); };
    const flush = () => {
      if (run.length >= 2) {
        // On a straight-sided shape like the ingot every point of a meridian shares one normal, so a
        // run cannot shrink away: it must fade instead, as its (mean) shade nears the threshold or it
        // turns edge-on. Each factor reaches zero exactly where its cutoff would remove the run.
        const meanShade = nIn ? shadeSum / nIn : 0, meanFacing = nIn ? facingSum / nIn : 0;
        const o = smooth((runLen - 2) / 20) * smooth((HATCH_THR - meanShade) / 0.18) * smooth((meanFacing - 0.08) / 0.22);
        if (o > 0.04) buckets[Math.min(NBUCKET - 1, Math.floor(o * NBUCKET))] += 'M' + run.join('L');
      }
      run = []; runLen = 0; shadeSum = 0; facingSum = 0; nIn = 0;
    };
    for (let j = 1; j < part.nV - 1; j++) {   // skip the base and the chamfer ring, whose normals differ
      const n = part.v0 + j * part.nU + i, m = n - part.nU;
      const front = VNZ[n] > 0.08 && !occluded(SX[n], SY[n], VZ[n], -1, -1);
      const inside = front && SHADE[n] < HATCH_THR;
      if (inside) {
        if (run.length === 0 && j > 1 && VNZ[m] > 0.08 && SHADE[m] > HATCH_THR) {
          const f = (SHADE[m] - HATCH_THR) / (SHADE[m] - SHADE[n]);
          push(lerp(SX[m], SX[n], f), lerp(SY[m], SY[n], f));
        }
        push(SX[n], SY[n]);
        shadeSum += SHADE[n]; facingSum += VNZ[n]; nIn++;
      } else {
        if (run.length && front && SHADE[n] > HATCH_THR) {
          const f = (HATCH_THR - SHADE[m]) / (SHADE[n] - SHADE[m]);
          push(lerp(SX[m], SX[n], f), lerp(SY[m], SY[n], f));
        }
        flush();
      }
    }
    flush();
  }
  return buckets;
}

// Surface detail strokes (quartz striations): short runs along a grid ring. Each piece fades with
// how squarely its face meets the eye, so the lines ease in and out as the crystal turns.
function details(part) {
  const buckets = new Array(NBUCKET).fill('');
  for (const seg of part.details) {
    for (let i = seg.i0; i < seg.i1; i++) {
      const a = part.v0 + seg.j * part.nU + (i % part.nU), b = part.v0 + seg.j * part.nU + ((i + 1) % part.nU);
      const facing = Math.min(VNZ[a], VNZ[b]);
      const o = smooth((facing - 0.1) / 0.4);
      if (o < 0.04) continue;
      if (occluded(SX[a], SY[a], VZ[a], -1, -1) || occluded(SX[b], SY[b], VZ[b], -1, -1)) continue;
      const k = Math.min(NBUCKET - 1, Math.floor(o * NBUCKET));
      buckets[k] += 'M' + pt(SX[a], SY[a]) + 'L' + pt(SX[b], SY[b]);
    }
  }
  return buckets;
}

// Join silhouette edges into polylines so the outline is one clean stroke.
function chain(silEdges) {
  const adj = new Map();
  const add = (v, k) => { let l = adj.get(v); if (!l) adj.set(v, l = []); l.push(k); };
  silEdges.forEach((e, k) => { add(e.a, k); add(e.b, k); });
  const used = new Uint8Array(silEdges.length);
  const next = (v) => { const l = adj.get(v); if (l) for (const k of l) if (!used[k]) return k; return -1; };
  let d = '';
  for (let k0 = 0; k0 < silEdges.length; k0++) {
    if (used[k0]) continue;
    used[k0] = 1;
    const e0 = silEdges[k0];
    const fwd = [e0.b];
    let cur = e0.b;
    for (;;) {
      const k = next(cur); if (k < 0) break;
      used[k] = 1; const e = silEdges[k];
      cur = e.a === cur ? e.b : e.a; fwd.push(cur);
      if (cur === e0.a) break;
    }
    const closed = cur === e0.a;
    const bwd = [e0.a];
    if (!closed) {
      cur = e0.a;
      for (;;) {
        const k = next(cur); if (k < 0) break;
        used[k] = 1; const e = silEdges[k];
        cur = e.a === cur ? e.b : e.a; bwd.push(cur);
      }
    }
    const pts = bwd.reverse().concat(closed ? fwd.slice(0, -1) : fwd);
    d += 'M' + pts.map((v) => pt(SX[v], SY[v])).join('L') + (closed ? 'Z' : '');
  }
  return d;
}

gsap.ticker.add(frame);

// Handy from the console: __demo.theta = 1.2; __demo.ctl.spin = 0
window.__demo = { state, ctl, parts: PARTS, get theta() { return theta; }, set theta(v) { theta = v; }, get d2() { return d2; } };
