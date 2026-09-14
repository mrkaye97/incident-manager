-- name: create_session(token_hash, team_member_id, expires_at)!
INSERT INTO session (token_hash, team_member_id, expires_at)
VALUES (:token_hash, :team_member_id, :expires_at);


-- name: get_session_member(token_hash)^
-- record_class: Member
SELECT tm.id, tm.name, tm.slack_user_id, tm.slack_handle, tm.pushover_user_key
FROM session s
JOIN team_member tm ON tm.id = s.team_member_id
WHERE s.token_hash = :token_hash AND s.expires_at > now();


-- name: delete_session(token_hash)!
DELETE FROM session WHERE token_hash = :token_hash;
