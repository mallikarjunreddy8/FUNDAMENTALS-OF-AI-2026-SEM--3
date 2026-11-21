/*
 * MediGuard - the fake medicine detection agent.
 *
 * It works like a classic AI agent:
 *
 *   1. PERCEIVE  read what the phone saw: barcode / QR / DataMatrix codes,
 *                the text on the strip (OCR) and what the user typed or ticked
 *   2. REASON    run a set of expert rules; each rule gives a piece of
 *                evidence with a weight (how strongly it points to "fake")
 *   3. DECIDE    add the weights into a risk score and pick a verdict
 *   4. ACT       tell the user what to do, how to report it, and suggest
 *                medicines with the same composition
 *
 * The agent can never PROVE a medicine is genuine - only a lab test can.
 * So the best answer it gives is "No red flags found", never "Genuine".
 *
 * Works in the browser (window.MediAgent) and in Node (require('./agent.js')).
 */
(function (root) {
  "use strict";

  const DATA = (typeof module !== "undefined" && module.exports)
    ? require("./data/medicines.js")
    : root.MEDI_DATA;

  // =============================================================================
  // SETTINGS YOU CAN CHANGE
  // =============================================================================
  const HIGH_RISK = 60;        // risk score at or above this -> "Likely fake"
  const SUSPICIOUS = 30;       // risk score at or above this -> "Suspicious"
  const MAX_SHELF_MONTHS = 60; // most tablets have 2 to 5 years of shelf life
  const SOON_MONTHS = 3;       // warn when the medicine expires within this many months

  const MONTHS = { JAN: 1, FEB: 2, MAR: 3, APR: 4, MAY: 5, JUN: 6, JUL: 7, AUG: 8, SEP: 9, SEPT: 9, OCT: 10, NOV: 11, DEC: 12 };
  const SHORTENERS = ["bit.ly", "tinyurl.com", "goo.gl", "t.ly", "is.gd", "cutt.ly", "rb.gy", "shorturl.at", "ow.ly"];

  // =============================================================================
  // SMALL HELPERS
  // =============================================================================

  const upper = (s) => String(s || "").toUpperCase();

  // "DOLO-650 Tablets" -> ["DOLO", "650", "TABLETS"]
  function tokens(text) {
    return upper(text).replace(/[^A-Z0-9]+/g, " ").trim().split(" ").filter(Boolean);
  }

  // OCR often mixes up 0/O, 1/I, 5/S, 8/B. Compare words on their "skeleton".
  const skeleton = (w) => w.replace(/0/g, "O").replace(/1/g, "I").replace(/5/g, "S").replace(/8/g, "B");
  const digits = (w) => w.replace(/O/g, "0").replace(/[IL]/g, "1").replace(/S/g, "5");

  // Edit distance: how many letters must change to turn a into b
  function levenshtein(a, b) {
    const d = Array.from({ length: a.length + 1 }, (_, i) => [i]);
    for (let j = 1; j <= b.length; j++) d[0][j] = j;
    for (let i = 1; i <= a.length; i++) {
      for (let j = 1; j <= b.length; j++) {
        d[i][j] = Math.min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1));
      }
    }
    return d[a.length][b.length];
  }

  // The composition as text, e.g. "AMOXYCILLIN 500MG + CLAVULANIC ACID 125MG"
  function compositionKey(med) {
    return med.salts.map(([s, n, u]) => `${upper(s)} ${n}${upper(u)}`).sort().join(" + ");
  }
  function compositionText(med) {
    return med.salts.map(([s, n, u]) => `${s} ${n} ${u}`).join(" + ");
  }

  // ---------- dates: everything becomes { y, m } ----------
  const DATE_RE = "(?:(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEPT|SEP|OCT|NOV|DEC)[A-Z]*[.\\s\\-\\/']*(\\d{4}|\\d{2})(?!\\d)" +
                  "|(\\d{1,2})[\\/\\-.](\\d{1,2})[\\/\\-.](\\d{4}|\\d{2})(?!\\d)" +
                  "|(\\d{1,2})[\\/\\-.](\\d{4}|\\d{2})(?!\\d)" +
                  "|(\\d{4})-(\\d{2}))";

  function fullYear(y) {
    y = parseInt(y, 10);
    return y < 100 ? 2000 + y : y;
  }

  function dateFromMatch(m) {
    let d = null;
    if (m[1]) d = { y: fullYear(m[2]), m: MONTHS[m[1]] };
    else if (m[3]) d = { y: fullYear(m[5]), m: parseInt(m[4], 10) };
    else if (m[6]) d = { y: fullYear(m[7]), m: parseInt(m[6], 10) };
    else if (m[8]) d = { y: parseInt(m[8], 10), m: parseInt(m[9], 10) };
    return d && d.m >= 1 && d.m <= 12 ? d : null;
  }

  // "MAR 2027", "03/27", "03/2027", "2027-03", "15/03/2027"
  function parseDate(text) {
    if (!text) return null;
    const m = upper(text).trim().match(new RegExp("^" + DATE_RE));
    return m ? dateFromMatch(m) : null;
  }

  // GS1 dates are YYMMDD
  function parseYYMMDD(s) {
    if (!/^\d{6}$/.test(s)) return null;
    const d = { y: 2000 + parseInt(s.slice(0, 2), 10), m: parseInt(s.slice(2, 4), 10) };
    return d.m >= 1 && d.m <= 12 ? d : null;
  }

  const monthIndex = (d) => d.y * 12 + (d.m - 1);
  const showDate = (d) => d ? `${String(d.m).padStart(2, "0")}/${d.y}` : "-";
  const sameDate = (a, b) => a && b && monthIndex(a) === monthIndex(b);
  const cleanBatch = (b) => upper(b).replace(/[^A-Z0-9]/g, "");

  // =============================================================================
  // 1. PERCEIVE - turn raw scans into facts
  // =============================================================================

  // GTIN / EAN-13 / EAN-8 / UPC check digit (GS1 standard, weights 3,1,3,1... from the right)
  function gtinValid(code) {
    if (!/^\d{8}$|^\d{12,14}$/.test(code)) return false;
    const nums = code.split("").map(Number);
    const check = nums.pop();
    const sum = nums.reverse().reduce((acc, n, i) => acc + n * (i % 2 === 0 ? 3 : 1), 0);
    return (10 - (sum % 10)) % 10 === check;
  }

  // GS1 DataMatrix / GS1-128: (01) GTIN, (17) expiry, (11) manufacture date, (10) batch, (21) serial
  function parseGS1(raw) {
    let s = String(raw).replace(/^\](d2|C1|Q3|e0)/, "");
    const out = {};
    if (/^\(\d{2}\)/.test(s)) {
      const re = /\((\d{2})\)([^(]*)/g;
      let m;
      while ((m = re.exec(s))) out[m[1]] = m[2].trim();
    } else {
      const fixed = { "01": 14, "17": 6, "11": 6, "15": 6 };
      let guard = 0;
      while (s.length > 2 && guard++ < 10) {
        const ai = s.slice(0, 2);
        s = s.slice(2);
        if (fixed[ai]) {
          out[ai] = s.slice(0, fixed[ai]);
          s = s.slice(fixed[ai]);
        } else if (ai === "10" || ai === "21") {
          const end = s.indexOf("\u001d");
          out[ai] = end === -1 ? s : s.slice(0, end);
          s = end === -1 ? "" : s.slice(end + 1);
        } else break;
        if (s[0] === "\u001d") s = s.slice(1);
      }
    }
    if (!out["01"]) return null;
    return {
      kind: "gs1",
      gtin: out["01"],
      gtinValid: gtinValid(out["01"]),
      exp: parseYYMMDD(out["17"] || ""),
      mfg: parseYYMMDD(out["11"] || ""),
      batch: out["10"] || null,
      serial: out["21"] || null,
    };
  }

  // India's QR code on medicines (Drugs Rules, Schedule H2) holds: product ID, generic name,
  // brand, manufacturer, batch, mfg date, expiry, licence number. Packs write it as "Key: value".
  function parseKeyValueQR(raw) {
    const out = { kind: "qr-data", fields: 0 };
    const parts = String(raw).split(/[\n\r|;]+/);
    for (const part of parts) {
      const m = part.match(/^\s*([A-Za-z .\/#()]+?)\s*[:=]\s*(.+)$/);
      if (!m) continue;
      const key = m[1].toLowerCase(), value = m[2].trim();
      if (/batch|lot|b\.?\s?no/.test(key)) out.batch = value;
      else if (/exp/.test(key)) out.exp = parseDate(value);
      else if (/mfg|mfd|manufactur\w*\s*date|dom/.test(key) && parseDate(value)) out.mfg = parseDate(value);
      else if (/brand/.test(key)) out.brand = value;
      else if (/manufacturer|mfr|mfd\.?\s*by|company|marketed/.test(key)) out.manufacturer = value;
      else if (/generic|composition|salt/.test(key)) out.generic = value;
      else if (/unique|upi|product\s*(id|code)|gtin/.test(key)) out.uid = value;
      else if (/lic/.test(key)) out.licence = value;
      else continue;
      out.fields++;
    }
    return out.fields >= 2 ? out : null;
  }

  function parseCode(code) {
    const raw = String(code.text || "").trim();
    const format = upper(code.format || "").replace(/\s+/g, "_");
    if (!raw) return null;
    const gs1 = parseGS1(raw);
    if (gs1 && raw.length > 16) return Object.assign({ format, raw }, gs1);
    if (/^\d{8}$|^\d{12,14}$/.test(raw)) {
      return { format, raw, kind: "gtin", gtin: raw, gtinValid: gtinValid(raw) };
    }
    if (/^https?:\/\//i.test(raw)) {
      let domain = "";
      try { domain = new URL(raw).hostname.replace(/^www\./, ""); } catch (e) { domain = raw; }
      return { format, raw, kind: "url", url: raw, domain };
    }
    const kv = parseKeyValueQR(raw);
    if (kv) return Object.assign({ format, raw }, kv);
    return { format, raw, kind: "text" };
  }

  // Pull batch, dates, manufacturer and strengths out of the OCR text
  function readPrintedText(text) {
    const t = upper(text);
    const out = { batch: null, mfg: null, exp: null, manufacturerLine: null, strengths: [] };

    const b = t.match(/(?:\bB\.?\s?NO|\bBATCH\s*(?:NO|NUMBER)?|\bLOT\s*(?:NO)?)\s*\.?\s*[:.#]?\s*([A-Z0-9][A-Z0-9\-\/]{2,14})/);
    if (b) out.batch = b[1];

    const mfg = t.match(new RegExp("(?:MFG|MFD|MANUFACTURED\\s+ON|MANUFACTURING\\s+DATE|DOM)\\.?\\s*(?:DATE|DT)?\\.?\\s*[:.\\-]?\\s*" + DATE_RE));
    if (mfg) out.mfg = dateFromMatch(mfg);

    const exp = t.match(new RegExp("(?:EXP(?:IRY)?|\\bE[KP]P?(?=[.:\\s])|USE\\s+BEFORE|BEST\\s+BEFORE)\\.?\\s*(?:DATE|DT)?\\.?\\s*[:.\\-]?\\s*" + DATE_RE));
    if (exp) out.exp = dateFromMatch(exp);
    // No "Exp" label read (smudged or sideways stamp)? The expiry is the latest date printed on a pack.
    if (!out.exp) {
      const all = [...t.matchAll(new RegExp(DATE_RE, "g"))].map(dateFromMatch)
        .filter((d) => d && d.y >= 2000 && d.y <= 2045 && (!out.mfg || monthIndex(d) > monthIndex(out.mfg)));
      if (all.length) {
        out.exp = all.reduce((a, b) => (monthIndex(b) > monthIndex(a) ? b : a));
        out.expGuessed = true;
      }
    }

    const maker = String(text || "").split(/\n/).find((line) => /(MANUFACTURED|MFD\.?|MFG\.?|MARKETED|MKTD\.?)\s*(BY|FOR)/i.test(line));
    if (maker) out.manufacturerLine = maker.trim();

    const re = /(\d+(?:\.\d+)?)\s*(MG|MCG|µG|IU|I\.U\.)(?![A-Z])/g;
    let m;
    while ((m = re.exec(t))) {
      const unit = m[2] === "µG" ? "MCG" : m[2].replace(/\./g, "");
      out.strengths.push({ value: parseFloat(m[1]), unit });
    }
    return out;
  }

  /*
   * perceive(observation) -> facts
   *   observation.text      OCR text from the photo of the strip / box
   *   observation.codes     [{ format, text }] from the barcode scanner
   *   observation.manual    { brand, batch, mfg, exp, manufacturer, barcode } typed by the user
   *   observation.checklist { sealBroken: true, ... } what the user ticked
   *   observation.today     a Date (default: now)
   */
  function perceive(obs) {
    obs = obs || {};
    const manual = obs.manual || {};
    const text = String(obs.text || "");
    const codes = (obs.codes || []).map(parseCode).filter(Boolean);
    if (manual.barcode && String(manual.barcode).trim()) {
      const typed = parseCode({ format: "TYPED", text: String(manual.barcode).replace(/\s+/g, "") });
      if (typed) codes.push(typed);
    }

    const printed = readPrintedText(text);
    // What the user typed beats what OCR read (they can correct OCR mistakes)
    if (manual.batch) printed.batch = upper(manual.batch).trim();
    if (manual.mfg) printed.mfg = parseDate(manual.mfg) || printed.mfg;
    if (manual.exp) printed.exp = parseDate(manual.exp) || printed.exp;
    if (manual.manufacturer) printed.manufacturerLine = manual.manufacturer;

    const now = obs.today ? new Date(obs.today) : new Date();
    return {
      text,
      brandText: manual.brand ? String(manual.brand) : "",
      price: parseFloat(manual.price) || 0,
      codes,
      printed,
      checklist: obs.checklist || {},
      aiNotes: Array.isArray(obs.aiNotes) ? obs.aiNotes.slice(0, 4) : [],
      today: { y: now.getFullYear(), m: now.getMonth() + 1 },
    };
  }

  // =============================================================================
  // 2. REASON - which medicine is this, and what looks wrong?
  // =============================================================================

  // Find the brand in a piece of text. Returns { med, kind, seen }
  //   kind = "exact"     name + strength (+ extra word) found
  //          "partial"   name found but strength / extra word missing
  //          "lookalike" a name 1-2 letters away from a real brand (classic fake trick)
  function identify(text) {
    const toks = tokens(text);
    if (!toks.length) return null;
    const meds = DATA.MEDICINES.filter((m) => m.match);
    const knownNames = new Set(meds.map((m) => m.match.name));
    const saltWords = new RegExp("^(" + Object.values(DATA.SALTS).join("|") + ")");
    let best = null;

    function consider(med, kind, score, i, distance) {
      const words = 1 + (med.match.number ? 1 : 0) + (med.match.extra ? 1 : 0);
      if (!best || score > best.score) best = { med, kind, score, seen: toks.slice(i, i + words).join(" "), distance };
    }

    toks.forEach((tok, i) => {
      const near = toks.slice(i + 1, i + 4);
      const hasNumber = (n) => near.some((w) => w === n || digits(w) === n);
      const hasExtra = (x) => near.some((w) => w === x || skeleton(w) === x);
      const sk = skeleton(tok);

      for (const med of meds) {
        const { name, number, extra } = med.match;
        const needs = (number ? 1 : 0) + (extra ? 1 : 0);
        const got = (number && hasNumber(number) ? 1 : 0) + (extra && hasExtra(extra) ? 1 : 0);

        if (sk === name) {
          consider(med, got === needs ? "exact" : "partial", got === needs ? 3 + got : 1 + got * 0.5, i, 0);
        } else if (name.length >= 5 && !knownNames.has(sk) && !saltWords.test(sk)) {
          const dist = levenshtein(sk, name);
          const allowed = name.length >= 8 ? 2 : 1;
          // a lookalike must also carry the right strength / extra word (or the brand has none)
          if (dist > 0 && dist <= allowed && (needs === 0 || got > 0)) {
            consider(med, "lookalike", 2 - dist * 0.1 + got * 0.2, i, dist);
          }
        }
      }
    });
    return best;
  }

  // Unbranded packs ("Calcium And Vitamin D3 Tablets IP") name the salts, not a brand:
  // find the medicine whose salts are ALL printed (most salts wins, generic version preferred)
  function identifyByComposition(text) {
    const t = upper(text);
    let best = null;
    for (const med of DATA.MEDICINES) {
      if (!med.salts.every(([s]) => new RegExp(DATA.SALTS[s] || upper(s)).test(t))) continue;
      const score = med.salts.length * 2 + (med.generic ? 1 : 0);
      if (!best || score > best.score) best = { med, kind: "composition", score, seen: compositionText(med) };
    }
    return best;
  }

  function findMedicineByName(name) {
    const n = upper(name).trim();
    return DATA.MEDICINES.find((m) => upper(m.brand) === n) || null;
  }

  // When the pack looks fake, the real brand from a licensed shop is also a safe choice
  function alternativesWithOriginal(med, verdict) {
    const list = alternativesFor(med);
    if ((verdict.key === "fake" || verdict.key === "suspicious") && !med.generic) {
      list.unshift({ brand: med.brand, company: med.company, generic: false, composition: compositionText(med),
        form: med.form, rx: med.rx, original: true });
    }
    return list;
  }

  function alternativesFor(med) {
    const key = compositionKey(med);
    return DATA.MEDICINES
      .filter((m) => m !== med && compositionKey(m) === key)
      .sort((a, b) => (b.generic ? 1 : 0) - (a.generic ? 1 : 0))
      .map((m) => ({
        brand: m.brand,
        company: m.company,
        generic: !!m.generic,
        composition: compositionText(m),
        form: m.form,
        rx: m.rx,
      }));
  }

  // Each piece of evidence: { level, weight, title, detail }
  //   level: "danger" (strong red flag), "warn" (doubt), "info" (note), "pass" (check passed)
  function reason(facts) {
    const ev = [];
    const add = (level, weight, title, detail) => ev.push({ level, weight, title, detail });
    const { printed, codes, today } = facts;

    // ---------- Rule 1: which medicine is it? ----------
    let id = null;
    if (facts.brandText) {
      const direct = findMedicineByName(facts.brandText);
      id = direct ? { med: direct, kind: "exact", seen: facts.brandText } : identify(facts.brandText);
    }
    if (!id || id.kind !== "exact") {
      const fromText = identify(facts.text);
      if (fromText && (!id || fromText.score > (id.score || 0))) id = fromText;
    }
    const qrBrand = codes.find((c) => c.brand);
    if ((!id || id.kind === "partial") && qrBrand) {
      const fromQR = findMedicineByName(qrBrand.brand) || (identify(qrBrand.brand) || {}).med;
      if (fromQR) id = { med: fromQR, kind: "exact", seen: qrBrand.brand };
    }
    if (!id && facts.text.length > 40) id = identifyByComposition(facts.text);
    const med = id ? id.med : null;

    if (!id) {
      add("info", 0, "Medicine not recognised",
        "This brand isn't in MediGuard's list yet, so only the general checks below were done. Pick the brand from the list if it's there.");
    } else if (id.kind === "lookalike") {
      add("danger", 35, `Name looks like a copy of "${med.brand}"`,
        `The pack reads "${id.seen}", which is ${id.distance} letter(s) away from the real brand "${med.brand}". ` +
        "Fakers often change one letter. Check the spelling on the pack with your own eyes (the camera can misread too).");
    } else if (id.kind === "composition") {
      add("pass", 0, "Recognised by composition",
        `No brand name, but the pack lists ${compositionText(med)}. Same as: ` +
        alternativesFor(med).filter((a) => !a.generic).map((a) => a.brand).join(", ") + ".");
    } else if (id.kind === "partial") {
      add("info", 5, `Probably ${med.brand}`,
        "The brand name was found but not its strength / full name. Please pick the exact brand from the list to be sure.");
    } else {
      add("pass", 0, `Recognised: ${med.brand}`, `${compositionText(med)} - marketed by ${med.company}.`);
    }

    // ---------- Rule 2: does the strength / composition on the pack match the brand? ----------
    if (med && id.kind !== "lookalike" && facts.text.length > 40) {
      // "equivalent to elemental calcium 500 mg" is an explanation, not a different strength
      const elemental = [...upper(facts.text).matchAll(/ELEMENT\w*\s+\w+\s+(\d+(?:\.\d+)?)\s*MG/g)].map((m) => parseFloat(m[1]));
      const found = printed.strengths.filter((s) => !(s.unit === "MG" && elemental.includes(s.value)));
      const missing = med.salts.filter(([, n, u]) => !found.some((s) => s.value === n && s.unit === upper(u)));
      // a strength is "wrong" only if the pack shows one that belongs to none of the salts
      const odd = found.filter((s) => !med.salts.some(([, n, u]) => s.value === n && s.unit === upper(u)));
      if (missing.length && !odd.length) {
        if (found.length) add("pass", 0, "Strength matches (partly readable)", compositionText(med));
      } else if (found.length && missing.length) {
        add("danger", 30, "Strength doesn't match the brand",
          `${med.brand} should contain ${compositionText(med)}, but the pack shows ` +
          found.map((s) => `${s.value} ${s.unit.toLowerCase()}`).join(", ") + ".");
      } else if (found.length) {
        add("pass", 0, "Strength matches the brand", compositionText(med));
      }
      const t = upper(facts.text);
      const noSalt = med.salts.filter(([s]) => !new RegExp(DATA.SALTS[s] || upper(s)).test(t));
      if (noSalt.length && t.length > 80) {
        add("warn", 10, "Salt name not found on the pack",
          `Couldn't find ${noSalt.map((s) => s[0]).join(", ")} in the text. Every genuine pack prints its composition. (May be an OCR miss - check by eye.)`);
      }
    }

    // ---------- Rule 3: manufacturer ----------
    if (med && !med.generic && facts.text.length + (printed.manufacturerLine || "").length > 40) {
      const t = upper(facts.text + " " + (printed.manufacturerLine || ""));
      const others = [...new Set(DATA.MEDICINES.flatMap((m) => m.companyKeys))]
        .filter((k) => !med.companyKeys.includes(k) && new RegExp("\\b" + k + "\\b").test(t));
      if (med.companyKeys.some((k) => t.includes(k))) {
        add("pass", 0, "Manufacturer matches", `${med.company} is printed on the pack.`);
      } else if (printed.manufacturerLine || others.length) {
        add("danger", 30, "Different manufacturer",
          `${med.brand} is made for ${med.company}, but the pack says "${printed.manufacturerLine || others.join(", ")}". ` +
          "Some brands are made by contract factories, but the marketing company is always printed too.");
      } else {
        add("info", 0, "Manufacturer not found", `Couldn't read the company name. It should be ${med.company}.`);
      }
    }

    // ---------- Rule 4: reported batches (CDSCO drug alerts) ----------
    const batches = [printed.batch].concat(codes.map((c) => c.batch)).filter(Boolean);
    const alert = DATA.BATCH_ALERTS.find((a) => batches.some((b) => cleanBatch(b) === cleanBatch(a.batch)));
    if (alert) {
      add("danger", 70, `Batch ${alert.batch} is on the drug alert list`,
        `${alert.brand} batch ${alert.batch}: ${alert.status}. Source: ${alert.source}.`);
    } else if (batches.length) {
      add("pass", 0, "Batch not on the alert list", `Batch ${batches[0]} isn't on MediGuard's alert list.`);
    } else {
      add("warn", 10, "No batch number found",
        "Every genuine medicine prints a batch number (B.No.). Type it in if the camera missed it.");
    }
    if (printed.batch && printed.batch.includes("?")) {
      add("info", 0, "Part of the batch no. is unreadable", `Read as "${printed.batch}". Type the full number from the strip.`);
    }
    if (printed.batch && !/^[A-Z0-9][A-Z0-9\-\/]{2,14}$/.test(cleanBatch(printed.batch))) {
      add("warn", 10, "Unusual batch number", `"${printed.batch}" doesn't look like a normal batch number.`);
    }

    // ---------- Rule 5: dates ----------
    const { mfg, exp } = printed;
    const now = monthIndex(today);
    if (exp) {
      const left = monthIndex(exp) - now;
      if (left < 0) add("danger", 50, "EXPIRED", `It expired in ${showDate(exp)}. Do not take it.`);
      else if (left < SOON_MONTHS) add("info", 0, "Expires soon", `Expiry ${showDate(exp)} - use before then.`);
      else add("pass", 0, "Not expired", `Expiry ${showDate(exp)}.` +
        (printed.expGuessed ? " (The latest date stamped on the pack - check it is the Exp. date.)" : ""));
    } else {
      add("warn", 10, "No expiry date found", "Every genuine medicine prints an expiry date. Type it in if the camera missed it.");
    }
    if (mfg && monthIndex(mfg) > now) {
      add("danger", 40, "Manufacturing date is in the future", `Mfg ${showDate(mfg)} hasn't happened yet - a clear sign of a fake label.`);
    }
    if (mfg && exp) {
      const shelf = monthIndex(exp) - monthIndex(mfg);
      if (shelf <= 0) add("danger", 40, "Expiry is before manufacture", `Mfg ${showDate(mfg)}, Exp ${showDate(exp)} - impossible on a real pack.`);
      else if (shelf > MAX_SHELF_MONTHS) add("warn", 20, "Shelf life is unusually long",
        `${Math.round(shelf / 12 * 10) / 10} years between Mfg and Exp. Most tablets have 2 to 5 years.`);
    }

    // ---------- Rule 6: barcodes and QR codes ----------
    for (const c of codes) {
      if (c.kind === "gs1" || c.kind === "gtin") {
        if (!c.gtinValid) {
          add("danger", 40, "Barcode number is invalid",
            `${c.gtin} fails the GS1 check digit test. Real barcodes always pass it; fakes often print made-up numbers.`);
        } else {
          add("pass", 0, "Barcode number is valid", `${c.gtin}${/^0?890/.test(c.gtin) ? " (GS1 India)" : ""} passes the GS1 check digit test.`);
        }
      }
      // the code and the printed text must tell the same story
      if (c.batch && printed.batch && cleanBatch(c.batch) !== cleanBatch(printed.batch)) {
        add("danger", 45, "QR / barcode batch doesn't match the print",
          `Code says ${c.batch}, pack says ${printed.batch}. Fakers often copy a QR code from a real pack.`);
      } else if (c.batch && printed.batch) {
        add("pass", 0, "Code batch matches the print", `Both say ${printed.batch}.`);
      }
      if (c.exp && exp && !sameDate(c.exp, exp)) {
        add("danger", 35, "QR / barcode expiry doesn't match the print", `Code says ${showDate(c.exp)}, pack says ${showDate(exp)}.`);
      }
      if (c.brand && med && id.kind !== "lookalike") {
        const qrMed = findMedicineByName(c.brand) || (identify(c.brand) || {}).med;
        if (qrMed && qrMed !== med && compositionKey(qrMed) !== compositionKey(med)) {
          add("danger", 40, "QR code is for a different medicine", `QR says "${c.brand}", the pack is ${med.brand}.`);
        }
      }
      if (c.kind === "qr-data") {
        add(c.fields >= 4 ? "pass" : "info", 0, "QR code has product details",
          `${c.fields} details found (batch, dates, brand, maker...). India requires this QR on top-selling brands.`);
      }
      if (c.kind === "url") {
        if (SHORTENERS.includes(c.domain)) {
          add("warn", 25, "QR uses a short link", `It opens ${c.domain}. Real makers link to their own website, not a URL shortener.`);
        } else {
          add("info", 0, "QR opens a website", `${c.domain} - make sure this is the manufacturer's official site before trusting it.`);
        }
      }
    }
    if (!codes.length) {
      add("info", 0, "No barcode / QR scanned",
        med && !med.generic ? "Popular brands in India carry a QR code - scan it for extra checks." : "Scan one if the pack has it.");
    }

    // ---------- Rule 6b: government free-supply medicine ----------
    const govt = upper(facts.text).match(/(\w+)\s+GOVERNMENT\s+SUPPLY|GOVT\.?\s+SUPPLY|GOVERNMENT\s+SUPPLY|NOT\s+FOR\s+SALE|FREE\s+SUPPLY|NOT\s+TO\s+BE\s+SOLD/);
    if (govt) {
      const paid = facts.price > 0;
      add(paid ? "warn" : "info", paid ? 25 : 0, "Government supply - not for sale",
        "This strip is marked for free distribution by a government hospital / health centre. " +
        (paid ? "You paid for it, so a shop may have sold diverted government stock - report it to the Drug Controller."
              : "If you bought it in a shop, that is illegal diversion - report it. If a government hospital gave it to you free, that is normal."));
    }

    // ---------- Rule 7: prescription warning ----------
    if (med && med.rx && facts.text.length > 120 && !/\bRX\b|SCHEDULE\s*H|PRESCRIPTION|REGISTERED MEDICAL PRACTITIONER/.test(upper(facts.text))) {
      add("info", 5, "Prescription warning not found",
        "Prescription medicines must print the 'Rx' / Schedule H warning. It may just be on another side of the box.");
    }

    // ---------- Rule 7b: what the AI reader saw on the pack (max 2 notes count) ----------
    facts.aiNotes.forEach((note, i) => add("warn", i < 2 ? 10 : 0, "AI noticed: " + note,
      "Check this by eye - compare with a pack you know is genuine."));

    // ---------- Rule 8: what the user saw ----------
    for (const item of DATA.CHECKLIST) {
      if (facts.checklist[item.id]) add("warn", item.weight, "You noticed: " + item.label, "");
    }

    return { identity: id, medicine: med, evidence: ev };
  }

  // =============================================================================
  // 3. DECIDE + 4. ACT
  // =============================================================================
  const VERDICTS = {
    fake:       { label: "HIGH RISK - likely fake", tone: "danger", say: "Do not take this medicine." },
    expired:    { label: "EXPIRED - do not use",    tone: "danger", say: "This medicine is expired. Do not take it." },
    suspicious: { label: "SUSPICIOUS - verify",     tone: "warn",   say: "Some things don't look right. Check with the pharmacist before taking it." },
    ok:         { label: "No red flags found",      tone: "ok",     say: "No warning signs were found. Keep the bill and buy from licensed pharmacies." },
    details:    { label: "Almost done - add the missing details", tone: "info",
                  say: "No warning signs so far. Tap 'Edit details', type the batch no. / expiry printed on the strip and check again." },
    unknown:    { label: "Not enough information",  tone: "info",   say: "Scan the barcode / QR and take a clear photo of the printed side, or type the details." },
  };

  function decide(facts, reasoning) {
    const ev = reasoning.evidence;
    const risk = Math.min(100, ev.reduce((s, e) => s + e.weight, 0));
    const passes = ev.filter((e) => e.level === "pass").length;
    const expired = ev.some((e) => e.title === "EXPIRED");
    const otherDanger = ev.filter((e) => e.level === "danger" && e.title !== "EXPIRED").reduce((s, e) => s + e.weight, 0);

    let key;
    if (otherDanger >= HIGH_RISK || (risk >= HIGH_RISK && !expired)) key = "fake";
    else if (expired) key = "expired";
    else if (risk >= SUSPICIOUS || ev.some((e) => e.weight >= 20)) key = "suspicious";  // one strong warning is enough
    else if (reasoning.medicine && passes >= 2 && !ev.some((e) => /^No (batch|expiry)|^Part of the batch/.test(e.title))) key = "ok";
    else if (reasoning.medicine && risk < SUSPICIOUS) key = "details";   // looks fine so far, but batch / expiry unread
    else if (risk > 0 && reasoning.medicine) key = "suspicious";
    else key = "unknown";
    return Object.assign({ key, risk, passes }, VERDICTS[key]);
  }

  function actionsFor(verdict) {
    const report = [
      "Report it: Pharmacovigilance Programme of India helpline 1800-180-3024 (toll free) or the ADR PvPI app.",
      "Complain to your State Drug Controller or CDSCO (cdsco.gov.in). Give the batch number, shop name and bill.",
    ];
    if (verdict.key === "fake") return [
      "Do NOT take it. Keep the strip, the box and the bill - they are evidence.",
      "Show it to the pharmacist / doctor and buy a fresh pack from a different licensed pharmacy.",
      ...report,
    ];
    if (verdict.key === "expired") return [
      "Do NOT take it. Return it to the shop or dispose of it safely.",
      "Buy a fresh pack and always check the expiry date before paying.",
    ];
    if (verdict.key === "suspicious") return [
      "Don't take it until a pharmacist has checked the pack.",
      "Compare it with a pack you know is genuine (colour, font, logo, foil).",
      "If the pharmacist also doubts it, report it:",
      ...report,
    ];
    if (verdict.key === "details") return [
      "Find the B.No. (batch number) and Exp. date stamped on the strip - often in small dark ink, sometimes sideways.",
      "Tap 'Edit details', type them and press Check this medicine.",
    ];
    if (verdict.key === "ok") return [
      "No warning signs found. This app can't do a lab test, so stay alert to how the medicine looks and works.",
      "Keep the bill. Buy only from licensed pharmacies.",
    ];
    return [
      "Scan the barcode / QR code on the box.",
      "Take a sharp photo of the side with batch no., Mfg and Exp dates, in good light.",
      "Or type the brand, batch and expiry by hand.",
    ];
  }

  /*
   * check(observation) -> full report. This is the one function the app calls.
   */
  function check(obs) {
    const facts = perceive(obs);
    const reasoning = reason(facts);
    const verdict = decide(facts, reasoning);
    const med = reasoning.medicine;
    const order = { danger: 0, warn: 1, info: 2, pass: 3 };
    return {
      verdict,
      medicine: med ? {
        brand: med.brand, company: med.company, composition: compositionText(med),
        form: med.form, rx: med.rx, use: med.use, generic: !!med.generic,
      } : null,
      match: reasoning.identity ? reasoning.identity.kind : null,
      evidence: reasoning.evidence.slice().sort((a, b) => order[a.level] - order[b.level] || b.weight - a.weight),
      extracted: {
        batch: facts.printed.batch,
        mfg: facts.printed.mfg ? showDate(facts.printed.mfg) : null,
        exp: facts.printed.exp ? showDate(facts.printed.exp) : null,
        manufacturer: facts.printed.manufacturerLine,
        codes: facts.codes.map((c) => ({ kind: c.kind, format: c.format, raw: c.raw })),
      },
      alternatives: med ? alternativesWithOriginal(med, verdict) : [],
      actions: actionsFor(verdict),
    };
  }

  // Search the database by brand or salt (for the "find alternatives" box)
  function search(query) {
    const q = upper(query).trim();
    if (q.length < 2) return [];
    return DATA.MEDICINES
      .filter((m) => upper(m.brand).includes(q) || m.salts.some(([s]) => upper(s).includes(q)))
      .map((m) => ({ brand: m.brand, composition: compositionText(m), company: m.company, generic: !!m.generic, alternatives: alternativesFor(m) }));
  }

  const MediAgent = {
    check, perceive, reason, decide, identify, search, alternativesFor,
    parseCode, parseGS1, gtinValid, parseDate, readPrintedText, levenshtein,
    brands: () => DATA.MEDICINES.map((m) => m.brand),
    checklist: () => DATA.CHECKLIST,
  };

  if (typeof module !== "undefined" && module.exports) module.exports = MediAgent;
  else root.MediAgent = MediAgent;
})(typeof self !== "undefined" ? self : this);
