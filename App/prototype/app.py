#!/usr/bin/env python3
"""Local-only academic reference app. No external packages or network services."""
import argparse, html, secrets, sqlite3, uuid
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse
import core

TOKEN=secrets.token_urlsafe(32)
DB=None
PORT=8765

def esc(v): return html.escape(str(v),quote=True)
def money(c): return f'${c/100:,.2f}'
def field(label,name,value='',kind='text',required=True):
    return f'<label>{esc(label)}<input name="{esc(name)}" type="{kind}" value="{esc(value)}" {"required" if required else ""}></label>'
def select(label,name,options,value=None):
    return f'<label>{esc(label)}<select name="{name}">'+''.join(f'<option value="{esc(k)}" {"selected" if str(k)==str(value) else ""}>{esc(v)}</option>' for k,v in options)+'</select></label>'
def hidden(name,value): return f'<input type="hidden" name="{esc(name)}" value="{esc(value)}">'
def form(action,body,button='Save',extra=None):
    return '<form method="post" action="/">'+hidden('csrf',TOKEN)+hidden('action',action)+''.join(hidden(k,v) for k,v in (extra or {}).items())+body+f'<button>{esc(button)}</button></form>'
def table(rows,entity=None):
    rows=list(rows)
    if not rows: return '<p class="muted">No matching records yet.</p>'
    cols=list(rows[0].keys())
    head=''.join('<th>'+esc(k.replace('_cents',' ($)').replace('hours_hundredths','hours').replace('_',' '))+'</th>' for k in cols)
    out='<div class="scroll"><table><thead><tr>'+head+('<th>Action</th>' if entity else '')+'</tr></thead><tbody>'
    for r in rows:
        out+='<tr>'+''.join('<td>'+esc(money(r[k]) if k.endswith('_cents') and r[k] is not None else (f'{r[k]/100:.2f}' if k=='hours_hundredths' else (r[k] if r[k] is not None else '—')))+'</td>' for k in cols)
        if entity:
            key=r['order_id' if entity=='orders' else entity+'_id']
            out+=f'<td><a href="/?{urlencode({"page":entity,"edit":key})}">Open</a></td>'
        out+='</tr>'
    return out+'</tbody></table></div>'

