# Incident Manager

(Name pending :P)

This is a barebones, [Hatchet](https://hatchet.run)-backed incident management tool for Slack. Intended to only do a few things:

1. Create a basic on call rotation
2. Create Slack channels for managing incidents
3. Page the on-call engineer when needed

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

Sign-in is "Sign in with Slack" (OpenID Connect); any full member of the workspace can sign in, and
signing in adds them to the team roster.
In the Slack app, add `https://localhost:3000/api/auth/callback` as a Redirect URL and the
`openid`, `email`, `profile` user scopes, then set `SLACK_CLIENT_ID` / `SLACK_CLIENT_SECRET`.
Set `APP_URL` (and `API_URL`, if the API is on a different origin) when deploying.

To dos:

1. Ingest webhooks from alerting tools (HyperDX) to create incidents from (and auto-page on critical)
2. Use some sort of app (like Pushover maybe) to enable pages to bypass DND
3. Allow for updating incident descriptions
4. Allow for creating, reading, etc. post-incident action items (with assignees)
5. Some kind of "IaC" to set up the necessary Hatchet webhooks
