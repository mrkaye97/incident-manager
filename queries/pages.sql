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
SELECT p.id, tm.name AS member_name, tm.slack_user_id, i.slack_channel_id
FROM page p
JOIN team_member tm ON tm.id = p.team_member_id
LEFT JOIN incident i ON i.id = p.incident_id
WHERE p.id = :page_id;


-- name: list_pages(incident_id, limit)
-- record_class: PageRecord
SELECT p.id, p.incident_id, p.team_member_id, tm.name AS member_name, p.paged_at
FROM page p
JOIN team_member tm ON tm.id = p.team_member_id
WHERE :incident_id::UUID IS NULL OR p.incident_id = :incident_id::UUID
ORDER BY p.paged_at DESC
LIMIT :limit;
