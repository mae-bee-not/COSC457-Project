-- SQLite physical reference. Fictional teaching data only. See migration notes for MySQL.
PRAGMA foreign_keys = ON;
CREATE TABLE customer (
 customer_id INTEGER PRIMARY KEY, name TEXT NOT NULL CHECK(length(trim(name))>0),
 phone TEXT NOT NULL DEFAULT '', email TEXT NOT NULL DEFAULT '', active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1))
);
CREATE TABLE vehicle (
 vehicle_id INTEGER PRIMARY KEY, customer_id INTEGER NOT NULL REFERENCES customer(customer_id),
 vin TEXT NOT NULL UNIQUE CHECK(length(trim(vin))>0), model_year INTEGER NOT NULL CHECK(model_year BETWEEN 1886 AND 2100),
 make TEXT NOT NULL CHECK(length(trim(make))>0), model TEXT NOT NULL CHECK(length(trim(model))>0)
);
CREATE TABLE employee (
 employee_id INTEGER PRIMARY KEY, name TEXT NOT NULL CHECK(length(trim(name))>0),
 role TEXT NOT NULL CHECK(role IN ('MECHANIC','ADVISOR','MANAGER')),
 active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1))
);
CREATE TABLE service (
 service_id INTEGER PRIMARY KEY, name TEXT NOT NULL CHECK(length(trim(name))>0),
 rate_cents INTEGER NOT NULL CHECK(rate_cents>=0), active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1))
);
CREATE TABLE part (
 part_id INTEGER PRIMARY KEY, part_number TEXT NOT NULL UNIQUE, name TEXT NOT NULL CHECK(length(trim(name))>0),
 price_cents INTEGER NOT NULL CHECK(price_cents>=0), reorder_level INTEGER NOT NULL DEFAULT 0 CHECK(reorder_level>=0),
 active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1))
);
CREATE TABLE repair_order (
 order_id INTEGER PRIMARY KEY, vehicle_id INTEGER NOT NULL REFERENCES vehicle(vehicle_id),
 bill_to_customer_id INTEGER NOT NULL REFERENCES customer(customer_id),
 opened_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
 complaint TEXT NOT NULL CHECK(length(trim(complaint))>0), diagnosis TEXT NOT NULL DEFAULT '',
 odometer INTEGER NOT NULL CHECK(odometer>=0),
 status TEXT NOT NULL DEFAULT 'OPEN' CHECK(status IN ('OPEN','IN_PROGRESS','COMPLETED','CANCELLED')),
 authorization_note TEXT NOT NULL DEFAULT ''
);
CREATE TABLE labor_line (
 labor_line_id INTEGER PRIMARY KEY, order_id INTEGER NOT NULL REFERENCES repair_order(order_id),
 service_id INTEGER NOT NULL REFERENCES service(service_id), mechanic_id INTEGER NOT NULL REFERENCES employee(employee_id),
 description TEXT NOT NULL, hours_hundredths INTEGER NOT NULL CHECK(hours_hundredths>0),
 rate_cents INTEGER NOT NULL CHECK(rate_cents>=0)
);
CREATE TABLE part_line (
 part_line_id INTEGER PRIMARY KEY, order_id INTEGER NOT NULL REFERENCES repair_order(order_id),
 part_id INTEGER NOT NULL REFERENCES part(part_id), description TEXT NOT NULL,
 quantity INTEGER NOT NULL CHECK(quantity>0), unit_price_cents INTEGER NOT NULL CHECK(unit_price_cents>=0)
);
CREATE TABLE inventory_movement (
 movement_id INTEGER PRIMARY KEY, part_id INTEGER NOT NULL REFERENCES part(part_id),
 order_id INTEGER REFERENCES repair_order(order_id), quantity_delta INTEGER NOT NULL CHECK(quantity_delta<>0),
 reason TEXT NOT NULL CHECK(length(trim(reason))>0),
 created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);
CREATE TABLE invoice (
 invoice_id INTEGER PRIMARY KEY, order_id INTEGER NOT NULL UNIQUE REFERENCES repair_order(order_id),
 issued_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
 customer_label TEXT NOT NULL, vehicle_label TEXT NOT NULL,
 labor_cents INTEGER NOT NULL CHECK(labor_cents>=0), parts_cents INTEGER NOT NULL CHECK(parts_cents>=0),
 tax_cents INTEGER NOT NULL CHECK(tax_cents>=0)
);
CREATE TABLE payment (
 payment_id INTEGER PRIMARY KEY, invoice_id INTEGER NOT NULL REFERENCES invoice(invoice_id),
 paid_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
 amount_cents INTEGER NOT NULL CHECK(amount_cents>0),
 method TEXT NOT NULL CHECK(method IN ('CASH','CHECK','CARD_RECORD','OTHER')),
 request_key TEXT NOT NULL UNIQUE
);
CREATE INDEX vehicle_customer_idx ON vehicle(customer_id);
CREATE INDEX order_vehicle_idx ON repair_order(vehicle_id);
CREATE INDEX order_bill_to_idx ON repair_order(bill_to_customer_id);
CREATE INDEX order_status_idx ON repair_order(status, opened_at);
CREATE INDEX labor_order_idx ON labor_line(order_id);
CREATE INDEX labor_mechanic_idx ON labor_line(mechanic_id);
CREATE INDEX part_line_order_idx ON part_line(order_id);
CREATE INDEX movement_part_idx ON inventory_movement(part_id);
CREATE INDEX payment_invoice_idx ON payment(invoice_id);
CREATE VIEW stock AS
 SELECT p.*, COALESCE((SELECT SUM(m.quantity_delta) FROM inventory_movement m WHERE m.part_id=p.part_id),0) AS on_hand FROM part p;
