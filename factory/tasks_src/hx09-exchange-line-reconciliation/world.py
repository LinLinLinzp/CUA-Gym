"""Deterministic native Shopify / QuickBooks world and materially distinct fixtures."""

from pathlib import Path

from copy import deepcopy
from decimal import Decimal

import csv,json,sys

STAMP='2026-11-19T14:00:00Z'

ROWS=[['SET-906','7101','A-MUG','CAP-118','Mira Lane','2026-11','Sales','40.00'],['SET-906','7101','A-TRAY','CAP-118','Mira Lane','2026-11','Sales','80.00'],['SET-906','7101','A-MUG','RF-371','Mira Lane','2026-11','Sales Returns','-40.00'],['SET-906','7103','X-BOWL','CAP-119','Mira Lane','2026-11','Sales','55.00'],['SET-907','7102','B-CUP','CAP-209','Evan Reed','2026-10','Shopify Clearing','40.00'],['SET-907','7102','B-VASE','CAP-209','Evan Reed','2026-10','Shopify Clearing','135.00'],['SET-907','7102','B-CUP','RF-684','Evan Reed','2026-11','Sales Returns','-40.00']]

HEAD=['settlement','order','line','reference','customer','source_period','category','amount']

def write(p,v):

 p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,indent=2)+'\n')

def ledger(p,rows):

 p.parent.mkdir(parents=True,exist_ok=True)

 with p.open('w',newline='') as f:

  w=csv.writer(f);w.writerow(HEAD);w.writerows(rows)

def sales_analytics(orders):
    """Seed the store's actual sales series without unrelated demo traffic."""
    by_day = {}
    for order in orders:
        day = order['createdAt'][:10]
        by_day.setdefault(day, []).append(order)

    daily = []
    for day, sales in sorted(by_day.items()):
        total = sum(Decimal(order['totalPrice']) for order in sales)
        products = {}
        for order in sales:
            for line in order['lineItems']:
                product = products.setdefault(line['productId'], {
                    'productId': line['productId'], 'title': line['title'],
                    'quantity': 0, 'revenue': Decimal('0.00'),
                })
                product['quantity'] += line['quantity']
                product['revenue'] += Decimal(line['price']) * line['quantity']
        daily.append(dict(
            date=day, totalSales=float(total), ordersCount=len(sales),
            averageOrderValue=float(total / len(sales)),
            onlineStoreSessions=0, returningCustomerRate=0, conversionRate=0,
            topProducts=[dict(product, revenue=float(product['revenue']))
                         for product in products.values()],
            topReferrers=[], sessionsByLocation=[],
        ))

    month = [row for row in daily if row['date'].startswith(STAMP[:7])]
    return dict(dailyMetrics=daily,
                totalSalesThisMonth=sum(row['totalSales'] for row in month),
                totalOrdersThisMonth=sum(row['ordersCount'] for row in month),
                totalSessionsThisMonth=0)

CATALOG_DIR = Path(__file__).with_name('catalog-thumbnails')

def thumbnail_url(sku):
 return f'/files/__SID__/catalog-{sku}.jpg'

def write_catalog_files(root):
 dest = root/'seed/files/shopify'
 dest.mkdir(parents=True, exist_ok=True)
 for file in sorted(CATALOG_DIR.glob('*.jpg')):
  (dest/f'catalog-{file.name}').write_bytes(file.read_bytes())

