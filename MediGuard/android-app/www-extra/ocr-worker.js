// MediGuard OCR worker for the hosted page.
// The page host only serves text files, so the English language data is stored as base64
// (lang/<name>.traineddata.txt). When the reader asks for <name>.traineddata.gz, hand it those bytes.
const realFetch = self.fetch.bind(self);
self.fetch = async (url, opts) => {
  const m = String(url).match(/([a-z_]+)\.traineddata\.gz$/);
  if (m) {
    const res = await realFetch(new URL("lang/" + m[1] + ".traineddata.txt", self.location.href));
    const b64 = await res.text();
    const bin = atob(b64.trim());
    const bytes = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    return new Response(bytes, { status: 200 });
  }
  return realFetch(url, opts);
};
importScripts("worker.min.js");
