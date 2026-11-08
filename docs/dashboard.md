# Staff analytics dashboard

Staff-only page at `/admin/dashboard/`, linked from the Django admin index ("Analytics" →
Staff dashboard). Non-staff users are redirected to the admin login.

## What it shows

All numbers come from the database with aggregate queries (no per-user Python loops):

- Total users; signups today / last 7 days / last 30 days
- Daily signups for the last 30 days (CSS bar chart plus a data table)
- Users per plan (Free vs each paid plan; only `active` / `trialing` subscriptions count)
- Active subscriptions and those set to cancel at period end
- Verified vs unverified emails (`allauth.account.EmailAddress`)
- Social vs password-only users (`allauth.socialaccount.SocialAccount`)
- Example `Project`s created in the last 30 days

## Plausible (optional)

Set `PLAUSIBLE_DOMAIN` (e.g. `example.com`) to inject the hosted Plausible script on public
pages and allow `https://plausible.io` in the Content-Security-Policy. Leave it empty (the
default) and nothing changes.