def seed():

 people=[dict(id='c1',firstName='Mira',lastName='Lane',email='mira@example.test',addresses=[],ordersCount=2,totalSpent='175.00',tags=[],createdAt=STAMP),dict(id='c2',firstName='Evan',lastName='Reed',email='evan@example.test',addresses=[],ordersCount=1,totalSpent='175.00',tags=[],createdAt=STAMP)]

 orders=[]

 for n,person,items,period in [(7101,people[0],[('A-MUG','Mug','40.00'),('A-TRAY','Tray','80.00')],'2026-11'),(7102,people[1],[('B-CUP','Cup','40.00'),('B-VASE','Vase','135.00')],'2026-10'),(7103,people[0],[('X-BOWL','Replacement bowl','55.00')],'2026-11'),(7090,people[1],[('OLD','Historical coaster','15.00')],'2026-10')]:

  total=sum(float(x[2]) for x in items)

  orders.append(dict(id='order-'+str(n),name='#'+str(n),orderNumber=n,email=person['email'],customer=person,createdAt=period+'-12T14:00:00Z',updatedAt=STAMP,paymentMethodLabel='Visa ending 4242 (original payment)',financialStatus='paid',fulfillmentStatus=None if n==7103 else 'fulfilled',currency='USD',subtotalPrice=str(total),totalPrice=str(total),totalShippingPrice='0.00',totalTax='0.00',totalDiscounts='0.00',tags=[],note='Paid replacement for #7101. CAP-119. Reserve has NOT been deducted from physical saleable inventory.' if n==7103 else 'Capture '+('CAP-118' if n==7101 else 'CAP-209'),refunds=[],shippingAddress={},billingAddress={},timeline=[],lineItems=[dict(id=code,productId='prod-'+code,title=title,variantTitle='Standard',sku=code,price=price,quantity=1,imageSrc=thumbnail_url(code)) for code,title,price in items]))

 products=[]

 for code,title,qty,price in [('A-MUG','Mug',8,'40.00'),('B-CUP','Cup',6,'40.00'),('X-BOWL','Replacement bowl',9,'55.00'),('OLD','Historical coaster',12,'15.00')]:

  products.append(dict(id='prod-'+code,title=title,description='',vendor='Brindle Home',productType='Home',status='active',tags=[],images=[dict(id='image-'+code,src=thumbnail_url(code),alt=title,position=1)],options=[],createdAt=STAMP,updatedAt=STAMP,variants=[dict(id='variant-'+code,title='Standard',sku=code,price=price,inventoryQuantity=qty,inventoryManagement='shopify',inventoryPolicy='deny',option1='Standard',position=1)]))

 shop=dict(store=dict(name='Brindle Home'),orders=orders,customers=people,products=products,discounts=[],draftOrders=[],analytics=sales_analytics(orders),settings=dict(storeName='Brindle Home',currency='USD'))

 tx=[dict(id=s,accountId='bank',date='2026-11-19',description='PROCESSOR '+s,bankDetail='Remittance '+s,payee='',amount=135,type='credit',category='Uncategorized Income',matchedTo=None,status='pending',isReconciled=False) for s in ['SET-906','SET-907']]

 tx.append(dict(id='old-bank',accountId='bank',date='2026-10-31',description='Historical rent',payee='Landlord',amount=-200,type='debit',category='Rent',matchedTo=None,status='posted',isReconciled=True))

 qb=dict(company=dict(name='Brindle Home'),accounts=[dict(id='bank',name='Checking',number='1000',type='Bank',detailType='',balance=1000,bankBalance=1270,isActive=True),dict(id='sales',name='Sales',number='4000',type='Income',detailType='',balance=0,bankBalance=0,isActive=True),dict(id='sales-returns',name='Sales Returns',number='4010',type='Income',detailType='',balance=0,bankBalance=0,isActive=True),dict(id='clearing',name='Shopify Clearing',number='1200',type='Other Current Assets',detailType='',balance=175,bankBalance=175,isActive=True)],transactions=tx,invoices=[],customers=[dict(id=p['id'],name=p['firstName']+' '+p['lastName'],email=p['email'],company='',phone='',address='',notes='',createdAt='2026-11-19',balance=0,isActive=True) for p in people],vendors=[],expenses=[],products=[],bills=[],employees=[],budgets=[],projects=[])

 return dict(shopify=shop,quickbooks=qb)

def apply(s,which='both'):

 for n,line,ref in [(7101,'A-MUG','RF-371'),(7102,'B-CUP','RF-684')]:

  if which=='A' and n==7102:continue

  o=next(o for o in s['shopify']['orders'] if o['orderNumber']==n)

  o.update(financialStatus='partially_refunded',refunds=[dict(id='refund-'+ref,createdAt=STAMP,lineItems=[dict(lineItemId=line,sku=line,quantity=1,amount='40.00')],shipping='0.00',total='40.00',note=ref,paymentMethod='original',status='succeeded',restock=n==7101,notifyCustomer=True)])

  settlement='SET-906' if n==7101 else 'SET-907'

  t=next(t for t in s['quickbooks']['transactions'] if t['id']==settlement)

  t.update(status='posted',payee='Mira Lane' if n==7101 else 'Evan Reed',category='Sales',splits=[dict(category=r[6],accountId={'Sales':'sales','Sales Returns':'sales-returns','Shopify Clearing':'clearing'}[r[6]],customer=r[4],customerId='c1' if r[4]=='Mira Lane' else 'c2',description=' '.join([r[1],r[2],r[3],r[5]]),amount=r[7]) for r in ROWS if r[0]==settlement])

 s['shopify']['orders'][2]['fulfillmentStatus']='fulfilled'

 if which=='both':

  s['shopify']['products'][0]['variants'][0]['inventoryQuantity']=9

  s['shopify']['products'][2]['variants'][0]['inventoryQuantity']=8



