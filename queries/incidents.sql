-- name: create_incident(name, slack_channel_id, lead_member_id, description)$
INSERT INTO incident (name, slack_channel_id, lead, description)
VALUES (:name, :slack_channel_id, :lead_member_id, :description)
RETURNING id;


-- name: find_open_incident_by_channel_id(slack_channel_id)^
-- record_class: Incident
SELECT id, name, slack_channel_id, description
FROM incident
WHERE slack_channel_id = :slack_channel_id AND status = 'OPEN';


-- name: find_open_incident_by_alert_title(title)^
-- record_class: Incident
SELECT i.id, i.name, i.slack_channel_id, i.description
FROM incident i
JOIN alert a ON a.incident_id = i.id
WHERE a.title = :title AND i.status = 'OPEN'
ORDER BY i.start_time DESC
LIMIT 1;


-- name: list_open_incidents()
-- record_class: IncidentOption
SELECT id, name, slack_channel_id
FROM incident
WHERE status = 'OPEN'
ORDER BY start_time DESC;


-- name: list_incidents(status, limit)
-- record_class: IncidentSummary
SELECT *
FROM incident_summary
WHERE :status::incident_status IS NULL OR status = :status::incident_status
ORDER BY start_time DESC
LIMIT :limit;


-- name: get_incident(incident_id)^
-- record_class: IncidentSummary
SELECT *
FROM incident_summary
WHERE id = :incident_id;


-- name: update_incident_description(incident_id, description)!
UPDATE incident
SET description = :description, updated_at = now()
WHERE id = :incident_id;


-- name: resolve_incident(incident_id)$
UPDATE incident
SET status = 'RESOLVED', end_time = now(), updated_at = now()
WHERE id = :incident_id AND status = 'OPEN'
RETURNING id;


-- name: set_incident_customers(incident_id, customer_ids)$
WITH removed AS (
    DELETE FROM incident_customer
    WHERE incident_id = :incident_id AND customer_id <> ALL(:customer_ids::UUID[])
), added AS (
    INSERT INTO incident_customer (incident_id, customer_id)
    SELECT :incident_id, unnest(:customer_ids::UUID[])
    ON CONFLICT DO NOTHING
)
SELECT :incident_id::UUID;
