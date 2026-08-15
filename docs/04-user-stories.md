# 04 — User stories

Each story below is one pull request (CLAUDE.md rule 4) and closes the functional
requirements named in its **Covers** line. The Gherkin scenarios are not illustrative: they
are the source the tests are written from, before the implementation exists (rule 6).

A **Covers** line may list functional and non-functional requirements together. An NFR is
listed only where this story's scenarios assert it directly; an NFR that every story must
satisfy stays cross-cutting in `docs/06-traceability.md` and is not listed here. Rule 5
names branches after a single requirement, so a story covering more than one requirement
branches on its lead — the first *FR* in its **Covers** line, never an NFR, regardless of
what else that line carries. US-01 becomes `feat/FR-02-isbn-validation`.

Scenarios use the golden fixture from CLAUDE.md throughout: `9780132350884`
(*Clean Code*, Robert C. Martin), its ISBN-10 form `0132350882`, and `9780132350885` —
the same digits with a wrong final check digit — as the invalid example.

US-10's not-found scenario needs a different fixture: an ISBN that is *valid* yet has no
record, so it cannot be one of the above. It uses `9780299999995` — valid check digit,
978-0 English-language prefix, and verified absent from Open Library. An earlier draft used
`9781234567897`, which turns out to return a real record (*Construction Cost Consultant for
Residential Commercial and Industrial Construction Projects*), so any scenario built on it
would have passed only against a stub that repeated the mistake. Absence is a property of
the upstream catalogue on a given day, not of the number: per NFR-06 this fixture must be
stubbed in tests rather than trusted live.

---

## US-01: ISBN validation and normalisation

**Covers:** FR-02, FR-03, FR-04

**As a** developer maintaining the lookup service **I want** a single module that decides
whether an ISBN is well formed and converts it to one canonical form **so that** every
later stage works with an identifier that has already been proved valid.

### Acceptance criteria

```gherkin
Scenario: A valid ISBN-13 passes the mod-10 check
  Given the ISBN-13 "9780132350884"
  When it is validated
  Then it is reported valid
  And the normalised form is "9780132350884"

Scenario: A valid ISBN-10 is normalised to ISBN-13
  Given the ISBN-10 "0132350882"
  When it is validated and normalised
  Then it is reported valid
  And the normalised form is "9780132350884"

Scenario: An ISBN-10 ending in X is accepted
  Given the ISBN-10 "043942089X"
  When it is validated and normalised
  Then the final "X" is read as the value 10
  And the normalised form is "9780439420891"

Scenario: An ISBN-13 failing the check digit is rejected
  Given the ISBN-13 "9780132350885"
  When it is validated
  Then it is reported invalid
  And the reason is "failed checksum"

Scenario: An ISBN-10 failing the check digit is rejected
  Given the ISBN-10 "0132350883"
  When it is validated
  Then it is reported invalid
  And the reason is "failed checksum"

Scenario: An entry of the wrong length is rejected before any checksum is attempted
  Given the entry "978013235088"
  When it is validated
  Then it is reported invalid
  And the reason is "wrong length"
```

---

## US-02: ISBN entry and inline rejection

**Covers:** FR-01, FR-05, NFR-02, NFR-04

**As a** librarian cataloguing an acquisition **I want** to type an ISBN exactly as it is
printed on the book and be told immediately if I have mistyped it **so that** I can correct
a transcription error without waiting on a lookup that could never succeed.

### Acceptance criteria

```gherkin
Scenario: A hyphenated ISBN is accepted as printed
  Given the lookup page
  When I enter "978-0-13-235088-4" and submit
  Then the entry is accepted
  And the ISBN "9780132350884" is submitted for lookup

Scenario: Surrounding whitespace is ignored
  Given the lookup page
  When I enter "  9780132350884  " and submit
  Then the entry is accepted
  And the ISBN "9780132350884" is submitted for lookup

Scenario: A failed checksum is reported inline and costs no request
  Given the lookup page
  When I enter "9780132350885" and submit
  Then an inline message names the reason as a failed checksum
  And no request is made to the lookup endpoint

Scenario: A too-short entry is reported inline
  Given the lookup page
  When I enter "978013235088" and submit
  Then an inline message names the reason as a wrong length
  And no request is made to the lookup endpoint

Scenario: A non-numeric character is reported inline
  Given the lookup page
  When I enter "978013235088X" and submit
  Then an inline message names the reason as a non-numeric character
  And no request is made to the lookup endpoint

Scenario: The ISBN input carries a visible, associated label
  Given the lookup page
  When the form is rendered
  Then the ISBN input has a visible label
  And that label is its accessible name, associated programmatically
  And the input can be reached and submitted by keyboard alone

Scenario: An inline error is announced to assistive technology
  Given the lookup page
  When I enter "9780132350885" and submit
  Then the inline message is rendered inside a live region
  And it is announced without focus being moved
  And the input is associated with the message as its error description
```

---

## US-03: Lookup endpoint

**Covers:** FR-06

