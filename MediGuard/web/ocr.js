/*
 * MediGuard - reading the text on a medicine strip (works offline, in the browser / Android app).
 *
 * Foil strips are hard for OCR: glare, embossed patterns, red print on silver, text in several
 * directions, and batch / dates STAMPED in small blue, violet or black ink. So we:
 *
 *   1. clean the photo   - enlarge it, keep the darkest colour channel (red, green and blue ink all
 *                          turn dark) and divide by the blurred background to remove glare
 *   2. find the direction - Tesseract's orientation detector (OSD): upright, sideways or upside down
 *   3. read the print     - on the cleaned image and on a black-and-white version, then merge
 *   4. read the stamp     - keep only blue / violet / black stamp ink, try every direction,
 *                           until the batch no. and expiry are found
 *
 * MediOCR.read(fileOrBlob, onProgress) -> { text, angle, passes }
 */
(function (root) {
  "use strict";

  const MAX_SIDE = 2400;          // big enough for the small print on a strip
  const STAMP_LINE = /\b(B\.?\s?NO|BATCH|LOT|E[XK]?P|EXPIRY|MFG|MFD|MFO|USE\s+BEFORE|M\.?R\.?P)\b|\d{1,2}\s*[\/.\-]\s*(\d{4}|\d{2})\b|\b(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)[A-Z]*[.\s\-\/]*\d{2,4}\b/i;

  // ------------------------------------------------------------------ image helpers
  function loadImage(file) {
    if (root.createImageBitmap) {
      return createImageBitmap(file, { imageOrientation: "from-image" }).catch(() => loadViaImg(file));
    }
    return loadViaImg(file);
  }
  function loadViaImg(file) {
    const url = URL.createObjectURL(file);
    return new Promise((resolve, reject) => {
      const i = new Image();
      i.onload = () => { URL.revokeObjectURL(url); resolve(i); };
      i.onerror = () => { URL.revokeObjectURL(url); reject(new Error("Couldn't open that image")); };
      i.src = url;
    });
  }

  function canvasOf(w, h) {
    const c = document.createElement("canvas");
    c.width = w; c.height = h;
    return c;
  }

  function scaled(img, maxSide) {
    const s = Math.min(maxSide / Math.max(img.width, img.height), 3);
    const c = canvasOf(Math.round(img.width * s), Math.round(img.height * s));
    const ctx = c.getContext("2d", { willReadFrequently: true });
    ctx.imageSmoothingQuality = "high";
    ctx.drawImage(img, 0, 0, c.width, c.height);
    return c;
  }

  // Box blur with an integral image: background brightness around each pixel
  function boxBlur(src, w, h, r) {
    const I = new Float64Array((w + 1) * (h + 1));
    for (let y = 0; y < h; y++) {
      let row = 0;
      for (let x = 0; x < w; x++) {
        row += src[y * w + x];
        I[(y + 1) * (w + 1) + x + 1] = I[y * (w + 1) + x + 1] + row;
      }
    }
    const out = new Float32Array(w * h);
    for (let y = 0; y < h; y++) {
      const y0 = Math.max(0, y - r), y1 = Math.min(h, y + r + 1);
      for (let x = 0; x < w; x++) {
        const x0 = Math.max(0, x - r), x1 = Math.min(w, x + r + 1);
        const sum = I[y1 * (w + 1) + x1] - I[y0 * (w + 1) + x1] - I[y1 * (w + 1) + x0] + I[y0 * (w + 1) + x0];
        out[y * w + x] = sum / ((y1 - y0) * (x1 - x0));
      }
    }
    return out;
  }

  /*
   * Prepare three versions of the photo (all grey, ink dark on white):
   *   flat   - glare removed, any colour of ink dark
   *   binary - black and white (local threshold) of `flat`
   *   stamp  - only blue / violet / black stamp ink
   */
  function prepare(img) {
    const base = scaled(img, MAX_SIDE);
    const w = base.width, h = base.height;
    const px = base.getContext("2d", { willReadFrequently: true }).getImageData(0, 0, w, h).data;
    const minc = new Float32Array(w * h), lum = new Float32Array(w * h), blueness = new Float32Array(w * h);
    for (let i = 0, j = 0; j < w * h; i += 4, j++) {
      const r = px[i], g = px[i + 1], b = px[i + 2];
      minc[j] = Math.min(r, g, b);
      lum[j] = (r + g + b) / 3;
      blueness[j] = b - Math.max(r, g * 0.9);
    }
    const R = Math.max(12, Math.round(Math.max(w, h) / 50));
    const bg = boxBlur(boxBlur(minc, w, h, R), w, h, R);
    const flatV = new Uint8ClampedArray(w * h);
    for (let j = 0; j < w * h; j++) flatV[j] = Math.min(255, (minc[j] / (bg[j] + 1)) * 225);
    const local = boxBlur(flatV, w, h, Math.max(8, Math.round(R / 3)));
    const lumBg = boxBlur(lum, w, h, R);

    // where is the bluish stamp ink? (grid of cells, then the biggest connected blocks)
    const blueInk = new Uint8Array(w * h);
    for (let j = 0; j < w * h; j++) blueInk[j] = blueness[j] > 18 && lum[j] < lumBg[j] * 0.9 ? 1 : 0;
    const boxes = stampBoxes(blueInk, w, h);

    const mk = () => { const c = canvasOf(w, h); return [c, c.getContext("2d", { willReadFrequently: true }).createImageData(w, h)]; };
    const [flat, fd] = mk(), [binary, bd] = mk(), [stamp, sd] = mk();
    for (let j = 0, i = 0; j < w * h; j++, i += 4) {
      const f = flatV[j];
      const bin = f < local[j] - 16 ? 0 : 255;
      // stamp ink: clearly bluer than red/green, or very dark and colourless, and darker than around it
      const st = (blueness[j] > 14 && lum[j] < lumBg[j] * 0.86) || (lum[j] < lumBg[j] * 0.45 && lum[j] < 90) ? 0 : 255;
      fd.data[i] = fd.data[i + 1] = fd.data[i + 2] = f; fd.data[i + 3] = 255;
      bd.data[i] = bd.data[i + 1] = bd.data[i + 2] = bin; bd.data[i + 3] = 255;
      sd.data[i] = sd.data[i + 1] = sd.data[i + 2] = st; sd.data[i + 3] = 255;
    }
    flat.getContext("2d").putImageData(fd, 0, 0);
    binary.getContext("2d").putImageData(bd, 0, 0);
    stamp.getContext("2d").putImageData(sd, 0, 0);
    return { flat, binary, stamp, boxes, w, h };
  }

  // Group stamp-ink pixels into cells, join neighbouring busy cells, return the biggest blocks
  function stampBoxes(ink, w, h) {
    const C = Math.max(8, Math.round(Math.max(w, h) / 120));
    const gw = Math.ceil(w / C), gh = Math.ceil(h / C);
    const busy = new Uint8Array(gw * gh);
    for (let gy = 0; gy < gh; gy++) {
      for (let gx = 0; gx < gw; gx++) {
        let n = 0;
        for (let y = gy * C; y < Math.min(h, (gy + 1) * C); y++) {
          for (let x = gx * C; x < Math.min(w, (gx + 1) * C); x++) n += ink[y * w + x];
        }
        busy[gy * gw + gx] = n > C * C * 0.06 ? 1 : 0;
      }
    }
    // close small gaps between letters / lines (dilate by 1 cell)
    const grown = new Uint8Array(gw * gh);
    for (let gy = 0; gy < gh; gy++) for (let gx = 0; gx < gw; gx++) {
      if (!busy[gy * gw + gx]) continue;
      for (let dy = -1; dy <= 1; dy++) for (let dx = -1; dx <= 1; dx++) {
        const x = gx + dx, y = gy + dy;
        if (x >= 0 && y >= 0 && x < gw && y < gh) grown[y * gw + x] = 1;
      }
    }
    const seen = new Uint8Array(gw * gh), boxes = [];
    for (let start = 0; start < gw * gh; start++) {
      if (!grown[start] || seen[start]) continue;
      let x0 = 1e9, y0 = 1e9, x1 = -1, y1 = -1, count = 0;
      const stack = [start];
      seen[start] = 1;
      while (stack.length) {
        const k = stack.pop(), x = k % gw, y = (k / gw) | 0;
        count += busy[k];
        x0 = Math.min(x0, x); x1 = Math.max(x1, x); y0 = Math.min(y0, y); y1 = Math.max(y1, y);
        for (const [dx, dy] of [[1, 0], [-1, 0], [0, 1], [0, -1]]) {
          const nx = x + dx, ny = y + dy, nk = ny * gw + nx;
          if (nx >= 0 && ny >= 0 && nx < gw && ny < gh && grown[nk] && !seen[nk]) { seen[nk] = 1; stack.push(nk); }
        }
      }
      if (count >= 6) boxes.push({ x: x0 * C, y: y0 * C, w: (x1 - x0 + 1) * C, h: (y1 - y0 + 1) * C, count });
    }
    return boxes.sort((a, b) => b.count - a.count).slice(0, 2);
  }

  // Black and white with Otsu's threshold (the foil pattern is lighter than the stamp ink)
  function otsu(src) {
    const c = canvasOf(src.width, src.height);
    const ctx = c.getContext("2d", { willReadFrequently: true });
    ctx.drawImage(src, 0, 0);
    const img = ctx.getImageData(0, 0, c.width, c.height), d = img.data;
    const hist = new Float64Array(256);
    for (let i = 0; i < d.length; i += 4) hist[d[i]]++;
    const total = d.length / 4;
    let sum = 0;
    for (let i = 0; i < 256; i++) sum += i * hist[i];
    let wB = 0, sumB = 0, best = 0, t = 128;
    for (let i = 0; i < 256; i++) {
      wB += hist[i]; if (!wB) continue;
      const wF = total - wB; if (!wF) break;
      sumB += i * hist[i];
      const between = wB * wF * (sumB / wB - (sum - sumB) / wF) ** 2;
      if (between > best) { best = between; t = i; }
    }
    for (let i = 0; i < d.length; i += 4) d[i] = d[i + 1] = d[i + 2] = d[i] < t ? 0 : 255;
    ctx.putImageData(img, 0, 0);
    return c;
  }

  // Cut a block out of a canvas (with a margin) and enlarge it so the letters are ~40 px high
  function crop(src, box, targetLong) {
    // generous margin along the line (the first / last letters are often fainter)
    const mx = Math.round(box.w * (box.w >= box.h ? 0.2 : 0.1) + Math.min(box.w, box.h) * 0.15) + 8;
    const my = Math.round(box.h * (box.h > box.w ? 0.2 : 0.1) + Math.min(box.w, box.h) * 0.15) + 8;
    const x = Math.max(0, box.x - mx), y = Math.max(0, box.y - my);
    const w = Math.min(src.width - x, box.w + 2 * mx), h = Math.min(src.height - y, box.h + 2 * my);
    const s = Math.min(3, Math.max(2, targetLong / Math.max(w, h)));   // at least 2x: stamp letters are small
    const c = canvasOf(Math.round(w * s), Math.round(h * s));
    const ctx = c.getContext("2d");
    ctx.imageSmoothingQuality = "high";
    ctx.drawImage(src, x, y, w, h, 0, 0, c.width, c.height);
    return c;
  }

  // Turn a canvas clockwise by 0 / 90 / 180 / 270 degrees
  function rotate(src, deg) {
    deg = ((deg % 360) + 360) % 360;
    if (!deg) return src;
    const turn = deg % 180 !== 0;
    const c = canvasOf(turn ? src.height : src.width, turn ? src.width : src.height);
    const ctx = c.getContext("2d");
    ctx.fillStyle = "#fff";
    ctx.fillRect(0, 0, c.width, c.height);
    ctx.translate(c.width / 2, c.height / 2);
    ctx.rotate((deg * Math.PI) / 180);
    ctx.drawImage(src, -src.width / 2, -src.height / 2);
    return c;
  }

  // ------------------------------------------------------------------ Tesseract workers
  let workers = null;
  async function getWorkers(progress) {
    if (workers) return workers;
    const opts = root.MEDIGUARD_OCR || {};
    const common = { workerPath: "lib/worker.min.js", ...opts };
    const text = await Tesseract.createWorker("eng", 1, {
      ...common,
      logger: (m) => { if (m.status === "recognizing text" && progress.pass) progress(progress.pass, m.progress); },
    });
    let osd = null;
    try {
      osd = await Tesseract.createWorker("osd", 0, { ...common, legacyCore: true, legacyLang: true });
    } catch (e) {
      osd = null;   // no orientation detector: we just try the common directions
    }
    workers = { text, osd };
    return workers;
  }

  async function recognize(w, canvas, psm) {
    await w.setParameters({ tessedit_pageseg_mode: String(psm), user_defined_dpi: "300", preserve_interword_spaces: "1" });
    const { data } = await w.recognize(canvas);
    const good = (data.words || []).filter((x) => x.confidence > 70 && /[A-Za-z]{3,}/.test(x.text)).length;
    return { text: (data.text || "").trim(), good };
  }

  // Which way is the text? -> list of clockwise turns to try, best first
  async function directions(osd, flat) {
    if (!osd) return [0, 90, 270, 180];
    try {
      const { data } = await osd.detect(flat);
      const deg = data && typeof data.orientation_degrees === "number" ? data.orientation_degrees : 0;
      const conf = (data && data.orientation_confidence) || 0;
      // OSD's angle, applied clockwise, makes the text upright (checked on real strips).
      // Strips often mix directions (print sideways, stamp straight), so upright is always read too.
      const turn = conf >= 0.5 ? deg % 360 : 0;
      return [...new Set([turn, 0])];
    } catch (e) {
      return [0];
    }
  }

  function mergeLines(texts) {
    const seen = new Set(), out = [];
    for (const t of texts) {
      for (const line of t.split("\n")) {
        const k = line.trim().toUpperCase().replace(/\s+/g, " ");
        if (k.length < 2 || seen.has(k)) continue;
        seen.add(k);
        out.push(line.trim());
      }
    }
    return out.join("\n");
  }

  /*
   * Read a photo. onProgress(message, fraction) is called as each pass runs.
   */
  async function read(file, onProgress) {
    const say = (msg, f) => onProgress && onProgress(msg, f);
    const progress = (msg, f) => say(msg, f);
    say("Opening the photo…", 0);
    const img = await loadImage(file);
    say("Cleaning the photo (glare, foil)…", 0);
    const v = prepare(img);
    const w = await getWorkers(progress);

    say("Finding which way the text runs…", 0);
    const dirs = await directions(w.osd, v.flat);
    const results = [];
    for (const d of dirs) {
      progress.pass = `Reading the print${d ? " (turned " + d + "°)" : ""}`;
      results.push(await recognize(w.text, rotate(v.flat, d), 3));
    }
    results.sort((a, b) => b.good - a.good);                 // best reading first
    const best = dirs.length > 1 ? (results[0].good > 0 ? results.slice(0, 2) : results) : results;
    const bestDir = dirs[0];
    progress.pass = "Reading the print again (black & white)";
    const bin = await recognize(w.text, rotate(v.binary, bestDir), 11);
    let text = mergeLines([...best.map((r) => r.text), bin.text]);

    // batch / dates are stamped: read the stamp ink in every direction until both are found
    const missing = () => {
      const p = root.MediAgent ? root.MediAgent.readPrintedText(text) : {};
      return !p.batch || !p.exp;
    };
    // 4a. the stamp block(s): cut out, enlarge, read both ways along the long side and with two
    //     layouts; keep the reading from which the most batch / date fields can be parsed
    const fields = (t) => {
      const p = root.MediAgent ? root.MediAgent.readPrintedText(t) : {};
      return (p.batch ? 2 : 0) + (p.exp ? 2 : 0) + (p.mfg ? 1 : 0);
    };
    for (const box of v.boxes) {
      if (!missing()) break;
      const dirsForBox = box.h > box.w * 1.2 ? [270, 90] : [0, 180];
      let best = null;
      for (const d of dirsForBox) {
        const piece = rotate(crop(v.flat, box, 2000), d);
        for (const [img, psm] of [[piece, 6], [otsu(piece), 6], [piece, 11]]) {
          progress.pass = "Reading the stamped batch no. / dates";
          const r = await recognize(w.text, img, psm);
          const lines = r.text.split("\n").filter((l) => STAMP_LINE.test(l)).join("\n");
          const score = fields(lines) * 100 + r.good;
          if (!best || score > best.score) best = { score, lines };
        }
        if (best && best.score >= 400) break;        // batch + expiry found: no need to try more
      }
      if (best && best.lines) text = mergeLines([text, best.lines]);
    }
    // 4b. still missing: stamp ink of the whole photo in every direction
    const stampDirs = [...new Set([bestDir, 0, 90, 270, 180])];
    for (let k = 0; k < stampDirs.length && missing(); k++) {
      progress.pass = `Looking for the stamped batch no. / expiry (${k + 1}/${stampDirs.length})`;
      const r = await recognize(w.text, rotate(v.stamp, stampDirs[k]), 11);
      const lines = r.text.split("\n").filter((l) => STAMP_LINE.test(l));
      if (lines.length) text = mergeLines([text, lines.join("\n")]);
    }
    progress.pass = null;
    return { text, angle: bestDir, passes: dirs.length + 1 };
  }

  root.MediOCR = { read, prepare, rotate, STAMP_LINE };
})(typeof self !== "undefined" ? self : this);
