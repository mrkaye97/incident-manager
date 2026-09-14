-- name: create_page(team_member_id, incident_id)^
-- record_class: Page
WITH page AS (
    INSERT INTO page (team_member_id, incident_id)
    VALUES (:team_member_id, :incident_id)
    RETURNING id
)

-- LEFT JOIN so pages without an incident still return a row
SELECT p.id, i.slack_channel_id, i.id AS incident_id
FROM page p
LEFT JOIN incident i ON i.id = :incident_id;


-- name: get_page_delivery(page_id)^
-- record_class: PageDelivery
SELECT
    p.id, tm.name AS member_name, tm.slack_user_id, tm.pushover_user_key, p.pushover_receipt,
    i.id AS incident_id, i.name AS incident_name, i.slack_channel_id
FROM page p
JOIN team_member tm ON tm.id = p.team_member_id
LEFT JOIN incident i ON i.id = p.incident_id
WHERE p.id = :page_id;


-- name: list_pages(incident_id, limit)
-- record_class: PageRecord
SELECT
    p.id, p.incident_id, p.team_member_id, tm.name AS member_name, p.paged_at,
    p.pushover_receipt IS NOT NULL AS pushed,
    p.acknowledged_at
FROM page p
JOIN team_member tm ON tm.id = p.team_member_id
WHERE :incident_id::UUID IS NULL OR p.incident_id = :incident_id::UUID
ORDER BY p.paged_at DESC
LIMIT :limit;


-- name: set_page_pushover_receipt(page_id, pushover_receipt, pushover_expires_at)!
UPDATE page
SET pushover_receipt = :pushover_receipt, pushover_expires_at = :pushover_expires_at, updated_at = now()
WHERE id = :page_id;


-- name: list_pending_acknowledgements()
-- record_class: PendingAcknowledgement
SELECT id, pushover_receipt
FROM page
WHERE pushover_receipt IS NOT NULL
  AND acknowledged_at IS NULL
  AND pushover_expires_at > now() - INTERVAL '5 minutes';


-- name: acknowledge_page(page_id, acknowledged_at)!
UPDATE page
SET acknowledged_at = :acknowledged_at, updated_at = now()
WHERE id = :page_id AND acknowledged_at IS NULL;