**As a** frontend developer building against this service **I want** one HTTP endpoint that
takes an ISBN and returns a `BookInfo` **so that** there is exactly one shape to code
against and one schema to generate types from.

### Acceptance criteria

```gherkin
Scenario: A valid ISBN returns a conforming BookInfo
  Given the lookup service is running
  When a lookup is requested for "9780132350884"
  Then the response status is 200
  And the body validates against the BookInfo schema in backend/app/models.py
  And the "isbn" field is "9780132350884"

Scenario: An ISBN-10 request returns the ISBN-13 in the contract
  Given the lookup service is running
  When a lookup is requested for "0132350882"
  Then the response status is 200
  And the "isbn" field is "9780132350884"

Scenario: An invalid ISBN is refused by the endpoint
  Given the lookup service is running
  When a lookup is requested for "9780132350885"
  Then the response status is 422
  And no upstream source is contacted
```

---

## US-04: Generated frontend types

**Covers:** FR-19

**As a** developer working on the frontend **I want** the `BookInfo` TypeScript type
generated from the backend's `/openapi.json` **so that** a change to the Pydantic model
breaks the build instead of drifting silently into a mismatch at runtime.

### Acceptance criteria

```gherkin
Scenario: Types are generated from the published schema
  Given the backend exposes /openapi.json
  When the type generation step is run
  Then a BookInfo type is written into the frontend source tree
  And its fields match the BookInfo model field for field, including which are nullable

Scenario: A model change that is not regenerated fails the build
  Given a field has been added to BookInfo in backend/app/models.py
  And the generated types have not been regenerated
  When "npm run build" is run
  Then the build fails

Scenario: A hand-written contract type is not accepted
  Given a hand-written BookInfo interface is added to the frontend source
  When the quality gates are run
  Then the gates fail, citing CLAUDE.md rule 2
```

---

## US-05: Identity from Open Library

**Covers:** FR-07

**As a** librarian cataloguing an acquisition **I want** the title, authors and cover to
come from Open Library **so that** the identity of the book is taken from one authoritative
source rather than reconciled between two that may disagree.

### Acceptance criteria

```gherkin
Scenario: Identity fields are populated from Open Library
  Given mcp-open-library returns a record for "9780132350884"
  When the lookup runs
  Then "title" is "Clean Code"
  And "authors" contains "Robert C. Martin"
  And "cover_url" holds the cover URL from that record
  And "sources" contains "open_library"

Scenario: Identity is never taken from the price source
  Given mcp-open-library returns a record whose title is "Clean Code"
  And Google Books returns a record whose title is "Clean Code: A Handbook"
  When the lookup runs
  Then "title" is "Clean Code"

Scenario: A record absent from Open Library yields no identity
  Given mcp-open-library returns no record for "9780132350884"
  When the lookup runs
  Then no title or authors are populated
  And the lookup does not return a successful result
```

---

## US-06: Price and description from Google Books

**Covers:** FR-08

**As a** bookseller checking a listing **I want** the list price and the publisher's
description to come from Google Books **so that** I get the commercial fields Open Library
does not carry.

### Acceptance criteria

```gherkin
Scenario: Price, currency and publisher description are populated
  Given Google Books returns a record for "9780132350884"
  And that record lists a price of 37.99 in EUR with a publisher description
  When the lookup runs
  Then "price" is 37.99
  And "currency" is "EUR"
  And "description" is the publisher description from that record
  And "sources" contains "google_books"

Scenario: Google Books does not supply identity fields
  Given both sources return a record for "9780132350884"
  When the lookup runs
  Then "title" and "authors" are taken from Open Library only

Scenario: A record with no price yields no price
  Given Google Books returns a record for "9780132350884" with no price
  When the lookup runs
  Then "price" is null
  And "currency" is null
```

---

## US-07: Provenance and the no-memory boundary

**Covers:** FR-09, FR-10, FR-11, NFR-05

**As a** reviewer auditing a returned record **I want** every fact to be attributable to a
named source, and model-authored prose to be flagged as such **so that** I can verify from
the response alone that nothing was invented.

### Acceptance criteria

```gherkin
Scenario: A publisher description is not flagged as generated
  Given Google Books returns a publisher description for "9780132350884"
  When the lookup runs
  Then "description_is_generated" is false
  And "sources" contains "open_library" and "google_books"
  And "sources" does not contain "llm"

Scenario: A model-written description is flagged and attributed
  Given Open Library returns a record for "9780132350884"
  And Google Books returns no description
  When the lookup runs
  Then "description" is written by the model from the tool output
  And "description_is_generated" is true
  And "sources" contains "llm"

Scenario: No fact is supplied from model memory
  Given every tool call returns an empty result for "9780132350884"
  When the lookup runs
  Then no title, author, price or cover value appears in the result
  And the lookup does not return a successful result

Scenario: Every source in the result actually contributed
  Given only Open Library returns a record for "9780132350884"
  When the lookup runs
  Then "sources" does not contain "google_books"
```

