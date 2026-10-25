"""ui/background.py
Holographic Market Globe (Three.js) rendered behind the whole Streamlit app.

Public API:
    inject_3d_background()              call once, right after inject_theme()
    set_scene_mode(mode, ticker="")     mode: idle | research | bullish | neutral | bearish
                                        ticker: rotates the globe to that stock's exchange

Visual notes
- Flow pulses and satellites leave fading light trails.
- In result modes the globe drifts toward the right edge so it stays out of the text.
- The scene watches its own frame rate and sheds detail if the machine struggles.
- With prefers-reduced-motion it renders one still frame and never animates.
"""
import json
import re
import uuid

from ui.inject import inject_html as _inject

THREE_CDN = "https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"
SCENE_VERSION = 9  # bump this when you change the scene so browsers reload it

VALID_MODES = {"idle", "research", "bullish", "neutral", "bearish"}

_SCENE_JS = r"""
(function () {
  var VERSION = __VERSION__;
  var THREE = window.THREE;
  if (!THREE) return;

  // tear down any previous scene (dev reloads, older versions)
  if (window.__finBg && window.__finBg.destroy) { try { window.__finBg.destroy(); } catch (e) {} }
  var oc = document.getElementById('fin-bg-canvas'); if (oc) oc.remove();
  var oh = document.getElementById('fin-bg-hud'); if (oh) oh.remove();
  var ot = document.getElementById('fin-bg-tag'); if (ot) ot.remove();

  // ======================= SCENE CONFIG (tweak freely) =======================
  var CFG = {
    dust: 1000, dustMobile: 420,
    globeDots: 2400, globeDotsMobile: 1100,
    globeRadius: 3.8,
    parallax: 1.0,           // 0 disables mouse movement
    dprCap: 1.5              // lower = lighter on the GPU
  };
  // gx = how far right the globe sits, as a fraction of the visible half-width
  var MODES = {
    idle:     { color: 0x22D3EE, spin: 1.0, flow: 1.0, zoom: 14.0, halo: 0.18, gx: 0.50, label: 'SYSTEM ONLINE' },
    research: { color: 0x8B5CF6, spin: 3.4, flow: 3.2, zoom: 12.6, halo: 0.20, gx: 0.50, label: 'AGENTS RESEARCHING' },
    bullish:  { color: 0x10B981, spin: 1.0, flow: 1.7, zoom: 13.6, halo: 0.09, gx: 0.80, label: 'SENTIMENT BULLISH' },
    neutral:  { color: 0xF59E0B, spin: 0.8, flow: 1.0, zoom: 13.6, halo: 0.09, gx: 0.80, label: 'SENTIMENT NEUTRAL' },
    bearish:  { color: 0xF43F5E, spin: 0.8, flow: 1.4, zoom: 13.6, halo: 0.09, gx: 0.80, label: 'SENTIMENT BEARISH' }
  };
  var HUBS = [
    { id: 'NYC', name: 'New York',  ex: 'NYSE / NASDAQ', lat: 40.7,  lon: -74.0 },
    { id: 'TOR', name: 'Toronto',   ex: 'TSX',           lat: 43.7,  lon: -79.4 },
    { id: 'SAO', name: 'Sao Paulo', ex: 'B3',            lat: -23.5, lon: -46.6 },
    { id: 'LON', name: 'London',    ex: 'LSE',           lat: 51.5,  lon: -0.1 },
    { id: 'FRA', name: 'Frankfurt', ex: 'XETRA',         lat: 50.1,  lon: 8.7 },
    { id: 'DXB', name: 'Dubai',     ex: 'DFM',           lat: 25.2,  lon: 55.3 },
    { id: 'MUM', name: 'Mumbai',    ex: 'NSE / BSE',     lat: 19.1,  lon: 72.9 },
    { id: 'SIN', name: 'Singapore', ex: 'SGX',           lat: 1.35,  lon: 103.8 },
    { id: 'HKG', name: 'Hong Kong', ex: 'HKEX',          lat: 22.3,  lon: 114.2 },
    { id: 'SHA', name: 'Shanghai',  ex: 'SSE',           lat: 31.2,  lon: 121.5 },
    { id: 'TYO', name: 'Tokyo',     ex: 'TSE',           lat: 35.7,  lon: 139.7 },
    { id: 'SYD', name: 'Sydney',    ex: 'ASX',           lat: -33.9, lon: 151.2 }
  ];
  var ARCS = [
    ['NYC','LON'], ['NYC','TOR'], ['NYC','SAO'], ['LON','FRA'], ['LON','DXB'],
    ['FRA','MUM'], ['DXB','MUM'], ['MUM','SIN'], ['SIN','HKG'], ['HKG','SHA'],
    ['SHA','TYO'], ['TYO','SYD'], ['NYC','TYO'], ['LON','HKG'], ['SIN','SYD'], ['MUM','LON']
  ];
  // light-trail tuning: how far behind the head each tail dot sits, and how bright / big it is
  var TRAIL_OFF = [0.035, 0.07, 0.105];
  var TRAIL_OP  = [0.60, 0.34, 0.16];
  var TRAIL_SC  = [0.34, 0.27, 0.20];
  // ===========================================================================

  var reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var isMobile = window.innerWidth < 768;
  var R = CFG.globeRadius;
  var camZ = reduceMotion ? 14 : 26;   // starts far away, then flies in (cinematic intro)
  var curMode = null;
  var quality = 0;                     // 0 = full detail, 1 = lighter, 2 = lightest
  var trailsOn = true;

  // ---------- helpers ----------
  function ll(lat, lon, r) {
    var phi = lat * Math.PI / 180, lam = lon * Math.PI / 180;
    return new THREE.Vector3(r * Math.cos(phi) * Math.sin(lam), r * Math.sin(phi), r * Math.cos(phi) * Math.cos(lam));
  }
  function wrapAngle(d) {
    var t = 2 * Math.PI;
    return ((d + Math.PI) % t + t) % t - Math.PI;
  }
  function hubForTicker(t) {
    t = (t || '').toUpperCase();
    if (!t) return null;
    var m = t.match(/\.([A-Z]{1,3})$/);
    var map = { NS: 'MUM', BO: 'MUM', L: 'LON', DE: 'FRA', F: 'FRA', T: 'TYO', HK: 'HKG',
                SS: 'SHA', SZ: 'SHA', SI: 'SIN', AX: 'SYD', TO: 'TOR', V: 'TOR', SA: 'SAO' };
    if (m) return map[m[1]] || null;
    return 'NYC';
  }
  function makeSprite() {
    var c = document.createElement('canvas');
    c.width = c.height = 64;
    var g = c.getContext('2d');
    var grad = g.createRadialGradient(32, 32, 0, 32, 32, 32);
    grad.addColorStop(0, 'rgba(255,255,255,1)');
    grad.addColorStop(0.35, 'rgba(255,255,255,0.55)');
    grad.addColorStop(1, 'rgba(255,255,255,0)');
    g.fillStyle = grad;
    g.fillRect(0, 0, 64, 64);
    return new THREE.CanvasTexture(c);
  }

  // ---------- canvas + renderer ----------
  var canvas = document.createElement('canvas');
  canvas.id = 'fin-bg-canvas';
  canvas.style.cssText =
    'position:fixed;top:0;left:0;width:100vw;height:100vh;z-index:-1;' +
    'pointer-events:none;opacity:0;transition:opacity 1.6s ease;';
  document.body.appendChild(canvas);

  var renderer;
  try {
    renderer = new THREE.WebGLRenderer({ canvas: canvas, alpha: true, antialias: true });
  } catch (e) { canvas.remove(); return; }
  function dprNow() { return quality >= 1 ? 1 : Math.min(window.devicePixelRatio || 1, CFG.dprCap); }
  renderer.setPixelRatio(dprNow());
  renderer.setSize(window.innerWidth, window.innerHeight, false);

  var scene = new THREE.Scene();
  var camera = new THREE.PerspectiveCamera(60, window.innerWidth / window.innerHeight, 0.1, 120);
  camera.position.z = camZ;

  var sprite = makeSprite();

  // ---------- colour state (everything "tinted" follows the current mode) ----------
  var tinted = [];
  function tint(m) { tinted.push(m); return m; }
  var accent = new THREE.Color(MODES.idle.color);
  var targetColor = new THREE.Color(MODES.idle.color);
  var modeCfg = MODES.idle;
  var spinSpeed = 1, flowSpeed = 1;
  var focusIdx = -1;

  // ---------- distant dust (depth) ----------
  var DUST = isMobile ? CFG.dustMobile : CFG.dust;
  var dPos = new Float32Array(DUST * 3), dCol = new Float32Array(DUST * 3);
  var cA = new THREE.Color(0x22D3EE), cB = new THREE.Color(0x8B5CF6), cT = new THREE.Color();
  for (var i = 0; i < DUST; i++) {
    dPos[i * 3] = (Math.random() - 0.5) * 70;
    dPos[i * 3 + 1] = (Math.random() - 0.5) * 40;
    dPos[i * 3 + 2] = (Math.random() - 0.5) * 40 - 8;
    cT.copy(cA).lerp(cB, Math.random());
    dCol[i * 3] = cT.r; dCol[i * 3 + 1] = cT.g; dCol[i * 3 + 2] = cT.b;
  }
  var dGeo = new THREE.BufferGeometry();
  dGeo.setAttribute('position', new THREE.BufferAttribute(dPos, 3));
  dGeo.setAttribute('color', new THREE.BufferAttribute(dCol, 3));
  var dust = new THREE.Points(dGeo, new THREE.PointsMaterial({
    size: 0.26, map: sprite, vertexColors: true, transparent: true, opacity: 0.55,
    depthWrite: false, blending: THREE.AdditiveBlending
  }));
  scene.add(dust);

  // ---------- globe ----------
  var globe = new THREE.Group();
  globe.position.set(0, isMobile ? 5.5 : -3.0, isMobile ? -9 : -5);
  scene.add(globe);

  // where the globe should sit horizontally (desktop): a fraction of the visible half-width
  function globeTargetX() {
    var halfW = Math.tan(camera.fov * Math.PI / 360) * (camZ - globe.position.z) * camera.aspect;
    return halfW * modeCfg.gx;
  }

  // dark translucent body (also hides the far-side lines)
  var body = new THREE.Mesh(
    new THREE.SphereGeometry(R * 0.985, 48, 32),
    new THREE.MeshBasicMaterial({ color: 0x040815, transparent: true, opacity: 0.78 })
  );
  body.renderOrder = 0;
  globe.add(body);

  // halo glow behind the globe
  var haloMat = tint(new THREE.SpriteMaterial({
    map: sprite, color: 0xffffff, transparent: true, opacity: 0.18,
    depthWrite: false, blending: THREE.AdditiveBlending
  }));
  var haloLevel = 0.18;   // softly dims while a report is on screen so text stays crisp
  var halo = new THREE.Sprite(haloMat);
  halo.scale.set(R * 5, R * 5, 1);
  halo.renderOrder = 0;
  globe.add(halo);

  // graticule (lat/long grid)
  var gp = [];
  function addPolyline(pts) {
    for (var k = 0; k < pts.length - 1; k++) {
      gp.push(pts[k].x, pts[k].y, pts[k].z, pts[k + 1].x, pts[k + 1].y, pts[k + 1].z);
    }
  }
  var lat, lon, pts;
  for (lat = -60; lat <= 60; lat += 30) {
    pts = []; for (lon = 0; lon <= 360; lon += 6) pts.push(ll(lat, lon, R));
    addPolyline(pts);
  }
  for (lon = 0; lon < 360; lon += 30) {
    pts = []; for (lat = -90; lat <= 90; lat += 6) pts.push(ll(lat, lon, R));
    addPolyline(pts);
  }
  var gGeo = new THREE.BufferGeometry();
  gGeo.setAttribute('position', new THREE.Float32BufferAttribute(gp, 3));
  var grid = new THREE.LineSegments(gGeo, tint(new THREE.LineBasicMaterial({
    color: 0xffffff, transparent: true, opacity: 0.17, depthWrite: false, blending: THREE.AdditiveBlending
  })));
  grid.renderOrder = 1;
  globe.add(grid);

  // dot-matrix surface (fibonacci sphere)
  var DN = isMobile ? CFG.globeDotsMobile : CFG.globeDots;
  var sp = new Float32Array(DN * 3), ga = Math.PI * (3 - Math.sqrt(5));
  for (var s = 0; s < DN; s++) {
    var y = 1 - (s / (DN - 1)) * 2, rr = Math.sqrt(1 - y * y), th = ga * s;
    sp[s * 3] = Math.cos(th) * rr * R * 1.002;
    sp[s * 3 + 1] = y * R * 1.002;
    sp[s * 3 + 2] = Math.sin(th) * rr * R * 1.002;
  }
  var sGeo = new THREE.BufferGeometry();
  sGeo.setAttribute('position', new THREE.BufferAttribute(sp, 3));
  var dots = new THREE.Points(sGeo, tint(new THREE.PointsMaterial({
    size: 0.075, map: sprite, color: 0xffffff, transparent: true, opacity: 0.7,
    depthWrite: false, blending: THREE.AdditiveBlending
  })));
  dots.renderOrder = 2;
  globe.add(dots);

  // fresnel rim glow (holographic edge)
  var rimUniforms = { uColor: { value: new THREE.Color(MODES.idle.color) }, uPower: { value: 2.4 } };
  var rim = new THREE.Mesh(
    new THREE.SphereGeometry(R * 1.02, 64, 48),
    new THREE.ShaderMaterial({
      uniforms: rimUniforms,
      vertexShader:
        'varying vec3 vN; varying vec3 vV;' +
        'void main(){ vN = normalize(normalMatrix * normal);' +
        'vec4 mv = modelViewMatrix * vec4(position,1.0); vV = normalize(-mv.xyz);' +
        'gl_Position = projectionMatrix * mv; }',
      fragmentShader:
        'uniform vec3 uColor; uniform float uPower; varying vec3 vN; varying vec3 vV;' +
        'void main(){ float f = pow(1.0 - max(dot(normalize(vN), normalize(vV)), 0.0), uPower);' +
        'gl_FragColor = vec4(uColor * f * 1.4, f); }',
      transparent: true, depthWrite: false, blending: THREE.AdditiveBlending
    })
  );
  rim.renderOrder = 3;
  globe.add(rim);
  tinted.push({ color: rimUniforms.uColor.value });

  // orbit rings + satellites (each satellite drags a short light trail)
  function makeOrbit(radius, tiltX, tiltY, opacity) {
    var m = new THREE.Mesh(
      new THREE.TorusGeometry(radius, 0.01, 6, 200),
      tint(new THREE.MeshBasicMaterial({
        color: 0xffffff, transparent: true, opacity: opacity, depthWrite: false, blending: THREE.AdditiveBlending
      }))
    );
    m.rotation.x = tiltX; m.rotation.y = tiltY;
    var sat = new THREE.Sprite(tint(new THREE.SpriteMaterial({
      map: sprite, color: 0xffffff, transparent: true, opacity: 0.95, depthWrite: false, blending: THREE.AdditiveBlending
    })));
    sat.scale.set(0.5, 0.5, 1);
    m.add(sat);
    var trail = [];
    for (var k = 1; k <= 3; k++) {
      var tm = tint(new THREE.SpriteMaterial({
        map: sprite, color: 0xffffff, transparent: true, opacity: 0.5 / k, depthWrite: false, blending: THREE.AdditiveBlending
      }));
      var ts = new THREE.Sprite(tm);
      ts.scale.set(0.5 - k * 0.1, 0.5 - k * 0.1, 1);
      m.add(ts);
      trail.push({ sp: ts, k: k });
    }
    globe.add(m);
    return { mesh: m, sat: sat, trail: trail, radius: radius, a: Math.random() * 6.28 };
  }
  var orbits = [makeOrbit(R * 1.45, Math.PI / 2.5, 0.2, 0.3), makeOrbit(R * 1.72, Math.PI / 1.9, -0.5, 0.18)];

  // exchange hubs
  var beacon = [];
  var hubs = HUBS.map(function (h, idx) {
    var n = ll(h.lat, h.lon, 1);
    var dotM = tint(new THREE.SpriteMaterial({
      map: sprite, color: 0xffffff, transparent: true, opacity: 0.95, depthWrite: false, blending: THREE.AdditiveBlending
    }));
    var dot = new THREE.Sprite(dotM);
    dot.position.copy(n.clone().multiplyScalar(R * 1.025));
    dot.scale.set(0.34, 0.34, 1);
    globe.add(dot);

    var ringM = tint(new THREE.MeshBasicMaterial({
      color: 0xffffff, transparent: true, opacity: 0.6, side: THREE.DoubleSide,
      depthWrite: false, blending: THREE.AdditiveBlending
    }));
    var ring = new THREE.Mesh(new THREE.RingGeometry(0.16, 0.2, 40), ringM);
    ring.position.copy(n.clone().multiplyScalar(R * 1.008));
    ring.quaternion.setFromUnitVectors(new THREE.Vector3(0, 0, 1), n);
    globe.add(ring);

    var b0 = n.clone().multiplyScalar(R), b1 = n.clone().multiplyScalar(R * 1.09);
    beacon.push(b0.x, b0.y, b0.z, b1.x, b1.y, b1.z);
    return { n: n, dot: dot, ring: ring, ringM: ringM, f: 0, idx: idx };
  });
  var bGeo = new THREE.BufferGeometry();
  bGeo.setAttribute('position', new THREE.Float32BufferAttribute(beacon, 3));
  globe.add(new THREE.LineSegments(bGeo, tint(new THREE.LineBasicMaterial({
    color: 0xffffff, transparent: true, opacity: 0.6, depthWrite: false, blending: THREE.AdditiveBlending
  }))));

  // capital-flow arcs with travelling pulses and fading light trails
  var idIndex = {};
  HUBS.forEach(function (h, i) { idIndex[h.id] = i; });
  var arcs = ARCS.map(function (pair) {
    var A = hubs[idIndex[pair[0]]], B = hubs[idIndex[pair[1]]];
    var ang = A.n.angleTo(B.n);
    var mid = A.n.clone().add(B.n);
    if (mid.lengthSq() < 1e-6) mid.set(0, 1, 0);
    mid.normalize();
    var pa = A.n.clone().multiplyScalar(R * 1.01), pb = B.n.clone().multiplyScalar(R * 1.01);
    var pc = mid.multiplyScalar(R * (1.1 + ang * 0.4));
    var curve = new THREE.QuadraticBezierCurve3(pa, pc, pb);
    var geo = new THREE.BufferGeometry().setFromPoints(curve.getPoints(60));
    var mat = tint(new THREE.LineBasicMaterial({
      color: 0xffffff, transparent: true, opacity: 0.25, depthWrite: false, blending: THREE.AdditiveBlending
    }));
    globe.add(new THREE.Line(geo, mat));
    var pm = tint(new THREE.SpriteMaterial({
      map: sprite, color: 0xffffff, transparent: true, opacity: 1, depthWrite: false, blending: THREE.AdditiveBlending
    }));
    var p = new THREE.Sprite(pm);
    p.scale.set(0.42, 0.42, 1);
    globe.add(p);
    var trail = TRAIL_OFF.map(function (off, k) {
      var tm = tint(new THREE.SpriteMaterial({
        map: sprite, color: 0xffffff, transparent: true, opacity: 0, depthWrite: false, blending: THREE.AdditiveBlending
      }));
      var ts = new THREE.Sprite(tm);
      ts.scale.set(TRAIL_SC[k], TRAIL_SC[k], 1);
      globe.add(ts);
      return { sp: ts, m: tm, off: off, k: k };
    });
    return { curve: curve, mat: mat, p: p, pm: pm, trail: trail, t: Math.random(), speed: 0.7 + Math.random() * 0.6, A: A, B: B };
  });

  // ---------- agent scanner ring (sweeps the globe while agents research) ----------
  var scanM = tint(new THREE.MeshBasicMaterial({
    color: 0xffffff, transparent: true, opacity: 0, side: THREE.DoubleSide,
    depthWrite: false, blending: THREE.AdditiveBlending
  }));
  var scan = new THREE.Mesh(new THREE.TorusGeometry(1, 0.008, 6, 160), scanM);
  scan.rotation.x = Math.PI / 2;
  scan.renderOrder = 4;
  scan.visible = false;
  globe.add(scan);
  var scanLevel = 0;

  // ---------- result shockwave (fires when a sentiment verdict lands) ----------
  var waveM = tint(new THREE.MeshBasicMaterial({
    color: 0xffffff, transparent: true, opacity: 0, side: THREE.DoubleSide,
    depthWrite: false, blending: THREE.AdditiveBlending
  }));
  var wave = new THREE.Mesh(new THREE.RingGeometry(0.988, 1, 96), waveM);
  wave.visible = false;
  wave.renderOrder = 4;
  scene.add(wave);
  var waveT = -1;

  // ---------- HUD ----------
  var hud = null;
  if (!isMobile) {
    hud = document.createElement('div');
    hud.id = 'fin-bg-hud';
    hud.style.cssText =
      'position:fixed;top:72px;right:28px;z-index:1;pointer-events:none;text-align:right;' +
      'font:600 11px/1.7 "Manrope",ui-monospace,monospace;letter-spacing:.16em;color:#9AA3B8;' +
      'opacity:0;transition:opacity .8s ease;';
    document.body.appendChild(hud);
  }
  // floating callout that tracks the focused exchange (sits behind the glass cards)
  var tag = null;
  if (!isMobile) {
    tag = document.createElement('div');
    tag.id = 'fin-bg-tag';
    tag.style.cssText =
      'position:fixed;left:0;top:0;z-index:-1;pointer-events:none;white-space:nowrap;' +
      'font:600 10px/1 "Manrope",ui-monospace,monospace;letter-spacing:.14em;color:#E8ECF4;' +
      'padding:5px 9px;border:1px solid #22D3EE;border-radius:6px;background:rgba(7,10,18,.65);' +
      'opacity:0;transition:opacity .35s ease;will-change:transform;';
    document.body.appendChild(tag);
  }
  function updateHud() {
    var hex = '#' + new THREE.Color(modeCfg.color).getHexString();
    var hub = focusIdx >= 0 ? HUBS[focusIdx] : null;
    if (tag) {
      tag.style.borderColor = hex;
      tag.textContent = hub ? '\u25B8 ' + hub.ex + ' \u00B7 ' + hub.name.toUpperCase() : '';
    }
    if (!hud) return;
    hud.innerHTML =
      '<div style="color:' + hex + '">\u25CF ' + modeCfg.label + '</div>' +
      '<div>' + (hub ? hub.ex + ' \u00B7 ' + hub.name.toUpperCase() : 'GLOBAL MARKET LINK') + '</div>';
  }

  // ---------- performance: shed detail if the machine struggles ----------
  function applyQuality() {
    renderer.setPixelRatio(dprNow());
    renderer.setSize(window.innerWidth, window.innerHeight, false);
    if (quality >= 2) {
      dust.visible = false;
      halo.visible = false;
      trailsOn = false;
      for (var a = 0; a < arcs.length; a++) {
        for (var t = 0; t < arcs[a].trail.length; t++) arcs[a].trail[t].sp.visible = false;
      }
      for (var o = 0; o < orbits.length; o++) {
        for (var q = 0; q < orbits[o].trail.length; q++) orbits[o].trail[q].sp.visible = false;
      }
    }
  }

  // ---------- public API ----------
  function setMode(mode, ticker) {
    var key = MODES[mode] ? mode : 'idle';
    if (!reduceMotion && curMode !== key && (key === 'bullish' || key === 'neutral' || key === 'bearish')) {
      waveT = 0;   // verdict landed: fire the shockwave
    }
    curMode = key;
    modeCfg = MODES[key];
    targetColor.setHex(modeCfg.color);
    if (typeof ticker === 'string') {
      var id = hubForTicker(ticker);
      focusIdx = -1;
      if (id) { for (var q = 0; q < HUBS.length; q++) { if (HUBS[q].id === id) focusIdx = q; } }
    }
    updateHud();
    if (reduceMotion) {
      accent.copy(targetColor);
      camZ = modeCfg.zoom;
      if (!isMobile) globe.position.x = globeTargetX();
      draw();
    }
  }

  // ---------- input + resize ----------
  var mx = 0, my = 0, tx = 0, ty = 0;
  function onMove(e) {
    tx = (e.clientX / window.innerWidth - 0.5) * 2;
    ty = (e.clientY / window.innerHeight - 0.5) * 2;
  }
  function onResize() {
    camera.aspect = window.innerWidth / window.innerHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(window.innerWidth, window.innerHeight, false);
    if (!isMobile && reduceMotion) { globe.position.x = globeTargetX(); draw(); }
  }
  window.addEventListener('mousemove', onMove, { passive: true });
  window.addEventListener('resize', onResize);

  // ---------- render loop ----------
  var clock = new THREE.Clock();
  var time = 0, destroyed = false, raf = 0;
  var lastT = 0, accMs = 0, frames = 0;
  var tmpV = new THREE.Vector3(), wpos = new THREE.Vector3(), nrm = new THREE.Vector3(),
      tcam = new THREE.Vector3(), projV = new THREE.Vector3();

  function draw() {
    var dt = Math.min(clock.getDelta(), 0.05);
    time += dt;
    var ease = Math.min(1, dt * 2.2);

    // mode transitions
    accent.lerp(targetColor, Math.min(1, dt * 3));
    spinSpeed += (modeCfg.spin - spinSpeed) * Math.min(1, dt * 2);
    flowSpeed += (modeCfg.flow - flowSpeed) * Math.min(1, dt * 2);
    for (var i = 0; i < tinted.length; i++) tinted[i].color.copy(accent);
    haloLevel += (modeCfg.halo - haloLevel) * Math.min(1, dt * 2);
    haloMat.opacity = haloLevel;

    // parallax + cinematic dolly
    var k = CFG.parallax;
    mx += (tx - mx) * Math.min(1, dt * 3);
    my += (ty - my) * Math.min(1, dt * 3);
    dust.rotation.y = time * 0.012 + mx * 0.1 * k;
    dust.rotation.x = my * 0.05 * k;
    camZ += (modeCfg.zoom - camZ) * Math.min(1, dt * 1.2);
    camera.position.z = camZ;
    camera.position.x = mx * 1.1 * k;
    camera.position.y = -my * 0.7 * k;
    camera.lookAt(0, 0, 0);

    // the globe drifts toward the right edge once a report is on screen (desktop)
    if (!isMobile) {
      globe.position.x += (globeTargetX() - globe.position.x) * Math.min(1, dt * 1.6);
    }

    // globe rotation: free spin, or turn to face the focused exchange
    var tgtX = 0.3;
    if (focusIdx >= 0) {
      var hb = HUBS[focusIdx];
      var d = wrapAngle(-hb.lon * Math.PI / 180 - globe.rotation.y);
      globe.rotation.y += d * ease;
      tgtX = hb.lat * Math.PI / 180 * 0.6;
    } else {
      globe.rotation.y += dt * 0.12 * spinSpeed;
    }
    globe.rotation.x += (tgtX - globe.rotation.x) * ease;
    var tgtS = focusIdx >= 0 ? 1.08 : 1;
    globe.scale.setScalar(globe.scale.x + (tgtS - globe.scale.x) * ease);

    // orbit rings + satellites + their trails
    for (var o = 0; o < orbits.length; o++) {
      var ob = orbits[o], dir = o ? -1 : 1;
      ob.a += dt * (0.35 + o * 0.15) * dir;
      ob.sat.position.set(Math.cos(ob.a) * ob.radius, Math.sin(ob.a) * ob.radius, 0);
      if (trailsOn) {
        for (var q = 0; q < ob.trail.length; q++) {
          var back = ob.a - dir * 0.13 * ob.trail[q].k;
          ob.trail[q].sp.position.set(Math.cos(back) * ob.radius, Math.sin(back) * ob.radius, 0);
        }
      }
    }

    // hubs
    for (var h = 0; h < hubs.length; h++) {
      var hub = hubs[h];
      hub.f += ((h === focusIdx ? 1 : 0) - hub.f) * Math.min(1, dt * 4);
      var ph = (time * (0.5 + hub.f * 0.7) + h * 0.37) % 1;
      hub.ring.scale.setScalar(1 + ph * (2.6 + hub.f * 2.2));
      hub.ringM.opacity = (1 - ph) * (0.35 + hub.f * 0.65);
      var ds = 0.3 + hub.f * 0.42;
      hub.dot.scale.set(ds, ds, 1);
    }

    // arcs + pulses + light trails
    for (var a = 0; a < arcs.length; a++) {
      var ar = arcs[a];
      ar.t = (ar.t + dt * 0.16 * flowSpeed * ar.speed) % 1;
      ar.curve.getPoint(ar.t, tmpV);
      ar.p.position.copy(tmpV);
      ar.pm.opacity = Math.sin(Math.PI * ar.t);
      ar.mat.opacity = 0.2 + 0.4 * Math.max(ar.A.f, ar.B.f);
      if (trailsOn) {
        for (var n = 0; n < ar.trail.length; n++) {
          var tr = ar.trail[n], tt = ar.t - tr.off;
          if (tt <= 0) { tr.m.opacity = 0; continue; }
          ar.curve.getPoint(tt, tmpV);
          tr.sp.position.copy(tmpV);
          tr.m.opacity = TRAIL_OP[tr.k] * Math.sin(Math.PI * tt);
        }
      }
    }

    // scanner ring: sweeps pole to pole only while agents are researching
    scanLevel += ((modeCfg === MODES.research ? 1 : 0) - scanLevel) * Math.min(1, dt * 3);
    scan.visible = scanLevel > 0.01;
    if (scan.visible) {
      var sy = Math.sin(time * 1.3) * R * 0.92;
      var sr = Math.sqrt(Math.max(R * R - sy * sy, 0)) * 1.012;
      scan.position.y = sy;
      scan.scale.set(sr, sr, 1);
      scanM.opacity = 0.85 * scanLevel;
    }

    // verdict shockwave
    if (waveT >= 0) {
      waveT += dt / 1.6;
      if (waveT >= 1) { waveT = -1; wave.visible = false; }
      else {
        wave.visible = true;
        wave.position.copy(globe.position);
        var ws = R * (1.1 + waveT * 1.7) * globe.scale.x;
        wave.scale.set(ws, ws, 1);
        waveM.opacity = 0.5 * (1 - waveT) * (1 - waveT);
      }
    }

    // exchange callout follows the focused hub (hidden when it rotates to the far side)
    if (tag) {
      if (focusIdx >= 0) {
        hubs[focusIdx].dot.getWorldPosition(wpos);
        nrm.copy(wpos).sub(globe.position).normalize();
        tcam.copy(camera.position).sub(wpos).normalize();
        projV.copy(wpos).project(camera);
        var px = (projV.x * 0.5 + 0.5) * window.innerWidth;
        var py = (-projV.y * 0.5 + 0.5) * window.innerHeight;
        tag.style.transform = 'translate(' + (px + 18).toFixed(1) + 'px,' + (py - 34).toFixed(1) + 'px)';
        tag.style.opacity = nrm.dot(tcam) > 0.2 ? '1' : '0';
      } else {
        tag.style.opacity = '0';
      }
    }

    renderer.render(scene, camera);
  }

  function loop() {
    if (destroyed) return;
    raf = requestAnimationFrame(loop);
    if (document.hidden) { lastT = 0; return; }          // pause completely in a background tab
    var now = performance.now();
    if (lastT) {                                         // frame-rate watchdog
      accMs += now - lastT; frames++;
      if (frames >= 90) {
        if (accMs / frames > 34 && quality < 2) { quality++; applyQuality(); }   // slower than ~30 fps
        accMs = 0; frames = 0;
      }
    }
    lastT = now;
    draw();
  }

  function destroy() {
    destroyed = true;
    cancelAnimationFrame(raf);
    window.removeEventListener('mousemove', onMove);
    window.removeEventListener('resize', onResize);
    try { renderer.dispose(); } catch (e) {}
    canvas.remove();
    if (hud) hud.remove();
    if (tag) tag.remove();
  }

  window.__finBg = { version: VERSION, setMode: setMode, destroy: destroy };

  var pend = window.__finBgPending;
  setMode(pend ? pend.mode : 'idle', pend ? pend.ticker : '');
  accent.copy(targetColor);
  if (!isMobile) globe.position.x = globeTargetX();      // start in place, no sideways slide
  draw();
  requestAnimationFrame(function () {
    canvas.style.opacity = '1';
    if (hud) hud.style.opacity = '1';
  });
  if (!reduceMotion) loop();
})();
"""

