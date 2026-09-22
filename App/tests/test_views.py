import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "prototype"))
import core

import app


class ViewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        p = Path(self.tmp.name) / "view.sqlite3"
        core.initialize(p)
        self.c = core.connect(p)
        core.seed(self.c)

    def tearDown(self):
        self.c.close()
        self.tmp.cleanup()

    def test_all_catalogs_create_edit_search(self):
        for page in core.CATALOG:
            for q in ({}, {"edit": "1"}, {"q": "no-such-record"}):
                rendered = app.catalog(self.c, page, q)
                self.assertIn("<form", rendered)

    def test_final_order_ui_has_no_mutating_line_forms(self):
        rendered = app.order_screen(self.c, {"edit": "1"})
        self.assertIn("Frozen invoice", rendered)
        self.assertNotIn("Add labor</button>", rendered)
        self.assertIn("Payment ($)", rendered)

    def test_html_escape(self):
        value = "<script>alert(1)</script>"
        r = app.field("Test", "test", value)
        self.assertNotIn(value, r)
        self.assertIn("&lt;script&gt;", r)

    def test_display_money_units(self):
        r = app.table([{"amount_cents": 1234, "hours_hundredths": 150}])
        self.assertIn("amount ($)", r)
        self.assertIn("$12.34", r)
        self.assertIn("1.50", r)
