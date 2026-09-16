"""Provisional repair-shop domain layer; all monetary values are integer cents."""
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from decimal import Decimal, InvalidOperation
import uuid

ROOT=Path(__file__).resolve().parent

def connect(path):
    c=sqlite3.connect(path, isolation_level=None, timeout=10)
    c.row_factory=sqlite3.Row
    c.execute('PRAGMA foreign_keys=ON')
    return c

@contextmanager
def transaction(c):
    c.execute('BEGIN IMMEDIATE')
    try:
        yield
        c.commit()
    except Exception:
        c.rollback()
        raise

def amount(value):
    try:
        d=Decimal(str(value))
        if not d.is_finite() or d<0 or d>Decimal('1000000') or d*100!=(d*100).to_integral_value():
            raise ValueError('Use a nonnegative amount with at most two decimal places (maximum 1,000,000).')
        return int(d*100)
    except InvalidOperation:
        raise ValueError('Enter a valid numeric amount.')

def whole(value, minimum=0):
    try: n=int(str(value))
    except (ValueError,TypeError): raise ValueError('Enter a whole number.')
    if n<minimum or n>100000000: raise ValueError('Whole number outside allowed range.')
    return n

def required(value):
    s=str(value).strip()
    if not s or len(s)>1000: raise ValueError('Required text must be 1-1000 characters.')
    return s

def one(c,sql,args=()):
    r=c.execute(sql,args).fetchone()
    if r is None: raise ValueError('Record not found.')
    return r

def initialize(path):
    c=connect(path)
    c.executescript((ROOT/'schema.sql').read_text())
    c.close()

def editable(c,order_id):
    r=one(c,'SELECT * FROM repair_order WHERE order_id=?',(order_id,))
    if r['status'] not in ('OPEN','IN_PROGRESS'): raise ValueError('This order is final.')
    return r

def totals(c,order_id):
    labor=c.execute('SELECT COALESCE(SUM(CAST((hours_hundredths*rate_cents+50)/100 AS INTEGER)),0) FROM labor_line WHERE order_id=?',(order_id,)).fetchone()[0]
    parts=c.execute('SELECT COALESCE(SUM(quantity*unit_price_cents),0) FROM part_line WHERE order_id=?',(order_id,)).fetchone()[0]
    return labor,parts

CATALOG={
 'customer':('name','phone','email','active'),
 'vehicle':('customer_id','vin','model_year','make','model'),
 'employee':('name','role','active'),
 'service':('name','rate_cents','active'),
 'part':('part_number','name','price_cents','reorder_level','active')
}

def save_record(c,entity,values,record_id=None):
    if entity not in CATALOG: raise ValueError('Unknown catalog.')
    cols=CATALOG[entity]
    vals={k:values.get(k,'') for k in cols}
    for k in cols:
        if k in ('rate_cents','price_cents'): vals[k]=amount(vals[k])
        elif k.endswith('_id') or k in ('model_year','reorder_level','active'): vals[k]=whole(vals[k])
        elif k not in ('phone','email'): vals[k]=required(vals[k])
    if entity=='vehicle': vals['vin']=vals['vin'].upper()
    with transaction(c):
        if record_id:
            one(c,f'SELECT * FROM {entity} WHERE {entity}_id=?',(record_id,))
            c.execute(f'UPDATE {entity} SET '+','.join(k+'=?' for k in cols)+f' WHERE {entity}_id=?',tuple(vals.values())+(record_id,))
            return int(record_id)
        return c.execute(f'INSERT INTO {entity} ({",".join(cols)}) VALUES ({",".join("?" for _ in cols)})',tuple(vals.values())).lastrowid

def create_order(c,vehicle_id,complaint,odometer):
    with transaction(c):
        v=one(c,'SELECT v.* FROM vehicle v JOIN customer c ON c.customer_id=v.customer_id WHERE v.vehicle_id=? AND c.active=1',(vehicle_id,))
        return c.execute('INSERT INTO repair_order(vehicle_id,bill_to_customer_id,complaint,odometer) VALUES(?,?,?,?)',(vehicle_id,v['customer_id'],required(complaint),whole(odometer))).lastrowid

