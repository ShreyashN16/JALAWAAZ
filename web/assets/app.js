/* Jal Awaaz shared front-end helpers. No framework, no build step, no external requests. */
(function () {
  "use strict";

  // ------------------------------------------------------------ DOM
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => Array.from(el.querySelectorAll(s));

  /** h("div.cls#id", {attrs}, ...children). Strings become text nodes (never HTML). */
  function h(spec, attrs, ...kids) {
    const m = spec.match(/^([a-z0-9-]+)?((?:[.#][\w-]+)*)$/i);
    const el = document.createElement((m && m[1]) || "div");
    if (m && m[2]) m[2].replace(/([.#])([\w-]+)/g, (_, t, v) => (t === "." ? el.classList.add(v) : (el.id = v)));
    if (attrs && (typeof attrs !== "object" || attrs instanceof Node || Array.isArray(attrs))) { kids.unshift(attrs); attrs = null; }
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v == null || v === false) continue;
      if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
      else if (k === "html") el.innerHTML = v;                       // only for trusted, static markup (icons)
      else if (k === "dataset") Object.assign(el.dataset, v);
      else if (k === "style" && typeof v === "object") Object.assign(el.style, v);
      else el.setAttribute(k, v === true ? "" : v);
    }
    const add = (k) => { if (k == null || k === false) return; if (Array.isArray(k)) return k.forEach(add);
      el.append(k instanceof Node ? k : document.createTextNode(String(k))); };
    kids.forEach(add);
    return el;
  }

  // ------------------------------------------------------------ icons (stroke, 24 grid)
  const P = {
    phone: '<path d="M5 4h4l2 5-2.5 1.5a11 11 0 0 0 5 5L15 13l5 2v4a2 2 0 0 1-2 2A16 16 0 0 1 3 6a2 2 0 0 1 2-2"/>',
    hangup: '<path d="M3 15.5c5-5 13-5 18 0l-2.4 2.4-3.6-1.5v-3c-2-.7-4-.7-6 0v3l-3.6 1.5z"/>',
    mic: '<rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3"/>',
    stop: '<rect x="7" y="7" width="10" height="10" rx="2"/>',
    keyboard: '<rect x="2.5" y="6" width="19" height="12" rx="2"/><path d="M6 10h.01M10 10h.01M14 10h.01M18 10h.01M7 14h10"/>',
    replay: '<path d="M4 12a8 8 0 1 0 2.3-5.7M4 4v4h4"/>',
    pin: '<path d="M12 21s-7-6.2-7-11.5A7 7 0 0 1 19 9.5C19 14.8 12 21 12 21z"/><circle cx="12" cy="9.5" r="2.5"/>',
    check: '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
    x: '<path d="M6 6l12 12M18 6L6 18"/>',
    alert: '<path d="M12 3l9.5 17h-19z"/><path d="M12 10v4M12 17.5h.01"/>',
    clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    drop: '<path d="M12 3s6.5 7.2 6.5 11.5a6.5 6.5 0 0 1-13 0C5.5 10.2 12 3 12 3z"/>',
    wrench: '<path d="M14.5 6.5a4 4 0 0 0 5 5l-8 8a2.1 2.1 0 0 1-3-3l8-8a4 4 0 0 1-2-2z"/>',
    refresh: '<path d="M20 11a8 8 0 0 0-14.3-4.3L4 9M4 4v5h5M4 13a8 8 0 0 0 14.3 4.3L20 15m0 5v-5h-5"/>',
    download: '<path d="M12 4v11M7 10l5 5 5-5M5 20h14"/>',
    external: '<path d="M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"/>',
    users: '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20a6.5 6.5 0 0 1 13 0M16 4.5a3.5 3.5 0 0 1 0 7M21.5 20a6.5 6.5 0 0 0-4-6"/>',
    calendar: '<rect x="3.5" y="5" width="17" height="15.5" rx="2"/><path d="M3.5 10h17M8 3v4M16 3v4"/>',
    info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7.5h.01"/>',
    eye: '<path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
    layers: '<path d="M12 3l9 5-9 5-9-5zM3 13l9 5 9-5"/>',
    plus: '<path d="M12 5v14M5 12h14"/>', minus: '<path d="M5 12h14"/>',
    target: '<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="3"/><path d="M12 1v3M12 20v3M1 12h3M20 12h3"/>',
    logout: '<path d="M15 4h4a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1h-4M10 17l5-5-5-5M15 12H3"/>',
    list: '<path d="M8 6h13M8 12h13M8 18h13M3.5 6h.01M3.5 12h.01M3.5 18h.01"/>',
    play: '<path d="M7 4.5v15l12.5-7.5z"/>',
    note: '<path d="M5 4h10l4 4v12H5z"/><path d="M14 4v5h5M8 13h8M8 17h5"/>',
    shield: '<path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z"/>',
    chevron: '<path d="M9 6l6 6-6 6"/>',
    sms: '<path d="M4 5h16v11H9l-5 4z"/>',
    speaker: '<path d="M4 9h4l5-4v14l-5-4H4z"/><path d="M16.5 8.5a5 5 0 0 1 0 7M19 6a8.5 8.5 0 0 1 0 12"/>',
  };
  function icon(name, cls) {
    return `<svg class="ic ${cls || ""}" viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${P[name] || ""}</svg>`;
  }
  const ic = (name, cls) => h("span", { html: icon(name, cls), style: { display: "inline-flex" } });

  // ------------------------------------------------------------ labels (English for staff, Marathi/Hindi for villagers)
  const L = {
    source: {
      handpump: { en: "Handpump", mr: "हातपंप", hi: "हैंडपंप" }, tap: { en: "Tap / pipeline", mr: "नळ", hi: "नल" },
      borewell: { en: "Borewell", mr: "बोअरवेल", hi: "बोरवेल" }, well: { en: "Well", mr: "विहीर", hi: "कुआँ" },
      tank: { en: "Water tank", mr: "टाकी", hi: "टंकी" }, tanker: { en: "Tanker", mr: "टँकर", hi: "टैंकर" },
      other: { en: "Other source", mr: "इतर स्रोत", hi: "दूसरा स्रोत" },
    },
    fault: {
      no_water: { en: "No water", mr: "पाणी नाही", hi: "पानी नहीं" }, low_pressure: { en: "Low pressure", mr: "कमी दाब", hi: "कम दबाव" },
      leakage: { en: "Leakage", mr: "गळती", hi: "लीकेज" }, contamination: { en: "Contaminated water", mr: "दूषित पाणी", hi: "गंदा पानी" },
      broken_part: { en: "Broken part", mr: "भाग तुटला", hi: "पुर्ज़ा टूटा" }, power: { en: "Power / motor", mr: "वीज समस्या", hi: "बिजली की समस्या" },
      other: { en: "Other fault", mr: "इतर अडचण", hi: "दूसरी समस्या" },
    },
    state: {
      NEW: { en: "New", mr: "नवीन", hi: "नई" }, ACKED: { en: "Acknowledged", mr: "इंजिनिअरने पाहिली", hi: "इंजीनियर ने देखी" },
      FIX_CLAIMED: { en: "Awaiting caller", mr: "तुमच्या खात्रीची वाट", hi: "आपकी पुष्टि का इंतज़ार" },
      VERIFIED: { en: "Verified by caller", mr: "दुरुस्त, तुम्ही खात्री केली", hi: "ठीक, आपने पुष्टि की" },
      REOPENED: { en: "Reopened", mr: "पुन्हा उघडली", hi: "फिर से खुली" }, UNVERIFIED: { en: "No answer", mr: "उत्तर नाही", hi: "जवाब नहीं" },
    },
    symptom: { diarrhoea: "Diarrhoea", vomiting: "Vomiting", fever: "Fever", skin: "Skin problem", stomach_pain: "Stomach pain", none: "None reported" },
  };
  const label = (kind, v, lang = "en") => (v && L[kind][v] ? (L[kind][v][lang] || L[kind][v].en) : v ? String(v) : "");
  const STATE_COLOR = { NEW: "var(--red)", ACKED: "var(--red)", REOPENED: "var(--red)", FIX_CLAIMED: "var(--haldi)", VERIFIED: "var(--green)", UNVERIFIED: "var(--slate)" };
  const stateChip = (s) => h("span.chip.st-" + s, label("state", s));
  const prio = (p) => h("span.prio.prio-" + p, { title: "Priority " + p }, "P" + p);

  // ------------------------------------------------------------ time (database stores UTC "YYYY-MM-DD HH:MM:SS")
  const parse = (ts) => (ts ? new Date(String(ts).replace(" ", "T") + (String(ts).endsWith("Z") ? "" : "Z")) : null);
  const IST = { timeZone: "Asia/Kolkata" };
  function when(ts) {
    const d = parse(ts); if (!d) return "";
    return d.toLocaleString("en-IN", { ...IST, day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", hour12: false });
  }
  function ago(ts) {
    const d = parse(ts); if (!d) return "";
    const s = Math.round((Date.now() - d.getTime()) / 1000);
    if (s < 45) return "just now";
    if (s < 3600) return Math.round(s / 60) + " min ago";
    if (s < 86400) return Math.round(s / 3600) + " h ago";
    return Math.round(s / 86400) + " d ago";
  }
  function dur(min) {
    if (min == null) return "–";
    const m = Math.abs(min);
    if (m < 1) return Math.round(m * 60) + " s";
    if (m < 90) return Math.round(m) + " min";
    if (m < 60 * 48) { const t = Math.round(m), hh = Math.floor(t / 60), mm = t % 60; return hh + " h" + (mm ? " " + mm + " min" : ""); }
    return (m / 1440).toFixed(1) + " d";
  }
  function until(ts) {
    const d = parse(ts); if (!d) return null;
    return (d.getTime() - Date.now()) / 60000;          // minutes; negative = overdue
  }
  const pct = (x, digits = 0) => (x == null ? "–" : (x * 100).toFixed(digits) + "%");

  // ------------------------------------------------------------ API
  class ApiError extends Error { constructor(msg, status, code) { super(msg); this.status = status; this.code = code; } }
  let CSRF = null;
  async function api(path, opts = {}) {
    const init = { method: opts.method || "GET", headers: { Accept: "application/json" }, credentials: "same-origin" };
    if (opts.json !== undefined) { init.body = JSON.stringify(opts.json); init.headers["Content-Type"] = "application/json"; }
    if (opts.form) init.body = opts.form;
    if (init.method !== "GET" && CSRF) init.headers["X-CSRF-Token"] = CSRF;
    let r;
    try { r = await fetch(path, init); }
    catch (e) { throw new ApiError("The server is not reachable. Check that it is running.", 0, "network"); }
    const isJson = (r.headers.get("content-type") || "").includes("json");
    const data = isJson ? await r.json().catch(() => null) : null;
    if (!r.ok) {
      const msg = (data && data.error && data.error.message) || `Request failed (${r.status})`;
      if (r.status === 401 && !opts.noRedirect && !location.pathname.startsWith("/login"))
        location.href = "/login?next=" + encodeURIComponent(location.pathname);
      throw new ApiError(msg, r.status, data && data.error && data.error.code);
    }
    return data;
  }
  async function me() {
    const m = await api("/api/me", { noRedirect: true });
    CSRF = m.csrf; return m;
  }

  // ------------------------------------------------------------ toasts
  function toast(msg, kind = "") {
    let box = $(".toasts");
    if (!box) { box = h("div.toasts", { role: "status", "aria-live": "polite" }); document.body.append(box); }
    const t = h("div.toast" + (kind ? "." + kind : ""), h("span", { html: icon(kind === "err" ? "alert" : kind === "ok" ? "check" : "info") }), h("span", msg));
    box.append(t);
    setTimeout(() => t.remove(), kind === "err" ? 7000 : 4200);
  }

  // ------------------------------------------------------------ top bar
  const LOGO = `<svg class="brand-mark" viewBox="0 0 32 32" aria-hidden="true"><path d="M16 3.5s9 10 9 16a9 9 0 0 1-18 0c0-6 9-16 9-16z" fill="#2FB3C0"/><path d="M11.5 20.5a4.5 4.5 0 0 0 9 0" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round"/><path d="M8.6 20.8a7.4 7.4 0 0 0 14.8 0" fill="none" stroke="#fff" stroke-width="1.4" stroke-linecap="round" opacity=".55"/></svg>`;
  function topbar(active, role) {
    const links = [["/", "Overview"], ["/phone", "Villager phone"]];
    if (role === "engineer") links.push(["/engineer", "Engineer queue"]);
    if (role) links.push(["/dashboard", "District dashboard"]);
    links.push(["/metrics", "Evaluation"], ["/docs", "API"]);
    const nav = h("nav.nav", { "aria-label": "Main" }, links.map(([href, t]) => h("a", { href, "aria-current": href === active ? "page" : null }, t)));
    const end = h("div.topbar-end");
    if (role) {
      end.append(h("span.role-tag", "Signed in: " + role),
        h("button.btn.btn-quiet.btn-sm", { onclick: async () => { await api("/api/logout", { method: "POST" }); location.href = "/"; } }, "Sign out"));
    } else if (active !== "/login") {
      end.append(h("a.btn.btn-quiet.btn-sm", { href: "/login?next=" + encodeURIComponent(active === "/" ? "/dashboard" : active) }, "Staff sign-in"));
    }
    const menuBtn = h("button.menu-btn", { type: "button", "aria-label": "Menu", "aria-expanded": "false", html: icon("list") });
    const bar = h("header.topbar", h("a.brand", { href: "/", html: LOGO + '<span class="brand-name" lang="mr">जल आवाज</span><span class="brand-latin">Jal Awaaz</span>' }), nav, end, menuBtn);
    menuBtn.addEventListener("click", () => { const open = bar.classList.toggle("open"); menuBtn.setAttribute("aria-expanded", String(open)); });
    const strip = h("div.notice-strip", h("span", h("strong", "Independent prototype."), " Not an official government service."),
      h("span", "Phone calls are simulated in the browser; SMS is logged, not sent."), h("a", { href: "/#real" }, "What is real here"));
    document.body.prepend(bar, strip);
  }

  // ------------------------------------------------------------ polling that pauses in background tabs
  function every(ms, fn) {
    let timer = null, stopped = false;
    const tick = async () => { if (stopped) return; try { await fn(); } catch (e) { console.warn(e); } timer = setTimeout(tick, document.hidden ? ms * 4 : ms); };
    tick();
    return { stop() { stopped = true; clearTimeout(timer); }, now() { clearTimeout(timer); tick(); } };
  }

  function sparkBars(values, opts = {}) {
    // Small multiple: one row of bars, shared scale passed in opts.max
    const w = opts.w || 280, hgt = opts.h || 46, n = values.length, gap = 2;
    const max = Math.max(1, opts.max || Math.max(...values));
    const bw = (w - gap * (n - 1)) / n;
    const bars = values.map((v, i) => `<rect x="${(i * (bw + gap)).toFixed(1)}" y="${(hgt - (v / max) * hgt).toFixed(1)}" width="${bw.toFixed(1)}" height="${((v / max) * hgt || 0).toFixed(1)}" rx="1.5" fill="${opts.color || "var(--teal)"}"><title>${opts.titles ? opts.titles[i] : v}</title></rect>`).join("");
    return `<svg viewBox="0 0 ${w} ${hgt}" width="100%" height="${hgt}" preserveAspectRatio="none" role="img" aria-label="${opts.label || "bar chart"}"><rect x="0" y="${hgt - 1}" width="${w}" height="1" fill="var(--line)"/>${bars}</svg>`;
  }

  window.JA = { $, $$, h, icon, ic, L, label, STATE_COLOR, stateChip, prio, parse, when, ago, dur, until, pct, api, ApiError, me,
    get csrf() { return CSRF; }, toast, topbar, every, sparkBars };
})();
