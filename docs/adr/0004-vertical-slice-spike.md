# 0004 — A vertical-slice spike, and the rules it suspends

**Status:** Accepted. The spike code is temporary and is overwritten story by story; this
record is permanent.

**Date:** 2026-08-15

## Context

The requirements baseline is complete and merged — 20 functional requirements, 10
non-functional ones, ten user stories with Gherkin acceptance criteria, and a traceability
matrix. No code existed.

Committing to ten story-sized pull requests on the strength of documents alone carries a
risk the documents cannot retire: that the upstream sources do not return what `BookInfo`
assumes. A story-first sequence would not discover this until US-05, five pull requests in,
with the endpoint and the generated types already built on the assumption.

The spike answers that question before the sequence starts. Its value is the answer, not
the code.

## Decision

Build the thinnest possible end-to-end path and keep nothing but what it teaches.

- `backend/app/sources.py` — two direct `httpx` calls. Open Library's `api/books` endpoint
  for title, authors and cover; Google Books' `volumes` endpoint for price and description.
- `backend/app/main.py` — FastAPI, `GET /api/books/{isbn}`, returning the real `BookInfo`
  from `backend/app/models.py`. Validation is 13 digits after stripping hyphens and spaces.
- `frontend/src/App.tsx` — a heading, an input, a Search button, and a table.
- `backend/tests/test_spike_smoke.py` — three tests against stubbed transports.

No LLM, no agent, no MCP, no checksum, no generated types.

**The spike's files sit at the paths the real implementation will use.** They are overwritten
by the stories, not deleted. No story should treat this code as a foundation to build on: it
is scaffolding that happens to occupy the right addresses.

## Rules this spike suspends

| CLAUDE.md rule | Status in the spike | Restored by |
|---|---|---|
| 1 — LLM never supplies facts from memory | **Not broken.** There is no LLM, so no fact can come from one. But the agent path is wholly unexercised, and rule 1's real test is whether it holds *with* a model in the loop. | US-05, US-06, US-07 |
| 2 — `BookInfo` is the single contract; frontend types are generated | **Broken.** `App.tsx` hand-writes the interface. | US-04 |
| 3 — a missing price is a designed state | **Not broken.** Null price renders "Not available". | — |
| 4 — every PR closes one story and updates traceability | **Broken.** This PR closes no story and touches code belonging to several. `docs/06-traceability.md` is deliberately left untouched — every row still reads "Not started", because nothing here is delivery. | Exemption, not a fix. Normal service resumes at US-01. |
| 5 — branch naming `feat/FR-XX-short-name` | **Broken.** The branch is `spike/vertical-slice`; no single FR owns this work. | Exemption, not a fix. |
| 6 — tests written from Gherkin, before implementation | **Broken.** `test_spike_smoke.py` was written after the code and from no scenario. It proves wiring, not requirements. | US-01 onward; each story rewrites its slice test-first. |
| 7 — no secrets in code | **Not broken.** No credentials are used at all. The backend URL is hardcoded in `App.tsx` — configuration, not a secret, but still wrong for anything shipped. | US-04 |

### Requirement gaps

Beyond the rules, the spike implements almost none of the requirements. Recorded so the gap
is not mistaken for progress: FR-02, FR-03, FR-04 (no checksum, no ISBN-10 — US-01);
FR-05 (no reason-naming inline errors — US-02); FR-09, FR-10, FR-11 (no agent, `sources`
assembled by hand — US-07); FR-14, FR-18 (no cover placeholder, no in-flight state — US-08);
FR-15, FR-16, FR-17 (one 404 stands in for three distinct states — US-10); FR-19 (US-04);
NFR-02 (US-02); NFR-04 (the table has `th` cells and the input a label, but nothing else —
US-02, US-08, US-10); NFR-06 (US-01 onward); NFR-08 (US-10).

## Consequences

### What the spike proved

The path works. `GET /api/books/9780132350884` returns "Clean Code" by Robert C. Martin with
a cover URL, end to end, in ~1.3 seconds against live sources — comfortably inside NFR-01's
5-second budget, though that measurement predates the agent, which will dominate it.

Open Library's `api/books` endpoint is the right choice over `/isbn/{isbn}.json`: it returns
author *names* and a cover URL inline, where the latter returns author keys requiring a
further request each.

### Two findings that change the plan

**1. Google Books rejects unauthenticated requests at this volume.** Every anonymous call
returns HTTP 429: *"Quota exceeded for quota metric 'Queries' and limit 'Queries per day'"*.
This is not a rate limit that patience clears — it is a shared daily quota against an
anonymous consumer project, exhausted before we arrived.

The consequence is direct: **`GOOGLE_BOOKS_API_KEY` is not optional**, contrary to the note
currently in `CLAUDE.md` and `.env.example`. US-06 cannot be built against anonymous access.
Either a key is obtained, or FR-08's price and description have no source and FR-13's
"missing price" becomes the permanent state rather than the exceptional one.

The spike degraded correctly, which is worth recording: the 429 produced a 200 response with
`price` and `currency` null and `sources` listing only `open_library`. That is FR-17's
designed behaviour, arrived at by accident before the story that specifies it.

**2. The ISBN chosen for US-10's not-found scenario is not absent.** `docs/04-user-stories.md`
uses `9781234567897` as its well-formed-but-unknown identifier. Open Library returns a real
record for it: *Construction Cost Consultant for Residential Commercial and Industrial
Construction Projects* by Toqeer Khan. The scenario as written would fail against live data
and pass only against a stub that encodes the same mistake.

`9780299999995` was verified absent and has a valid check digit. It also carries the 978-0
English-language prefix, so it reads as a plausible book identifier rather than an obvious
sentinel. Note that "absent" is a property of Open Library today, not of the number:
any fixture built on absence should be stubbed, per NFR-06, rather than trusted live.

### Unverified

The frontend was **not** verified in a browser. `npm run build` and `npm run lint` pass, the
Vite dev server serves the app, and the backend returns the correct
`access-control-allow-origin` header for `http://localhost:5173` — so the data path is
sound. But no one has seen the table render. That check remains outstanding.

### A smaller finding, but the reason rule 2 exists

Pydantic serialises `Decimal` as a JSON **string**, not a number: `"price": "37.99"`. The
hand-written interface in `App.tsx` gets this right only because it was checked against
`/openapi.json` first. A developer writing that interface from intuition would type `price`
as `number`, and TypeScript would not catch it — which is precisely the drift rule 2 exists
to prevent, demonstrated inside the change that breaks rule 2.
