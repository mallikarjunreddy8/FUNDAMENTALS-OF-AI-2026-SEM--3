# 💊 MediGuard – Fake Medicine Detection Agent

Fake and substandard medicines harm patients, and they are hard to spot. **MediGuard** is a phone app
(it runs in the browser, so there's nothing to install) that:

1. **Scans** the medicine with the phone camera: barcode, QR code, GS1 DataMatrix, plus a photo of the strip
   that is read with OCR (batch no., Mfg/Exp dates, maker, strength).
2. **Reasons** like an expert pharmacist with 8 rule groups and gives a **risk score** and a verdict:
   *No red flags found*, *Suspicious*, *HIGH RISK – likely fake*, *Expired*, or *Not enough information*.
3. **Explains** every red flag in plain words, and can **read the result aloud** for people who find reading hard.
4. **Suggests alternatives with the same composition** (same salts and strength), with the low-cost
   **generic (Jan Aushadhi)** option first, and tells the user **how to report** the fake.

Everything runs on the phone. Photos are never uploaded.

## Run it

| Where | How |
|---|---|
| **On your PC** | Double-click `run.bat`, then open http://localhost:8000 |
| **Any terminal** | `cd MediGuard` then `python -m http.server 8000`, open http://localhost:8000 |
| **On your phone (best)** | Publish with GitHub Pages (Settings → Pages → branch, root). Open `https://<user>.github.io/<repo>/MediGuard/` on the phone and choose *Add to Home screen*. |

- The **live camera** needs `https://` or `localhost` (a browser rule). On a plain `http://` address,
  the **📷 Photo of strip / box** button still works – it opens the phone's camera app.
- Reading text from photos downloads the OCR model (~5 MB) the first time, so it needs internet once.
  Barcode / QR scanning and the agent itself work offline.
- No strip at hand? Press a **demo** button: ✅ Genuine, ❌ Fake, ⚠️ Copied QR, ⌛ Expired.

Tests: `node test/agent.test.js` (17 tests).

## How the agent thinks

```
 PERCEIVE                     REASON (rules → evidence + weight)          DECIDE            ACT
 ─────────                    ─────────────────────────────────           ──────            ───
 barcode / QR / DataMatrix ─┐  1 Which medicine? (fuzzy brand match)      risk = Σ weights  verdict + reasons
 OCR text of the strip     ─┼─ 2 Strength & salts match the brand?   ───► ≥ 60  likely fake ► what to do / report
 typed details             ─┤  3 Manufacturer matches?                    ≥ 30  suspicious   same-composition
 "what do you notice" ticks ┘  4 Batch on the drug-alert list?            else  no red flags   alternatives
                               5 Dates: expired / Mfg in future / too long shelf life           read aloud
                               6 Barcode check digit; QR vs print agree?
                               7 Prescription (Rx) warning printed?
                               8 What the user noticed (seal, print, price, seller…)
```

| Red flag the agent looks for | Why it matters | Weight |
|---|---|---|
| Batch on the CDSCO drug-alert list | Officially reported spurious / not-of-standard-quality batch | 70 |
| EXPIRED | Unsafe, whether fake or not | 50 |
| QR / barcode batch ≠ printed batch | Fakers copy a QR from one real pack onto thousands | 45 |
| Barcode fails the GS1 check digit | Real barcodes always pass; made-up numbers usually don't | 40 |
| Mfg date in the future / Exp before Mfg | Impossible on a real label | 40 |
| Brand name 1–2 letters off (*Crosin* vs *Crocin*) | Classic lookalike trick. OCR mix-ups like 0/O are ignored | 35 |
| Strength doesn't match the brand | e.g. "Dolo 650" printed with 500 mg | 30 |
| Different manufacturer | Brand belongs to another company | 30 |
| User ticks (broken seal, blurry print, too cheap, no bill…) | What a careful buyer notices | 15–25 |

The agent **never says "Genuine"**: only a lab test can prove that. Its best answer is *"No red flags found"*.

**Alternatives** are found by composition: every medicine's salts + strengths become a key such as
`AMOXYCILLIN 500MG + CLAVULANIC ACID 125MG`, and all brands with the same key are listed. When a pack
looks fake, the genuine brand from a licensed shop is also offered.

## Files

| File | What it is |
|---|---|
| `agent.js` | The agent: perceive → reason → decide → act |
| `data/medicines.js` | Knowledge base: 60+ brands/generics in 21 compositions, salt spellings, drug-alert list, checklist |
| `data/samples.js` | Demo packs (also used by the tests) |
| `app.js`, `index.html`, `style.css` | The phone web page |
| `lib/` | Barcode scanner (html5-qrcode) and OCR (tesseract.js), both Apache-2.0 |
| `sw.js`, `manifest.json` | Lets it work offline and install like an app |

**Add a medicine:** copy one block in `data/medicines.js`.
**Update the alert list:** the two entries in `BATCH_ALERTS` are *samples*. Replace them with the monthly
*Drug Alert* list from [cdsco.gov.in](https://cdsco.gov.in) or your State Drug Controller.

## Report a fake medicine (India)

- Pharmacovigilance Programme of India (PvPI) helpline **1800-180-3024** (toll free), or the *ADR PvPI* app
- Your **State Drug Controller** or **CDSCO** – give the batch no., shop name and bill

## Limits

- It is a screening tool, not a lab test. A perfect copy with a valid barcode can pass.
- The medicine list is small (a college project). Unknown brands get only the general checks.
- OCR can misread poor photos – always check the filled-in details before pressing *Check*.
- Ask a doctor or pharmacist before switching to any alternative.

## Ideas for next steps

- Hindi / Telugu / Tamil interface and voice
- Load the CDSCO alert list and a full drug database automatically
- Check the QR code against the manufacturer's official verification page
- An image model trained on genuine vs fake packaging photos
