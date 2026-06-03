import * as THREE from "https://cdn.jsdelivr.net/npm/three@0.160.1/build/three.module.js";

/* ================================================================
   Liquid Glass  –  metaball refraction over typography
   ================================================================ */

/* ── Constants ──────────────────────────────────────────── */
const MAX_DROPLETS = 40;
const FIXED_DT_MS = 8;
const MAX_FRAME_DT_MS = 100;
const MAX_CATCHUP = 6;

/* ── Renderer ───────────────────────────────────────────── */
const app = document.getElementById("app");
const renderer = new THREE.WebGLRenderer({ antialias: false });
renderer.setPixelRatio(Math.min(2, devicePixelRatio || 1));
renderer.setSize(innerWidth, innerHeight);
app.appendChild(renderer.domElement);

const scene = new THREE.Scene();
const camera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);

/* ── Background typography texture ──────────────────────── */
const bgCanvas = document.createElement("canvas");
const bgCtx = bgCanvas.getContext("2d");
const bgTexture = new THREE.CanvasTexture(bgCanvas);
bgTexture.minFilter = THREE.LinearFilter;
bgTexture.magFilter = THREE.LinearFilter;

function drawBackground() {
  const w = renderer.domElement.width;
  const h = renderer.domElement.height;
  bgCanvas.width = w;
  bgCanvas.height = h;

  /* gradient background — CaseHub teal palette */
  const grd = bgCtx.createLinearGradient(0, 0, w * 0.6, h);
  grd.addColorStop(0, "#e8e4df");    /* warm off-white */
  grd.addColorStop(0.3, "#b8d8d8");  /* light cyan-gray */
  grd.addColorStop(0.6, "#1C2447");  /* CaseHub teal */
  grd.addColorStop(1, "#1a6670");    /* CaseHub teal dark */
  bgCtx.fillStyle = grd;
  bgCtx.fillRect(0, 0, w, h);

  /* decorative colour waves — teal/green hues */
  bgCtx.save();
  bgCtx.globalAlpha = 0.35;
  for (let i = 0; i < 5; i++) {
    const cx = w * (0.2 + i * 0.18);
    const cy = h * (0.3 + Math.sin(i * 1.3) * 0.25);
    const rg = bgCtx.createRadialGradient(cx, cy, 0, cx, cy, w * 0.35);
    const hue = 170 + i * 12;  /* range 170-218: teal → cyan */
    rg.addColorStop(0, `hsla(${hue}, 55%, 50%, 0.6)`);
    rg.addColorStop(1, `hsla(${hue}, 45%, 35%, 0)`);
    bgCtx.fillStyle = rg;
    bgCtx.fillRect(0, 0, w, h);
  }
  bgCtx.restore();

  /* main title */
  bgCtx.fillStyle = "#ffffff";
  bgCtx.textAlign = "center";
  bgCtx.textBaseline = "middle";

  const titleSize = Math.round(w * 0.13);
  bgCtx.font = `700 ${titleSize}px 'Space Grotesk', sans-serif`;
  bgCtx.fillText("Liquid", w * 0.5, h * 0.38);
  bgCtx.fillText("Glass", w * 0.5, h * 0.38 + titleSize * 1.05);

  /* subtitle */
  const subSize = Math.round(w * 0.022);
  bgCtx.font = `500 ${subSize}px 'Space Grotesk', sans-serif`;
  bgCtx.globalAlpha = 0.55;
  bgCtx.fillText(
    "Metaball Refraction Demo",
    w * 0.5,
    h * 0.38 + titleSize * 2.3,
  );
  bgCtx.globalAlpha = 1;

  /* scattered small text */
  const words = [
    "physics",
    "refraction",
    "merge",
    "split",
    "surface tension",
    "metaball",
    "IOR",
    "glass",
    "droplet",
  ];
  bgCtx.globalAlpha = 0.08;
  const scatterSize = Math.round(w * 0.018);
  bgCtx.font = `500 ${scatterSize}px 'Space Grotesk', sans-serif`;
  for (let i = 0; i < words.length; i++) {
    bgCtx.fillText(
      words[i],
      w * (0.12 + (i % 4) * 0.25),
      h * (0.08 + Math.floor(i / 4) * 0.35 + (i % 3) * 0.12),
    );
  }
  bgCtx.globalAlpha = 1;

  bgTexture.needsUpdate = true;
}

/* wait for font to load, then draw */
document.fonts.ready.then(() => {
  drawBackground();
});
drawBackground();

