# Incident Manager

(Name pending :P)

This is a barebones, [Hatchet](https://hatchet.run)-backed incident management tool for Slack. Intended to only do a few things:

1. Create a basic on call rotation
2. Create Slack channels for managing incidents
3. Page the on-call engineer when needed

To dos:

1. Ingest webhooks from alerting tools (HyperDX) to create incidents from (and auto-page on critical)
2. Use some sort of app (like Pushover maybe) to enable pages to bypass DND
3. Allow for updating incident descriptions
4. Allow for creating, reading, etc. post-incident action items (with assignees)
5. Some kind of "IaC" to set up the necessary Hatchet webhooks
