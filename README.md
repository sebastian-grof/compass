<p align="center">
  <em>Your tournaments. One tap on your Tabbycat Private URL</em>
</p>

---

Compass is a shortcut. Sign in once, and you see exactly the tournaments you're judging right
now. One tap and you're on your [Tabbycat](https://github.com/TabbycatDebate/tabbycat)
private page. Add it to your phone's home screen and it feels like a native app.

The best part is what you don't have to do. Nobody pastes links into a
spreadsheet. Compass reads them straight from Tabbycat and quietly matches each
private URL to the right person by email, so the list is always current and
always yours.

## What you get

- **One tap to your round.** No emails, no copy-pasting links.
- **Nothing to set up as an adjudicator.** An admin adds you; your tournaments
  just appear.
- **Lives on your phone.** Installable PWA, fullscreen, offline-friendly shell.
- **Sign in once.** Email + password, with "remember me".
- **Built on trust.** API tokens and private URL keys are encrypted at rest, and
  you can only ever land on your private URL.

## How it works

Compass doesn't touch Tabbycat, no fork, no plugin. It's a small standalone app
that reads Tabbycat's normal REST API with a staff token and does one job well:

1. A sync job pulls the active tournaments and their adjudicators.
2. For every adjudicator email that matches a Compass account (or one of its
   aliases), it stores that person's private URL key for that tournament.
3. The home screen lists your active tournaments and taps through to the stored
   private page.

That sync is the heart of the whole thing, so it's built to be safe to run often
and hard to break. Run it every few minutes / hours with a scheduler.
**[Keep it in sync](SETUP.md#keep-it-in-sync)** for the details.

## Get it running

Running Compass locally takes about a minute:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env                         # optional; sensible defaults work as-is
.venv/bin/python manage.py migrate
.venv/bin/python manage.py createsuperuser
.venv/bin/python manage.py runserver
```

Connecting a Tabbycat instance, adding adjudicators, scheduling the sync, and
deploying to production are all walked through in **[SETUP.md](SETUP.md)**.

## A Note On Security

Private URL keys are unguessable secrets: they are a person's identity in a
tournament. Compass treats them that way: they're encrypted at rest and never
shown in the admin, templates, logs, or the service-worker cache. A signed-in
user can only ever be redirected to their own URL, and authenticated pages and
redirects are sent `no-store`.

## License

Compass is released under the **GNU Affero General Public License v3.0**
(AGPL-3.0) — see [LICENSE](LICENSE).

It's built to run as a hosted service, so the AGPL's network clause matters: if
you run a modified version for other people to use, you have to make your
modified source available to them.

Built and maintained by **Sebastian Grof** — originally for the Slovak Debating
Association (SDA), and free for any debate community to run.
