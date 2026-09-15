/*!
 * MAARS / KS0MAN -- waterfall.js
 * ---------------------------------------------------------------------------
 * The masthead is a receiver.
 *
 * Every licensed amateur alive today reads one picture without being taught
 * it: the spectrum trace with a waterfall scrolling underneath. It is on the
 * front of an IC-7300, it is what an RTL-SDR dongle draws, and it means the
 * same thing to somebody licensed in 1962 and to somebody licensed last month.
 * So instead of a banner image the head of this site is an instrument, tuned
 * to 147.255 MHz -- the Society's own repeater -- with the identity resting
 * in it.
 *
 * It is SOFT AND SMOOTH by construction, not by decoration:
 *   - the heat map is a continuous ramp, drawn at low resolution and scaled up
 *     with bilinear smoothing, so there is no hard edge anywhere in it;
 *   - the top and bottom edges are masked off to transparent, so the band
 *     dissolves into the page rather than stopping at a line;
 *   - the area behind the identity is masked off too, with the same soft
 *     falloff, so the wordmark sits on calm ground and is legible over the
 *     brightest thing the instrument can draw. That mask is the reason this
 *     module needs no dark scrim rectangle behind the text.
 *
 * WHAT IS HONEST ABOUT IT. This is a DRAWING of a 2 m band, not a receiver.
 * There is no radio, no network and no data: the trace is synthesised from a
 * noise model plus one marked carrier. The block that mounts it says so in
 * words underneath, the canvas is aria-hidden, and the identity over it is
 * real text. Nothing here claims to be live.
 *
 * No libraries. No CDN. No imports. No network access of any kind. One
 * self-contained IIFE that exposes:
 *
 *     window.MAARSWaterfall.mount(canvasEl, opts) -> { destroy() }
 *
 * mirroring skywave.js, which is the other module in this theme.
 *
 * COST. One frame every 80ms (12.5 fps), and a frame is: 384x72 pixels written
 * into an ImageData, one scaled drawImage, one path of 256 points, one scaled
 * mask composite. That is a few hundred thousand pixel writes a second on a
 * strip 180px tall -- it is meant to run on a 2013 laptop in a church
 * basement without the fan coming on. Under prefers-reduced-motion it draws
 * exactly ONE frame and never schedules another, and it stops entirely while
 * the tab is hidden.
 * ---------------------------------------------------------------------------
 */
