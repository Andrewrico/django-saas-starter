# Billing

Billing is **off by default**. Every user is on the free plan and no Stripe code runs.

## Switch

`billing_enabled()` is true only when `BILLING_ENABLED=true` **and** `STRIPE_SECRET_KEY` **and**
`STRIPE_WEBHOOK_SECRET` are set. Otherwise checkout, portal and the webhook return 404, and the
`stripe` package is never imported.

## Plans

`billing.Plan` has `slug`, `name`, `limits` (JSON, e.g. `{"max_items": 20}`), `stripe_price_id`.
Migrations seed `free` (20 items) and `pro` (1000 items, no price id, so not purchasable). The
database is the source of truth: edit them in the admin or add your own. Use limits in code with
`get_plan(user)` / `get_limit(user, "max_items")`.

## Enable Stripe

1. In Stripe (test mode first) create a Product with a recurring Price.
2. In the admin, set that Price id on the `pro` plan.
3. Set `BILLING_ENABLED=true`, `STRIPE_SECRET_KEY`, and the `BILLING_*_URL` settings.
4. Add a webhook endpoint `https://<host>/api/billing/webhook/` for at least
   `checkout.session.completed` and `customer.subscription.created|updated|deleted`; copy its
   signing secret to `STRIPE_WEBHOOK_SECRET`. Locally, `stripe listen --forward-to
   localhost:8000/api/billing/webhook/` prints one.
5. Call `POST /api/billing/checkout/` with `{"plan": "pro"}` and redirect the user to the
   returned `url`. Use `POST /api/billing/portal/` for self-service changes and cancellation.

## How it behaves

- A user's plan changes only when the **webhook** reports an `active` or `trialing`
  subscription; returning from Checkout alone grants nothing.
- Webhooks are verified with Stripe's signature and recorded in `StripeEvent`. A replayed event
  id is acknowledged (`duplicate: true`) and not applied again. Processing and recording happen
  in one transaction, so a failure rolls back and Stripe retries.
- Events for unknown customers are logged and ignored. Other event types are recorded only.
- The `prune_stripe_events` job deletes event rows older than 90 days.

## Limits of this implementation

Single subscription per user, one price per plan, no trials/coupons/taxes handling beyond what
Stripe Checkout does, no invoice emails, no seat-based billing. Tests mock Stripe and sign
webhook payloads locally; a live Stripe account has not been exercised by this repository.
