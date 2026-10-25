# Authentication

## Model

`accounts.User` uses `email` as `USERNAME_FIELD`; there is no username. Emails are stored lower
case and are unique case-insensitively (database constraint on `Lower(email)`).

## JSON API (session cookies)

| Method and path | Purpose |
|---|---|
| `GET /api/auth/csrf/` | Sets the `csrftoken` cookie and returns `{"csrfToken": ...}` |
| `POST /api/auth/signup/` | `{email, password, name?}` creates the user and (unless verification is mandatory) signs in |
| `POST /api/auth/login/` | `{email, password}` |
| `POST /api/auth/logout/` | Ends the session |
| `GET/PATCH /api/auth/me/` | Read or update `name` |
| `DELETE /api/auth/me/` | `{password}` deletes the account and its data |

Send `X-CSRFToken` on every POST/PATCH/DELETE. `signup` and `login` are throttled by
`THROTTLE_AUTH` (default `10/min` per IP). Passwords use Django's validators.

```bash
curl -c jar -b jar localhost:8000/api/auth/csrf/ >/dev/null
TOKEN=$(awk '/csrftoken/ {print $7}' jar)
curl -c jar -b jar -H "X-CSRFToken: $TOKEN" -H 'Content-Type: application/json' \
  -d '{"email":"me@example.com","password":"a-long-unusual-password"}' localhost:8000/api/auth/signup/
```

## Pages

`/login/`, `/signup/`, `/account/` (profile, plan), `/account/delete/`. django-allauth serves the
rest under `/accounts/` (password reset, change password, email confirmation). Its own
`/accounts/login/` and `/accounts/signup/` also exist; the site links to the pages above.

## Email verification

`ACCOUNT_EMAIL_VERIFICATION`:

- `none`: no verification mail; a welcome mail is sent.
- `optional` (default): a confirmation mail is sent; users can sign in unverified.
- `mandatory`: signup does not sign in, and login (API and page) is refused until verified.

Mail goes through the configured `EMAIL_BACKEND` (console in development).

## Social providers (stub)

`allauth.socialaccount` is installed with no providers. To add one, for example Google: add
`"allauth.socialaccount.providers.google"` to `INSTALLED_APPS`, define `SOCIALACCOUNT_PROVIDERS`
(scopes, app credentials from env), register the redirect URI
`https://<host>/accounts/google/login/callback/` with the provider, and add a "Sign in with" link
to the login template. See the [allauth docs](https://docs.allauth.org). This path is not
exercised by the test suite.

## Not included

Email change, MFA and token authentication are on the roadmap.
