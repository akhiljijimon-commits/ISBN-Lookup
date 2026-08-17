# 0005 — An agent without autonomous tool calling

**Status:** Accepted. Supersedes the open risks recorded in
[ADR-0003](0003-self-hosted-vllm-qwen.md), which are now resolved with a split verdict.

**Date:** 2026-08-17

## Context

ADR-0003 recorded two capabilities the design assumed and the deployment did not guarantee:
structured output, and tool calling. Both have now been tested against the Surfgreen vLLM
endpoint.

**Structured output works.** `response_format: {"type": "json_object"}` is accepted and the model
returns schema-conforming JSON.

**Autonomous tool calling does not.** The server was not started with `--enable-auto-tool-choice`,
so the model cannot be given tools and left to decide when to call them.

This is exactly the second fallback ADR-0003 anticipated: *"orchestrate the sources from Python in
a fixed sequence, invoking the model once at the end."* That fallback is now the design, not a
contingency. MCP (`mcp-open-library`) is out of scope for this change and remains a later optional
enhancement — with tool calling unavailable there is nothing for an MCP server to plug into.

## Decision

`backend/app/agent.py` runs a Pydantic AI agent over tool output that Python has already
fetched. `backend/app/sources.py` is unchanged and remains the only code that talks to upstreams.

### Prompted output mode, pinned explicitly

Pydantic AI's default structured-output mode is `'tool'` — the model returns the result *by calling
a tool* (`pydantic_ai/profiles/__init__.py:224`). On this deployment that fails outright. So:

- `output_type=PromptedOutput(BookInfo, template=OUTPUT_TEMPLATE)`.
- A custom `ModelProfile(supports_json_object_output=True, default_structured_output_mode='prompted')`.
  Without that flag prompted mode sends *no* `response_format` at all: `models/openai.py:1108` only
  emits `{'type': 'json_object'}` when the profile advertises support, and the base default is
  `False`. Setting it is what makes the wire format match what was verified live.

### One system message, not two

The endpoint rejects a second system message:

```
400 — {'message': 'System message must be at the beginning.', 'type': 'BadRequestError'}
```

Pydantic AI emits `instructions=` as one system message and `PromptedOutput`'s schema block as
another, producing `['system', 'system', 'user']`. The fix is to carry the rule-1 prompt inside
`PromptedOutput`'s own `template` (which substitutes `{schema}`) and pass no `instructions`,
yielding `['system', 'user']`. This is a deployment constraint, not a stylistic choice, and it is
why the prompt lives where it does.

### The ISBN must be in the prompt

The first live run failed validation with `"isbn": null`. The model was refusing to invent an ISBN
it had not been given — rule 1 working correctly — but `BookInfo.isbn` is a required `str`. The
prompt now states the ISBN that was looked up. Python overwrites the field regardless.

### Field ownership

The agent returns a full `BookInfo`, but Python re-asserts every field it already knows:

| Field | Owner | Why |
|---|---|---|
| `title`, `authors`, `cover_url`, `description` | model | The normalisation and writing the agent exists for |
| `isbn` | Python | Already normalised (FR-04) |
| `price`, `currency` | Python | The `Decimal` came from Google Books; a model retyping it is pure hallucination surface |
| `sources` | Python | Provenance must not be self-asserted (FR-11, NFR-05) |
| `description_is_generated` | Python | True iff Google Books supplied no description (FR-10) |

A fabricated price or a self-declared `sources: ["llm"]` is therefore *structurally impossible*,
not merely forbidden by the prompt. `test_model_cannot_fabricate_price_or_provenance` proves it by
having the model attempt exactly that and asserting the overrides win.

### Degradation

`USE_AGENT` gates the path and defaults on. If the agent raises for any reason — endpoint
unreachable, malformed output, retries exhausted — the request logs a warning and falls back to the
deterministic assembly. An unreachable LLM costs normalisation and a written description, not the
lookup. `USE_AGENT=0` selects the deterministic path outright.

## Consequences

### Rule 1 does not fully hold for the generated description

This is the finding that matters most, and it is not solved.

Given tool output containing only a title, an author, a price and a currency, the model was asked
to write a description. It produced:

> Clean Code is a book by Robert C. Martin that presents a set of best practices for writing clean,
> maintainable code. **It covers topics such as naming conventions, formatting, and error
> handling** to help developers create software that is easy to read and understand.

The emphasised clause is not in the tool output. It comes from the model's memory of the book. The
system prompt forbids this explicitly — it names structure, chapters, themes, reception and
biography as off limits, and says a short plain description is correct — and the model complied
only partially. Strengthening the wording reduced the leakage; it did not remove it.

**This is a genuine tension between CLAUDE.md rule 1 and FR-10, not a bug.** Rule 1 says the model
never supplies book facts from memory. FR-10 permits the model to author a description. A
description built strictly from a title and an author can say almost nothing beyond restating them;
anything that reads like a description is, in part, remembered. The two requirements cannot both be
fully satisfied by prompting.

What holds today: `description_is_generated` is `true` and `llm` appears in `sources` whenever this
happens, so the reader is told the prose is authored rather than sourced. That is precisely FR-10's
purpose, and NFR-05's auditability is intact — a reviewer can see which fields to distrust.

Three ways to close it properly, none taken here:

1. **Accept it**, and reword rule 1 to scope the prohibition to the structured fields, where it is
   now structurally enforced. Honest, and matches what the system actually does.
2. **Template the description in Python** — no model involvement, no leakage, and no reason to call
   an LLM for this project at all.
3. **Constrain harder**, e.g. requiring every noun phrase to appear in the tool output. Brittle, and
   likely to produce prose no one wants to read.

This should be decided before US-07, which is the story that formally delivers FR-09 and FR-10.

### Latency

Model calls took **2.7–4.6 seconds** against the live endpoint. NFR-01 budgets 5 seconds p95 for
the *whole* lookup, and the upstream fetches cost about a second on top. **The agent path is at or
over budget.** Either NFR-01 is renegotiated, the sources are fetched concurrently, or the agent
runs only when it has something to do — the description case — rather than on every request.

### Identity fields still pass through the model

`title`, `authors` and `cover_url` are model output, so a hallucinated title remains possible in
principle. Only the system prompt prevents it. A cheap future guard: reject output whose title
bears no resemblance to the tool title.

### Testing

Six new tests in `backend/tests/test_agent.py`, all offline: upstreams stubbed through the
`_new_client` seam, the LLM replaced with `FunctionModel`. No network call and no credential is
needed, per NFR-06. `test_spike_smoke.py` now pins `USE_AGENT=0`, since it asserts the
pre-agent shape and would otherwise reach the live endpoint.

## What changes if the server flags are enabled

If vLLM is restarted with `--enable-auto-tool-choice` and a tool-call parser for the model family:

- `output_type=BookInfo` can drop `PromptedOutput` and use the default `'tool'` mode, and the custom
  `ModelProfile` becomes unnecessary.
- `mcp-open-library` can be attached as an MCP server, and the Google Books call becomes an agent
  tool. The agent then decides which sources to consult.
- The Python orchestration in `main.py` becomes the *fallback* rather than the design — worth
  keeping, since it is also what runs when the LLM is unreachable.
- The single-system-message constraint should be re-tested; it is a property of this deployment's
  request validation, not of tool calling, and may well persist.

None of that changes the field-ownership table. Python should keep owning provenance regardless of
how the facts are fetched, because that is what makes FR-09 checkable rather than trusted.
