-- name: create_page(team_member_id, incident_id, root_page_id, escalation_step)^
-- record_class: Page
WITH page AS (
    INSERT INTO page (team_member_id, incident_id, root_page_id, escalation_step)
    VALUES (:team_member_id, :incident_id, :root_page_id, :escalation_step)
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
SELECT p.id, COALESCE(p.root_page_id, p.id) AS root_page_id, p.pushover_receipt
FROM page p
WHERE p.pushover_receipt IS NOT NULL
  AND p.acknowledged_at IS NULL
  AND p.pushover_expires_at > now() - INTERVAL '5 minutes'
  AND NOT EXISTS (
      SELECT 1 FROM page a
      WHERE COALESCE(a.root_page_id, a.id) = COALESCE(p.root_page_id, p.id)
        AND a.acknowledged_at IS NOT NULL
  );


-- name: acknowledge_page(page_id, acknowledged_at)!
UPDATE page
SET acknowledged_at = :acknowledged_at, updated_at = now()
WHERE id = :page_id AND acknowledged_at IS NULL;


-- name: get_escalation_state(root_page_id, step)^
-- record_class: EscalationState
SELECT
    r.id AS root_page_id,
    r.team_member_id AS root_member_id,
    r.incident_id,
    i.status AS incident_status,
    EXISTS (
        SELECT 1 FROM page p
        WHERE (p.id = r.id OR p.root_page_id = r.id) AND p.acknowledged_at IS NOT NULL
    ) AS acknowledged,
    EXISTS (
        SELECT 1 FROM page p WHERE p.root_page_id = r.id AND p.escalation_step = :step
    ) AS step_done
FROM page r
LEFT JOIN incident i ON i.id = r.incident_id
WHERE r.id = :root_page_id;


-- name: list_ringing_chain_pages(root_page_id)
-- record_class: PendingAcknowledgement
SELECT id, COALESCE(root_page_id, id) AS root_page_id, pushover_receipt
FROM page
WHERE (id = :root_page_id OR root_page_id = :root_page_id)
  AND pushover_receipt IS NOT NULL
  AND acknowledged_at IS NULL
  AND pushover_expires_at > now();


-- name: stop_page_alert(page_id)!
UPDATE page
SET pushover_expires_at = now(), updated_at = now()
WHERE id = :page_id;
