/* Villager phone: missed call -> simulated callback -> voice conversation -> ticket -> verification call.
   Audio flow: the mic opens after the assistant finishes speaking and closes when the caller pauses
   (voice activity detection), like a real call. Tap the talk button to start or stop by hand, or hold
   it down to talk; or type. Recordings go to the server and are deleted after transcription. */
(function () {
  "use strict";
  const { $, $$, h, icon, api, toast, label, every } = JA;

  // ------------------------------------------------------------ villager-language strings
  const UI = {
    mr: {
      title: "पाण्याची तक्रार नोंदवा", step1: "मिस्ड कॉल द्या", step2: "जल आवाज परत फोन करेल, तक्रार ऐकेल आणि वाचून दाखवेल", step3: "दुरुस्तीनंतर पुन्हा फोन: पाणी आले का?", sub: "मिस्ड कॉल द्या. जल आवाज तुम्हाला परत फोन करेल आणि तुमची तक्रार ऐकेल.",
      missed: "मिस्ड कॉल द्या", free: "मोफत. फोन आम्ही करतो.", mine: "माझ्या तक्रारी",
      tel: "फोन-लाईनचा आवाज (8 kHz)", ai: "हा एआय सहायक आहे. हा स्वतंत्र प्रायोगिक प्रकल्प आहे, सरकारी सेवा नाही. तुमचा आवाज साठवला जात नाही.",
      wait: "जल आवाज थोड्याच वेळात फोन करेल", waitSub: "फोन जवळ ठेवा.", cancel: "रद्द करा",
      ringReport: "परत फोन (कॉलबॅक)", ringVerify: "दुरुस्ती तपासणी कॉल", ringSubR: "तुमच्या मिस्ड कॉलला उत्तर", ringSubV: "तक्रार क्रमांक {ref}: पाणी आले का?",
      answer: "उचला", decline: "नाकारा", talk: "बोला", stop: "थांबवा", listening: "ऐकत आहे… बोला", thinking: "समजून घेत आहे…",
      speaking: "जल आवाज बोलत आहे", tap: "बोलण्यासाठी बटण दाबा", send: "पाठवा", typeHint: "उत्तर लिहा", auto: "बोलणे संपल्यावर आपोआप ऐका",
      yes: "हो", no: "नाही", heard: "तुम्ही म्हणालात:", back: "मुख्य पानावर",
      ticketTitle: "तक्रार नोंदवली", ticketNo: "तक्रार क्रमांक", next1: "इंजिनिअरला कळवले आहे.", next2: "दुरुस्तीनंतर आम्ही फोन करून विचारू: पाणी आले का?",
      next3: "तुम्ही हो म्हणाल तेव्हाच तक्रार बंद होईल.",
      verifiedTitle: "धन्यवाद! पाणी आल्याची नोंद झाली", verifiedText: "तक्रार बंद केली आहे.",
      reopenedTitle: "तक्रार पुन्हा उघडली", reopenedText: "प्राधान्य वाढवले आहे आणि इंजिनिअरला पुन्हा कळवले आहे.",
      handoffTitle: "तक्रार नोंदवली नाही", handoffText: "पूर्ण माहिती मिळाली नाही. एक व्यक्ती तुम्हाला फोन करेल.",
      noAnswerTitle: "उत्तर समजले नाही", noAnswerText: "आम्ही नंतर पुन्हा फोन करू.",
      endedTitle: "कॉल संपला", endedText: "तक्रार नोंदवली नाही. पुन्हा मिस्ड कॉल देऊ शकता.",
      none: "अजून कोणतीही तक्रार नाही.", micDenied: "मायक्रोफोन बंद आहे. उत्तर लिहू शकता.",
    },
    hi: {
      title: "पानी की शिकायत दर्ज करें", step1: "मिस्ड कॉल दें", step2: "जल आवाज वापस फ़ोन करेगा, शिकायत सुनेगा और पढ़कर सुनाएगा", step3: "मरम्मत के बाद फिर फ़ोन: क्या पानी आया?", sub: "मिस्ड कॉल दीजिए. जल आवाज आपको वापस फ़ोन करेगा और आपकी शिकायत सुनेगा.",
      missed: "मिस्ड कॉल दें", free: "मुफ़्त. फ़ोन हम करते हैं.", mine: "मेरी शिकायतें",
      tel: "फ़ोन-लाइन जैसी आवाज़ (8 kHz)", ai: "यह एआई सहायक है. यह एक स्वतंत्र प्रायोगिक प्रोजेक्ट है, सरकारी सेवा नहीं. आपकी आवाज़ सेव नहीं होती.",
      wait: "जल आवाज थोड़ी देर में फ़ोन करेगा", waitSub: "फ़ोन पास रखें.", cancel: "रद्द करें",
      ringReport: "वापस कॉल (कॉलबैक)", ringVerify: "मरम्मत जाँच कॉल", ringSubR: "आपकी मिस्ड कॉल का जवाब", ringSubV: "शिकायत क्रमांक {ref}: क्या पानी आया?",
      answer: "उठाएँ", decline: "मना करें", talk: "बोलिए", stop: "रोकें", listening: "सुन रहे हैं… बोलिए", thinking: "समझ रहे हैं…",
      speaking: "जल आवाज बोल रहा है", tap: "बोलने के लिए बटन दबाएँ", send: "भेजें", typeHint: "जवाब लिखें", auto: "बोलना ख़त्म होने पर अपने-आप सुनें",
      yes: "हाँ", no: "नहीं", heard: "आपने कहा:", back: "मुख्य पेज पर",
      ticketTitle: "शिकायत दर्ज हो गई", ticketNo: "शिकायत क्रमांक", next1: "इंजीनियर को बता दिया गया है.", next2: "मरम्मत के बाद हम फ़ोन करके पूछेंगे: क्या पानी आया?",
      next3: "आपके हाँ कहने पर ही शिकायत बंद होगी.",
      verifiedTitle: "धन्यवाद! पानी आने की पुष्टि हुई", verifiedText: "शिकायत बंद कर दी गई है.",
      reopenedTitle: "शिकायत फिर से खोली गई", reopenedText: "प्राथमिकता बढ़ा दी गई है और इंजीनियर को फिर बताया गया है.",
      handoffTitle: "शिकायत दर्ज नहीं हुई", handoffText: "पूरी जानकारी नहीं मिली. एक व्यक्ति आपको फ़ोन करेगा.",
      noAnswerTitle: "जवाब समझ नहीं आया", noAnswerText: "हम बाद में फिर फ़ोन करेंगे.",
      endedTitle: "कॉल ख़त्म", endedText: "शिकायत दर्ज नहीं हुई. आप फिर से मिस्ड कॉल दे सकते हैं.",
      none: "अभी कोई शिकायत नहीं.", micDenied: "माइक्रोफ़ोन बंद है. आप जवाब लिख सकते हैं.",
    },
    hinglish: {
      title: "Paani ki complaint darj karein", step1: "Missed call dein", step2: "Jal Awaaz call back karega, problem sunega aur padhkar sunayega", step3: "Repair ke baad phir call: kya paani aaya?", sub: "Missed call dijiye. Jal Awaaz aapko call back karega aur aapki problem sunega.",
      missed: "Missed call dein", free: "Free. Call hum karte hain.", mine: "Meri complaints",
      tel: "Phone-line jaisi awaaz (8 kHz)", ai: "Yeh AI assistant hai. Yeh ek independent prototype hai, sarkari service nahi. Aapki awaaz save nahi hoti.",
      wait: "Jal Awaaz thodi der mein call karega", waitSub: "Phone paas rakhiye.", cancel: "Cancel",
      ringReport: "Call back", ringVerify: "Repair check call", ringSubR: "Aapki missed call ka jawab", ringSubV: "Complaint {ref}: kya paani aaya?",
      answer: "Uthayein", decline: "Mana karein", talk: "Boliye", stop: "Rokein", listening: "Sun rahe hain… boliye", thinking: "Samajh rahe hain…",
      speaking: "Jal Awaaz bol raha hai", tap: "Bolne ke liye button dabayein", send: "Bhejein", typeHint: "Jawab likhiye", auto: "Bolna khatam hone par khud sunein",
      yes: "Haan", no: "Nahi", heard: "Aapne kaha:", back: "Home",
      ticketTitle: "Complaint darj ho gayi", ticketNo: "Complaint number", next1: "Engineer ko bata diya gaya hai.", next2: "Repair ke baad hum call karke poochhenge: kya paani aaya?",
      next3: "Aapke haan kehne par hi complaint band hogi.",
      verifiedTitle: "Thank you! Paani aane ki confirmation ho gayi", verifiedText: "Complaint band kar di gayi hai.",
      reopenedTitle: "Complaint phir se kholi gayi", reopenedText: "Priority badha di gayi hai aur engineer ko phir bataya gaya hai.",
      handoffTitle: "Complaint darj nahi hui", handoffText: "Poori detail nahi mili. Ek vyakti aapko call karega.",
      noAnswerTitle: "Jawab samajh nahi aaya", noAnswerText: "Hum baad mein phir call karenge.",
      endedTitle: "Call khatam", endedText: "Complaint darj nahi hui. Aap phir se missed call de sakte hain.",
      none: "Abhi koi complaint nahi.", micDenied: "Microphone band hai. Aap jawab likh sakte hain.",
    },
  };
  const VOICE_LANG = { mr: "mr-IN", hi: "hi-IN", hinglish: "hi-IN" };
  const LABEL_LANG = { mr: "mr", hi: "hi", hinglish: "hi" };

  // ------------------------------------------------------------ state
  const S = {
    device: localStorage.getItem("ja_device") || (crypto.randomUUID ? crypto.randomUUID() : "dev-" + Math.random().toString(36).slice(2) + Date.now()),
    lang: localStorage.getItem("ja_lang") || "mr",
    status: null, session: null, mode: null, ticketId: null, ticketRef: null, callLang: null,
    expecting: null, state: null, lastAudio: null, lastSpeech: "", done: null, timerStart: 0,
    stream: null, ctx: null, analyser: null, rec: null, chunks: [], mime: "", listening: false, holding: false,
    busy: false, ringer: null, waitTimer: null, poller: null, report: {},
  };
  localStorage.setItem("ja_device", S.device);
  const T = (k, vars) => { let s = (UI[S.callLang || S.lang] || UI.mr)[k] || UI.mr[k] || k; for (const [a, b] of Object.entries(vars || {})) s = s.replace("{" + a + "}", b); return s; };
  const voice = $("#voice");

  // ------------------------------------------------------------ screens
  function show(id) {
    $$("[data-screen]").forEach((s) => (s.hidden = s.id !== id));
    $("#device").classList.toggle("dark", id === "s-ring");
    if (id === "s-home" || id === "s-wait") ensurePolling();
  }
  function applyLang() {
    const l = S.callLang || S.lang;
    document.documentElement.lang = l === "hinglish" ? "en" : l;
    $$("[data-t]").forEach((el) => (el.textContent = T(el.dataset.t)));
    $$(".langs button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.lang === S.lang)));
    $("#typed").placeholder = T("typeHint");
    setTalkLabel();
  }
  function iconsInit() {
    $(".call-ic").innerHTML = icon("phone");
    $$(".ic-phone").forEach((e) => (e.innerHTML = icon("phone")));
    $$(".ic-hang").forEach((e) => (e.innerHTML = icon("hangup")));
    $("#btn-replay").innerHTML = icon("replay");
    $("#btn-type").innerHTML = icon("keyboard");
    $("#btn-mine-back").innerHTML = icon("chevron");
    $("#btn-mine-back").firstChild.style.transform = "rotate(180deg)";
    $(".talk-ic").innerHTML = icon("mic");
  }
  const tick = () => ($("#clock").textContent = new Date().toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", hour12: false }));
  tick(); setInterval(tick, 1000);

  // ------------------------------------------------------------ incoming calls
  function ensurePolling() {
    if (S.poller) return;
    S.poller = every(2000, async () => {
      if (S.session || !$("#s-ring").hidden) return;
      const r = await api("/api/poll?device=" + encodeURIComponent(S.device));
      if (r.incoming) ring(r);
      else if (r.next && !$("#s-wait").hidden) setWait(r.next.in_sec);
    });
  }
  function ring(r) {
    S.mode = r.incoming === "verification" ? "verify" : "report";
    S.ticketId = r.ticket_id || null;
    S.ticketRef = r.ticket_ref || null;
    S.callLang = S.mode === "verify" && r.lang ? r.lang : null;
    applyLang();
    clearInterval(S.waitTimer);
    $("#ring-kind").textContent = S.mode === "verify" ? T("ringVerify") : T("ringReport");
    $("#ring-sub").textContent = S.mode === "verify" ? T("ringSubV", { ref: S.ticketRef || "" }) : T("ringSubR");
    show("s-ring");
    startRinger();
    if (navigator.vibrate) navigator.vibrate([400, 250, 400, 250, 400]);
    rail.event(S.mode === "verify" ? `Verification call ringing for ticket ${S.ticketRef}` : "Callback ringing", "Simulated call");
    const tel = $("#tel").checked;
    S.preSession = api("/api/session", { method: "POST", json: { device: S.device, mode: S.mode, lang: S.callLang || S.lang, ticket_id: S.ticketId, telephone: tel } });
    S.preSession.then((res) => {
      if (res && res.audio_url) {
        const link = document.createElement("link");
        link.rel = "preload"; link.as = "fetch"; link.href = res.audio_url;
        document.head.appendChild(link);
      }
    }).catch(() => {});
  }
  function startRinger() {
    stopRinger();
    const ctx = audioCtx();
    if (!ctx) return;
    let on = true;
    const beep = () => {
      if (!on) return;
      const g = ctx.createGain(); g.gain.value = 0.0001; g.connect(ctx.destination);
      [440, 480].forEach((f) => { const o = ctx.createOscillator(); o.frequency.value = f; o.connect(g); o.start(); o.stop(ctx.currentTime + 1.6); });
      g.gain.exponentialRampToValueAtTime(0.06, ctx.currentTime + 0.05);
      g.gain.setValueAtTime(0.06, ctx.currentTime + 1.5);
      g.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + 1.6);
    };
    beep();
    const t = setInterval(beep, 3200);
    S.ringer = () => { on = false; clearInterval(t); };
  }
  function stopRinger() { if (S.ringer) S.ringer(); S.ringer = null; if (navigator.vibrate) navigator.vibrate(0); }
  function audioCtx() {
    try { if (!S.ctx) S.ctx = new (window.AudioContext || window.webkitAudioContext)(); if (S.ctx.state === "suspended") S.ctx.resume(); return S.ctx; }
    catch (e) { return null; }
  }

  // ------------------------------------------------------------ missed call
  async function missedCall() {
    audioCtx();                                           // unlock audio on this tap (iOS/Chrome autoplay rules)
    unlockVoice();
    try {
      const r = await api("/api/missed-call", { method: "POST", json: { device: S.device } });
      rail.reset();
      rail.event("Missed call placed. A callback is queued on the server.", "Simulated");
      show("s-wait");
      setWait(r.callback_in_sec);
    } catch (e) { toast(e.message, "err"); }
  }
  function setWait(sec) {
    clearInterval(S.waitTimer);
    const total = Math.max(1, sec);
    let left = sec;
    const arc = $("#wait-arc");
    const paint = () => { $("#wait-n").textContent = Math.max(0, left); arc.style.strokeDashoffset = String(327 * (1 - Math.max(0, left) / total)); };
    paint();
    S.waitTimer = setInterval(() => { left--; paint(); if (left <= 0) { clearInterval(S.waitTimer); S.poller && S.poller.now(); } }, 1000);
  }

  function unlockVoice() {
    // play a silent clip inside the user gesture so later replies can autoplay
    try { voice.src = "data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQAAAAA="; voice.play().catch(() => {}); } catch (e) {}
  }

  // ------------------------------------------------------------ answering
  async function answer() {
    stopRinger();
    audioCtx();
    unlockVoice();
    const tel = $("#tel").checked;
    const pre = S.preSession;
    S.preSession = null;
    try {
      const r = pre ? await pre : await api("/api/session", { method: "POST", json: { device: S.device, mode: S.mode, lang: S.callLang || S.lang, ticket_id: S.ticketId, telephone: tel } });
      S.session = r.session_id; S.done = null; S.report = {};
      S.callLang = r.lang; applyLang();
      $("#call-kind").textContent = S.mode === "verify" ? T("ringVerify") : T("ringReport");
      $("#tel-on").hidden = !r.telephone;
      $("#heard").textContent = ""; $("#caption").textContent = "";
      $("#typebox").hidden = S.sttOn !== false;            // keep typing open when speech recognition is off
      show("s-call");
      startTimer();
      rail.slots(S.mode === "report" ? {} : null);
      handleReply(r, null);
      prepareMic();
    } catch (e) { toast(e.message, "err"); show("s-home"); }
  }
  async function decline() {
    stopRinger();
    S.preSession = null;
    try { await api("/api/decline", { method: "POST", json: { device: S.device, ticket_id: S.ticketId } }); } catch (e) {}
    rail.event("Call declined by the caller.", "");
    S.callLang = null; applyLang(); show("s-home");
  }
  function startTimer() {
    S.timerStart = Date.now();
    clearInterval(S.callTimer);
    S.callTimer = setInterval(() => {
      const s = Math.floor((Date.now() - S.timerStart) / 1000);
      $("#timer").textContent = String(Math.floor(s / 60)).padStart(2, "0") + ":" + String(s % 60).padStart(2, "0");
    }, 500);
  }

  // ------------------------------------------------------------ microphone and voice activity detection
  function pickMime() {
    const c = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/ogg;codecs=opus"];
    return (window.MediaRecorder && c.find((m) => MediaRecorder.isTypeSupported(m))) || "";
  }
  async function prepareMic() {
    if (S.stream) return true;
    if (!navigator.mediaDevices || !window.MediaRecorder) { micUnavailable(); return false; }
    try {
      S.stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true, channelCount: 1 } });
      const ctx = audioCtx();
      const src = ctx.createMediaStreamSource(S.stream);
      S.analyser = ctx.createAnalyser(); S.analyser.fftSize = 1024; src.connect(S.analyser);
      S.mime = pickMime();
      return true;
    } catch (e) { micUnavailable(); return false; }
  }
  function micUnavailable() {
    $("#btn-talk").disabled = true;
    $("#typebox").hidden = false;
    toast(T("micDenied"), "err");
  }
  function level() {
    if (!S.analyser) return 0;
    const buf = new Float32Array(S.analyser.fftSize);
    S.analyser.getFloatTimeDomainData(buf);
    let sum = 0; for (const v of buf) sum += v * v;
    return Math.sqrt(sum / buf.length);
  }

  async function startListening(manual) {
    if (S.listening || S.busy || !S.session || S.done) return;
    if (!(await prepareMic())) return;
    stopVoice();
    S.chunks = [];
    try { S.rec = new MediaRecorder(S.stream, S.mime ? { mimeType: S.mime } : undefined); }
    catch (e) { micUnavailable(); return; }
    S.rec.ondataavailable = (e) => e.data && e.data.size && S.chunks.push(e.data);
    S.rec.start(250);
    S.listening = true;
    setMode("listening");
    const cfg = S.status || {};
    const maxMs = (cfg.max_utterance_seconds || 25) * 1000, silentMs = (cfg.silence_seconds || 6) * 1000;
    const t0 = performance.now();
    let floor = null, heard = false, lastVoice = t0;
    const loop = () => {
      if (!S.listening) return;
      const now = performance.now(), lv = level();
      if (now - t0 < 300) floor = floor == null ? lv : Math.min(floor, lv) || lv;
      const thr = Math.max(0.018, (floor || 0.01) * 2.6);
      if (lv > thr) { heard = true; lastVoice = now; }
      $(".orb-core").style.transform = `scale(${1 + Math.min(0.35, lv * 6)})`;
      if (!S.holding) {
        if (heard && now - lastVoice > 1300) return stopListening("pause");
        if (!heard && now - t0 > silentMs && !manual) return stopListening("silence");
      }
      if (now - t0 > maxMs) return stopListening("max");
      requestAnimationFrame(loop);
    };
    requestAnimationFrame(loop);
    S._heard = () => heard;
  }
  function stopListening(reason) {
    if (!S.listening) return;
    S.listening = false;
    $(".orb-core").style.transform = "";
    const heard = S._heard ? S._heard() : true;
    const rec = S.rec;
    rec.onstop = () => {
      const blob = new Blob(S.chunks, { type: S.mime || "audio/webm" });
      if (reason === "silence" && !heard) sendTurn({ text: "", silent: true });
      else if (reason === "cancel") setMode("idle");
      else sendTurn({ blob });
    };
    try { rec.stop(); } catch (e) {}
  }

  // talk button: tap toggles, press-and-hold talks while held
  let downAt = 0;
  function talkDown(e) {
    e.preventDefault();
    if (S.busy || S.done) return;
    downAt = performance.now();
    if (S.listening) { stopListening("tap"); downAt = 0; return; }
    S.holding = true;
    startListening(true);
  }
  function talkUp() {
    if (!downAt) return;
    const held = performance.now() - downAt;
    downAt = 0;
    if (held > 450 && S.listening) { S.holding = false; stopListening("release"); }
    else S.holding = false;                             // short tap: keep listening until the caller pauses
  }

  // ------------------------------------------------------------ turns
  async function sendTurn({ blob, text, silent }) {
    if (!S.session) return;
    S.busy = true;
    setMode("thinking");
    const fd = new FormData();
    fd.append("session_id", S.session);
    if (blob) fd.append("audio", blob, "turn." + ((S.mime || "").includes("mp4") ? "m4a" : (S.mime || "").includes("ogg") ? "ogg" : "webm"));
    else fd.append("text", text);
    if (text && !silent) rail.me(text, ["typed"]);
    try {
      const r = await api("/api/turn", { method: "POST", form: fd });
      if (blob) rail.me(r.transcript || "(nothing recognised)", turnBadges(r));
      if (r.transcript) $("#heard").innerHTML = "";
      if (r.transcript) $("#heard").append(h("b", T("heard") + " "), r.transcript);
      handleReply(r, r);
    } catch (e) {
      S.busy = false;
      setMode("idle");
      toast(e.message, "err");
      if (e.code === "no_session" || e.code === "call_over") endCall({ outcome: "ended" });
    }
  }
  function turnBadges(r) {
    const out = [];
    const p = r.providers || {};
    if (p.stt === "prisma") out.push(`Prisma ${r.stt && r.stt.detected ? r.stt.detected : ""}`.trim());
    else if (p.stt) out.push(p.stt);
    if (r.stt && r.stt.context && r.stt.context.length) out.push("context: " + r.stt.context.join(", "));
    if (p.llm) out.push(p.llm === "evon" ? "Evon" : p.llm.includes("rules") ? "rules" : p.llm);
    return out;
  }

  function handleReply(r, turn) {
    S.busy = false;
    S.state = r.state; S.expecting = r.expecting || null;
    (r.notices || []).forEach((n) => toast(n, "err"));
    $("#caption").textContent = r.reply_text;
    rail.ai(r.reply_text, [r.audio_url ? "Timbre" : r.browser_voice ? "browser voice" : "text only"]);
    if (r.report) rail.slots(r.report);
    if (turn) rail.timings(r);
    renderQuick();
    if (r.done) S.done = r;
    if (r.offer_text) $("#typebox").hidden = false;
    speak(r);
  }

  function renderQuick() {
    const q = $("#quick");
    q.innerHTML = "";
    const yn = S.state === "CONFIRM" || S.state === "VILLAGE_CONFIRM" || S.state === "VERIFY" || S.expecting === "drinking_source" || S.expecting === "health_symptoms";
    if (!yn || S.done) { q.hidden = true; return; }
    q.hidden = false;
    q.append(h("button.yes", { type: "button", onclick: () => quickSay(T("yes")) }, T("yes")),
      h("button.no", { type: "button", onclick: () => quickSay(T("no")) }, T("no")));
  }
  function quickSay(t) { if (S.busy) return; if (S.listening) stopListening("cancel"); stopVoice(); sendTurn({ text: t }); }

  // ------------------------------------------------------------ speaking
  function speak(r) {
    stopVoice();
    S.lastAudio = r.audio_url || null; S.lastSpeech = r.speech_text || r.reply_text;
    $("#btn-replay").disabled = !S.lastAudio && !r.browser_voice;
    setMode("speaking");
    if (r.audio_url) {
      voice.src = r.audio_url;
      voice.onended = afterSpeech;
      voice.onerror = () => { toast("The voice could not be played. The reply is on screen.", "err"); afterSpeech(); };
      const p = voice.play();
      if (p) p.catch(() => { toast("Tap the replay button to hear the reply.", ""); setMode("idle"); });
      return;
    }
    if (r.browser_voice && "speechSynthesis" in window) {
      const u = new SpeechSynthesisUtterance(S.lastSpeech);
      S.utter = u;
      u.lang = VOICE_LANG[S.callLang || S.lang] || "hi-IN";
      u.rate = 0.95;
      u.onend = afterSpeech; u.onerror = afterSpeech;
      speechSynthesis.speak(u);
      return;
    }
    setTimeout(afterSpeech, 1200);
  }
  function stopVoice() {
    // detach first: cancelling must not count as "finished speaking" (that would reset the mic state)
    voice.onended = null; voice.onerror = null;
    try { voice.pause(); } catch (e) {}
    if (S.utter) { S.utter.onend = null; S.utter.onerror = null; S.utter = null; }
    if ("speechSynthesis" in window) speechSynthesis.cancel();
  }
  function afterSpeech() {
    if (S.done) { setTimeout(() => endCall(S.done), 600); return; }
    setMode("idle");
    if ($("#auto").checked && $("#typebox").hidden) startListening(false);
  }
  function replay() {
    if (S.listening) stopListening("cancel");
    if (S.lastAudio) { stopVoice(); voice.src = S.lastAudio; voice.onended = afterSpeech; voice.play().catch(() => {}); setMode("speaking"); }
    else if (S.lastSpeech && "speechSynthesis" in window) speak({ browser_voice: true, speech_text: S.lastSpeech, reply_text: $("#caption").textContent });
  }

  function setMode(m) {
    $("#orb").dataset.mode = m;
    const ic = { speaking: "speaker", listening: "mic", thinking: "drop", idle: "mic" }[m];
    $("#orb-ic").innerHTML = icon(ic);
    $("#orb-state").textContent = m === "speaking" ? T("speaking") : m === "listening" ? T("listening") : m === "thinking" ? T("thinking") : T("tap");
    $("#btn-talk").classList.toggle("rec", m === "listening");
    $("#btn-talk").disabled = m === "thinking" || !!S.done;
    setTalkLabel();
  }
  function setTalkLabel() {
    const listening = $("#orb") && $("#orb").dataset.mode === "listening";
    $("#talk-t").textContent = listening ? T("stop") : T("talk");
    $(".talk-ic").innerHTML = icon(listening ? "stop" : "mic");
  }

  // ------------------------------------------------------------ end of call
  function endCall(r) {
    clearInterval(S.callTimer);
    if (S.listening) stopListening("cancel");
    stopVoice();
    const outcome = r.outcome || "ended";
    const badge = $("#end-badge");
    const next = $("#end-next");
    next.innerHTML = "";
    $("#end-ref").hidden = true;
    const set = (cls, ic, title, text) => { badge.className = "end-badge " + cls; badge.innerHTML = icon(ic); $("#end-title").textContent = title; $("#end-text").textContent = text || ""; };
    if (outcome === "ticket") {
      set("info", "check", T("ticketTitle"), "");
      $("#end-ref").hidden = false; $("#end-refnum").textContent = r.ticket_ref;
      [T("next1"), T("next2"), T("next3")].forEach((t) => next.append(h("li", h("span", { html: icon("check") }), t)));
      rail.event(`Ticket ${r.ticket_ref} created. The engineer was sent a (simulated) SMS.`, "Ticket");
    } else if (outcome === "verified") { set("ok", "check", T("verifiedTitle"), T("verifiedText")); rail.event("Caller said yes. Ticket VERIFIED and closed.", "Verified"); }
    else if (outcome === "reopened") { set("bad", "refresh", T("reopenedTitle"), T("reopenedText")); rail.event("Caller said no. Ticket REOPENED, priority raised.", "Reopened"); }
    else if (outcome === "no_answer") { set("warn", "clock", T("noAnswerTitle"), T("noAnswerText")); rail.event("No clear answer. The verification call will be retried.", ""); }
    else if (outcome === "handoff" || outcome === "error") { set("warn", "users", T("handoffTitle"), T("handoffText")); rail.event("Handed off to a person. No ticket was created.", ""); }
    else { set("warn", "phone", T("endedTitle"), S.mode === "verify" ? T("noAnswerText") : T("endedText")); }
    S.session = null; S.done = null;
    show("s-end");
    loadMine();
  }
  async function hangUp() {
    const wasDone = S.done;
    if (wasDone) return endCall(wasDone);
    rail.event("Caller hung up.", "");
    endCall({ outcome: "ended" });
  }

  // ------------------------------------------------------------ my complaints
  async function loadMine() {
    try {
      const rows = await api("/api/my-tickets?device=" + encodeURIComponent(S.device));
      $("#mine-count").textContent = rows.length ? String(rows.length) : "";
      const ul = $("#mine-list"); ul.innerHTML = "";
      const L2 = LABEL_LANG[S.lang];
      if (!rows.length) ul.append(h("li.muted", T("none")));
      rows.forEach((t) => ul.append(h("li",
        h("div.m-top", h("span.m-ref", t.ref), h("span.chip.st-" + t.state, label("state", t.state, L2))),
        h("div.m-what", [t.village, label("source", t.source_type, L2), label("fault", t.fault, L2)].filter(Boolean).join(", ")),
        h("div.m-when", JA.when(t.created_at)))));
    } catch (e) { /* status list is optional */ }
  }

  // ------------------------------------------------------------ rail (behind the call)
  const SLOT_ORDER = [["village", "Village"], ["source_type", "Water source"], ["fault", "Fault"], ["duration_days", "Days"],
    ["households_affected", "Households"], ["drinking_source", "Drinking water"], ["health_symptoms", "Symptoms"]];
  const rail = {
    reset() { $("#convo").innerHTML = ""; $("#timings").innerHTML = '<span class="muted small">No turn yet.</span>'; this.slots({}); },
    _add(cls, text, badges) {
      const empty = $("#convo .convo-empty"); if (empty) empty.remove();
      const li = h("li." + cls, h("div.who", cls === "ai" ? "Jal Awaaz" : cls === "me" ? "Caller" : "Event", (badges || []).filter(Boolean).map((b) => h("span.provider" + (cls === "ev" ? "" : ".on"), b))), text);
      $("#convo").append(li); li.scrollIntoView({ block: "nearest" });
    },
    ai(t, b) { this._add("ai", t, b); }, me(t, b) { this._add("me", t, b); },
    event(t, b) { this._add("ev", t, [b]); const li = $("#convo").lastChild; li.style.cssText = "font-size:13px;font-family:var(--body);color:var(--muted);padding:2px 0"; },
    slots(rep) {
      const dl = $("#slots"); const prev = S.report || {};
      dl.innerHTML = "";
      if (rep === null) { dl.append(h("dt", "Call"), h("dd", "Verification: the caller is asked if the water is running.")); return; }
      for (const [k, name] of SLOT_ORDER) {
        let v = rep[k];
        if (k === "village" && rep.village_matched) v = rep.village_matched + (rep.village_on_map ? "" : " (not on map)");
        if (k === "source_type") v = label("source", v);
        if (k === "fault") v = label("fault", v);
        if (k === "drinking_source") v = v === true ? "Yes" : v === false ? "No" : null;
        if (k === "health_symptoms") v = (v || []).filter((x) => x !== "none").map((x) => JA.L.symptom[x] || x).join(", ") || (v && v.includes("none") ? "None" : null);
        const isNew = v && JSON.stringify(prev[k]) !== JSON.stringify(rep[k]);
        dl.append(h("dt", name), h("dd" + (v == null || v === "" ? ".nil" : "") + (isNew ? ".new" : ""), v == null || v === "" ? "not yet" : String(v)));
      }
      S.report = rep;
    },
    timings(r) {
      const t = r.timings_ms || {};
      const box = $("#timings"); box.innerHTML = "";
      const cell = (v, l) => h("div", h("b", v == null ? "–" : v), h("span", l));
      box.append(cell(t.stt_ms ? (t.stt_ms / 1000).toFixed(2) + " s" : r.providers && r.providers.stt === "typed" ? "typed" : "–", "Speech to text"),
        cell(t.llm_ms ? Math.round(t.llm_ms) + " ms" : "rules", "Understanding"),
        cell(t.until_text_ms ? (t.until_text_ms / 1000).toFixed(2) + " s" : "–", "Until reply text"),
        cell(r.audio_url ? "streamed" : "–", "Voice"));
    },
  };

  // ------------------------------------------------------------ wire up
  async function init() {
    iconsInit();
    applyLang();
    try {
      S.status = await api("/api/status");
      const p = S.status.providers;
      const pill = (cls, t) => h("span.provider." + cls, t);
      $("#prov").append(
        p.stt.provider === "prisma" ? pill("on", "Speech: Prisma " + (p.stt.model || "")) : pill("off", "Speech: off, type instead"),
        p.tts.provider === "timbre" ? pill("on", "Voice: Timbre " + (p.tts.streaming ? "streamed" : "")) : pill("fallback", "Voice: browser"),
        p.llm.provider === "evon" ? pill("on", "Understanding: Evon") : pill("fallback", "Understanding: rules"),
        pill("off", S.status.demo_mode ? "Time compressed" : "Real timings"));
      $("#tel").checked = !!S.status.telephone_mode_default;
      S.sttOn = p.stt.provider === "prisma";
    } catch (e) { toast(e.message, "err"); }
    $$(".langs button").forEach((b) => b.addEventListener("click", () => { S.lang = b.dataset.lang; localStorage.setItem("ja_lang", S.lang); applyLang(); loadMine(); }));
    $("#btn-missed").addEventListener("click", missedCall);
    $("#btn-cancel").addEventListener("click", () => { clearInterval(S.waitTimer); show("s-home"); });
    $("#btn-answer").addEventListener("click", answer);
    $("#btn-decline").addEventListener("click", decline);
    $("#btn-hang").addEventListener("click", hangUp);
    $("#btn-replay").addEventListener("click", replay);
    $("#btn-type").addEventListener("click", () => { $("#typebox").hidden = !$("#typebox").hidden; if (!$("#typebox").hidden) { if (S.listening) stopListening("cancel"); $("#typed").focus(); } });
    $("#typebox").addEventListener("submit", (e) => { e.preventDefault(); const v = $("#typed").value.trim(); if (!v || S.busy) return; $("#typed").value = ""; stopVoice(); sendTurn({ text: v }); });
    const talk = $("#btn-talk");
    talk.addEventListener("pointerdown", talkDown);
    ["pointerup", "pointerleave", "pointercancel"].forEach((ev) => talk.addEventListener(ev, talkUp));
    talk.addEventListener("keydown", (e) => { if (e.key === " " || e.key === "Enter") { e.preventDefault(); S.listening ? stopListening("tap") : startListening(true); } });
    $("#btn-home").addEventListener("click", () => { S.callLang = null; applyLang(); show("s-home"); });
    $("#btn-mine").addEventListener("click", () => { loadMine(); show("s-mine"); });
    $("#btn-mine-back").addEventListener("click", () => show("s-home"));
    $("#auto").checked = localStorage.getItem("ja_auto") !== "0";
    $("#auto").addEventListener("change", () => localStorage.setItem("ja_auto", $("#auto").checked ? "1" : "0"));
    setMode("idle");
    show("s-home");
    loadMine();
    let role = null; try { role = (await JA.me()).role; } catch (e) {}
    JA.topbar("/phone", role);
  }
  init();
  window.JAPhone = { S, sendTurn, endCall };                 // exposed for the browser test suite
})();