_LOADER = """
<script>
(function () {
  var P = window.parent;
  if (!P) return;
  var V = __VERSION__;
  if (P.__finBg && P.__finBg.version === V) return;
  if (P.__finBgLoading === V) return;
  P.__finBgLoading = V;
  var D = P.document;
  function run() {
    var old = D.getElementById('fin-bg-script');
    if (old) old.remove();
    var s = D.createElement('script');
    s.id = 'fin-bg-script';
    s.textContent = __SRC__;
    D.head.appendChild(s);
    P.__finBgLoading = 0;
  }
  if (P.THREE) { run(); return; }
  var t = D.createElement('script');
  t.src = __CDN__;
  t.onload = run;
  t.onerror = function () { P.__finBgLoading = 0; };
  D.head.appendChild(t);
})();
</script>
"""

_SET_MODE = """
<script>
(function () {
  var P = window.parent;
  var d = __PAYLOAD__;
  P.__finBgPending = d;
  if (P.__finBg && P.__finBg.setMode) { P.__finBg.setMode(d.mode, d.ticker); }
})();
/*__NONCE__*/
</script>
"""


def inject_3d_background() -> None:
    """Inject the Market Globe scene into the main page. Safe to call on every rerun."""
    src = _SCENE_JS.replace("__VERSION__", str(SCENE_VERSION))
    html = (
        _LOADER.replace("__VERSION__", str(SCENE_VERSION))
        .replace("__SRC__", json.dumps(src))
        .replace("__CDN__", json.dumps(THREE_CDN))
    )
    _inject(html)


def set_scene_mode(mode: str = "idle", ticker: str = "") -> None:
    """Drive the 3D scene from Python.

    mode:   idle | research | bullish | neutral | bearish
    ticker: e.g. 'AAPL' or 'TCS.NS' -> the globe rotates to that exchange ('' clears focus)
    """
    mode = mode if mode in VALID_MODES else "idle"
    ticker = re.sub(r"[^A-Za-z0-9.^-]", "", ticker or "")[:15]
    payload = json.dumps({"mode": mode, "ticker": ticker})
    # unique nonce so Streamlit never reuses an identical iframe (which would skip the script)
    html = _SET_MODE.replace("__PAYLOAD__", payload).replace("__NONCE__", uuid.uuid4().hex)
    _inject(html)