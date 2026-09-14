-- name: record_alert(title, state, body, source_url, incident_id)$
INSERT INTO alert (title, state, body, source_url, incident_id)
VALUES (:title, :state, :body, :source_url, :incident_id)
RETURNING id;


-- name: list_incident_alerts(incident_id)
-- record_class: AlertRecord
SELECT id, title, state, body, source_url, created_at
FROM alert
WHERE incident_id = :incident_id
ORDER BY created_at DESC;
