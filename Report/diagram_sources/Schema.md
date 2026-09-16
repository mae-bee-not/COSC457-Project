# Proposed schema

Matches the current Python/SQLite sample. Confirm against the interview and required tools.

PK = primary key. FK = foreign key. All foreign keys required except inventory_movement.order_id.

## customer
Contact details for a customer.

PK customer_id, name, phone, email, active



## vehicle
A vehicle and its current customer.

PK vehicle_id, FK customer_id, vin, model_year, make, model

customer_id links to customer.customer_id

## repair_order
One visit; bill-to customer is recorded separately from current ownership.

PK order_id, FK vehicle_id, FK bill_to_customer_id, opened_at, complaint, diagnosis, odometer, status, authorization_note

bill_to_customer_id links to customer.customer_id; vehicle_id links to vehicle.vehicle_id

## employee
Staff; only an active mechanic can be selected for a labor line.

PK employee_id, name, role, active



## service
Catalog of labor types and current rates.

PK service_id, name, rate_cents, active



## labor_line
A service performed on a job, by one mechanic, at the rate charged.

PK labor_line_id, FK order_id, FK service_id, FK mechanic_id, description, hours_hundredths, rate_cents

mechanic_id links to employee.employee_id; service_id links to service.service_id; order_id links to repair_order.order_id

## part
Part catalog; stock is calculated from inventory movements.

PK part_id, part_number, name, price_cents, reorder_level, active



## part_line
Parts used on a job, at the price charged.

PK part_line_id, FK order_id, FK part_id, description, quantity, unit_price_cents

part_id links to part.part_id; order_id links to repair_order.order_id

## inventory_movement
Each stock increase or decrease; a repair link is optional.

PK movement_id, FK part_id, FK order_id, quantity_delta, reason, created_at

order_id links to repair_order.order_id (optional); part_id links to part.part_id

## invoice
One final bill per order, with labels and amounts preserved.

PK invoice_id, FK order_id, issued_at, customer_label, vehicle_label, labor_cents, parts_cents, tax_cents

order_id links to repair_order.order_id

## payment
One payment toward an invoice; several partial payments are allowed.

PK payment_id, FK invoice_id, paid_at, amount_cents, method, request_key

invoice_id links to invoice.invoice_id
