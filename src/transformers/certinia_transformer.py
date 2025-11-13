"""Transform Certinia Finance Cloud data to SAF-T format"""
import logging
from typing import Dict, List, Any
from datetime import datetime, timedelta


logger = logging.getLogger(__name__)


class CertiniaTransformer:
    """Transform Certinia data to SAF-T structure"""
    
    def __init__(self, config: dict):
        """
        Initialize transformer
        
        Args:
            config: Configuration dictionary
        """
        self.config = config
    
    def transform(self, certinia_data: Dict[str, List]) -> Dict[str, Any]:
        """
        Transform Certinia data to SAF-T structure
        
        Args:
            certinia_data: Raw data from Certinia
            
        Returns:
            Dictionary structured for SAF-T generation
        """
        logger.info("Starting SAF-T data transformation...")
        
        saft_data = {
            'header': self._transform_header(certinia_data),
            'master_files': self._transform_master_files(certinia_data),
            'general_ledger_entries': self._transform_gl_entries(certinia_data),
            'source_documents': self._transform_source_documents(certinia_data),
            'tax_codes': self._transform_tax_codes(certinia_data)
        }
        
        logger.info("SAF-T transformation complete")
        return saft_data
    
    def _transform_header(self, data: Dict) -> Dict[str, Any]:
        """Transform header information"""
        company_info = data.get('company', [{}])[0]
        saft_config = self.config['saft']
        
        # Get company name in Cyrillic if available, otherwise use Latin name
        company_name = company_info.get('FF_Name_cyrillic__c') or company_info.get('Name', saft_config.get('company_name', ''))
        
        # Get address fields with fallbacks
        street = company_info.get('F_Address_Cyrillic__c') or company_info.get('c2g__Street__c', '')
        city = company_info.get('F_City_Cyrillic__c') or company_info.get('c2g__City__c', '')
        postal_code = company_info.get('c2g__ZipPostCode__c', '')
        country = company_info.get('c2g__Country__c', 'BG')
        
        # Get contact information
        telephone = company_info.get('c2g__Phone__c', '')
        fax = company_info.get('c2g__Fax__c', '')
        email = company_info.get('c2g__ContactEmail__c', '')
        website = company_info.get('c2g__Website__c', '')
        
        # Get registration numbers - prioritize SFocus_Company_Identification_Number__c
        registration_number = (company_info.get('SFocus_Company_Identification_Number__c') or 
                              company_info.get('c2g__TaxIdentificationNumber__c') or 
                              saft_config.get('company_id', ''))
        
        tax_registration_number = (company_info.get('c2g__VATRegistrationNumber__c') or 
                                  company_info.get('c2g__TaxIdentificationNumber__c') or 
                                  saft_config.get('tax_registration_number', ''))
        
        # Get IBAN from related Bank Account
        iban = company_info.get('c2g__BankAccount__r.c2g__IBANNumber__c', saft_config.get('iban', ''))
        
        return {
            'audit_file_version': '1.0',
            'audit_file_country': 'BG',
            'audit_file_date_created': datetime.now().isoformat(),
            'software_company_name': saft_config['software_company_name'],
            'software_product_name': saft_config['software_product_name'],
            'software_product_version': saft_config['software_product_version'],
            'company': {
                'registration_number': registration_number,
                'name': company_name,
                'tax_registration_number': tax_registration_number,
                'street': street,
                'city': city,
                'postal_code': postal_code,
                'country': country,
                'telephone': telephone,
                'fax': fax,
                'email': email,
                'website': website,
                'state_province': company_info.get('c2g__StateProvince__c', ''),
                'iban': iban,
            },
            'fiscal_year': saft_config['fiscal_year'],
            'start_date': saft_config['selection_start_date'],
            'end_date': saft_config['selection_end_date'],
            'header_comment': saft_config['header_comment']
        }
    
    def _get_period_info(self) -> Dict[str, Any]:
        """Get period information from config"""
        period_start_date = self.config['saft']['selection_start_date']
        start_dt = datetime.strptime(period_start_date, '%Y-%m-%d')
        previous_period_end = (start_dt - timedelta(days=1)).strftime('%Y-%m-%d')
        
        return {
            'period': start_dt.month,
            'period_year': start_dt.year,
            'period_start_name': f"{start_dt.year}/{start_dt.month:03d}",
            'period_start_date': period_start_date,
            'previous_period_end': previous_period_end
        }
    
    def _get_transaction_date(self, line: Dict) -> str:
        """Extract transaction date from nested structure"""
        if 'c2g__Transaction__r' in line and isinstance(line['c2g__Transaction__r'], dict):
            return line['c2g__Transaction__r'].get('c2g__TransactionDate__c', '')
        return line.get('c2g__Transaction__r.c2g__TransactionDate__c', '')
    
    def _transform_master_files(self, data: Dict) -> Dict[str, List]:
        """Transform master data (accounts, customers, suppliers)"""
        period_info = self._get_period_info()
        
        return {
            'general_ledger_accounts': self._transform_gl_accounts(
                data.get('gl_accounts', []), 
                data.get('transaction_lines', []),
                period_info['period_start_name']
            ),
            'customers': self._transform_customers(
                data.get('accounts', []),
                data.get('transaction_lines', [])
            ),
            'suppliers': self._transform_suppliers(
                data.get('accounts', []),
                data.get('transaction_lines', [])
            ),
            'products': self._transform_products(data.get('products', []))
        }
    
    def _transform_gl_accounts(self, gl_accounts: List[Dict], transaction_lines: List[Dict], period_start_name: str) -> List[Dict]:
        """Transform general ledger accounts with calculated balances from transaction line items"""
        logger.info(f"Calculating GL balances for {len(gl_accounts)} accounts, period: {period_start_name}")

        period_info = self._get_period_info()
        previous_period_end = period_info['previous_period_end']

        # Build balances by account using NET VALUE approach (matching SAQL logic)
        # Net value = Debit - Credit (positive = debit balance, negative = credit balance)
        opening_balances = {}  # Net balance through end of PREVIOUS period
        closing_balances = {}  # Net balance through end of CURRENT period
        
        for line in transaction_lines:
            gl_account_id = line.get('c2g__GeneralLedgerAccount__c')
            if not gl_account_id:
                continue
            
            # Use c2g__HomeValue__c if available (signed net value), otherwise calculate
            home_value = line.get('c2g__HomeValue__c')
            if home_value is not None:
                net_value = self._parse_decimal(home_value)
            else:
                debit = self._parse_decimal(line.get('c2g__HomeDebits__c', 0))
                credit = self._parse_decimal(line.get('c2g__HomeCredits__c', 0))
                net_value = debit - credit
            
            transaction_date = self._get_transaction_date(line)
            
            # Accumulate closing net balance (all transactions through end of CURRENT period)
            closing_balances.setdefault(gl_account_id, 0.0)
            closing_balances[gl_account_id] += net_value
            
            # Accumulate opening net balance (all transactions through end of PREVIOUS period)
            if transaction_date and transaction_date <= previous_period_end:
                opening_balances.setdefault(gl_account_id, 0.0)
                opening_balances[gl_account_id] += net_value

        def compute_balances(account):
            """Convert net balances to debit/credit format with same-side rule enforcement"""
            account_id = account.get('Id')
            
            # Get net balances (positive = debit, negative = credit)
            opening_net = opening_balances.get(account_id, 0.0)
            closing_net = closing_balances.get(account_id, 0.0)
            
            # Determine the side based on closing balance (same-side rule)
            # If closing is debit, opening must be debit; if closing is credit, opening must be credit
            if closing_net > 0:
                # Closing is debit, so opening must also be debit
                closing_debit = closing_net
                closing_credit = 0.0
                opening_debit = abs(opening_net)  # Force to debit side
                opening_credit = 0.0
            elif closing_net < 0:
                # Closing is credit, so opening must also be credit
                closing_debit = 0.0
                closing_credit = abs(closing_net)
                opening_debit = 0.0
                opening_credit = abs(opening_net)  # Force to credit side
            else:
                # Closing is zero - determine side from opening, or default to debit if both zero
                if opening_net > 0:
                    opening_debit = opening_net
                    opening_credit = 0.0
                    closing_debit = 0.0
                    closing_credit = 0.0
                elif opening_net < 0:
                    opening_debit = 0.0
                    opening_credit = abs(opening_net)
                    closing_debit = 0.0
                    closing_credit = 0.0
                else:
                    # Both zero - default to debit side
                    opening_debit = 0.0
                    opening_credit = 0.0
                    closing_debit = 0.0
                    closing_credit = 0.0
            
            return {
                'opening_debit_balance': opening_debit,
                'opening_credit_balance': opening_credit,
                'closing_debit_balance': closing_debit,
                'closing_credit_balance': closing_credit
            }

        transformed = [
            {
                'account_id': account.get('c2g__ReportingCode__c', account.get('Name')),
                'account_description': account.get('Name', ''),
                'account_type': account.get('c2g__Type__c', ''),
                **compute_balances(account)
            }
            for account in gl_accounts
        ]
        transformed.sort(key=lambda x: x['account_id'])
        logger.info(f"Transformed {len(transformed)} GL accounts with calculated balances")
        return transformed
    
    def _calculate_balances(self, transaction_lines: List[Dict], group_by_field: str) -> Dict[str, Dict]:
        """Calculate opening and closing balances for accounts grouped by specified field"""
        period_info = self._get_period_info()
        previous_period_end = period_info['previous_period_end']
        
        # Build balances by account ID using NET VALUE approach
        opening_balances = {}  # Net balance through end of PREVIOUS period
        closing_balances = {}  # Net balance through end of CURRENT period
        
        for line in transaction_lines:
            account_id = line.get(group_by_field)
            if not account_id:
                continue
            
            # Use c2g__HomeValue__c if available (signed net value), otherwise calculate
            home_value = line.get('c2g__HomeValue__c')
            if home_value is not None:
                net_value = self._parse_decimal(home_value)
            else:
                debit = self._parse_decimal(line.get('c2g__HomeDebits__c', 0))
                credit = self._parse_decimal(line.get('c2g__HomeCredits__c', 0))
                net_value = debit - credit
            
            transaction_date = self._get_transaction_date(line)
            
            # Accumulate closing net balance (all transactions through end of CURRENT period)
            closing_balances.setdefault(account_id, 0.0)
            closing_balances[account_id] += net_value
            
            # Accumulate opening net balance (all transactions through end of PREVIOUS period)
            if transaction_date and transaction_date <= previous_period_end:
                opening_balances.setdefault(account_id, 0.0)
                opening_balances[account_id] += net_value
        
        # Convert net balances to debit/credit format
        return self._convert_net_to_debit_credit(opening_balances, closing_balances)
    
    def _convert_net_to_debit_credit(self, opening_balances: Dict[str, float], closing_balances: Dict[str, float]) -> Dict[str, Dict]:
        """Convert net balances to debit/credit format following same-side rule"""
        account_balances = {}
        all_account_ids = set(opening_balances.keys()) | set(closing_balances.keys())
        
        for account_id in all_account_ids:
            opening_net = opening_balances.get(account_id, 0.0)
            closing_net = closing_balances.get(account_id, 0.0)
            
            # Determine the side based on closing balance (same-side rule)
            if closing_net > 0:
                # Closing is debit, so opening must also be debit
                closing_debit = closing_net
                closing_credit = 0.0
                opening_debit = abs(opening_net)
                opening_credit = 0.0
            elif closing_net < 0:
                # Closing is credit, so opening must also be credit
                closing_debit = 0.0
                closing_credit = abs(closing_net)
                opening_debit = 0.0
                opening_credit = abs(opening_net)
            else:
                # Closing is zero
                if opening_net > 0:
                    opening_debit = opening_net
                    opening_credit = 0.0
                    closing_debit = 0.0
                    closing_credit = 0.0
                elif opening_net < 0:
                    opening_debit = 0.0
                    opening_credit = abs(opening_net)
                    closing_debit = 0.0
                    closing_credit = 0.0
                else:
                    opening_debit = 0.0
                    opening_credit = 0.0
                    closing_debit = 0.0
                    closing_credit = 0.0
            
            account_balances[account_id] = {
                'opening_debit_balance': opening_debit,
                'opening_credit_balance': opening_credit,
                'closing_debit_balance': closing_debit,
                'closing_credit_balance': closing_credit
            }
        
        logger.info(f"Converted {len(account_balances)} account balances")
        return account_balances
    
    def _transform_customers(self, accounts: List[Dict], transaction_lines: List[Dict]) -> List[Dict]:
        """Transform customer accounts with calculated balances"""
        # Calculate balances for each account
        account_balances = self._calculate_balances(transaction_lines, 'c2g__Account__c')
        
        transformed = []
        for acc in accounts:
            # Get RecordType from nested structure
            record_type = ''
            if 'RecordType' in acc and isinstance(acc['RecordType'], dict):
                record_type = acc['RecordType'].get('Name', '')
            else:
                record_type = acc.get('RecordType.Name', '')
            
            # Only process Standard (customer) accounts
            if record_type != 'Standard':
                continue
                
            account_id = acc.get('Id')
            balances = account_balances.get(account_id, {
                'opening_debit_balance': 0.0,
                'opening_credit_balance': 0.0,
                'closing_debit_balance': 0.0,
                'closing_credit_balance': 0.0
            })
            
            transformed.append({
                'customer_id': acc.get('AccountNumber', acc.get('Id')),
                'account_id': acc.get('AccountNumber', ''),
                'customer_tax_id': acc.get('c2g__CODATaxpayerIdentificationNumber__c', ''),
                'company_name': acc.get('Name', ''),
                'contact': {
                    'telephone': acc.get('Phone', ''),
                    'fax': acc.get('Fax', ''),
                    'email': acc.get('c2g__CODAInvoiceEmail__c', ''),
                    'website': acc.get('Website', '')
                },
                'billing_address': {
                    'street_name': acc.get('BillingStreet', ''),
                    'city': acc.get('BillingCity', ''),
                    'postal_code': acc.get('BillingPostalCode', ''),
                    'country': acc.get('BillingCountry', 'BG')
                },
                **balances
            })
        
        logger.info(f"Transformed {len(transformed)} customers")
        return transformed
    
    def _transform_suppliers(self, accounts: List[Dict], transaction_lines: List[Dict]) -> List[Dict]:
        """Transform supplier accounts with calculated balances"""
        # Calculate balances for each account
        account_balances = self._calculate_balances(transaction_lines, 'c2g__Account__c')
        
        transformed = []
        for acc in accounts:
            # Get RecordType from nested structure
            record_type = ''
            if 'RecordType' in acc and isinstance(acc['RecordType'], dict):
                record_type = acc['RecordType'].get('Name', '')
            else:
                record_type = acc.get('RecordType.Name', '')
            
            # Only process Supplier Data Management accounts
            if record_type != 'Supplier Data Management':
                continue
                
            account_id = acc.get('Id')
            balances = account_balances.get(account_id, {
                'opening_debit_balance': 0.0,
                'opening_credit_balance': 0.0,
                'closing_debit_balance': 0.0,
                'closing_credit_balance': 0.0
            })
            
            transformed.append({
                'supplier_id': acc.get('AccountNumber', acc.get('Id')),
                'account_id': acc.get('AccountNumber', ''),
                'supplier_tax_id': acc.get('c2g__CODATaxpayerIdentificationNumber__c', ''),
                'company_name': acc.get('Name', ''),
                'contact': {
                    'telephone': acc.get('Phone', ''),
                    'fax': acc.get('Fax', ''),
                    'email': acc.get('c2g__CODAInvoiceEmail__c', ''),
                    'website': acc.get('Website', '')
                },
                'billing_address': {
                    'street_name': acc.get('BillingStreet', ''),
                    'city': acc.get('BillingCity', ''),
                    'postal_code': acc.get('BillingPostalCode', ''),
                    'country': acc.get('BillingCountry', 'BG')
                },
                **balances
            })
        
        logger.info(f"Transformed {len(transformed)} suppliers")
        return transformed
    
    def _transform_gl_entries(self, data: Dict) -> List[Dict]:
        """Transform journal entries to general ledger entries"""
        journals = data.get('journals', [])
        lines = data.get('journal_lines', [])
        
        period_info = self._get_period_info()
        period = period_info['period']
        period_year = period_info['period_year']
        
        # Sort journals by transaction date ascending
        journals_sorted = sorted(journals, key=lambda j: j.get('c2g__JournalDate__c', ''))
        
        # Create lookup for lines by journal
        lines_by_journal = {}
        for line in lines:
            journal_id = line.get('c2g__Journal__c')
            if journal_id not in lines_by_journal:
                lines_by_journal[journal_id] = []
            lines_by_journal[journal_id].append(line)
        
        transformed = []
        transaction_id = 1
        
        for journal in journals_sorted:
            journal_id = journal.get('Id')
            journal_lines = lines_by_journal.get(journal_id, [])
            
            if not journal_lines:
                continue
            
            journal_date = journal.get('c2g__JournalDate__c', '')
            
            # Group lines into transaction
            transaction = {
                'transaction_id': str(transaction_id),
                'period': period,
                'period_year': period_year,
                'transaction_date': journal_date,
                'transaction_type': 'Normal',
                'description': journal.get('c2g__Reference__c', 'Journal Entry'),
                'system_entry_date': journal_date,
                'gl_posting_date': journal_date,
                'source_id': journal_id or '0',
                'batch_id': '0',
                'customer_id': '0',
                'supplier_id': '0',
                'system_id': journal_id or '0',
                'lines': []
            }
            
            line_number = 1
            for line in journal_lines:
                debit_amount = self._parse_decimal(line.get('c2g__Debits__c', 0))
                credit_amount = self._parse_decimal(line.get('c2g__Credits__c', 0))
                account_id = line.get('c2g__GeneralLedgerAccount__r.c2g__ReportingCode__c', '')
                
                transaction['lines'].append({
                    'record_id': str(line_number),
                    'account_id': account_id,
                    'taxpayer_account_id': account_id,
                    'debit_amount': debit_amount,
                    'credit_amount': credit_amount,
                    'description': line.get('c2g__LineDescription__c', ''),
                    'value_date': journal_date,
                    'source_document_id': journal_id or '0',
                    'customer_id': '0',
                    'supplier_id': '0',
                    'currency_code': 'BGN',
                    'exchange_rate': '1.0000',
                    'tax_type': '',
                    'tax_code': '',
                    'tax_percentage': 0,
                    'tax_base': 0,
                    'tax_base_description': '',
                    'tax_amount': 0,
                    'tax_exemption_reason': '',
                    'tax_declaration_period': ''
                })
                line_number += 1
            
            transformed.append(transaction)
            transaction_id += 1
        
        logger.info(f"Transformed {len(transformed)} GL transactions with {sum(len(t['lines']) for t in transformed)} lines")
        return transformed
    
    def _transform_source_documents(self, data: Dict) -> Dict[str, List]:
        """Transform source documents (invoices, payments, etc.)"""
        sales_invoices = self._transform_sales_invoices(data)
        purchase_invoices = self._transform_purchase_invoices(data)
        payments = self._transform_payments(data)
        
        return {
            'sales_invoices': sales_invoices,
            'purchase_invoices': purchase_invoices,
            'payments': payments
        }
    
    def _transform_sales_invoices(self, data: Dict) -> List[Dict]:
        """Transform sales invoices to SAF-T format"""
        invoices = data.get('sales_invoices', [])
        invoice_lines = data.get('sales_invoice_lines', [])
        
        period_info = self._get_period_info()
        period = period_info['period']
        period_year = period_info['period_year']
        
        # Create lookup for lines by invoice
        lines_by_invoice = {}
        for line in invoice_lines:
            invoice_id = line.get('fferpcore__BillingDocument__c')
            if invoice_id not in lines_by_invoice:
                lines_by_invoice[invoice_id] = []
            lines_by_invoice[invoice_id].append(line)
        
        transformed = []
        
        for invoice in invoices:
            invoice_id = invoice.get('Id')
            inv_lines = lines_by_invoice.get(invoice_id, [])
            
            if not inv_lines:
                continue
            
            invoice_date = invoice.get('fferpcore__DocumentDate__c', '')
            account_info = invoice.get('fferpcore__Account__r') or {}
            
            # Transform invoice lines
            transformed_lines = []
            line_number = 1
            total_debit = 0
            total_credit = 0
            
            for line in inv_lines:
                net_value = self._parse_decimal(line.get('fferpcore__NetValue__c', 0))
                tax_value = self._parse_decimal(line.get('fferpcore__TaxValue1__c', 0))
                quantity = self._parse_decimal(line.get('fferpcore__Quantity__c', 0))
                unit_price = self._parse_decimal(line.get('fferpcore__UnitPrice__c', 0))
                
                product_info = line.get('fferpcore__ProductService__r') or {}
                gl_account = line.get('c2g__GeneralLedgerAccount__r') or {}
                
                transformed_lines.append({
                    'line_number': str(line_number),
                    'account_id': gl_account.get('c2g__ReportingCode__c', ''),
                    'product_code': product_info.get('ProductCode', ''),
                    'product_description': product_info.get('Name', ''),
                    'quantity': quantity,
                    'unit_price': unit_price,
                    'line_amount': net_value,
                    'tax_amount': tax_value,
                    'description': line.get('fferpcore__LineDescription__c', ''),
                    'debit_credit_indicator': 'C',  # Sales invoices credit revenue
                })
                
                total_credit += net_value
                line_number += 1
            
            transformed.append({
                'invoice_no': invoice.get('Name', ''),
                'invoice_date': invoice_date,
                'period': period,
                'period_year': period_year,
                'customer_id': account_info.get('c2g__CODATaxpayerIdentificationNumber__c', ''),
                'customer_name': account_info.get('Name', ''),
                'gl_posting_date': invoice_date,
                'system_id': invoice_id,
                'lines': transformed_lines,
                'total_debit': total_debit,
                'total_credit': total_credit
            })
        
        logger.info(f"Transformed {len(transformed)} sales invoices")
        return transformed
    
    def _transform_payments(self, data: Dict) -> List[Dict]:
        """Transform cash entries (payments) to SAF-T format"""
        payments = data.get('payments', [])
        payment_lines = data.get('payment_lines', [])
        
        period_info = self._get_period_info()
        period = period_info['period']
        period_year = period_info['period_year']
        
        # Create lookup for lines by payment
        lines_by_payment = {}
        for line in payment_lines:
            payment_id = line.get('c2g__CashEntry__c')
            if payment_id not in lines_by_payment:
                lines_by_payment[payment_id] = []
            lines_by_payment[payment_id].append(line)
        
        transformed = []
        
        for payment in payments:
            payment_id = payment.get('Id')
            pay_lines = lines_by_payment.get(payment_id, [])
            
            if not pay_lines:
                continue
            
            payment_date = payment.get('c2g__Date__c', '')
            account_info = payment.get('c2g__Account__r') or {}
            
            # Transform payment lines
            transformed_lines = []
            line_number = 1
            total_debit = 0
            total_credit = 0
            
            for line in pay_lines:
                cash_value = self._parse_decimal(line.get('c2g__CashEntryValue__c', 0))
                net_value = self._parse_decimal(line.get('c2g__NetValue__c', 0))
                line_account_info = line.get('c2g__Account__r') or {}
                
                # Determine debit/credit based on payment type and value sign
                payment_type = payment.get('c2g__Type__c', '')
                if payment_type == 'Receipt' or cash_value > 0:
                    debit_amount = abs(cash_value)
                    credit_amount = 0
                else:
                    debit_amount = 0
                    credit_amount = abs(cash_value)
                
                transformed_lines.append({
                    'line_number': str(line_number),
                    'account_id': line_account_info.get('Name', ''),
                    'customer_id': line_account_info.get('c2g__CODATaxpayerIdentificationNumber__c', ''),
                    'description': line.get('c2g__LineDescription__c', ''),
                    'debit_amount': debit_amount,
                    'credit_amount': credit_amount,
                    'debit_credit_indicator': 'D' if debit_amount > 0 else 'C'
                })
                
                total_debit += debit_amount
                total_credit += credit_amount
                line_number += 1
            
            transformed.append({
                'payment_ref_no': payment.get('Name', ''),
                'payment_date': payment_date,
                'period': period,
                'period_year': period_year,
                'account_id': account_info.get('c2g__CODATaxpayerIdentificationNumber__c', ''),
                'account_name': account_info.get('Name', ''),
                'reference': payment.get('c2g__Reference__c', ''),
                'system_id': payment_id,
                'lines': transformed_lines,
                'total_debit': total_debit,
                'total_credit': total_credit
            })
        
        logger.info(f"Transformed {len(transformed)} payments")
        return transformed
    
    def _transform_purchase_invoices(self, data: Dict) -> List[Dict]:
        """Transform purchase invoices (payable invoices) to SAF-T format"""
        invoices = data.get('purchase_invoices', [])
        invoice_lines = data.get('purchase_invoice_lines', [])
        
        period_info = self._get_period_info()
        period = period_info['period']
        period_year = period_info['period_year']
        
        # Create lookup for lines by invoice
        lines_by_invoice = {}
        for line in invoice_lines:
            invoice_id = line.get('c2g__PurchaseInvoice__c')
            if invoice_id not in lines_by_invoice:
                lines_by_invoice[invoice_id] = []
            lines_by_invoice[invoice_id].append(line)
        
        transformed = []
        
        for invoice in invoices:
            invoice_id = invoice.get('Id')
            inv_lines = lines_by_invoice.get(invoice_id, [])
            
            if not inv_lines:
                continue
            
            invoice_date = invoice.get('c2g__InvoiceDate__c', '')
            account_info = invoice.get('c2g__Account__r') or {}
            
            # Transform invoice lines
            transformed_lines = []
            line_number = 1
            total_debit = 0
            total_credit = 0
            
            for line in inv_lines:
                net_value = self._parse_decimal(line.get('c2g__NetValue__c', 0))
                tax_value = self._parse_decimal(line.get('c2g__TaxValue1__c', 0))
                quantity = self._parse_decimal(line.get('F_Quantity__c', 0))
                unit_price = net_value / quantity if quantity else 0
                
                product_info = line.get('F_Product__r') or {}
                gl_account = line.get('c2g__GeneralLedgerAccount__r') or {}
                
                transformed_lines.append({
                    'line_number': str(line_number),
                    'account_id': gl_account.get('c2g__ReportingCode__c', ''),
                    'product_code': product_info.get('ProductCode', ''),
                    'product_description': product_info.get('Name', ''),
                    'quantity': quantity,
                    'unit_price': unit_price,
                    'line_amount': net_value,
                    'tax_amount': tax_value,
                    'description': line.get('c2g__LineDescription__c', ''),
                    'debit_credit_indicator': 'D',  # Purchase invoices debit expense
                })
                
                total_debit += net_value
                line_number += 1
            
            transformed.append({
                'invoice_no': invoice.get('Name', ''),
                'invoice_date': invoice_date,
                'period': period,
                'period_year': period_year,
                'supplier_id': account_info.get('c2g__CODATaxpayerIdentificationNumber__c', ''),
                'supplier_name': account_info.get('Name', ''),
                'gl_posting_date': invoice_date,
                'system_id': invoice_id,
                'lines': transformed_lines,
                'total_debit': total_debit,
                'total_credit': total_credit
            })
        
        logger.info(f"Transformed {len(transformed)} purchase invoices")
        return transformed
    
    def _transform_tax_codes(self, data: Dict) -> List[Dict]:
        """Transform Salesforce tax codes to SAF-T tax table entries"""
        tax_codes = data.get('tax_codes', [])
        
        transformed = []
        for tax_code in tax_codes:
            # Get the most recent tax rate from the nested relationship
            tax_rates_obj = tax_code.get('c2g__TaxRates__r')
            tax_rate = 0.0
            
            if tax_rates_obj and isinstance(tax_rates_obj, dict):
                tax_rates = tax_rates_obj.get('records', [])
                if tax_rates:
                    # Get the rate from the first (most recent) record (0.20 -> 20.00)
                    tax_rate = self._parse_decimal(tax_rates[0].get('c2g__Rate__c', 0))
            
            transformed.append({
                'tax_type': 'ДДС',  # VAT in Bulgarian
                'tax_code': tax_code.get('Name', 'STD'),
                'description': tax_code.get('c2g__Description__c', ''),
                'tax_percentage': tax_rate
            })
        
        logger.info(f"Transformed {len(transformed)} tax codes")
        return transformed
    
    def _transform_products(self, products: List[Dict]) -> List[Dict]:
        """Transform Salesforce Product2 records to SAF-T products"""
        transformed = []
        
        for product in products:
            transformed.append({
                'product_code': product.get('ProductCode', ''),
                'goods_services_id': '01',  # 01 = Goods, 02 = Services
                'product_group': product.get('Family', ''),
                'description': product.get('Name', ''),
                'product_commodity_code': '0',  # Always 0 as specified
                'product_number_code': product.get('ProductCode', ''),
                'uom_base': 'HUR',
                'uom_standard': 'ЧАС',
                'uom_conversion_factor': '1',
                'tax_type': '100',
                'tax_code': '100211'
            })
        
        logger.info(f"Transformed {len(transformed)} products")
        return transformed
    
    def _parse_decimal(self, value: Any) -> float:
        """Parse decimal value safely"""
        try:
            return float(value) if value else 0.0
        except (ValueError, TypeError):
            return 0.0
