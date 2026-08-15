# 03 — Requirements

Requirement IDs are stable and permanent. They are the branch names
(`feat/FR-XX-short-name`) and the left-hand column of `docs/06-traceability.md`. Where a
requirement derives from a rule in `CLAUDE.md`, the rationale cites the rule number.

The data contract referenced throughout is `BookInfo` in `backend/app/models.py`.

---

## Functional requirements

### FR-01 — ISBN input

**The system shall** provide a single input in which the user enters one ISBN, accepting
either ISBN-10 or ISBN-13 form, and shall ignore hyphens and surrounding whitespace when
interpreting the entry.

**Priority:** Must | **Rationale:** ISBN is the only input the product takes, and printed
ISBNs are conventionally hyphenated. Rejecting a correctly transcribed hyphenated ISBN
would be a defect from the user's point of view.

### FR-02 — ISBN-10 checksum validation

**The system shall** validate a 10-character entry using the ISBN-10 mod-11 check, where
the final character may be `X` representing the value 10, and shall treat any entry
failing that check as invalid.

**Priority:** Must | **Rationale:** The checksum catches transcription errors — the
dominant failure mode when copying an identifier off a book — locally and for free,
before any network call is spent on an identifier that cannot exist.

### FR-03 — ISBN-13 checksum validation

**The system shall** validate a 13-digit entry using the ISBN-13 mod-10 check with
alternating weights of 1 and 3, and shall treat any entry failing that check as invalid.

**Priority:** Must | **Rationale:** As FR-02, for the modern 13-digit form, which is what
the lookup ultimately queries.

### FR-04 — Normalisation to ISBN-13

**The system shall** convert a valid ISBN-10 to its ISBN-13 equivalent before performing
the lookup, and shall return that ISBN-13 in `BookInfo.isbn` regardless of which form the
user entered.

**Priority:** Must | **Rationale:** `BookInfo.isbn` is documented as "the ISBN-13 that was
looked up", so there is exactly one identifier form downstream. Upstream sources are also
keyed more reliably on ISBN-13.

### FR-05 — Rejection of invalid input

**The system shall** reject an entry that is not a valid ISBN-10 or ISBN-13 by displaying
an inline message that names the reason (wrong length, non-numeric character, or failed
checksum), and shall make no upstream request for that entry.

**Priority:** Must | **Rationale:** An invalid ISBN cannot produce a result, so calling
upstream wastes latency, quota and tokens. Naming the reason lets the user fix a typo
rather than guess.

### FR-06 — Lookup endpoint

**The system shall** expose an HTTP endpoint that accepts a validated ISBN and returns a
`BookInfo` object conforming to the schema in `backend/app/models.py`.

**Priority:** Must | **Rationale:** `BookInfo` is the single contract shared by agent, API
and UI (CLAUDE.md rule 2); one endpoint returning one contract keeps it that way.

### FR-07 — Identity from Open Library

**The system shall** obtain title, authors and cover image URL from `mcp-open-library`
tool calls.

**Priority:** Must | **Rationale:** Open Library is the authoritative source for
bibliographic identity in this design. Fixing which source owns which field prevents two
sources silently disagreeing about a title.

### FR-08 — Price and description from Google Books

**The system shall** obtain list price, currency and the publisher description from the
Google Books API.

**Priority:** Must | **Rationale:** Open Library carries no pricing. Google Books is the
designated source for the commercial fields and for a publisher-authored blurb.

### FR-09 — No facts from model memory

**The system shall** derive every book fact it returns from a tool call. The language
model shall not supply any book fact from its own memory; its permitted role is limited
to normalising the shape of tool output and writing a description when FR-10 applies.

**Priority:** Must | **Rationale:** CLAUDE.md rule 1, and the product's central promise.
A model-supplied fact is indistinguishable from a real one at the UI, which would make
every other fact in the table untrustworthy too.

### FR-10 — Generated-description flag

**The system shall** set `description_is_generated` to true when the description was
written by the language model, and false when it came from a publisher via an upstream
source.

**Priority:** Must | **Rationale:** The description is the one field the model is allowed
to author. The reader must be able to tell authored prose from sourced prose; the flag is
what makes FR-09's boundary visible rather than merely asserted.

### FR-11 — Source attribution

**The system shall** populate `sources` with every source that contributed to the
returned result, drawn from `open_library`, `google_books` and `llm`.

**Priority:** Must | **Rationale:** Attribution is what makes the result auditable. It is
also the mechanism by which a reviewer can check FR-09 held on any given response.

### FR-12 — Result table

**The system shall** display a successful result as a table showing title, authors, cover
image, price, description and contributing sources.

**Priority:** Must | **Rationale:** The tabular, field-by-field presentation is the
product — one scannable record per lookup, with the provenance shown alongside the facts
rather than buried.

### FR-13 — Missing price

**The system shall** return `price` and `currency` as null with HTTP 200 when no source
supplies a price, and shall display "Not available" in the price cell.

**Priority:** Must | **Rationale:** CLAUDE.md rule 3 — a missing price is a valid,
designed state, not an error. Many books legitimately have no listed price, and treating
that as a failure would discard an otherwise complete record.

### FR-14 — Missing cover

**The system shall** display a placeholder in place of the cover image when `cover_url`
is null, rather than a broken image.

**Priority:** Should | **Rationale:** `cover_url` is optional in the contract, so absence
is expected. A broken image reads as a bug and undermines confidence in the rest of the
row.

### FR-15 — Book not found

**The system shall**, when the ISBN is valid but no source has a record for it, display a
distinct "no book found" state that names the ISBN searched, visually separate from both
a successful result and a service failure.

