// Run with:  node test/agent.test.js
const assert = require("assert");
const A = require("../agent.js");
const S = require("../data/samples.js");

let passed = 0;
function test(name, fn) {
  try { fn(); passed++; console.log("  ok  " + name); }
  catch (e) { console.error("  FAIL " + name + "\n       " + e.message); process.exitCode = 1; }
}
const titles = (r) => r.evidence.map((e) => e.title).join(" | ");
const today = "2026-11-20";

console.log("Demo packs");
test("genuine Dolo 650 -> no red flags", () => {
  const r = A.check(S.genuine);
  assert.strictEqual(r.verdict.key, "ok", titles(r));
  assert.strictEqual(r.medicine.brand, "Dolo 650");
  assert.ok(r.alternatives.some((a) => a.brand === "Calpol 650"));
  assert.ok(r.alternatives[0].generic, "generic should be listed first");
});
test("fake 'Crosin' -> likely fake, lookalike of Crocin Advance", () => {
  const r = A.check(S.fake);
  assert.strictEqual(r.verdict.key, "fake");
  assert.strictEqual(r.match, "lookalike");
  assert.strictEqual(r.medicine.brand, "Crocin Advance");
  assert.ok(r.alternatives[0].original, "the genuine brand is offered first");
});
test("copied QR -> likely fake (batch + expiry mismatch)", () => {
  const r = A.check(S.copiedQR);
  assert.strictEqual(r.verdict.key, "fake", titles(r));
  assert.ok(/batch doesn't match/.test(titles(r)));
});
test("expired Pan 40 -> expired", () => {
  const r = A.check(S.expired);
  assert.strictEqual(r.verdict.key, "expired");
});

console.log("Rules");
test("GS1 check digit", () => {
  assert.ok(A.gtinValid("8901234567890"));
  assert.ok(!A.gtinValid("8901234567891"));
  assert.ok(A.gtinValid("08907654321005"));
});
test("GS1 DataMatrix without brackets (with GS separator)", () => {
  const g = A.parseGS1("]d2010890765432100517270131" + "10AB12\u001d21XYZ");
  assert.strictEqual(g.gtin, "08907654321005");
  assert.deepStrictEqual(g.exp, { y: 2027, m: 1 });
  assert.strictEqual(g.batch, "AB12");
  assert.strictEqual(g.serial, "XYZ");
});
test("dates in many formats", () => {
  for (const s of ["MAR 2027", "Mar.27", "03/27", "03/2027", "2027-03", "15/03/2027", "03-2027"]) {
    assert.deepStrictEqual(A.parseDate(s), { y: 2027, m: 3 }, s);
  }
});
test("'Mfg. Lic. No.' is not read as a date", () => {
  const p = A.readPrintedText("Mfg. Lic. No. KTK/25/394/94\nMfg. 04/2026 Exp. 03/2030");
  assert.deepStrictEqual(p.mfg, { y: 2026, m: 4 });
  assert.deepStrictEqual(p.exp, { y: 2030, m: 3 });
});
test("OCR confusion 0/O is not called a fake", () => {
  const r = A.identify("D0L0-650 tablets");
  assert.strictEqual(r.kind, "exact");
  assert.strictEqual(r.med.brand, "Dolo 650");
});
test("similar real brands don't flag each other (Pantocid / Pantodac)", () => {
  assert.strictEqual(A.identify("PANTOCID 40").med.brand, "Pantocid 40");
  assert.strictEqual(A.identify("PANTODAC 40").med.brand, "Pantodac 40");
  assert.strictEqual(A.identify("PANTODAC 40").kind, "exact");
});
test("strength mismatch is caught", () => {
  const r = A.check({ today, text: "DOLO-650 Paracetamol Tablets IP 500 mg B.No. X1234 Exp. 03/2029 Manufactured by: Micro Labs Ltd" });
  assert.ok(/Strength doesn't match/.test(titles(r)), titles(r));
});
test("manufacture date in the future is caught", () => {
  const r = A.check({ today, manual: { brand: "Telma 40", batch: "TL123", mfg: "2027-05", exp: "2029-04" } });
  assert.ok(/in the future/.test(titles(r)));
});
test("typed details only, all fine -> no red flags", () => {
  const r = A.check({ today, manual: { brand: "Azee 500", batch: "AZ2201", mfg: "2026-01", exp: "2028-12", barcode: "8901234567890" } });
  assert.strictEqual(r.verdict.key, "ok", titles(r));
});
test("visual checklist alone makes it suspicious", () => {
  const r = A.check({ today, manual: { brand: "Azee 500", batch: "AZ2201", exp: "2028-12" }, checklist: { sealBroken: true, poorPrint: true } });
  assert.strictEqual(r.verdict.key, "suspicious", titles(r));
});
test("short-link QR is a warning", () => {
  const r = A.check({ today, codes: [{ format: "QR_CODE", text: "https://bit.ly/abc" }] });
  assert.ok(/short link/.test(titles(r)));
});
test("unknown medicine -> not enough information", () => {
  const r = A.check({ today, text: "Some unknown syrup" });
  assert.strictEqual(r.verdict.key, "unknown");
});
test("search by salt finds brands and alternatives", () => {
  const res = A.search("pantoprazole");
  assert.ok(res.length >= 3);
  assert.ok(res.every((r) => r.composition.startsWith("Pantoprazole")));
});

console.log("Real strip photo (user test, no QR, sideways stamp, foil)");
const REAL = require("fs").readFileSync(__dirname + "/real_strip_ocr.txt", "utf8");
test("unbranded calcium + D3 strip is recognised by composition", () => {
  const r = A.check({ today: "2026-11-21", text: REAL });
  assert.strictEqual(r.match, "composition");
  assert.ok(/Calcium/.test(r.medicine.brand));
  assert.strictEqual(r.extracted.exp, "09/2027");          // from the sideways stamp "DP.09/2027"
  assert.strictEqual(r.verdict.key, "details", titles(r)); // asks for the batch no.
  assert.ok(!/Strength doesn't match/.test(titles(r)));   // "elemental calcium 500 mg" is not a wrong strength
});
test("same strip with the batch typed in -> no red flags", () => {
  const r = A.check({ today: "2026-11-21", text: REAL, manual: { batch: "CCV-A102" } });
  assert.strictEqual(r.verdict.key, "ok", titles(r));
});
test("government-supply strip bought in a shop is suspicious", () => {
  const r = A.check({ today: "2026-11-21", text: REAL + "\nTelangana Government Supply\nNot for Sale",
                      manual: { batch: "CCV-A102", price: "40" } });
  assert.strictEqual(r.verdict.key, "suspicious", titles(r));
});

test("a past expiry read only by the camera asks to check instead of saying EXPIRED", () => {
  const r = A.check({ today: "2026-11-21", text: REAL.replace("DP.09/2027", "EXP.09/2022"), unconfirmed: true });
  assert.strictEqual(r.verdict.key, "suspicious", titles(r));
  assert.ok(/please check/.test(titles(r)));
  const r2 = A.check({ today: "2026-11-21", text: REAL.replace("DP.09/2027", "EXP.09/2022") });
  assert.strictEqual(r2.verdict.key, "expired");   // confirmed by the user -> EXPIRED
});

console.log(`\n${passed} passed${process.exitCode ? ", some FAILED" : ""}`);
