from simple_salesforce import Salesforce
import json

config = json.load(open('config.json'))
sf = Salesforce(session_id=config['session_id'], instance_url=config['instance_url'])

# Describe the object
desc = sf.c2g__codaTransactionLineItem__c.describe()

# Find fields with debit, credit, or type in name
print('Fields with debit/credit/type in name:')
for field in desc['fields']:
    name = field['name'].lower()
    if any(word in name for word in ['debit', 'credit', 'type']):
        print(f"  {field['name']} ({field['type']})")