**Priority:** Must | **Rationale:** "This identifier has no record" and "we could not
reach the sources" call for different user actions — check the number versus try again
later. Echoing the ISBN lets the user confirm what was actually searched.

### FR-16 — Upstream service failure

**The system shall**, when the identity source cannot be reached or returns an error,
display a distinct failure state offering a retry, and shall not render a partial or
empty result table.

**Priority:** Must | **Rationale:** Without identity there is no result worth showing. A
half-filled table would be indistinguishable from a book with genuinely sparse data,
which is exactly the ambiguity this product exists to remove.

### FR-17 — Degraded result on price-source failure

**The system shall**, when the price source fails but the identity source succeeds,
return the result with `price` and `currency` null rather than failing the lookup.

**Priority:** Should | **Rationale:** The identity fields are still complete and useful,
and null price is already a designed state under FR-13. Note that this renders
identically to a book that genuinely has no price; distinguishing the two would require a
field beyond the current `BookInfo` contract and is deliberately not done.

### FR-18 — In-flight state

**The system shall** display a loading indicator while a lookup is in progress and
prevent a second submission until it resolves.

**Priority:** Should | **Rationale:** A lookup may take several seconds under NFR-01.
Without feedback the user re-submits, doubling upstream cost for no benefit.

### FR-19 — Generated frontend types

**The system shall** generate the frontend's TypeScript types for `BookInfo` from the
backend's `/openapi.json`. Hand-written equivalents shall not be introduced.

**Priority:** Must | **Rationale:** CLAUDE.md rule 2. A hand-copied interface drifts
silently from the Pydantic model; generation makes the contract single-sourced and drift
a build error.

### FR-20 — Repeat lookup

**The system shall** perform a fresh lookup each time an ISBN is submitted, including a
repeat of an ISBN looked up earlier in the session.

**Priority:** Could | **Rationale:** No caching is in scope (see `docs/01-vision.md`), and
re-querying is the simplest way to guarantee the displayed record reflects the sources as
they are now.

---

## Non-functional requirements

### NFR-01 — Response time

**The system shall** complete an end-to-end lookup within 5 seconds at the 95th
percentile, and shall apply a timeout of 3 seconds to each individual upstream call.

**Priority:** Must | **Rationale:** The per-call timeout is what makes the overall budget
achievable: one unresponsive source cannot hold the whole request open. Beyond roughly
five seconds a single-field lookup stops feeling interactive.

### NFR-02 — Local validation feedback

**The system shall** perform ISBN format and checksum validation client-side, so that
FR-05's feedback appears without a network round trip.

**Priority:** Should | **Rationale:** Checksum validation is arithmetic on ten or thirteen
characters. Spending a round trip on it makes typo correction feel slow for no gain.

### NFR-03 — API key handling

**The system shall** read all credentials from environment variables or a local `.env`
file that is never committed. Keys shall not appear in source, logs, API responses or the
frontend bundle, and `.env.example` shall list every variable required with placeholder
values.

**Priority:** Must | **Rationale:** CLAUDE.md rule 7. Upstream calls happen server-side
precisely so keys stay server-side; `.env.example` keeps the requirement discoverable
without leaking anything.

### NFR-04 — Accessibility

**The system shall** meet WCAG 2.1 Level AA: the ISBN input has an associated visible
label, all functionality is operable by keyboard alone, results are marked up as a
semantic table with header cells, the cover image carries meaningful `alt` text, error
and result state changes are announced via a live region, and text meets a 4.5:1 contrast
ratio.

**Priority:** Must | **Rationale:** The audience includes library and archive staff, where
accessibility is frequently a procurement requirement. A result that appears without
announcement is invisible to a screen reader user, which makes the product unusable
rather than merely awkward.

### NFR-05 — Auditability

**The system shall** ensure every fact in a response is attributable to an entry in
`sources`, such that a reviewer can verify FR-09 from the response alone.

**Priority:** Must | **Rationale:** FR-09 is a promise about behaviour; this is what makes
it checkable after the fact rather than taken on trust.

### NFR-06 — Deterministic tests

**The system shall** be testable without live upstream calls, with tool responses stubbed,
and shall use `9780132350884` (Clean Code, Robert C. Martin) as the golden end-to-end
fixture.

**Priority:** Must | **Rationale:** Tests are written from Gherkin acceptance criteria
before implementation (CLAUDE.md rule 6), which is only possible against stubs. Live
upstreams would also make the suite flaky and quota-bound.

### NFR-07 — Quality gates

**The system shall** keep `uv run ruff check`, `uv run mypy app`, `uv run pytest`,
`npm run lint` and `npm run build` passing on every merged change.

**Priority:** Must | **Rationale:** The gates are already defined in CLAUDE.md; making
green a merge condition is what stops the contract and the types from drifting apart
between stories.

### NFR-08 — Safe error reporting

**The system shall** present failures as human-readable messages and shall not expose
stack traces, upstream URLs, request internals or credentials to the client.

**Priority:** Must | **Rationale:** Internal detail in an error is both a disclosure risk
and useless to the user, who needs to know whether to retry or check the number.

### NFR-09 — No data retention

**The system shall** not persist looked-up ISBNs, results or any user data beyond the
lifetime of the request.

**Priority:** Should | **Rationale:** Persistence is out of scope, and holding no data is
the cheapest way to have no data-protection obligations to discharge.

### NFR-10 — Local runnability

**The system shall** be startable locally with the commands documented in `CLAUDE.md`,
requiring only `.env` to be populated from `.env.example`.

**Priority:** Could | **Rationale:** The project doubles as a reference implementation;
a reader who cannot run it in one step gets far less from it.

---

## Coverage note

Traceability from these IDs to user stories, tests and code is maintained in
`docs/06-traceability.md`. User stories are not written yet.
