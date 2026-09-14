/* cosmic-bg.js — shared deep-space backdrop for the ambient oracle scenes.
 *
 * Injects a fixed, full-screen <canvas> BEHIND the page content (z-index:-1,
 * pointer-events:none) and animates a cosmic starfield + nebula matching the
 * R3F "CosmicCanvas" family:
 *   base background  #04030f  (near-black deep purple)
 *   nebula tints     purple #2a1145 / cyan #0e3a52 / magenta #3a1038
 *   star accents     cyan #6ee7ff / purple #c084fc / magenta #f472b6 / white
 *
 * Two parallax star layers (small/dim + a few brighter coloured) with slow
 * twinkle + drift, over a large-scale soft nebula gradient. Pure vanilla JS,
 * DPR-aware, resizes with the window. No external deps. Self-contained.
 */
(function () {
  "use strict";
  if (window.__cosmicBg) return; // guard against double-include
  window.__cosmicBg = true;

  var cv = document.createElement("canvas");
  cv.id = "cosmic-bg";
  cv.style.cssText =
    "position:fixed;inset:0;width:100%;height:100%;" +
    "z-index:-1;pointer-events:none;display:block;background:#04030f";

  function attach() {
    // sit behind everything in <body>
    if (document.body.firstChild) document.body.insertBefore(cv, document.body.firstChild);
    else document.body.appendChild(cv);
  }
  if (document.body) attach();
  else document.addEventListener("DOMContentLoaded", attach);

  var x = cv.getContext("2d");
  var W = 0, H = 0, DPR = 1;

  // ---- nebula clouds: soft radial glows that drift very slowly ----
  var NEBULA = [
    { tint: "42,17,69",   ox: 0.22, oy: 0.30, rad: 0.62, amp: 0.34, sp: 0.013, ph: 0.0 }, // purple #2a1145
    { tint: "14,58,82",   ox: 0.78, oy: 0.68, rad: 0.58, amp: 0.30, sp: 0.011, ph: 2.1 }, // cyan   #0e3a52
    { tint: "58,16,56",   ox: 0.58, oy: 0.18, rad: 0.50, amp: 0.24, sp: 0.017, ph: 4.0 }, // magenta#3a1038
    { tint: "42,17,69",   ox: 0.40, oy: 0.82, rad: 0.55, amp: 0.22, sp: 0.009, ph: 5.3 }
  ];

  // ---- star layers ----
  var STAR_COLORS = ["255,255,255", "110,231,255", "192,132,252", "244,114,182"]; // white, cyan, purple, magenta
  var farStars = [];   // many, small, dim, slow
  var nearStars = [];  // fewer, larger, brighter coloured, faster drift

  function rand(a, b) { return a + Math.random() * (b - a); }

  function seedStars() {
    farStars = [];
    nearStars = [];
    var area = (W * H) / (1280 * 720); // density relative to a reference viewport
    var nFar = Math.round(170 * Math.max(0.5, Math.min(2.2, area)));
    var nNear = Math.round(50 * Math.max(0.5, Math.min(2.2, area)));
    for (var i = 0; i < nFar; i++) {
      farStars.push({
        x: Math.random(), y: Math.random(),
        r: rand(0.4, 1.1),
        base: rand(0.18, 0.55),
        tw: rand(0.6, 1.8),     // twinkle speed
        ph: rand(0, Math.PI * 2),
        col: "255,255,255"
      });
    }
    for (var j = 0; j < nNear; j++) {
      nearStars.push({
        x: Math.random(), y: Math.random(),
        r: rand(0.9, 2.2),
        base: rand(0.4, 0.85),
        tw: rand(0.8, 2.4),
        ph: rand(0, Math.PI * 2),
        col: STAR_COLORS[(Math.random() * STAR_COLORS.length) | 0]
      });
    }
  }

  function resize() {
    DPR = Math.min(2, window.devicePixelRatio || 1);
    W = window.innerWidth;
    H = window.innerHeight;
    cv.width = Math.max(1, Math.round(W * DPR));
    cv.height = Math.max(1, Math.round(H * DPR));
    cv.style.width = W + "px";
    cv.style.height = H + "px";
    x.setTransform(DPR, 0, 0, DPR, 0, 0);
    seedStars();
  }
  window.addEventListener("resize", resize);
  resize();

  function drawNebula(t) {
    // base fill
    x.globalCompositeOperation = "source-over";
    x.fillStyle = "#04030f";
    x.fillRect(0, 0, W, H);

    // soft drifting radial glows (additive so they layer like gas)
    x.globalCompositeOperation = "lighter";
    var diag = Math.hypot(W, H);
    for (var i = 0; i < NEBULA.length; i++) {
      var n = NEBULA[i];
      var cx = (n.ox + Math.sin(t * n.sp + n.ph) * 0.04) * W;
      var cy = (n.oy + Math.cos(t * n.sp * 0.8 + n.ph) * 0.04) * H;
      var r = n.rad * diag;
      var a = n.amp * (0.78 + 0.22 * Math.sin(t * n.sp * 1.7 + n.ph));
      var g = x.createRadialGradient(cx, cy, 0, cx, cy, r);
      g.addColorStop(0, "rgba(" + n.tint + "," + a.toFixed(3) + ")");
      g.addColorStop(0.55, "rgba(" + n.tint + "," + (a * 0.35).toFixed(3) + ")");
      g.addColorStop(1, "rgba(" + n.tint + ",0)");
      x.fillStyle = g;
      x.fillRect(0, 0, W, H);
    }
    x.globalCompositeOperation = "source-over";
  }

  function drawStars(t) {
    x.globalCompositeOperation = "lighter";
    var driftFar = (t * 0.0015) % 1;   // very slow horizontal drift, wraps
    var driftNear = (t * 0.0040) % 1;
    var k, s, px, py, a;
    for (k = 0; k < farStars.length; k++) {
      s = farStars[k];
      px = ((s.x + driftFar) % 1) * W;
      py = s.y * H;
      a = s.base * (0.55 + 0.45 * Math.sin(t * s.tw + s.ph));
      if (a <= 0.01) continue;
      x.fillStyle = "rgba(" + s.col + "," + a.toFixed(3) + ")";
      x.beginPath();
      x.arc(px, py, s.r, 0, 6.2832);
      x.fill();
    }
    for (k = 0; k < nearStars.length; k++) {
      s = nearStars[k];
      px = ((s.x + driftNear) % 1) * W;
      py = s.y * H;
      a = s.base * (0.5 + 0.5 * Math.sin(t * s.tw + s.ph));
      if (a <= 0.01) continue;
      x.shadowBlur = 6 * a;
      x.shadowColor = "rgba(" + s.col + ",1)";
      x.fillStyle = "rgba(" + s.col + "," + a.toFixed(3) + ")";
      x.beginPath();
      x.arc(px, py, s.r, 0, 6.2832);
      x.fill();
    }
    x.shadowBlur = 0;
    x.globalCompositeOperation = "source-over";
  }

  function frame(now) {
    var t = now * 0.001;
    drawNebula(t);
    drawStars(t);
    requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);
})();