def update_order(c,order_id,diagnosis,authorization_note):
    with transaction(c):
        editable(c,order_id)
        note=required(authorization_note)
        c.execute("UPDATE repair_order SET diagnosis=?,authorization_note=?,status='IN_PROGRESS' WHERE order_id=?",(required(diagnosis),note,order_id))

def add_labor(c,order_id,service_id,mechanic_id,hours):
    h=amount(hours)
    if h<=0: raise ValueError('Labor hours must be positive.')
    with transaction(c):
        editable(c,order_id)
        s=one(c,'SELECT * FROM service WHERE service_id=? AND active=1',(service_id,))
        return c.execute('INSERT INTO labor_line(order_id,service_id,mechanic_id,description,hours_hundredths,rate_cents) VALUES(?,?,?,?,?,?)',(order_id,service_id,mechanic_id,s['name'],h,s['rate_cents'])).lastrowid

def add_part(c,order_id,part_id,quantity):
    q=whole(quantity,1)
    with transaction(c):
        editable(c,order_id)
        p=one(c,'SELECT * FROM part WHERE part_id=? AND active=1',(part_id,))
        line=c.execute('INSERT INTO part_line(order_id,part_id,description,quantity,unit_price_cents) VALUES(?,?,?,?,?)',(order_id,part_id,p['name'],q,p['price_cents'])).lastrowid
        c.execute('INSERT INTO inventory_movement(part_id,order_id,quantity_delta,reason) VALUES(?,?,?,?)',(part_id,order_id,-q,'ISSUE line '+str(line)))
        return line

def remove_line(c,kind,line_id):
    if kind not in ('labor','part'): raise ValueError('Unknown line type.')
    with transaction(c):
        r=one(c,f'SELECT * FROM {kind}_line WHERE {kind}_line_id=?',(line_id,))
        editable(c,r['order_id'])
        c.execute(f'DELETE FROM {kind}_line WHERE {kind}_line_id=?',(line_id,))
        if kind=='part': c.execute('INSERT INTO inventory_movement(part_id,order_id,quantity_delta,reason) VALUES(?,?,?,?)',(r['part_id'],r['order_id'],r['quantity'],'RETURN line '+str(line_id)))

def adjust_stock(c,part_id,quantity_delta,reason):
    delta=int(str(quantity_delta))
    if delta==0 or abs(delta)>1000000: raise ValueError('Stock change must be nonzero and no more than 1,000,000 units.')
    with transaction(c):
        c.execute('INSERT INTO inventory_movement(part_id,quantity_delta,reason) VALUES(?,?,?)',(part_id,delta,required(reason)))

def cancel_order(c,order_id):
    with transaction(c):
        editable(c,order_id)
        for r in c.execute('SELECT * FROM part_line WHERE order_id=?',(order_id,)).fetchall():
            c.execute('INSERT INTO inventory_movement(part_id,order_id,quantity_delta,reason) VALUES(?,?,?,?)',(r['part_id'],order_id,r['quantity'],'CANCEL return line '+str(r['part_line_id'])))
        c.execute('DELETE FROM part_line WHERE order_id=?',(order_id,))
        c.execute('DELETE FROM labor_line WHERE order_id=?',(order_id,))
        c.execute("UPDATE repair_order SET status='CANCELLED' WHERE order_id=?",(order_id,))

def finalize(c,order_id,tax):
    tax_cents=amount(tax)
    with transaction(c):
        r=editable(c,order_id)
        if r['status']!='IN_PROGRESS': raise ValueError('Record diagnosis and authorization first.')
        labor,parts=totals(c,order_id)
        count=c.execute('SELECT (SELECT COUNT(*) FROM labor_line WHERE order_id=?)+(SELECT COUNT(*) FROM part_line WHERE order_id=?)',(order_id,order_id)).fetchone()[0]
        if not count: raise ValueError('Add at least one labor or part line before completion.')
        cust=one(c,'SELECT name FROM customer WHERE customer_id=?',(r['bill_to_customer_id'],))
        v=one(c,'SELECT * FROM vehicle WHERE vehicle_id=?',(r['vehicle_id'],))
        inv=c.execute('INSERT INTO invoice(order_id,customer_label,vehicle_label,labor_cents,parts_cents,tax_cents) VALUES(?,?,?,?,?,?)',(order_id,cust['name'],f"{v['model_year']} {v['make']} {v['model']} | {v['vin']}",labor,parts,tax_cents)).lastrowid
        c.execute("UPDATE repair_order SET status='COMPLETED' WHERE order_id=?",(order_id,))
        return inv

