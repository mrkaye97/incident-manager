# Incident Manager

(Name pending :P)

This is a barebones, [Hatchet](https://hatchet.run)-backed incident management tool for Slack. Intended to only do a few things:

1. Create a basic on call rotation (with overrides)
2. Create Slack channels for managing incidents, and track action items and affected customers
3. Page the on-call engineer when needed (Slack plus Pushover, with escalation until acknowledged)
4. Open incidents automatically from HyperDX alerts

## Running locally

```sh
docker compose up -d        # postgres on :5499 (apply schema.sql once)
make worker                 # hatchet worker: slack commands, alerts, paging
make api                    # FastAPI on :8000
make frontend               # https://localhost:3000 (mkcert cert via `make certs`), proxies /api to :8000
```

The web UI covers incidents, action items, paging, the on-call schedule, rotation config,
overrides, and the team roster. After changing API models, run `make openapi` to regenerate
the frontend types.

The frontend is a standalone static app. By default it calls the API on its own origin under
`/api` (the dev server proxies that); if the API lives elsewhere, set `VITE_API_URL` at build time
and add the frontend's origin to the API's `CORS_ORIGINS` (a JSON list).

Set `STATUS_PAGE_URL` to link to the status page (defaults to a placeholder).

SQL lives in `queries/*.sql` (loaded with [aiosql](https://github.com/nackjicholson/aiosql)),
with `-- record_class:` naming the Pydantic model in `db.py` each row maps to. `db.py` wraps
each query in a typed function. `make test` prepares every query against a fresh database built
from `schema.sql` and checks result columns and types against those models.

On startup the worker creates its Hatchet webhooks if they don't exist (existing ones are left
untouched) and logs their URLs: `incident-bot-slack-commands` (Slack slash command Request URL),
`incident-bot-slack-interactivity` (Slack Interactivity Request URL), and `incident-bot-hyperdx`
(HyperDX webhook; configure HyperDX to send `HYPERDX_WEBHOOK_SECRET` in an `X-Webhook-Secret`
header). Requires `SLACK_SIGNING_SECRET` and `HYPERDX_WEBHOOK_SECRET`.

Sign-in is "Sign in with Slack" (OpenID Connect); any full member of the workspace can sign in, and
signing in adds them to the team roster.
In the Slack app, add `https://localhost:3000/api/auth/callback` as a Redirect URL and the
`openid`, `email`, `profile` user scopes, then set `SLACK_CLIENT_ID` / `SLACK_CLIENT_SECRET`.
Set `APP_URL` (and `API_URL`, if the API is on a different origin) when deploying.

Pages go out over Slack, and over [Pushover](https://pushover.net) (emergency priority, so they
bypass Do Not Disturb) for members with a Pushover user key. Set `PUSHOVER_APP_TOKEN` to enable it;
an unacknowledged page escalates through the on-call list every five minutes.
