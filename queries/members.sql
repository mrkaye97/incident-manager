-- name: member_id_by_slack_id(slack_user_id)$
SELECT id FROM team_member WHERE slack_user_id = :slack_user_id;


-- name: upsert_member(name, slack_user_id, slack_handle)$
INSERT INTO team_member (name, slack_user_id, slack_handle)
VALUES (:name, :slack_user_id, :slack_handle)
ON CONFLICT (slack_user_id)
DO UPDATE SET name = EXCLUDED.name, slack_handle = EXCLUDED.slack_handle
RETURNING id;


-- name: list_members()
-- record_class: Member
SELECT id, name, slack_user_id, slack_handle, pushover_user_key
FROM team_member
ORDER BY name;


-- name: get_member(member_id)^
-- record_class: Member
SELECT id, name, slack_user_id, slack_handle, pushover_user_key
FROM team_member
WHERE id = :member_id;


-- name: existing_member_ids(member_ids)
SELECT id FROM team_member WHERE id = ANY(:member_ids::BIGINT[]);


-- name: create_member(name, slack_user_id, slack_handle, pushover_user_key)^
-- record_class: Member
INSERT INTO team_member (name, slack_user_id, slack_handle, pushover_user_key)
VALUES (:name, :slack_user_id, :slack_handle, :pushover_user_key)
RETURNING id, name, slack_user_id, slack_handle, pushover_user_key;


-- name: update_member(member_id, name, slack_user_id, slack_handle, pushover_user_key)^
-- record_class: Member
UPDATE team_member
SET
    name = :name,
    slack_user_id = :slack_user_id,
    slack_handle = :slack_handle,
    pushover_user_key = :pushover_user_key,
    updated_at = now()
WHERE id = :member_id
RETURNING id, name, slack_user_id, slack_handle, pushover_user_key;


-- name: get_member_by_slack_id(slack_user_id)^
-- record_class: Member
SELECT id, name, slack_user_id, slack_handle, pushover_user_key
FROM team_member
WHERE slack_user_id = :slack_user_id;
