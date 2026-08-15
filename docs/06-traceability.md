# 06 — Traceability

This table is the link between a requirement in `docs/03-requirements.md`, the story that
closes it in `docs/04-user-stories.md`, and the work that delivers it. It is maintained
incrementally, never in a batch: every pull request closes exactly one user story
(CLAUDE.md rule 4) and, in that same PR, fills in the Issue, Test, PR and Status cells of
every row that story covers. A PR that changes behaviour without updating its rows is
incomplete, and a row still reading "Not started" after its story has merged is a defect in
the record rather than a formality. Requirement IDs are stable and permanent, so rows are
edited in place — never renumbered, never deleted. Test cells name the test that proves the
requirement, so the table doubles as the audit trail for NFR-05.

**Status values:** Not started → In progress → Merged.

## Functional requirements

| Requirement | Priority | User Story | GitHub Issue | Test | PR | Status |
|---|---|---|---|---|---|---|
| FR-01 — ISBN input | Must | US-02 | | | | Not started |
| FR-02 — ISBN-10 checksum validation | Must | US-01 | | | | Not started |
| FR-03 — ISBN-13 checksum validation | Must | US-01 | | | | Not started |
| FR-04 — Normalisation to ISBN-13 | Must | US-01 | | | | Not started |
| FR-05 — Rejection of invalid input | Must | US-02 | | | | Not started |
| FR-06 — Lookup endpoint | Must | US-03 | | | | Not started |
| FR-07 — Identity from Open Library | Must | US-05 | | | | Not started |
| FR-08 — Price and description from Google Books | Must | US-06 | | | | Not started |
| FR-09 — No facts from model memory | Must | US-07 | | | | Not started |
| FR-10 — Generated-description flag | Must | US-07 | | | | Not started |
| FR-11 — Source attribution | Must | US-07 | | | | Not started |
| FR-12 — Result table | Must | US-08 | | | | Not started |
| FR-13 — Missing price | Must | US-09 | | | | Not started |
| FR-14 — Missing cover | Should | US-08 | | | | Not started |
| FR-15 — Book not found | Must | US-10 | | | | Not started |
| FR-16 — Upstream service failure | Must | US-10 | | | | Not started |
| FR-17 — Degraded result on price-source failure | Should | US-10 | | | | Not started |
| FR-18 — In-flight state | Should | US-08 | | | | Not started |
| FR-19 — Generated frontend types | Must | US-04 | | | | Not started |
| FR-20 — Repeat lookup | Could | none — by design | | | | Not started |

## Non-functional requirements

| Requirement | Priority | User Story | GitHub Issue | Test | PR | Status |
|---|---|---|---|---|---|---|
| NFR-01 — Response time | Must | cross-cutting | | | | Not started |
| NFR-02 — Local validation feedback | Should | US-02 | | | | Not started |
| NFR-03 — API key handling | Must | cross-cutting | | | | Not started |
| NFR-04 — Accessibility | Must | US-02, US-08, US-10 | | | | Not started |
| NFR-05 — Auditability | Must | US-07 | | | | Not started |
| NFR-06 — Deterministic tests | Must | cross-cutting | | | | Not started |
| NFR-07 — Quality gates | Must | cross-cutting | | | | Not started |
| NFR-08 — Safe error reporting | Must | cross-cutting | | | | Not started |
| NFR-09 — No data retention | Should | cross-cutting | | | | Not started |
| NFR-10 — Local runnability | Could | cross-cutting | | | | Not started |

## Notes on the User Story column

**FR-20** carries "none — by design" rather than "cross-cutting". It is the one functional
requirement with no story, because no caching is in scope (`docs/01-vision.md`) and so a
fresh lookup per submission is a property of the architecture, not work to be done. See the
closing section of `docs/04-user-stories.md`. Its status stays "Not started" until US-08
merges, at which point the property holds and it can be marked Merged against that PR.

**NFR-02**, **NFR-04** and **NFR-05** name stories because those stories' acceptance
criteria assert them directly. US-02's scenarios require that an invalid entry makes no
request to the endpoint; US-07's require that every entry in `sources` actually contributed;
and US-02, US-08 and US-10 each carry scenarios for the accessibility clauses they own —
the labelled input and announced inline error, the semantic header cells and cover alt text,
and the announced result states that differ by more than colour. NFR-04 is the one
requirement here spanning three stories, so its row is complete only when all three have
merged. The remaining NFRs are marked cross-cutting because no single story's Gherkin
exercises them.

"Cross-cutting" means every PR must satisfy it, not that nobody owns it. Five of the
cross-cutting NFRs are Must-priority — NFR-01, NFR-03, NFR-06, NFR-07 and NFR-08 — and each
is a condition on merging any story, not deferred work. They are marked Merged only once the
last functional story has landed and they have been verified against the whole system.
