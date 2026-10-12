# LLM provider facts (research notes, checked 2026-10-12)

The official docs hosts (api-docs.deepseek.com, platform.kimi.ai / platform.moonshot.ai) are blocked from the
build sandbox and also failed DNS from the web-fetch tool, so these facts come from:

- **DeepSeek:** an automatically synced mirror of the official docs (github.com/thevibeworks/deepseek-docs,
  last commit 2026-10-09; each page records its source URL and fetch date 2026-08-02..2026-09-29), cross-checked
  against search-engine excerpts restricted to api-docs.deepseek.com.
- **Kimi / Moonshot:** search-engine excerpts restricted to platform.kimi.ai and platform.moonshot.ai (lower
  confidence: no full page was read). **Re-check https://platform.kimi.ai/docs/pricing/chat before relying on
  the prices.**

## DeepSeek

- OpenAI-compatible base URL: `https://api.deepseek.com` (strict function calling: `https://api.deepseek.com/beta`).
- Models (https://api-docs.deepseek.com/quick_start/pricing, /api/list-models):
  - `deepseek-flash` → DeepSeek-V4.1-Flash (released 2026-09-10). 1M context, max output 384K.
  - `deepseek-v4-pro` → DeepSeek-V4-Pro-0813. Docs are contradictory about Pro being phased out (news 2026-09-10
    says routing to V4.1-Flash from 2026-09-14; changelog says service continues; pricing page still lists it).
  - `deepseek-chat` / `deepseek-reasoner` were retired 2026-07-24 15:59 UTC. `deepseek-v4-flash` still accepted.
- Structured output (https://api-docs.deepseek.com/guides/json_mode, /guides/tool_calls):
  - JSON mode `response_format={"type":"json_object"}`; prompt must contain the word "json" **and an example**;
    may occasionally return empty content; set `max_tokens` high enough.
  - **No** `json_schema` response format (only `text` / `json_object`).
  - Strict function calling is beta: base URL `/beta`, `"strict": true` on every function; all properties
    `required`, `additionalProperties: false`; no `minLength/maxLength/minItems/maxItems`.
- Caching: automatic, best-effort, prefix units. `usage.prompt_cache_hit_tokens`,
  `usage.prompt_cache_miss_tokens` (sum = `prompt_tokens`); `prompt_tokens_details.cached_tokens` = hits.
- Thinking is ON by default (effort `high`). Disable with `extra_body={"thinking": {"type": "disabled"}}` or
  `reasoning_effort="none"`. `tool_choice` required/named → 400 in thinking mode.
- Pricing USD / 1M tokens (effective 2026-09-10 04:00 UTC):

  | | flash off-peak | flash peak | v4-pro off-peak | v4-pro peak |
  |---|---|---|---|---|
  | input cache hit | 0.003 | 0.006 | 0.022 | 0.044 |
  | input cache miss | 0.15 | 0.30 | 0.66 | 1.32 |
  | output | 0.60 | 1.20 | 1.98 | 3.96 |

  Peak hours: **01:00–04:00 and 06:00–10:00 UTC, Monday–Friday** (excl. Chinese public holidays); everything
  else is off-peak (50% of peak). Scheme in effect since 2026-08-16 16:00 UTC.
- Data: Hangzhou DeepSeek AI; privacy policy says personal data is processed and stored in the PRC.

## Moonshot / Kimi

- Base URL `https://api.moonshot.ai/v1` (OpenAI-compatible). Docs moved to platform.kimi.ai.
- Models: `kimi-k2.6` (256K), `kimi-k2.7-code` / `kimi-k2.7-code-highspeed` (256K), `kimi-k3` (1M).
  Old K2 IDs (`kimi-k2-0905-preview`, `kimi-k2-turbo-preview`, `kimi-k2-thinking`, ...) discontinued 2026-05-25;
  `kimi-k2.5` and `moonshot-v1-*` retired 2026-08-31.
- Output limit param: `max_completion_tokens` (`max_tokens` deprecated).
- Structured output: JSON mode (`json_object`, top level must be an object, ask for JSON + example) and
  `json_schema` with `strict: true` (kimi-k2.6 noted as unstable with complex schemas: `$ref`, `oneOf`, may wrap
  output in a code fence).
- Sampling params are fixed — omit `temperature` / `top_p` (kimi-k2.6: 0.6 without thinking, 1.0 with).
  kimi-k2.6 thinking ON by default; disable with `extra_body={"thinking": {"type": "disabled"}}`.
- Caching automatic (previous request > 256 prompt tokens). Reads in `usage.prompt_tokens_details.cached_tokens`.
- Pricing USD / 1M (homepage + caching guide; verify): kimi-k2.6 miss 0.95 / hit 0.16 / out 4.00;
  kimi-k2.7-code 0.95 / 0.19 / 4.00; kimi-k3 3.00 / 0.30 / 15.00.
- Data: Kimi OpenPlatform privacy policy (2025-04-30) names MOONSHOT AI PTE. LTD. (Singapore), servers in
  Singapore; parent company Moonshot AI is Beijing-based. Consumer kimi.com reportedly stores data in China
  (unverified).

## Anthropic / Claude (optional provider)

Source: the `claude-api` skill's bundled documentation (model table cached 2026-10-06), read before writing the
provider, and the installed SDK (`anthropic` 1.13.0) source.

- Model `claude-haiku-5-5` (no date suffix): 1M context, 128K output. **Two rate cards by prompt size:**
  $0.10 / $0.50 per MTok input / output up to 100K prompt tokens, $0.50 / $2.50 above. Cache reads 0.1x input,
  5-minute cache writes 1.25x, 1-hour writes 2x. Judge candidate `claude-opus-5-5`: $4 / $20, cache reads
  $0.20 (0.05x), thinking cannot be disabled (effort is the only lever, default `medium`).
- Structured outputs: `output_config={"format": {"type": "json_schema", "schema": ...}}` on `messages.create`
  (`output_format` is deprecated). Supported: object/array/string/number/integer/boolean/null, `enum`, `const`,
  `anyOf`, `allOf`, `$ref`/`$defs`; `additionalProperties: false` required on every object. **Not supported:
  recursive schemas, numeric bounds, string length bounds, complex array constraints.** Refusals and
  `max_tokens` stops may not match the schema.
- Prompt caching: `cache_control: {"type": "ephemeral"}` on a block (max 4 breakpoints); minimum cacheable
  prefix 512 tokens on Haiku 5.5 (shorter prefixes silently don't cache); usage reports `input_tokens`
  (uncached), `cache_read_input_tokens`, `cache_creation_input_tokens`, `output_tokens`.
- Haiku 5.5 thinking: adaptive and **on by default**; `budget_tokens` → 400; `{"type": "disabled"}` only at
  effort ≤ high; the documented cost lever is `output_config.effort` (default `medium`; we use `low`).
  Thinking tokens bill as output. Responses can start with (empty) thinking blocks — read blocks by type.
- Haiku 5.5 rejects non-default `temperature`/`top_p`/`top_k` and assistant prefill (400).
- `stop_reason == "refusal"` with `stop_details.category`; no server-side fallback for Haiku 5.5.
- Both `anthropic` 1.13 and `openai` 3.29 are built on `httpx2` (not `httpx`): custom/mock HTTP clients must
  be `httpx2.Client`s.
- Reachability from the build sandbox: api.anthropic.com is reachable (401 without a key); api.deepseek.com
  and api.moonshot.ai are refused by the egress proxy (403 on CONNECT).
