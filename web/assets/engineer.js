/* Engineer queue. One tap to acknowledge; "Report fix" asks for confirmation and explains that only the
   caller can close the ticket. Polls every 3 s so a reopened ticket appears without a reload. */
(async function () {
  "use strict";
  const { $, $$, h, icon, api, toast, label, stateChip, prio, when, ago, dur, until, every } = JA;
  const me = await JA.me().catch(() => ({}));
  JA.topbar("/engineer", me.role);
  const E = { tickets: [], tab: (location.hash.match(/tab=(\w+)/) || [])[1] || "todo", lastOk: 0, flash: null, seen: new Map() };
  const focusId = +((location.hash.match(/#t(\d+)/) || [])[1] || 0);
  const NOTE_CHIPS = ["Handpump washer and valve replaced", "Pipeline leak repaired", "Motor starter replaced", "Tank cleaned and chlorinated", "Power restored, motor running", "Flow tested for 10 minutes"];

  const bucket = (t) => (["NEW", "ACKED", "REOPENED"].includes(t.state) ? "todo" : t.state === "FIX_CLAIMED" ? "wait" : "done");
  function sorted(rows) {
    return rows.slice().sort((a, b) => a.priority - b.priority || (a.sla_due_at || "~").localeCompare(b.sla_due_at || "~") || a.created_at.localeCompare(b.created_at));
  }

  function slaPill(t) {
    if (!t.sla_due_at) return null;
    const m = until(t.sla_due_at);
    if (m < 0) return h("span.sla.over", { html: icon("clock") }, `SLA passed ${dur(-m)} ago`);
    return h("span.sla" + (m < 60 ? ".soon" : ""), { html: icon("clock") }, `${t.state === "NEW" ? "Acknowledge" : "Fix"} within ${dur(m)}`);
  }

  function card(t) {
    const facts = [];
    if (t.duration_days != null) facts.push(h("span", { html: icon("calendar") }, `${t.duration_days} day${t.duration_days === 1 ? "" : "s"} without service`));
    if (t.households != null) facts.push(h("span", { html: icon("users") }, `${t.households} households`));
    if (t.drinking_source) facts.push(h("span", { html: icon("drop") }, "Drinking water"));
    const sym = (t.symptoms || []).filter((s) => s !== "none");
    if (sym.length) facts.push(h("span", { html: icon("alert") }, "Symptoms: " + sym.map((s) => JA.L.symptom[s] || s).join(", ")));
    const el = h("article.job.p" + t.priority, { id: "t" + t.id },
      h("div.job-top", prio(t.priority), h("h2", t.village), t.is_synthetic ? h("span.tag-syn", "synthetic") : null, h("span.ref", "#" + t.ref)),
      h("div.job-what", `${label("source", t.source_type) || "Water source not given"}: ${label("fault", t.fault) || "fault not given"}`),
      facts.length ? h("div.job-facts", facts) : null,
      h("div.row-wrap", stateChip(t.state), slaPill(t), h("span.small.muted", `Reported ${ago(t.created_at)}`)),
      h("p.why", { style: { marginTop: "10px" } }, h("b", `Why P${t.priority}: `), t.priority_reason),
      t.reopened_count ? h("div.alert", { html: icon("alert") }, h("span", `The caller said the last fix did not work (reopened ${t.reopened_count}x). Priority was raised.`)) : null,
      t.transcript ? h("details.words", h("summary", "What the caller said"), h("p.deva", t.transcript)) : null,
      t.notes ? h("details.words", h("summary", "Your notes"), h("p", { style: { whiteSpace: "pre-wrap", fontSize: "var(--s-sm)" } }, t.notes)) : null,
      actions(t));
    if (E.flash === t.id) el.classList.add("flash");
    return el;
  }

  function actions(t) {
    const nav = t.lat != null ? h("a.btn.btn-quiet.btn-lg", { href: `https://www.google.com/maps/dir/?api=1&destination=${t.lat},${t.lon}`, target: "_blank", rel: "noopener", html: icon("pin") + "Directions" }) : null;
    if (t.state === "NEW" || t.state === "REOPENED")
      return h("div.actions", h("button.btn.btn-lg", { type: "button", onclick: (e) => act(t, "ack", e.currentTarget) }, h("span", { html: icon("check") }), "Acknowledge"), nav);
    if (t.state === "ACKED")
      return h("div.actions", h("button.btn.btn-haldi.btn-lg", { type: "button", onclick: () => fixSheet(t) }, h("span", { html: icon("wrench") }), "Report fix"),
        h("button.btn.btn-quiet.btn-lg", { type: "button", onclick: () => noteSheet(t) }, h("span", { html: icon("note") }), "Add note"), nav);
    if (t.state === "FIX_CLAIMED") {
      const next = t.next_verify_at ? until(t.next_verify_at) : null;
      return h("div.wait-note", { html: icon("phone") }, h("span", `Fix reported ${ago(t.fix_claimed_at)}. Jal Awaaz ` +
        (next != null && next > 0 ? `calls the caller in ${dur(next)}` : "is calling the caller now") + `. Attempt ${t.verify_attempts} of 3.`));
    }
    if (t.state === "VERIFIED") return h("div.closed-line", stateChip("VERIFIED"), `Caller confirmed ${when(t.verified_at)}.`);
    return h("div.closed-line", stateChip("UNVERIFIED"), "No answer after 3 verification calls. Not counted as fixed.");
  }

  async function act(t, what, btn, note) {
    if (btn) btn.disabled = true;
    try {
      const r = await api(`/api/tickets/${t.id}/${what}`, { method: "POST", json: note !== undefined ? { note } : {} });
      E.flash = t.id;
      toast(what === "ack" ? `Acknowledged #${t.ref}.` : what === "fix-claimed" ? `Fix reported for #${t.ref}. The caller will be called to confirm.` : "Note saved.", "ok");
      if (what === "fix-claimed") E.tab = "wait";
      await load();
      return r;
    } catch (e) { toast(e.message, "err"); if (btn) btn.disabled = false; }
  }

  function sheet(content) {
    const scrim = h("div.scrim");
    const sh = h("div.sheet", { role: "dialog", "aria-modal": "true" }, content);
    const close = () => { scrim.remove(); sh.remove(); document.removeEventListener("keydown", esc); };
    const esc = (e) => { if (e.key === "Escape") close(); };
    scrim.addEventListener("click", close);
    document.addEventListener("keydown", esc);
    document.body.append(scrim, sh);
    return { close, el: sh };
  }

  function noteArea(t) {
    const ta = h("textarea.input", { maxlength: 500, placeholder: "Parts replaced, flow tested, chlorination…", "aria-label": "Note" });
    const chips = h("div.chips", NOTE_CHIPS.map((c) => h("button", { type: "button", onclick: () => { ta.value = (ta.value ? ta.value + "; " : "") + c; ta.focus(); } }, c)));
    return { ta, chips };
  }

  function fixSheet(t) {
    const { ta, chips } = noteArea(t);
    const s = sheet([
      h("h2", `Report the fix for #${t.ref}`),
      h("p.lede", `This does not close the ticket. Jal Awaaz will call the person who reported it and ask whether the ${label("source", t.source_type).toLowerCase() || "water source"} in ${t.village} works. Only their “yes” closes it; a “no” reopens it at higher priority.`),
      h("label.small", { style: { fontWeight: 600 } }, "What did you do? (optional)"), chips, ta,
      h("div.actions", h("button.btn.btn-haldi.btn-lg", { type: "button", onclick: async (e) => { e.currentTarget.disabled = true; await act(t, "fix-claimed", null, ta.value.trim()); s.close(); } }, "Report fix and request the call"),
        h("button.btn.btn-quiet.btn-lg", { type: "button", onclick: () => s.close() }, "Cancel"))]);
    s.el.querySelector("button.btn-haldi").focus();
  }
  function noteSheet(t) {
    const { ta, chips } = noteArea(t);
    const s = sheet([h("h2", `Note on #${t.ref}`), chips, ta,
      h("div.actions", h("button.btn.btn-lg", { type: "button", onclick: async () => { if (!ta.value.trim()) return s.close(); await act(t, "note", null, ta.value.trim()); s.close(); } }, "Save note"),
        h("button.btn.btn-quiet.btn-lg", { type: "button", onclick: () => s.close() }, "Cancel"))]);
    ta.focus();
  }

  function render() {
    const groups = { todo: [], wait: [], done: [] };
    for (const t of E.tickets) groups[bucket(t)].push(t);
    for (const k of Object.keys(groups)) $("#n-" + k).textContent = String(groups[k].length);
    $$(".tabs button").forEach((b) => b.setAttribute("aria-selected", String(b.dataset.tab === E.tab)));
    const box = $("#jobs"); box.innerHTML = "";
    const rows = E.tab === "done" ? groups.done.sort((a, b) => (b.verified_at || b.unverified_at || "").localeCompare(a.verified_at || a.unverified_at || "")) : sorted(groups[E.tab]);
    if (!rows.length) {
      const msg = { todo: ["Nothing to do", "New complaints appear here as soon as a caller confirms the read-back."],
        wait: ["No fix waiting for a caller", "After you report a fix, the ticket waits here until the caller answers the verification call."],
        done: ["Nothing closed yet", "Tickets the caller confirmed, or that got no answer after three calls, are listed here."] }[E.tab];
      box.append(h("div.panel", h("div.empty", h("h3", msg[0]), msg[1])));
    }
    rows.forEach((t) => box.append(card(t)));
    E.flash = null;
  }

  async function load() {
    const syn = $("#f-syn").checked ? "1" : "0";
    E.tickets = await api(`/api/tickets?synthetic=${syn}`);
    for (const t of E.tickets) {                        // tell the engineer when a caller reopens a ticket
      const before = E.seen.get(t.id);
      if (before && before !== t.state && t.reopened_count && t.state === "ACKED" && before === "FIX_CLAIMED") toast(`#${t.ref} ${t.village}: the caller says it is still broken. Reopened at P${t.priority}.`, "err");
      E.seen.set(t.id, t.state);
    }
    E.lastOk = Date.now();
    if (!document.querySelector(".sheet")) render();
  }

  $$(".tabs button").forEach((b) => b.addEventListener("click", () => { E.tab = b.dataset.tab; history.replaceState(null, "", "#tab=" + E.tab); render(); }));
  $("#f-syn").addEventListener("change", () => poll.now());
  setInterval(() => {
    const s = Math.round((Date.now() - E.lastOk) / 1000);
    $("#live").classList.toggle("stale", s > 10);
    $("#live").lastChild.textContent = E.lastOk ? (s > 10 ? "Reconnecting…" : "Live") : "Connecting…";
  }, 1000);
  const poll = every(3000, load);
  if (focusId) setTimeout(() => { const el = document.getElementById("t" + focusId); if (el) { el.scrollIntoView({ block: "center" }); el.classList.add("flash"); } }, 900);
})();