def shell(title,body,page='dashboard'):
    links=[('dashboard','Overview'),('customer','Customers'),('vehicle','Vehicles'),('orders','Repair orders'),('part','Parts & stock'),('service','Services'),('employee','Employees'),('reports','Reports')]
    nav=''.join(f'<a class="{"selected" if p==page else ""}" href="/?page={p}">{label}</a>' for p,label in links)
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(title)} | Repair study</title><style>
    :root{{--ink:#17333b;--accent:#087f83;--paper:#f2f5f4;--line:#d6e2df}}*{{box-sizing:border-box}}body{{margin:0;font:15px/1.5 system-ui,sans-serif;color:var(--ink);background:var(--paper)}}header{{background:var(--ink);color:white;padding:22px 4vw}}header strong{{font-size:24px}}header p{{margin:5px 0 0;color:#c5e0dc}}nav{{display:flex;flex-wrap:wrap;gap:6px;padding:12px 4vw;background:white;border-bottom:1px solid var(--line)}}nav a{{text-decoration:none;padding:8px 12px;border-radius:5px}}a{{color:#086b73}}nav .selected{{background:#def1eb}}main{{max-width:1380px;margin:auto;padding:24px 4vw 60px}}h1{{font-size:30px;margin:0 0 18px}}h2{{font-size:20px;margin-top:0}}section,.card{{padding:22px;background:white;border:1px solid var(--line);border-radius:10px;margin:0 0 20px}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:18px}}.stat{{font-size:34px;font-weight:700}}.muted{{color:#586d72}}.banner{{border-left:4px solid #d99e35;background:#fff8e9;padding:12px 16px;margin-bottom:20px}}form{{display:flex;align-items:end;flex-wrap:wrap;gap:12px}}label{{display:grid;gap:5px;min-width:160px;flex:1;font-size:13px;font-weight:600}}input,select{{min-width:0;width:100%;padding:10px;border:1px solid #afc2c2;border-radius:5px;background:white;font:inherit}}button{{border:0;border-radius:5px;padding:11px 17px;background:var(--accent);color:white;font:inherit;cursor:pointer}}button:hover{{background:#075c62}}table{{border-collapse:collapse;width:100%;font-size:13px}}th,td{{padding:10px 12px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}}th{{background:#eaf2ef;white-space:nowrap}}.scroll{{overflow-x:auto}}.small{{font-size:12px}}@media print{{header,nav,form,.banner{{display:none}}main{{padding:0}}section{{border:0}}}} 
    </style></head><body><header><strong>Repair workflow study</strong><p>Leo's Auto candidate project · COSC 457 · Four-person team</p></header><nav>{nav}</nav><main><div class="banner">Academic prototype · Fictional data only · Business rules and final course stack await confirmation.</div><h1>{esc(title)}</h1>{body}</main></body></html>'''

def options(c,entity,where='1=1'):
    return [(r[entity+'_id'],f"#{r[entity+'_id']} · "+(r['vin'] if entity=='vehicle' else r['name'])) for r in c.execute(f'SELECT * FROM {entity} WHERE {where}')]

def catalog(c,page,q):
    edit=q.get('edit','')
    r=dict(core.one(c,f'SELECT * FROM {page} WHERE {page}_id=?',(edit,))) if edit else {}
    body=''
    for col in core.CATALOG[page]:
        val=r.get(col,1 if col=='active' else '')
        if col=='active': body+=select('Active','active',[(1,'Active'),(0,'Inactive')],val)
        elif col=='role': body+=select('Role','role',[(s,s) for s in ('MECHANIC','ADVISOR','MANAGER')],val)
        elif col=='customer_id': body+=select('Current owner',col,options(c,'customer'),val)
        else:
            title={'rate_cents':'Hourly rate ($)','price_cents':'Unit price ($)'}.get(col,col.replace('_',' ').title())
            if col.endswith('_cents') and col in r: val=f'{val/100:.2f}'
            body+=field(title,col,val,required=col not in ('phone','email'))
    title='Edit record' if edit else 'Add record'
    out=f'<section><h2>{title}</h2>'+form('save',body,extra={'entity':page,'record_id':edit})+'</section>'
    query=q.get('q','').lower()
    rows=list(c.execute(f'SELECT * FROM {"stock" if page=="part" else page} ORDER BY {page}_id'))
    if query: rows=[r for r in rows if query in ' '.join(str(v) for v in r).lower()]
    out+='<section><h2>Records</h2><form method="get">'+hidden('page',page)+field('Search records','q',q.get('q',''),required=False)+'<button>Search</button></form><br>'+table(rows,page)+'</section>'
    if page=='part':
        out+='<section><h2>Receive or adjust stock</h2><p>Enter a signed whole-unit change and reason. Negative adjustments cannot take stock below zero.</p>'+form('stock',select('Part','part_id',options(c,'part'))+field('Quantity change (+/-)','delta')+field('Reason','reason'),'Record movement')+'</section>'
    out+='<p class="muted">Archive customers, employees, services or parts by setting Active to Inactive. Referenced history is retained. Vehicle ownership edits do not change existing orders’ bill-to customer. VIN-like demo identifiers are not validated as real VINs.</p>'
    return out

def order_screen(c,q):
    out='<section><h2>Open a repair order</h2>'+form('open',select('Vehicle','vehicle_id',options(c,'vehicle'))+field('Complaint','complaint')+field('Odometer','odometer'),'Create order')+'</section>'
    rows=c.execute('SELECT order_id,vehicle_id,bill_to_customer_id,status,complaint,opened_at FROM repair_order ORDER BY order_id DESC')
    out+='<section><h2>All repair orders</h2>'+table(rows,'orders')+'</section>'
    if not q.get('edit'): return out
    oid=int(q['edit']); r=core.one(c,'SELECT * FROM repair_order WHERE order_id=?',(oid,)); extras={'order_id':oid}
    out+=f'<section><h2>Order #{oid} · {esc(r["status"])}</h2>'+table([r])+'</section>'
    if r['status'] in ('OPEN','IN_PROGRESS'):
        out+='<section><h2>Diagnosis and authorization</h2><p>Record the fictional authorization details before entering work. This field is documentation, not a real customer approval service.</p>'+form('authorize',field('Diagnosis','diagnosis',r['diagnosis'])+field('Authorization note','authorization',r['authorization_note']),'Save and start work',extras)+'</section>'
        if r['status']=='IN_PROGRESS':
            out+='<div class="grid"><section><h2>Add labor</h2>'+form('labor',select('Service','service_id',options(c,'service','active=1'))+select('Mechanic','mechanic_id',options(c,'employee',"active=1 AND role='MECHANIC'"))+field('Hours (e.g. 1.50)','hours'),'Add labor',extras)+'</section>'
            out+='<section><h2>Add parts</h2>'+form('part',select('Part','part_id',options(c,'part','active=1'))+field('Whole units','quantity'),'Issue parts',extras)+'</section></div>'
    for kind in ('labor','part'):
        lines=list(c.execute(f'SELECT * FROM {kind}_line WHERE order_id=?',(oid,)))
        out+=f'<section><h2>{kind.title()} lines</h2>'+table(lines)
        if lines and r['status'] in ('OPEN','IN_PROGRESS'):
            opts=[(x[kind+'_line_id'],f"#{x[kind+'_line_id']} {x['description']}") for x in lines]
            out+=form('remove',select('Line to remove','line_id',opts),'Remove selected line',dict(extras,kind=kind))
        out+='</section>'
    labor,parts=core.totals(c,oid)
    out+=f'<section><h2>Charges</h2><p>Labor {money(labor)} · Parts {money(parts)} · Subtotal {money(labor+parts)}</p>'
    if r['status']=='IN_PROGRESS':
        out+='<p>Tax is a manually entered demonstration amount. No jurisdictional tax calculation is implemented. Finalization locks this order and its invoice.</p>'+form('finalize',field('Demonstration tax ($)','tax','0.00'),'Complete and issue invoice',extras)
    if r['status'] in ('OPEN','IN_PROGRESS'):
        out+='<hr><p>Cancel an unbilled order: returns issued parts and removes draft labor/part lines. The cancelled order and inventory ledger remain.</p>'+form('cancel','', 'Cancel this order',extras)
    out+='</section>'
    inv=c.execute('SELECT * FROM invoice_balance WHERE order_id=?',(oid,)).fetchone()
    if inv:
        out+='<section><h2>Frozen invoice</h2>'+table([inv])+'<p class="small">Use browser Print for a local paper/PDF copy. This is a class demonstration, not a business invoice.</p>'
        if inv['balance_cents']>0:
            out+=form('pay',field('Payment ($)','amount')+select('Method','method',[(s,s) for s in ('CASH','CHECK','CARD_RECORD','OTHER')]),'Record payment',dict(extras,invoice_id=inv['invoice_id'],request_key=str(uuid.uuid4())))
        else: out+='<p><strong>Paid in full.</strong></p>'
        out+='<h3>Recorded payments</h3>'+table(c.execute('SELECT payment_id,paid_at,amount_cents,method FROM payment WHERE invoice_id=?',(inv['invoice_id'],)))+'</section>'
    return out

class Handler(BaseHTTPRequestHandler):
    def valid_host(self): return self.headers.get('Host') in (f'127.0.0.1:{PORT}',f'localhost:{PORT}')
    def send(self,body,status=200,kind='text/html; charset=utf-8'):
        data=body.encode('utf-8'); self.send_response(status); self.send_header('Content-Type',kind); self.send_header('Content-Length',str(len(data))); self.send_header('Cache-Control','no-store'); self.send_header('X-Content-Type-Options','nosniff'); self.send_header('X-Frame-Options','DENY'); self.end_headers(); self.wfile.write(data)
    def do_GET(self):
        if not self.valid_host(): return self.send('Invalid host',403)
        q={k:v[0] for k,v in parse_qs(urlparse(self.path).query).items()}; page=q.get('page','dashboard')
        c=core.connect(DB)
        try:
            if page=='reports':
                name=q.get('report','Vehicle history'); sql=core.REPORTS.get(name)
                if not sql: raise ValueError('Unknown report.')
                rows=list(c.execute(sql)); needle=q.get('q','').lower()
                if needle: rows=[r for r in rows if needle in ' '.join(str(v) for v in r).lower()]
                body='<section><form method="get">'+hidden('page','reports')+select('Report','report',[(s,s) for s in core.REPORTS],name)+field('Filter results (e.g. VIN)','q',q.get('q',''),required=False)+'<button>Run report</button></form>'+table(rows)+'</section>'
                title='Reports'
            elif page=='orders': title='Repair orders'; body=order_screen(c,q)
            elif page in core.CATALOG: title={'part':'Parts & stock'}.get(page,page.title()+' records'); body=catalog(c,page,q)
            elif page=='dashboard':
                metrics=[('Open orders',c.execute("SELECT COUNT(*) FROM repair_order WHERE status IN ('OPEN','IN_PROGRESS')").fetchone()[0]),('Outstanding invoices',money(c.execute('SELECT COALESCE(SUM(balance_cents),0) FROM invoice_balance').fetchone()[0])),('Low-stock parts',c.execute('SELECT COUNT(*) FROM stock WHERE active=1 AND on_hand<=reorder_level').fetchone()[0])]
                body='<div class="grid">'+''.join(f'<section><h2>{esc(label)}</h2><div class="stat">{esc(v)}</div></section>' for label,v in metrics)+'</div><section><h2>Start with one complete repair</h2><p>1. Create customer and vehicle records. 2. Open a repair order. 3. Record diagnosis and authorization. 4. Add labor and parts. 5. Finalize an invoice. 6. Record payment and inspect reports.</p><p>The seeded completed order totals $230.00 with $100.00 paid and $130.00 due. Those are illustrative values only.</p><a href="/?page=orders&edit=1">Inspect the seeded repair →</a></section><section><h2>Open work</h2>'+table(c.execute(core.REPORTS['Open work']),'orders')+'</section>'
                title='Project overview'
            else: raise ValueError('Unknown page.')
            self.send(shell(title,body,page))
        except (ValueError,sqlite3.Error) as e: self.send(shell('Unable to open page',f'<section><p>{esc(e)}</p><a href="/">Return to overview</a></section>'),400)
        finally: c.close()
    def do_POST(self):
        if not self.valid_host(): return self.send('Invalid host',403)
        length=int(self.headers.get('Content-Length','0'))
        if length>16384: return self.send('Request too large',413)
        d={k:v[0] for k,v in parse_qs(self.rfile.read(length).decode(),keep_blank_values=True).items()}
        if not secrets.compare_digest(d.get('csrf',''),TOKEN): return self.send('Invalid form token. Reload the page.',403)
        c=core.connect(DB)
        try:
            action=d.get('action'); oid=d.get('order_id'); dest={'page':'orders','edit':oid or ''}
            if action=='save':
                rid=core.save_record(c,d['entity'],d,d.get('record_id') or None); dest={'page':d['entity'],'edit':rid}
            elif action=='open': dest['edit']=core.create_order(c,d['vehicle_id'],d['complaint'],d['odometer'])
            elif action=='authorize': core.update_order(c,oid,d['diagnosis'],d['authorization'])
            elif action=='labor': core.add_labor(c,oid,d['service_id'],d['mechanic_id'],d['hours'])
            elif action=='part': core.add_part(c,oid,d['part_id'],d['quantity'])
            elif action=='remove': core.remove_line(c,d['kind'],d['line_id'])
            elif action=='finalize': core.finalize(c,oid,d['tax'])
            elif action=='pay': core.pay(c,int(d['invoice_id']),d['amount'],d['method'],d['request_key'])
            elif action=='cancel': core.cancel_order(c,oid)
            elif action=='stock': core.adjust_stock(c,d['part_id'],d['delta'],d['reason']); dest={'page':'part'}
            else: raise ValueError('Unknown action.')
            self.send_response(303); self.send_header('Location','/?'+urlencode(dest)); self.end_headers()
        except (ValueError,KeyError,sqlite3.Error) as e:
            self.send(shell('Change not saved',f'<section><p>{esc(e)}</p><p>The operation was rejected. Transactional changes were rolled back.</p><p>Use your browser Back button to correct the form, or <a href="/">return to overview</a>.</p></section>'),400)
        finally: c.close()

def main():
    global DB,PORT
    parser=argparse.ArgumentParser(); parser.add_argument('--db',type=Path,default=Path(__file__).with_name('demo.sqlite3')); parser.add_argument('--port',type=int,default=8765); args=parser.parse_args()
    DB=args.db; PORT=args.port
    if not DB.exists():
        core.initialize(DB); c=core.connect(DB)
        try: core.seed(c)
        finally: c.close()
    server=HTTPServer(('127.0.0.1',PORT),Handler)
    print(f'Fictional-data prototype: http://127.0.0.1:{PORT} | DB: {DB}',flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()
if __name__=='__main__': main()
