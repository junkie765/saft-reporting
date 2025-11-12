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
            'source_documents': self._transform_source_documents(certinia_data)
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
    
    def _transform_master_files(self, data: Dict) -> Dict[str, List]:
        """Transform master data (accounts, customers, suppliers)"""
        # Get period start date and convert to period name format (YYYY/PPP)
        period_start_date = self.config['saft']['selection_start_date']
        start_dt = datetime.strptime(period_start_date, '%Y-%m-%d')
        period_start_name = f"{start_dt.year}/{start_dt.month:03d}"
        
        return {
            'general_ledger_accounts': self._transform_gl_accounts(
                data.get('gl_accounts', []), 
                data.get('transaction_lines', []),
                period_start_name
            ),
            'customers': self._transform_customers(
                data.get('accounts', []),
                data.get('transaction_lines', [])
            ),
            'suppliers': self._transform_suppliers(
                data.get('accounts', []),
                data.get('transaction_lines', [])
            )
        }
    
    def _transform_gl_accounts(self, gl_accounts: List[Dict], transaction_lines: List[Dict], period_start_name: str) -> List[Dict]:
        """Transform general ledger accounts with calculated balances from transaction line items"""
        logger.info(f"Calculating GL balances for {len(gl_accounts)} accounts, period: {period_start_name}")

        # Calculate the previous period end date (day before period start)
        period_start_date = self.config['saft']['selection_start_date']
        start_dt = datetime.strptime(period_start_date, '%Y-%m-%d')
        previous_period_end = (start_dt - timedelta(days=1)).strftime('%Y-%m-%d')

        def get_transaction_date(line: Dict) -> str:
            """Extract transaction date from nested structure"""
            if 'c2g__Transaction__r' in line and isinstance(line['c2g__Transaction__r'], dict):
                return line['c2g__Transaction__r'].get('c2g__TransactionDate__c', '')
            return line.get('c2g__Transaction__r.c2g__TransactionDate__c', '')

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
            
            transaction_date = get_transaction_date(line)
            
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
    
    def _calculate_account_balances(self, transaction_lines: List[Dict]) -> Dict[str, Dict]:
        """Calculate opening and closing balances for customer/supplier accounts"""
        period_start_date = self.config['saft']['selection_start_date']
        start_dt = datetime.strptime(period_start_date, '%Y-%m-%d')
        previous_period_end = (start_dt - timedelta(days=1)).strftime('%Y-%m-%d')
        
        def get_transaction_date(line: Dict) -> str:
            """Extract transaction date from nested structure"""
            if 'c2g__Transaction__r' in line and isinstance(line['c2g__Transaction__r'], dict):
                return line['c2g__Transaction__r'].get('c2g__TransactionDate__c', '')
            return line.get('c2g__Transaction__r.c2g__TransactionDate__c', '')
        
        # Build balances by account ID using NET VALUE approach
        opening_balances = {}  # Net balance through end of PREVIOUS period
        closing_balances = {}  # Net balance through end of CURRENT period
        
        for line in transaction_lines:
            account_id = line.get('c2g__Account__c')
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
            
            transaction_date = get_transaction_date(line)
            
            # Accumulate closing net balance (all transactions through end of CURRENT period)
            closing_balances.setdefault(account_id, 0.0)
            closing_balances[account_id] += net_value
            
            # Accumulate opening net balance (all transactions through end of PREVIOUS period)
            if transaction_date and transaction_date <= previous_period_end:
                opening_balances.setdefault(account_id, 0.0)
                opening_balances[account_id] += net_value
        
        # Convert net balances to debit/credit format for each account
        account_balances = {}
        all_account_ids = set(opening_balances.keys()) | set(closing_balances.keys())
        
        for account_id in all_account_ids:
            opening_net = opening_balances.get(account_id, 0.0)
            closing_net = closing_balances.get(account_id, 0.0)
            
            # Determine the side based on closing balance (same-side rule)
            # For customers: typically debit (receivables)
            # For suppliers: typically credit (payables)
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
        
        logger.info(f"Calculated balances for {len(account_balances)} accounts from transaction lines")
        return account_balances
    
    def _transform_customers(self, accounts: List[Dict], transaction_lines: List[Dict]) -> List[Dict]:
        """Transform customer accounts with calculated balances"""
        # Calculate balances for each account
        account_balances = self._calculate_account_balances(transaction_lines)
        
        transformed = []
        for acc in accounts:
            if acc.get('Type') == 'Subco' or acc.get('Type') == 'Partner':
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
        account_balances = self._calculate_account_balances(transaction_lines)
        
        transformed = []
        for acc in accounts:
            if acc.get('Type') != 'Subco' and acc.get('Type') != 'Partner':
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
        
        # Create lookup for lines by journal
        lines_by_journal = {}
        for line in lines:
            journal_id = line.get('c2g__Journal__c')
            if journal_id not in lines_by_journal:
                lines_by_journal[journal_id] = []
            lines_by_journal[journal_id].append(line)
        
        transformed = []
        transaction_id = 1
        
        for journal in journals:
            journal_id = journal.get('Id')
            journal_lines = lines_by_journal.get(journal_id, [])
            
            if not journal_lines:
                continue
            
            # Group lines into transaction
            transaction = {
                'transaction_id': f"T{transaction_id:08d}",
                'period': journal.get('c2g__Period__r.Name', ''),
                'transaction_date': journal.get('c2g__JournalDate__c', ''),
                'transaction_type': journal.get('c2g__Type__c', ''),
                'description': journal.get('c2g__Reference__c', ''),
                'system_entry_date': journal.get('c2g__JournalDate__c', ''),
                'gl_posting_date': journal.get('c2g__JournalDate__c', ''),
                'lines': []
            }
            
            line_number = 1
            for line in journal_lines:
                value = self._parse_decimal(line.get('c2g__Value__c', 0))
                line_type = line.get('c2g__LineType__c', '')
                
                transaction['lines'].append({
                    'record_id': f"T{transaction_id:08d}-L{line_number:04d}",
                    'account_id': line.get('c2g__GeneralLedgerAccount__r.c2g__ReportingCode__c', ''),
                    'analysis_type': line_type,
                    'debit_amount': value if line_type == 'Debit' else 0,
                    'credit_amount': value if line_type == 'Credit' else 0,
                    'amount': value,
                    'description': line.get('c2g__LineDescription__c', ''),
                })
                line_number += 1
            
            transformed.append(transaction)
            transaction_id += 1
        
        logger.info(f"Transformed {len(transformed)} GL transactions with {sum(len(t['lines']) for t in transformed)} lines")
        return transformed
    
    def _transform_source_documents(self, data: Dict) -> Dict[str, List]:
        """Transform source documents (invoices, payments, etc.)"""
        # This would include sales invoices, purchase invoices, payments
        # For now, returning empty structure
        return {
            'sales_invoices': [],
            'purchase_invoices': [],
            'payments': []
        }
    
    def _parse_decimal(self, value: Any) -> float:
        """Parse decimal value safely"""
        try:
            return float(value) if value else 0.0
        except (ValueError, TypeError):
            return 0.0
