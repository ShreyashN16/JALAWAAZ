/* District dashboard. Polls the API every 3 s; every number on screen comes from /api/metrics or /api/tickets. */
(async function () {
  "use strict";
  const { $, $$, h, icon, api, toast, label, stateChip, prio, when, ago, dur, until, pct, every, sparkBars, STATE_COLOR } = JA;
  const me = await JA.me().catch(() => ({}));
  JA.topbar("/dashboard", me.role);
  const D = { tickets: [], metrics: null, villages: [], sel: null, village: "", prio: "", state: "", q: "", lastOk: 0, map: null, openPop: null };
  if (me.role === "officer") {
    $$(".officer-only").forEach((e) => (e.hidden = false));
    $("#btn-csv").innerHTML = icon("download") + "Export CSV";
    if (!me.demo_mode) $("#demo-menu").hidden = true;
  }
  const syn = () => ($("#f-syn").checked ? "1" : "0");
  const isOpen = (t) => !["VERIFIED", "UNVERIFIED"].includes(t.state);

  // ------------------------------------------------------------ map
  const mc = await api("/api/map-config").catch(() => ({}));
  D.villages = await api("/api/villages");
  D.map = new JAMap($("#map"), { tileUrl: mc.tile_url, attribution: mc.attribution, label: "Map of pilot villages with ticket pins" });
  const mapped = D.villages.filter((v) => v.lat != null);
  D.map.fit(mapped.map((v) => ({ lat: v.lat, lon: v.lon })));
  function drawDots(pinned) {
    D.map.setLayer("villages", mapped.filter((v) => !pinned.has(v.name)).map((v) => ({ lat: v.lat, lon: v.lon,
      el: h("div.vdot" + (v.coord_quality === "approximate" ? ".approx" : ""), { title: `${v.name}: ${v.coord_quality} position. Source: ${v.coord_source}` }, h("i"), h("span", v.name)) })));
  }
  drawDots(new Set());
  const talukas = [...new Set(D.villages.map((v) => v.taluka).filter(Boolean))], districts = [...new Set(D.villages.map((v) => v.district).filter(Boolean))];
  $("#area").textContent = talukas.length === 1 ? `${talukas[0]} taluka, ${districts[0]} district` : "District dashboard";
  $("#map-hint").textContent = `${mapped.length} of ${D.villages.length} villages located. Open dots: approximate positions.`;

  function drawPins() {
    const repeat = new Set((D.metrics ? D.metrics.repeat_sources : []).map((r) => r.village));
    const byV = {};
    for (const t of D.tickets) (byV[t.village] = byV[t.village] || []).push(t);
    const pins = [];
    for (const [name, ts] of Object.entries(byV)) {
      const v = D.villages.find((x) => x.name === name);
      if (!v || v.lat == null) continue;
      const open = ts.filter(isOpen);
      const reopenedOpen = open.some((t) => t.reopened_count > 0), p1 = open.some((t) => t.priority === 1);
      let color = "var(--slate)";
      if (open.some((t) => ["NEW", "ACKED"].includes(t.state))) color = "var(--red)";
      else if (open.some((t) => t.state === "FIX_CLAIMED")) color = "var(--haldi)";
      else if (ts.some((t) => t.state === "VERIFIED")) color = "var(--green)";
      const n = open.length || ts.length;
      const el = h("div.vpin" + (D.village === name ? ".sel" : ""), { style: { "--pin": color } },
        (reopenedOpen || p1) ? h("span.ripple", h("i"), h("i"), h("i")) : null,
        repeat.has(name) ? h("span.ring") : null,
        h("button", { type: "button", "aria-label": `${name}: ${open.length} open of ${ts.length} tickets`, title: `${name}: ${open.length} open of ${ts.length}`,
          onclick: (e) => { e.stopPropagation(); villagePop(v, ts); } }, String(n)),
        h("span.vname", name));
      pins.push({ lat: v.lat, lon: v.lon, el });
    }
    D.map.setLayer("pins", pins);
    drawDots(new Set(Object.keys(byV)));
    const off = Object.keys(byV).filter((n) => { const v = D.villages.find((x) => x.name === n); return !v || v.lat == null; });
    $("#offmap").textContent = off.length ? `Not on the map (no verified coordinates): ${off.map((n) => `${n} (${byV[n].length})`).join(", ")}. They are in the ticket list.` : "Every village with tickets is on the map.";
  }
  function villagePop(v, ts) {
    closePop();
    const open = ts.filter(isOpen);
    const pub = $("#f-public").checked;
    const pop = h("div.pop", h("h4", v.name), h("div", `${open.length} open of ${ts.length} tickets`),
      h("div.muted", `${ts.filter((t) => t.state === "VERIFIED").length} verified by caller, ${ts.filter((t) => t.reopened_count).length} reopened at least once`),
      pub ? null : h("button.btn-link.small", { type: "button", style: { marginTop: "6px" }, onclick: () => { setVillage(v.name); closePop(); } }, "Show these tickets"));
    D.map.setLayer("pop", [{ lat: v.lat, lon: v.lon, el: pop }]);
    D.openPop = pop;
  }
  function closePop() { if (D.openPop) { D.map.setLayer("pop", []); D.openPop = null; } }
  $("#map").addEventListener("click", (e) => { if (!e.target.closest(".pop")) closePop(); });

  // ------------------------------------------------------------ figures
  const short = (min) => {
    const v = (n, u) => h("span", String(n), h("small", u));
    if (min < 1) return v(Math.round(min * 60), "s");
    if (min < 90) return v(Math.round(min), "min");
    if (min < 2880) return v(+(min / 60).toFixed(1), "h");
    return v(+(min / 1440).toFixed(1), "d");
  };
  function figures() {
    const m = D.metrics, fc = m.false_closure, ins = m.insights;
    const box = $("#figures"); box.innerHTML = "";
    const f = (cls, labelT, value, foot, title) => h("div.figure" + cls, { title: title || null }, h("div.label", labelT), h("div.value", value), h("div.foot", foot));
    box.append(
      f(".lead", "False-closure rate", fc.rate == null ? "–" : h("span", pct(fc.rate)),
        h("span", `${fc.reopened} reopened of ${fc.answered} fixes the caller answered (n = ${fc.answered})`, h("div.lead-formula", "Tickets reopened at least once ÷ tickets whose fix got a yes or no")),
        "How often a claimed fix turned out not to work, according to the person who reported it"),
      f(m.p1_open ? ".warn" : "", "Open tickets", String(m.open), `${m.p1_open} at P1`),
      f("", "Report to acknowledge", m.median_ack_min == null ? "–" : short(m.median_ack_min), `median, n = ${m.n_ack}`),
      f("", "Fix to caller's yes", m.median_fix_to_verified_min == null ? "–" : short(m.median_fix_to_verified_min), `median, n = ${m.n_fix_verified}`),
      f(ins.sla.awaiting_caller ? ".amber" : "", "Awaiting caller", String(ins.sla.awaiting_caller), "fix claimed, not yet confirmed"),
      f(ins.sla.overdue.length ? ".warn" : "", "Past SLA", String(ins.sla.overdue.length), `of ${ins.sla.open_with_sla} new or acknowledged`),
    );
    $("#syn-n").textContent = String(m.synthetic_tickets);
  }

  // ------------------------------------------------------------ queue
  function filtered() {
    const q = D.q.toLowerCase();
    return D.tickets.filter((t) => (!D.village || t.village === D.village) && (!D.prio || String(t.priority) === D.prio) &&
      (!D.state || (D.state === "open" ? isOpen(t) : t.state === D.state)) &&
      (!q || [t.ref, t.village, label("source", t.source_type), label("fault", t.fault), t.priority_reason].join(" ").toLowerCase().includes(q)));
  }
  function queue() {
    const rows = filtered();
    const ul = $("#tlist"); ul.innerHTML = "";
    $("#q-count").textContent = `${rows.length} of ${D.tickets.length}`;
    $("#f-reset").hidden = !(D.village || D.prio || D.state || D.q);
    if (!rows.length) ul.append(h("li", h("div.empty", h("h3", D.tickets.length ? "No ticket matches these filters" : "No tickets yet"),
      D.tickets.length ? "Clear the filters to see every ticket." : "Report a fault from the villager phone, or add synthetic demo data from the menu above.")));
    for (const t of rows) {
      const mins = t.sla_due_at ? until(t.sla_due_at) : null;
      const sla = mins == null ? null : mins < 0 ? h("span.sla-over", "SLA passed " + dur(-mins) + " ago") : h("span", "SLA in " + dur(mins));
      ul.append(h("li", h("button.trow", { type: "button", "aria-current": D.sel === t.id ? "true" : "false", onclick: () => openDrawer(t.id) },
        prio(t.priority),
        h("span.v", t.village, " ", t.is_synthetic ? h("span.tag-syn", "synthetic") : null),
        h("span.meta", stateChip(t.state), sla || h("span", ago(t.created_at))),
        h("span.w", `${label("source", t.source_type) || "Source not given"}: ${label("fault", t.fault) || "fault not given"}` +
          (t.households ? `, ${t.households} households` : "") + (t.duration_days != null ? `, ${t.duration_days} d` : "") + `  #${t.ref}`),
        h("span.reason", (t.reopened_count ? `Reopened ${t.reopened_count}x. ` : "") + t.priority_reason))));
    }
  }
  function villageOptions() {
    const sel = $("#f-village"), cur = sel.value;
    const names = [...new Set(D.tickets.map((t) => t.village))].sort();
    sel.innerHTML = ""; sel.append(h("option", { value: "" }, "All villages"), names.map((n) => h("option", { value: n }, n)));
    sel.value = names.includes(cur) ? cur : "";
  }
  function setVillage(v) { D.village = v; $("#f-village").value = v; queue(); drawPins(); }

  // ------------------------------------------------------------ insights
  function insights() {
    const ins = D.metrics.insights;
    const d = ins.daily, max = Math.max(1, ...d.map((x) => Math.max(x.reported, x.verified, x.reopened)));
    const titles = (k) => d.map((x) => `${x.date}: ${x[k]} ${k}`);
    const row = (name, k, color) => h("div.sm-row", h("span", name), h("div", { html: sparkBars(d.map((x) => x[k]), { max, color, titles: titles(k), label: name + " per day" }) }), h("b", String(d.reduce((a, x) => a + x[k], 0))));
    const tr = $("#trend"); tr.innerHTML = "";
    tr.append(row("Reported", "reported", "var(--ink)"), row("Verified", "verified", "var(--green)"), row("Reopened", "reopened", "var(--red)"),
      h("div.axis", h("span", d[0].date.slice(5)), h("span", d[d.length - 1].date.slice(5))));
    const mix = $("#mix"); mix.innerHTML = "";
    const total = Math.max(1, ...Object.values(ins.by_fault));
    mix.append(h("div.small.muted", { style: { margin: "0 0 6px" } }, "Fault"));
    for (const [k, n] of Object.entries(ins.by_fault)) mix.append(h("div.hbar", h("span", label("fault", k) || "Not given"), h("div.bar", h("i", { style: { width: (100 * n / total) + "%", background: k === "contamination" ? "var(--red)" : "var(--teal)" } })), h("b", String(n))));
    mix.append(h("div.small.muted", { style: { margin: "14px 0 6px" } }, "Water source"));
    const st = Math.max(1, ...Object.values(ins.by_source));
    for (const [k, n] of Object.entries(ins.by_source)) mix.append(h("div.hbar", h("span", label("source", k) || "Not given"), h("div.bar", h("i", { style: { width: (100 * n / st) + "%", background: "var(--ink-2)" } })), h("b", String(n))));
    const at = $("#attn"); at.innerHTML = "";
    const ul = h("ul.attn");
    ins.sla.overdue.forEach((o) => ul.append(h("li", prio(o.priority), h("span", h("b", o.village), ` #${o.ref} ${label("state", o.state).toLowerCase()}, SLA passed ${dur(-until(o.due))} ago`))));
    (D.metrics.repeat_sources || []).forEach((r) => ul.append(h("li", h("span", { html: icon("refresh") }), h("span", h("b", r.village), ` ${label("source", r.source_type).toLowerCase()}: ${r.reports} reports in ${30} days`))));
    const unv = D.tickets.filter((t) => t.state === "UNVERIFIED");
    unv.forEach((t) => ul.append(h("li", h("span.chip.st-UNVERIFIED", "No answer"), h("span", h("b", t.village), ` #${t.ref}: caller never confirmed the fix`))));
    at.append(ul.childElementCount ? ul : h("div.empty", "Nothing past its SLA, no repeat failures, no unanswered verifications."));
  }

  async function feeds() {
    if ($("#f-public").checked) return;
    const [ev, sms] = await Promise.all([api(`/api/activity?synthetic=${syn()}&limit=40`), api("/api/sms")]);
    const fe = $("#feed"); fe.innerHTML = "";
    const say = (e) => {
      if (e.event === "created") return `Ticket created at P${e.to_priority}`;
      if (e.event === "state") return `${label("state", e.from_state)} → ${label("state", e.to_state)}` + (e.detail ? `: ${e.detail}` : "");
      if (e.event === "priority") return `Priority P${e.from_priority} → P${e.to_priority}`;
      if (e.event === "sla_escalation") return `SLA missed, priority raised P${e.from_priority} → P${e.to_priority}`;
      if (e.event === "sla_breach_p1") return "Past its SLA at P1 (already the highest priority)";
      if (e.event === "verify_declined") return "Caller declined the verification call";
      if (e.event === "note") return `Note: ${e.detail}`;
      if (e.event === "verify_call_queued") return `Verification call queued (${e.detail})`;
      if (e.event === "verify_no_answer") return `No answer to the verification call (${e.detail})`;
      return e.event.replace(/_/g, " ") + (e.detail ? `: ${e.detail}` : "");
    };
    if (!ev.length) fe.append(h("li", h("span"), h("span.muted", "No activity yet.")));
    ev.forEach((e) => fe.append(h("li", h("time", { datetime: e.at, title: when(e.at) }, ago(e.at)),
      h("span", h("button.btn-link", { type: "button", onclick: () => openDrawer(e.ticket_id) }, `#${e.ref}`), ` ${e.village}: ${say(e)} `, h("span.muted.small", `(${e.actor})`), e.is_synthetic ? h("span.tag-syn", "synthetic") : null))));
    const sm = $("#sms"); sm.innerHTML = "";
    const smsRows = sms.filter((s) => syn() === "1" || !s.is_synthetic);
    if (!smsRows.length) sm.append(h("li.muted", "No SMS yet."));
    smsRows.slice(0, 20).forEach((s) => sm.append(h("li", h("time", `${ago(s.at)} to ${s.to_role}`), h("span", s.body))));
  }

  // ------------------------------------------------------------ drawer
  async function openDrawer(id) {
    if ($("#f-public").checked) return;
    D.sel = id; queue();
    let t;
    try { t = await api(`/api/tickets/${id}`); } catch (e) { return toast(e.message, "err"); }
    closeDrawer(true);
    const scrim = h("div.scrim", { onclick: closeDrawer });
    const ev = (e) => {
      const cls = e.to_state === "VERIFIED" ? "t-green" : e.to_state === "FIX_CLAIMED" ? "t-haldi" : ["REOPENED"].includes(e.to_state) || e.event.includes("sla") ? "t-red" : e.event === "verify_call_queued" ? "t-teal" : "";
      const txt = e.event === "created" ? `Created at P${e.to_priority}` : e.event === "state" ? `${label("state", e.to_state)}` : e.event === "priority" ? `Priority P${e.from_priority} → P${e.to_priority}` : e.event.replace(/_/g, " ");
      return h("li." + (cls || "x"), h("div", h("b", txt), e.detail ? ` ${e.detail}` : ""), h("div.when", `${when(e.at)}, by ${e.actor}`));
    };
    const kv = (pairs) => h("dl.kv", pairs.filter((p) => p[1] !== null && p[1] !== undefined && p[1] !== "").flatMap(([k, v]) => [h("dt", k), h("dd", v)]));
    const mins = t.sla_due_at ? until(t.sla_due_at) : null;
    const dr = h("aside.drawer", { role: "dialog", "aria-modal": "true", "aria-label": `Ticket ${t.ref}` },
      h("div.drawer-head",
        h("div", h("div.row-wrap", prio(t.priority), stateChip(t.state), t.is_synthetic ? h("span.tag-syn", "synthetic") : null, t.needs_review ? h("span.chip.plain", "needs review") : null),
          h("h2", { style: { marginTop: "8px", fontSize: "var(--s-2xl)" } }, h("span.num", `#${t.ref}`), " ", t.village),
          h("div.muted.small", `Reported ${when(t.created_at)} (${ago(t.created_at)})`)),
        h("span.spacer"), h("button.btn.btn-quiet.btn-icon", { type: "button", "aria-label": "Close", onclick: closeDrawer, html: icon("x") })),
      h("div.drawer-body",
        h("section", h("h3", "Why this priority"), h("p", t.priority_reason),
          mins != null ? h("p.small", { style: { color: mins < 0 ? "var(--red)" : "var(--ink-2)" } }, mins < 0 ? `SLA passed ${dur(-mins)} ago. The scheduler raises priority one level per missed SLA.` : `Escalates in ${dur(mins)} if nobody acts.`) : null,
          t.reopened_count ? h("p.small", { style: { color: "var(--red)" } }, `Reopened ${t.reopened_count}x after the caller said the fix did not work.`) : null),
        h("section", h("h3", "What was reported"), kv([
          ["Source", label("source", t.source_type) || "Not given"], ["Fault", label("fault", t.fault) || "Not given"],
          ["Duration", t.duration_days != null ? `${t.duration_days} days` : "Not given"], ["Households", t.households != null ? String(t.households) : "Not given"],
          ["Drinking water", t.drinking_source == null ? "Not asked or not said" : t.drinking_source ? "Yes" : "No"],
          ["Symptoms", (t.symptoms || []).filter((s) => s !== "none").map((s) => JA.L.symptom[s] || s).join(", ") || "None reported"],
          ["Also mentioned", t.smell_colour_taste], ["Language", { mr: "Marathi", hi: "Hindi", hinglish: "Hinglish" }[t.lang] || t.lang],
          ["Extracted by", t.extraction_source]])),
        h("section", h("h3", "Where"), kv([["Village", t.village], ["Taluka", t.taluka], ["District", t.district],
          ["Position", t.lat != null ? `${t.lat.toFixed(4)}, ${t.lon.toFixed(4)} (${t.coord_quality || "cited"})` : "Not on the map"], ["Source", t.coord_source]]),
          t.lat != null ? h("a.btn.btn-quiet.btn-sm", { href: `https://www.google.com/maps/dir/?api=1&destination=${t.lat},${t.lon}`, target: "_blank", rel: "noopener", style: { marginTop: "10px" }, html: icon("pin") + "Directions" }) : null),
        h("section", h("h3", "The caller's words"), t.transcript ? h("p.deva", { style: { fontSize: "16px" } }, t.transcript) : h("p.muted", "Not kept (retention window passed) or synthetic."),
          t.evidence_quote ? h("p.small.muted", "Evidence for the extraction: ", h("span.deva", `“${t.evidence_quote}”`)) : null),
        h("section", h("h3", "Timeline"), h("ol.timeline", (t.events || []).map(ev))),
        h("section", h("h3", "Verification calls"), (t.verifications || []).length ? h("ul.attn", t.verifications.map((v) => h("li",
          h("span.chip.st-" + (v.result === "yes" ? "VERIFIED" : v.result === "no" ? "REOPENED" : "UNVERIFIED"), v.result === "yes" ? "Yes, water runs" : v.result === "no" ? "No, still broken" : "No answer"),
          h("span.small.muted", when(v.at))))) : h("p.muted", t.state === "FIX_CLAIMED" ? `Next call ${t.next_verify_at ? when(t.next_verify_at) : "soon"}; attempt ${t.verify_attempts} of 3 so far.` : "None yet.")),
        h("section", h("h3", "SMS sent (simulated)"), (t.sms || []).length ? h("ul.feed.sms", t.sms.map((s) => h("li", h("time", `${when(s.at)} to ${s.to_role}`), h("span", s.body)))) : h("p.muted", "None.")),
        t.notes ? h("section", h("h3", "Engineer notes"), h("pre", { style: { whiteSpace: "pre-wrap", font: "inherit", margin: 0 } }, t.notes)) : null));
    document.body.append(scrim, dr);
    dr.querySelector("button").focus();
    document.addEventListener("keydown", escClose);
  }
  function escClose(e) { if (e.key === "Escape") closeDrawer(); }
  function closeDrawer(keepSel) {
    $$(".drawer, .scrim").forEach((e) => e.remove());
    document.removeEventListener("keydown", escClose);
    if (keepSel !== true) { D.sel = null; queue(); }
  }

  // ------------------------------------------------------------ data loop
  async function load() {
    const [tickets, metrics] = await Promise.all([api(`/api/tickets?synthetic=${syn()}`), api(`/api/metrics?synthetic=${syn()}`)]);
    D.tickets = tickets; D.metrics = metrics; D.lastOk = Date.now();
    figures(); villageOptions(); queue(); drawPins(); insights();
  }
  const live = $("#live");
  setInterval(() => {
    const s = Math.round((Date.now() - D.lastOk) / 1000);
    live.classList.toggle("stale", s > 10);
    live.lastChild.textContent = D.lastOk ? (s > 10 ? `Last update ${s} s ago. Reconnecting…` : `Live. Updated ${s} s ago`) : "Connecting…";
  }, 1000);
  const poller = every(3000, load);
  const feedPoller = every(6000, feeds);

  // ------------------------------------------------------------ controls
  $("#f-syn").addEventListener("change", () => { poller.now(); feedPoller.now(); });
  $("#f-public").addEventListener("change", () => { document.body.classList.toggle("public", $("#f-public").checked); closeDrawer(); closePop(); setTimeout(() => D.map.fit(), 50); });
  $("#f-q").addEventListener("input", (e) => { D.q = e.target.value; queue(); });
  $("#f-state").addEventListener("change", (e) => { D.state = e.target.value; queue(); });
  $("#f-village").addEventListener("change", (e) => setVillage(e.target.value));
  $$("#f-prio button").forEach((b) => b.addEventListener("click", () => { D.prio = b.dataset.p; $$("#f-prio button").forEach((x) => x.setAttribute("aria-pressed", String(x === b))); queue(); }));
  $("#f-reset").addEventListener("click", () => { D.q = ""; D.state = ""; D.prio = ""; $("#f-q").value = ""; $("#f-state").value = ""; $$("#f-prio button").forEach((x, i) => x.setAttribute("aria-pressed", String(i === 0))); setVillage(""); });
  $("#btn-demo").addEventListener("click", (e) => { const p = $("#demo-pop"); p.hidden = !p.hidden; e.currentTarget.setAttribute("aria-expanded", String(!p.hidden)); });
  document.addEventListener("click", (e) => { if (!e.target.closest("#demo-menu")) $("#demo-pop").hidden = true; });
  $("#demo-add").addEventListener("click", async () => { $("#demo-pop").hidden = true; try { const r = await api("/api/demo/seed", { method: "POST" }); toast(`Added ${r.added} synthetic tickets.`, "ok"); poller.now(); feedPoller.now(); } catch (e) { toast(e.message, "err"); } });
  $("#demo-clear").addEventListener("click", async () => { $("#demo-pop").hidden = true; try { const r = await api("/api/demo/clear", { method: "POST" }); toast(`Removed ${r.removed} synthetic tickets. Real tickets were kept.`, "ok"); poller.now(); feedPoller.now(); } catch (e) { toast(e.message, "err"); } });
  $("#btn-csv").addEventListener("click", (e) => { e.preventDefault(); location.href = `/api/export/tickets.csv?synthetic=${syn()}`; });
})();
