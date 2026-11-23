"""Persisted native outcome verifier; no solution text or declared status credit."""
from collections import Counter
from decimal import Decimal,InvalidOperation
import csv
from cuaverify import load_site,OUTPUT_DIR,run
ROWS=[('SET-906','7101','A-MUG','CAP-118','Mira Lane','2026-11','Sales','40.00'),('SET-906','7101','A-TRAY','CAP-118','Mira Lane','2026-11','Sales','80.00'),('SET-906','7101','A-MUG','RF-371','Mira Lane','2026-11','Sales Returns','-40.00'),('SET-906','7103','X-BOWL','CAP-119','Mira Lane','2026-11','Sales','55.00'),('SET-907','7102','B-CUP','CAP-209','Evan Reed','2026-10','Shopify Clearing','40.00'),('SET-907','7102','B-VASE','CAP-209','Evan Reed','2026-10','Shopify Clearing','135.00'),('SET-907','7102','B-CUP','RF-684','Evan Reed','2026-11','Sales Returns','-40.00')]
def cents(x):
 try:return Decimal(str(x)).quantize(Decimal('.01'))
 except (InvalidOperation,ValueError):return None
def text(x):return ' '.join(str(x).lower().split())
def index(rows):return {r['id']:r for r in rows}
def preserved(before,after):
 old,new=index(before),index(after)
 return old.keys()==new.keys() and all(all(new[k].get(field)==value for field,value in record.items()) for k,record in old.items())

def refund(o,line,ref):
 rs=o.get('refunds',[])
 return len(rs)==1 and rs[0].get('paymentMethod')=='original' and rs[0].get('status')=='succeeded' and cents(rs[0].get('total'))==40 and cents(rs[0].get('shipping',0))==0 and ref.lower() in text(rs[0].get('note')) and len(rs[0].get('lineItems',[]))==1 and rs[0]['lineItems'][0].get('lineItemId')==line and rs[0]['lineItems'][0].get('quantity')==1 and cents(rs[0]['lineItems'][0].get('amount'))==40

def damaged_not_restocked(order):
 refund_record=order['refunds'][0]
 return refund_record.get('restock') is False and refund_record['lineItems'][0].get('restock',False) is False

def splits(t,settlement,accounts,customers):
 want=[r for r in ROWS if r[0]==settlement];actual=t.get('splits',[])
 if t.get('status')!='posted' or len(actual)!=len(want) or cents(t.get('amount'))!=135:return False
 unused=list(actual)
 for r in want:
  match=next((a for a in unused if text(accounts.get(a.get('accountId'),{}).get('name'))==text(r[6]) and text(customers.get(a.get('customerId'),{}).get('name'))==text(r[4]) and text(a.get('category'))==text(r[6]) and text(a.get('customer'))==text(r[4]) and cents(a.get('amount'))==cents(r[7]) and all(text(v) in text(a.get('description')) for v in [r[1],r[2],r[3],r[5]])),None)
  if match is None:return False
  unused.remove(match)
 return not unused

def ledger():
 try:
  with (OUTPUT_DIR/'November-return-reconciliation.csv').open(encoding='utf-8-sig',newline='') as f:
   rows=list(csv.DictReader(f))
  keys=['settlement','order','line','reference','customer','source_period','category','amount']
  def norm(r):return tuple(text(r[k]) if k!='amount' else cents(r[k]) for k in keys)
  return Counter(norm(r) for r in rows)==Counter(norm(dict(zip(keys,r))) for r in ROWS)
 except (OSError,KeyError,csv.Error):return False

def evaluate(g):
 before,s=load_site('shopify');qb0,q=load_site('quickbooks');orders=index(s.get('orders',[]));original=index(before['orders']);tx=index(q.get('transactions',[]));products=index(s.get('products',[]))
 a=refund(orders.get('order-7101',{}),'A-MUG','RF-371')
 damaged=orders.get('order-7102',{})
 b=refund(damaged,'B-CUP','RF-684') and damaged_not_restocked(damaged)
 sa=splits(tx.get('SET-906',{}),'SET-906',index(qb0.get('accounts',[])),index(qb0.get('customers',[])));sb=splits(tx.get('SET-907',{}),'SET-907',index(qb0.get('accounts',[])),index(qb0.get('customers',[])))
 x=orders.get('order-7103',{});replacement=x.get('fulfillmentStatus')=='fulfilled' and x.get('lineItems')==original['order-7103']['lineItems'] and x.get('financialStatus')=='paid' and not x.get('refunds')
 stock=all(products.get('prod-'+code,{}).get('variants',[{}])[0].get('inventoryQuantity')==qty for code,qty in [('A-MUG',9),('B-CUP',6),('X-BOWL',8),('OLD',12)])
 protected=preserved(qb0.get('accounts',[]),q.get('accounts',[])) and preserved(qb0.get('customers',[]),q.get('customers',[])) and orders.get('order-7090')==original['order-7090'] and tx.get('old-bank')==index(qb0['transactions'])['old-bank'] and len(orders)==len(original) and len(tx)==len(qb0['transactions']) and all(orders.get(k,{}).get('lineItems')==v['lineItems'] for k,v in original.items())
 for cid,w,ok in [('A_RETURN',10,a),('B_RETURN',10,b),('A_SPLIT',15,sa),('B_SPLIT',15,sb),('REPLACEMENT',10,replacement),('STOCK',10,stock),('RECONCILIATION',30,all([a,b,sa,sb,replacement,stock,protected,ledger()]))]:g.add(cid,w,ok,core=True)
if __name__=='__main__':run('cua-hard/hx09-exchange-line-reconciliation','1.1.2',evaluate)
