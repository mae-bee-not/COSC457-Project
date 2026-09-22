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
        core.update_order(self.c, o, "DEMO diagnosis", "DEMO consent")
        return o

    def test_seed_invoice_math(self):
        r = core.one(self.c, "SELECT * FROM invoice_balance WHERE invoice_id=1")
        self.assertEqual(
            (r["labor_cents"], r["parts_cents"], r["total_cents"], r["balance_cents"]),
            (15000, 8000, 23000, 13000),
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
        with self.assertRaises(sqlite3.IntegrityError):
            core.pay(self.c, 1, "130.01", "CASH")
        core.pay(self.c, 1, "130", "CASH")
        self.assertEqual(
            core.one(
                self.c, "SELECT balance_cents FROM invoice_balance WHERE invoice_id=1"
            )["balance_cents"],
            0,
        )

    def test_payment_retry_idempotent(self):
        a = core.pay(self.c, 1, "10", "CASH", "test-token")
        b = core.pay(self.c, 1, "10", "CASH", "test-token")
        self.assertEqual(a, b)
        with self.assertRaises(ValueError):
            core.pay(self.c, 1, "11", "CASH", "test-token")

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
        for sql in core.REPORTS.values():
            list(self.c.execute(sql))
        core.pay(self.c, 1, "10", "CASH")
        invoices = list(self.c.execute(core.REPORTS["Unpaid invoices"]))
        self.assertEqual(len(invoices), 1)
        self.assertEqual(
            (
                invoices[0]["total_cents"],
                invoices[0]["paid_cents"],
                invoices[0]["balance_cents"],
            ),
            (23000, 11000, 12000),
        )
        history = [
            r
            for r in self.c.execute(core.REPORTS["Vehicle history"])
            if r["order_id"] == 1
        ]
        self.assertEqual(len(history), 1)
        self.assertEqual(
            (history[0]["total_cents"], history[0]["balance_cents"]), (23000, 12000)
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


if __name__ == "__main__":
    unittest.main()
