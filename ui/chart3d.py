"""ui/chart3d.py
Interactive 3D candlestick explorer (Three.js), rendered inside the report card.

Public API:
    render_chart_3d(ticker)
"""
import json

import streamlit as st
import streamlit.components.v1 as components
import yfinance as yf

THREE_CDN = "https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"


@st.cache_data(ttl=600, show_spinner=False)
def _load_history(ticker: str) -> list:
    """6 months of daily OHLCV as plain dicts. Returns [] on any failure."""
    try:
        hist = yf.Ticker(ticker).history(period="6mo")
    except Exception:
        return []
    if hist is None or hist.empty:
        return []
    hist = hist.dropna(subset=["Open", "High", "Low", "Close"])
    rows = []
    for ts, r in hist.iterrows():
        vol = r["Volume"]
        rows.append({
            "d": ts.strftime("%d %b %Y"),
            "o": round(float(r["Open"]), 2),
            "h": round(float(r["High"]), 2),
            "l": round(float(r["Low"]), 2),
            "c": round(float(r["Close"]), 2),
            "v": int(vol) if vol == vol else 0,
        })
    return rows


_TEMPLATE = r"""<!doctype html>
<html><head><meta charset="utf-8">
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600&family=Space+Grotesk:wght@600&display=swap');
html,body{margin:0;height:100%;background:transparent;overflow:hidden;font-family:'Inter',system-ui,sans-serif;}
#wrap{position:relative;width:100%;height:100%;border-radius:16px;overflow:hidden;
  border:1px solid rgba(255,255,255,.09);
  background:radial-gradient(900px 400px at 50% 0%,rgba(34,211,238,.10),transparent 60%),
             radial-gradient(700px 400px at 100% 100%,rgba(139,92,246,.12),transparent 60%),
             rgba(8,12,22,.72);}
#c{display:block;width:100%;height:100%;cursor:grab;touch-action:pan-y;}
#c.drag{cursor:grabbing;}
.hud{position:absolute;left:14px;top:12px;pointer-events:none;color:#E6EAF2;}
.hud b{font-family:'Space Grotesk',sans-serif;font-size:15px;letter-spacing:.02em;}
.hud span{display:block;margin-top:3px;font-size:10.5px;color:#8B93A7;letter-spacing:.08em;}
.legend{position:absolute;right:14px;top:12px;pointer-events:none;font-size:11px;color:#8B93A7;display:flex;gap:12px;}
.legend i{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:5px;}
#tip{position:absolute;left:0;top:0;pointer-events:none;opacity:0;transition:opacity .12s;
  padding:8px 10px;border-radius:10px;background:rgba(7,10,18,.92);
  border:1px solid rgba(34,211,238,.45);font-size:11.5px;line-height:1.6;color:#E6EAF2;
  white-space:nowrap;box-shadow:0 8px 24px -8px rgba(0,0,0,.7);}
.msg{display:grid;place-items:center;height:100%;color:#8B93A7;font-size:13px;}
</style></head>
<body>
<div id="wrap">
  <canvas id="c"></canvas>
  <div class="hud"><b id="ttl"></b><span>6 MONTHS · DRAG TO ROTATE · HOVER A CANDLE</span></div>
  <div class="legend">
    <div><i style="background:#10B981"></i>Up</div>
    <div><i style="background:#F43F5E"></i>Down</div>
    <div><i style="background:#8B5CF6"></i>20-day avg</div>
  </div>
  <div id="tip"></div>
</div>
<script src="__CDN__"></script>
<script>
(function () {
  var P = __PAYLOAD__;
  var rows = P.rows, N = rows.length, cur = P.cur;
  var wrap = document.getElementById('wrap');
  var canvas = document.getElementById('c');
  var tip = document.getElementById('tip');
  document.getElementById('ttl').textContent = P.ticker + ' \u00B7 3D MARKET VIEW';

  function fail(t) { wrap.innerHTML = '<div class="msg">' + t + '</div>'; }
  if (!window.THREE) { fail('3D view unavailable (could not load the 3D library)'); return; }
  if (N < 3) { fail('Not enough price history for 3D view'); return; }

  var reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var renderer;
  try { renderer = new THREE.WebGLRenderer({ canvas: canvas, alpha: true, antialias: true }); }
  catch (e) { fail('3D view unavailable (WebGL not supported)'); return; }
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));

  var scene = new THREE.Scene();
  var camera = new THREE.PerspectiveCamera(42, 2, 0.1, 100);
  var root = new THREE.Group();
  scene.add(root);

  // ---------- layout constants + scales ----------
  var W = 16, PY0 = -1.0, PY1 = 3.0, VY0 = -3.0, VMAX = 1.5;
  var minP = Infinity, maxP = -Infinity, maxV = 1, i, r;
  for (i = 0; i < N; i++) {
    r = rows[i];
    if (r.l < minP) minP = r.l;
    if (r.h > maxP) maxP = r.h;
    if (r.v > maxV) maxV = r.v;
  }
  var pad = (maxP - minP) * 0.04 || 1;
  minP -= pad; maxP += pad;
  function yP(p) { return PY0 + (p - minP) / (maxP - minP) * (PY1 - PY0); }
  function xI(k) { return (k / (N - 1) - 0.5) * W; }
  function f2(v) { return cur + v.toFixed(2); }
  function fPrice(v) { return cur + (v >= 1000 ? Math.round(v).toLocaleString('en-US') : v.toFixed(2)); }
  function fVol(v) {
    return v >= 1e9 ? (v / 1e9).toFixed(2) + 'B' : v >= 1e6 ? (v / 1e6).toFixed(2) + 'M' : v >= 1e3 ? (v / 1e3).toFixed(1) + 'K' : String(v);
  }

  // ---------- candles + volume ----------
  var UP = 0x10B981, DN = 0xF43F5E;
  var box = new THREE.BoxGeometry(1, 1, 1);
  box.translate(0, 0.5, 0);                    // origin at the base, so scale.y grows upward
  var edgesGeo = new THREE.EdgesGeometry(box);
  function mat(c, o) {
    return new THREE.MeshBasicMaterial({ color: c, transparent: true, opacity: o, depthWrite: false, blending: THREE.AdditiveBlending });
  }
  var bodyUp = mat(UP, 0.38), bodyDn = mat(DN, 0.38);
  var wickUp = mat(UP, 0.9), wickDn = mat(DN, 0.9);
  var volUp = mat(UP, 0.22), volDn = mat(DN, 0.22);
  var edgeUp = new THREE.LineBasicMaterial({ color: UP, transparent: true, opacity: 0.95 });
  var edgeDn = new THREE.LineBasicMaterial({ color: DN, transparent: true, opacity: 0.95 });

  var cw = W / N * 0.62;
  var bodies = [], parts = [];
  for (i = 0; i < N; i++) {
    r = rows[i];
    var up = r.c >= r.o, x = xI(i);
    var top = yP(Math.max(r.o, r.c)), bot = yP(Math.min(r.o, r.c));

    var body = new THREE.Mesh(box, up ? bodyUp : bodyDn);
    body.position.set(x, bot, 0);
    body.scale.set(cw, 0.0001, 0.42);
    body.userData = { i: i, h: Math.max(top - bot, 0.04) };
    body.add(new THREE.LineSegments(edgesGeo, up ? edgeUp : edgeDn));
    root.add(body); bodies.push(body); parts.push(body);

    var yl = yP(r.l), yh = yP(r.h);
    var wick = new THREE.Mesh(box, up ? wickUp : wickDn);
    wick.position.set(x, yl, 0);
    wick.scale.set(cw * 0.1, 0.0001, cw * 0.1);
    wick.userData = { i: i, h: Math.max(yh - yl, 0.02) };
    root.add(wick); parts.push(wick);

    var vb = new THREE.Mesh(box, up ? volUp : volDn);
    vb.position.set(x, VY0, 0);
    vb.scale.set(cw, 0.0001, 0.42);
    vb.userData = { i: i, h: Math.max(r.v / maxV * VMAX, 0.02) };
    root.add(vb); parts.push(vb);
  }

  // ---------- price wall, glowing close line, 20-day average ----------
  var lineMats = [];
  function glowMat(color, op) {
    var m = new THREE.MeshBasicMaterial({ color: color, transparent: true, opacity: op, depthWrite: false, blending: THREE.AdditiveBlending, side: THREE.DoubleSide });
    lineMats.push({ m: m, base: op });
    return m;
  }
  function tube(pts, color, rad, op) {
    var curve = new THREE.CatmullRomCurve3(pts);
    return new THREE.Mesh(new THREE.TubeGeometry(curve, Math.max(pts.length * 2, 8), rad, 6, false), glowMat(color, op));
  }
  var ZW = -1.0, closePts = [], maPts = [], pos = [], idx = [], sum = 0;
  for (i = 0; i < N; i++) {
    var cy = yP(rows[i].c);
    closePts.push(new THREE.Vector3(xI(i), cy, ZW));
    pos.push(xI(i), cy, ZW, xI(i), PY0 - 0.15, ZW);
    if (i < N - 1) { var a = i * 2; idx.push(a, a + 1, a + 2, a + 1, a + 3, a + 2); }
    sum += rows[i].c;
    if (i >= 20) sum -= rows[i - 20].c;
    if (i >= 19) maPts.push(new THREE.Vector3(xI(i), yP(sum / 20), 0.35));
  }
  var sg = new THREE.BufferGeometry();
  sg.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
  sg.setIndex(idx);
  root.add(new THREE.Mesh(sg, glowMat(0x22D3EE, 0.07)));
  root.add(tube(closePts, 0x22D3EE, 0.09, 0.12));
  root.add(tube(closePts, 0x22D3EE, 0.028, 0.95));
  if (maPts.length >= 2) {
    root.add(tube(maPts, 0x8B5CF6, 0.1, 0.12));
    root.add(tube(maPts, 0x8B5CF6, 0.035, 0.95));
  }

  // ---------- floor grid + horizontal price guides ----------
  var grid = new THREE.GridHelper(22, 22, 0x22D3EE, 0x22D3EE);
  grid.position.y = VY0 - 0.02;
  grid.material.transparent = true;
  grid.material.opacity = 0.14;
  grid.material.depthWrite = false;
  root.add(grid);

  var gl = [];
  [0, 0.33, 0.66, 1].forEach(function (fr) {
    var gy = PY0 + fr * (PY1 - PY0);
    gl.push(-W / 2, gy, -1.3, W / 2, gy, -1.3);
  });
  var glg = new THREE.BufferGeometry();
  glg.setAttribute('position', new THREE.Float32BufferAttribute(gl, 3));
  root.add(new THREE.LineSegments(glg, new THREE.LineBasicMaterial({ color: 0x22D3EE, transparent: true, opacity: 0.12 })));

  // ---------- labels ----------
  function label(text, color, sx) {
    var c = document.createElement('canvas'); c.width = 256; c.height = 64;
    var g = c.getContext('2d');
    g.font = '600 30px Inter, Arial, sans-serif';
    g.textAlign = 'center'; g.textBaseline = 'middle'; g.fillStyle = color;
    g.fillText(text, 128, 34);
    var s = new THREE.Sprite(new THREE.SpriteMaterial({ map: new THREE.CanvasTexture(c), transparent: true, depthWrite: false }));
    s.scale.set(sx, sx / 4, 1);
    return s;
  }
  [0, 0.5, 1].forEach(function (fr) {
    var lb = label(fPrice(minP + fr * (maxP - minP)), '#8B93A7', 3.0);
    lb.position.set(-W / 2 - 1.5, PY0 + fr * (PY1 - PY0), 0);
    root.add(lb);
  });
  [0, Math.floor(N / 2), N - 1].forEach(function (k) {
    var lb = label(rows[k].d, '#8B93A7', 3.4);
    lb.position.set(xI(k), VY0 - 0.5, 1.0);
    root.add(lb);
  });

  // ---------- latest-price marker ----------
  function glowTex() {
    var c = document.createElement('canvas'); c.width = c.height = 64;
    var g = c.getContext('2d'), gr = g.createRadialGradient(32, 32, 0, 32, 32, 32);
    gr.addColorStop(0, 'rgba(255,255,255,1)'); gr.addColorStop(0.4, 'rgba(255,255,255,.5)'); gr.addColorStop(1, 'rgba(255,255,255,0)');
    g.fillStyle = gr; g.fillRect(0, 0, 64, 64);
    return new THREE.CanvasTexture(c);
  }
  var last = closePts[N - 1];
  var marker = new THREE.Sprite(new THREE.SpriteMaterial({ map: glowTex(), color: 0x22D3EE, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending }));
  marker.position.copy(last);
  marker.scale.set(0.6, 0.6, 1);
  root.add(marker);
  var lastLbl = label(fPrice(rows[N - 1].c), '#22D3EE', 3.0);
  lastLbl.position.set(last.x + 0.4, last.y + 0.55, ZW);
  root.add(lastLbl);

  // ---------- hover cursor ----------
  var cursor = new THREE.Mesh(new THREE.BoxGeometry(1, 1, 1), new THREE.MeshBasicMaterial({
    color: 0xffffff, transparent: true, opacity: 0.07, depthWrite: false, blending: THREE.AdditiveBlending
  }));
  cursor.scale.set(cw * 1.8, PY1 - VY0, 1.6);
  cursor.position.y = (PY1 + VY0) / 2;
  cursor.visible = false;
  root.add(cursor);

  // ---------- interaction ----------
  var time = reduce ? 99 : 0, intro = true;
  var drag = false, inside = false, lx = 0, ly = 0, tY = -0.55, tX = 0.22, lastInt = -99;
  var mouse = new THREE.Vector2(), px = 0, py = 0;
  var ray = new THREE.Raycaster();
  root.rotation.set(0.22, reduce ? -0.55 : -1.1, 0);   // starts turned away, swings into place

  canvas.addEventListener('pointerdown', function (e) {
    drag = true; lx = e.clientX; ly = e.clientY; lastInt = time;
    canvas.classList.add('drag');
    try { canvas.setPointerCapture(e.pointerId); } catch (err) {}
  });
  canvas.addEventListener('pointermove', function (e) {
    var b = canvas.getBoundingClientRect();
    px = e.clientX - b.left; py = e.clientY - b.top;
    mouse.x = (px / b.width) * 2 - 1; mouse.y = -(py / b.height) * 2 + 1;
    inside = true;
    if (drag) {
      tY += (e.clientX - lx) * 0.008;
      tX += (e.clientY - ly) * 0.005;
      tX = Math.max(-0.05, Math.min(0.85, tX));
      lx = e.clientX; ly = e.clientY; lastInt = time;
    }
  });
  function endDrag() { drag = false; canvas.classList.remove('drag'); }
  canvas.addEventListener('pointerup', endDrag);
  canvas.addEventListener('pointercancel', endDrag);
  canvas.addEventListener('pointerleave', function () { inside = false; hideTip(); });

  var hoverIdx = -1;
  function hideTip() { hoverIdx = -1; tip.style.opacity = '0'; cursor.visible = false; }
  function showTip(k) {
    var d = rows[k], isUp = d.c >= d.o, chg = (d.c - d.o) / d.o * 100;
    if (k !== hoverIdx) {
      hoverIdx = k;
      tip.innerHTML =
        '<b>' + d.d + '</b><br>O ' + f2(d.o) + ' &nbsp; H ' + f2(d.h) +
        '<br>L ' + f2(d.l) + ' &nbsp; C <span style="color:' + (isUp ? '#10B981' : '#F43F5E') + '">' + f2(d.c) + '</span>' +
        '<br>' + (isUp ? '\u25B2 ' : '\u25BC ') + Math.abs(chg).toFixed(2) + '% \u00B7 Vol ' + fVol(d.v);
      cursor.position.x = xI(k);
      cursor.visible = true;
    }
    var tw = tip.offsetWidth, th = tip.offsetHeight;
    tip.style.left = Math.max(8, Math.min(px + 14, cw0 - tw - 8)) + 'px';
    tip.style.top = Math.max(8, py - th - 10) + 'px';
    tip.style.opacity = '1';
  }

  // ---------- sizing (also handles being shown after being hidden) ----------
  var cw0 = 0, ch0 = 0;
  function fit() {
    var w = wrap.clientWidth, h = wrap.clientHeight;
    if (w < 2 || h < 2) return false;
    if (w !== cw0 || h !== ch0) {
      cw0 = w; ch0 = h;
      renderer.setSize(w, h, false);
      camera.aspect = w / h;
      camera.position.set(0, 1.4, Math.max(15, 21.5 / camera.aspect));
      camera.lookAt(0, 0, 0);
      camera.updateProjectionMatrix();
    }
    return true;
  }

  var onScreen = true;
  if ('IntersectionObserver' in window) {
    new IntersectionObserver(function (en) { onScreen = en[0].isIntersecting; }).observe(wrap);
  }

  // ---------- render loop ----------
  var clock = new THREE.Clock();
  function ease(t) { return 1 - Math.pow(1 - t, 3); }

  function draw() {
    var dt = Math.min(clock.getDelta(), 0.05);
    time += dt;

    if (intro) {
      var done = true;
      for (var k = 0; k < parts.length; k++) {
        var m = parts[k], g = Math.min(1, Math.max(0, (time - m.userData.i * 0.011) / 0.9));
        if (g < 1) done = false;
        m.scale.y = Math.max(m.userData.h * ease(g), 0.0001);
      }
      var fade = Math.min(1, time / 1.4);
      for (var q = 0; q < lineMats.length; q++) lineMats[q].m.opacity = lineMats[q].base * fade;
      if (done && fade >= 1) intro = false;
    }

    var auto = (!reduce && !drag && time - lastInt > 2.5) ? Math.sin(time * 0.35) * 0.22 : 0;
    var s = Math.min(1, dt * 5);
    root.rotation.y += ((tY + auto) - root.rotation.y) * s;
    root.rotation.x += (tX - root.rotation.x) * s;

    if (!reduce) { var pz = 0.6 + 0.16 * Math.sin(time * 3); marker.scale.set(pz, pz, 1); }

    if (inside && !drag) {
      ray.setFromCamera(mouse, camera);
      var hit = ray.intersectObjects(bodies, false);
      if (hit.length) showTip(hit[0].object.userData.i); else hideTip();
    }
    renderer.render(scene, camera);
  }

  function loop() {
    requestAnimationFrame(loop);
    if (document.hidden || !onScreen) return;
    if (!fit()) return;
    draw();
  }
  loop();
})();
</script>
</body></html>"""


def render_chart_3d(ticker: str, height: int = 440) -> None:
    """Render the interactive 3D candlestick explorer for a ticker."""
    rows = _load_history(ticker)
    if not rows:
        _load_history.clear()   # don't keep an empty (failed) result cached
        st.caption("⚠️ 3D view unavailable right now (price history could not be loaded).")
        return
    cur = "₹" if ticker.upper().endswith((".NS", ".BO")) else "$"
    payload = json.dumps(
        {"rows": rows, "ticker": ticker, "cur": cur}, ensure_ascii=False
    ).replace("</", "<\\/")
    html = _TEMPLATE.replace("__PAYLOAD__", payload).replace("__CDN__", THREE_CDN)
    try:
        components.html(html, height=height)
    except AttributeError:
        st.iframe(html, height=height)   # fallback for Streamlit versions without components.html