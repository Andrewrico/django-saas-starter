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
| `POST /api/auth/login/mfa/` | `{code}` completes the pending MFA login, using the same session cookie |
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

## Social sign-in (Google, GitHub)

Both providers are installed and **off until their keys are set**. A provider with keys shows a
"Continue with ..." button on `/login/` and `/signup/`; one without keys has no button and its
URLs return 404.

| Provider | Env vars | Redirect URI to register |
|---|---|---|
| Google | `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | `https://<host>/accounts/google/login/callback/` |
| GitHub | `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET` | `https://<host>/accounts/github/login/callback/` |

- Google: Google Cloud console, APIs & Services, Credentials, "OAuth client ID" (Web
  application). Scopes: `openid email profile`.
- GitHub: Settings, Developer settings, OAuth Apps. Scopes: `read:user user:email`.
- For local testing register `http://localhost:8000/accounts/<provider>/login/callback/`.

Behaviour (see the `SOCIALACCOUNT_*` block in `config/settings.py`):

- Sign-in starts with a POST carrying the CSRF token (`SOCIALACCOUNT_LOGIN_ON_GET = False`), so
  another site cannot start a login with a link.
- A new user is created with the provider's email and name and no usable password (they can set
  one with password reset). If the provider has no email, allauth asks for one.
- **No silent account linking.** If the email already belongs to a password account, the provider
  login does not sign into it (`SOCIALACCOUNT_EMAIL_AUTHENTICATION = False`). The user signs in
  with their password and connects the provider at `/accounts/3rdparty/`.
- Provider access tokens are not stored (`SOCIALACCOUNT_STORE_TOKENS = False`).

Another provider: add `"allauth.socialaccount.providers.<name>"` to `INSTALLED_APPS` and an entry
to `SOCIAL_PROVIDER_DEFAULTS`; the env-var pattern and the buttons follow automatically. Apps can
also be added in the Django admin (Social applications) instead of env vars.
`tests/test_social.py` covers the GitHub flow end to end with the provider's HTTP calls mocked.

## Two-factor authentication

Set `MFA_ENROLLMENT_ENABLED=true` to allow users to enrol an authenticator from the security
link on `/account/`. Run `python manage.py migrate` first (this includes allauth's MFA
migrations). Users must verify their primary email before enrolling. The setup page gives a
manual setup key: use a time-based account with six digits and a 30-second interval. Activation
generates recovery codes; save them somewhere private. Recovery codes are single-use and can
be regenerated from the security page. Sensitive changes require recent reauthentication.
Nothing changes for users who have not enrolled.

Enrolment defaults to off. Turning it off later **does not disable existing MFA**: its login
stages are always installed. `/login/`, `/accounts/login/`, linked social sign-in, and the JSON
API all run allauth's staged login. The admin redirects to this same login flow. No authenticated
session is issued until the second factor succeeds. Trusted-browser bypass is disabled.

The API returns HTTP 401 with `{"mfa_required": true, "detail": "..."}` after a correct password
for an enrolled account. Retain the pending session cookie and send a CSRF-protected JSON
`POST /api/auth/login/mfa/` with `{"code": "123456"}` (or a recovery code). The response is the
usual user JSON on success; a wrong/replayed code is HTTP 400. Both steps are throttled, and
allauth also limits MFA failures per user. Pending logins expire after allauth's login timeout
(default 15 minutes); missing or expired challenges require starting again. Fetch a fresh CSRF
token after successful login, since Django rotates it. Clients cannot supply a user ID or backend.

TOTP replay counters are stored in the database under a user-row lock, so replay protection
survives worker changes and cache eviction. Recovery codes use allauth's database-backed
single-use tracking. MFA secrets are encrypted using a key derived from `SECRET_KEY`; protect
that key and database backups. `SECRET_KEY_FALLBACKS` supports decrypting records during key
rotation (retain old keys until authenticators have been re-enrolled). MFA imports cryptography
only when encrypting/decrypting a secret. Install the declared `django-allauth[mfa]` extra;
allauth imports its WebAuthn dependency even when only TOTP/recovery codes are enabled.

## Change email

Use **Manage email addresses** on `/account/` (`/accounts/email/`). After reauthenticating, add
the new address, open its emailed confirmation link, confirm it with a POST, then select **Make
primary**. Unverified addresses can never be promoted, even when the old address is unverified.
allauth updates `User.email` when the verified address becomes primary. Addresses belonging to
another account cannot be taken; custom signup also checks secondary allauth addresses.

Email confirmation never signs a user in. MFA users may add an address after recent
reauthentication; the starter replaces allauth's blanket MFA add-email prohibition with this
check while retaining its verified-email requirement for enrolment. Confirmation links are
signed and expire under allauth's settings. In production configure a working email backend.

Token authentication is not included.
