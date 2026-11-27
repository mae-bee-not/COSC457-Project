import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "prototype"))
import core


class RepairTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "test.sqlite3"
        core.initialize(self.path)
        self.c = core.connect(self.path)
        core.seed(self.c)

    def tearDown(self):
        self.c.close()
        self.tmp.cleanup()

    def order(self):
        o = core.create_order(self.c, 2, "DEMO test", 100)
        core.update_order(
            self.c, o, "DEMO diagnosis", "DEMO consent", "DEMO Customer"
        )
        return o
    
    def unpaid_invoice(self):
        # Create a new unpaid invoice for payment testing.
        o = self.order()
        core.add_labor(self.c, o, 1, 1, "1")
        core.add_labor(self.c, o, 1, 1, "0.50")
        core.add_part(self.c, o, 1, 1)
        core.add_part(self.c, o, 1, 1)
        return core.finalize(self.c, o, "0")
    
    def test_seed_invoice_math(self):
        r = core.one(self.c, "SELECT * FROM invoice_balance WHERE invoice_id=1")
        self.assertEqual(
            (r["labor_cents"], r["parts_cents"], r["total_cents"], r["balance_cents"]),
            (15000, 8000, 23000, 0),
        )

    def test_stock_failure_rolls_back_line(self):
        o = self.order()
        before = self.c.execute("SELECT COUNT(*) FROM part_line").fetchone()[0]
        with self.assertRaises(sqlite3.IntegrityError):
            core.add_part(self.c, o, 1, 99)
        self.assertEqual(
            self.c.execute("SELECT COUNT(*) FROM part_line").fetchone()[0], before
        )
        self.assertEqual(
            core.one(self.c, "SELECT on_hand FROM stock WHERE part_id=1")["on_hand"], 8
        )

    def test_remove_and_cancel_return_stock_once(self):
        o = self.order()
        line = core.add_part(self.c, o, 1, 2)
        core.remove_line(self.c, "part", line)
        core.add_part(self.c, o, 1, 3)
        core.cancel_order(self.c, o)
        self.assertEqual(
            core.one(self.c, "SELECT on_hand FROM stock WHERE part_id=1")["on_hand"], 8
        )
        with self.assertRaises(ValueError):
            core.cancel_order(self.c, o)
        self.assertEqual(
            core.one(self.c, "SELECT on_hand FROM stock WHERE part_id=1")["on_hand"], 8
        )

    def test_overpayment_rejected(self):
        i = self.unpaid_invoice()

        # Reject overpayments.
        with self.assertRaises(sqlite3.IntegrityError):
            core.pay(self.c, i, "230.01", "CASH")

        # Reject partial payments.
        with self.assertRaises(sqlite3.IntegrityError):
            core.pay(self.c, i, "100", "CASH")

        # Accept full payment.
        core.pay(self.c, i, "230", "CASH")
        self.assertEqual(
            core.one(
                self.c,
                "SELECT balance_cents FROM invoice_balance WHERE invoice_id=?",
                (i,),
            )["balance_cents"],
            0,
        )

    def test_payment_retry_idempotent(self):
        i = self.unpaid_invoice()

        # Retrying the same payment must not charge twice.
        a = core.pay(self.c, i, "230", "CASH", "test-token")
        b = core.pay(self.c, i, "230", "CASH", "test-token")
        self.assertEqual(a, b)

        with self.assertRaises(ValueError):
            core.pay(self.c, i, "231", "CASH", "test-token")

    def test_final_order_and_invoice_immutable(self):
        with self.assertRaises(ValueError):
            core.add_part(self.c, 1, 1, 1)
        with self.assertRaises(sqlite3.IntegrityError):
            self.c.execute("UPDATE invoice SET tax_cents=1 WHERE invoice_id=1")
        with self.assertRaises(sqlite3.IntegrityError):
            self.c.execute("DELETE FROM labor_line WHERE order_id=1")
        with self.assertRaises(sqlite3.IntegrityError):
            self.c.execute("UPDATE repair_order SET status='OPEN' WHERE order_id=1")

    def test_historical_price_and_owner(self):
        self.c.execute("UPDATE service SET rate_cents=99999 WHERE service_id=1")
        self.c.execute("UPDATE part SET price_cents=99999 WHERE part_id=1")
        self.c.execute("UPDATE vehicle SET customer_id=2 WHERE vehicle_id=1")
        self.c.execute("UPDATE customer SET name='DEMO renamed' WHERE customer_id=1")
        r = core.one(self.c, "SELECT * FROM invoice_balance WHERE invoice_id=1")
        self.assertEqual(r["total_cents"], 23000)
        self.assertEqual(r["customer_label"], "DEMO Avery Sample")
        self.assertEqual(
            core.one(
                self.c, "SELECT bill_to_customer_id FROM repair_order WHERE order_id=1"
            )["bill_to_customer_id"],
            1,
        )

    def test_duplicate_vin_and_foreign_keys(self):
        with self.assertRaises(sqlite3.IntegrityError):
            core.save_record(
                self.c,
                "vehicle",
                dict(
                    customer_id=1,
                    vin="DEMO-VEHICLE-001",
                    license_plate="TEST001",
                    model_year=2020,
                    make="x",
                    model="y",
                ),
            )
        with self.assertRaises(sqlite3.IntegrityError):
            self.c.execute("DELETE FROM customer WHERE customer_id=1")
        self.assertEqual(list(self.c.execute("PRAGMA foreign_key_check")), [])

    def test_authorization_and_mechanic(self):
        with self.assertRaises(sqlite3.IntegrityError):
            core.add_labor(self.c, 2, 1, 1, "1")
        o = self.order()
        with self.assertRaises(sqlite3.IntegrityError):
            core.add_labor(self.c, o, 1, 2, "1")

    def test_money_validation_and_rounding(self):
        for v in ("NaN", "Infinity", "-1", "1.001", "bad"):
            with self.assertRaises(ValueError):
                core.amount(v)
        o = self.order()
        self.c.execute("UPDATE service SET rate_cents=101 WHERE service_id=1")
        core.add_labor(self.c, o, 1, 1, "0.50")
        self.assertEqual(core.totals(self.c, o)[0], 51)

    def test_empty_invoice_and_double_finalization(self):
        o = self.order()
        with self.assertRaises(ValueError):
            core.finalize(self.c, o, "0")
        core.add_part(self.c, o, 1, 1)
        core.finalize(self.c, o, "2.40")
        with self.assertRaises(ValueError):
            core.finalize(self.c, o, "0")

    def test_reports_no_join_multiplication(self):
        i = self.unpaid_invoice()

        # Verify that all reports execute successfully.
        for sql in core.REPORTS.values():
            list(self.c.execute(sql))

        # Verify the unpaid invoice totals.
        invoices = list(
            self.c.execute(core.REPORTS["Unpaid invoices"])
        )
        self.assertEqual(len(invoices), 1)
        self.assertEqual(invoices[0]["invoice_id"], i)
        self.assertEqual(
            (
                invoices[0]["total_cents"],
                invoices[0]["paid_cents"],
                invoices[0]["balance_cents"],
            ),
            (23000, 0, 23000),
        )

        # Verify that repair history contains no duplicate orders.
        order_id = invoices[0]["order_id"]
        history = [
            r
            for r in self.c.execute(core.REPORTS["Vehicle history"])
            if r["order_id"] == order_id
        ]

        self.assertEqual(len(history), 1)
        self.assertEqual(
            (history[0]["total_cents"], history[0]["balance_cents"]),
            (23000, 23000),
        )

        # Verify that fully paid invoices leave the unpaid report.
        core.pay(self.c, i, "230", "CARD")
        self.assertEqual(
            list(self.c.execute(core.REPORTS["Unpaid invoices"])),
            [],
        )

    def test_stock_adjustment_and_ledger_immutable(self):
        with self.assertRaises(sqlite3.IntegrityError):
            core.adjust_stock(self.c, 1, -9, "DEMO too much")
        with self.assertRaises(sqlite3.IntegrityError):
            self.c.execute("DELETE FROM inventory_movement")
        core.adjust_stock(self.c, 1, 2, "DEMO delivery")
        self.assertEqual(
            core.one(self.c, "SELECT on_hand FROM stock WHERE part_id=1")["on_hand"], 10
        )

    def test_sql_injection_is_plain_text(self):
        x = "DEMO x'); DROP TABLE customer; --"
        core.create_order(self.c, 1, x, 1)
        self.assertEqual(
            self.c.execute("SELECT COUNT(*) FROM customer").fetchone()[0], 2
        )

    def test_zero_line_price_and_zero_balance(self):
        o = self.order()
        self.c.execute("UPDATE service SET rate_cents=0 WHERE service_id=1")
        core.add_labor(self.c, o, 1, 1, "1")
        i = core.finalize(self.c, o, "0")
        self.assertEqual(
            core.one(
                self.c,
                "SELECT balance_cents FROM invoice_balance WHERE invoice_id=?",
                (i,),
            )["balance_cents"],
            0,
        )
        with self.assertRaises(sqlite3.IntegrityError):
            core.pay(self.c, i, "1", "CASH")

    def test_reopen_connection_persists(self):
        self.c.close()
        self.c = core.connect(self.path)
        self.assertEqual(
            self.c.execute("SELECT COUNT(*) FROM invoice").fetchone()[0], 1
        )

    def test_approval_details(self):
        # Verify that the approval name and timestamp are saved.
        o = self.order()
        r = core.one(
            self.c,
            "SELECT * FROM repair_order WHERE order_id=?",
            (o,),
        )
        self.assertEqual(r["approval_name"], "DEMO Customer")
        self.assertTrue(r["approved_at"])

        # Reject an empty approval name.
        with self.assertRaises(ValueError):
            core.update_order(self.c, o, "Diagnosis", "Consent", "")

    def test_waiting_for_parts(self):
        # Verify that a repair can be paused and resumed.
        o = self.order()
        core.set_order_status(self.c, o, "WAITING_FOR_PARTS")
        r = core.one(
            self.c,
            "SELECT status FROM repair_order WHERE order_id=?",
            (o,),
        )
        self.assertEqual(r["status"], "WAITING_FOR_PARTS")

        core.set_order_status(self.c, o, "IN_PROGRESS")
        r = core.one(
            self.c,
            "SELECT status FROM repair_order WHERE order_id=?",
            (o,),
        )
        self.assertEqual(r["status"], "IN_PROGRESS")

    def test_shop_supplies(self):
        # Verify that supplies and tax are included in the total.
        o = self.order()
        core.add_labor(self.c, o, 1, 1, "1")
        i = core.finalize(self.c, o, "2.50", "5.00")

        r = core.one(
            self.c,
            "SELECT * FROM invoice_balance WHERE invoice_id=?",
            (i,),
        )
        self.assertEqual(r["shop_supplies_cents"], 500)
        self.assertEqual(r["total_cents"], 10750)

    def test_payment_method_and_completion(self):
        # Reject unsupported payment methods.
        i = self.unpaid_invoice()

        with self.assertRaises(sqlite3.IntegrityError):
            core.pay(self.c, i, "230", "CHECK")

        # Verify that full payment completes the repair.
        core.pay(self.c, i, "230", "CARD")

        r = core.one(
            self.c,
            """SELECT o.status
               FROM repair_order o
               JOIN invoice i ON o.order_id = i.order_id
               WHERE i.invoice_id=?""",
            (i,),
        )
        self.assertEqual(r["status"], "COMPLETED")

    def test_history_by_phone(self):
        # Verify that repair history matches the phone number.
        rows = core.history_by_phone(self.c, "410-555-0101")
        self.assertTrue(rows)

        for r in rows:
            self.assertEqual(r["phone"], "410-555-0101")

        # An unknown phone number should return no results.
        self.assertEqual(
            core.history_by_phone(self.c, "000-000-0000"),
            [],
        )

    def test_open_work_statuses(self):
        # Create repairs with different active statuses.
        self.order()
        waiting = self.order()
        core.set_order_status(
            self.c, waiting, "WAITING_FOR_PARTS"
        )
        self.unpaid_invoice()

        # Verify that all four active statuses are included.
        rows = list(self.c.execute(core.REPORTS["Open work"]))
        statuses = {r["status"] for r in rows}

        self.assertEqual(
            statuses,
            {
                "OPEN",
                "IN_PROGRESS",
                "WAITING_FOR_PARTS",
                "READY_FOR_PICKUP",
            },
        )

if __name__ == "__main__":
    unittest.main()
