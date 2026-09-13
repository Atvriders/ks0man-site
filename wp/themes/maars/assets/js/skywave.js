/*!
 * MAARS / KS0MAN -- skywave.js
 * ---------------------------------------------------------------------------
 * A raw WebGL2 teaching visualisation of HF skywave propagation from
 * Manhattan, Kansas (the home of the Manhattan Area Amateur Radio Society).
 *
 * No three.js. No libraries. No CDN. No imports. No network access of any
 * kind. One self-contained IIFE that exposes:
 *
 *     window.MAARSSkywave.mount(canvasEl, opts) -> { destroy() }
 *
 * WHAT IS COMPUTED AND WHAT IS DRAWN
 * ----------------------------------
 * Ground distances, take-off angles and the skip distance are COMPUTED from
 * the secant law with virtual reflection heights (see solveRay / scanBand).
 * They are not hand-tuned curves. What is *illustrative* rather than
 * predictive is the choice of critical frequencies (a smooth day/night model,
 * not an ionosonde), the D-layer absorption constant, and the cosmetic bend
 * applied to rays that penetrate every layer and escape to space.
 *
 * Altitudes are drawn exaggerated (default x6) because the whole ionosphere
 * is 5% of the Earth's radius; the on-screen HUD says so.
 *
 * This is a teaching aid. It is NOT a propagation prediction.
 * ---------------------------------------------------------------------------
 */
