# ISBN Lookup

Enter an ISBN, get one verified table of book details — title, authors, cover, price,
description — with the sources that supplied each result shown alongside them. The design
principle the whole system is built around is that **the language model never supplies a book
fact from memory**. Python fetches from Open Library and Google Books, and Python owns every
structured field in the response: it sets `isbn`, `price`, `currency`, `sources` and
`description_is_generated` itself and overwrites whatever the model returns for them. The model's
remit is deliberately narrow — normalise the shape of what the tools returned, and write a short
description when no publisher supplied one. A fabricated price or a self-declared source is
therefore *structurally impossible*, not merely discouraged by a prompt, and the test suite proves
it by having the model attempt exactly that.

## What it looks like

![Lookup of Clean Code](docs/images/Screenshot%202026-08-17%20at%2013.37.16.png)

*The golden test ISBN `9780132350884`. No source carries a price for this title, so the price cell
reads **"Not available"** — a designed state returning HTTP 200, never an error. The collapsible
**API response** panel exposes the endpoint, status, timing and raw JSON, so the contract is
visible rather than described. Note `sources` reads `google_books, llm`: these screenshots were
taken during an Open Library outage, with the temporary identity fallback enabled (see
[Known issues](#known-issues)).*

![Lookup of a priced title](docs/images/Screenshot%202026-08-17%20at%2013.38.12.png)

*`9783527823925` does carry a price, so the same table renders **19.99 EUR**. Prices cross the wire
as JSON strings, not numbers — `Decimal` is serialised as `"19.99"` to avoid float error, a detail
the generated frontend types will carry automatically.*

![Rejected input](docs/images/Screenshot%202026-08-17%20at%2013.39.22.png)

*A twelve-digit entry is rejected in **5 ms** with HTTP 422 and no upstream request at all. Invalid
input never costs latency, quota or tokens.*

![Lookup of Effective Java](docs/images/Screenshot%202026-08-17%20at%2013.39.49.png)

*`9780134685991` — a different title through the same path, confirming nothing is special-cased to
the test fixture, and that a publisher-supplied description is passed through unchanged with
`description_is_generated: false`.*

## Architecture

```
React (Vite)
    │  GET /api/books/{isbn}
    ▼
FastAPI
    │  validate → fetch → normalise
    ├─────────────► Open Library      identity: title, authors, cover
    ├─────────────► Google Books      price, currency, publisher description
    │
    └─────────────► Pydantic AI agent ──► self-hosted vLLM endpoint
                    (normalisation and         (OpenAI-compatible,
                     description only)          provider-supplied)
```

Python calls both sources directly and hands the raw results to the agent. The agent returns a
validated `BookInfo`; Python then re-asserts every field it already knows. The model is reached
through Pydantic AI's OpenAI-compatible provider pointed at a self-hosted vLLM endpoint supplied by
the project's infrastructure provider.

`BookInfo` in `backend/app/models.py` is the single shared contract. The frontend type is currently
hand-written and will be generated from `/openapi.json`.

## Documentation

| Document | What it covers |
|---|---|
| [`docs/01-vision.md`](docs/01-vision.md) | The problem, the target user, and what is explicitly out of scope |
| [`docs/03-requirements.md`](docs/03-requirements.md) | 20 functional and 10 non-functional requirements, each with a rationale |
| [`docs/04-user-stories.md`](docs/04-user-stories.md) | Ten stories with Gherkin acceptance criteria — the source the tests are written from |
| [`docs/05-technical-concept.md`](docs/05-technical-concept.md) | How the system is put together, as designed and as actually built |
| [`docs/06-traceability.md`](docs/06-traceability.md) | Requirement → story → test → PR, one row per requirement |
| [`docs/adr/0003-self-hosted-vllm-qwen.md`](docs/adr/0003-self-hosted-vllm-qwen.md) | Choosing the self-hosted vLLM endpoint, and the two capability risks it carried |
| [`docs/adr/0004-vertical-slice-spike.md`](docs/adr/0004-vertical-slice-spike.md) | The throwaway spike, every project rule it suspended, and the upstream findings it produced |
| [`docs/adr/0005-agent-without-autonomous-tool-calling.md`](docs/adr/0005-agent-without-autonomous-tool-calling.md) | Building the agent when the server disables tool calling, and where rule 1 does *not* fully hold |

## Running it locally

**Prerequisites:** Python 3.12 and [uv](https://docs.astral.sh/uv/) for the backend; Node.js
20.19+, 22.13+ or 24+ with npm for the frontend (Vite 8 and ESLint 10 both refuse older 20.x and
22.x releases).

```bash
cp .env.example .env      # then fill in the values
```

`.env` needs `LLM_API_KEY`, `LLM_BASE_URL` and `LLM_MODEL` for the vLLM endpoint, and
`GOOGLE_BOOKS_API_KEY`. The Google Books key is **required**, not optional: anonymous requests hit
an exhausted shared daily quota and return HTTP 429. `.env` is gitignored; `.env.example` lists
every variable with placeholders and is committed.

```bash
cd backend  && uv run uvicorn app.main:app --reload   # http://localhost:8000
cd frontend && npm install && npm run dev             # http://localhost:5173
```

Two optional flags: `USE_AGENT=0` serves a deterministic path with no LLM call, and
`ALLOW_IDENTITY_FALLBACK=1` enables the temporary Open Library workaround described below.

Quality gates:

```bash
cd backend  && uv run pytest && uv run ruff check . && uv run mypy app
cd frontend && npm run lint && npm run build
```

## Example ISBNs

| ISBN | What it demonstrates |
|---|---|
| `9780132350884` | *Clean Code* — the golden fixture. No source carries a price, so it permanently exercises the "Not available" state |
| `9783527823925` | *Clean Code für Dummies* — a title that **does** carry a price (19.99 EUR) |
| `9780134685991` | *Effective Java* — a second real title with a publisher description |
| `978-0-13-235088-4` | The golden ISBN hyphenated as printed; hyphens and spaces are stripped before lookup |
| `9780299999995` | Valid check digit, but no catalogue holds it — returns 404 |
| `978013235088` | Twelve digits — rejected with 422 in milliseconds, no upstream call |

Note that checksum validation is **not yet implemented** — only the 13-digit shape is checked. A
checksum-invalid ISBN like `9780132350885` is currently looked up and returns 404 rather than being
rejected up front. That is US-01's job.

## On MCP

The design calls for `mcp-open-library`, a community MCP server, as the route to Open Library.
**It is designed but not integrated**, for two independent reasons:

1. **The server wraps an API that is currently unreachable.** Open Library has been refusing TCP
   connections throughout development (see [Known issues](#known-issues)). An MCP server in front of
   an unreachable API is an unreachable MCP server.
2. **Autonomous tool calling is disabled server-side.** The vLLM deployment was not started with
   `--enable-auto-tool-choice`, so the model cannot be handed tools and left to decide when to
   invoke them — which is the entire point of MCP. This is recorded in
   [ADR-0005](docs/adr/0005-agent-without-autonomous-tool-calling.md).

**How it would slot in.** `backend/app/sources.py` would stop making its own HTTP call for identity.
The agent would instead be constructed with the MCP server attached as a toolset, and the model
would call the server's ISBN lookup tool itself, deciding when it needs identity data rather than
receiving it pre-fetched. `backend/app/main.py`'s orchestration would become the fallback path
rather than the design — worth keeping regardless, since it is also what runs when the model is
unreachable. Crucially, **the field-ownership rule would not change**: Python would still re-assert
`price`, `sources` and `description_is_generated` after the agent returned, because that is what
makes the no-facts-from-memory guarantee checkable rather than merely trusted.

Enabling the server flag is the prerequisite. Until then, MCP would add a dependency without adding
a capability.

## Known issues

**End-to-end latency is roughly double the budget.** NFR-01 asks for 5 seconds at the 95th
percentile. Observed lookups take **7–8.5 seconds** in the screenshots above and up to ~10 seconds
on the fallback path. The model call dominates at 2.7–4.6 seconds, and a further 3 seconds is
currently burnt waiting for the unreachable Open Library to time out. Fetching the two sources
concurrently, and skipping the model when there is no description to write, would recover most of
it. Neither is done.

**An upstream timeout is reported as "no book found".** `_get_json` collapses every failure —
timeout, connection refused, 5xx, malformed JSON — into the same `None` as "this source has no
record". The endpoint cannot tell them apart, so it returns 404 either way. A reviewer will see
"No book found for ISBN …" when the truth is "the source is down". FR-15 and FR-16 exist precisely
to separate these two states, because "check the number" and "try again later" call for different
actions from the user; US-10 delivers it. This is the most user-visible gap in the system.

**Two third-party outages during development**, both documented rather than papered over:

- **Google Books rejected anonymous requests** with HTTP 429 against an exhausted shared daily
  quota. This falsified the project's initial assumption that the key was optional. Fixed by
  obtaining a key; the documentation was corrected to say the key is required. Google Books has
  since also been observed alternating 200 and 503 on consecutive requests, which turned healthy
  lookups into 404s — handled by a bounded single retry on transient statuses, taking a rapid-fire
  sample from flapping to 9 of 10 succeeding.
- **Open Library became unreachable at the TCP layer** — no handshake, every host under the domain,
  while `archive.org` on the same infrastructure stayed up. This is *not* rate limiting, though a
  required `User-Agent` header identifying the application was added along the way since their API
  documentation asks for one. Because identity comes from Open Library, every lookup returned 404.
  Handled by `ALLOW_IDENTITY_FALLBACK`, **off by default**, which sources identity from Google Books
  instead and honestly reports `sources: ["google_books"]` so the result never claims a contribution
  Open Library did not make. It is a stopgap to be deleted when Open Library returns — Google Books
  has noisier identity data, which is the reason the source split exists at all.

**Rule 1 does not fully hold for generated descriptions.** When no publisher description exists, the
model writes one — and in testing it included details about the book that were not in the tool
output. The system prompt forbids this explicitly and compliance is only partial. The affected
result is flagged with `description_is_generated: true` and `llm` in `sources`, so a reader is told
the prose is authored rather than sourced, but the tension between the no-memory rule and permitting
an authored description is real and unresolved. It is analysed in
[ADR-0005](docs/adr/0005-agent-without-autonomous-tool-calling.md).
