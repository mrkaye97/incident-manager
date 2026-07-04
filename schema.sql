CREATE EXTENSION IF NOT EXISTS btree_gist;

CREATE TABLE IF NOT EXISTS team_member (
    id BIGINT PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    name TEXT NOT NULL,
    slack_user_id TEXT UNIQUE,
    slack_handle TEXT
);

CREATE TYPE timerange AS RANGE (
    SUBTYPE = TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS on_call_shift (
    id BIGINT PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    team_member_id BIGINT NOT NULL REFERENCES team_member(id),
    shift timerange NOT NULL,
    escalation_priority INTEGER NOT NULL,
    CONSTRAINT on_call_shift_escalation_priority_shift_exclusion_constraint
        EXCLUDE USING GIST (escalation_priority WITH =, shift WITH &&)
);

CREATE TABLE IF NOT EXISTS incident (
    id BIGINT PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    name TEXT NOT NULL,
    slack_channel_id TEXT NOT NULL,
    lead BIGINT NOT NULL REFERENCES team_member(id),
    status TEXT NOT NULL DEFAULT 'OPEN' CHECK (status IN ('OPEN', 'RESOLVED')),
    start_time TIMESTAMPTZ NOT NULL DEFAULT now(),
    end_time TIMESTAMPTZ,
    description TEXT
);

CREATE TABLE IF NOT EXISTS page (
    id BIGINT PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    incident_id BIGINT REFERENCES incident(id),
    team_member_id BIGINT NOT NULL REFERENCES team_member(id),
    paged_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