(function (global) {
  'use strict';

  if (!global || typeof global.document === 'undefined') { return; }

  var VERSION = '1.0.0';
  var DEG = Math.PI / 180;
  var RAD = 180 / Math.PI;

  /* Mean Earth radius, km. */
  var R_KM = 6371.0;

  /* The club's home town. A city centroid -- not anybody's address. */
  var SITE = { lat: 39.1836, lon: -96.5717 };

  /* Vertical exaggeration. The whole ionosphere is under 5% of the Earth's
   * radius, so some exaggeration is needed -- but the view is zoomed into a
   * few thousand km of ground, so x3 is enough to separate D/E/F1/F2 while
   * keeping hop geometry close to the shape the physics actually gives.
   * The HUD states the factor. */
  var DEFAULT_EXAG = 3.0;

  /* ---------------------------------------------------------------------
   * Band data. These are the club's REAL operating frequencies and they are
   * the actual teaching content of this visualisation.
   * ------------------------------------------------------------------- */
  var BANDS = [
    {
      key: '80', id: '80m', name: '80 M', mhz: 3.920,
      net: 'KANSAS SIDEBAND NET',
      spoken: '80 metres, 3.920 megahertz, the Kansas Sideband Net'
    },
    {
      key: '40', id: '40m', name: '40 M', mhz: 7.260,
      net: 'KANSAS WEATHER NET',
      spoken: '40 metres, 7.260 megahertz, the Kansas Weather Net'
    },
    {
      key: '20', id: '20m', name: '20 M', mhz: 14.290,
      net: 'DAYTIME DX',
      spoken: '20 metres, 14.290 megahertz, daytime D X'
    },
    {
      key: '2', id: '2m', name: '2 M', mhz: 147.255,
      net: 'KS\u00d8MAN REPEATER',
      spoken: '2 metres, 147.255 megahertz, the KS0MAN repeater',
      /* 147.255 MHz out / 147.855 in / +600 kHz / 88.5 Hz CTCSS. The machine
       * moved off the KSDB-FM tower to a Riley County site in Nov 2023 and
       * the S-COM 7330 controller was voted out in Jan 2024. All UNVERIFIED,
       * which is why the HUD says so and why the horizon figure is labelled
       * illustrative. */
      vhf: true,
      antennaM: 90
    }
  ];

  /* ---------------------------------------------------------------------
   * Palette -- measured from the club's own 1997 stylesheet.
   * navy #00008C (15.23:1 on white) - magenta #990066 (8.25:1) -
   * lavender #DBDBFB - ink #14142B - alarm #A5171B, plus the dark-mode
   * variants navy #9FA0F2 / magenta #F09FD0 / ground #0C0C18 / paper #14142A.
   * ------------------------------------------------------------------- */
  var C = {
    navy:      [0.000, 0.000, 0.549],
    navyLight: [0.624, 0.627, 0.949],
    magenta:   [0.600, 0.000, 0.400],
    magentaLt: [0.941, 0.624, 0.816],
    lavender:  [0.859, 0.859, 0.984],
    ink:       [0.078, 0.078, 0.169],
    ground:    [0.047, 0.047, 0.094],
    paper:     [0.078, 0.078, 0.165],
    alarm:     [0.647, 0.090, 0.106]
  };
  var CSS = {
    lavender: '#DBDBFB',
    magentaLt: '#F09FD0',
    navyLight: '#9FA0F2',
    paperDim: 'rgba(219,219,251,0.62)',
    alarm: '#F2A0A2',
    panel: 'rgba(12,12,24,0.72)',
    panelEdge: 'rgba(159,160,242,0.30)'
  };

  /* =====================================================================
   * 1. Small maths helpers (no library, so these are hand rolled).
   * =================================================================== */

  function clamp(v, a, b) { return v < a ? a : (v > b ? b : v); }
  function smoothstep(e0, e1, x) {
    var t = clamp((x - e0) / (e1 - e0), 0, 1);
    return t * t * (3 - 2 * t);
  }
  function vsub(a, b) { return [a[0] - b[0], a[1] - b[1], a[2] - b[2]]; }
  function vdot(a, b) { return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]; }
  function vcross(a, b) {
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
  }
  function vlen(a) { return Math.sqrt(vdot(a, a)); }
  function vnorm(a) {
    var l = vlen(a) || 1;
    return [a[0] / l, a[1] / l, a[2] / l];
  }
  function vscale(a, s) { return [a[0] * s, a[1] * s, a[2] * s]; }

  function mat4Identity() {
    return new Float32Array([1,0,0,0, 0,1,0,0, 0,0,1,0, 0,0,0,1]);
  }

  function mat4Perspective(out, fovy, aspect, near, far) {
    var f = 1 / Math.tan(fovy / 2), nf = 1 / (near - far);
    out[0] = f / aspect; out[1] = 0; out[2] = 0; out[3] = 0;
    out[4] = 0; out[5] = f; out[6] = 0; out[7] = 0;
    out[8] = 0; out[9] = 0; out[10] = (far + near) * nf; out[11] = -1;
    out[12] = 0; out[13] = 0; out[14] = 2 * far * near * nf; out[15] = 0;
    return out;
  }

  function mat4LookAt(out, eye, center, up) {
    var z = vnorm(vsub(eye, center));
    var x = vcross(up, z);
    var xl = vlen(x);
    if (xl < 1e-6) { x = vcross([0, 0, 1], z); xl = vlen(x) || 1; }
    x = vscale(x, 1 / xl);
    var y = vcross(z, x);
    out[0] = x[0]; out[1] = y[0]; out[2] = z[0]; out[3] = 0;
    out[4] = x[1]; out[5] = y[1]; out[6] = z[1]; out[7] = 0;
    out[8] = x[2]; out[9] = y[2]; out[10] = z[2]; out[11] = 0;
    out[12] = -vdot(x, eye); out[13] = -vdot(y, eye); out[14] = -vdot(z, eye); out[15] = 1;
    return out;
  }

  function mat4Mul(out, a, b) {
    for (var c = 0; c < 4; c++) {
      var b0 = b[c * 4], b1 = b[c * 4 + 1], b2 = b[c * 4 + 2], b3 = b[c * 4 + 3];
      out[c * 4]     = a[0] * b0 + a[4] * b1 + a[8]  * b2 + a[12] * b3;
      out[c * 4 + 1] = a[1] * b0 + a[5] * b1 + a[9]  * b2 + a[13] * b3;
      out[c * 4 + 2] = a[2] * b0 + a[6] * b1 + a[10] * b2 + a[14] * b3;
      out[c * 4 + 3] = a[3] * b0 + a[7] * b1 + a[11] * b2 + a[15] * b3;
    }
    return out;
  }

  /* =====================================================================
   * 2. Geographic frame.
   *
   * Geographic (ECEF-ish) frame: +Y = north pole, +X = (0 lat, 0 lon),
   * +Z = (0 lat, 90E).  Scene frame: Manhattan is at +Y so the interesting
   * geometry sits on top of the globe.  Scene basis rows are
   * [east, up, north] which is right handed (east x up = north).
   * =================================================================== */

  function geoVec(latDeg, lonDeg) {
    var la = latDeg * DEG, lo = lonDeg * DEG, cl = Math.cos(la);
    return [cl * Math.cos(lo), Math.sin(la), cl * Math.sin(lo)];
  }

  function sceneBasis(latDeg, lonDeg) {
    var la = latDeg * DEG, lo = lonDeg * DEG;
    var up = geoVec(latDeg, lonDeg);
    var east = [-Math.sin(lo), 0, Math.cos(lo)];
    var north = [-Math.sin(la) * Math.cos(lo), Math.cos(la), -Math.sin(la) * Math.sin(lo)];
    return { up: up, east: east, north: north };
  }

  /* mat3 (column-major for GL) that maps a scene-frame vector into the
   * geographic frame: geo = east*x + up*y + north*z. */
  function geoFromSceneMat3(basis) {
    var b = basis;
    return new Float32Array([
      b.east[0], b.east[1], b.east[2],
      b.up[0],   b.up[1],   b.up[2],
      b.north[0],b.north[1],b.north[2]
    ]);
  }

  /* =====================================================================
   * 3. Where is the Sun? (low-precision solar position, no network)
   * Standard almanac approximation, good to a fraction of a degree, which
   * is far better than this visualisation needs for a terminator tint.
   * =================================================================== */

  function subsolarPoint(date) {
    var jd = date.getTime() / 86400000 + 2440587.5;
    var d = jd - 2451545.0;
    var g = (357.529 + 0.98560028 * d) * DEG;
    var q = (280.459 + 0.98564736 * d) * DEG;
    var L = q + (1.915 * Math.sin(g) + 0.020 * Math.sin(2 * g)) * DEG;
    var e = (23.439 - 0.00000036 * d) * DEG;
    var dec = Math.asin(Math.sin(e) * Math.sin(L));
    var ra = Math.atan2(Math.cos(e) * Math.sin(L), Math.cos(L));
    var gmst = (18.697374558 + 24.06570982441908 * d) % 24;
    if (gmst < 0) { gmst += 24; }
    var lon = ra * RAD - gmst * 15;
    lon = ((lon + 180) % 360 + 360) % 360 - 180;
    return { lat: dec * RAD, lon: lon };
  }

  /* =====================================================================
   * 4. The ionosphere, and the physics that is actually computed.
   * =================================================================== */

  /* Virtual reflection heights, km. Textbook daytime values. */
  var LAYER_H = { D: 75, E: 110, F1: 200, F2: 300 };

  /**
   * Critical frequencies as a smooth function of how sunlit the site is.
   * ILLUSTRATIVE: a mid-latitude, mid-solar-cycle sketch, not an ionosonde.
   * The D layer never reflects at HF -- it only absorbs -- so its fo is 0.
   */
  function ionosphere(day) {
    var d = clamp(day, 0, 1);
    return [
      { id: 'D',  h: LAYER_H.D,  fo: 0,                                  absorbs: true },
      { id: 'E',  h: LAYER_H.E,  fo: 0.4 + 3.1 * Math.pow(d, 0.25),      absorbs: false },
      { id: 'F1', h: LAYER_H.F1, fo: d > 0.18 ? 4.6 * Math.pow(d, 0.20) : 0, absorbs: false },
      { id: 'F2', h: LAYER_H.F2, fo: 4.0 + 5.0 * d,                      absorbs: false }
    ];
  }

  /**
   * Spherical-earth hop geometry for one take-off angle and one virtual
   * reflection height.
   *
   *   sin(phi) = R cos(elev) / (R + h)        (sine rule in the triangle
   *                                            earth-centre / TX / apex)
   *   theta    = 90deg - elev - phi           (central angle, half hop)
   *   hop      = 2 R theta
   *
   * phi is the angle of incidence at the layer, which is what the secant
   * law needs.
   */
  function hopGeometry(elevDeg, hKm) {
    var e = elevDeg * DEG;
    var sinPhi = (R_KM * Math.cos(e)) / (R_KM + hKm);
    if (sinPhi > 1) { return null; }
    var phi = Math.asin(sinPhi);
    var theta = Math.PI / 2 - e - phi;
    if (theta < 0) { theta = 0; }
    return { phi: phi, theta: theta, hopKm: 2 * R_KM * theta, secPhi: 1 / Math.cos(phi) };
  }

  /**
   * Secant law. A ray reflects from a layer when
   *     f * cos(phi) <= foLayer          (equivalently f <= foLayer * sec phi)
   * Layers are tried bottom up, because the ray meets them in that order.
   * If no layer turns it, the ray escapes to space.
   */
  function solveRay(freqMhz, elevDeg, iono) {
    var bestRatio = 0, i, L, g, ratio;
    for (i = 0; i < iono.length; i++) {
      L = iono[i];
      if (L.fo <= 0) { continue; }
      g = hopGeometry(elevDeg, L.h);
      if (!g) { continue; }
      ratio = L.fo / (freqMhz * Math.cos(g.phi));
      if (ratio > bestRatio) { bestRatio = ratio; }
      if (freqMhz * Math.cos(g.phi) <= L.fo) {
        return {
          mode: 'reflect', layer: L.id, h: L.h, hopKm: g.hopKm,
          theta: g.theta, phi: g.phi, muf: L.fo * g.secPhi
        };
      }
    }
    return { mode: 'escape', closeness: clamp(bestRatio, 0, 1) };
  }

  /**
   * D-layer absorption, one traversal, in dB.
   *     L ~ K * sec(phi_D) * dayFactor / (f + fH)^1.8
   * with fH ~ 1.2 MHz for the electron gyrofrequency. ILLUSTRATIVE constant,
   * chosen so 80 m at noon lands in the 25-35 dB per traversal region that
   * makes the band unusable for DX by day -- which is the point being taught.
   */
  function absorptionDb(freqMhz, elevDeg, day) {
    if (day <= 0.001) { return 0; }
    var g = hopGeometry(elevDeg, LAYER_H.D);
    var sec = g ? Math.min(g.secPhi, 4.5) : 1;
    return 320 * day * sec / Math.pow(freqMhz + 1.2, 1.8);
  }

  /**
   * Sweep take-off angle to find the skip distance: the shortest ground
   * distance any ray can reach. Inside that radius nothing lands, which is
   * the dead ring the visualisation draws.
   */
  function scanBand(freqMhz, iono) {
    var anyReflect = false, minHop = Infinity, minElev = 0, minLayer = '', maxRefl = -1;
    var lowest = -1, e, s;
    for (e = 89; e >= 1.0; e -= 0.25) {
      s = solveRay(freqMhz, e, iono);
      if (s.mode !== 'reflect') { continue; }
      anyReflect = true;
      if (e > maxRefl) { maxRefl = e; }
      lowest = e;
      if (s.hopKm < minHop) { minHop = s.hopKm; minElev = e; minLayer = s.layer; }
    }
    return {
      anyReflect: anyReflect,
      skipKm: anyReflect ? minHop : null,
      skipElev: minElev,
      skipLayer: minLayer,
      maxReflectElev: maxRefl,
      lowestReflectElev: lowest
    };
  }

  /** Take-off angle whose hop lands nearest a wanted ground distance. */
  function elevForHop(freqMhz, iono, targetKm) {
    var best = null, bestErr = Infinity, e, s, err;
    for (e = 88; e >= 1.5; e -= 0.25) {
      s = solveRay(freqMhz, e, iono);
      if (s.mode !== 'reflect' || s.hopKm < 20) { continue; }
      err = Math.abs(s.hopKm - targetKm);
      if (err < bestErr) { bestErr = err; best = e; }
    }
    return best;
  }

  /** Radio horizon, km, for a 4/3-earth: 4.12 * (sqrt(h1) + sqrt(h2)) metres. */
  function radioHorizonKm(txM, rxM) {
    return 4.12 * (Math.sqrt(txM) + Math.sqrt(rxM));
  }

  /* =====================================================================
   * 5. Turning physics into geometry.
   *
   * Scene units: the Earth's radius is 1.0. Altitude is exaggerated so the
   * ionosphere is legible; above the top of the ionosphere the exaggeration
   * is dropped so escaping rays do not shoot off to absurd distances.
   * =================================================================== */

  function makeAltScale(exag) {
    var LIN = 400; /* km: exaggerate fully up to here */
    return function (altKm) {
      var a = altKm <= LIN ? altKm * exag : LIN * exag + (altKm - LIN) * 0.9;
      return 1 + a / R_KM;
    };
  }

  /* Point at central angle a (rad) from the site, along azimuth az, at
   * altitude alt (km). The site is +Y; azimuth 0 is north (+Z). */
  function scenePoint(a, altKm, az, rOf) {
    var sa = Math.sin(a), r = rOf(altKm);
    return [Math.sin(az) * sa * r, Math.cos(a) * r, Math.cos(az) * sa * r];
  }

  /**
   * Altitude profile of one hop, as a cubic Hermite in (central angle,
   * altitude) whose start slope is the real take-off angle and whose apex
   * slope is zero. The tangent is clamped the Fritsch-Carlson way so the
   * curve can never overshoot the virtual height.
   */
  function hopProfile(theta, h, elevDeg, samplesPerLeg) {
    var pts = [], i, s, s2, s3, m0, alt;
    if (theta < 1e-5) {
      /* Straight up and straight back down (near-vertical incidence). */
      for (i = 0; i <= samplesPerLeg; i++) { pts.push([0, h * (i / samplesPerLeg)]); }
      for (i = 1; i <= samplesPerLeg; i++) { pts.push([0, h * (1 - i / samplesPerLeg)]); }
      return pts;
    }
    m0 = R_KM * Math.tan(elevDeg * DEG) * theta;
    m0 = clamp(m0, 0, 3 * h);
    for (i = 0; i <= samplesPerLeg; i++) {
      s = i / samplesPerLeg; s2 = s * s; s3 = s2 * s;
      alt = (s3 - 2 * s2 + s) * m0 + (-2 * s3 + 3 * s2) * h;
      pts.push([theta * s, alt]);
    }
    for (i = samplesPerLeg - 1; i >= 0; i--) {
      pts.push([2 * theta - pts[i][0], pts[i][1]]);
    }
    return pts;
  }

  /** Ray that penetrates every layer. Straight up to the top of the
   *  ionosphere, then a single illustrative bend proportional to how close
   *  it came to reflecting, then straight out. Above 30 MHz the bend is
   *  exactly zero: at VHF the ionosphere simply is not there. */
  function escapeProfile(elevDeg, closeness, freqMhz) {
    var hTop = 350, hOut = 2600;
    var e = elevDeg * DEG;
    var px = 0, py = R_KM, dx = Math.cos(e), dy = Math.sin(e);
    var b = R_KM * Math.sin(e);
    var t1 = -b + Math.sqrt(b * b + (R_KM + hTop) * (R_KM + hTop) - R_KM * R_KM);
    var p1x = px + dx * t1, p1y = py + dy * t1;
    var r1 = Math.sqrt(p1x * p1x + p1y * p1y);
    var elev1 = Math.asin(clamp((dx * p1x + dy * p1y) / r1, -1, 1)) * RAD;
    var bend = freqMhz >= 30 ? 0 : Math.min(45 * closeness, Math.max(0, elev1 - 3));
    var cb = Math.cos(bend * DEG), sb = Math.sin(bend * DEG);
    var d2x = dx * cb + dy * sb, d2y = -dx * sb + dy * cb;
    var b2 = p1x * d2x + p1y * d2y;
    var t2 = -b2 + Math.sqrt(Math.max(0, b2 * b2 + (R_KM + hOut) * (R_KM + hOut) - r1 * r1));
    var out = [], i, f, x, y;
    for (i = 0; i <= 8; i++) {
      f = t1 * (i / 8); x = px + dx * f; y = py + dy * f;
      out.push([Math.atan2(x, y), Math.sqrt(x * x + y * y) - R_KM, 0.55]);
    }
    for (i = 1; i <= 18; i++) {
      f = t2 * (i / 18); x = p1x + d2x * f; y = p1y + d2y * f;
      out.push([Math.atan2(x, y), Math.sqrt(x * x + y * y) - R_KM,
        0.55 * Math.pow(1 - i / 18, 1.6) + 0.02]);
    }
    return out;
  }

  /**
   * Build one complete ray (all hops) as a list of {a, alt, intensity}.
   * Returns { pts, landings, escaped }.
   */
  function buildRay(freqMhz, elevDeg, iono, day, maxHops) {
    var s = solveRay(freqMhz, elevDeg, iono);
    if (s.mode === 'escape') {
      return { pts: escapeProfile(elevDeg, s.closeness, freqMhz), landings: [], escaped: true, sol: s };
    }
    var pts = [], landings = [], A = 0, inten = 1, hop = 0, i, prof;
    var perHopDb = 2 * absorptionDb(freqMhz, elevDeg, day);
    /* Display compression: the HUD prints the honest dB figure, the drawing
     * uses a gentler curve so a 60 dB path is faint rather than invisible. */
    var perHopVis = Math.pow(10, -perHopDb / 45);
    for (hop = 0; hop < maxHops; hop++) {
      if (s.hopKm < 1 && hop > 0) { break; }
      prof = hopProfile(s.theta, s.h, elevDeg, 13);
      var mid = (prof.length - 1) / 2;
      for (i = (hop === 0 ? 0 : 1); i < prof.length; i++) {
        /* The D layer is crossed twice per hop -- once climbing, once coming
         * back down -- so the ray has to visibly lose its strength as it
         * passes 75 km, not in one lump at the far end. */
        var cross = i <= mid
          ? smoothstep(35, 115, prof[i][1])
          : 2 - smoothstep(35, 115, prof[i][1]);
        pts.push([A + prof[i][0], prof[i][1],
          inten * Math.pow(perHopVis, cross / 2) * (1 - 0.14 * (i / prof.length))]);
      }
      A += 2 * s.theta;
      landings.push(A * R_KM);
      inten *= perHopVis * 0.55; /* 0.55 = ground reflection loss */
      if (inten < 0.02) { break; }
      if (inten < 0.035 || A * R_KM > 9000) { break; }
    }
    return { pts: pts, landings: landings, escaped: false, sol: s, absDb: perHopDb };
  }

  /* ---------------------------------------------------------------------
   * Ribbon lines. WebGL line width is unreliable above 1px, so every line
   * is expanded into a screen-space quad in the vertex shader.
   * Vertex layout (12 floats): pos.xyz | other.xyz | side | s | phase |
   *                            style | intensity | widthMul
   * ------------------------------------------------------------------- */

  function ribbonInit() { return { v: [], idx: [], n: 0 }; }

  function ribbonPush(dst, pts, style, phase, widthMul) {
    var n = pts.length, i, j, tot = 0, acc = [0], d, a, b, base;
    if (n < 2) { return; }
    for (i = 1; i < n; i++) {
      d = Math.sqrt(
        (pts[i][0] - pts[i - 1][0]) * (pts[i][0] - pts[i - 1][0]) +
        (pts[i][1] - pts[i - 1][1]) * (pts[i][1] - pts[i - 1][1]) +
        (pts[i][2] - pts[i - 1][2]) * (pts[i][2] - pts[i - 1][2]));
      tot += d; acc.push(tot);
    }
    if (tot < 1e-9) { return; }
    for (i = 0; i < n - 1; i++) {
      a = pts[i]; b = pts[i + 1];
      base = dst.n;
      for (j = 0; j < 4; j++) {
        var atA = (j < 2);
        var p = atA ? a : b, q = atA ? b : a;
        var side = (j === 0 || j === 3) ? 1 : -1;
        var sv = (atA ? acc[i] : acc[i + 1]) / tot;
        var iv = atA ? a[3] : b[3];
        dst.v.push(p[0], p[1], p[2], q[0], q[1], q[2], side, sv, phase, style, iv, widthMul);
      }
      dst.idx.push(base, base + 1, base + 2, base + 1, base + 3, base + 2);
      dst.n += 4;
    }
  }

  /** Circle of constant ground distance around the site. */
  function ringPoints(groundKm, altKm, rOf, inten, segments) {
    var a = groundKm / R_KM, out = [], i, az;
    for (i = 0; i <= segments; i++) {
      az = (i / segments) * Math.PI * 2;
      var p = scenePoint(a, altKm, az, rOf);
      out.push([p[0], p[1], p[2], inten]);
    }
    return out;
  }

  /* =====================================================================
   * 6. Shaders (GLSL ES 3.00). #version must be the very first characters.
   * =================================================================== */

  var VS_CAP = [
    '#version 300 es',
    'layout(location = 0) in vec3 aUnit;',
    'uniform mat4 uViewProj;',
    'uniform float uRadius;',
    'out vec3 vUnit;',
    'out vec3 vWorld;',
    'void main(){',
    '  vUnit = aUnit;',
    '  vWorld = aUnit * uRadius;',
    '  gl_Position = uViewProj * vec4(vWorld, 1.0);',
    '}'
  ].join('\n');

  var FS_EARTH = [
    '#version 300 es',
    'precision highp float;',
    'in vec3 vUnit;',
    'in vec3 vWorld;',
    'uniform mat3 uGeoFromScene;',
    'uniform vec3 uSunGeo;',
    'uniform float uCapCos;',
    'uniform vec3 uDay;',
    'uniform vec3 uNight;',
    'uniform vec3 uGrid;',
    'uniform vec3 uRing;',
    'uniform vec3 uEye;',
    'uniform float uEarthR;',
    'out vec4 frag;',
    'float lineMask(float v, float period, float w){',
    '  float d = abs(fract(v / period + 0.5) - 0.5) * period;',
    '  float aa = fwidth(v) * w + 1e-6;',
    '  return 1.0 - smoothstep(aa * 0.45, aa * 1.35, d);',
    '}',
    'void main(){',
    '  vec3 u = normalize(vUnit);',
    '  vec3 g = uGeoFromScene * u;',
    '  float lat = asin(clamp(g.y, -1.0, 1.0)) * 57.2957795;',
    '  float lon = atan(g.z, g.x) * 57.2957795;',
    '  float cz = dot(g, uSunGeo);',
    '  float day = smoothstep(-0.13, 0.15, cz);',
    '  vec3 col = mix(uNight, uDay, day);',
    '  col *= mix(0.48, 0.66, clamp(cz, 0.0, 1.0));',
    /* twilight band: the terminator itself, warm magenta */
    '  float tw = exp(-(cz * cz) / (2.0 * 0.055 * 0.055));',
    '  col += vec3(0.42, 0.05, 0.30) * tw * 0.55;',
    /* lat/long graticule every 10 degrees */
    '  float grid = max(lineMask(lat, 10.0, 1.1), lineMask(lon, 10.0, 1.1));',
    '  col = mix(col, uGrid, grid * (0.10 + 0.09 * day));',
    /* range rings from the site every 1000 km -- how you read skip distance */
    '  float dkm = acos(clamp(u.y, -1.0, 1.0)) * uEarthR;',
    '  float rings = lineMask(dkm, 1000.0, 1.25);',
    '  col = mix(col, uRing, rings * 0.19);',
    '  vec3 vdir = normalize(uEye - vWorld);',
    '  float limb = pow(1.0 - clamp(dot(u, vdir), 0.0, 1.0), 3.5);',
    '  col += uRing * limb * 0.18;',
    '  float edge = smoothstep(uCapCos, uCapCos + 0.075, u.y);',
    '  frag = vec4(col, edge);',
    '}'
  ].join('\n');

  var FS_SHELL = [
    '#version 300 es',
    'precision highp float;',
    'in vec3 vUnit;',
    'in vec3 vWorld;',
    'uniform mat3 uGeoFromScene;',
    'uniform vec3 uSunGeo;',
    'uniform vec3 uEye;',
    'uniform vec3 uColor;',
    'uniform float uCapCos;',
    'uniform float uIntensity;',
    'uniform float uNightMul;',
    'uniform vec2 uFade;',
    'out vec4 frag;',
    'void main(){',
    '  vec3 n = normalize(vUnit);',
    '  vec3 g = uGeoFromScene * n;',
    '  vec3 vdir = normalize(uEye - vWorld);',
    '  float rim = pow(1.0 - abs(dot(n, vdir)), 2.4);',
    '  float day = smoothstep(-0.13, 0.15, dot(g, uSunGeo));',
    '  float ion = mix(uNightMul, 1.0, day);',
    '  float colat = acos(clamp(n.y, -1.0, 1.0));',
    '  float edge = 1.0 - smoothstep(uFade.x, uFade.y, colat);',
    '  edge *= edge;',
    '  float a = (0.016 + 0.30 * rim) * uIntensity * ion * edge;',
    '  frag = vec4(uColor, a);',
    '}'
  ].join('\n');

  var FS_ZONE = [
    '#version 300 es',
    'precision highp float;',
    'in vec3 vUnit;',
    'in vec3 vWorld;',
    'uniform float uOuterKm;',
    'uniform float uEarthR;',
    'uniform vec3 uTint;',
    'uniform vec3 uEdge;',
    'uniform float uStyle;',
    'uniform float uAlpha;',
    'out vec4 frag;',
    'void main(){',
    '  vec3 u = normalize(vUnit);',
    '  float dkm = acos(clamp(u.y, -1.0, 1.0)) * uEarthR;',
    '  if (dkm > uOuterKm) { discard; }',
    '  float az = atan(u.z, u.x);',
    '  float body = uAlpha;',
    '  if (uStyle < 0.5) {',
    '    float h = abs(fract(dkm / (uOuterKm * 0.16 + 55.0) + az * 2.2) - 0.5);',
    '    float hatch = 1.0 - smoothstep(0.10, 0.20, h);',
    '    body = uAlpha * (0.30 + 0.85 * hatch);',
    '  }',
    '  body *= smoothstep(0.0, uOuterKm * 0.10 + 8.0, dkm);',
    '  vec3 col = uTint;',
    '  float ring = 1.0 - smoothstep(0.0, max(28.0, uOuterKm * 0.018), abs(dkm - uOuterKm));',
    '  col = mix(col, uEdge, ring);',
    '  float a = clamp(body + ring * 0.85, 0.0, 1.0);',
    '  frag = vec4(col, a);',
    '}'
  ].join('\n');

  var VS_LINE = [
    '#version 300 es',
    'layout(location = 0) in vec3 aPos;',
    'layout(location = 1) in vec3 aOther;',
    'layout(location = 2) in float aSide;',
    'layout(location = 3) in float aS;',
    'layout(location = 4) in vec3 aMeta;',   /* phase, style, intensity */
    'layout(location = 5) in float aWidth;',
    'uniform mat4 uViewProj;',
    'uniform vec2 uViewport;',
    'uniform float uWidth;',
    'out float vS;',
    'out vec3 vMeta;',
    'void main(){',
    '  vec4 cp = uViewProj * vec4(aPos, 1.0);',
    '  vec4 cq = uViewProj * vec4(aOther, 1.0);',
    '  if (cp.w <= 0.0) { gl_Position = vec4(2.0, 2.0, 2.0, 1.0); vS = aS; vMeta = aMeta; return; }',
    '  vec2 hv = uViewport * 0.5;',
    '  vec2 sp = (cp.xy / cp.w) * hv;',
    '  vec2 sq = (cq.xy / max(cq.w, 1e-4)) * hv;',
    '  vec2 d = sq - sp;',
    '  float L = length(d);',
    '  vec2 dir = L > 1e-5 ? d / L : vec2(1.0, 0.0);',
    '  vec2 nrm = vec2(-dir.y, dir.x);',
    '  vec2 off = nrm * aSide * (uWidth * aWidth) * 0.5;',
    '  cp.xy += (off / hv) * cp.w;',
    '  gl_Position = cp;',
    '  vS = aS;',
    '  vMeta = aMeta;',
    '}'
  ].join('\n');

  var FS_LINE = [
    '#version 300 es',
    'precision highp float;',
    'in float vS;',
    'in vec3 vMeta;',
    'uniform float uTime;',
    'uniform float uMotion;',
    'uniform float uGain;',
    'uniform vec3 uRay;',
    'uniform vec3 uDeco;',
    'uniform vec3 uEscape;',
    'uniform vec3 uMark;',
    'uniform vec3 uHot;',
    'out vec4 frag;',
    'void main(){',
    '  int style = int(vMeta.y + 0.5);',
    '  vec3 col = uRay;',
    '  if (style == 1) { col = uDeco; }',
    '  else if (style == 2) { col = uEscape; }',
    '  else if (style == 3) { col = uMark; }',
    '  float base = mix(0.62, 0.30, uMotion);',
    '  float a = vMeta.z * base;',
    '  float pulse = 0.0;',
    '  if (uMotion > 0.5 && vMeta.x >= 0.0) {',
    '    float head = fract(uTime * 0.20 + vMeta.x);',
    '    float d = vS - head;',
    '    d -= floor(d + 0.5);',
    '    pulse = exp(-(d * d) / (2.0 * 0.030 * 0.030));',
    '    a += vMeta.z * pulse * 1.9;',
    '  }',
    '  col = mix(col, uHot, clamp(pulse * 0.85, 0.0, 1.0));',
    '  a *= uGain;',
    '  frag = vec4(col * a, a);',
    '}'
  ].join('\n');

  var VS_LABEL = [
    '#version 300 es',
    'layout(location = 0) in vec2 aCorner;',
    'layout(location = 1) in vec3 aAnchor;',
    'layout(location = 2) in float aMode;',
    'layout(location = 3) in vec2 aOffPx;',
    'layout(location = 4) in vec2 aSizePx;',
    'layout(location = 5) in vec4 aUV;',
    'layout(location = 6) in float aOpacity;',
    'uniform mat4 uViewProj;',
    'uniform vec2 uViewport;',
    'out vec2 vUV;',
    'out float vOpacity;',
    'void main(){',
    '  vec2 ndc;',
    '  if (aMode < 0.5) {',
    '    vec4 cp = uViewProj * vec4(aAnchor, 1.0);',
    '    if (cp.w <= 0.0) { gl_Position = vec4(2.0, 2.0, 2.0, 1.0); vUV = vec2(0.0); vOpacity = 0.0; return; }',
    '    ndc = cp.xy / cp.w;',
    '  } else {',
    '    ndc = aAnchor.xy;',
    '  }',
    '  vec2 px = (ndc * 0.5 + 0.5) * uViewport + aOffPx + aCorner * aSizePx;',
    '  gl_Position = vec4((px / uViewport) * 2.0 - 1.0, 0.0, 1.0);',
    '  vUV = vec2(mix(aUV.x, aUV.z, aCorner.x), mix(aUV.w, aUV.y, aCorner.y));',
    '  vOpacity = aOpacity;',
    '}'
  ].join('\n');

  var FS_LABEL = [
    '#version 300 es',
    'precision highp float;',
    'in vec2 vUV;',
    'in float vOpacity;',
    'uniform sampler2D uTex;',
    'out vec4 frag;',
    'void main(){',
    '  vec4 t = texture(uTex, vUV);',
    '  frag = t * vOpacity;',
    '}'
  ].join('\n');

  var VS_BG = [
    '#version 300 es',
    'layout(location = 0) in vec2 aCorner;',
    'out vec2 vUV;',
    'void main(){',
    '  vUV = aCorner;',
    '  gl_Position = vec4(aCorner * 2.0 - 1.0, 0.0, 1.0);',
    '}'
  ].join('\n');

  var FS_BG = [
    '#version 300 es',
    'precision highp float;',
    'in vec2 vUV;',
    'uniform vec3 uTop;',
    'uniform vec3 uBottom;',
    'out vec4 frag;',
    'void main(){',
    '  vec3 col = mix(uBottom, uTop, pow(vUV.y, 1.35));',
    '  vec2 d = vUV - 0.5;',
    '  col *= 1.0 - 0.55 * dot(d, d);',
    '  frag = vec4(col, 1.0);',
    '}'
  ].join('\n');

  /* =====================================================================
   * 7. Thin WebGL2 plumbing.
   * =================================================================== */

  function logErr(msg) {
    if (global.console && global.console.error) { global.console.error('[MAARS skywave] ' + msg); }
  }

  function compileShader(gl, type, src, name) {
    var sh = gl.createShader(type);
    gl.shaderSource(sh, src);
    gl.compileShader(sh);
    if (!gl.getShaderParameter(sh, gl.COMPILE_STATUS)) {
      logErr(name + ' shader did not compile:\n' + gl.getShaderInfoLog(sh));
      gl.deleteShader(sh);
      return null;
    }
    return sh;
  }

  function makeProgram(gl, vsSrc, fsSrc, name) {
    var vs = compileShader(gl, gl.VERTEX_SHADER, vsSrc, name + ' vertex');
    if (!vs) { return null; }
    var fs = compileShader(gl, gl.FRAGMENT_SHADER, fsSrc, name + ' fragment');
    if (!fs) { gl.deleteShader(vs); return null; }
    var p = gl.createProgram();
    gl.attachShader(p, vs);
    gl.attachShader(p, fs);
    gl.linkProgram(p);
    gl.deleteShader(vs);
    gl.deleteShader(fs);
    if (!gl.getProgramParameter(p, gl.LINK_STATUS)) {
      logErr(name + ' program did not link: ' + gl.getProgramInfoLog(p));
      gl.deleteProgram(p);
      return null;
    }
    var u = {}, a = {}, i, info, n;
    n = gl.getProgramParameter(p, gl.ACTIVE_UNIFORMS);
    for (i = 0; i < n; i++) {
      info = gl.getActiveUniform(p, i);
      u[info.name.replace(/\[0\]$/, '')] = gl.getUniformLocation(p, info.name);
    }
    n = gl.getProgramParameter(p, gl.ACTIVE_ATTRIBUTES);
    for (i = 0; i < n; i++) {
      info = gl.getActiveAttrib(p, i);
      a[info.name] = gl.getAttribLocation(p, info.name);
    }
    return { p: p, u: u, a: a, name: name };
  }

  /** Spherical cap of unit vectors around +Y, denser toward the middle. */
  function capMesh(thetaMaxDeg, rings, segs) {
    var verts = new Float32Array((rings + 1) * (segs + 1) * 3);
    var idx = new Uint16Array(rings * segs * 6);
    var tmax = thetaMaxDeg * DEG, vi = 0, ii = 0, i, j, t, th, st, ct, ph;
    for (i = 0; i <= rings; i++) {
      t = Math.pow(i / rings, 1.45);
      th = t * tmax;
      st = Math.sin(th); ct = Math.cos(th);
      for (j = 0; j <= segs; j++) {
        ph = (j / segs) * Math.PI * 2;
        verts[vi++] = st * Math.sin(ph);
        verts[vi++] = ct;
        verts[vi++] = st * Math.cos(ph);
      }
    }
    for (i = 0; i < rings; i++) {
      for (j = 0; j < segs; j++) {
        var r0 = i * (segs + 1) + j, r1 = (i + 1) * (segs + 1) + j;
        idx[ii++] = r0; idx[ii++] = r1; idx[ii++] = r0 + 1;
        idx[ii++] = r0 + 1; idx[ii++] = r1; idx[ii++] = r1 + 1;
      }
    }
    return { verts: verts, idx: idx, count: ii, capCos: Math.cos(tmax) };
  }

  /* =====================================================================
   * 8. Label atlas. Text is rasterised once into an ordinary 2D canvas and
   * uploaded as a premultiplied texture; the labels are then screen-space
   * quads. This keeps real typography without shipping a font or a library.
   * =================================================================== */

  var FONT_STACK = '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, ' +
    '"Helvetica Neue", Arial, "DejaVu Sans", sans-serif';

  function fontFor(px, weight) { return (weight || 600) + ' ' + px + 'px ' + FONT_STACK; }

  function roundRectPath(ctx, x, y, w, h, r) {
    r = Math.min(r, w / 2, h / 2);
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.lineTo(x + w - r, y);
    ctx.arcTo(x + w, y, x + w, y + r, r);
    ctx.lineTo(x + w, y + h - r);
    ctx.arcTo(x + w, y + h, x + w - r, y + h, r);
    ctx.lineTo(x + r, y + h);
    ctx.arcTo(x, y + h, x, y + h - r, r);
    ctx.lineTo(x, y + r);
    ctx.arcTo(x, y, x + r, y, r);
    ctx.closePath();
  }

  /**
   * items: [{ lines: [{ text, px, color, weight, gap }], panel: bool }]
   * Returns { canvas, boxes: [{x,y,w,h}] } in device pixels.
   */
  function buildAtlas(items, dpr) {
    var mc = document.createElement('canvas');
    var mx = mc.getContext('2d');
    var pad = Math.round(9 * dpr), lead = Math.round(4 * dpr);
    var maxW = Math.round(1024 * Math.max(1, dpr / 2));
    var boxes = [], i, j, it, ln, w, h, lw;

    for (i = 0; i < items.length; i++) {
      it = items[i]; w = 0; h = 0;
      for (j = 0; j < it.lines.length; j++) {
        ln = it.lines[j];
        mx.font = fontFor(Math.round(ln.px * dpr), ln.weight);
        lw = mx.measureText(ln.text).width;
        if (lw > w) { w = lw; }
        h += Math.round(ln.px * dpr * 1.30) + (j ? lead : 0);
      }
      var bw = Math.ceil(w) + (it.panel ? pad * 2 : Math.round(6 * dpr));
      var bh = Math.ceil(h) + (it.panel ? pad * 2 : Math.round(6 * dpr));
      boxes.push({ w: Math.min(bw, maxW), h: bh });
    }

    var x = 0, y = 0, rowH = 0, gap = 2;
    for (i = 0; i < boxes.length; i++) {
      if (x + boxes[i].w + gap > maxW && x > 0) { x = 0; y += rowH + gap; rowH = 0; }
      boxes[i].x = x; boxes[i].y = y;
      x += boxes[i].w + gap;
      if (boxes[i].h > rowH) { rowH = boxes[i].h; }
    }
    var atlasW = maxW, atlasH = Math.max(4, y + rowH + gap);

    var cv = document.createElement('canvas');
    cv.width = atlasW; cv.height = atlasH;
    var cx = cv.getContext('2d');
    cx.clearRect(0, 0, atlasW, atlasH);
    cx.textBaseline = 'top';

    for (i = 0; i < items.length; i++) {
      it = items[i];
      var b = boxes[i];
      var ox = b.x + (it.panel ? pad : Math.round(3 * dpr));
      var oy = b.y + (it.panel ? pad : Math.round(3 * dpr));
      if (it.panel) {
        cx.fillStyle = CSS.panel;
        roundRectPath(cx, b.x + 0.5, b.y + 0.5, b.w - 1, b.h - 1, Math.round(5 * dpr));
        cx.fill();
        cx.strokeStyle = CSS.panelEdge;
        cx.lineWidth = Math.max(1, dpr);
        cx.stroke();
      }
      for (j = 0; j < it.lines.length; j++) {
        ln = it.lines[j];
        cx.font = fontFor(Math.round(ln.px * dpr), ln.weight);
        cx.fillStyle = ln.color || CSS.lavender;
        if (!it.panel) {
          cx.shadowColor = 'rgba(6,6,18,0.95)';
          cx.shadowBlur = Math.round(4 * dpr);
        } else {
          cx.shadowColor = 'rgba(0,0,0,0)';
          cx.shadowBlur = 0;
        }
        cx.fillText(ln.text, ox, oy);
        oy += Math.round(ln.px * dpr * 1.30) + lead;
      }
      cx.shadowColor = 'rgba(0,0,0,0)';
      cx.shadowBlur = 0;
    }
    return { canvas: cv, boxes: boxes, w: atlasW, h: atlasH };
  }

  /* =====================================================================
   * 9. Presentation helpers.
   * =================================================================== */

  function fmtInt(v) {
    return Math.round(v).toString().replace(/\B(?=(\d{3})+(?!\d))/g, ',');
  }
  function fmtUTC(d) {
    return d.toISOString().slice(0, 16).replace('T', ' ') + ' UTC';
  }
  function bandByKey(k) {
    if (k === null || k === undefined) { return null; }
    var s = String(k).toLowerCase().replace(/[^0-9]/g, '');
    for (var i = 0; i < BANDS.length; i++) {
      if (BANDS[i].key === s) { return BANDS[i]; }
    }
    return null;
  }
  function dayWord(day) {
    if (day > 0.75) { return 'DAY AT MANHATTAN'; }
    if (day < 0.12) { return 'NIGHT AT MANHATTAN'; }
    return 'TWILIGHT AT MANHATTAN';
  }

  /* =====================================================================
   * 10. Scene state: everything the physics decides for a given band and
   *     moment. Recomputed on band change and every 30 s of wall clock so
   *     the terminator actually moves.
   * =================================================================== */

  function computeState(band, date, exag) {
    var sun = subsolarPoint(date);
    var sunGeo = geoVec(sun.lat, sun.lon);
    var siteGeo = geoVec(SITE.lat, SITE.lon);
    var cosZ = vdot(sunGeo, siteGeo);
    var day = smoothstep(-0.12, 0.16, cosZ);
    var iono = ionosphere(day);
    var f = band.mhz;
    var scan = scanBand(f, iono);

    var st = {
      band: band, date: date, exag: exag,
      sunGeo: sunGeo, day: day, iono: iono, scan: scan,
      rOf: makeAltScale(exag),
      ringElevs: [], landings: [],
      losKm: band.vhf ? radioHorizonKm(band.antennaM, 3) : null
    };

    /* foF2 sec(phi) for a nominal 3000 km F2 path -- the MUF(3000) every
     * propagation chart quotes. */
    var e3000 = null, g3000, i;
    for (i = 1; i <= 88; i += 0.25) {
      g3000 = hopGeometry(i, LAYER_H.F2);
      if (g3000 && g3000.hopKm <= 3000) { e3000 = i; break; }
    }
    var foF2 = iono[3].fo;
    st.foF2 = foF2;
    st.foE = iono[1].fo;
    st.foF1 = iono[2].fo;
    st.muf3000 = e3000 ? foF2 * hopGeometry(e3000, LAYER_H.F2).secPhi : foF2;

    /* Absorption quoted for a representative low-angle path. */
    st.absDb = 2 * absorptionDb(f, scan.anyReflect ? clamp(scan.skipElev, 8, 60) : 15, day);

    if (scan.anyReflect) {
      if (scan.skipKm > 150) { st.ringElevs.push(scan.skipElev); }
      var e1 = elevForHop(f, iono, Math.max(scan.skipKm, 750));
      var e2 = elevForHop(f, iono, Math.max(scan.skipKm * 2.0, 2300));
      if (e1 !== null && !st.ringElevs.some(function (v) { return Math.abs(v - e1) < 1.2; })) {
        st.ringElevs.push(e1);
      }
      if (e2 !== null && !st.ringElevs.some(function (v) { return Math.abs(v - e2) < 1.2; })) {
        st.ringElevs.push(e2);
      }
    }

    st.hopKm = null;
    if (st.ringElevs.length) {
      var h0 = solveRay(f, st.ringElevs[st.ringElevs.length - 1], iono);
      if (h0.mode === 'reflect') { st.hopKm = h0.hopKm; }
    }

    /* Which layer is doing the work, for the shell highlight. */
    st.activeLayer = scan.anyReflect ? scan.skipLayer : '';

    st.headline = headlineFor(st);
    st.aria = describeAria(st);
    return st;
  }

  function headlineFor(st) {
    var s = st.scan;
    if (!s.anyReflect) {
      if (st.band.vhf) { return 'ESCAPES TO SPACE \u00b7 LINE OF SIGHT ONLY'; }
      return 'BAND CLOSED \u00b7 EVERY RAY ESCAPES';
    }
    var head = s.skipKm < 120
      ? s.skipLayer + ' REFLECTION \u00b7 NO SKIP ZONE (NVIS)'
      : s.skipLayer + ' REFLECTION \u00b7 SKIP ZONE ' + fmtInt(s.skipKm) + ' KM';
    if (st.absDb > 18) {
      head += ' \u00b7 ' + Math.round(st.absDb) + ' dB D-LAYER LOSS';
    }
    return head;
  }

  function describeAria(st) {
    var b = st.band, s = st.scan, out = [];
    out.push('Three dimensional skywave propagation map centred on Manhattan, Kansas.');
    out.push('Band: ' + b.spoken + '.');
    out.push(st.day > 0.75 ? 'It is daytime at Manhattan.'
      : (st.day < 0.12 ? 'It is night at Manhattan.' : 'It is twilight at Manhattan.'));
    if (b.vhf) {
      out.push('At ' + b.mhz + ' megahertz the signal is roughly ' +
        Math.round(b.mhz / Math.max(st.foF2, 0.1)) +
        ' times the critical frequency of the ionosphere, which is about ' +
        st.foF2.toFixed(1) + ' megahertz, so the rays pass straight through every layer ' +
        'and escape to space. There is no skip and no skip zone.');
      out.push('Coverage is line of sight only, roughly ' + Math.round(st.losKm) +
        ' kilometres to the radio horizon. That figure is illustrative: the repeater site ' +
        'and antenna height are unverified since the machine moved in November 2023.');
    } else if (!s.anyReflect) {
      out.push('The band is closed. The critical frequency of the F2 layer is only ' +
        st.foF2.toFixed(1) + ' megahertz, so every ray at every take-off angle passes ' +
        'through the ionosphere and is lost to space.');
    } else if (s.skipKm < 120) {
      out.push('Signals reflect from the ' + s.skipLayer + ' layer near ' +
        (s.skipLayer === 'E' ? '110' : (s.skipLayer === 'F1' ? '200' : '300')) +
        ' kilometres. There is no skip zone: near vertical incidence works, so the band ' +
        'covers the ground continuously from directly overhead outwards.');
    } else {
      out.push('Signals reflect from the ' + s.skipLayer + ' layer. The skip distance is about ' +
        fmtInt(s.skipKm) + ' kilometres, so there is a dead ring of ground around Manhattan, ' +
        'from zero out to ' + fmtInt(s.skipKm) + ' kilometres, where nothing lands.');
    }
    if (st.absDb > 6) {
      out.push('D layer absorption is about ' + Math.round(st.absDb) +
        ' decibels per hop right now, which is why the rays are drawn faint.');
    }
    out.push('Illustrative model based on the secant law and virtual reflection heights. ' +
      'Not a propagation prediction.');
    out.push('Drag, or use the arrow keys, to orbit the scene.');
    return out.join(' ');
  }

  /* =====================================================================
   * 11. mount()
   * =================================================================== */

  function noopHandle(extra) {
    var h = {
      destroy: function () {},
      setBand: function () {},
      getState: function () { return null; },
      fallback: true
    };
    if (extra) { for (var k in extra) { if (extra.hasOwnProperty(k)) { h[k] = extra[k]; } } }
    return h;
  }

  function mount(canvas, opts) {
    opts = opts || {};

    if (!canvas || typeof canvas.getContext !== 'function') {
      logErr('mount() needs a <canvas> element.');
      return noopHandle();
    }
    var parent = canvas.parentElement || canvas.parentNode || null;

    function markFallback() {
      if (parent && parent.classList) { parent.classList.add('maars-skywave--fallback'); }
      try { canvas.dataset.maarsFallback = '1'; } catch (e) { /* detached */ }
    }

    var gl = null;
    try {
      gl = canvas.getContext('webgl2', {
        alpha: false,
        depth: true,
        stencil: false,
        antialias: true,
        premultipliedAlpha: true,
        preserveDrawingBuffer: true,
        powerPreference: 'default',
        failIfMajorPerformanceCaveat: false
      });
    } catch (e) { gl = null; }

    if (!gl) {
      markFallback();
      return noopHandle();
    }

    /* ---------------- configuration ---------------- */
    var exag = Number(opts.altitudeExaggeration || canvas.getAttribute('data-maars-exag') || DEFAULT_EXAG) || DEFAULT_EXAG;
    var band = bandByKey(opts.band) || bandByKey(canvas.getAttribute('data-maars-band')) || BANDS[0];
    var fixedTime = opts.time ? new Date(opts.time) : null;
    var onState = typeof opts.onState === 'function' ? opts.onState : null;

    var camAz = (typeof opts.azimuthDeg === 'number' ? opts.azimuthDeg : 18) * DEG;
    var camEl = (typeof opts.elevationDeg === 'number' ? opts.elevationDeg : 30) * DEG;
    var camDist = typeof opts.distance === 'number' ? opts.distance : 0.86;

    var EL_MIN = 3 * DEG, EL_MAX = 78 * DEG, D_MIN = 0.55, D_MAX = 4.5;

    /* ---------------- lifecycle flags ---------------- */
    var destroyed = false, contextLost = false, ready = false;
    var rafId = 0, t0 = (global.performance || Date).now();
    var lastStateTick = -1e9;
    var dpr = 1, vw = 2, vh = 2;

    var mq = global.matchMedia ? global.matchMedia('(prefers-reduced-motion: reduce)') : null;
    var reduceMotion = !!(mq && mq.matches);

    var state = computeState(band, fixedTime || new Date(), exag);

    /* ---------------- GL resources ---------------- */
    var R = null;   /* everything deletable lives here */

    var mesh = capMesh(72, 56, 120);
    var basis = sceneBasis(SITE.lat, SITE.lon);
    var geoMat = geoFromSceneMat3(basis);

    var proj = mat4Identity(), view = mat4Identity(), viewProj = mat4Identity();
    var eye = [0, 0, 0];

    function createResources() {
      var r = { ok: false, buffers: [], vaos: [], programs: [], textures: [] };

      r.pEarth = makeProgram(gl, VS_CAP, FS_EARTH, 'earth');
      r.pShell = makeProgram(gl, VS_CAP, FS_SHELL, 'shell');
      r.pZone  = makeProgram(gl, VS_CAP, FS_ZONE, 'zone');
      r.pLine  = makeProgram(gl, VS_LINE, FS_LINE, 'line');
      r.pLabel = makeProgram(gl, VS_LABEL, FS_LABEL, 'label');
      r.pBg    = makeProgram(gl, VS_BG, FS_BG, 'background');
      if (!r.pEarth || !r.pShell || !r.pZone || !r.pLine || !r.pLabel || !r.pBg) {
        return r;
      }
      r.programs = [r.pEarth, r.pShell, r.pZone, r.pLine, r.pLabel, r.pBg];

      /* cap mesh */
      r.capVbo = gl.createBuffer();
      gl.bindBuffer(gl.ARRAY_BUFFER, r.capVbo);
      gl.bufferData(gl.ARRAY_BUFFER, mesh.verts, gl.STATIC_DRAW);
      r.capIbo = gl.createBuffer();
      gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, r.capIbo);
      gl.bufferData(gl.ELEMENT_ARRAY_BUFFER, mesh.idx, gl.STATIC_DRAW);
      r.buffers.push(r.capVbo, r.capIbo);

      r.capVao = gl.createVertexArray();
      gl.bindVertexArray(r.capVao);
      gl.bindBuffer(gl.ARRAY_BUFFER, r.capVbo);
      gl.enableVertexAttribArray(0);
      gl.vertexAttribPointer(0, 3, gl.FLOAT, false, 0, 0);
      gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, r.capIbo);
      gl.bindVertexArray(null);
      r.vaos.push(r.capVao);

      /* full-screen quad (background) */
      r.quadVbo = gl.createBuffer();
      gl.bindBuffer(gl.ARRAY_BUFFER, r.quadVbo);
      gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([0, 0, 1, 0, 0, 1, 1, 1]), gl.STATIC_DRAW);
      r.buffers.push(r.quadVbo);
      r.quadVao = gl.createVertexArray();
      gl.bindVertexArray(r.quadVao);
      gl.enableVertexAttribArray(0);
      gl.vertexAttribPointer(0, 2, gl.FLOAT, false, 0, 0);
      gl.bindVertexArray(null);
      r.vaos.push(r.quadVao);

      /* ribbon lines (filled in by rebuildGeometry) */
      r.lineVbo = gl.createBuffer();
      r.lineIbo = gl.createBuffer();
      r.buffers.push(r.lineVbo, r.lineIbo);
      r.lineCount = 0;
      r.lineVao = gl.createVertexArray();
      gl.bindVertexArray(r.lineVao);
      gl.bindBuffer(gl.ARRAY_BUFFER, r.lineVbo);
      var S = 12 * 4;
      gl.enableVertexAttribArray(0); gl.vertexAttribPointer(0, 3, gl.FLOAT, false, S, 0);
      gl.enableVertexAttribArray(1); gl.vertexAttribPointer(1, 3, gl.FLOAT, false, S, 12);
      gl.enableVertexAttribArray(2); gl.vertexAttribPointer(2, 1, gl.FLOAT, false, S, 24);
      gl.enableVertexAttribArray(3); gl.vertexAttribPointer(3, 1, gl.FLOAT, false, S, 28);
      gl.enableVertexAttribArray(4); gl.vertexAttribPointer(4, 3, gl.FLOAT, false, S, 32);
      gl.enableVertexAttribArray(5); gl.vertexAttribPointer(5, 1, gl.FLOAT, false, S, 44);
      gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, r.lineIbo);
      gl.bindVertexArray(null);
      r.vaos.push(r.lineVao);

      /* labels: unit quad + instance buffer */
      r.labQuad = gl.createBuffer();
      gl.bindBuffer(gl.ARRAY_BUFFER, r.labQuad);
      gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([0, 0, 1, 0, 0, 1, 1, 1]), gl.STATIC_DRAW);
      r.labInst = gl.createBuffer();
      r.buffers.push(r.labQuad, r.labInst);
      r.labVao = gl.createVertexArray();
      gl.bindVertexArray(r.labVao);
      gl.bindBuffer(gl.ARRAY_BUFFER, r.labQuad);
      gl.enableVertexAttribArray(0); gl.vertexAttribPointer(0, 2, gl.FLOAT, false, 0, 0);
      gl.bindBuffer(gl.ARRAY_BUFFER, r.labInst);
      var L = 13 * 4;
      gl.enableVertexAttribArray(1); gl.vertexAttribPointer(1, 3, gl.FLOAT, false, L, 0);  gl.vertexAttribDivisor(1, 1);
      gl.enableVertexAttribArray(2); gl.vertexAttribPointer(2, 1, gl.FLOAT, false, L, 12); gl.vertexAttribDivisor(2, 1);
      gl.enableVertexAttribArray(3); gl.vertexAttribPointer(3, 2, gl.FLOAT, false, L, 16); gl.vertexAttribDivisor(3, 1);
      gl.enableVertexAttribArray(4); gl.vertexAttribPointer(4, 2, gl.FLOAT, false, L, 24); gl.vertexAttribDivisor(4, 1);
      gl.enableVertexAttribArray(5); gl.vertexAttribPointer(5, 4, gl.FLOAT, false, L, 32); gl.vertexAttribDivisor(5, 1);
      gl.enableVertexAttribArray(6); gl.vertexAttribPointer(6, 1, gl.FLOAT, false, L, 48); gl.vertexAttribDivisor(6, 1);
      gl.bindVertexArray(null);
      r.vaos.push(r.labVao);

      r.labTex = gl.createTexture();
      r.textures.push(r.labTex);
      gl.bindTexture(gl.TEXTURE_2D, r.labTex);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
      gl.bindTexture(gl.TEXTURE_2D, null);

      r.ok = true;
      return r;
    }

    function destroyResources() {
      if (!R) { return; }
      var i;
      try {
        for (i = 0; i < R.vaos.length; i++) { gl.deleteVertexArray(R.vaos[i]); }
        for (i = 0; i < R.buffers.length; i++) { gl.deleteBuffer(R.buffers[i]); }
        for (i = 0; i < R.textures.length; i++) { gl.deleteTexture(R.textures[i]); }
        for (i = 0; i < R.programs.length; i++) {
          if (R.programs[i]) { gl.deleteProgram(R.programs[i].p); }
        }
      } catch (e) { /* context already gone */ }
      R = null;
    }

    /* ---------------- ray + decoration geometry ---------------- */

    var geometryDirty = true, labelsDirty = true;
    var labelDefs = [], labelInstances = null, atlasSize = [1, 1];

    function pushRayInto(rib, elevDeg, az, phase, maxHops, dim, landings) {
      var r = buildRay(state.band.mhz, elevDeg, state.iono, state.day, maxHops);
      var pts = [], i, p;
      for (i = 0; i < r.pts.length; i++) {
        p = scenePoint(r.pts[i][0], r.pts[i][1], az, state.rOf);
        pts.push([p[0], p[1], p[2], r.pts[i][2] * dim]);
      }
      ribbonPush(rib, pts, r.escaped ? 2 : 0, phase, r.escaped ? 0.8 : 1.0);
      for (i = 0; i < r.landings.length; i++) { landings.push(r.landings[i]); }
      return r;
    }

    function rebuildGeometry() {
      geometryDirty = false;
      if (!R || !R.ok) { return; }
      var rib = ribbonInit(), landings = [], i, j, az;
      var AZ = 10;
      var fan = [4, 8, 13, 19, 26, 34, 44, 57, 72];
      var rOf = state.rOf;

      /* Rings of rays in every direction -- these are what make the skip
       * zone read as a ring rather than as a diagram. */
      for (i = 0; i < AZ; i++) {
        az = (i / AZ) * Math.PI * 2;
        for (j = 0; j < state.ringElevs.length; j++) {
          pushRayInto(rib, state.ringElevs[j], az,
            (j * 0.34) % 1, j === 0 ? 3 : 2, 1.0, landings);
        }
        if (!state.scan.anyReflect) {
          pushRayInto(rib, 18 + (i % 3) * 9, az, (i * 0.17) % 1, 1, 0.85, landings);
        }
      }

      /* A full take-off-angle fan on two opposite azimuths: the classic
       * cross-section, showing which angles come back and which do not. */
      var fanAz = [Math.PI / 2, -Math.PI / 2];
      for (i = 0; i < fanAz.length; i++) {
        for (j = 0; j < fan.length; j++) {
          pushRayInto(rib, fan[j], fanAz[i], (j * 0.11) % 1, 2, 0.9, landings);
        }
      }

      /* Decorations: site pin, hop rings, skip boundary. */
      var pin = [];
      for (i = 0; i <= 6; i++) {
        pin.push([0, rOf(330 * (i / 6)), 0, 0.18 + 0.42 * (1 - i / 6)]);
      }
      ribbonPush(rib, pin, 3, -1, 1.2);
      ribbonPush(rib, ringPoints(70, 4, rOf, 0.85, 64), 3, -1, 1.1);

      var seen = {};
      landings.sort(function (a, b) { return a - b; });
      for (i = 0; i < landings.length; i++) {
        var km = Math.round(landings[i] / 40) * 40;
        if (km < 60 || km > 9000 || seen[km]) { continue; }
        seen[km] = 1;
        ribbonPush(rib, ringPoints(km, 7, rOf, 0.42, 96), 1, -1, 0.8);
      }
      if (state.scan.anyReflect && state.scan.skipKm > 60) {
        ribbonPush(rib, ringPoints(state.scan.skipKm, 9, rOf, 0.95, 128), 3, -1, 1.35);
      }
      if (state.losKm) {
        ribbonPush(rib, ringPoints(state.losKm, 5, rOf, 0.9, 96), 3, -1, 1.35);
      }

      var verts = new Float32Array(rib.v);
      var idx = new Uint32Array(rib.idx);
      gl.bindBuffer(gl.ARRAY_BUFFER, R.lineVbo);
      gl.bufferData(gl.ARRAY_BUFFER, verts, gl.DYNAMIC_DRAW);
      gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, R.lineIbo);
      gl.bufferData(gl.ELEMENT_ARRAY_BUFFER, idx, gl.DYNAMIC_DRAW);
      gl.bindBuffer(gl.ARRAY_BUFFER, null);
      gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, null);
      R.lineCount = idx.length;
    }

    /* ---------------- labels ---------------- */

    function layerLine(id, h, fo) {
      if (fo <= 0) {
        return id + ' ' + h + ' KM \u00b7 ABSENT';
      }
      return id + ' ' + h + ' KM \u00b7 fo' + id + ' ' + fo.toFixed(1) + ' MHz';
    }

    function rebuildLabels() {
      labelsDirty = false;
      if (!R || !R.ok) { return; }
      var st = state, items = [], defs = [];
      var ui = clamp(vw / (960 * dpr), 0.72, 1.2);
      var wide = vw / dpr > 620;
      var tall = vh / dpr > 380;

      function add(lines, panel, def) {
        var k;
        for (k = 0; k < lines.length; k++) { lines[k].px = lines[k].px * ui; }
        def.item = items.length;
        items.push({ lines: lines, panel: panel });
        defs.push(def);
      }

      var warn = (!st.scan.anyReflect) || st.absDb > 18;

      add([
        { text: st.band.name + '  ' + st.band.mhz.toFixed(3) + ' MHz', px: 19, color: CSS.lavender, weight: 700 },
        { text: st.band.net, px: 11.5, color: CSS.magentaLt, weight: 700 },
        { text: st.headline, px: 11.5, color: warn ? CSS.alarm : CSS.navyLight, weight: 600 }
      ], true, { mode: 1, align: 'tl' });

      if (wide && tall) {
        add([
          { text: dayWord(st.day), px: 12, color: CSS.lavender, weight: 700 },
          { text: 'foE ' + st.foE.toFixed(1) + '  foF1 ' + (st.foF1 > 0 ? st.foF1.toFixed(1) : '\u2014') +
                  '  foF2 ' + st.foF2.toFixed(1) + ' MHz', px: 11, color: CSS.paperDim, weight: 600 },
          { text: 'MUF(3000) ' + st.muf3000.toFixed(1) + ' MHz \u00b7 D-LAYER ' +
                  Math.round(st.absDb) + ' dB/HOP', px: 11, color: CSS.paperDim, weight: 600 },
          { text: fmtUTC(st.date), px: 10.5, color: CSS.paperDim, weight: 600 }
        ], true, { mode: 1, align: 'tr' });
      }

      add([
        { text: 'ILLUSTRATIVE MODEL \u2014 SECANT LAW, VIRTUAL HEIGHTS.', px: 10.5, color: CSS.paperDim, weight: 600 },
        { text: 'NOT A PROPAGATION PREDICTION.', px: 10.5, color: CSS.alarm, weight: 700 }
      ], true, { mode: 1, align: 'bl' });

      if (wide) {
        add([
          { text: 'ALTITUDES \u00d7' + st.exag + ' \u00b7 DRAG OR ARROW KEYS TO ORBIT', px: 10.5, color: CSS.paperDim, weight: 600 }
        ], true, { mode: 1, align: 'br' });
      }

      add([{ text: 'MANHATTAN, KANSAS \u00b7 KS\u00d8MAN', px: 11.5, color: CSS.lavender, weight: 700 }],
        false, { mode: 0, kind: 'site' });

      if (tall) {
        var L = st.iono, colats = [0.34, 0.34, 0.34, 0.34], k;
        for (k = 0; k < 4; k++) {
          var active = (L[k].id === st.activeLayer);
          var absorbing = (L[k].id === 'D' && st.absDb > 6);
          add([{
            text: L[k].id === 'D'
              ? (st.day > 0.15
                  ? 'D 75 KM \u00b7 ABSORBS ' + Math.round(st.absDb / 2) + ' dB EACH WAY'
                  : 'D 75 KM \u00b7 GONE AT NIGHT')
              : layerLine(L[k].id, L[k].h, L[k].fo),
            px: 10.5,
            color: active ? CSS.magentaLt : (absorbing ? CSS.alarm : CSS.paperDim),
            weight: active ? 700 : 600
          }], false, { mode: 0, kind: 'layer', h: L[k].h, colat: colats[k] });
        }
      }

      if (st.scan.anyReflect && st.scan.skipKm > 60) {
        add([{ text: 'SKIP ZONE \u00b7 NOTHING LANDS INSIDE ' + fmtInt(st.scan.skipKm) + ' KM',
               px: 11, color: CSS.alarm, weight: 700 }],
          false, { mode: 0, kind: 'ground', km: st.scan.skipKm, azOff: 0, oy: -22 });
      } else if (st.scan.anyReflect) {
        add([{ text: 'NO SKIP ZONE \u00b7 NVIS COVERS THE GROUND UNDER YOU',
               px: 11, color: CSS.magentaLt, weight: 700 }],
          false, { mode: 0, kind: 'ground', km: 520, azOff: 0, oy: -22 });
      }

      /* Only claim a landing point when enough of the ray survives to get there. */
      if (st.hopKm && st.hopKm > 250 && st.absDb < 26) {
        add([{ text: 'FIRST HOP LANDS AT ' + fmtInt(st.hopKm) + ' KM',
               px: 10.5, color: CSS.magentaLt, weight: 700 }],
          false, { mode: 0, kind: 'ground', km: st.hopKm, azOff: -1.05, oy: -20 });
      }

      if (st.losKm) {
        add([{ text: 'RADIO HORIZON \u2248 ' + Math.round(st.losKm) + ' KM (UNVERIFIED SITE)',
               px: 11, color: CSS.magentaLt, weight: 700 }],
          false, { mode: 0, kind: 'ground', km: st.losKm, azOff: 0, oy: -30 });
        add([{ text: '147.255 MHz IS \u2248' + Math.round(st.band.mhz / Math.max(st.foF2, 0.1)) +
                     '\u00d7 THE CRITICAL FREQUENCY \u2014 NO REFRACTION',
               px: 11, color: CSS.alarm, weight: 700 }],
          false, { mode: 0, kind: 'sky', alt: 1500, colat: 0.36, azOff: -0.78 });
      } else if (!st.scan.anyReflect) {
        add([{ text: 'EVERY RAY PENETRATES \u2014 BAND CLOSED', px: 11, color: CSS.alarm, weight: 700 }],
          false, { mode: 0, kind: 'sky', alt: 1300, colat: 0.34, azOff: -0.78 });
      }

      var atlas = buildAtlas(items, dpr);
      atlasSize = [atlas.w, atlas.h];
      gl.bindTexture(gl.TEXTURE_2D, R.labTex);
      gl.pixelStorei(gl.UNPACK_PREMULTIPLY_ALPHA_WEBGL, true);
      gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, false);
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, atlas.canvas);
      gl.pixelStorei(gl.UNPACK_PREMULTIPLY_ALPHA_WEBGL, false);
      gl.bindTexture(gl.TEXTURE_2D, null);

      for (var i = 0; i < defs.length; i++) { defs[i].box = atlas.boxes[defs[i].item]; }
      labelDefs = defs;
      labelInstances = new Float32Array(defs.length * 13);
    }

    function packLabels() {
      var m = 14 * dpr, i, d, b, o = 0, anchor, opacity, u0, v0, u1, v1;
      for (i = 0; i < labelDefs.length; i++) {
        d = labelDefs[i]; b = d.box;
        opacity = 1;
        anchor = [0, 0, 0];
        var ox = 0, oy = 0;
        if (d.mode === 1) {
          if (d.align === 'tl') { anchor = [-1, 1, 0]; ox = m; oy = -b.h - m; }
          else if (d.align === 'tr') { anchor = [1, 1, 0]; ox = -b.w - m; oy = -b.h - m; }
          else if (d.align === 'bl') { anchor = [-1, -1, 0]; ox = m; oy = m; }
          else { anchor = [1, -1, 0]; ox = -b.w - m; oy = m; }
        } else {
          if (d.kind === 'site') {
            anchor = scenePoint(0, 330, 0, state.rOf);
          } else if (d.kind === 'layer') {
            anchor = scenePoint(d.colat, d.h, camAz + 0.92, state.rOf);
          } else if (d.kind === 'sky') {
            anchor = scenePoint(d.colat, d.alt, camAz + (d.azOff || 0), state.rOf);
          } else {
            anchor = scenePoint(d.km / R_KM, 12, camAz + (d.azOff || 0), state.rOf);
          }
          ox = -b.w / 2;
          oy = (typeof d.oy === 'number' ? d.oy : 10) * dpr;
          var toEye = vnorm(vsub(eye, anchor));
          opacity = smoothstep(-0.06, 0.10, vdot(vnorm(anchor), toEye));
        }
        u0 = b.x / atlasSize[0]; v0 = b.y / atlasSize[1];
        u1 = (b.x + b.w) / atlasSize[0]; v1 = (b.y + b.h) / atlasSize[1];
        labelInstances[o++] = anchor[0]; labelInstances[o++] = anchor[1]; labelInstances[o++] = anchor[2];
        labelInstances[o++] = d.mode;
        labelInstances[o++] = ox; labelInstances[o++] = oy;
        labelInstances[o++] = b.w; labelInstances[o++] = b.h;
        labelInstances[o++] = u0; labelInstances[o++] = v0; labelInstances[o++] = u1; labelInstances[o++] = v1;
        labelInstances[o++] = opacity;
      }
    }

    /* ---------------- drawing ---------------- */

    function drawCap(prog, radius) {
      gl.uniform1f(prog.u.uRadius, radius);
      gl.drawElements(gl.TRIANGLES, mesh.count, gl.UNSIGNED_SHORT, 0);
    }

    function draw(tSec) {
      if (!R || !R.ok) { return; }
      var st = state;

      gl.viewport(0, 0, vw, vh);
      gl.clearColor(C.ground[0], C.ground[1], C.ground[2], 1);
      gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);

      var ce = Math.cos(camEl), se = Math.sin(camEl);
      eye = [Math.sin(camAz) * ce * camDist, 1 + se * camDist, Math.cos(camAz) * ce * camDist];
      var aspect = Math.max(vw / vh, 0.25);
      /* Keep the horizontal field constant when the canvas goes portrait,
       * otherwise a narrow column shows a postage stamp of the scene. */
      var fovy = aspect < 1
        ? Math.min(72 * DEG, 2 * Math.atan(Math.tan(21 * DEG) / aspect))
        : 42 * DEG;
      mat4Perspective(proj, fovy, aspect, 0.01, 40);
      mat4LookAt(view, eye, [0, 1.045, 0], [0, 1, 0]);
      mat4Mul(viewProj, proj, view);

      /* background */
      gl.disable(gl.DEPTH_TEST);
      gl.depthMask(false);
      gl.disable(gl.BLEND);
      gl.useProgram(R.pBg.p);
      gl.uniform3f(R.pBg.u.uTop, 0.055, 0.055, 0.125);
      gl.uniform3f(R.pBg.u.uBottom, 0.020, 0.020, 0.052);
      gl.bindVertexArray(R.quadVao);
      gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);

      /* earth */
      gl.enable(gl.DEPTH_TEST);
      gl.depthFunc(gl.LEQUAL);
      gl.depthMask(true);
      gl.enable(gl.BLEND);
      gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);
      gl.bindVertexArray(R.capVao);
      gl.useProgram(R.pEarth.p);
      gl.uniformMatrix4fv(R.pEarth.u.uViewProj, false, viewProj);
      gl.uniformMatrix3fv(R.pEarth.u.uGeoFromScene, false, geoMat);
      gl.uniform3fv(R.pEarth.u.uSunGeo, st.sunGeo);
      gl.uniform1f(R.pEarth.u.uCapCos, mesh.capCos);
      gl.uniform3f(R.pEarth.u.uDay, C.navy[0], C.navy[1], C.navy[2]);
      gl.uniform3f(R.pEarth.u.uNight, 0.058, 0.058, 0.195);
      gl.uniform3fv(R.pEarth.u.uGrid, C.navyLight);
      gl.uniform3fv(R.pEarth.u.uRing, C.lavender);
      gl.uniform3fv(R.pEarth.u.uEye, eye);
      gl.uniform1f(R.pEarth.u.uEarthR, R_KM);
      drawCap(R.pEarth, 1.0);

      /* skip zone / line-of-sight footprint */
      gl.depthMask(false);
      gl.useProgram(R.pZone.p);
      gl.uniformMatrix4fv(R.pZone.u.uViewProj, false, viewProj);
      gl.uniform1f(R.pZone.u.uEarthR, R_KM);
      if (st.scan.anyReflect && st.scan.skipKm > 40) {
        gl.uniform1f(R.pZone.u.uOuterKm, st.scan.skipKm);
        gl.uniform3f(R.pZone.u.uTint, C.alarm[0], C.alarm[1], C.alarm[2]);
        gl.uniform3fv(R.pZone.u.uEdge, C.magentaLt);
        gl.uniform1f(R.pZone.u.uStyle, 0);
        gl.uniform1f(R.pZone.u.uAlpha, 0.42);
        drawCap(R.pZone, 1.0025);
      }
      if (st.losKm) {
        gl.uniform1f(R.pZone.u.uOuterKm, st.losKm);
        gl.uniform3fv(R.pZone.u.uTint, C.navyLight);
        gl.uniform3fv(R.pZone.u.uEdge, C.magentaLt);
        gl.uniform1f(R.pZone.u.uStyle, 1);
        gl.uniform1f(R.pZone.u.uAlpha, 0.30);
        drawCap(R.pZone, 1.0025);
      }

      /* rays: a wide dim pass for glow, then a narrow bright core */
      if (R.lineCount) {
        gl.blendFunc(gl.ONE, gl.ONE);
        gl.useProgram(R.pLine.p);
        gl.bindVertexArray(R.lineVao);
        gl.uniformMatrix4fv(R.pLine.u.uViewProj, false, viewProj);
        gl.uniform2f(R.pLine.u.uViewport, vw, vh);
        gl.uniform1f(R.pLine.u.uTime, tSec);
        gl.uniform1f(R.pLine.u.uMotion, reduceMotion ? 0 : 1);
        gl.uniform3fv(R.pLine.u.uRay, C.magenta);
        gl.uniform3fv(R.pLine.u.uDeco, C.navyLight);
        gl.uniform3f(R.pLine.u.uEscape, 0.45, 0.47, 0.85);
        gl.uniform3fv(R.pLine.u.uMark, C.lavender);
        gl.uniform3fv(R.pLine.u.uHot, C.magentaLt);
        gl.uniform1f(R.pLine.u.uWidth, 2.1 * dpr * 3.4);
        gl.uniform1f(R.pLine.u.uGain, 0.22);
        gl.drawElements(gl.TRIANGLES, R.lineCount, gl.UNSIGNED_INT, 0);
        gl.uniform1f(R.pLine.u.uWidth, 2.1 * dpr);
        gl.uniform1f(R.pLine.u.uGain, 0.85);
        gl.drawElements(gl.TRIANGLES, R.lineCount, gl.UNSIGNED_INT, 0);
      }

      /* ionospheric shells, additive, so they read as atmosphere */
      gl.blendFunc(gl.SRC_ALPHA, gl.ONE);
      gl.useProgram(R.pShell.p);
      gl.bindVertexArray(R.capVao);
      gl.uniformMatrix4fv(R.pShell.u.uViewProj, false, viewProj);
      gl.uniformMatrix3fv(R.pShell.u.uGeoFromScene, false, geoMat);
      gl.uniform3fv(R.pShell.u.uSunGeo, st.sunGeo);
      gl.uniform3fv(R.pShell.u.uEye, eye);
      gl.uniform1f(R.pShell.u.uCapCos, mesh.capCos);
      gl.uniform2f(R.pShell.u.uFade, 0.34, 0.80);
      for (var li = 0; li < st.iono.length; li++) {
        var Ly = st.iono[li];
        var active = (Ly.id === st.activeLayer);
        var col = C.lavender;
        var inten = active ? 0.95 : 0.42;
        var nightMul = 0.55;
        if (Ly.id === 'D') {
          var sev = clamp(st.absDb / 40, 0, 1);
          col = [
            C.lavender[0] * (1 - sev) + C.alarm[0] * sev + sev * 0.25,
            C.lavender[1] * (1 - sev) + C.alarm[1] * sev,
            C.lavender[2] * (1 - sev) + C.alarm[2] * sev
          ];
          inten = 0.30 + 0.85 * sev;
          nightMul = 0.06;
        } else if (Ly.fo <= 0) {
          inten = 0.16;
          nightMul = 0.20;
        }
        gl.uniform3fv(R.pShell.u.uColor, new Float32Array(col));
        gl.uniform1f(R.pShell.u.uIntensity, inten);
        gl.uniform1f(R.pShell.u.uNightMul, nightMul);
        drawCap(R.pShell, st.rOf(Ly.h));
      }

      /* labels */
      if (labelDefs.length) {
        packLabels();
        gl.disable(gl.DEPTH_TEST);
        gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA);
        gl.useProgram(R.pLabel.p);
        gl.bindVertexArray(R.labVao);
        gl.bindBuffer(gl.ARRAY_BUFFER, R.labInst);
        gl.bufferData(gl.ARRAY_BUFFER, labelInstances, gl.DYNAMIC_DRAW);
        gl.uniformMatrix4fv(R.pLabel.u.uViewProj, false, viewProj);
        gl.uniform2f(R.pLabel.u.uViewport, vw, vh);
        gl.activeTexture(gl.TEXTURE0);
        gl.bindTexture(gl.TEXTURE_2D, R.labTex);
        gl.uniform1i(R.pLabel.u.uTex, 0);
        gl.drawArraysInstanced(gl.TRIANGLE_STRIP, 0, 4, labelDefs.length);
      }

      gl.bindVertexArray(null);
      gl.flush();

      if (!ready) {
        ready = true;
        try { canvas.dataset.maarsReady = '1'; } catch (e) { /* detached */ }
      }
    }

    /* ---------------- sizing, loop ---------------- */

    function resize() {
      var d = Math.min(global.devicePixelRatio || 1, 2);
      var rect = canvas.getBoundingClientRect ? canvas.getBoundingClientRect() : null;
      var cw = (rect && rect.width) || canvas.clientWidth || 640;
      var ch = (rect && rect.height) || canvas.clientHeight || 400;
      var w = Math.max(2, Math.round(cw * d));
      var h = Math.max(2, Math.round(ch * d));
      if (w === vw && h === vh && d === dpr) { return; }
      vw = w; vh = h;
      if (canvas.width !== w) { canvas.width = w; }
      if (canvas.height !== h) { canvas.height = h; }
      if (d !== dpr) { dpr = d; }
      labelsDirty = true;
    }

    function frame() {
      rafId = 0;
      if (destroyed || contextLost) { return; }
      resize();
      var now = (global.performance || Date).now();
      if (!fixedTime && now - lastStateTick > 30000) {
        lastStateTick = now;
        applyState(computeState(band, new Date(), exag));
      }
      if (geometryDirty) { rebuildGeometry(); }
      if (labelsDirty) { rebuildLabels(); }
      draw(reduceMotion ? 0.35 : (now - t0) / 1000);
      if (!reduceMotion) { rafId = global.requestAnimationFrame(frame); }
    }

    function requestFrame() {
      if (destroyed || contextLost || rafId) { return; }
      rafId = global.requestAnimationFrame(frame);
    }

    function applyState(next) {
      state = next;
      geometryDirty = true;
      labelsDirty = true;
      try {
        canvas.setAttribute('aria-label', state.aria);
      } catch (e) { /* detached */ }
      if (onState) {
        try {
          onState({
            band: state.band.id,
            freqMhz: state.band.mhz,
            net: state.band.net,
            dayFactor: state.day,
            foE: state.foE, foF1: state.foF1, foF2: state.foF2,
            muf3000Mhz: state.muf3000,
            reflects: state.scan.anyReflect,
            layer: state.scan.skipLayer || null,
            skipKm: state.scan.anyReflect ? state.scan.skipKm : null,
            lineOfSightKm: state.losKm,
            absorptionDbPerHop: state.absDb,
            headline: state.headline,
            ariaLabel: state.aria
          });
        } catch (e) { logErr('onState callback threw: ' + e); }
      }
      requestFrame();
    }

    /* ---------------- interaction ---------------- */

    var dragging = false, lastX = 0, lastY = 0, pointerId = null;

    function onPointerDown(e) {
      if (e.pointerType === 'mouse' && e.button !== 0) { return; }
      dragging = true;
      pointerId = e.pointerId;
      lastX = e.clientX; lastY = e.clientY;
      if (canvas.setPointerCapture) {
        try { canvas.setPointerCapture(e.pointerId); } catch (err) { /* ignore */ }
      }
      e.preventDefault();
    }
    function onPointerMove(e) {
      if (!dragging || (pointerId !== null && e.pointerId !== pointerId)) { return; }
      var dx = e.clientX - lastX, dy = e.clientY - lastY;
      lastX = e.clientX; lastY = e.clientY;
      camAz -= dx * 0.0065;
      camEl = clamp(camEl + dy * 0.005, EL_MIN, EL_MAX);
      requestFrame();
      e.preventDefault();
    }
    function onPointerUp(e) {
      if (!dragging) { return; }
      dragging = false;
      if (canvas.releasePointerCapture && pointerId !== null) {
        try { canvas.releasePointerCapture(pointerId); } catch (err) { /* ignore */ }
      }
      pointerId = null;
    }
    function onWheel(e) {
      /* Only steal the wheel when the canvas is actually the focus, so the
       * page keeps scrolling normally otherwise. */
      if (document.activeElement !== canvas && !e.ctrlKey) { return; }
      camDist = clamp(camDist * (e.deltaY > 0 ? 1.09 : 0.917), D_MIN, D_MAX);
      requestFrame();
      e.preventDefault();
    }
    function onKeyDown(e) {
      var k = e.key, handled = true;
      if (k === 'ArrowLeft') { camAz -= 5 * DEG; }
      else if (k === 'ArrowRight') { camAz += 5 * DEG; }
      else if (k === 'ArrowUp') { camEl = clamp(camEl + 4 * DEG, EL_MIN, EL_MAX); }
      else if (k === 'ArrowDown') { camEl = clamp(camEl - 4 * DEG, EL_MIN, EL_MAX); }
      else if (k === '+' || k === '=') { camDist = clamp(camDist * 0.9, D_MIN, D_MAX); }
      else if (k === '-' || k === '_') { camDist = clamp(camDist * 1.1, D_MIN, D_MAX); }
      else { handled = false; }
      if (handled) { e.preventDefault(); requestFrame(); }
    }
    function onBandClick(e) {
      var el = e.target;
      while (el && el !== parent) {
        /* The canvas itself carries data-maars-band; only real controls count. */
        if (el !== canvas && el.getAttribute && el.getAttribute('data-maars-band')) {
          if (setBand(el.getAttribute('data-maars-band'))) { e.preventDefault(); }
          return;
        }
        el = el.parentNode;
      }
    }
    function onContextLost(e) {
      e.preventDefault();
      contextLost = true;
      if (rafId) { global.cancelAnimationFrame(rafId); rafId = 0; }
      R = null;
      ready = false;
      try { delete canvas.dataset.maarsReady; } catch (err) { /* ignore */ }
    }
    function onContextRestored() {
      if (destroyed) { return; }
      contextLost = false;
      R = createResources();
      if (!R || !R.ok) { markFallback(); return; }
      geometryDirty = true;
      labelsDirty = true;
      requestFrame();
    }
    function onMotionChange() {
      reduceMotion = !!(mq && mq.matches);
      if (!reduceMotion) { requestFrame(); }
      else if (rafId) { global.cancelAnimationFrame(rafId); rafId = 0; requestFrame(); }
    }

    /* ---------------- public methods ---------------- */

    /* The block renders real <button data-maars-band> controls next to the
       canvas. Clicking one routes through onBandClick -> setBand; this is the
       other half of that contract, so the pressed state a screen reader
       announces is the band actually being drawn. */
    function syncControls() {
      if (!parent || !parent.querySelectorAll) { return; }
      var nodes = parent.querySelectorAll('[data-maars-band]');
      for (var i = 0; i < nodes.length; i++) {
        var el = nodes[i];
        if (el === canvas) { continue; }
        var on = el.getAttribute('data-maars-band') === band.id;
        if (el.hasAttribute('aria-pressed') || el.tagName === 'BUTTON') {
          el.setAttribute('aria-pressed', on ? 'true' : 'false');
        }
        if (el.tagName === 'LI') {
          if (on) { el.setAttribute('data-current', '1'); }
          else { el.removeAttribute('data-current'); }
        }
      }
    }

    function setBand(key) {
      var b = bandByKey(key);
      if (!b || destroyed) { return false; }
      if (b === band) { return true; }
      band = b;
      try { canvas.setAttribute('data-maars-band', b.id); } catch (e) { /* ignore */ }
      applyState(computeState(band, fixedTime || new Date(), exag));
      syncControls();
      return true;
    }

    function setTime(t) {
      fixedTime = t ? new Date(t) : null;
      applyState(computeState(band, fixedTime || new Date(), exag));
    }

    function destroy() {
      if (destroyed) { return; }
      destroyed = true;
      if (rafId) { global.cancelAnimationFrame(rafId); rafId = 0; }
      if (ro && ro.disconnect) { try { ro.disconnect(); } catch (e) { /* ignore */ } }
      global.removeEventListener('resize', onWindowResize);
      canvas.removeEventListener('pointerdown', onPointerDown);
      canvas.removeEventListener('pointermove', onPointerMove);
      canvas.removeEventListener('pointerup', onPointerUp);
      canvas.removeEventListener('pointercancel', onPointerUp);
      canvas.removeEventListener('wheel', onWheel);
      canvas.removeEventListener('keydown', onKeyDown);
      canvas.removeEventListener('webglcontextlost', onContextLost);
      canvas.removeEventListener('webglcontextrestored', onContextRestored);
      if (parent && parent.removeEventListener) { parent.removeEventListener('click', onBandClick); }
      if (mq) {
        if (mq.removeEventListener) { mq.removeEventListener('change', onMotionChange); }
        else if (mq.removeListener) { mq.removeListener(onMotionChange); }
      }
      if (!contextLost) { destroyResources(); } else { R = null; }
      try { delete canvas.dataset.maarsReady; } catch (e) { /* ignore */ }
    }

    /* ---------------- wire up ---------------- */

    R = createResources();
    if (!R || !R.ok) {
      logErr('shader setup failed; falling back to the static panel.');
      destroyResources();
      markFallback();
      return noopHandle();
    }

    canvas.setAttribute('role', 'img');
    canvas.setAttribute('aria-label', state.aria);
    canvas.setAttribute('data-maars-band', band.id);
    if (!canvas.hasAttribute('tabindex')) { canvas.setAttribute('tabindex', '0'); }
    /* pan-y, not none: a horizontal drag orbits the scene while a vertical
       swipe still scrolls the page. On a phone the canvas is most of the
       viewport, and touch-action:none there means the page cannot be
       scrolled past it at all. Vertical orbit stays available on the
       arrow keys and with a mouse. */
    canvas.style.touchAction = 'pan-y';
    canvas.style.display = canvas.style.display || 'block';

    canvas.addEventListener('pointerdown', onPointerDown);
    canvas.addEventListener('pointermove', onPointerMove);
    canvas.addEventListener('pointerup', onPointerUp);
    canvas.addEventListener('pointercancel', onPointerUp);
    canvas.addEventListener('wheel', onWheel, { passive: false });
    canvas.addEventListener('keydown', onKeyDown);
    canvas.addEventListener('webglcontextlost', onContextLost, false);
    canvas.addEventListener('webglcontextrestored', onContextRestored, false);
    if (parent && parent.addEventListener) { parent.addEventListener('click', onBandClick); }
    syncControls();
    if (mq) {
      if (mq.addEventListener) { mq.addEventListener('change', onMotionChange); }
      else if (mq.addListener) { mq.addListener(onMotionChange); }
    }

    function onWindowResize() { resize(); requestFrame(); }
    global.addEventListener('resize', onWindowResize);

    var ro = null;
    if (typeof global.ResizeObserver === 'function') {
      ro = new global.ResizeObserver(function () { resize(); requestFrame(); });
      try { ro.observe(canvas); } catch (e) { ro = null; }
    }

    resize();
    if (onState) { applyState(state); } else { requestFrame(); }

    return {
      destroy: destroy,
      setBand: setBand,
      setTime: setTime,
      bands: BANDS.map(function (b) { return { id: b.id, key: b.key, mhz: b.mhz, net: b.net }; }),
      getState: function () {
        return {
          band: state.band.id, freqMhz: state.band.mhz,
          skipKm: state.scan.anyReflect ? state.scan.skipKm : null,
          layer: state.scan.skipLayer || null,
          reflects: state.scan.anyReflect,
          lineOfSightKm: state.losKm,
          dayFactor: state.day, foF2: state.foF2,
          absorptionDbPerHop: state.absDb,
          headline: state.headline, ariaLabel: state.aria,
          ready: ready
        };
      },
      fallback: false
    };
  }

  global.MAARSSkywave = {
    version: VERSION,
    mount: mount,
    bands: BANDS.map(function (b) {
      return { id: b.id, key: b.key, mhz: b.mhz, net: b.net };
    })
  };

}(typeof window !== 'undefined' ? window : this));