/* ── Droplet data (main + ghost trailing blobs) ─────────── */
const MAX_ENTRIES = MAX_DROPLETS * 2;
const dropletBuf = new Float32Array(MAX_ENTRIES * 4);
const dropletTex = new THREE.DataTexture(
  dropletBuf,
  MAX_ENTRIES,
  1,
  THREE.RGBAFormat,
  THREE.FloatType,
);
dropletTex.minFilter = THREE.NearestFilter;
dropletTex.magFilter = THREE.NearestFilter;
dropletTex.needsUpdate = true;

let drops = [];
let uid = 0;

function spawn(x, y, r, vx = 0, vy = 0) {
  if (drops.length >= MAX_DROPLETS) return null;
  const area = Math.PI * r * r;
  const angle = Math.random() * Math.PI * 2;
  const spd = 0.0003 + Math.random() * 0.0008;
  const d = {
    id: uid++,
    x,
    y,
    r,
    area,
    vx: vx || Math.cos(angle) * spd,
    vy: vy || Math.sin(angle) * spd,
    alive: true,
    wanderAngle: Math.random() * Math.PI * 2,
    wanderSpeed: 0.3 + Math.random() * 0.5,
    /* soft-body state */
    softPrevX: x,
    softPrevY: y,
    softOffX: 0,
    softOffY: 0,
    softVelX: 0,
    softVelY: 0,
  };
  drops.push(d);
  return d;
}

/* seed */
for (let i = 0; i < 12; i++) {
  spawn(
    (Math.random() - 0.5) * 0.7,
    (Math.random() - 0.5) * 0.5,
    0.03 + Math.random() * 0.05,
  );
}

/* ── Liquid Glass shader ────────────────────────────────── */
const vertSrc = /* glsl */ `void main(){ gl_Position = vec4(position, 1.0); }`;

const fragSrc = /* glsl */ `
precision highp float;
#define MAX_N ${MAX_ENTRIES}

uniform vec2      uRes;
uniform sampler2D uData;
uniform sampler2D uBg;
uniform int       uCount;
uniform float     uTime;

void main(){
  vec2  uv  = gl_FragCoord.xy / uRes;
  float asp = uRes.x / uRes.y;
  vec2  p   = (uv - 0.5) * vec2(asp, 1.0);

  /* ── Accumulate metaball field + lens displacement ── */
  float field = 0.0;
  vec2  grad  = vec2(0.0);
  vec2  lens  = vec2(0.0);   /* weighted pull toward blob centres */
  float lensW = 0.0;

  for(int i = 0; i < MAX_N; i++){
    if(i >= uCount) break;
    vec4  d = texture2D(uData, vec2((float(i)+0.5)/float(MAX_N), 0.5));
    vec2  c = d.xy;
    float r = d.z;
    if(r < 0.001) continue;
    vec2  delta = p - c;
    float dSq   = dot(delta, delta) + 1e-5;
    float contrib = r * r / dSq;
    field += contrib;
    grad  += -2.0 * contrib / dSq * delta;

    /* lens weight: smooth falloff from centre, no singularity */
    float w = r * r / (dSq + r * r);
    lens += (c - p) * w;
    lensW += w;
  }

  /* normalise lens displacement */
  lens /= (lensW + 0.001);
  float lensLen = length(lens);

  float thr  = 1.0;
  float edge = smoothstep(thr - 0.08, thr + 0.03, field);

  /* ── Lens-based refraction (no centre fold) ── */
  float refractStrength = 0.035;
  float mappedLens = atan(lensLen * 6.0) * refractStrength;
  vec2  refractDir = (lensLen > 1e-5) ? lens / lensLen : vec2(0.0);
  /* scale refraction by edge mask with wide soft ramp */
  float refractMask = smoothstep(thr - 0.2, thr + 1.5, field);
  vec2  refractedUV = clamp(uv + refractDir * mappedLens * refractMask, 0.001, 0.999);

  /* sample background */
  vec3  bgClean = texture2D(uBg, uv).rgb;

  /* ── Glass normal from gradient (atan-compressed) ── */
  float gradLen = length(grad);
  float nScale = atan(gradLen * 0.5) * 0.3;
  vec2  nGrad  = (gradLen > 1e-4) ? (grad / gradLen) * nScale : vec2(0.0);
  vec3  N = normalize(vec3(-nGrad, 1.0));
  vec3  L = normalize(vec3(0.3, 0.6, 1.0));
  vec3  V = vec3(0.0, 0.0, 1.0);
  vec3  H = normalize(L + V);
  float diff = max(dot(N, L), 0.0);
  float spec = pow(max(dot(N, H), 0.0), 180.0);

  /* Fresnel (Schlick) */
  float cosTheta = max(dot(N, V), 0.0);
  float fresnel  = 0.04 + 0.96 * pow(1.0 - cosTheta, 4.0);

  /* rim highlight at boundary */
  float rim = smoothstep(thr + 0.6, thr, field) * edge;

  /* subtle chromatic aberration */
  float caStr = 0.0018 * edge;
  vec3 bgCA;
  bgCA.r = texture2D(uBg, refractedUV + vec2(caStr, caStr * 0.5)).r;
  bgCA.g = texture2D(uBg, refractedUV).g;
  bgCA.b = texture2D(uBg, refractedUV - vec2(caStr, caStr * 0.5)).b;

  /* depth tint */
  float depth = smoothstep(thr, thr + 3.0, field);
  vec3  tint  = mix(vec3(1.0), vec3(0.93, 0.96, 1.0), depth * 0.45);

  /* compose glass */
  vec3 glassColor = bgCA * tint * (0.92 + 0.08 * diff)
                  + vec3(1.0) * spec * 0.85
                  + vec3(0.9, 0.95, 1.0) * rim * 0.22
                  + vec3(1.0) * fresnel * 0.10;

  /* soft shadow */
  float shadowField = smoothstep(thr - 0.35, thr - 0.05, field);
  vec3 bg = bgClean * (1.0 - shadowField * 0.06);

  /* thin white border */
  float borderOuter = smoothstep(thr - 0.10, thr - 0.01, field);
  float borderInner = smoothstep(thr + 0.0, thr + 0.06, field);
  float border = borderOuter * (1.0 - borderInner) * 0.28;

  vec3  col = mix(bg, glassColor, edge);
  col += vec3(1.0) * border;

  gl_FragColor = vec4(col, 1.0);
}
`;