CREATE VIEW invoice_balance AS
 SELECT i.*, i.labor_cents+i.parts_cents+i.tax_cents AS total_cents,
 COALESCE((SELECT SUM(p.amount_cents) FROM payment p WHERE p.invoice_id=i.invoice_id),0) AS paid_cents,
 i.labor_cents+i.parts_cents+i.tax_cents-COALESCE((SELECT SUM(p.amount_cents) FROM payment p WHERE p.invoice_id=i.invoice_id),0) AS balance_cents
 FROM invoice i;
CREATE TRIGGER stock_nonnegative BEFORE INSERT ON inventory_movement
 WHEN NEW.quantity_delta+COALESCE((SELECT SUM(quantity_delta) FROM inventory_movement WHERE part_id=NEW.part_id),0)<0
 BEGIN SELECT RAISE(ABORT,'Insufficient stock'); END;
CREATE TRIGGER movement_no_update BEFORE UPDATE ON inventory_movement BEGIN SELECT RAISE(ABORT,'Inventory ledger is append-only'); END;
CREATE TRIGGER movement_no_delete BEFORE DELETE ON inventory_movement BEGIN SELECT RAISE(ABORT,'Inventory ledger is append-only'); END;
CREATE TRIGGER invoice_no_update BEFORE UPDATE ON invoice BEGIN SELECT RAISE(ABORT,'Invoice is immutable'); END;
CREATE TRIGGER invoice_no_delete BEFORE DELETE ON invoice BEGIN SELECT RAISE(ABORT,'Invoice is immutable'); END;
CREATE TRIGGER payment_no_update BEFORE UPDATE ON payment BEGIN SELECT RAISE(ABORT,'Payment is immutable'); END;
CREATE TRIGGER payment_no_delete BEFORE DELETE ON payment BEGIN SELECT RAISE(ABORT,'Payment is immutable'); END;
CREATE TRIGGER payment_balance BEFORE INSERT ON payment
 WHEN NEW.amount_cents>(SELECT balance_cents FROM invoice_balance WHERE invoice_id=NEW.invoice_id)
 BEGIN SELECT RAISE(ABORT,'Payment exceeds outstanding balance'); END;
CREATE TRIGGER labor_mechanic BEFORE INSERT ON labor_line
 WHEN NOT EXISTS(SELECT 1 FROM employee WHERE employee_id=NEW.mechanic_id AND role='MECHANIC' AND active=1)
 BEGIN SELECT RAISE(ABORT,'Select an active mechanic'); END;
CREATE TRIGGER order_frozen BEFORE UPDATE ON repair_order
 WHEN OLD.status IN ('COMPLETED','CANCELLED')
 BEGIN SELECT RAISE(ABORT,'Final orders cannot be edited'); END;

-- Line records can be corrected by removing and re-adding before finalization.
CREATE TRIGGER labor_line_insert_guard BEFORE INSERT ON labor_line
 WHEN (SELECT status FROM repair_order WHERE order_id=NEW.order_id)!='IN_PROGRESS'
 BEGIN SELECT RAISE(ABORT,'Order must be authorized and in progress'); END;
CREATE TRIGGER labor_line_no_update BEFORE UPDATE ON labor_line
 BEGIN SELECT RAISE(ABORT,'Remove and re-add a draft line to correct it'); END;
CREATE TRIGGER labor_line_delete_guard BEFORE DELETE ON labor_line
 WHEN (SELECT status FROM repair_order WHERE order_id=OLD.order_id) NOT IN ('OPEN','IN_PROGRESS')
 BEGIN SELECT RAISE(ABORT,'Final order lines cannot be removed'); END;
CREATE TRIGGER part_line_insert_guard BEFORE INSERT ON part_line
 WHEN (SELECT status FROM repair_order WHERE order_id=NEW.order_id)!='IN_PROGRESS'
 BEGIN SELECT RAISE(ABORT,'Order must be authorized and in progress'); END;
CREATE TRIGGER part_line_no_update BEFORE UPDATE ON part_line
 BEGIN SELECT RAISE(ABORT,'Remove and re-add a draft line to correct it'); END;
CREATE TRIGGER part_line_delete_guard BEFORE DELETE ON part_line
 WHEN (SELECT status FROM repair_order WHERE order_id=OLD.order_id) NOT IN ('OPEN','IN_PROGRESS')
 BEGIN SELECT RAISE(ABORT,'Final order lines cannot be removed'); END;
