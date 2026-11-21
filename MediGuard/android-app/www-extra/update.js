/*
 * MediGuard Android app - update roll-out.
 * On start the app asks GitHub for the newest release. If it is newer than this app,
 * a banner offers the new APK; tapping it downloads the update in the phone's browser.
 */
(function () {
  "use strict";
  const cfg = window.MEDIGUARD_APP || {};
  if (!cfg.repo || !cfg.version) return;

  const parts = (v) => String(v).replace(/^v/i, "").split(".").map((n) => parseInt(n, 10) || 0);
  const newer = (a, b) => {
    const x = parts(a), y = parts(b);
    for (let i = 0; i < Math.max(x.length, y.length); i++) {
      if ((x[i] || 0) !== (y[i] || 0)) return (x[i] || 0) > (y[i] || 0);
    }
    return false;
  };

  function banner(release, apk) {
    const bar = document.createElement("div");
    bar.className = "update-banner";
    bar.setAttribute("role", "status");
    const text = document.createElement("div");
    const title = document.createElement("strong");
    title.textContent = `Update available: ${release.tag_name}`;
    const note = document.createElement("small");
    note.textContent = `You have v${cfg.version}. Tap Update, then open the downloaded file to install.`;
    text.append(title, note);
    const get = document.createElement("a");
    get.className = "btn small update-get";
    get.href = apk.browser_download_url;
    get.textContent = "Update";
    const later = document.createElement("button");
    later.className = "btn ghost small";
    later.textContent = "Later";
    later.onclick = () => {
      bar.remove();
      try { sessionStorage.setItem("mg-update-later", release.tag_name); } catch (e) { /* private mode */ }
    };
    bar.append(text, get, later);
    document.body.prepend(bar);
  }

  async function check() {
    try {
      if (sessionStorage.getItem("mg-update-later")) return;
    } catch (e) { /* ignore */ }
    try {
      const res = await fetch(`https://api.github.com/repos/${cfg.repo}/releases/latest`,
        { headers: { Accept: "application/vnd.github+json" } });
      if (!res.ok) return;
      const rel = await res.json();
      const apk = (rel.assets || []).find((a) => /\.apk$/i.test(a.name));
      if (apk && newer(rel.tag_name, cfg.version)) banner(rel, apk);
    } catch (e) {
      /* offline: try again next start */
    }
  }

  const about = () => {
    const d = document.querySelector(".disclaimer");
    if (d) {
      const v = document.createElement("span");
      v.className = "app-version";
      v.textContent = ` App version ${cfg.version}.`;
      d.append(v);
    }
  };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", () => { about(); check(); });
  else { about(); check(); }
})();
