-- name: list_rotations()
-- record_class: Rotation
SELECT id, level, member_ids, period_days, anchor
FROM on_call_rotation
ORDER BY level;


-- name: upsert_rotation(level, member_ids, period_days, anchor)^
-- record_class: Rotation
INSERT INTO on_call_rotation (level, member_ids, period_days, anchor)
VALUES (:level, :member_ids, :period_days, :anchor)
ON CONFLICT (level) DO UPDATE SET
    member_ids = EXCLUDED.member_ids,
    period_days = EXCLUDED.period_days,
    anchor = EXCLUDED.anchor,
    updated_at = now()
RETURNING id, level, member_ids, period_days, anchor;


-- name: delete_rotation(level)!
DELETE FROM on_call_rotation WHERE level = :level;


-- name: current_oncall()
-- record_class: OnCallEntry
WITH scheduled AS (
    SELECT
        level,
        -- window k covering now() is floor((now - anchor) / period); members take turns by window
        member_ids[
            (
                floor(
                    extract(epoch FROM now() - anchor)
                    / extract(epoch FROM make_interval(days => period_days))
                )::BIGINT % array_length(member_ids, 1)
            )::INT + 1
        ] AS team_member_id
    FROM on_call_rotation
    WHERE now() >= anchor
), active_override AS (
    SELECT level, team_member_id
    FROM on_call_override
    WHERE shift @> now()
), oncall AS (
    SELECT level, team_member_id FROM active_override
    UNION ALL
    SELECT level, team_member_id
    FROM scheduled
    WHERE level NOT IN (SELECT level FROM active_override)
)

SELECT tm.id AS team_member_id, tm.name, tm.slack_user_id, oncall.level
FROM oncall
JOIN team_member tm ON tm.id = oncall.team_member_id
ORDER BY oncall.level;


-- name: list_overrides(start, end)
-- record_class: Override
SELECT
    o.id, o.team_member_id, tm.name AS member_name,
    lower(o.shift) AS start, upper(o.shift) AS "end", o.level
FROM on_call_override o
JOIN team_member tm ON tm.id = o.team_member_id
WHERE o.shift && timerange(:start, :end, '[)')
ORDER BY lower(o.shift), o.level;


-- name: create_override(team_member_id, start, end, level)^
-- record_class: Override
WITH o AS (
    INSERT INTO on_call_override (team_member_id, shift, level)
    VALUES (:team_member_id, timerange(:start, :end, '[)'), :level)
    RETURNING *
)

SELECT
    o.id, o.team_member_id, tm.name AS member_name,
    lower(o.shift) AS start, upper(o.shift) AS "end", o.level
FROM o
JOIN team_member tm ON tm.id = o.team_member_id;


-- name: delete_override(override_id)!
DELETE FROM on_call_override WHERE id = :override_id;
