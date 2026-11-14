# Build specification

The full build specification is `JalAwaaz_Build_Spec.md` in the claude.ai Project
"Jal Awaaz – AI-Powered Water Fault Reporting & Verification System".

If you are upgrading from 1.0, copy your existing `docs/SPEC.md` over this file:
it is the same specification, kept in the repository so `CLAUDE.md` and the docs can link to it.

Where this build differs from the specification, `docs/decisions.md` (D1–D36) records what
changed and why. The most visible ones:

- **D1 / D36** The web layer is Starlette, the toolkit FastAPI is built on, because FastAPI
  was not installed in the build environment. Routes, validation and the OpenAPI document are
  equivalent; see `docs/API.md`.
- **D22–D28** Gnani API changes since the specification was written (Prisma `topic`,
  `previous_text`, `substitution_map`; Timbre SSE streaming, mp3 output, mu-law telephone audio,
  numbers spoken as words) and Evon JSON mode.
- **D29–D35** The hand-built map, removal of fabricated numbers from the UI, the held-out
  evaluation set, two extraction fixes, the demo data menu and auto-listen on the phone.
