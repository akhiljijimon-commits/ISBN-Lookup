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

### Findings that change the plan

**1. Google Books rejects unauthenticated requests at this volume.** Every anonymous call
returns HTTP 429: *"Quota exceeded for quota metric 'Queries' and limit 'Queries per day'"*.
This is not a rate limit that patience clears — it is a shared daily quota against an
anonymous consumer project, exhausted before we arrived.

The consequence is direct: **`GOOGLE_BOOKS_API_KEY` is not optional.** US-06 cannot be built
against anonymous access. Either a key is obtained, or FR-08's price and description have no
source and FR-13's "missing price" becomes the permanent state rather than the exceptional
one.

*Resolved, 2026-08-15.* A key was obtained and verified. `CLAUDE.md` and `.env.example`,
which had both described the key as optional, now state that it is required;
`fetch_google_books` appends it from the environment when set. The finding stands as the
reason those documents changed.

**1a. The golden ISBN has no price, and never will.** With the key working, Google Books
returns HTTP 200 for `9780132350884` with `saleability: NOT_FOR_SALE` and no `listPrice`
at all. The description populates; the price does not. So `price: null` for the golden
fixture is correct upstream data, not a quota artefact and not an extraction bug.

This makes the golden ISBN a permanent exerciser of FR-13 — "Not available" is its normal
rendering, in every demo and every manual check. A title that *does* carry a price is
needed to exercise the other branch: `9783527823925` (*Clean Code für Dummies*) returns
`"19.99"` / `EUR`. It also returns `cover_url: null`, so it doubles as a live case for
FR-14's placeholder. Both belong in US-06's and US-09's stubbed fixtures.

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

**3. Open Library requires an identified client.** Its API documentation asks for a descriptive
`User-Agent` carrying a contact address. Unidentified clients are rate-limited to one request per
second; identified ones are allowed three. `fetch_open_library` now sends:

```
User-Agent: ISBN-Lookup/0.1 (akhiljijimon@gmail.com)
```

The header is sent only to Open Library, not to Google Books, and
`test_open_library_request_identifies_the_application` guards it.

*Recorded 2026-08-17, with a correction to the reason for adding it.* The change was prompted by
an assumption that we were being throttled. Measurement does not support that. At the time of
writing `openlibrary.org` is not throttling us — it is **unreachable**: the TCP handshake to
`207.241.234.205:443` never completes, `curl` reports `connect=0.000000s` before timing out, and
every host under the domain including `covers.openlibrary.org` behaves the same way. `archive.org`,
run by the same operator, returns 200 from the same machine, so this is specific to Open Library
rather than a local network fault. Throttling would present as HTTP 429 or slow-but-successful
responses, not as a refused connection.

So the header is correct and required by their documentation, and it should stay — but it did not
fix the failure we were seeing, and it will not. While the outage lasts, `_get_json` turns the
timeout into `None` and every lookup returns 404, which is the FR-15/FR-16 conflation described
elsewhere in this ADR showing up in production form: "the source is down" is being reported to users
as "no such book".

### A temporary identity fallback, added 2026-08-17

**Why.** Open Library is unreachable, as measured above. Because `_get_json` turns the failure into
`None` and `BookInfo.title` is required, *every* lookup returns 404 — the system does nothing at
all while the outage lasts. The fallback exists so it keeps working.

**What.** When `fetch_open_library` yields nothing and `ALLOW_IDENTITY_FALLBACK` is set, title,
authors and cover come from Google Books instead. `sources` then reports `google_books` alone: the
result truthfully says Open Library contributed nothing, so FR-11 and NFR-05 still hold.

**The flag defaults to off**, so the documented architecture is what runs unless someone opts out of
it. FR-07 is unchanged — Open Library owns identity, and the fallback fires only when Open Library
has already returned nothing. `test_open_library_still_wins_when_reachable` pins that.

**This is a degradation path, not a design change, and it should be deleted when Open Library
returns.** Google Books has noisier identity data (`docs/01-vision.md`), which is the reason the
split in §5 of the technical concept exists. Its cover is also a small `books.google.com` thumbnail
rather than a full-size jacket. The fallback produces worse data that is honestly labelled — not
equivalent data.

**A bug found while verifying it.** The first implementation called Google Books twice on this path:
once for identity, once for commerce. The second call was rate-limited in live testing, which
silently discarded the publisher description and flipped `description_is_generated` to `true` — a
provenance error caused purely by asking twice. `fetch_google_books_pair` now derives both
projections from a single request. Worth recording because the failure was invisible in the
response: nothing about a generated description looks wrong until you know a publisher one existed.

**Latency is now badly over budget.** A fallback lookup measured **10.3 seconds** end to end: three
seconds burnt on the Open Library timeout, about a second on Google Books, and the rest on the model.
NFR-01 budgets five seconds p95 for the whole lookup. This path is double it, and even the healthy
agent path is at the limit (see [ADR-0005](0005-agent-without-autonomous-tool-calling.md)).

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