const mat = new THREE.ShaderMaterial({
  vertexShader: vertSrc,
  fragmentShader: fragSrc,
  uniforms: {
    uRes: {
      value: new THREE.Vector2(
        renderer.domElement.width,
        renderer.domElement.height,
      ),
    },
    uData: { value: dropletTex },
    uBg: { value: bgTexture },
    uCount: { value: 0 },
    uTime: { value: 0 },
  },
});
scene.add(new THREE.Mesh(new THREE.PlaneGeometry(2, 2), mat));

/* ── Input ──────────────────────────────────────────────── */
let aspect = innerWidth / innerHeight;
const mouse = { x: 999, y: 999, active: false, down: false };
let spawnCD = 0;

renderer.domElement.addEventListener("pointermove", (e) => {
  const rect = renderer.domElement.getBoundingClientRect();
  mouse.x = ((e.clientX - rect.left) / rect.width - 0.5) * aspect;
  mouse.y = 0.5 - (e.clientY - rect.top) / rect.height;
  mouse.active = true;
});
renderer.domElement.addEventListener("pointerdown", () => {
  mouse.down = true;
});
renderer.domElement.addEventListener("pointerup", () => {
  mouse.down = false;
});
renderer.domElement.addEventListener("pointerleave", () => {
  mouse.active = false;
  mouse.down = false;
});

window.addEventListener("resize", () => {
  renderer.setSize(innerWidth, innerHeight);
  renderer.setPixelRatio(Math.min(2, devicePixelRatio || 1));
  aspect = innerWidth / innerHeight;
  mat.uniforms.uRes.value.set(
    renderer.domElement.width,
    renderer.domElement.height,
  );
  drawBackground();
});

/* ── Physics parameters ─────────────────────────────────── */
const DAMP = 0.993;
const MOUSE_R = 0.18;
const MOUSE_F = 0.004;
const TENSION_RANGE = 0.12;
const TENSION_F = 0.0004;
const MERGE_RATIO = 0.62;
const SPLIT_SPEED = 0.013;
const SPLIT_MIN_R = 0.04;
const MAX_SPEED = 0.015;
const BOUNCE = 0.4;
const WANDER_F = 0.00004;
const CENTER_PULL = 0.000008;

