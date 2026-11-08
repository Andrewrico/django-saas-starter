# Other payment providers

Only Stripe is built in. This page explains why, and how to add another provider
(Lemon Squeezy, Paddle, Polar, ...) without touching the rest of the app.

## Why not more providers out of the box

Each provider has its own checkout, customer portal, webhook signature scheme and subscription
states. Shipping several means several money paths to test and keep current, for a starter whose
goal is code you can read end to end. Merchant-of-record providers (Lemon Squeezy, Paddle) are
worth it when you want them to handle sales tax and VAT for you; Stripe Tax covers that for Stripe.

## The seam

Feature code never touches a payment provider. It calls `get_plan(user)` / `get_limit(user, key)`
(`apps/billing/limits.py`), which read only the `Subscription` row. A provider's job is to keep
that row correct:

| Piece | Stripe implementation | What a new provider needs |
|---|---|---|
| Client | `apps/billing/stripe_client.py` (lazy import, `billing_enabled()`) | Its SDK or HTTP client, same lazy pattern and on/off switch |
| Checkout | `services.create_checkout_session(user, plan_slug) -> url` | Same signature; map `Plan` to the provider's product/variant id |
| Portal | `services.create_portal_session(user) -> url` | The provider's customer portal URL |
| Webhook | `views.webhook` + `services.construct_event` (signature check) + `StripeEvent` (idempotency) | Verify its signature (usually HMAC of the raw body), store event ids, update `Subscription.status`, `plan`, `current_period_end`, `cancel_at_period_end` |
| Plan mapping | `Plan.stripe_price_id` | A new field, e.g. `Plan.lemonsqueezy_variant_id` |

Map the provider's subscription states onto `active` / `trialing` (counts as paid) and anything
else (falls back to the free plan). Reuse the existing tests in `tests/test_billing.py` and
`tests/test_billing_pages.py` as the checklist: signature rejected, idempotent replay,
downgrade on cancel, unknown customer ignored, endpoints 404 while off.

Run one provider at a time. Supporting two at once needs a `provider` field on `Subscription`.
