-- name: list_customers()
-- record_class: Customer
SELECT id, name
FROM customer
ORDER BY name;


-- name: get_customers(customer_ids)
-- record_class: Customer
SELECT id, name
FROM customer
WHERE id = ANY(:customer_ids::UUID[])
ORDER BY name;


-- name: create_customer(name)^
-- record_class: Customer
INSERT INTO customer (name)
VALUES (:name)
RETURNING id, name;


-- name: update_customer(customer_id, name)^
-- record_class: Customer
UPDATE customer
SET name = :name, updated_at = now()
WHERE id = :customer_id
RETURNING id, name;
