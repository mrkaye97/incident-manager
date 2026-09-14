-- name: list_open_action_items(incident_id)
-- record_class: ActionItemOption
SELECT id, description
FROM incident_action_item
WHERE incident_id = :incident_id AND is_completed = FALSE
ORDER BY created_at;


-- name: create_action_item(incident_id, description, assignee_member_id)$
INSERT INTO incident_action_item (incident_id, description, assignee_team_member_id)
VALUES (:incident_id, :description, :assignee_member_id)
RETURNING id;


-- name: list_action_items(incident_id, open_only)
-- record_class: ActionItem
SELECT *
FROM action_item_detail
WHERE
  (:incident_id::UUID IS NULL OR incident_id = :incident_id::UUID)
  AND NOT (:open_only::BOOLEAN AND is_completed)
ORDER BY is_completed, created_at;


-- name: get_action_item(action_item_id)^
-- record_class: ActionItem
SELECT *
FROM action_item_detail
WHERE id = :action_item_id;


-- name: update_action_item(action_item_id, description, is_completed, assignee_member_id)!
UPDATE incident_action_item
SET
    description = :description,
    is_completed = :is_completed,
    assignee_team_member_id = :assignee_member_id,
    updated_at = NOW()
WHERE id = :action_item_id;
