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
make frontend               # vite dev server on :3000
```

The web UI covers incidents, action items, paging, the on-call schedule, rotation config,
overrides, and the team roster. After changing API models, run `make openapi` to regenerate
the frontend types.

The frontend is a standalone static app: set `VITE_API_URL` at build time (defaults to
`http://localhost:8000`), and add its origin to the API's `CORS_ORIGINS` (a JSON list).

Set `STATUS_PAGE_URL` to link to the status page (defaults to a placeholder).

SQL lives in `queries/*.sql` (loaded with [aiosql](https://github.com/nackjicholson/aiosql)),
with `-- record_class:` naming the Pydantic model in `db.py` each row maps to. `db.py` wraps
each query in a typed function. `make test` prepares every query against a fresh database built
from `schema.sql` and checks result columns and types against those models.

There is no auth on the API or UI yet.

To dos:

1. Ingest webhooks from alerting tools (HyperDX) to create incidents from (and auto-page on critical)
2. Use some sort of app (like Pushover maybe) to enable pages to bypass DND
3. Allow for updating incident descriptions
4. Allow for creating, reading, etc. post-incident action items (with assignees)
5. Some kind of "IaC" to set up the necessary Hatchet webhooks
