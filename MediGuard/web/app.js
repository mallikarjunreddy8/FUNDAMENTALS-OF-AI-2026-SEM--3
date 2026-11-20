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
  };

  const FIELDS = { brand: "fBrand", batch: "fBatch", barcode: "fBarcode", mfg: "fMfg", exp: "fExp", manufacturer: "fMaker" };

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

  // ---------------------------------------------------------------- photo: barcode + OCR
  // Shrink big phone photos and boost contrast so the text is easier to read
  async function prepareImage(file) {
    const url = URL.createObjectURL(file);
    try {
      const img = await new Promise((resolve, reject) => {
        const i = new Image();
        i.onload = () => resolve(i);
        i.onerror = () => reject(new Error("Couldn't open that image"));
        i.src = url;
      });
      const scale = Math.min(1, 1800 / Math.max(img.width, img.height));
      const c = document.createElement("canvas");
      c.width = Math.round(img.width * scale);
      c.height = Math.round(img.height * scale);
      const ctx = c.getContext("2d");
      ctx.drawImage(img, 0, 0, c.width, c.height);
      const px = ctx.getImageData(0, 0, c.width, c.height);
      const d = px.data;
      let lo = 255, hi = 0;
      for (let i = 0; i < d.length; i += 4) {
        const g = 0.299 * d[i] + 0.587 * d[i + 1] + 0.114 * d[i + 2];
        d[i] = d[i + 1] = d[i + 2] = g;
        if (g < lo) lo = g;
        if (g > hi) hi = g;
      }
      const span = Math.max(1, hi - lo);
      for (let i = 0; i < d.length; i += 4) d[i] = d[i + 1] = d[i + 2] = ((d[i] - lo) * 255) / span;
      ctx.putImageData(px, 0, 0);
      return c;
    } finally {
      URL.revokeObjectURL(url);
    }
  }

  async function scanPhoto(file) {
    if (!file) return;
    await stopLive();
    state.today = null;
    $("btnCheck").disabled = true;

    // 1. look for a barcode / QR / DataMatrix in the photo
    if (window.Html5Qrcode) {
      setStatus("Looking for a barcode or QR code…", true);
      try {
        const scanner = new Html5Qrcode("readerFile", { formatsToSupport: formats(), verbose: false });
        const res = await scanner.scanFileV2(file, false);
        addCode(res.result && res.result.format ? res.result.format.formatName : "CODE", res.decodedText);
        scanner.clear();
      } catch (e) { /* no code in this photo - that's fine */ }
    }

    // 2. read the printed text (OCR)
    if (!window.Tesseract) {
      setStatus("The text reader didn't load. Type the details in step 2.");
    } else {
      try {
        setStatus("Reading the text on the pack… (first time downloads the reader, ~5 MB)", true);
        const canvas = await prepareImage(file);
        const worker = await Tesseract.createWorker("eng", 1, {
          workerPath: "lib/worker.min.js",
          logger: (m) => {
            if (m.status === "recognizing text") setStatus(`Reading the text… ${Math.round(m.progress * 100)}%`, true);
          },
        });
        const { data } = await worker.recognize(canvas);
        await worker.terminate();
        $("ocrText").value = (data.text || "").trim();
        setStatus($("ocrText").value ? "Done. Check the details below, then press Check." :
          "Couldn't read any text. Try a sharper photo in better light, or type the details.");
      } catch (err) {
        setStatus("Couldn't read the text (" + (err.message || err) + "). You can type the details in step 2.");
      }
    }
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
    return { text: $("ocrText").value, codes: state.codes, manual, checklist, today: state.today || undefined };
  }

  function resetForm() {
    for (const id of Object.values(FIELDS)) $(id).value = "";
    document.querySelectorAll("#checklist input").forEach((cb) => { cb.checked = false; });
    state.codes = [];
    renderCodes();
  }

  // ---------------------------------------------------------------- result
  const ICONS = { danger: "⛔", warn: "⚠️", info: "ℹ️", pass: "✅" };
  const METER = { danger: "var(--danger)", warn: "var(--warn)", ok: "var(--ok)", info: "var(--info)" };

  function runCheck() {
    const report = MediAgent.check(readForm());
    state.lastReport = report;
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
        el("div", {}, `${m.form} · ${m.use} · by ${m.company}${m.rx ? " · prescription only" : ""}`));
    }

    $("evidence").replaceChildren(...report.evidence.map((e) => el("li", { class: "lv-" + e.level },
      el("span", { class: "ico", "aria-hidden": "true" }, ICONS[e.level]),
      el("div", {}, el("b", {}, e.title), e.detail ? el("small", {}, e.detail) : null))));

    $("altBox").hidden = !report.alternatives.length;
    $("alternatives").replaceChildren(...report.alternatives.map(altItem));

    $("actions").replaceChildren(...report.actions.map((a) => el("li", {}, a)));

    $("result").hidden = false;
    $("result").scrollIntoView({ behavior: "smooth", block: "start" });
    $("result").focus({ preventScroll: true });
  }

  function altItem(a) {
    return el("li", {},
      el("b", {}, a.brand),
      a.generic ? el("span", { class: "tag generic" }, "Generic · low cost") : null,
      a.original ? el("span", { class: "tag original" }, "Genuine pack from a licensed shop") : null,
      a.rx ? el("span", { class: "tag rx" }, "Rx") : null,
      el("small", {}, `${a.composition} · ${a.company}`));
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
  function runSearch() {
    const results = MediAgent.search($("search").value).filter((r) => !r.generic).slice(0, 6);
    const q = $("search").value.trim();
    $("searchResults").replaceChildren(...(q.length >= 2 && !results.length
      ? [el("p", { class: "hint" }, "Not in MediGuard's list yet.")]
      : results.map((r) => el("div", { class: "search-item" },
          el("b", {}, r.brand), el("small", {}, `${r.composition} · ${r.company}`),
          el("ul", { class: "alts" }, r.alternatives.map(altItem))))));
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
    setStatus(`Demo loaded: ${s.title} (demo date ${s.today}).`);
    runCheck();
  }

  // ---------------------------------------------------------------- start
  function init() {
    $("brandList").replaceChildren(...MediAgent.brands().map((b) => el("option", { value: b })));
    $("checklist").replaceChildren(...MediAgent.checklist().map((c) =>
      el("label", {}, el("input", { type: "checkbox", value: c.id }), el("span", {}, c.label))));

    $("btnLive").addEventListener("click", startLive);
    $("btnStop").addEventListener("click", stopLive);
    $("photo").addEventListener("change", (e) => { scanPhoto(e.target.files[0]); e.target.value = ""; });
    $("btnCheck").addEventListener("click", runCheck);
    $("btnSpeak").addEventListener("click", speak);
    $("search").addEventListener("input", runSearch);
    document.querySelectorAll("[data-demo]").forEach((b) => b.addEventListener("click", () => loadDemo(b.dataset.demo)));
    // typing anything yourself means it's no longer a demo
    document.querySelectorAll("main input, main textarea").forEach((i) => i.addEventListener("input", () => {
      if (i.id !== "search") state.today = null;
    }));

    if ("serviceWorker" in navigator && location.protocol.startsWith("http")) {
      navigator.serviceWorker.register("sw.js").catch(() => {});
    }
  }

  init();
})();
