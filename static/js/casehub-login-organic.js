import * as THREE from '/static/vendor/three/0.160.0/three.module.min.js';

const root = document.documentElement;
const canvas = document.getElementById('casehub-login-organic-bg');

if (canvas && root.dataset.product === 'lite') {
  const skipWebGL = navigator.webdriver === true;

  const canUseWebGL = () => {
    const probe = document.createElement('canvas');
    try {
      const gl =
        probe.getContext('webgl2', { alpha: true, antialias: false }) ||
        probe.getContext('webgl', { alpha: true, antialias: false }) ||
        probe.getContext('experimental-webgl', { alpha: true, antialias: false });
      return Boolean(gl);
    } catch (_) {
      return false;
    }
  };

  const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const isLowPowerViewport = () => window.matchMedia('(max-width: 520px)').matches;
  const prefersLowPower = isLowPowerViewport();

  const shared = {
    depth: 0.04,
    lightX: 0.968,
    lightY: -0.36,
    speed: prefersLowPower ? 0.085 : 0.1148,
    angle: 1.08699,
    foldFrequency: 1.865,
    warpAmount: 4.0,
    noiseScale: 0.714,
    connections: 0.8715,
    shadowWidth: 0.01,
  };

  // Four-stop shader palette from the approved CaseHub Brand Kit colors.
  const palettes = {
    meadow: ['#001f3e', '#1e4890', '#008c4d', '#b5e2a4'],
    deep: ['#001f3e', '#1e4890', '#008c4d', '#6fbe54'],
    fresh: ['#005f3d', '#008c4d', '#6fbe54', '#fafbf7'],
    azure: ['#001f3e', '#1e4890', '#6fbe54', '#fafbf7'],
    night: ['#00111f', '#001f3e', '#1e4890', '#6fbe54'],
    dawn: ['#001f3e', '#1e4890', '#6fbe54', '#dbe64c'],
    'pollen-field': ['#001f3e', '#008c4d', '#6fbe54', '#dbe64c'],
  };

  const variant = palettes[root.dataset.loginVariant] ? root.dataset.loginVariant : 'meadow';
  const colors = palettes[variant];

  const scene = new THREE.Scene();
  const camera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0.1, 10);
  camera.position.z = 1;

  if (skipWebGL || !canUseWebGL()) {
    canvas.hidden = true;
    root.classList.remove('casehub-login-organic-ready');
  } else {
    let renderer;
    try {
      renderer = new THREE.WebGLRenderer({
        canvas,
        antialias: false,
        alpha: true,
        powerPreference: 'low-power',
      });
    } catch (_) {
      canvas.hidden = true;
      renderer = null;
    }

    if (!renderer) {
      root.classList.remove('casehub-login-organic-ready');
    } else {
  renderer.setClearColor(0x000000, 0);

  const vertexShader = `
    varying vec2 vUv;
    void main() {
      vUv = uv;
      gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
    }
  `;

  const fragmentShader = `
    precision highp float;
    varying vec2 vUv;
    uniform float uTime;
    uniform vec2 uResolution;
    uniform vec3 uColor1;
    uniform vec3 uColor2;
    uniform vec3 uColor3;
    uniform vec3 uColor4;
    uniform vec3 uLightPos;
    uniform float uDepth;
    uniform float uSpeed;
    uniform float uNoiseScale;
    uniform float uWarpAmount;
    uniform float uFoldFrequency;
    uniform float uAngle;
    uniform float uConnections;
    uniform float uShadowWidth;

    vec3 mod289(vec3 x) { return x - floor(x * (1.0 / 289.0)) * 289.0; }
    vec4 mod289(vec4 x) { return x - floor(x * (1.0 / 289.0)) * 289.0; }
    vec4 permute(vec4 x) { return mod289(((x * 34.0) + 1.0) * x); }
    vec4 taylorInvSqrt(vec4 r) { return 1.79284291400159 - 0.85373472095314 * r; }

    float snoise(vec3 v) {
      const vec2 C = vec2(1.0 / 6.0, 1.0 / 3.0);
      const vec4 D = vec4(0.0, 0.5, 1.0, 2.0);
      vec3 i = floor(v + dot(v, C.yyy));
      vec3 x0 = v - i + dot(i, C.xxx);
      vec3 g = step(x0.yzx, x0.xyz);
      vec3 l = 1.0 - g;
      vec3 i1 = min(g.xyz, l.zxy);
      vec3 i2 = max(g.xyz, l.zxy);
      vec3 x1 = x0 - i1 + C.xxx;
      vec3 x2 = x0 - i2 + C.yyy;
      vec3 x3 = x0 - D.yyy;
      i = mod289(i);
      vec4 p = permute(permute(permute(
          i.z + vec4(0.0, i1.z, i2.z, 1.0))
        + i.y + vec4(0.0, i1.y, i2.y, 1.0))
        + i.x + vec4(0.0, i1.x, i2.x, 1.0));
      float n_ = 0.142857142857;
      vec3 ns = n_ * D.wyz - D.xzx;
      vec4 j = p - 49.0 * floor(p * ns.z * ns.z);
      vec4 x_ = floor(j * ns.z);
      vec4 y_ = floor(j - 7.0 * x_);
      vec4 x = x_ * ns.x + ns.yyyy;
      vec4 y = y_ * ns.x + ns.yyyy;
      vec4 h = 1.0 - abs(x) - abs(y);
      vec4 b0 = vec4(x.xy, y.xy);
      vec4 b1 = vec4(x.zw, y.zw);
      vec4 s0 = floor(b0) * 2.0 + 1.0;
      vec4 s1 = floor(b1) * 2.0 + 1.0;
      vec4 sh = -step(h, vec4(0.0));
      vec4 a0 = b0.xzyw + s0.xzyw * sh.xxyy;
      vec4 a1 = b1.xzyw + s1.xzyw * sh.zzww;
      vec3 p0 = vec3(a0.xy, h.x);
      vec3 p1 = vec3(a0.zw, h.y);
      vec3 p2 = vec3(a1.xy, h.z);
      vec3 p3 = vec3(a1.zw, h.w);
      vec4 norm = taylorInvSqrt(vec4(dot(p0, p0), dot(p1, p1), dot(p2, p2), dot(p3, p3)));
      p0 *= norm.x;
      p1 *= norm.y;
      p2 *= norm.z;
      p3 *= norm.w;
      vec4 m = max(0.5 - vec4(dot(x0, x0), dot(x1, x1), dot(x2, x2), dot(x3, x3)), 0.0);
      m = m * m;
      return 105.0 * dot(m * m, vec4(dot(p0, x0), dot(p1, x1), dot(p2, x2), dot(p3, x3)));
    }

    float surface(vec2 p) {
      float c = cos(uAngle);
      float s = sin(uAngle);
      mat2 rot = mat2(c, -s, s, c);
      vec2 rp = rot * p;
      float n1 = snoise(vec3(rp * uNoiseScale * 0.25, uTime * uSpeed * 0.7));
      float n2 = snoise(vec3(rp * uNoiseScale * 0.25 + vec2(21.4, 15.2), uTime * uSpeed * 0.9));
      float trig1 = sin(rp.x * uNoiseScale * 0.5 + uTime * uSpeed) * 0.3;
      float trig2 = cos(rp.y * uNoiseScale * 0.5 - uTime * uSpeed) * 0.3;
      vec2 flow = vec2(n1 + trig1, n2 + trig2);
      vec2 wp = rp + flow * (uWarpAmount * 0.12);
      float freq = uFoldFrequency * 0.5;
      float phase = sin(wp.y * freq + flow.y * 2.0) * uConnections;
      float mainWave = sin(wp.x * freq + phase * uWarpAmount * 0.3);
      float n3 = snoise(vec3(wp * 0.5, uTime * uSpeed * 0.5));
      return (mainWave * 0.85 + n3 * 0.15) * 0.5;
    }

    void main() {
      vec2 uv = gl_FragCoord.xy / uResolution.xy;
      vec2 p = uv * 2.0 - 1.0;
      p.x *= uResolution.x / uResolution.y;
      vec2 e = vec2(0.09, 0.0);
      float dx = (surface(p + e.xy) - surface(p - e.xy)) / (2.0 * e.x);
      float dy = (surface(p + e.yx) - surface(p - e.yx)) / (2.0 * e.x);
      float safeDepth = max(uDepth, 0.02);
      vec3 normal = normalize(vec3(-dx, -dy, safeDepth));
      float diffuse = dot(normal, normalize(uLightPos)) * 0.5 + 0.5;
      float t = clamp(diffuse + surface(p) * 0.04, 0.0, 1.0);
      t = t * t * (3.0 - 2.0 * t);
      vec3 color = mix(uColor1, uColor2, smoothstep(0.0, uShadowWidth + 0.15, t));
      color = mix(color, uColor3, smoothstep(uShadowWidth + 0.05, 0.65, t));
      color = mix(color, uColor4, smoothstep(0.55, 1.05, t));
      float grain = fract(sin(dot(uv.xy, vec2(12.9898, 78.233))) * 43758.5453);
      color += (grain - 0.5) * 0.03;
      gl_FragColor = vec4(color, 1.0);
    }
  `;

  const material = new THREE.ShaderMaterial({
    vertexShader,
    fragmentShader,
    uniforms: {
      uTime: { value: 0 },
      uResolution: { value: new THREE.Vector2(1, 1) },
      uColor1: { value: new THREE.Color(colors[0]) },
      uColor2: { value: new THREE.Color(colors[1]) },
      uColor3: { value: new THREE.Color(colors[2]) },
      uColor4: { value: new THREE.Color(colors[3]) },
      uDepth: { value: shared.depth },
      uLightPos: { value: new THREE.Vector3(shared.lightX, shared.lightY, 1) },
      uSpeed: { value: shared.speed },
      uNoiseScale: { value: shared.noiseScale },
      uWarpAmount: { value: shared.warpAmount },
      uFoldFrequency: { value: shared.foldFrequency },
      uAngle: { value: shared.angle },
      uConnections: { value: shared.connections },
      uShadowWidth: { value: shared.shadowWidth },
    },
  });

  scene.add(new THREE.Mesh(new THREE.PlaneGeometry(2, 2), material));

  const resize = () => {
    const width = window.innerWidth;
    const height = window.innerHeight;
    const maxPixelRatio = isLowPowerViewport() ? 1.15 : 2;
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, maxPixelRatio));
    renderer.setSize(width, height, false);
    material.uniforms.uResolution.value.set(width, height);
    if (prefersReducedMotion) {
      renderer.render(scene, camera);
    }
  };

  resize();
  window.addEventListener('resize', resize, { passive: true });
  root.classList.add('casehub-login-organic-ready');

  if (!prefersReducedMotion) {
    const clock = new THREE.Clock();
    const animate = () => {
      material.uniforms.uTime.value = clock.getElapsedTime();
      renderer.render(scene, camera);
      window.requestAnimationFrame(animate);
    };
    animate();
  }
    }
  }
}
