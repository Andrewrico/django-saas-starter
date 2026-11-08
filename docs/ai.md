# AI assistant demo

A small, working example of calling Claude from Django: `/ai/` lets a signed-in user summarize
text, improve writing, or ask a question. Use it as the pattern for your own AI features.

**Off until `ANTHROPIC_API_KEY` is set** (page 404, no nav link, the SDK is never imported).

| Setting | Default | Notes |
|---|---|---|
| `ANTHROPIC_API_KEY` | empty | From the Claude Console; keep it in a secret manager |
| `AI_MODEL` | `claude-opus-5-5` | Any current Claude model id |
| `AI_EFFORT` | `low` | `low`, `medium`, `high`, `xhigh`, `max`: more effort, deeper answers, more tokens |
| `AI_MAX_INPUT_CHARS` | `20000` | Longer input is rejected with a form error |

How it works (`apps/ai/client.py` is the only file that imports `anthropic`):

- One Messages API call per request, the user's text in the user turn and fixed instructions in
  the system prompt (which tells the model to treat the text as content, not instructions).
- Refusals: `fallbacks: "default"` lets the API retry a safety decline on Anthropic's recommended
  fallback model; a final `stop_reason: "refusal"` shows a polite message.
- Errors map to friendly messages (rate limit, auth, server, network); the key is never shown.
- **Daily limit per plan**: plan `limits` key `ai_requests_per_day` (default 10 when unset),
  counted over the last 24 hours, failed attempts included, so a user can't run up your bill.
- **Usage log** `AIRequest` (admin): task, input size, tokens, outcome, model. The user's text
  and the answer are not stored.

Costs are billed to your Anthropic account per token; check current pricing and set a spend
limit in the Claude Console before turning this on in production.
