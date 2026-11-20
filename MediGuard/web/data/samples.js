/*
 * MediGuard - demo packs, so you can try the agent without a real strip.
 * Used by the "Try a demo" buttons and by the tests. All values are made up.
 * The demo "today" is fixed so the results never change.
 */
(function (root) {
  "use strict";

  const SAMPLES = {
    genuine: {
      title: "Genuine-looking Dolo 650",
      today: "2026-11-20",
      text: [
        "DOLO-650",
        "Paracetamol Tablets IP 650 mg",
        "Each uncoated tablet contains: Paracetamol IP 650 mg",
        "B.No. DOBS3975",
        "Mfg. 04/2026   Exp. 03/2030",
        "M.R.P. Rs. 33.60 for 15 tablets incl. of all taxes",
        "Mfg. Lic. No. KTK/25/394/94",
        "Manufactured by: Micro Labs Limited, Bengaluru, India",
      ].join("\n"),
      codes: [
        { format: "QR_CODE", text: "Brand: Dolo 650\nGeneric: Paracetamol Tablets IP 650 mg\nManufacturer: Micro Labs Ltd\nBatch: DOBS3975\nMfg: 04/2026\nExp: 03/2030\nUPI: 8901234567890" },
        { format: "EAN_13", text: "8901234567890" },
      ],
      checklist: {},
    },

    fake: {
      title: "Fake 'Crosin Advance'",
      today: "2026-11-20",
      text: [
        "CROSIN Advance",
        "Paracetamol Tablets 650 mg",
        "B.No. FAKE2291",
        "Mfg. 01/2027  Exp. 12/2035",
        "Manufactured by: Healthline Pharma Pvt Ltd",
      ].join("\n"),
      codes: [{ format: "EAN_13", text: "8901234567891" }],
      checklist: { poorPrint: true, tooCheap: true },
    },

    copiedQR: {
      title: "Augmentin with a copied QR code",
      today: "2026-11-20",
      text: [
        "AUGMENTIN 625 DUO",
        "Amoxycillin and Potassium Clavulanate Tablets IP",
        "Amoxycillin 500 mg  Clavulanic acid 125 mg",
        "B.No. AG7731  Mfg. 02/2026  Exp. 01/2028",
        "Rx Schedule H Prescription Drug",
        "Marketed by: GlaxoSmithKline Pharmaceuticals Ltd",
      ].join("\n"),
      codes: [{ format: "DATA_MATRIX", text: "(01)08907654321005(17)270131(10)AG1002(21)X55K2" }],
      checklist: {},
    },

    expired: {
      title: "Expired Pan 40",
      today: "2026-11-20",
      text: [
        "PAN 40",
        "Pantoprazole Gastro-resistant Tablets IP 40 mg",
        "B.No. PNX2408   Mfg. 09/2024   Exp. 08/2026",
        "Rx Schedule H Prescription Drug",
        "Manufactured by: Alkem Laboratories Ltd, Mumbai",
      ].join("\n"),
      codes: [],
      checklist: {},
    },
  };

  if (typeof module !== "undefined" && module.exports) module.exports = SAMPLES;
  else root.MEDI_SAMPLES = SAMPLES;
})(typeof self !== "undefined" ? self : this);