/* ── Forces (no gravity, random wander) ─────────────────── */
function applyForces(time) {
  for (const d of drops) {
    /* random wander */
    d.wanderAngle += (Math.random() - 0.5) * d.wanderSpeed;
    d.vx += Math.cos(d.wanderAngle) * WANDER_F;
    d.vy += Math.sin(d.wanderAngle) * WANDER_F;

    /* gentle pull toward center to keep them in view */
    d.vx -= d.x * CENTER_PULL;
    d.vy -= d.y * CENTER_PULL;

    /* mouse repulsion */
    if (mouse.active) {
      const dx = d.x - mouse.x;
      const dy = d.y - mouse.y;
      const dSq = dx * dx + dy * dy;
      const rr = MOUSE_R + d.r;
      if (dSq < rr * rr && dSq > 1e-5) {
        const dist = Math.sqrt(dSq);
        const s = 1 - dist / rr;
        const f = s * s * MOUSE_F;
        d.vx += (dx / dist) * f;
        d.vy += (dy / dist) * f;
      }
    }
  }

  /* pairwise surface tension */
  for (let i = 0; i < drops.length; i++) {
    const a = drops[i];
    for (let j = i + 1; j < drops.length; j++) {
      const b = drops[j];
      const dx = b.x - a.x;
      const dy = b.y - a.y;
      const dSq = dx * dx + dy * dy;
      const rng = TENSION_RANGE + a.r + b.r;
      if (dSq < rng * rng && dSq > 1e-5) {
        const dist = Math.sqrt(dSq);
        const s = 1 - dist / rng;
        const f = s * TENSION_F;
        const fx = (dx / dist) * f;
        const fy = (dy / dist) * f;
        a.vx += fx;
        a.vy += fy;
        b.vx -= fx;
        b.vy -= fy;
      }
    }
  }
}

/* ── Integration + wall constraints ─────────────────────── */
function integrate() {
  for (const d of drops) {
    const sp = Math.sqrt(d.vx * d.vx + d.vy * d.vy);
    if (sp > MAX_SPEED) {
      const s = MAX_SPEED / sp;
      d.vx *= s;
      d.vy *= s;
    }
    d.x += d.vx;
    d.y += d.vy;
    d.vx *= DAMP;
    d.vy *= DAMP;

    const wx = aspect * 0.5;
    const wy = 0.5;
    if (d.x - d.r < -wx) {
      d.x = -wx + d.r;
      d.vx = Math.abs(d.vx) * BOUNCE;
    }
    if (d.x + d.r > wx) {
      d.x = wx - d.r;
      d.vx = -Math.abs(d.vx) * BOUNCE;
    }
    if (d.y - d.r < -wy) {
      d.y = -wy + d.r;
      d.vy = Math.abs(d.vy) * BOUNCE;
    }
    if (d.y + d.r > wy) {
      d.y = wy - d.r;
      d.vy = -Math.abs(d.vy) * BOUNCE;
    }
  }
}

/* ── Merge (area-conserving) ────────────────────────────── */
function mergeDroplets() {
  for (let i = 0; i < drops.length; i++) {
    const a = drops[i];
    if (!a.alive) continue;
    for (let j = i + 1; j < drops.length; j++) {
      const b = drops[j];
      if (!b.alive) continue;
      const dx = b.x - a.x;
      const dy = b.y - a.y;
      const dist = Math.sqrt(dx * dx + dy * dy);
      if (dist < (a.r + b.r) * MERGE_RATIO) {
        const na = a.area + b.area;
        a.x = (a.x * a.area + b.x * b.area) / na;
        a.y = (a.y * a.area + b.y * b.area) / na;
        a.vx = (a.vx * a.area + b.vx * b.area) / na;
        a.vy = (a.vy * a.area + b.vy * b.area) / na;
        a.r = Math.sqrt(na / Math.PI);
        a.area = na;
        b.alive = false;
      }
    }
  }
  drops = drops.filter((d) => d.alive);
}

/* ── Split (momentum-driven) ────────────────────────────── */
function splitDroplets() {
  const add = [];
  for (const d of drops) {
    if (d.r < SPLIT_MIN_R) continue;
    const sp = Math.sqrt(d.vx * d.vx + d.vy * d.vy);
    if (sp < SPLIT_SPEED) continue;

    const ha = d.area * 0.5;
    const nr = Math.sqrt(ha / Math.PI);
    const nx = -d.vy / sp;
    const ny = d.vx / sp;
    const off = nr * 0.7;

    d.r = nr;
    d.area = ha;
    d.x -= nx * off;
    d.y -= ny * off;

    add.push({
      id: uid++,
      x: d.x + nx * off * 2,
      y: d.y + ny * off * 2,
      r: nr,
      area: ha,
      vx: d.vx + nx * sp * 0.35,
      vy: d.vy + ny * sp * 0.35,
      alive: true,
      wanderAngle: Math.random() * Math.PI * 2,
      wanderSpeed: 0.3 + Math.random() * 0.5,
      softPrevX: d.x + nx * off * 2,
      softPrevY: d.y + ny * off * 2,
      softOffX: 0,
      softOffY: 0,
      softVelX: 0,
      softVelY: 0,
    });
  }
  for (const a of add) if (drops.length < MAX_DROPLETS) drops.push(a);
}

