-- Leo's Auto Database Reports
-- All monetary values are stored as integer cents.

-- Report 1: Open work
-- Display all repair orders that are still active.
SELECT o.order_id, c.name AS bill_to,
       v.vin, v.license_plate,
       o.opened_at, o.status, o.complaint
FROM repair_order o
JOIN customer c ON c.customer_id = o.bill_to_customer_id
JOIN vehicle v ON v.vehicle_id = o.vehicle_id
WHERE o.status IN (
    'OPEN',
    'IN_PROGRESS',
    'WAITING_FOR_PARTS',
    'READY_FOR_PICKUP'
)
ORDER BY o.opened_at, o.order_id;


-- Report 2: Repair history by customer phone number
-- Retrieve repair orders associated with the billing customer.
SELECT c.phone, c.name AS bill_to,
       v.vin, v.license_plate,
       o.order_id, o.opened_at, o.odometer,
       o.complaint, o.status,
       i.total_cents, i.balance_cents
FROM repair_order o
JOIN customer c ON c.customer_id = o.bill_to_customer_id
JOIN vehicle v ON v.vehicle_id = o.vehicle_id
LEFT JOIN invoice_balance i ON i.order_id = o.order_id
WHERE c.phone = :phone
ORDER BY o.opened_at DESC, o.order_id DESC;


-- Report 3: Unpaid invoices
-- Display invoices with an outstanding balance.
SELECT invoice_id, order_id, customer_label,
       issued_at, total_cents, paid_cents, balance_cents
FROM invoice_balance
WHERE balance_cents > 0
ORDER BY issued_at;