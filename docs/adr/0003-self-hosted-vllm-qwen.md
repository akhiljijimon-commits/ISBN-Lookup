# 0003 — Self-hosted vLLM endpoint serving Qwen3.6 as the model provider

**Status:** Accepted, with two open risks recorded below that must be resolved before US-05
begins.

**Date:** 2026-08-15

> Numbering note: this is the first ADR in the repository. `0001` and `0002` do not exist.
> The number reflects the position this decision holds in the sequence, not a pair of
> missing documents — the two earlier slots are left free for the decisions that preceded
> it in practice (the overall stack, and the split of fields between Open Library and Google
> Books) should anyone choose to write them up retrospectively.

## Context

The language model for this project is provided by Surfgreen GmbH as a self-hosted vLLM
endpoint serving `nvidia/Qwen3.6-35B-A3B-NVFP4`. The endpoint is OpenAI-compatible and
configured with `max_model_len` 32768.

This was given, not chosen. No evaluation of alternative providers or models took place,
and no decision here should be read as a claim that this model is better suited to the task
than another. The relevant question was never "which model" but "how do we build against
the one we have".

Two properties of that endpoint shape everything downstream. It is *self-hosted*, so its
feature surface is whatever this particular deployment was built and configured to expose,
rather than the documented, versioned surface of a commercial API. And Qwen3.6 is a
*reasoning* model, which by default emits a thinking block ahead of its answer.

## Decision

Access the endpoint through Pydantic AI's OpenAI-compatible provider, pointing `base_url` at
the Surfgreen deployment. Configuration comes from `LLM_API_KEY`, `LLM_BASE_URL` and
`LLM_MODEL` in `.env`, per NFR-03; no endpoint URL or model name is hardcoded.

Pass `chat_template_kwargs` `{"enable_thinking": false}` on requests. Qwen3.6's thinking
output interferes with structured extraction: the reasoning preamble is not part of the
requested schema, and leaving it enabled means the response must be salvaged from around it.
The agent's job here is narrow — normalise tool output and write a description — and it does
not benefit from extended reasoning enough to justify parsing around it.

## Consequences

### Two open risks, to be confirmed with Surfgreen before US-05

The design as specified depends on two model capabilities that a hosted commercial API
guarantees and a self-hosted vLLM deployment does not. Neither has been verified against
this endpoint. Both are recorded here as open, not resolved.

**1. Structured output.** The intended shape is `output_type=BookInfo`, with Pydantic AI
constraining the model to the contract in `backend/app/models.py`. This relies on the
deployment exposing a guided-decoding or JSON-schema mechanism, and on it working through
the OpenAI-compatible surface. A vLLM server may be built without it, may expose it under a
parameter name the OpenAI-compatible provider does not send, or may support it unreliably
for a NVFP4-quantised model.

*Fallback if unavailable:* build `BookInfo` in Python from the tool results and use the model
only to produce the `description` string, validating its output with Pydantic and retrying
on failure. This costs the convenience of `output_type`, not correctness.

**2. Tool calling.** The agent is specified to obtain every fact through tool calls
(FR-09), which assumes the model reliably emits well-formed tool-call requests and that the
deployment's chat template supports them. Tool-calling support in self-hosted vLLM depends on
the server being started with a tool-call parser matching the model family; it is a
deployment flag, not an inherent model property.

*Fallback if unavailable:* move orchestration into application code. Call `mcp-open-library`
and Google Books directly from Python in a fixed sequence, and invoke the model once, at the
end, with the retrieved data.

Both fallbacks converge on the same shape: less agency in the model, more in deterministic
Python. This is a smaller loss than it first appears, because CLAUDE.md rule 1 already
confines the model to normalising tool output and writing a description. The product's
central promise — that no fact originates from model memory — is *easier* to guarantee under
the fallbacks, not harder. What is lost is the agentic structure this repository also exists
to demonstrate, which matters to the secondary audience in `docs/01-vision.md`.

**These risks must be closed before US-05 (identity from Open Library) is started**, because
US-05 is the first story whose implementation depends on the answer. Confirming them costs
one conversation with the provider and one probe request against the endpoint; discovering
them during US-05 costs a rewrite of the agent layer.

### Accepted consequences

- **Coupling to vLLM.** `chat_template_kwargs` is not part of the OpenAI API. It is passed
  as a provider extra, so the request path is OpenAI-compatible in shape but vLLM-specific
  in content. Moving to a different backend means revisiting this.
- **A 32768-token context.** Ample for a single book record, but it rules out passing large
  raw upstream payloads wholesale. Tool output should be trimmed to the fields `BookInfo`
  needs before it reaches the model.
- **No vendor SLA.** Availability, latency and version stability are Surfgreen's to manage.
  NFR-01's 5-second p95 and 3-second per-call timeout are budgeted against an endpoint whose
  performance characteristics are not yet measured. The timeout applies to upstream data
  sources; whether the model call needs its own budget is an open question for US-03.
- **Quantisation.** NVFP4 is an aggressive format. Instruction-following and schema
  adherence may be measurably weaker than the same model at higher precision. This is a
  reason to validate model output rather than trust it, which the design does anyway.
- **Tests are unaffected.** NFR-06 requires the suite to run without live upstream calls,
  with tool responses stubbed. That isolation covers the model endpoint too, so none of the
  above risks can make the test suite flaky or environment-dependent.
