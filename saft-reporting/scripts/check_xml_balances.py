import xml.etree.ElementTree as ET

tree = ET.parse('output/SAFT_BG_123456789_2024_01.xml')
root = tree.getroot()

ns = {'ns': 'http://www.saf-t.bg/SAF-T_BG'}

# Find first 10 GL accounts with non-zero balances
count = 0
for account in root.findall('.//ns:GeneralLedgerAccounts/ns:Account', ns):
    account_id = account.find('ns:AccountID', ns).text
    opening_debit = account.find('ns:OpeningDebitBalance', ns)
    opening_credit = account.find('ns:OpeningCreditBalance', ns)
    closing_debit = account.find('ns:ClosingDebitBalance', ns)
    closing_credit = account.find('ns:ClosingCreditBalance', ns)
    
    # Check if any balance is non-zero
    has_balance = False
    if opening_debit is not None and float(opening_debit.text) > 0:
        has_balance = True
    if opening_credit is not None and float(opening_credit.text) > 0:
        has_balance = True
    if closing_debit is not None and float(closing_debit.text) > 0:
        has_balance = True
    if closing_credit is not None and float(closing_credit.text) > 0:
        has_balance = True
    
    if has_balance:
        print(f'Account: {account_id}')
        if opening_debit is not None:
            print(f'  OpeningDebitBalance: {opening_debit.text}')
        if opening_credit is not None:
            print(f'  OpeningCreditBalance: {opening_credit.text}')
        if closing_debit is not None:
            print(f'  ClosingDebitBalance: {closing_debit.text}')
        if closing_credit is not None:
            print(f'  ClosingCreditBalance: {closing_credit.text}')
        print()
        count += 1
        if count >= 10:
            break
