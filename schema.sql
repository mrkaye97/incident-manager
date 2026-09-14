CREATE EXTENSION IF NOT EXISTS btree_gist;

CREATE TABLE IF NOT EXISTS team_member (
    id BIGINT PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    name TEXT NOT NULL,
    slack_user_id TEXT UNIQUE,
    slack_handle TEXT,
    pushover_user_key TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TYPE timerange AS RANGE (
    SUBTYPE = TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS on_call_rotation (
    id BIGINT PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    name TEXT NOT NULL UNIQUE,
    member_ids BIGINT[] NOT NULL,
    period_days INTEGER NOT NULL CHECK (period_days > 0),
    anchor TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT rotation_members_nonempty CHECK (array_length(member_ids, 1) >= 1)
);

CREATE TABLE IF NOT EXISTS on_call_override (
    id BIGINT PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    team_member_id BIGINT NOT NULL REFERENCES team_member(id),
    shift timerange NOT NULL,
    escalation_priority INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT on_call_override_escalation_priority_shift_exclusion_constraint
        EXCLUDE USING GIST (escalation_priority WITH =, shift WITH &&)
);

CREATE TYPE incident_status AS ENUM ('OPEN', 'RESOLVED');

CREATE TABLE IF NOT EXISTS incident (
    id UUID PRIMARY KEY DEFAULT uuidv7(),
    name TEXT NOT NULL,
    slack_channel_id TEXT NOT NULL,
    lead BIGINT NOT NULL REFERENCES team_member(id),
    status incident_status NOT NULL DEFAULT 'OPEN',
    start_time TIMESTAMPTZ NOT NULL DEFAULT now(),
    end_time TIMESTAMPTZ,
    description TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS page (
    id BIGINT PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    incident_id UUID REFERENCES incident(id),
    team_member_id BIGINT NOT NULL REFERENCES team_member(id),
    paged_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    pushover_receipt TEXT UNIQUE,
    pushover_expires_at TIMESTAMPTZ,
    acknowledged_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS incident_action_item (
    id BIGINT PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    incident_id UUID NOT NULL REFERENCES incident(id),
    description TEXT NOT NULL,
    is_completed BOOLEAN NOT NULL DEFAULT FALSE,
    assignee_team_member_id BIGINT REFERENCES team_member(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS alert (
    id BIGINT PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    title TEXT NOT NULL,
    state TEXT,
    body TEXT,
    source_url TEXT,
    incident_id UUID REFERENCES incident(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS alert_title_idx ON alert (title);

CREATE OR REPLACE VIEW incident_summary AS
SELECT
    i.id, i.name, i.status, i.slack_channel_id, i.description, i.start_time, i.end_time,
    i.lead AS lead_id,
    tm.name AS lead_name,
    ai.open_action_items,
    ai.total_action_items
FROM incident i
JOIN team_member tm ON tm.id = i.lead
CROSS JOIN LATERAL (
    SELECT
        count(*) FILTER (WHERE NOT is_completed) AS open_action_items,
        count(*) AS total_action_items
    FROM incident_action_item
    WHERE incident_id = i.id
) ai;

CREATE OR REPLACE VIEW action_item_detail AS
SELECT
    ai.id, ai.incident_id, i.name AS incident_name, ai.description, ai.is_completed,
    ai.assignee_team_member_id AS assignee_id, tm.name AS assignee_name, ai.created_at
FROM incident_action_item ai
JOIN incident i ON i.id = ai.incident_id
LEFT JOIN team_member tm ON tm.id = ai.assignee_team_member_id;

CREATE TABLE IF NOT EXISTS session (
    token_hash TEXT PRIMARY KEY,
    team_member_id BIGINT NOT NULL REFERENCES team_member(id),
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
