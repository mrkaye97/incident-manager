-- name: get_rotation(name)^
-- record_class: Rotation
SELECT id, member_ids, period_days, anchor
FROM on_call_rotation
WHERE name = :name;


-- name: upsert_rotation(name, member_ids, period_days, anchor)^
-- record_class: Rotation
INSERT INTO on_call_rotation (name, member_ids, period_days, anchor)
VALUES (:name, :member_ids, :period_days, :anchor)
ON CONFLICT (name) DO UPDATE SET
    member_ids = EXCLUDED.member_ids,
    period_days = EXCLUDED.period_days,
    anchor = EXCLUDED.anchor,
    updated_at = now()
RETURNING id, member_ids, period_days, anchor;


-- name: current_oncall(escalation_levels)
-- record_class: OnCallEntry
WITH rotation AS (
    SELECT
        member_ids,
        array_length(member_ids, 1) AS num_members,
        LEAST(:escalation_levels::INT, array_length(member_ids, 1)) AS depth,
        -- index of the window covering now(): floor((now - anchor) / period)
        floor(
            extract(epoch FROM now() - anchor)
            / extract(epoch FROM make_interval(days => period_days))
        )::BIGINT AS k
    FROM on_call_rotation
    WHERE now() >= anchor
    LIMIT 1
), active_override AS (
    SELECT escalation_priority, team_member_id
    FROM on_call_override
    WHERE shift @> now()
), oncall AS (
    -- overrides win at their priority (and may add priorities beyond the stack)
    SELECT escalation_priority, team_member_id
    FROM active_override
    UNION ALL
    -- scheduled seat for each priority the round-robin covers, unless overridden
    SELECT
        priority AS escalation_priority,
        (
            SELECT r.member_ids[((r.k + priority - 1) % r.num_members)::INT + 1]
            FROM rotation r
        ) AS team_member_id
    -- depth is bounded by how many members are in the rotation, so this is fine to do
    FROM generate_series(1, (SELECT depth FROM rotation)) AS priority
    WHERE priority NOT IN (SELECT escalation_priority FROM active_override)
)

SELECT tm.id AS team_member_id, tm.name, tm.slack_user_id, oncall.escalation_priority
FROM oncall
JOIN team_member tm ON tm.id = oncall.team_member_id
ORDER BY oncall.escalation_priority;


-- name: list_overrides(start, end)
-- record_class: Override
SELECT
    o.id, o.team_member_id, tm.name AS member_name,
    lower(o.shift) AS start, upper(o.shift) AS "end", o.escalation_priority
FROM on_call_override o
JOIN team_member tm ON tm.id = o.team_member_id
WHERE o.shift && timerange(:start, :end, '[)')
ORDER BY lower(o.shift), o.escalation_priority;


-- name: create_override(team_member_id, start, end, escalation_priority)^
-- record_class: Override
WITH o AS (
    INSERT INTO on_call_override (team_member_id, shift, escalation_priority)
    VALUES (:team_member_id, timerange(:start, :end, '[)'), :escalation_priority)
    RETURNING *
)

SELECT
    o.id, o.team_member_id, tm.name AS member_name,
    lower(o.shift) AS start, upper(o.shift) AS "end", o.escalation_priority
FROM o
JOIN team_member tm ON tm.id = o.team_member_id;


-- name: delete_override(override_id)!
DELETE FROM on_call_override WHERE id = :override_id;
