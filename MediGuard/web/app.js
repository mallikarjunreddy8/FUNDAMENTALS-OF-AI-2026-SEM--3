/*
 * MediGuard - the web page (camera, photo, form, result).
 * The thinking is done by MediAgent in agent.js; this file only collects
 * what the phone sees and shows what the agent decides.
 */
(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const state = {
    codes: [],       // [{ format, text }] from the scanner
    today: null,     // only set for demos (fixed date so the demo never changes)
    live: null,      // Html5Qrcode instance while the camera is on
    lastReport: null,
    aiNotes: [],     // problems the AI reader saw on the pack (blurry print, misspellings...)
    photos: [],      // the photos of the last scan (for zooming on the stamp)
    stampBoxes: [],  // where the reader thinks the stamp is, per photo
    zoom: null,      // { img, rect, index } while the zoom screen is open
    readBy: "",      // "Claude vision" or "OCR"
  };

  // ---------------------------------------------------------------- AI reader (Claude vision)
  // On claude.ai the page may ask Claude to read the photo. Elsewhere (PC server, plain browser)
  // this resolves null and the free OCR reader is used instead.
  const aiReaderPromise = (async () => {
    try {
      if (!window.claude || typeof window.claude.use !== "function") return null;
      const sample = await window.claude.use("sample");
      if (!sample) return null;
      const lim = await sample.limits().catch(() => null);
      return lim && lim.images ? sample : null;
    } catch (e) {
      return null;
    }
  })();

  const AI_PROMPT = `You are reading a photo of a medicine strip, blister or box (usually sold in India) for a fake-medicine check.
Copy what is PRINTED exactly as printed: keep spelling mistakes, odd letters and spacing, never correct or complete words, never guess.
Use null for anything you cannot read. Batch numbers and dates are often stamped in small dark ink, sometimes sideways or partly rubbed off:
look carefully; for a single character you cannot make out write "?".
Reply with only this JSON object:
{"brand": string or null (the brand name exactly as printed; null if the pack only gives the generic / chemical name),
 "generic_name": string or null,
 "composition": [{"salt": string, "strength": string}],
 "batch": string or null, "mfg": "MM/YYYY" or null, "exp": "MM/YYYY" or null,
 "manufacturer": string or null (company after "Manufactured by" / "Mfd. by"), "marketed_by": string or null,
 "mrp": string or null, "licence_no": string or null,
 "government_supply": true or false (printed "Government supply", "Not for sale" or similar),
 "has_qr_or_barcode": true or false,
 "text_lines": [every printed line, verbatim, in reading order],
 "print_problems": [short notes on visible problems a pharmacist would worry about: misspelled words (quote them), blurry, smudged or uneven printing, mismatched fonts or colours, signs of tampering or re-sealing; [] if none],
 "photo_quality": "good" or "fair" or "poor"}`;

  // Turn the AI's reading into the same "printed text" the agent reads from OCR
  function aiToText(r) {
    const lines = Array.isArray(r.text_lines) ? r.text_lines.map(String) : [];
    if (r.brand) lines.unshift(String(r.brand));            // brands lead the pack
    (r.composition || []).forEach((c) => c && c.salt && lines.push(`${c.salt} ${c.strength || ""}`));
    if (r.batch) lines.push(`B.No. ${r.batch}`);
    if (r.mfg) lines.push(`Mfg. ${r.mfg}`);
    if (r.exp) lines.push(`Exp. ${r.exp}`);
    if (r.manufacturer) lines.push(`Manufactured by: ${r.manufacturer}`);
    if (r.government_supply) lines.push("Government Supply - Not for Sale");
    return lines.join("\n");
  }

  async function readWithAI(sample, file) {
    setStatus("Claude is reading the photo… (5-30 seconds)", true);
    const r = await sample.json(AI_PROMPT, { images: file });
    if (!r || typeof r !== "object") throw { code: "invalid_json" };
    state.aiNotes = (Array.isArray(r.print_problems) ? r.print_problems : []).map(String).filter(Boolean).slice(0, 4);
    const text = aiToText(r);
    const put = (id, v) => { if (v && !$(id).value) $(id).value = v; };
    put("fBatch", r.batch ? String(r.batch).toUpperCase() : "");
    put("fMfg", toMonthInput(r.mfg));
    put("fExp", toMonthInput(r.exp));
    put("fMaker", r.manufacturer || r.marketed_by || "");
    state.readBy = "Claude vision";
    const unsure = r.batch && String(r.batch).includes("?") ? " Part of the batch no. was unreadable - tap 'Edit details' to fix it." : "";
    setStatus((r.photo_quality === "poor" ? "Read, but the photo is unclear - a sharper photo gives a better check. " :
      "Read by Claude. ") + "Check the details below." + unsure);
    return text;
  }

  const FIELDS = { brand: "fBrand", batch: "fBatch", barcode: "fBarcode", price: "fPrice", mfg: "fMfg", exp: "fExp", manufacturer: "fMaker" };

  // ---------------------------------------------------------------- helpers
  function setStatus(msg, busy) {
    const el = $("status");
    el.textContent = msg || "";
    el.classList.toggle("busy", !!busy);
  }

  function el(tag, attrs, ...children) {
    const node = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (k === "class") node.className = v;
      else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
      else node.setAttribute(k, v);
    }
    for (const c of children.flat()) if (c != null && c !== false) node.append(c.nodeType ? c : String(c));
    return node;
  }

  // "03/2027" -> "2027-03" (for <input type="month">)
  const toMonthInput = (s) => {
    const m = /^(\d{2})\/(\d{4})$/.exec(s || "");
    return m ? `${m[2]}-${m[1]}` : "";
  };

  function formats() {
    const F = window.Html5QrcodeSupportedFormats;
    return F ? [F.QR_CODE, F.DATA_MATRIX, F.EAN_13, F.EAN_8, F.UPC_A, F.CODE_128] : undefined;
  }

  // ---------------------------------------------------------------- codes
  function addCode(format, text) {
    if (!text || state.codes.some((c) => c.text === text)) return false;
    state.codes.push({ format: format || "CODE", text });
    renderCodes();
    if (navigator.vibrate) navigator.vibrate(80);
    return true;
  }

  function renderCodes() {
    const list = $("codeList");
    list.replaceChildren(...state.codes.map((c, i) => el("li", { title: c.text },
      `▦ ${c.format.replace(/_/g, " ")}: ${c.text.replace(/\s+/g, " ").slice(0, 40)}`,
      el("button", { "aria-label": "Remove code", onclick: () => { state.codes.splice(i, 1); renderCodes(); } }, "✕"))));
  }

  // ---------------------------------------------------------------- live camera
  async function startLive() {
    if (!window.Html5Qrcode) return setStatus("The scanner didn't load. Check your connection and reload the page.");
    if (!window.isSecureContext) {
      return setStatus("Live camera needs https:// (or localhost). Use \"Photo of strip / box\" instead - it works everywhere.");
    }
    $("liveBox").hidden = false;
    $("btnLive").disabled = true;
    setStatus("Point the camera at the barcode or QR code…", true);
    try {
      state.live = new Html5Qrcode("reader", { formatsToSupport: formats(), verbose: false,
        experimentalFeatures: { useBarCodeDetectorIfSupported: true } });
      await state.live.start(
        { facingMode: "environment" },
        { fps: 10, qrbox: (w, h) => ({ width: Math.floor(Math.min(w, h * 1.4) * 0.85), height: Math.floor(Math.min(w, h * 1.4) * 0.55) }) },
        (text, result) => {
          const fmt = result && result.result && result.result.format ? result.result.format.formatName : "CODE";
          if (addCode(fmt, text)) {
            setStatus(`Got it (${fmt.replace(/_/g, " ")}). Scan another code, or press Stop.`);
            fillFromScan();
          }
        },
        () => {}
      );
    } catch (err) {
      setStatus("Couldn't open the camera (" + (err.message || err) + "). Use \"Photo of strip / box\" instead.");
      await stopLive();
    }
  }

  async function stopLive() {
    if (state.live) {
      try { if (state.live.isScanning) await state.live.stop(); state.live.clear(); } catch (e) { /* already stopped */ }
      state.live = null;
    }
    $("liveBox").hidden = true;
    $("btnLive").disabled = false;
    if ($("status").classList.contains("busy")) setStatus("");
  }

  // ---------------------------------------------------------------- photos: see ocr.js for the text reader

  // ---------------------------------------------------------------- zoom on the stamp
  // The user frames the batch / dates; only that part is read (several ways, then a vote)
  async function openZoom(index) {
    if (!state.photos.length) {
      showView("home");
      return setStatus("Scan or upload a photo first.");
    }
    index = index || 0;
    showView("zoom");
    $("zoomStatus").textContent = "Opening the photo…";
    const img = await MediOCR.loadImage(state.photos[index]);
    const guess = state.stampBoxes[index];
    const pad = (b) => ({ x: b.x - b.w * 0.15, y: b.y - b.h * 0.15, w: b.w * 1.3, h: b.h * 1.3 });
    state.zoom = { img, index, rect: guess ? pad(guess) : { x: img.width * 0.2, y: img.height * 0.6, w: img.width * 0.6, h: img.height * 0.15 } };
    $("zoomPhotos").replaceChildren(...(state.photos.length > 1 ? state.photos.map((f, i) =>
      el("button", { class: "chip-btn" + (i === index ? " active" : ""), onclick: () => openZoom(i) }, `Photo ${i + 1}`)) : []));
    $("zoomStatus").textContent = guess ? "The box shows where the stamp seems to be - move it if needed." : "Drag a box around the batch no. and dates.";
    drawZoom();
  }

  function drawZoom() {
    const z = state.zoom, c = $("zoomCanvas");
    if (!z) return;
    const cssW = c.parentElement.clientWidth || 360;
    const scale = cssW / z.img.width, dpr = window.devicePixelRatio || 1;
    c.width = Math.round(cssW * dpr);
    c.height = Math.round(z.img.height * scale * dpr);
    const ctx = c.getContext("2d");
    ctx.setTransform(dpr * scale, 0, 0, dpr * scale, 0, 0);
    ctx.drawImage(z.img, 0, 0);
    const r = z.rect;
    ctx.fillStyle = "rgba(0,0,0,0.45)";            // dim everything outside the box
    ctx.fillRect(0, 0, z.img.width, r.y);
    ctx.fillRect(0, r.y + r.h, z.img.width, z.img.height - r.y - r.h);
    ctx.fillRect(0, r.y, r.x, r.h);
    ctx.fillRect(r.x + r.w, r.y, z.img.width - r.x - r.w, r.h);
    ctx.strokeStyle = "#2bb3a3";
    ctx.lineWidth = 3 / scale;
    ctx.strokeRect(r.x, r.y, r.w, r.h);
    z.scale = scale;
  }

  function zoomPointer() {
    const c = $("zoomCanvas");
    let start = null;
    const pos = (e) => {
      const b = c.getBoundingClientRect(), z = state.zoom;
      return { x: Math.max(0, Math.min(z.img.width, (e.clientX - b.left) / z.scale)),
               y: Math.max(0, Math.min(z.img.height, (e.clientY - b.top) / z.scale)) };
    };
    c.addEventListener("pointerdown", (e) => { if (!state.zoom) return; start = pos(e); c.setPointerCapture(e.pointerId); });
    c.addEventListener("pointermove", (e) => {
      if (!start) return;
      const p = pos(e);
      state.zoom.rect = { x: Math.min(start.x, p.x), y: Math.min(start.y, p.y), w: Math.abs(p.x - start.x), h: Math.abs(p.y - start.y) };
      drawZoom();
    });
    c.addEventListener("pointerup", () => { start = null; });
    window.addEventListener("resize", drawZoom);
  }

  async function readZoom() {
    const z = state.zoom;
    if (!z) return;
    if (z.rect.w < 20 || z.rect.h < 10) return ($("zoomStatus").textContent = "Drag a bigger box around the batch no. and dates.");
    $("btnZoomRead").disabled = true;
    const st = $("zoomStatus");
    st.classList.add("busy");
    try {
      const out = await MediOCR.readRegion(z.img, z.rect, (msg, f) => { st.textContent = f ? `${msg}… ${Math.round(f * 100)}%` : msg; });
      const p = MediAgent.readPrintedText(out.text);
      const month = (d) => (d ? `${d.y}-${String(d.m).padStart(2, "0")}` : "");
      if (p.batch) $("fBatch").value = p.batch;
      if (p.mfg) $("fMfg").value = month(p.mfg);
      if (p.exp) $("fExp").value = month(p.exp);
      $("ocrText").value = ($("ocrText").value + "\n" + out.text).trim();
      st.classList.remove("busy");
      if (!p.batch && !p.mfg && !p.exp) {
        st.textContent = "Couldn't read it. Try a tighter box, or type the details (Check tab).";
      } else {
        state.readBy = state.readBy || "on-device reader";
        runCheck();
      }
    } catch (err) {
      st.classList.remove("busy");
      st.textContent = "Couldn't read it (" + (err.message || err) + ").";
    } finally {
      $("btnZoomRead").disabled = false;
    }
  }

  // ---------------------------------------------------------------- screens
  const TITLES = { home: "MediGuard", scan: "Scanning…", manual: "Check manually", result: "Result", find: "Same composition",
    zoom: "Zoom on the stamp" };
  function showView(name) {
    document.querySelectorAll(".view").forEach((v) => { v.hidden = v.id !== "view-" + name; });
    $("viewTitle").textContent = TITLES[name] || "MediGuard";
    $("btnBack").hidden = name === "home";
    document.querySelectorAll(".tab[data-go]").forEach((t) => t.classList.toggle("active", t.dataset.go === name));
    window.scrollTo(0, 0);
    if (name === "find") setTimeout(() => $("search").focus(), 50);
    document.querySelectorAll("#view-manual .btn-zoom").forEach((b) => { b.hidden = !state.photos.length; });
  }

  // One or more photos (e.g. front and back of a strip) are read and their text combined
  async function scanPhotos(fileList) {
    const files = [...(fileList || [])].filter(Boolean).slice(0, 4);
    if (!files.length) return;
    await stopLive();
    resetForm();                 // every scan starts fresh
    $("ocrText").value = "";
    showView("scan");
    state.today = null;
    $("btnCheck").disabled = true;
    const texts = [];
    state.photos = files;
    state.stampBoxes = [];
    const sample = await aiReaderPromise;   // Claude vision: only on claude.ai, never needed

    for (let i = 0; i < files.length; i++) {
      const file = files[i];
      const of = files.length > 1 ? ` (photo ${i + 1} of ${files.length})` : "";
      // 1. a barcode / QR / DataMatrix (many strips have none - that's normal)
      if (window.Html5Qrcode) {
        setStatus("Looking for a barcode or QR code" + of + "…", true);
        try {
          const scanner = new Html5Qrcode("readerFile", { formatsToSupport: formats(), verbose: false });
          const res = await scanner.scanFileV2(file, false);
          addCode(res.result && res.result.format ? res.result.format.formatName : "CODE", res.decodedText);
          scanner.clear();
        } catch (e) { /* no code in this photo */ }
      }
      // 2. the printed text: on-device reader (offline); Claude vision only if this page runs on claude.ai
      let text = "";
      if (sample) {
        try {
          text = await readWithAI(sample, file);
        } catch (e) {
          setStatus("AI reading unavailable - using the on-device reader…", true);
        }
      }
      if (!text && window.MediOCR && window.Tesseract) {
        try {
          const res = await MediOCR.read(file, (msg, f) => setStatus((f ? `${msg}… ${Math.round(f * 100)}%` : msg) + of, true));
          text = res.text;
          state.stampBoxes[i] = res.stampBox;
          state.readBy = state.readBy || "on-device reader";
        } catch (err) {
          setStatus("Couldn't read the text (" + (err.message || err) + ").");
        }
      }
      if (text) texts.push(text);
    }
    $("ocrText").value = texts.join("\n");
    setStatus($("ocrText").value ? "Done. Check the result - tap 'Edit details' to fix anything misread." :
      "Couldn't read any text. Try a sharper photo in good light, or type the details.");
    $("btnCheck").disabled = false;
    fillFromScan();
    if ($("ocrText").value || state.codes.length) runCheck();
  }

  // ---------------------------------------------------------------- form
  // Put what the agent extracted into empty form fields (never overwrite the user's typing)
  function fillFromScan() {
    const r = MediAgent.check({ text: $("ocrText").value, codes: state.codes });
    const put = (id, value) => { if (value && !$(id).value) $(id).value = value; };
    if (r.medicine && r.match !== "lookalike") put("fBrand", r.medicine.brand);
    put("fBatch", r.extracted.batch);
    put("fMfg", toMonthInput(r.extracted.mfg));
    put("fExp", toMonthInput(r.extracted.exp));
    if (r.extracted.manufacturer) put("fMaker", cleanMaker(r.extracted.manufacturer));
    const gtin = r.extracted.codes.find((c) => c.kind === "gtin");
    if (gtin) put("fBarcode", gtin.raw);
  }

  // "Manufactured by: Micro Labs Limited, Bengaluru 0] of ns" -> "Micro Labs Limited, Bengaluru"
  function cleanMaker(line) {
    const s = line.replace(/^.*?\b(by|for)\b\s*:?\s*/i, "").split(/[\[\]|{}=_—~»«]/)[0];
    const m = s.match(/^(.*?\b(?:LTD|LIMITED|INC|LLP)\b\.?(?:,\s*[A-Za-z]+(?:\s[A-Za-z]+)?)?)/i);
    return (m ? m[1] : s).trim();
  }

  function readForm() {
    const manual = {};
    for (const [k, id] of Object.entries(FIELDS)) manual[k] = $(id).value.trim();
    // the barcode was already scanned - don't count it twice
    if (state.codes.some((c) => c.text === manual.barcode)) manual.barcode = "";
    const checklist = {};
    document.querySelectorAll("#checklist input").forEach((cb) => { checklist[cb.value] = cb.checked; });
    return { text: $("ocrText").value, codes: state.codes, manual, checklist, today: state.today || undefined,
             aiNotes: state.aiNotes };
  }

  function resetForm() {
    for (const id of Object.values(FIELDS)) $(id).value = "";
    document.querySelectorAll("#checklist input").forEach((cb) => { cb.checked = false; });
    state.codes = [];
    state.aiNotes = [];
    state.readBy = "";
    renderCodes();
  }

  // ---------------------------------------------------------------- result
  const ICONS = { danger: "⛔", warn: "⚠️", info: "ℹ️", pass: "✅" };
  const METER = { danger: "var(--danger)", warn: "var(--warn)", ok: "var(--ok)", info: "var(--info)" };

  // With server.py running, the check uses the full 253,973-medicine dataset; otherwise the built-in list.
  async function serverCheck(obs) {
    if (!location.protocol.startsWith("http")) return null;
    try {
      const ctrl = new AbortController();
      const timer = setTimeout(() => ctrl.abort(), 4000);
      const res = await fetch("api/check", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(obs), signal: ctrl.signal });
      clearTimeout(timer);
      return res.ok ? await res.json() : null;
    } catch (e) {
      return null;
    }
  }

  async function runCheck() {
    const obs = readForm();
    const report = (await serverCheck(obs)) || Object.assign(MediAgent.check(obs),
      { source: `Offline check (built-in list of ${MediAgent.brands().length} medicines)` });
    state.lastReport = report;
    // what the camera read, so the user can compare it with the strip
    const readItems = [["Name", $("fBrand").value || (report.medicine ? report.medicine.brand : "")],
      ["Batch no.", $("fBatch").value], ["Mfg.", $("fMfg").value], ["Exp.", $("fExp").value]];
    $("readBox").hidden = !state.readBy;
    $("readList").replaceChildren(...readItems.flatMap(([k, val]) => [el("dt", {}, k),
      el("dd", { class: val ? "" : "missing" }, val ? (/^\d{4}-\d{2}$/.test(val) ? val.slice(5) + "/" + val.slice(0, 4) : val) : "not read")]));
    $("source").textContent = (report.source || "") + (state.readBy ? ` · photo read by ${state.readBy}` : "");
    const v = report.verdict;

    $("verdict").className = "verdict tone-" + v.tone;
    $("verdict").replaceChildren(el("strong", {}, v.label), el("p", {}, v.say));
    $("meterFill").style.width = Math.max(4, v.risk) + "%";
    $("meterFill").style.background = METER[v.tone];
    $("riskText").textContent = `Risk score ${v.risk}/100 · ${v.passes} check(s) passed`;

    const m = report.medicine;
    $("medInfo").hidden = !m;
    if (m) {
      $("medInfo").replaceChildren(
        el("b", {}, report.match === "lookalike" ? `Pretends to be: ${m.brand}` : m.brand),
        el("div", {}, `Composition: ${m.composition}`),
        el("div", {}, [m.form, m.use, m.pack, m.price ? `MRP ₹${m.price}` : "", `by ${m.company}`,
          m.rx ? "prescription only" : "", m.discontinued ? "discontinued" : ""].filter(Boolean).join(" · ")));
    }

    $("evidence").replaceChildren(...report.evidence.map((e) => el("li", { class: "lv-" + e.level },
      el("span", { class: "ico", "aria-hidden": "true" }, ICONS[e.level]),
      el("div", {}, el("b", {}, e.title), e.detail ? el("small", {}, e.detail) : null))));

    $("altBox").hidden = !report.alternatives.length;
    $("alternatives").replaceChildren(...report.alternatives.map(altItem));

    $("actions").replaceChildren(...report.actions.map((a) => el("li", {}, a)));

    showView("result");
    $("result").focus({ preventScroll: true });
  }

  function altItem(a) {
    return el("li", {},
      el("b", {}, a.brand),
      a.generic ? el("span", { class: "tag generic" }, "Generic · low cost") : null,
      a.original ? el("span", { class: "tag original" }, "Genuine pack from a licensed shop") : null,
      a.rx ? el("span", { class: "tag rx" }, "Rx") : null,
      a.saving > 0 ? el("span", { class: "tag generic" }, `${a.saving}% cheaper per tablet`) : null,
      el("small", {}, [a.composition, a.company, a.price ? `₹${a.price} (${a.pack})` : ""].filter(Boolean).join(" · ")));
  }

  function speak() {
    const r = state.lastReport;
    if (!r || !("speechSynthesis" in window)) return;
    const flags = r.evidence.filter((e) => e.level === "danger" || e.level === "warn").slice(0, 3).map((e) => e.title);
    const alt = r.alternatives.length ? `Other options with the same composition: ${r.alternatives.slice(0, 3).map((a) => a.brand).join(", ")}.` : "";
    const msg = new SpeechSynthesisUtterance(`${r.verdict.label}. ${r.verdict.say} ${flags.length ? "Reasons: " + flags.join(". ") + "." : ""} ${alt}`);
    msg.lang = "en-IN";
    speechSynthesis.cancel();
    speechSynthesis.speak(msg);
  }

  // ---------------------------------------------------------------- search
  // One card per composition: every brand with the same salts + strength, generic first
  function runSearch() {
    const q = $("search").value.trim();
    const groups = new Map();
    for (const r of MediAgent.search(q)) {
      if (!groups.has(r.composition)) groups.set(r.composition, { match: r, items: new Map() });
      const g = groups.get(r.composition);
      for (const a of [r, ...r.alternatives]) if (!g.items.has(a.brand)) g.items.set(a.brand, a);
    }
    if (q.length < 2) return $("searchResults").replaceChildren();
    if (!groups.size) {
      return $("searchResults").replaceChildren(el("p", { class: "hint" },
        `"${q}" is not in MediGuard's list yet. Try the salt name (for example paracetamol), or ask your pharmacist.`));
    }
    $("searchResults").replaceChildren(...[...groups.values()].slice(0, 5).map(({ match, items }) => {
      const list = [...items.values()].sort((a, b) => (b.generic ? 1 : 0) - (a.generic ? 1 : 0));
      return el("div", { class: "card find-card" },
        el("b", {}, match.generic ? match.composition : match.brand),
        el("div", { class: "comp" }, match.composition),
        el("small", {}, `${list.length} option${list.length > 1 ? "s" : ""} with the same composition:`),
        el("ul", { class: "alts" }, list.map(altItem)));
    }));
  }

  // ---------------------------------------------------------------- demos
  function loadDemo(key) {
    const s = window.MEDI_SAMPLES[key];
    resetForm();
    state.today = s.today;
    state.codes = s.codes.map((c) => ({ ...c }));
    renderCodes();
    $("ocrText").value = s.text;
    $("ocrBox").open = true;
    document.querySelectorAll("#checklist input").forEach((cb) => { cb.checked = !!s.checklist[cb.value]; });
    fillFromScan();
    setStatus(`Sample pack: ${s.title} (sample date ${s.today}).`);
    state.readBy = "";
    runCheck();
  }

  // ---------------------------------------------------------------- start
  function init() {
    $("brandList").replaceChildren(...MediAgent.brands().map((b) => el("option", { value: b })));
    $("checklist").replaceChildren(...MediAgent.checklist().map((c) =>
      el("label", {}, el("input", { type: "checkbox", value: c.id }), el("span", {}, c.label))));

    document.querySelectorAll("[data-go]").forEach((b) => b.addEventListener("click", () => showView(b.dataset.go)));
    $("btnBack").addEventListener("click", () => showView("home"));
    document.querySelectorAll(".btn-zoom").forEach((b) => b.addEventListener("click", () => openZoom(0)));
    $("btnZoomRead").addEventListener("click", readZoom);
    zoomPointer();
    $("quickPicks").replaceChildren(...["Dolo 650", "Pan 40", "Azee 500", "Telma 40", "Paracetamol", "Calcium"].map((n) =>
      el("button", { class: "chip-btn", onclick: () => { $("search").value = n; runSearch(); } }, n)));
    // live barcode scanning needs a camera page of its own (https / localhost, not inside claude.ai)
    $("btnLive").hidden = !(window.isSecureContext && !window.claude);
    $("btnLive").addEventListener("click", startLive);
    $("btnStop").addEventListener("click", stopLive);
    $("photo").addEventListener("change", (e) => { scanPhotos(e.target.files); e.target.value = ""; });
    $("photoUpload").addEventListener("change", (e) => { scanPhotos(e.target.files); e.target.value = ""; });
    $("btnCheck").addEventListener("click", runCheck);
    $("btnSpeak").addEventListener("click", speak);
    $("search").addEventListener("input", runSearch);
    document.querySelectorAll("[data-demo]").forEach((b) => b.addEventListener("click", () => loadDemo(b.dataset.demo)));
    // typing anything yourself means it's no longer a demo
    document.querySelectorAll("main input, main textarea").forEach((i) => i.addEventListener("input", () => {
      if (i.id !== "search") state.today = null;
    }));

    if ("serviceWorker" in navigator && location.protocol.startsWith("http") && !window.MEDIGUARD_APP) {
      navigator.serviceWorker.register("sw.js").catch(() => {});
    }
  }

  init();
  showView("home");
})();