def pay(c,invoice_id,value,method,request_key=None):
    cents=amount(value)
    if cents<=0: raise ValueError('Payment must be positive.')
    key=request_key or str(uuid.uuid4())
    with transaction(c):
        prior=c.execute('SELECT * FROM payment WHERE request_key=?',(key,)).fetchone()
        if prior:
            if (prior['invoice_id'],prior['amount_cents'],prior['method'])!=(int(invoice_id),cents,method): raise ValueError('Payment request key reused with different values.')
            return prior['payment_id']
        return c.execute('INSERT INTO payment(invoice_id,amount_cents,method,request_key) VALUES(?,?,?,?)',(invoice_id,cents,method,key)).lastrowid

def seed(c):
    # Fictional names, identifiers and prices. Nothing is a real Leo's customer record.
    a=save_record(c,'customer',dict(name='DEMO Avery Sample',phone='410-555-0101',email='avery@example.invalid',active=1))
    b=save_record(c,'customer',dict(name='DEMO Jordan Sample',phone='410-555-0102',email='jordan@example.invalid',active=1))
    for cust,vin,year,make,model in [(a,'DEMO-VEHICLE-001',2020,'Demo','Sedan'),(a,'DEMO-VEHICLE-002',2022,'Demo','Wagon'),(b,'DEMO-VEHICLE-003',2018,'Demo','Hatch')]:
        save_record(c,'vehicle',dict(customer_id=cust,vin=vin,model_year=year,make=make,model=model))
    save_record(c,'employee',dict(name='DEMO Morgan Mechanic',role='MECHANIC',active=1))
    save_record(c,'employee',dict(name='DEMO Riley Advisor',role='ADVISOR',active=1))
    save_record(c,'service',dict(name='DEMO Brake labor',rate_cents='100.00',active=1))
    save_record(c,'service',dict(name='DEMO Inspection labor',rate_cents='80.00',active=1))
    save_record(c,'part',dict(part_number='DEMO-PAD',name='DEMO Brake part',price_cents='40.00',reorder_level=3,active=1))
    save_record(c,'part',dict(part_number='DEMO-FILTER',name='DEMO Filter',price_cents='15.00',reorder_level=2,active=1))
    adjust_stock(c,1,10,'DEMO opening inventory')
    adjust_stock(c,2,1,'DEMO opening inventory')
    o=create_order(c,1,'DEMO brake concern',45000)
    update_order(c,o,'DEMO inspection complete','DEMO authorization for teaching example')
    add_labor(c,o,1,1,'1.50')
    add_part(c,o,1,2)
    i=finalize(c,o,'0')
    pay(c,i,'100','CASH','demo-initial-payment')
    create_order(c,3,'DEMO routine inspection',60000)

REPORTS={
 'Open work': "SELECT o.order_id,c.name AS bill_to,v.vin,o.opened_at,o.status,o.complaint FROM repair_order o JOIN customer c ON c.customer_id=o.bill_to_customer_id JOIN vehicle v ON v.vehicle_id=o.vehicle_id WHERE o.status IN ('OPEN','IN_PROGRESS') ORDER BY o.opened_at,o.order_id",
 'Vehicle history': "SELECT v.vin,o.order_id,o.opened_at,o.odometer,o.complaint,o.status,i.total_cents,i.balance_cents FROM vehicle v JOIN repair_order o ON o.vehicle_id=v.vehicle_id LEFT JOIN invoice_balance i ON i.order_id=o.order_id ORDER BY v.vin,o.opened_at DESC,o.order_id DESC",
 'Unpaid invoices': 'SELECT invoice_id,order_id,customer_label,issued_at,total_cents,paid_cents,balance_cents FROM invoice_balance WHERE balance_cents>0 ORDER BY issued_at',
}
