# User guide

## Villager: the phone (`/phone`)

1. **Choose your language**: मराठी, हिंदी or Hinglish. The screen and the assistant use it.
2. **Give a missed call** with the big button. It is free; Jal Awaaz calls you back. (In this demo the
   callback is simulated: the same page rings.)
3. **Answer.** The assistant first says it is an AI assistant and that this is a prototype, not a
   government service.
4. **Say what is wrong** in your own words: which village, which water source (handpump, tap, well,
   borewell, tank or tanker), what the problem is, for how many days, and how many houses are affected.
   You do not need to say everything at once; it asks one question at a time.
   - After the assistant speaks, the microphone opens by itself. Stop talking for a moment and it sends
     your answer.
   - Or tap the big **बोला / बोलिए** button to start, and tap again to stop. Or hold it while you speak.
   - The keyboard button lets you type instead. The **हो / नाही** buttons answer yes or no.
5. **Listen to the read-back** and say yes (हो / हाँ) if it is right, or no (नाही / नहीं) to correct it.
6. **Write down the complaint number.** It is spoken twice, digit by digit, and shown on the screen.
7. **Later, the phone rings again** after the engineer says it is fixed. Say yes only if water is really
   coming. If you say no, the complaint reopens and becomes more urgent.

"माझ्या तक्रारी / मेरी शिकायतें" shows the status of complaints made from this phone.
Your voice is not stored. Only the words, the details and the complaint number are kept.

The switch at the bottom of the home screen makes the call sound like a real phone line (8 kHz). It is for
testing that the system still understands phone-quality audio.

## Engineer: the queue (`/engineer`)

Sign in with the engineer PIN. Three tabs:

- **To do**: new and reopened tickets, most urgent first. Each card shows the village, the water source
  and fault, days without service, households, and **why it has this priority**. The pill shows how long
  you have before it escalates (or how long ago the SLA passed).
- **Awaiting caller**: you reported a fix; Jal Awaaz is calling the caller to check. Nothing to do.
- **Closed**: verified by the caller, or no answer after three calls (not counted as fixed).

Actions:
- **Acknowledge**: you have seen it and will act. Stops the "acknowledge" SLA from escalating.
- **Report fix**: tell Jal Awaaz the work is done. This **does not close** the ticket. Add what you did
  (quick chips for common repairs). The caller is called and only their "yes" closes the ticket.
- **Add note**: anything the next person should know.
- **Directions** opens the village in a maps app (only for villages with known coordinates).

A red banner on a card means the caller said the last fix did not work. A toast also appears when that
happens while you have the page open.

## District officer: the dashboard (`/dashboard`)

Sign in with the officer PIN (engineers can view it too).

- **Figure strip**: the **false-closure rate** (tickets reopened at least once ÷ tickets whose fix the
  caller answered), always with its n; open tickets and P1s; median time to acknowledge; median time from
  fix to the caller's yes; tickets awaiting the caller; tickets past their SLA.
- **Map**: one pin per village. The number is open tickets (or all tickets if none are open). Colour is the
  most urgent state: red open, yellow awaiting the caller, green verified, grey no answer. A rippling pin
  has a P1 or reopened ticket. A dashed ring marks a repeat failure (two or more reports on the same
  source within 30 days). Hollow dots are approximate positions. Click a pin for its numbers.
- **Tickets**: search and filter by state, priority and village. Click a row for the full record: why it
  has its priority, what was reported, where, the caller's words, the full timeline, every verification
  attempt and the SMS sent.
- **Last 14 days, What is breaking, Needs attention**: trends, the fault and source mix, SLA breaches,
  repeat failures and unanswered verifications.
- **Activity** and **SMS log**: the audit trail and the (simulated) messages.
- **Synthetic demo data** switch: include or hide the labelled synthetic tickets. **Public view** hides
  every individual record and shows aggregates only, for a screen others can see.
- **Export CSV**: tickets without caller identifiers or transcripts. **Demo data** (demo mode only): add or
  remove the 14 synthetic tickets; real tickets are never touched.

## Everyone: evaluation (`/metrics`)

What was measured, with n: how well the language layer understands complaints (held-out and regression
sets, every failing case listed), speech-recognition benchmarks once run, live latency of every Gnani
request this server made, and call outcomes. Staff also see the system status and can run the text
evaluation; officers can check the Gnani key.