/* ── Auto-spawn (random position, no top bias) ──────────── */
let autoTimer = 0;
function autoSpawn() {
  autoTimer += FIXED_DT_MS;
  if (autoTimer > 2000 && drops.length < 10) {
    autoTimer = 0;
    spawn(
      (Math.random() - 0.5) * aspect * 0.6,
      (Math.random() - 0.5) * 0.6,
      0.025 + Math.random() * 0.03,
    );
  }
}

/* ── Click / drag spawn ─────────────────────────────────── */
function mouseSpawn() {
  if (!mouse.down || !mouse.active) return;
  spawnCD -= FIXED_DT_MS;
  if (spawnCD <= 0 && drops.length < MAX_DROPLETS) {
    spawnCD = 120;
    spawn(
      mouse.x + (Math.random() - 0.5) * 0.02,
      mouse.y + (Math.random() - 0.5) * 0.02,
      0.02 + Math.random() * 0.015,
    );
  }
}

/* ── Soft-body spring follow (like physics-demo) ────────── */
const SOFT_STIFFNESS = 0.22;
const SOFT_DAMPING = 0.6;

function updateSoftBodies() {
  for (const d of drops) {
    const dx = d.x - d.softPrevX;
    const dy = d.y - d.softPrevY;

    d.softVelX += (dx - d.softOffX) * SOFT_STIFFNESS;
    d.softVelY += (dy - d.softOffY) * SOFT_STIFFNESS;
    d.softVelX *= SOFT_DAMPING;
    d.softVelY *= SOFT_DAMPING;
    d.softOffX += d.softVelX;
    d.softOffY += d.softVelY;

    d.softPrevX = d.x;
    d.softPrevY = d.y;
  }
}

/* ── Fixed step ─────────────────────────────────────────── */
let simTime = 0;
function fixedUpdate() {
  simTime += FIXED_DT_MS;
  applyForces(simTime);
  integrate();
  mergeDroplets();
  splitDroplets();
  updateSoftBodies();
  autoSpawn();
  mouseSpawn();
}

/* ── Sync texture for shader (main + ghost trailing blobs) ── */
function sync() {
  dropletBuf.fill(0);
  const n = Math.min(drops.length, MAX_DROPLETS);
  for (let i = 0; i < n; i++) {
    const d = drops[i];
    /* main blob */
    dropletBuf[i * 4] = d.x;
    dropletBuf[i * 4 + 1] = d.y;
    dropletBuf[i * 4 + 2] = d.r;
    dropletBuf[i * 4 + 3] = 1;

    /* ghost trailing blob: positioned behind by softOffset,
       smaller radius → creates a teardrop tail via metaball merge */
    const ghostScale = 0.7;
    const trailStr = 3.5;
    const gi = (n + i) * 4;
    dropletBuf[gi] = d.x - d.softOffX * trailStr;
    dropletBuf[gi + 1] = d.y - d.softOffY * trailStr;
    dropletBuf[gi + 2] = d.r * ghostScale;
    dropletBuf[gi + 3] = 1;
  }
  dropletTex.needsUpdate = true;
  mat.uniforms.uCount.value = n * 2;
}

/* ── Main loop ──────────────────────────────────────────── */
let last = performance.now();
let acc = 0;
let paused = false;

document.addEventListener("visibilitychange", () => {
  paused = document.hidden;
  if (!paused) last = performance.now();
});

(function loop() {
  if (paused) {
    requestAnimationFrame(loop);
    return;
  }
  const now = performance.now();
  const dt = Math.min(now - last, MAX_FRAME_DT_MS);
  last = now;
  acc += dt;

  let g = 0;
  while (acc >= FIXED_DT_MS && g < MAX_CATCHUP) {
    fixedUpdate();
    acc -= FIXED_DT_MS;
    g++;
  }
  if (g >= MAX_CATCHUP) acc = 0;

  mat.uniforms.uTime.value = now * 0.001;
  sync();
  renderer.render(scene, camera);
  requestAnimationFrame(loop);
})();