def main(out):

 s=seed()

 for k,v in s.items():write(out/'seed'/f'{k}.json',v)
 write_catalog_files(out)

 inp=out/'input';inp.mkdir(parents=True,exist_ok=True)

 (inp/'receiving-and-authority.txt').write_text('''Brindle Home | signed by Nina Holt, Operations | November 19\n#7101 Mira Lane: received 1 A-MUG in saleable condition; refund RF-371 $40. Retain A-TRAY. Customer accepted replacement X-BOWL under already-paid #7103, CAP-119 $55. Refund and replacement are independent cash legs; exchange difference is $15 collected, not a second refund. Dispatch replacement today.\n#7102 Evan Reed: received 1 B-CUP, cracked and quarantined. Refund RF-684 $40. Retain B-VASE. Do not add damaged cup to saleable inventory.\nShopify physical saleable starting counts: A-MUG 8, B-CUP 6, X-BOWL 9. Neither receiving nor replacement dispatch has been entered. No shipping refund. Historical #7090 and bank records are closed.\nAccounting policy: current sales -> Sales; returns -> Sales Returns; prior-period sale proceeds already recognized -> Shopify Clearing. Use capture source month, not release date, on clearing lines. Refunds belong to November. All source references belong in split descriptions.\n''')

 ledger(inp/'processor-advice.csv',ROWS)

 (inp/'processor-cover.txt').write_text('Processor November 19: SET-906 remits CAP-118 $120 less RF-371 $40 plus CAP-119 $55 = $135. SET-907 releases October-held CAP-209 $175 less current RF-684 $40 = $135. CAP-209 revenue was already booked in October. Do not book it as November sales. Both deposits dated November 19; bank order is not customer order. Reference, not amount or recency, determines ownership.\n')

 # Minimal contrast exchanges receiving references and saleable dispositions, keeping dates/totals fixed.

 contrast=out/'contrast-reference-swap.txt';contrast.write_text('Independent reset contrast (not the live instruction): RF-371 belongs to B-CUP / #7102, RF-684 belongs to A-MUG / #7101; A-MUG damaged and B-CUP saleable. Deposit advice changes refund references correspondingly. Correct refund notes, settlement split lineage and closing counts change; dates and totals do not.\n')

 # Reviewer contrast: a resettable second input/seed with the same dates and amounts.

 contrast=out/'contrast';contrast.mkdir(parents=True,exist_ok=True)

 swapped=deepcopy(s)

 for site,v in swapped.items():write(contrast/'seed'/f'{site}.json',v)
 write_catalog_files(contrast)

 swapped_rows=deepcopy(ROWS)

 for r in swapped_rows:

  if r[3]=='RF-371':r[3]='RF-684'

  elif r[3]=='RF-684':r[3]='RF-371'

 ledger(contrast/'input'/'processor-advice.csv',swapped_rows)

 (contrast/'input'/'receiving-and-authority.txt').write_text((inp/'receiving-and-authority.txt').read_text().replace('RF-371','TEMP').replace('RF-684','RF-371').replace('TEMP','RF-684').replace('A-MUG in saleable condition','A-MUG damaged and quarantined').replace('B-CUP, cracked and quarantined','B-CUP in saleable condition').replace('Do not add damaged cup to saleable inventory.','Do not add damaged mug to saleable inventory.'))

 write(contrast/'expected-business-delta.json',dict(refunds={'7101':'RF-684','7102':'RF-371'},closing_stock={'A-MUG':8,'B-CUP':7,'X-BOWL':8},unchanged_deposits={'SET-906':135,'SET-907':135}))



 (contrast/'input'/'processor-cover.txt').write_text((inp/'processor-cover.txt').read_text().replace('RF-371','TEMP').replace('RF-684','RF-371').replace('TEMP','RF-684'))

 contrast_end=deepcopy(s);apply(contrast_end)

 for order in contrast_end['shopify']['orders'][:2]:

  saleable=order['orderNumber']==7102
  for refund in order.get('refunds',[]):
   refund.update(note='RF-371' if saleable else 'RF-684',restock=saleable)
   for line in refund['lineItems']:line['restock']=saleable

 for transaction in contrast_end['quickbooks']['transactions'][:2]:

  for line in transaction.get('splits',[]):line['description']=line['description'].replace('RF-371','TEMP').replace('RF-684','RF-371').replace('TEMP','RF-684')

 contrast_end['shopify']['products'][0]['variants'][0]['inventoryQuantity']=8

 contrast_end['shopify']['products'][1]['variants'][0]['inventoryQuantity']=7

 for site,data in contrast_end.items():write(contrast/'golden'/f'{site}.json',data)

 ledger(contrast/'golden_output'/'November-return-reconciliation.csv',swapped_rows)

 for name in ['golden','equivalent','nop','bypass','one_core','false_completion','wrong_line','wrong_customer','wrong_period','wrong_stock','duplicate_refund','partial_returns','totals_only','wrong_payment','wrong_account','damaged_restock_corrected']:

  cur=deepcopy(s);rows=deepcopy(ROWS)

  if name not in ['nop','bypass','false_completion']:apply(cur,'A' if name=='one_core' else 'both')

  if name=='wrong_payment':
   cur['shopify']['orders'][0]['refunds'][0]['paymentMethod']='store_credit';cur['shopify']['customers'][0]['storeCreditBalance']='40.00'

  if name=='wrong_account':cur['quickbooks']['transactions'][0]['splits'][0].update(accountId='clearing',category='Shopify Clearing')

  if name=='wrong_line':cur['shopify']['orders'][0]['refunds'][0]['lineItems'][0].update(lineItemId='A-TRAY',sku='A-TRAY')

  if name=='wrong_customer':cur['quickbooks']['transactions'][0]['splits'][0].update(customer='Evan Reed',customerId='c2')

  if name=='wrong_period':rows[4][5]='2026-11'

  if name=='wrong_stock':cur['shopify']['products'][1]['variants'][0]['inventoryQuantity']=7

  if name=='damaged_restock_corrected':
   record=cur['shopify']['orders'][1]['refunds'][0]
   record['restock']=True
   record['lineItems'][0]['restock']=True

  if name=='duplicate_refund':cur['shopify']['orders'][1]['refunds']*=2

  if name in ['partial_returns','totals_only']:

   cur['quickbooks']=deepcopy(s['quickbooks']);cur['shopify']['products']=deepcopy(s['shopify']['products']);cur['shopify']['products'][0]['variants'][0]['inventoryQuantity']=9;cur['shopify']['orders'][2]['fulfillmentStatus']=None

  if name=='bypass':

   for t in cur['quickbooks']['transactions'][:2]:t.update(status='posted',payee='Processor',category='Sales')

  if name=='equivalent':
   for order in cur['shopify']['orders'][:2]:
    for refund in order.get('refunds',[]):refund.update(restock=False,notifyCustomer=False)

   for t in cur['quickbooks']['transactions'][:2]:

    t['splits'].reverse()

    for r in t['splits']:r['description']='Source: '+r['description'].upper()

  target=out/'variants'/name

  for site in s:

   write(target/'state'/site/'initial.json',s[site]);write(target/'state'/site/'current.json',cur[site])

   if name=='golden':write(out/'golden'/f'{site}.json',cur[site])

  if name=='false_completion':

   target.joinpath('output').mkdir(parents=True,exist_ok=True);target.joinpath('output/Completed.txt').write_text('All returns reconciled. Both deposits $135.')

  if name=='totals_only':rows=[['SET-906','','','','','','Sales','135.00'],['SET-907','','','','','','Sales','135.00']]

  if name not in ['nop','bypass','one_core','partial_returns','false_completion']:

   ledger(target/'output'/'November-return-reconciliation.csv',rows[::-1] if name=='equivalent' else rows)

  if name=='golden':ledger(out/'golden_output'/'November-return-reconciliation.csv',rows)

if __name__=='__main__':main(Path(sys.argv[1]))