---

## US-08: Result table

**Covers:** FR-12, FR-14, FR-18, NFR-04

**As a** librarian cataloguing an acquisition **I want** a successful lookup rendered as one
scannable table with its sources shown alongside the facts **so that** I can read the whole
record, and judge how far to trust it, in a single glance.

### Acceptance criteria

```gherkin
Scenario: A successful lookup renders every field
  Given a lookup for "9780132350884" returns a complete record
  When the result is displayed
  Then a table shows the title, authors, cover image, price, description and sources
  And the cover image is rendered from "cover_url"

Scenario: A missing cover renders a placeholder
  Given a lookup for "9780132350884" returns "cover_url" as null
  When the result is displayed
  Then a placeholder is shown in place of the cover
  And no broken image is rendered

Scenario: A lookup in progress shows a loading indicator
  Given I have submitted "9780132350884"
  And the lookup has not yet resolved
  Then a loading indicator is displayed
  And the result table is not displayed

Scenario: A second submission is prevented while one is in flight
  Given a lookup for "9780132350884" is in progress
  When I submit again
  Then no second request is made

Scenario: The result is a semantic table with header cells
  Given a lookup for "9780132350884" returns a complete record
  When the result is displayed
  Then the result is marked up as a table
  And each field name is a "th" header cell, not a styled data cell
  And each value is in a data cell associated with its header

Scenario: The cover image carries meaningful alt text
  Given a lookup for "9780132350884" returns a cover image
  When the result is displayed
  Then the cover image has alt text naming the book
  And the alt text is not "cover" or the empty string

Scenario: The cover placeholder is not announced as a cover
  Given a lookup for "9780132350884" returns "cover_url" as null
  When the result is displayed
  Then the placeholder is announced as a missing cover
  And it is not announced as an image of the book
```

---

## US-09: Missing price

**Covers:** FR-13

**As a** bookseller checking a listing **I want** a book with no listed price to return its
record normally, with the price shown as unavailable **so that** I keep an otherwise
complete record instead of losing it to an error.

### Acceptance criteria

```gherkin
Scenario: No source supplies a price
  Given no source supplies a price for "9780132350884"
  When the lookup runs
  Then the response status is 200
  And "price" is null
  And "currency" is null

Scenario: The price cell reads "Not available"
  Given a result for "9780132350884" with "price" null
  When the result is displayed
  Then the price cell reads "Not available"
  And the remaining fields are displayed as normal

Scenario: A missing price is not treated as a failure
  Given a result for "9780132350884" with "price" null
  When the result is displayed
  Then no error state is displayed
```

---

## US-10: Distinct not-found and service-failure states

**Covers:** FR-15, FR-16, FR-17, NFR-04

**As an** archivist confirming an edition **I want** "this ISBN has no record" and "we could
not reach the sources" to look different **so that** I know whether to re-check the number
or simply try again later.

### Acceptance criteria

```gherkin
Scenario: A valid ISBN with no record shows a not-found state
  Given "9780299999995" is a valid ISBN
  And no source has a record for it
  When the lookup runs
  Then a "no book found" state is displayed
  And the state names the ISBN "9780299999995" as the one searched
  And no result table is displayed

Scenario: An unreachable identity source shows a failure state with a retry
  Given mcp-open-library cannot be reached
  When a lookup is requested for "9780132350884"
  Then a service failure state is displayed
  And it offers a retry
  And no partial or empty result table is displayed

Scenario: The two states are distinguishable
  Given a not-found result and a service failure result
  When each is displayed
  Then they render as visibly different states
  And neither is rendered as a successful result

Scenario: A failing price source degrades rather than fails the lookup
  Given mcp-open-library returns a record for "9780132350884"
  And the Google Books request fails
  When the lookup runs
  Then the response status is 200
  And the identity fields are populated
  And "price" and "currency" are null

Scenario Outline: Each result state is announced to assistive technology
  Given a lookup that ends in the <state> state
  When the state is displayed
  Then the state change is announced via a live region
  And the announcement names the reason, not merely that an error occurred

  Examples:
    | state           |
    | no book found   |
    | service failure |

Scenario: The two states differ by more than colour
  Given a not-found result and a service failure result
  When each is displayed
  Then they differ in their text, not only in their colour
  And each remains distinguishable with colour information removed
```

---

## Requirements deliberately not covered by a story

**FR-20 — Repeat lookup (Could).** This requirement falls out of the architecture rather
than being built. No caching or persistence is in scope (`docs/01-vision.md`), so every
submission already performs a fresh lookup; there is no code a story could close, only a
property that US-08's scenarios must not break. It is recorded here so its absence from the
story list reads as a decision rather than an oversight.

All Must-priority functional requirements are covered by exactly one story above. The
Should-priority requirements FR-14, FR-17 and FR-18 are folded into US-08 and US-10, the
stories whose pull requests would naturally contain them.

Traceability from requirements to stories, tests and code is maintained separately in
`docs/06-traceability.md`.
