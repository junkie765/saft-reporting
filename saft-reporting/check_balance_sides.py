"""Check GL accounts, customers, and suppliers for mismatched opening/closing balance sides"""
import xml.etree.ElementTree as ET
import sys

filename = sys.argv[1] if len(sys.argv) > 1 else 'output/SAFT_BG_201996987_2023_12.xml'
tree = ET.parse(filename)
root = tree.getroot()
ns = {'ns': 'mf:nra:dgti:dxxxx:declaration:v1'}

def check_balances(elements, element_type, id_tag):
    """Check balance side consistency for GL accounts, customers, or suppliers"""
    mismatches = []
    for element in elements:
        elem_id_node = element.find(f'ns:{id_tag}', ns)
        if elem_id_node is None:
            continue
        elem_id = elem_id_node.text
        
        opening_debit = element.find('ns:OpeningDebitBalance', ns)
        opening_credit = element.find('ns:OpeningCreditBalance', ns)
        closing_debit = element.find('ns:ClosingDebitBalance', ns)
        closing_credit = element.find('ns:ClosingCreditBalance', ns)
        
        has_opening_debit = opening_debit is not None
        has_opening_credit = opening_credit is not None
        has_closing_debit = closing_debit is not None
        has_closing_credit = closing_credit is not None
        
        # Check if opening side != closing side
        if (has_opening_debit and has_closing_credit) or (has_opening_credit and has_closing_debit):
            mismatches.append({
                'id': elem_id,
                'opening': 'DR' if has_opening_debit else 'CR',
                'closing': 'DR' if has_closing_debit else 'CR',
                'opening_val': opening_debit.text if has_opening_debit else opening_credit.text,
                'closing_val': closing_debit.text if has_closing_debit else closing_credit.text
            })
    
    return mismatches

# Check GL Accounts
gl_accounts = root.findall('.//ns:GeneralLedgerAccounts/ns:Account', ns)
gl_mismatches = check_balances(gl_accounts, 'GL Account', 'AccountID')

# Check Customers
customers = root.findall('.//ns:Customers/ns:Customer', ns)
customer_mismatches = check_balances(customers, 'Customer', 'CustomerID')

# Check Suppliers
suppliers = root.findall('.//ns:Suppliers/ns:Supplier', ns)
supplier_mismatches = check_balances(suppliers, 'Supplier', 'SupplierID')

# Report results
print(f"Checking file: {filename}")
print("=" * 80)

if gl_mismatches:
    print(f'\n❌ GL Accounts: Found {len(gl_mismatches)} with mismatched sides:')
    for m in gl_mismatches:
        print(f"  {m['id']}: Opening {m['opening']} {m['opening_val']} -> Closing {m['closing']} {m['closing_val']}")
else:
    print(f'✓ GL Accounts: All {len(gl_accounts)} accounts OK')

if customer_mismatches:
    print(f'\n❌ Customers: Found {len(customer_mismatches)} with mismatched sides:')
    for m in customer_mismatches:
        print(f"  {m['id']}: Opening {m['opening']} {m['opening_val']} -> Closing {m['closing']} {m['closing_val']}")
else:
    print(f'✓ Customers: All {len(customers)} customers OK')

if supplier_mismatches:
    print(f'\n❌ Suppliers: Found {len(supplier_mismatches)} with mismatched sides:')
    for m in supplier_mismatches:
        print(f"  {m['id']}: Opening {m['opening']} {m['opening_val']} -> Closing {m['closing']} {m['closing_val']}")
else:
    print(f'✓ Suppliers: All {len(suppliers)} suppliers OK')

total_mismatches = len(gl_mismatches) + len(customer_mismatches) + len(supplier_mismatches)
print("\n" + "=" * 80)
if total_mismatches == 0:
    print("✓ ALL CHECKS PASSED - Same-side rule enforced throughout")
else:
    print(f"❌ TOTAL MISMATCHES: {total_mismatches}")
