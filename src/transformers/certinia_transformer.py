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
        self._period_info_cache = None  # Cache period info to avoid recalculation
    
    def transform(self, certinia_data: Dict[str, List]) -> Dict[str, Any]:
        """
        Transform Certinia data to SAF-T structure
        
        Args:
            certinia_data: Raw data from Certinia
            
        Returns:
            Dictionary structured for SAF-T generation with header, master files,
            general ledger entries, source documents, and tax codes
        """
        logger.info("Starting SAF-T data transformation...")
        
        logger.info("Transforming header information...")
        header = self._transform_header(certinia_data)
        
        logger.info("Transforming master files (accounts, customers, suppliers)...")
        master_files = self._transform_master_files(certinia_data)
        
        logger.info("Transforming general ledger entries...")
        gl_entries = self._transform_gl_entries(certinia_data)
        
        logger.info("Transforming source documents...")
        source_docs = self._transform_source_documents(certinia_data)
        
        logger.info("Transforming tax codes...")
        tax_codes = self._transform_tax_codes(certinia_data)
        
        saft_data = {
            'header': header,
            'master_files': master_files,
            'general_ledger_entries': gl_entries,
            'source_documents': source_docs,
            'tax_codes': tax_codes
        }
        
        logger.info("Data transformation complete")
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
        """Get period information from config (with caching)
        
        For balance calculations:
        - start_period: Used for opening balance calculation (transactions < start_period)
        - end_period: Used for closing balance calculation (transactions <= end_period)
        """
        if self._period_info_cache is not None:
            return self._period_info_cache
        
        period_start_date = self.config['saft']['selection_start_date']
        period_end_date = self.config['saft']['selection_end_date']
        
        start_dt = datetime.strptime(period_start_date, '%Y-%m-%d')
        end_dt = datetime.strptime(period_end_date, '%Y-%m-%d')
        previous_period_end = (start_dt - timedelta(days=1)).strftime('%Y-%m-%d')
        
        self._period_info_cache = {
            'period': end_dt.month,  # End period for closing balance
            'period_year': end_dt.year,  # End period year for closing balance
            'start_period': start_dt.month,  # Start period for opening balance
            'start_period_year': start_dt.year,  # Start period year for opening balance
            'period_start_name': f"{start_dt.year}/{start_dt.month:03d}",
            'period_start_date': period_start_date,
            'period_end_date': period_end_date,
            'previous_period_end': previous_period_end
        }
        return self._period_info_cache
    
    def _get_transaction_date(self, line: Dict) -> str:
        """Extract transaction date from nested structure"""
        if 'c2g__Transaction__r' in line and isinstance(line['c2g__Transaction__r'], dict):
            return line['c2g__Transaction__r'].get('c2g__TransactionDate__c', '')
        return line.get('c2g__Transaction__r.c2g__TransactionDate__c', '')
    
    def _get_period_number(self, line: Dict) -> str:
        """Extract period number for comparison from period Name
        
        Period Name format is 'YYYY/NNN' (e.g., '2024/001', '2024/000')
        Returns concatenated string '2024001' or '2024000' for numeric comparison
        """
        if 'c2g__Transaction__r' in line and isinstance(line['c2g__Transaction__r'], dict):
            transaction = line['c2g__Transaction__r']
            if 'c2g__Period__r' in transaction and isinstance(transaction['c2g__Period__r'], dict):
                period = transaction['c2g__Period__r']
                period_name = period.get('Name', '')  # Format: '2024/001'
                if period_name and '/' in period_name:
                    year, period_num = period_name.split('/')
                    return f"{year}{period_num}"  # '2024001'
        return ''
    
    def _get_net_value(self, line: Dict) -> float:
        """Extract net value from transaction line
        
        Prioritizes c2g__HomeValue__c if available, otherwise calculates from debits/credits.
        Returns positive for debits, negative for credits.
        """
        home_value = line.get('c2g__HomeValue__c')
        if home_value is not None and home_value != '':
            return self._parse_decimal(home_value)
        # Fallback: calculate from debits and credits
        debit = self._parse_decimal(line.get('c2g__HomeDebits__c', 0))
        credit = self._parse_decimal(line.get('c2g__HomeCredits__c', 0))
        return debit - credit
    
    def _get_record_type(self, record: Dict) -> str:
        """Extract RecordType.Name from nested structure"""
        if 'RecordType' in record and isinstance(record['RecordType'], dict):
            return record['RecordType'].get('Name', '')
        return record.get('RecordType.Name', '')
    
    def _transform_master_files(self, data: Dict) -> Dict[str, List]:
        """Transform master data (accounts, customers, suppliers)"""
        period_info = self._get_period_info()
        
        # Calculate all balances in a single pass through transaction lines
        # This is ~3x faster than calculating separately for each account type
        transaction_lines = data.get('transaction_lines', [])
        logger.info(f"Calculating balances for all account types in single pass ({len(transaction_lines)} transaction lines)...")
        gl_balances, account_balances = self._calculate_all_balances(transaction_lines)
        
        return {
            'general_ledger_accounts': self._transform_gl_accounts(
                data.get('gl_accounts', []), 
                gl_balances,
                period_info['period_start_name']
            ),
            'customers': self._transform_customers(
                data.get('accounts', []),
                account_balances
            ),
            'suppliers': self._transform_suppliers(
                data.get('accounts', []),
                account_balances
            ),
            'products': self._transform_products(data.get('products', []))
        }
    
    def _transform_gl_accounts(self, gl_accounts: List[Dict], account_balances: Dict[str, Dict], period_start_name: str) -> List[Dict]:
        """Transform general ledger accounts with calculated balances from transaction line items"""
        logger.info(f"Transforming {len(gl_accounts)} GL accounts for period {period_start_name}")

        transformed = [
            {
                'account_id': account.get('c2g__ReportingCode__c', account.get('Name')),
                'account_description': account.get('Name', ''),
                'account_type': account.get('c2g__Type__c', ''),
                **account_balances.get(str(account.get('Id', '')), {
                    'opening_debit_balance': 0.0,
                    'closing_debit_balance': 0.0,
                    'opening_credit_balance': 0.0,
                    'closing_credit_balance': 0.0
                })
            }
            for account in gl_accounts
        ]
        transformed.sort(key=lambda x: x['account_id'])
        return transformed
    
    def _calculate_all_balances(self, transaction_lines: List[Dict]) -> tuple[Dict[str, Dict], Dict[str, Dict]]:
        """Calculate balances for GL accounts and c2g__Account__c in a single pass
        
        This consolidates balance calculations to process transaction lines only once,
        significantly improving performance when dealing with large datasets (500k+ records).
        
        Returns:
            Tuple of (gl_account_balances, account_balances) dictionaries
        """
        if not transaction_lines:
            logger.warning("No transaction lines provided for balance calculation")
            return {}, {}
        
        period_info = self._get_period_info()
        start_period_number = f"{period_info['start_period_year']}{period_info['start_period']:03d}"
        end_period_number = f"{period_info['period_year']}{period_info['period']:03d}"
        logger.info(f"Calculating consolidated balances: Opening before period {start_period_number}, Closing through period {end_period_number}")
        logger.info(f"Processing {len(transaction_lines)} transaction lines for GL accounts and c2g__Account__c")
        
        # Initialize accumulators for both account types
        gl_opening_debits = {}
        gl_opening_credits = {}
        gl_closing_debits = {}
        gl_closing_credits = {}
        
        acc_opening_debits = {}
        acc_opening_credits = {}
        acc_closing_debits = {}
        acc_closing_credits = {}
        
        # Track statistics
        skipped_no_gl_account = 0
        skipped_no_account = 0
        skipped_no_period = 0
        processed_opening = 0
        processed_closing = 0
        
        # Single pass through all transaction lines
        for line in transaction_lines:
            gl_account_id = line.get('c2g__GeneralLedgerAccount__c')
            account_id = line.get('c2g__Account__c')
            
            if not gl_account_id:
                skipped_no_gl_account += 1
            if not account_id:
                skipped_no_account += 1
            
            net_value = self._get_net_value(line)
            period_number = self._get_period_number(line)
            
            if not period_number:
                skipped_no_period += 1
                continue
            
            is_opening = period_number < start_period_number
            is_closing = period_number <= end_period_number
            
            # Process GL account balances
            if gl_account_id:
                if is_opening:
                    if net_value > 0:
                        gl_opening_debits[gl_account_id] = gl_opening_debits.get(gl_account_id, 0.0) + net_value
                    elif net_value < 0:
                        gl_opening_credits[gl_account_id] = gl_opening_credits.get(gl_account_id, 0.0) + abs(net_value)
                
                if is_closing:
                    if net_value > 0:
                        gl_closing_debits[gl_account_id] = gl_closing_debits.get(gl_account_id, 0.0) + net_value
                    elif net_value < 0:
                        gl_closing_credits[gl_account_id] = gl_closing_credits.get(gl_account_id, 0.0) + abs(net_value)
            
            # Process c2g__Account__c balances
            if account_id:
                if is_opening:
                    if net_value > 0:
                        acc_opening_debits[account_id] = acc_opening_debits.get(account_id, 0.0) + net_value
                    elif net_value < 0:
                        acc_opening_credits[account_id] = acc_opening_credits.get(account_id, 0.0) + abs(net_value)
                    processed_opening += 1
                
                if is_closing:
                    if net_value > 0:
                        acc_closing_debits[account_id] = acc_closing_debits.get(account_id, 0.0) + net_value
                    elif net_value < 0:
                        acc_closing_credits[account_id] = acc_closing_credits.get(account_id, 0.0) + abs(net_value)
                    processed_closing += 1
        
        # Log statistics
        gl_accounts = gl_opening_debits.keys() | gl_opening_credits.keys() | gl_closing_debits.keys() | gl_closing_credits.keys()
        accounts = acc_opening_debits.keys() | acc_opening_credits.keys() | acc_closing_debits.keys() | acc_closing_credits.keys()
        
        logger.info(f"Balance calculation complete: {len(gl_accounts)} GL accounts, {len(accounts)} c2g__Account__c records")
        logger.info(f"  Processed: {processed_opening} opening transactions, {processed_closing} closing transactions")
        logger.info(f"  Total transaction lines analyzed: {len(transaction_lines)}")
        if skipped_no_gl_account > 0:
            logger.warning(f"  Skipped {skipped_no_gl_account} transactions with no GL account ID")
        if skipped_no_account > 0:
            logger.warning(f"  Skipped {skipped_no_account} transactions with no c2g__Account__c ID")
        if skipped_no_period > 0:
            logger.warning(f"  Skipped {skipped_no_period} transactions with no period number")
        
        # Log sample totals for GL accounts
        total_gl_opening_dr = sum(gl_opening_debits.values())
        total_gl_opening_cr = sum(gl_opening_credits.values())
        total_gl_closing_dr = sum(gl_closing_debits.values())
        total_gl_closing_cr = sum(gl_closing_credits.values())
        
        # Log sample totals for c2g__Account__c
        total_acc_opening_dr = sum(acc_opening_debits.values())
        total_acc_opening_cr = sum(acc_opening_credits.values())
        total_acc_closing_dr = sum(acc_closing_debits.values())
        total_acc_closing_cr = sum(acc_closing_credits.values())
        
        # Convert to final balance structures
        gl_balances = self._convert_debit_credit_to_net_position(
            gl_opening_debits, gl_opening_credits, gl_closing_debits, gl_closing_credits
        )
        account_balances = self._convert_debit_credit_to_net_position(
            acc_opening_debits, acc_opening_credits, acc_closing_debits, acc_closing_credits
        )
        
        return gl_balances, account_balances
    
    def _calculate_balances(self, transaction_lines: List[Dict], group_by_field: str) -> Dict[str, Dict]:
        """Calculate opening and closing balances for accounts grouped by specified field
        
        Matches Salesforce Analytics trial balance logic:
        - Opening: sum of transactions where PeriodYearPeriodNumber < START period (before period range start)
        - Closing: sum of transactions where PeriodYearPeriodNumber <= END period (through period range end)
        - Uses period assignment, not transaction date, to match Salesforce's period-based accounting
        - Debit = sum of positive ValueHome (where ValueHome >= 0)
        - Credit = sum of absolute value of negative ValueHome (where ValueHome < 0)
        
        Args:
            transaction_lines: List of transaction line items from Salesforce
            group_by_field: Field to group balances by (e.g., 'c2g__GeneralLedgerAccount__c')
            
        Returns:
            Dictionary mapping account IDs to their opening/closing debit/credit balances
        """
        if not transaction_lines:
            logger.warning(f"No transaction lines provided for balance calculation on field {group_by_field}")
            return {}
        
        period_info = self._get_period_info()
        start_period_number = f"{period_info['start_period_year']}{period_info['start_period']:03d}"
        end_period_number = f"{period_info['period_year']}{period_info['period']:03d}"
        logger.info(f"Calculating balances for {group_by_field}: Opening before period {start_period_number}, Closing through period {end_period_number}")
        logger.info(f"Processing {len(transaction_lines)} transaction lines")
        
        # Separate debit and credit accumulators
        opening_debits = {}   # Sum of positive values before START period
        opening_credits = {}  # Sum of abs(negative values) before START period
        closing_debits = {}   # Sum of positive values through END period
        closing_credits = {}  # Sum of abs(negative values) through END period
        
        # Track statistics for validation
        skipped_no_account = 0
        skipped_no_period = 0
        processed_opening = 0
        processed_closing = 0
        
        for line in transaction_lines:
            account_id = line.get(group_by_field)
            if not account_id:
                skipped_no_account += 1
                continue
            
            net_value = self._get_net_value(line)
            period_number = self._get_period_number(line)
            
            # Skip transactions without period assignment
            if not period_number:
                skipped_no_period += 1
                continue
            
            # Accumulate OPENING balances (transactions BEFORE start period)
            # PeriodYearPeriodNumber < start_period_number (e.g., 2023012 < 2024001)
            if period_number < start_period_number:
                if net_value > 0:
                    # Positive value = Debit
                    opening_debits[account_id] = opening_debits.get(account_id, 0.0) + net_value
                elif net_value < 0:
                    # Negative value = Credit (store as absolute value)
                    opening_credits[account_id] = opening_credits.get(account_id, 0.0) + abs(net_value)
                processed_opening += 1
            
            # Accumulate CLOSING balances (transactions THROUGH end period)
            # PeriodYearPeriodNumber <= end_period_number (e.g., all 2024 periods <= 2024012)
            if period_number <= end_period_number:
                if net_value > 0:
                    # Positive value = Debit
                    closing_debits[account_id] = closing_debits.get(account_id, 0.0) + net_value
                elif net_value < 0:
                    # Negative value = Credit (store as absolute value)
                    closing_credits[account_id] = closing_credits.get(account_id, 0.0) + abs(net_value)
                processed_closing += 1
        
        # Log statistics for validation
        all_accounts = opening_debits.keys() | opening_credits.keys() | closing_debits.keys() | closing_credits.keys()
        logger.info(f"Balance calculation complete: {len(all_accounts)} accounts")
        logger.info(f"  Processed: {processed_opening} opening transactions, {processed_closing} closing transactions")
        logger.info(f"  Total transaction lines analyzed: {len(transaction_lines)}")
        if skipped_no_account > 0:
            logger.warning(f"  Skipped {skipped_no_account} transactions with no account ID")
        if skipped_no_period > 0:
            logger.warning(f"  Skipped {skipped_no_period} transactions with no period number")
        
        # Log sample totals for validation
        total_opening_dr = sum(opening_debits.values())
        total_opening_cr = sum(opening_credits.values())
        total_closing_dr = sum(closing_debits.values())
        total_closing_cr = sum(closing_credits.values())
        logger.info(f"  Opening balances: Debit {total_opening_dr:,.2f}, Credit {total_opening_cr:,.2f}, Net {total_opening_dr - total_opening_cr:,.2f}")
        logger.info(f"  Closing balances: Debit {total_closing_dr:,.2f}, Credit {total_closing_cr:,.2f}, Net {total_closing_dr - total_closing_cr:,.2f}")
        
        # Convert to final balance structure with same-side rule
        return self._convert_debit_credit_to_net_position(opening_debits, opening_credits, 
                                                          closing_debits, closing_credits)
    
    def _convert_debit_credit_to_net_position(self, opening_debits: Dict[str, float], 
                                              opening_credits: Dict[str, float],
                                              closing_debits: Dict[str, float], 
                                              closing_credits: Dict[str, float]) -> Dict[str, Dict]:
        """Convert raw debit/credit sums to net position balances following same-side rule
        
        This matches Salesforce trial balance logic where:
        - We calculate net position: net = debits - credits
        - Closing net determines which side (debit or credit) the account balance belongs on
        - Opening balance must be on the same side as closing (same-side rule)
        """
        account_balances = {}
        all_account_ids = (set(opening_debits.keys()) | set(opening_credits.keys()) | 
                          set(closing_debits.keys()) | set(closing_credits.keys()))
        
        for account_id in all_account_ids:
            opening_debit = opening_debits.get(account_id, 0.0)
            opening_credit = opening_credits.get(account_id, 0.0)
            closing_debit = closing_debits.get(account_id, 0.0)
            closing_credit = closing_credits.get(account_id, 0.0)
            
            # Calculate net positions
            opening_net = opening_debit - opening_credit
            closing_net = closing_debit - closing_credit
            
            # Same-side rule: closing net determines the side, opening must match
            if closing_net > 0:  # Net debit position
                account_balances[account_id] = {
                    'opening_debit_balance': abs(opening_net),
                    'opening_credit_balance': 0.0,
                    'closing_debit_balance': closing_net,
                    'closing_credit_balance': 0.0
                }
            elif closing_net < 0:  # Net credit position
                account_balances[account_id] = {
                    'opening_debit_balance': 0.0,
                    'opening_credit_balance': abs(opening_net),
                    'closing_debit_balance': 0.0,
                    'closing_credit_balance': abs(closing_net)
                }
            else:  # Zero closing - use opening to determine side
                if opening_net > 0:
                    account_balances[account_id] = {
                        'opening_debit_balance': opening_net,
                        'opening_credit_balance': 0.0,
                        'closing_debit_balance': 0.0,
                        'closing_credit_balance': 0.0
                    }
                elif opening_net < 0:
                    account_balances[account_id] = {
                        'opening_debit_balance': 0.0,
                        'opening_credit_balance': abs(opening_net),
                        'closing_debit_balance': 0.0,
                        'closing_credit_balance': 0.0
                    }
                else:  # Both zero
                    account_balances[account_id] = {
                        'opening_debit_balance': 0.0,
                        'opening_credit_balance': 0.0,
                        'closing_debit_balance': 0.0,
                        'closing_credit_balance': 0.0
                    }
        
        return account_balances
    
    def _transform_customers(self, accounts: List[Dict], account_balances: Dict[str, Dict]) -> List[Dict]:
        """Transform customer accounts with calculated balances"""
        default_balances = {'opening_debit_balance': 0.0, 'closing_debit_balance': 0.0, 
                            'opening_credit_balance': 0.0, 'closing_credit_balance': 0.0}
        
        transformed = []
        for acc in accounts:
            if self._get_record_type(acc) != 'Standard':
                continue
            
            acc_id = acc.get('Id')
            if not isinstance(acc_id, str) or not acc_id:
                continue
            balances = account_balances.get(acc_id, default_balances)
            
            transformed.append({
                'customer_id': acc.get('AccountNumber', acc_id),
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
        
        return transformed
    
    def _transform_suppliers(self, accounts: List[Dict], account_balances: Dict[str, Dict]) -> List[Dict]:
        """Transform supplier accounts with calculated balances"""
        default_balances = {'opening_debit_balance': 0.0, 'closing_debit_balance': 0.0, 
                            'opening_credit_balance': 0.0, 'closing_credit_balance': 0.0}
        
        transformed = []
        for acc in accounts:
            if self._get_record_type(acc) != 'Supplier Data Management':
                continue
            
            acc_id = acc.get('Id')
            if not isinstance(acc_id, str) or not acc_id:
                continue
            balances = account_balances.get(acc_id, default_balances)
            
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
        result = {
            'sales_invoices': self._transform_sales_invoices(data),
            'purchase_invoices': self._transform_purchase_invoices(data),
            'payments': self._transform_payments(data)
        }
        logger.info(f"Transformed source documents: {len(result['sales_invoices'])} sales invoices, "
                   f"{len(result['purchase_invoices'])} purchase invoices, {len(result['payments'])} payments")
        return result
    
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
        
        return transformed
    
    def _transform_tax_codes(self, data: Dict) -> List[Dict]:
        """Transform Salesforce tax codes to SAF-T tax table entries"""
        transformed = []
        for tax_code in data.get('tax_codes', []):
            # Get the most recent tax rate from nested relationship
            tax_rate = 0.0
            tax_rates_obj = tax_code.get('c2g__TaxRates__r')
            if isinstance(tax_rates_obj, dict):
                tax_rates = tax_rates_obj.get('records', [])
                if tax_rates:
                    tax_rate = self._parse_decimal(tax_rates[0].get('c2g__Rate__c', 0))
            
            transformed.append({
                'tax_type': 'ДДС',
                'tax_code': tax_code.get('Name', 'STD'),
                'description': tax_code.get('c2g__Description__c', ''),
                'tax_percentage': tax_rate
            })
        
        return transformed
    
    def _transform_products(self, products: List[Dict]) -> List[Dict]:
        """Transform Salesforce Product2 records to SAF-T products"""
        return [
            {
                'product_code': product.get('ProductCode', ''),
                'goods_services_id': '01',
                'product_group': product.get('Family', ''),
                'description': product.get('Name', ''),
                'product_commodity_code': '0',
                'product_number_code': product.get('ProductCode', ''),
                'uom_base': 'HUR',
                'uom_standard': 'ЧАС',
                'uom_conversion_factor': '1',
                'tax_type': '100',
                'tax_code': '100211'
            }
            for product in products
        ]
    
    def _parse_decimal(self, value: Any) -> float:
        """Parse decimal value safely with validation"""
        if value is None or value == '':
            return 0.0
        try:
            result = float(value)
            # Validate result is a valid number (not NaN or Inf)
            if not (-1e15 < result < 1e15):
                logger.warning(f"Unusual decimal value detected: {value} -> {result}")
            return result
        except (ValueError, TypeError) as e:
            logger.debug(f"Failed to parse decimal value '{value}': {e}")
            return 0.0
