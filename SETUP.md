# Setup & running Compass

Everything you need to get Compass running locally, connect it to a Tabbycat
instance, provision adjudicators, and keep it humming in production.

- [Run it locally](#run-it-locally)
- [Connect a Tabbycat instance](#connect-a-tabbycat-instance)
- [Provision adjudicators](#provision-adjudicators)
- [Keep it in sync](#keep-it-in-sync)
- [Install on a phone](#install-on-a-phone)
- [Deploy it](#deploy-it)
- [How it works under the hood](#how-it-works-under-the-hood)

---

## Run it locally

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env                         # optional — the defaults work as-is
.venv/bin/python manage.py migrate
.venv/bin/python manage.py createsuperuser   # email + password; log in to /admin
.venv/bin/python manage.py runserver
```

The admin lives at `/admin/`.

---

## Connect a Tabbycat instance

1. In the Django admin, go to **Core → Tabbycat instances → Add**:
   - **Base URL** — the Tabbycat root, e.g. `https://sda.calicotab.com`
   - **API token** — a staff token (how to mint one is below)
2. Run the **"Sync now"** action on that instance, or run `sync_tabbycat` from
   the command line.

### Minting a Tabbycat API token

Tabbycat auto-creates an API token for every user. To read private URLs and
participant emails, that user must be **staff**, or hold the *view private urls*
and *view participants' contact information* permissions.

On the **Tabbycat** server:

```bash
# Simplest: a dedicated staff user's token (full read access).
python manage.py shell -c "from rest_framework.authtoken.models import Token; \
print(Token.objects.get(user__username='compass-bot').key)"
```

For a tighter scope, make `compass-bot` a **non-staff** user and grant it a
tournament role/group containing only *view private urls* + *view participants'
contact information*, then use its token.

Paste the token into the Compass instance config. It's encrypted at rest.

---

## Provision adjudicators

Accounts are admin-created. Three ways:

- **One at a time** — Admin → Accounts → Users → Add. Set a password, or use the
  *"Send set-password / invite email"* action.
- **In bulk** — a CSV with an `email` column (optional `name`):
  ```bash
  .venv/bin/python manage.py import_adjudicators people.csv --invite
  ```
  New users get a random password; `--invite` emails each of them a
  set-password link.
- **Self-serve** — adjudicators set their own password via the
  *"Set or reset your password"* link on the login page.

You can also let sync auto-provision login-disabled accounts for any Tabbycat
adjudicator email it sees, set `AUTO_CREATE_ADJUDICATOR_ACCOUNTS=True`. Those
people then set a password through the reset flow; no invite mail is sent.

> **Matching is by email** (case-insensitive), and it includes any **email
> aliases** on a user (Admin → Users → inline aliases). So if someone's Tabbycat
> email changes, adding it as an alias keeps their link intact.

---

## Keep it in sync

`sync_tabbycat` is idempotent, so run it on a schedule. A cron entry every five
minutes is plenty:

```cron
*/5 * * * * cd /srv/compass && .venv/bin/python manage.py sync_tabbycat
```

Limit it to one instance with `--instance "SDA"`.

The sync is deliberately cautious: if a token comes back without permission to
read private URLs, it returns no keys — and Compass refuses to prune existing
links rather than wiping everyone's access on a bad token. (See `core/sync.py`.)

---

## Install on a phone

Open the site in mobile Safari or Chrome → **Share / ⋮ → Add to Home Screen**.
It launches fullscreen from the home-screen icon, like a native app.

---

## Deploy it

Set real environment variables (see `.env.example`):

- `DJANGO_SECRET_KEY`, `DJANGO_DEBUG=False`, `DJANGO_ALLOWED_HOSTS`
- `FIELD_ENCRYPTION_KEY` — a dedicated Fernet key. Don't lean on the
  `SECRET_KEY` fallback in production: rotating `SECRET_KEY` would make stored
  tokens and keys unreadable. Generate one with:
  ```bash
  python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
  ```
- `DATABASE_URL` — Postgres (e.g. `postgres://…`)
- `SITE_DOMAIN`, `CSRF_TRUSTED_ORIGINS`, and SMTP `EMAIL_*` for real invite mail

Then:

```bash
.venv/bin/python manage.py collectstatic --noinput
.venv/bin/python manage.py migrate
.venv/bin/gunicorn compass.wsgi
DJANGO_DEBUG=False .venv/bin/python manage.py check --deploy   # should be clean
```

WhiteNoise serves static files. HTTPS/HSTS/secure-cookie settings switch on
automatically when `DJANGO_DEBUG=False`. A `Procfile` is included for
Heroku-style deploys (`release` runs migrations, `web` runs gunicorn).

---

## How it works under the hood

Compass **never forks or modifies Tabbycat**. It's a standalone Django app that
reads Tabbycat's existing REST API:

- `GET /api/v1/tournaments` → tournament `slug`, `name`, `active`, `current_rounds`
- `GET /api/v1/tournaments/<slug>/adjudicators` → adjudicator `email` + `url_key`
  (these private fields are only returned to a staff API token)
- Auth: `Authorization: Token <token>` (DRF TokenAuthentication)

The sync job pulls tournaments and adjudicators. For every adjudicator email that
matches a Compass user (primary email or alias) it stores or updates that user's
`url_key` for that tournament. The app then lists active tournaments and
302-redirects to the stored private URL.

### Project layout

- `compass/` — project settings and URLs; env-driven config (see `.env.example`).
- `accounts/` — the custom **email-login** `User` (no username), `EmailAlias`,
  the login view with remember-me, the password-reset/invite flow, and the
  `import_adjudicators` command.
- `core/` — `TabbycatInstance`, `Tournament`, `PrivateURL` models; the Tabbycat
  API client (`tabbycat.py`); the sync logic (`sync.py`) and `sync_tabbycat`
  command; the adjudicator-facing `home` and `go` views.
- `templates/`, `static/` — the server-rendered UI, PWA manifest, service
  worker, and icons.

### Conventions worth knowing

- **Secrets are encrypted at rest.** `TabbycatInstance.api_token` and
  `PrivateURL.url_key` use `core.fields.EncryptedTextField` (Fernet). Never
  expose `url_key` in admin, templates, logs, or the service-worker cache.
- **Email is the join key.** Matching is case-insensitive and includes
  `EmailAlias`es, so a changed Tabbycat email doesn't break the link.
- **Per-user isolation.** The `go` redirect filters on `user=request.user`, so a
  user can only ever reach their own private URL. Keep it that way.
- **Sync is defensive.** A token lacking permission to read private URLs returns
  no keys, and the sync refuses to prune existing links in that case.
- **The custom user matters.** Always create users via
  `User.objects.create_user(email=…)` and reference the model through
  `settings.AUTH_USER_MODEL` / `get_user_model()`.

### Running the tests

```bash
.venv/bin/python manage.py test
```

There's no live Tabbycat token in development, so the sync tests swap in a fake
`TabbycatClient` that returns sample API payloads (see `core/tests.py`). They
check that tournaments mirror correctly, emails match (including aliases),
`full_url` is right, pruning works, and a key-less token never wipes links.
Auth, redirect, and per-user isolation are covered with Django's test client.
