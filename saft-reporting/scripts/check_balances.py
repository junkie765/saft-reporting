import sys
import os
import json
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.salesforce.auth import authenticate
from src.salesforce.bulk_client import SalesforceBulkClient
from src.transformers.certinia_transformer import CertiniaTransformer

config = json.load(open('config.json'))

# Authenticate (uses session_id from config.json)
sf = authenticate(config)

bulk = SalesforceBulkClient(sf, config)

start = datetime(2024,1,1)
end = datetime(2024,1,31)

print('Extracting data (GL accounts + transaction lines)...')
data = bulk.extract_certinia_data(start, end, 'Scalefocus AD')

trans = CertiniaTransformer(config)

gl_accounts = trans._transform_gl_accounts(data.get('gl_accounts', []), data.get('transaction_lines', []))

print(f'Transformed GL accounts: {len(gl_accounts)}')
nonzero = [a for a in gl_accounts if a.get('closing_debit_balance',0) > 0 or a.get('closing_credit_balance',0) > 0]
print(f'Accounts with non-zero closing balance: {len(nonzero)}')

for a in nonzero[:50]:
    print(f"{a['account_id']:>12} | opening D {a.get('opening_debit_balance',0):12.2f} | opening C {a.get('opening_credit_balance',0):12.2f} | closing D {a.get('closing_debit_balance',0):12.2f} | closing C {a.get('closing_credit_balance',0):12.2f} | desc: {a.get('account_description','')}")

# Print summary of totals

total_opening_debit = sum(a.get('opening_debit_balance',0) for a in gl_accounts)
total_opening_credit = sum(a.get('opening_credit_balance',0) for a in gl_accounts)
total_closing_debit = sum(a.get('closing_debit_balance',0) for a in gl_accounts)
total_closing_credit = sum(a.get('closing_credit_balance',0) for a in gl_accounts)

print('\nTotals:')
print('Opening Debit:', f"{total_opening_debit:.2f}")
print('Opening Credit:', f"{total_opening_credit:.2f}")
print('Closing Debit:', f"{total_closing_debit:.2f}")
print('Closing Credit:', f"{total_closing_credit:.2f}")
