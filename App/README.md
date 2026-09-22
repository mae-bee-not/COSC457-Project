# Run and use the sample app

Python 3.10+ and SQLite; no extra Python packages. Use fictional records.

## Start

Open a terminal in the **App** folder and run:

```sh
python3 prototype/app.py
```

On Windows, try `py -3 prototype/app.py`.  
On Mac, `Run_Prototype.command` is a shortcut.

Open **http://127.0.0.1:8765** in a browser.  
Leave the terminal running; stop with **Ctrl+C**.  
Changes are saved in `prototype/demo.sqlite3`.

For a fresh practice database, use an unused filename:

```sh
python3 prototype/app.py --db practice-01.sqlite3
```

If the port is busy, add `--port 8766` and open **http://127.0.0.1:8766**. If a form says its token is invalid after restarting, reload the page.

## What each screen does

| Screen                               | Use                                                                                                                                                                                                   |
| ------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Overview                             | Open jobs, amount owed, low-stock count and a link to the example repair.                                                                                                                             |
| Customers                            | Add, search or edit contact details. Set Active to Inactive to archive.                                                                                                                               |
| Vehicles                             | Add, search or edit cars and their current customer. VIN must be unique. Changing ownership keeps old bills tied to their original customer.                                                          |
| Employees and Services               | Maintain staff and hourly labor types/rates. Only active mechanics can be assigned to work. Archive with Active = Inactive.                                                                           |
| Parts & stock                        | Maintain parts/prices. Receive or adjust whole-unit stock with a signed quantity and reason. Stock cannot go negative. Archive parts with Active = Inactive.                                          |
| Repair orders                        | Create a visit, record diagnosis/authorization, add labor and parts. Remove/re-add draft lines to correct them. Cancelling an unbilled job returns its parts.                                         |
| Invoice and payment, within a repair | Issue a bill, then record full or partial payments. Issuing locks the bill and job. Tax is a manually entered demo amount; payments cannot exceed the balance. Use browser Print if a copy is needed. |
| Reports                              | Vehicle history, open work and unpaid invoices. Filter results by text, such as VIN. Money is displayed in dollars.                                                                                   |

## One demo to practice

Use a fresh practice database for these example amounts.

1. **Customers:** add DEMO Taylor Test.
2. **Vehicles:** select Taylor; VIN `DEMO-VEHICLE-004`, year 2021, make Demo, model Sedan.
3. **Repair orders:** select that vehicle, complaint “Brake inspection,” odometer 50000. Open the new order.
4. Enter a diagnosis and a fictional authorization note; click **Save and start work**.
5. Add **DEMO Brake labor**, **DEMO Morgan Mechanic**, **1.50** hours. Add **2** DEMO Brake parts.
6. Check **$150 labor + $80 parts = $230**. Use demo tax **0.00** and issue the invoice.
7. Record **$100 CASH**, then **$130 CHECK**. Balance should become **$0**.
8. Run the three reports. Filter history by `DEMO-VEHICLE-004`; the new invoice should not appear as unpaid.
9. Restart the app and check that the saved repair remains.

Also try a duplicate VIN, insufficient stock and overpayment; each should be rejected without saving a bad change. Another seeded invoice starts at $230 total, $100 paid, $130 due.

## For the two builders

- `prototype/schema.sql`: tables, keys and constraints.
- `prototype/core.py`: workflow operations and seed data.
- `prototype/app.py`: screens and form handling.
- `report_queries.sql`: the three SQL reports.

After changes, run from **App**:

```sh
python3 -m unittest discover -s tests -v
```

Keep the existing workflow unless the interview or course requires a change. The sample assumes one current customer per vehicle, one mechanic per labor line, and one invoice per visit. It does not handle deposits before invoicing, refunds or changes to issued bills. Update this guide if you change the app; it supplies the required function reference and tutorial.