(function (global) {
  'use strict';

  if (!global || typeof global.document === 'undefined') { return; }

  var VERSION = '1.0.0';

  /* The Society's repeater, and the slice of 2 m either side of it. These are
     the numbers the block prints in real text underneath the canvas; they are
     here so the picture and the sentence cannot drift apart. */
  var DEFAULT_CENTRE = 147.255;
  var DEFAULT_START = 147.0;
  var DEFAULT_END = 147.5;

  /* Resolution of the model, not of the canvas. 384 bins across 500 kHz is
     1.3 kHz per bin, so a carrier 6 kHz wide occupies about five bins --
     which is roughly what an FM repeater looks like on a rig set to this
     span. 72 rows of history at 80ms a row is just under six seconds of
     scrollback. Both are scaled UP to the canvas with smoothing, and that
     upscale is what makes the heat map continuous. 256 bins was tried first
     and read as a smear at 1440px: one bin was six pixels wide before the
     upscale, and the band lost the fine vertical structure that says
     "waterfall" rather than "blue gradient". */
  var BINS = 384;
  var ROWS = 72;
  var FRAME_MS = 80;

  /* Proportions. A real rig puts the trace on top and the waterfall beneath;
     these are the two numbers that say how much of the strip each one gets. */
  var SPECTRUM_FRACTION = 0.40;

  /* Edge softening, in CSS pixels. The bottom fade is the deeper of the two
     because it is doing two jobs at once: dissolving the bottom edge of the
     band, and ageing out the oldest rows of the waterfall so the frequency
     scale has somewhere quiet to sit. */
  var FADE_TOP = 14;
  var FADE_BOTTOM = 26;

  /* How far the trace's wash runs past the split and into the top of the
     waterfall, in CSS pixels, so the two regions meet in a fade rather than
     at a line. */
  var JOIN_SOFT = 22;

  /* How far the clearing behind the identity feathers out, in CSS pixels. Big
     enough that the eye reads it as depth rather than as a hole. */
  var CLEAR_FEATHER = 64;
  var CLEAR_PAD = 14;

  /* The mask is computed per pixel, so it is computed small and scaled up.
     160x64 over a 1440x180 strip is one mask pixel per 9x3 CSS pixels, and
     the bilinear upscale smooths what is left. */
  var MASK_W = 160;
  var MASK_H = 64;

  /* ---------------------------------------------------------------------
   * Palette. This has to read as MAARS, not as a generic SDR, so there is no
   * rainbow in it. The noise ramp walks the club's own navy from a deep
   * ground up through navy and navy-soft into the pale haze the rest of the
   * site uses for quiet fills; magenta is reserved for the archive everywhere
   * else on this site, and here it is reserved for the one thing that is
   * genuinely a signal -- the club's carrier.
   *
   * Written as [position, r, g, b] and expanded into a 256-entry lookup table
   * once at mount, so a frame never evaluates a gradient.
   * ------------------------------------------------------------------- */
  /*
   * THE RAMPS ARE CAPPED, AND THE CAP IS A CONTRAST FLOOR, NOT A TASTE CALL.
   * The identity is white text resting in this band. Revision 3's first cut ran
   * both ramps up to near-white (#e8eaf6 and #f6e0ef), so wherever a bright peak
   * landed under the wordmark the page reproduced the exact white-on-white
   * failure this whole rebuild exists to fix: measured 1.13:1 where large text
   * needs 3.0. Capping the tops also makes the band softer, which is what it
   * wanted to be anyway -- a near-white hot spot was never "soft".
   * Computed against white: #6169c8 = 4.81:1, #c34796 = 4.50:1. Both clear AA
   * for normal text, so the identity is safe over ANY pixel the band can draw.
   * Do not raise these without recomputing.
   */
  var RAMP_NOISE = [
    [0.00, 0x05, 0x05, 0x1c],
    [0.16, 0x0a, 0x0a, 0x38],
    [0.34, 0x10, 0x10, 0x74],
    [0.52, 0x1b, 0x1b, 0xa4],
    [0.70, 0x2b, 0x2b, 0x84],
    [0.86, 0x31, 0x36, 0x8e],
    [1.00, 0x36, 0x3c, 0x94]
  ];
  /*
   * WHY THE NOISE CAP IS DARKER THAN THE CARRIER CAP, in numbers.
   * The first capping put both ramps at nearly the same brightness -- noise
   * topped at luma 113.4 and the carrier at 117.1, a ratio of 1.03. The
   * carrier was a different HUE but not a brighter signal, so the one thing
   * this band exists to show could not be picked out of its own noise floor.
   * The floor now tops at luma 68.2 against the carrier's 117.1: a ratio of
   * 1.72. White text still clears on both (9.41:1 and 4.50:1), and a real
   * waterfall has a dark floor anyway.
   */

  var RAMP_CARRIER = [
    [0.00, 0x05, 0x05, 0x1c],
    [0.28, 0x3a, 0x0a, 0x46],
    [0.52, 0x7a, 0x0f, 0x62],
    [0.74, 0x99, 0x00, 0x66],
    [1.00, 0xc3, 0x47, 0x96]
  ];

  var CSS = {
    trace: 'rgba(151, 158, 214, 0.95)',   /* capped with the ramps, same reason */
    traceCarrier: 'rgba(195, 71, 150, 0.98)',  /* the carrier reads magenta */
    /* The wash under the trace. Denser at the baseline and thinning upward,
       so the area under the curve reads as accumulated energy and joins the
       waterfall beneath it instead of floating over a hole. */
    fillTop: 'rgba(126, 133, 210, 0.16)',
    fillBottom: 'rgba(37, 37, 148, 0.62)',
    fillFade: 'rgba(37, 37, 148, 0)',
    marker: 'rgba(212, 95, 168, 0.55)',
    bloom: 'rgba(153, 0, 102, 0.50)',
    tick: 'rgba(185, 192, 232, 0.72)',
    tickLine: 'rgba(185, 192, 232, 0.46)',
    tickCarrier: 'rgba(240, 159, 208, 0.96)'
  };

  var TICK_FONT = '"Fira Code", ui-monospace, SFMono-Regular, Menlo, Consolas, monospace';

  /* =====================================================================
   * 1. Small maths. No library, so these are hand rolled.
   * =================================================================== */

  function clamp(v, lo, hi) { return v < lo ? lo : (v > hi ? hi : v); }

  /* Cubic smoothstep on 0..1. Every soft edge in this file is one of these;
     a linear ramp shows its start and end as faint bands and that is exactly
     the hard edge the brief is asking us not to draw. */
  function smooth01(t) {
    if (t <= 0) { return 0; }
    if (t >= 1) { return 1; }
    return t * t * (3 - 2 * t);
  }

  function smoothstep(edge0, edge1, x) {
    if (edge1 === edge0) { return x < edge0 ? 0 : 1; }
    return smooth01((x - edge0) / (edge1 - edge0));
  }

  function gauss(x, mu, sigma) {
    var d = (x - mu) / sigma;
    return Math.exp(-0.5 * d * d);
  }

  /* Deterministic PRNG (mulberry32). Deterministic matters twice: a static
     frame drawn under prefers-reduced-motion is the same picture every time,
     and the render test can assert on pixels without chasing a moving target. */
  function rng(seed) {
    var a = seed >>> 0;
    return function () {
      a = (a + 0x6d2b79f5) >>> 0;
      var t = a;
      t = Math.imul(t ^ (t >>> 15), t | 1);
      t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
      return ((t ^ (t >>> 14)) >>> 0) / 0x100000000;  /* 2^32 */
    };
  }

  /* Expand a ramp into a 256 x 3 lookup table. */
  function makeLut(stops) {
    var lut = new Uint8Array(256 * 3);
    var s = 0;
    for (var i = 0; i < 256; i++) {
      var t = i / 255;
      while (s < stops.length - 2 && t > stops[s + 1][0]) { s++; }
      var a = stops[s];
      var b = stops[s + 1];
      var span = b[0] - a[0];
      var k = span <= 0 ? 0 : clamp((t - a[0]) / span, 0, 1);
      k = smooth01(k);
      lut[i * 3] = a[1] + (b[1] - a[1]) * k;
      lut[i * 3 + 1] = a[2] + (b[2] - a[2]) * k;
      lut[i * 3 + 2] = a[3] + (b[3] - a[3]) * k;
    }
    return lut;
  }

  var LUT_NOISE = null;
  var LUT_CARRIER = null;

  function luts() {
    if (!LUT_NOISE) {
      LUT_NOISE = makeLut(RAMP_NOISE);
      LUT_CARRIER = makeLut(RAMP_CARRIER);
    }
  }

  /* =====================================================================
   * 2. The band model.
   *
   * One row of the waterfall is one "sweep": an amplitude per bin, plus how
   * much of that amplitude came from the club's carrier rather than from the
   * noise floor. The second array is what keeps magenta off everything except
   * the repeater.
   * =================================================================== */

  function Model(opts) {
    this.bins = opts.bins;
    this.startMhz = opts.startMhz;
    this.endMhz = opts.endMhz;
    this.centreMhz = opts.centreMhz;
    this.rand = rng(opts.seed);
    this.amp = new Float32Array(this.bins);
    this.car = new Float32Array(this.bins);
    this.tmp = new Float32Array(this.bins);
    this.tmp2 = new Float32Array(this.bins);
    /* Carrier width in MHz. 6 kHz is about what narrow-band FM occupies once
       a receiver has drawn it at this span. */
    this.carrierSigma = 0.006;
    this.span = this.endMhz - this.startMhz;
    this.centreFrac = (this.centreMhz - this.startMhz) / this.span;
  }

  /* Fill amp[] and car[] for the sweep at time t (ms). */
  Model.prototype.sweep = function (t) {
    var n = this.bins;
    var amp = this.amp;
    var car = this.car;
    var rand = this.rand;
    var sigma = this.carrierSigma / this.span;
    var fc = this.centreFrac;

    /* The carrier breathes. Two slow sines rather than one, so the repeat is
       long enough that nobody watching the masthead sees it loop. This is the
       only thing on the page that moves. */
    /* The carrier has to be unmistakable in EVERY frame, not on average. The
       first tuning breathed between 0.695 and 0.905, and on the low swing the
       marked column sat only 1.08x above the noise floor -- a peak a reader
       would have to be told was there. Higher base, shallower breath: the
       repeater is the one thing this band exists to show. */
    var level = 1.25 + 0.045 * Math.sin(t * 0.00055) + 0.020 * Math.sin(t * 0.00130 + 0.6);

    /* Two faint humps of adjacent activity, wandering slowly. Without them the
       noise floor is too even to be believed. */
    var h1 = 0.180 + 0.030 * Math.sin(t * 0.000210);
    var h2 = 0.800 + 0.040 * Math.sin(t * 0.000165 + 1.7);

    for (var i = 0; i < n; i++) {
      var f = i / (n - 1);

      /* The receiver's own passband rolls off at the edges of the span. It is
         also what keeps the two ends of the strip dark, which is what lets the
         band dissolve sideways into the page. */
      var edge = smoothstep(0, 0.07, f) * smoothstep(0, 0.07, 1 - f);

      /* WHERE THE FLOOR SITS, AND WHY IT IS NOT LOWER.
         This is the brightness control on a real rig, and it is the whole
         difference between a waterfall and a dark rectangle. The first draft
         put the floor at 0.17, which lands on #0a0a38 -- three levels off the
         masthead's own background -- and the band rendered as one flat navy
         block with a single pink stripe in it. MEASURED, not guessed: the
         pixels under the trace came back (9,9,55) against a (7,7,42) ground.
         A floor near a quarter of full scale, with swings big enough to reach
         both ends of it, is what puts dark valleys and lit ridges in the same
         picture -- which is what a waterfall actually looks like. */
      var v = 0.245
        + 0.090 * Math.sin(f * 11.0 + t * 0.00048)
        + 0.062 * Math.sin(f * 23.0 - t * 0.00072)
        + 0.046 * Math.sin(f * 37.0 + t * 0.00031);

      v += (rand() - 0.5) * 0.075;
      v += 0.185 * gauss(f, h1, 0.035);
      v += 0.125 * gauss(f, h2, 0.028);

      /* The carrier, plus a wide, weak skirt. The skirt is what gives the
         repeater the soft bloom around it rather than a cut-out stripe. */
      var c = level * (gauss(f, fc, sigma) + 0.20 * gauss(f, fc, sigma * 4.5));

      var a = (v + c) * edge;
      if (a < 0) { a = 0; } else if (a > 1) { a = 1; }

      amp[i] = a;
      car[i] = a > 0.0001 ? clamp((c * edge) / a, 0, 1) : 0;
    }

    /* Two passes of [1 2 1]. A noise floor drawn straight from a random
       generator is a picket fence; smoothing it is what makes it look like a
       receiver rather than like static, and it is also what guarantees there
       is no hard edge between neighbouring bins. */
    this.blur(amp);
    this.blur(amp);
    this.blur(car);
  };

  Model.prototype.blur = function (arr) {
    var n = arr.length;
    var tmp = this.tmp;
    var i;
    for (i = 0; i < n; i++) { tmp[i] = arr[i]; }
    for (i = 0; i < n; i++) {
      var a = tmp[i > 0 ? i - 1 : 0];
      var b = tmp[i];
      var c = tmp[i < n - 1 ? i + 1 : n - 1];
      arr[i] = (a + 2 * b + c) * 0.25;
    }
  };

  /* =====================================================================
   * 3. mount()
   * =================================================================== */

  function noopHandle(extra) {
    var h = {
      destroy: function () {},
      redraw: function () {},
      getState: function () { return null; },
      fallback: true
    };
    if (extra) {
      for (var k in extra) {
        if (Object.prototype.hasOwnProperty.call(extra, k)) { h[k] = extra[k]; }
      }
    }
    return h;
  }

  function logErr(msg) {
    if (global.console && global.console.error) {
      global.console.error('maars/waterfall: ' + msg);
    }
  }

  function readOpts(canvas, opts) {
    var fromAttr = {};
    try {
      fromAttr = JSON.parse(canvas.getAttribute('data-maars-waterfall') || '{}') || {};
    } catch (e) { fromAttr = {}; }

    var merged = {};
    var k;
    for (k in fromAttr) {
      if (Object.prototype.hasOwnProperty.call(fromAttr, k)) { merged[k] = fromAttr[k]; }
    }
    for (k in opts) {
      if (Object.prototype.hasOwnProperty.call(opts, k)) { merged[k] = opts[k]; }
    }
    return merged;
  }

  function mount(canvas, opts) {
    opts = opts || {};

    if (!canvas || typeof canvas.getContext !== 'function') {
      logErr('mount() needs a <canvas> element.');
      return noopHandle();
    }

    var parent = canvas.parentElement || canvas.parentNode || null;

    function markFallback(reason) {
      if (parent && parent.classList) { parent.classList.add('maars-masthead--fallback'); }
      try {
        canvas.dataset.maarsFallback = '1';
        canvas.dataset.maarsFallbackReason = reason || 'unknown';
      } catch (e) { /* detached */ }
    }

    /* No 2D context, or a browser with no canvas at all: add the class and let
       CSS put a soft navy gradient in the strip. Never blank, never an error,
       and the identity over it is real text either way. */
    var ctx = null;
    try {
      ctx = canvas.getContext('2d', { alpha: true, desynchronized: false });
    } catch (e) { ctx = null; }

    if (!ctx || typeof ctx.createImageData !== 'function') {
      markFallback(ctx ? 'no-imagedata' : 'no-2d-context');
      return noopHandle();
    }

    luts();

    var cfg = readOpts(canvas, opts);

    var centreMhz = Number(cfg.centreMhz);
    if (!isFinite(centreMhz)) { centreMhz = DEFAULT_CENTRE; }
    var startMhz = Number(cfg.startMhz);
    if (!isFinite(startMhz)) { startMhz = DEFAULT_START; }
    var endMhz = Number(cfg.endMhz);
    if (!isFinite(endMhz) || endMhz <= startMhz) { endMhz = DEFAULT_END; }

    var bins = Math.round(Number(cfg.bins) || BINS);
    bins = clamp(bins, 64, 1024);
    var rows = Math.round(Number(cfg.rows) || ROWS);
    rows = clamp(rows, 16, 240);
    var frameMs = Math.round(Number(cfg.frameMs) || FRAME_MS);
    frameMs = clamp(frameMs, 40, 500);

    var tickStepMhz = Number(cfg.tickStepMhz);
    if (!isFinite(tickStepMhz) || tickStepMhz <= 0) { tickStepMhz = 0.1; }

    /* The element whose box gets cleared out of the band so the identity has
       calm ground under it. Resolved from the canvas's own container, so the
       block hands over a selector and nothing here needs to know the markup. */
    var clearSel = typeof cfg.clearSelector === 'string' ? cfg.clearSelector : '';
    var clearEl = cfg.clearElement || null;

    function findClearEl() {
      if (clearEl && clearEl.getBoundingClientRect) { return clearEl; }
      if (!clearSel) { return null; }
      var scope = parent && parent.querySelector ? parent : global.document;
      var found = null;
      try { found = scope.querySelector(clearSel); } catch (e) { found = null; }
      if (!found && global.document && global.document.querySelector) {
        try { found = global.document.querySelector(clearSel); } catch (e2) { found = null; }
      }
      return found;
    }

    /* ---------------- lifecycle ---------------- */
    var destroyed = false;
    var ready = false;
    var rafId = 0;
    var timerId = 0;
    var frames = 0;

    var mq = global.matchMedia ? global.matchMedia('(prefers-reduced-motion: reduce)') : null;
    var reduceMotion = !!(mq && mq.matches);

    var model = new Model({
      bins: bins,
      startMhz: startMhz,
      endMhz: endMhz,
      centreMhz: centreMhz,
      seed: Number(cfg.seed) || 0x4d414152
    });

    /* History. Two flat arrays rather than an array of arrays: one allocation,
       no garbage, and the render loop walks them with a stride. */
    var histAmp = new Float32Array(rows * bins);
    var histCar = new Float32Array(rows * bins);
    var head = rows - 1;          /* index of the newest row */
    var clock = 0;                /* model time, ms */

    /* The waterfall is drawn at model resolution into this little canvas and
       scaled up. That upscale IS the smoothing: there is no other blur in the
       file and no hard edge survives it. */
    var wf = global.document.createElement('canvas');
    wf.width = bins;
    wf.height = rows;
    var wfCtx = wf.getContext('2d');
    if (!wfCtx) {
      markFallback('no-2d-context');
      return noopHandle();
    }
    var wfImage = wfCtx.createImageData(bins, rows);

    /* The soft mask: top fade, bottom fade and the clearing behind the
       identity, all in one small alpha image composited with destination-out. */
    var mask = global.document.createElement('canvas');
    mask.width = MASK_W;
    mask.height = MASK_H;
    var maskCtx = mask.getContext('2d');
    var maskImage = maskCtx ? maskCtx.createImageData(MASK_W, MASK_H) : null;

    var dpr = 1;
    var cssW = 0;
    var cssH = 0;

    /* ---------------- history ---------------- */

    function pushRow(t) {
      model.sweep(t);
      head = (head + 1) % rows;
      var base = head * bins;
      for (var i = 0; i < bins; i++) {
        histAmp[base + i] = model.amp[i];
        histCar[base + i] = model.car[i];
      }
    }

    /* Start with a full screen of history rather than an empty box that fills
       in over six seconds. It also means the one frame drawn under
       prefers-reduced-motion is a complete picture. */
    function seed() {
      clock = 0;
      head = rows - 1;
      for (var r = rows - 1; r >= 0; r--) {
        pushRow(clock);
        clock += frameMs;
      }
    }

    /* ---------------- geometry ---------------- */

    function measure() {
      var rect = canvas.getBoundingClientRect ? canvas.getBoundingClientRect() : null;
      var w = rect && rect.width ? rect.width : (canvas.clientWidth || 0);
      var h = rect && rect.height ? rect.height : (canvas.clientHeight || 0);

      /* Never 0x0. A canvas sized zero throws on some drivers and silently
         draws nothing on the rest, and the commonest way to get there is
         mounting while the element is still display:none. */
      /* Whether the element has actually been laid out yet. Mounting before
         layout gives a fallback size, and painting then under reduced motion
         burns the single frame on a picture at the wrong width. */
      haveRealSize = !!(rect && rect.width > 0 && rect.height > 0);
      if (!(w > 0)) { w = canvas.width || 320; }
      if (!(h > 0)) { h = canvas.height || 160; }

      dpr = clamp(global.devicePixelRatio || 1, 1, 2);
      cssW = w;
      cssH = h;

      var bw = Math.max(1, Math.round(w * dpr));
      var bh = Math.max(1, Math.round(h * dpr));

      if (canvas.width !== bw) { canvas.width = bw; }
      if (canvas.height !== bh) { canvas.height = bh; }
    }

    /* The identity's box, in this canvas's CSS pixel space. Null when the two
       do not overlap -- which is the narrow-screen layout, where the identity
       sits under the band instead of in it, and nothing needs clearing. */
    function clearRect() {
      var el = findClearEl();
      if (!el || !el.getBoundingClientRect || !canvas.getBoundingClientRect) { return null; }
      var a = el.getBoundingClientRect();
      var c = canvas.getBoundingClientRect();
      if (!a.width || !a.height || !c.width || !c.height) { return null; }

      var x0 = a.left - c.left - CLEAR_PAD;
      var x1 = a.right - c.left + CLEAR_PAD;
      var y0 = a.top - c.top - CLEAR_PAD;
      var y1 = a.bottom - c.top + CLEAR_PAD;

      /* No vertical overlap at all: the identity is somewhere else on the
         page and the band belongs entirely to the instrument. */
      if (y1 <= 0 || y0 >= c.height) { return null; }

      return { x0: x0, x1: x1, y0: y0, y1: y1 };
    }

    /* How much of the band is cleared at this point, 0..1. The product of two
       smoothsteps is what gives the clearing soft corners without a single
       rounded-rectangle path. */
    function clearAt(rect, x, y) {
      if (!rect) { return 0; }
      var dx = Math.max(0, Math.max(rect.x0 - x, x - rect.x1));
      var dy = Math.max(0, Math.max(rect.y0 - y, y - rect.y1));
      var sx = 1 - smooth01(dx / CLEAR_FEATHER);
      var sy = 1 - smooth01(dy / CLEAR_FEATHER);
      return sx * sy;
    }

    /* ---------------- drawing ---------------- */

    function paintWaterfall() {
      var data = wfImage.data;
      var lutN = LUT_NOISE;
      var lutC = LUT_CARRIER;
      var o = 0;
      for (var r = 0; r < rows; r++) {
        /* Row 0 is the newest and sits directly under the trace; the history
           scrolls DOWNWARD from there, the way every rig draws it. */
        var src = ((head - r) % rows + rows) % rows;
        var base = src * bins;
        for (var i = 0; i < bins; i++) {
          var a = histAmp[base + i];
          var k = a <= 0 ? 0 : (a >= 1 ? 255 : (a * 255) | 0);
          var m = histCar[base + i] * 1.15;
          if (m > 1) { m = 1; }
          var k3 = k * 3;
          var nr = lutN[k3], ng = lutN[k3 + 1], nb = lutN[k3 + 2];
          if (m > 0.002) {
            data[o] = nr + (lutC[k3] - nr) * m;
            data[o + 1] = ng + (lutC[k3 + 1] - ng) * m;
            data[o + 2] = nb + (lutC[k3 + 2] - nb) * m;
          } else {
            data[o] = nr;
            data[o + 1] = ng;
            data[o + 2] = nb;
          }
          data[o + 3] = 255;
          o += 4;
        }
      }
      wfCtx.putImageData(wfImage, 0, 0);
    }

    function paintMask(rect) {
      if (!maskImage) { return; }
      var d = maskImage.data;
      var o = 0;
      for (var my = 0; my < MASK_H; my++) {
        var y = ((my + 0.5) / MASK_H) * cssH;
        var keepY = smoothstep(0, FADE_TOP, y) * smoothstep(0, FADE_BOTTOM, cssH - y);
        for (var mx = 0; mx < MASK_W; mx++) {
          var x = ((mx + 0.5) / MASK_W) * cssW;
          var keep = keepY * (1 - clearAt(rect, x, y));
          d[o] = 0;
          d[o + 1] = 0;
          d[o + 2] = 0;
          d[o + 3] = (1 - keep) * 255;
          o += 4;
        }
      }
      maskCtx.putImageData(maskImage, 0, 0);
    }

    function xOf(mhz) {
      return ((mhz - startMhz) / (endMhz - startMhz)) * cssW;
    }

    function drawSpectrum(specTop, specBottom) {
      var base = head * bins;
      var h = specBottom - specTop;
      var i;

      /* The trace, as a path smoothed through the bin midpoints. A polyline
         over 256 points would be correct and would also be the one hard-edged
         thing in the picture. */
      var pts = new Array(bins);
      for (i = 0; i < bins; i++) {
        var a = histAmp[base + i];
        pts[i] = {
          x: (i / (bins - 1)) * cssW,
          y: specBottom - a * h
        };
      }

      function tracePath() {
        ctx.beginPath();
        ctx.moveTo(pts[0].x, pts[0].y);
        for (var j = 1; j < bins - 1; j++) {
          var mx = (pts[j].x + pts[j + 1].x) * 0.5;
          var my = (pts[j].y + pts[j + 1].y) * 0.5;
          ctx.quadraticCurveTo(pts[j].x, pts[j].y, mx, my);
        }
        ctx.lineTo(pts[bins - 1].x, pts[bins - 1].y);
      }

      /* Fill under the curve. This gradient is the signal, not a wash: it is
         strength shading, exactly like the waterfall's ramp.
         It runs PAST the split and fades out inside the top of the waterfall,
         which is the joint between the two regions. Stopping it dead on the
         split left a straight bright line the full width of the strip -- the
         one hard edge in a picture whose entire brief is that it has none. */
      var join = JOIN_SOFT;
      var g = ctx.createLinearGradient(0, specTop, 0, specBottom + join);
      g.addColorStop(0, CSS.fillTop);
      g.addColorStop(Math.max(0.01, (specBottom - specTop) / (specBottom - specTop + join)), CSS.fillBottom);
      g.addColorStop(1, CSS.fillFade);
      ctx.save();
      tracePath();
      ctx.lineTo(cssW, specBottom + join);
      ctx.lineTo(0, specBottom + join);
      ctx.closePath();
      ctx.fillStyle = g;
      ctx.fill();
      ctx.restore();

      ctx.save();
      ctx.lineJoin = 'round';
      ctx.lineCap = 'round';
      ctx.lineWidth = 1.5;
      ctx.strokeStyle = CSS.trace;
      tracePath();
      ctx.stroke();

      /* And the carrier's own few bins, in magenta, over the top of it. */
      var c0 = Math.max(1, Math.floor(model.centreFrac * (bins - 1)) - 9);
      var c1 = Math.min(bins - 2, Math.ceil(model.centreFrac * (bins - 1)) + 9);
      ctx.beginPath();
      ctx.moveTo(pts[c0].x, pts[c0].y);
      for (i = c0; i < c1; i++) {
        var qx = (pts[i].x + pts[i + 1].x) * 0.5;
        var qy = (pts[i].y + pts[i + 1].y) * 0.5;
        ctx.quadraticCurveTo(pts[i].x, pts[i].y, qx, qy);
      }
      ctx.lineWidth = 2;
      ctx.strokeStyle = CSS.traceCarrier;
      ctx.stroke();
      ctx.restore();
    }

    function drawCarrierMark(specTop, specBottom) {
      var cx = xOf(centreMhz);

      /* A soft bloom either side of the marked frequency. It is a gradient
         that means something: it is where the Society's signal is.

         It is confined to the trace region. Below the split the waterfall
         already carries the carrier in magenta through its own ramp, and
         adding light on top of that washed the column out to white, which
         would have spent the one colour this site reserves for the archive
         on nothing. */
      var w = Math.max(18, cssW * 0.018);
      var g = ctx.createLinearGradient(cx - w, 0, cx + w, 0);
      g.addColorStop(0, 'rgba(153, 0, 102, 0)');
      g.addColorStop(0.5, CSS.bloom);
      g.addColorStop(1, 'rgba(153, 0, 102, 0)');
      ctx.save();
      ctx.globalCompositeOperation = 'lighter';
      ctx.fillStyle = g;
      ctx.fillRect(cx - w, specTop, w * 2, specBottom - specTop);
      ctx.restore();

      /* The marker itself: a hairline through the trace region only. */
      ctx.save();
      ctx.strokeStyle = CSS.marker;
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(Math.round(cx) + 0.5, specTop);
      ctx.lineTo(Math.round(cx) + 0.5, specBottom);
      ctx.stroke();
      ctx.restore();
    }

    function drawScale(rect) {
      var baseline = cssH - 9;
      var tickTop = cssH - 20;
      var fontPx = 12;
      var label;
      var x;

      ctx.save();
      ctx.font = fontPx + 'px ' + TICK_FONT;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'alphabetic';

      var steps = Math.round((endMhz - startMhz) / tickStepMhz);
      for (var s = 0; s <= steps; s++) {
        var mhz = startMhz + s * tickStepMhz;
        x = xOf(mhz);
        if (x < -2 || x > cssW + 2) { continue; }

        /* The ticks fade out under the identity by the same rule that clears
           the band there, so the scale never reads as clutter behind a name. */
        var a = 1 - clearAt(rect, x, baseline - 4);
        if (a <= 0.03) { continue; }

        ctx.globalAlpha = a;
        ctx.strokeStyle = CSS.tickLine;
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(Math.round(x) + 0.5, tickTop);
        ctx.lineTo(Math.round(x) + 0.5, tickTop + 5);
        ctx.stroke();

        /* Skip the two labels the carrier's own label would collide with.
           The ticks stay; only the numbers give way. */
        if (Math.abs(mhz - centreMhz) < tickStepMhz * 0.7) { continue; }

        /* The first and last labels are the two ends of the span and they
           have to be readable, so they turn in rather than falling off the
           edge. Centre them and half of "147.0" is outside the canvas. */
        label = mhz.toFixed(tickStepMhz < 0.1 ? 3 : 1);
        ctx.fillStyle = CSS.tick;
        if (x < 34) {
          ctx.textAlign = 'left';
          ctx.fillText(label, Math.max(4, x - 4), baseline);
        } else if (x > cssW - 34) {
          ctx.textAlign = 'right';
          ctx.fillText(label, Math.min(cssW - 4, x + 4), baseline);
        } else {
          ctx.textAlign = 'center';
          ctx.fillText(label, x, baseline);
        }
      }

      /* 147.255, labelled, in the one colour reserved for the club's own
         carrier. */
      x = xOf(centreMhz);
      ctx.textAlign = 'center';
      if (x > 6 && x < cssW - 6) {
        ctx.globalAlpha = 1 - clearAt(rect, x, baseline - 4);
        if (ctx.globalAlpha > 0.03) {
          ctx.fillStyle = CSS.tickCarrier;
          ctx.beginPath();
          ctx.moveTo(x, tickTop - 1);
          ctx.lineTo(x - 4, tickTop - 7);
          ctx.lineTo(x + 4, tickTop - 7);
          ctx.closePath();
          ctx.fill();
          ctx.fillText(centreMhz.toFixed(3), x, baseline);
        }
      }

      ctx.restore();
    }

    function draw() {
      if (destroyed) { return; }
      if (!(cssW > 0) || !(cssH > 0)) { return; }

      var rect = clearRect();
      var specTop = 8;
      var specBottom = Math.round(cssH * SPECTRUM_FRACTION);

      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, cssW, cssH);

      /* 1. the waterfall, model-sized and scaled up with smoothing on. */
      paintWaterfall();
      ctx.imageSmoothingEnabled = true;
      if ('imageSmoothingQuality' in ctx) { ctx.imageSmoothingQuality = 'high'; }
      ctx.drawImage(wf, 0, 0, bins, rows, 0, specBottom, cssW, cssH - specBottom);

      /* 2. the carrier's bloom, under the trace so the trace stays crisp. */
      drawCarrierMark(specTop, specBottom);

      /* 3. the trace. */
      drawSpectrum(specTop, specBottom);

      /* 4. the soft mask: both edges, and the ground under the identity. */
      paintMask(rect);
      if (maskCtx) {
        ctx.save();
        ctx.globalCompositeOperation = 'destination-out';
        ctx.imageSmoothingEnabled = true;
        ctx.drawImage(mask, 0, 0, MASK_W, MASK_H, 0, 0, cssW, cssH);
        ctx.restore();
      }

      /* 5. the frequency scale, last, so the mask cannot eat it. */
      drawScale(rect);

      frames++;
      if (!ready) {
        ready = true;
        try { canvas.dataset.maarsReady = '1'; } catch (e) { /* detached */ }
      }
    }

    /* Under prefers-reduced-motion the contract is ONE frame, and it has to hold
       no matter who calls redraw() -- mount, the ResizeObserver firing on
       observe, a visibility change. Repainting is allowed only when the canvas
       has actually changed size, because a resized window showing a stale
       picture would be a worse failure than a second paint. */
    var lastPaintW = -1;
    var lastPaintH = -1;
    var haveRealSize = false;

    function redraw() {
      measure();
      /* One frame means one frame: not a pre-layout guess and then the real
         thing. Wait for a real size, then paint once and stop. */
      if (reduceMotion && !haveRealSize) { return; }
      if (reduceMotion && cssW === lastPaintW && cssH === lastPaintH) { return; }
      lastPaintW = cssW;
      lastPaintH = cssH;
      draw();
    }

    /* ---------------- the loop ---------------- */

    function stop() {
      if (rafId) { global.cancelAnimationFrame(rafId); rafId = 0; }
      if (timerId) { global.clearTimeout(timerId); timerId = 0; }
    }

    function tick() {
      timerId = 0;
      rafId = 0;
      if (destroyed || reduceMotion) { return; }
      clock += frameMs;
      pushRow(clock);
      draw();
      schedule();
    }

    /* setTimeout drives the cadence and rAF only aligns the paint with a
       frame. A plain rAF loop gated on elapsed time would wake this page
       sixty times a second to decide to do nothing, which is exactly the
       thing an old laptop cannot afford. */
    function schedule() {
      if (destroyed || reduceMotion) { return; }
      if (timerId || rafId) { return; }
      timerId = global.setTimeout(function () {
        timerId = 0;
        if (destroyed || reduceMotion) { return; }
        if (typeof global.requestAnimationFrame === 'function') {
          rafId = global.requestAnimationFrame(tick);
        } else {
          tick();
        }
      }, frameMs);
    }

    function start() {
      if (destroyed) { return; }
      if (reduceMotion) { stop(); return; }
      if (global.document && global.document.hidden) { return; }
      schedule();
    }

    /* ---------------- events ---------------- */

    function onVisibility() {
      if (destroyed) { return; }
      if (global.document.hidden) {
        stop();
      } else {
        /* Do not fast-forward the history to wall-clock time: six seconds of
           scrollback would arrive in one frame as a visible jump. Pick the
           band up where it was left. */
        redraw();
        start();
      }
    }

    function onMotionChange() {
      if (destroyed) { return; }
      reduceMotion = !!(mq && mq.matches);
      if (reduceMotion) {
        stop();
        redraw();
      } else {
        start();
      }
    }

    function onWindowResize() { redraw(); }

    /* ---------------- destroy ---------------- */

    function destroy() {
      if (destroyed) { return; }
      destroyed = true;
      stop();
      if (ro && ro.disconnect) {
        try { ro.disconnect(); } catch (e) { /* ignore */ }
      }
      ro = null;
      global.removeEventListener('resize', onWindowResize);
      if (global.document.removeEventListener) {
        global.document.removeEventListener('visibilitychange', onVisibility);
      }
      if (mq) {
        if (mq.removeEventListener) { mq.removeEventListener('change', onMotionChange); }
        else if (mq.removeListener) { mq.removeListener(onMotionChange); }
      }
      try {
        delete canvas.dataset.maarsReady;
        delete canvas.dataset.maarsMounted;
      } catch (e) { /* detached */ }
      /* Drop the offscreen buffers explicitly. A 256x72 pair is small, but a
         page that mounts and destroys on every navigation should not leave
         them for the collector to find. */
      wf.width = 1; wf.height = 1;
      mask.width = 1; mask.height = 1;
      wfImage = null;
      maskImage = null;
      histAmp = null;
      histCar = null;
      model = null;
    }

    /* ---------------- wire up ---------------- */

    canvas.setAttribute('aria-hidden', 'true');
    if (!canvas.hasAttribute('role')) { canvas.setAttribute('role', 'presentation'); }
    canvas.style.display = canvas.style.display || 'block';

    seed();
    /* Through redraw(), not straight to draw(): redraw() holds the
       reduced-motion contract, and mounting before layout used to burn the
       single allowed frame on a fallback-sized picture, with the
       ResizeObserver then painting the real one -- two frames for a reader who
       asked for none. */
    redraw();

    global.addEventListener('resize', onWindowResize);
    if (global.document.addEventListener) {
      global.document.addEventListener('visibilitychange', onVisibility);
    }
    if (mq) {
      if (mq.addEventListener) { mq.addEventListener('change', onMotionChange); }
      else if (mq.addListener) { mq.addListener(onMotionChange); }
    }

    var ro = null;
    if (typeof global.ResizeObserver === 'function') {
      ro = new global.ResizeObserver(function () { redraw(); });
      try {
        ro.observe(canvas);
        /* Also watch the identity: it is what the clearing is measured from,
           and it reflows on its own when the wordmark wraps. */
        var watch = findClearEl();
        if (watch) { ro.observe(watch); }
      } catch (e) { ro = null; }
    }

    start();

    return {
      destroy: destroy,
      redraw: redraw,
      getState: function () {
        return {
          centreMhz: centreMhz,
          startMhz: startMhz,
          endMhz: endMhz,
          bins: bins,
          rows: rows,
          frameMs: frameMs,
          reduceMotion: reduceMotion,
          frames: frames,
          width: cssW,
          height: cssH,
          dpr: dpr,
          ready: ready
        };
      },
      fallback: false
    };
  }

  global.MAARSWaterfall = {
    version: VERSION,
    mount: mount,
    centreMhz: DEFAULT_CENTRE,
    startMhz: DEFAULT_START,
    endMhz: DEFAULT_END
  };

}(typeof window !== 'undefined' ? window : this));
