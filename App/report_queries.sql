-- Three project reports. Money is stored as integer cents.

-- Open work
SELECT o.order_id,c.name AS bill_to,v.vin,o.opened_at,o.status,o.complaint FROM repair_order o JOIN customer c ON c.customer_id=o.bill_to_customer_id JOIN vehicle v ON v.vehicle_id=o.vehicle_id WHERE o.status IN ('OPEN','IN_PROGRESS') ORDER BY o.opened_at,o.order_id;

-- Vehicle history
SELECT v.vin,o.order_id,o.opened_at,o.odometer,o.complaint,o.status,i.total_cents,i.balance_cents FROM vehicle v JOIN repair_order o ON o.vehicle_id=v.vehicle_id LEFT JOIN invoice_balance i ON i.order_id=o.order_id ORDER BY v.vin,o.opened_at DESC,o.order_id DESC;

-- Unpaid invoices
SELECT invoice_id,order_id,customer_label,issued_at,total_cents,paid_cents,balance_cents FROM invoice_balance WHERE balance_cents>0 ORDER BY issued_at;
