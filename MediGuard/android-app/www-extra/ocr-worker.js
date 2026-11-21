// MediGuard OCR worker for the hosted page.
// The page host only serves text files, so the English language data is stored as base64
// (lang/eng.traineddata.txt). When the text reader asks for eng.traineddata.gz, hand it those bytes.
const realFetch = self.fetch.bind(self);
self.fetch = async (url, opts) => {
  if (String(url).endsWith("eng.traineddata.gz")) {
    const res = await realFetch(new URL("lang/eng.traineddata.txt", self.location.href));
    const b64 = await res.text();
    const bin = atob(b64.trim());
    const bytes = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    return new Response(bytes, { status: 200 });
  }
  return realFetch(url, opts);
};
importScripts("worker.min.js");
