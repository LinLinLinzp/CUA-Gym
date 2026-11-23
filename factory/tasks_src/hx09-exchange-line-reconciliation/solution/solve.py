"""Reconcile the processor deposits through the 1280x800 desktop UI."""
from pathlib import Path
from computer import act,click,key,type_text,wait
ROWS=[['SET-906','7101','A-MUG','CAP-118','Mira Lane','2026-11','Sales','40.00'],['SET-906','7101','A-TRAY','CAP-118','Mira Lane','2026-11','Sales','80.00'],['SET-906','7101','A-MUG','RF-371','Mira Lane','2026-11','Sales Returns','-40.00'],['SET-906','7103','X-BOWL','CAP-119','Mira Lane','2026-11','Sales','55.00'],['SET-907','7102','B-CUP','CAP-209','Evan Reed','2026-10','Shopify Clearing','40.00'],['SET-907','7102','B-VASE','CAP-209','Evan Reed','2026-10','Shopify Clearing','135.00'],['SET-907','7102','B-CUP','RF-684','Evan Reed','2026-11','Sales Returns','-40.00']]
def shot(n):
 p=Path('/logs/agent/desktop');p.mkdir(parents=True,exist_ok=True);(p/(n+'.png')).write_bytes(act('screenshot'))
def address(url):
 key('Ctrl+l');type_text(url);key('Return');wait(1.2)
def open_evidence():
 key('Super+e');wait(.8)
 for name,image_name in (
  ('receiving-and-authority.txt','signed-receiving'),
  ('processor-cover.txt','processor-advice'),
 ):
  key('Ctrl+l');type_text('/workspace/input/'+name);key('Return');wait(1.2)
  if image_name=='signed-receiving':
   # Mousepad's Document > Word Wrap shows the full-length evidence lines.
   key('Alt+d');key('w')
  shot(image_name)
  key('Alt+F4');wait(.5)
 key('Alt+F4');wait(.5)
def fill(x,y,s):
 click(x,y);key('Ctrl+a');type_text(str(s))
def select_option(x,y,*keys):
 click(x,y)
 for option_key in keys:
  key(option_key)
 key('Return')
def refund(n,ref,restock=True):
 address('https://admin.shopify.com/orders/order-'+str(n));shot(str(n)+'-before')
 click(1077,193);wait(.4);shot(str(n)+'-refund-page')
 fill(850,372,1);fill(590,761,ref)
 if not restock:click(292,504)
 fill(1090,513,'40.00');shot(str(n)+'-original-payment-refund')
 click(1090,636);wait(.8);shot(str(n)+'-saved-refund')
def stock(code,qty):
 address('https://admin.shopify.com/products/prod-'+code)
 click(912,207);key('Ctrl+End');wait(.3);shot(code+'-inventory-before')
 fill(778,575,qty);click(912,207);key('Ctrl+Home');wait(.25);click(1180,183);wait(.7)
def settlement(code,rows):
 address('https://qbo.intuit.com/transactions');click(530,611);wait(.3);shot(code+'-expanded')
 click(1030,703);wait(.3);shot(code+'-split-transaction-modal')
 # The modal recenters as each line is added. Use its final layout for entry.
 click(181,484)
 if len(rows)==4:
  click(181,512)
  row_y=(350,405,460,515)
  save_y=744
 else:
  row_y=(362,417,472)
  save_y=733
 category_keys={'Sales':('s','a'), 'Sales Returns':('End','Up'), 'Shopify Clearing':('End',)}
 for y,r in zip(row_y,rows):
  select_option(266,y,*category_keys[r[6]])
  click(530,y);type_text(' '.join([r[1],r[2],r[3],r[5]]))
  select_option(800,y,r[4][0].lower())
  click(1000,y);type_text(r[7])
 shot(code+'-balanced-modal')
 click(1061,save_y);wait(.8);shot(code+'-saved-settlement')
def csv_output():
 # The processor advice is the approved complete line ledger; retain its text
 # periods and references while delivering the verified reconciled copy.
 key('Super+e');wait(.8);key('Ctrl+l');type_text('/workspace/input/processor-advice.csv');key('Return');wait(6)
 shot('ledger-import-dialog');click(1225,774);wait(1);key('Return');wait(.3);shot('ledger-open')
 key('Ctrl+Shift+s');wait(.7);key('Ctrl+a');type_text('/workspace/output/November-return-reconciliation.csv');key('Return');wait(.8)
 shot('ledger-csv-confirmation');click(806,462);wait(.7);shot('ledger-saved')
 key('Alt+F4');wait(.5);key('Alt+F4');wait(.5)
def main():
 open_evidence()
 refund(7101,'RF-371',True);refund(7102,'RF-684',False)
 address('https://admin.shopify.com/orders/order-7103');click(836,276);wait(.4);shot('replacement-dialog');click(800,567);wait(.6);shot('replacement-fulfilled')
 stock('X-BOWL',8)
 csv_output()
 # The split rows transcribe the opened advice and the checked receiving policy.
 for code in ['SET-906','SET-907']:settlement(code,[r for r in ROWS if r[0]==code])
if __name__=='__main__':main()
