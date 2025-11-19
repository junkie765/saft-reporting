"""Salesforce REST API client"""
import logging
import time
import csv
import io
from datetime import datetime
from typing import Dict, List, Any, Set
import requests


logger = logging.getLogger(__name__)


class SalesforceRestClient:
    """Client for Salesforce REST API"""
    
    def __init__(self, sf_session, config: dict):
        """
        Initialize REST API client
        
        Args:
            sf_session: Authenticated Salesforce session from OAuth
            config: Configuration dictionary
        """
        self.sf_session = sf_session
        self.config = config
        self.instance_url = f"https://{sf_session.sf_instance}"
        self.api_version = config['salesforce']['api_version']
        self.base_url = f"{self.instance_url}/services/data/v{self.api_version}"
        
        self.headers = {
            'Authorization': f'Bearer {sf_session.session_id}',
            'Content-Type': 'application/json'
        }

    def query_rest(self, soql_query: str, record_type: str = "records") -> List[Dict[str, Any]]:
        """
        Execute SOQL query using REST API with automatic pagination support
        
        Args:
            soql_query: SOQL query string
            record_type: Descriptive name for the records being queried (for logging)
            
        Returns:
            List of records from query results
            
        Raises:
            requests.exceptions.RequestException: If API request fails
        """
        url = f"{self.base_url}/query"
        params = {'q': soql_query}
        all_records = []
        
        try:
            while url:
                response = requests.get(url, params=params if params else None, headers=self.headers)
                response.raise_for_status()
                
                result = response.json()
                all_records.extend(result.get('records', []))
                
                # Handle pagination
                if url := result.get('nextRecordsUrl'):
                    url = f"{self.instance_url}{url}"
                    params = None
            
            return all_records
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error querying {record_type}: {e}")
            raise
    
    def query_bulk(self, soql_query: str, record_type: str = "records") -> List[Dict[str, Any]]:
        """
        Execute SOQL query using Bulk API v2 for large datasets (optimized for 1M+ records)
        
        Args:
            soql_query: SOQL query string
            record_type: Descriptive name for the records being queried (for logging)
            
        Returns:
            List of records from query results
            
        Raises:
            requests.exceptions.RequestException: If API request fails
        """
        bulk_url = f"{self.base_url}/jobs/query"
        
        try:
            # Step 1: Create bulk query job
            logger.info(f"Creating Bulk API v2 job for {record_type}...")
            job_data = {
                "operation": "query",
                "query": soql_query
            }
            response = requests.post(bulk_url, json=job_data, headers=self.headers)
            response.raise_for_status()
            job_info = response.json()
            job_id = job_info['id']
            logger.info(f"Bulk job created: {job_id}")
            
            # Step 2: Poll job status until complete
            job_status_url = f"{bulk_url}/{job_id}"
            max_wait = 600  # 10 minutes max wait
            wait_time = 0
            poll_interval = 2  # Start with 2 seconds
            
            while wait_time < max_wait:
                time.sleep(poll_interval)
                wait_time += poll_interval
                
                response = requests.get(job_status_url, headers=self.headers)
                response.raise_for_status()
                job_info = response.json()
                state = job_info['state']
                
                if state == 'JobComplete':
                    num_records = job_info.get('numberRecordsProcessed', 0)
                    logger.info(f"Bulk job completed: {num_records} records processed in {wait_time}s")
                    break
                elif state == 'Failed':
                    error_msg = job_info.get('errorMessage', 'Unknown error')
                    raise Exception(f"Bulk job failed: {error_msg}")
                elif state == 'Aborted':
                    raise Exception("Bulk job was aborted")
                
                # Increase poll interval gradually (2s -> 5s -> 10s)
                if wait_time > 30 and poll_interval < 5:
                    poll_interval = 5
                elif wait_time > 120 and poll_interval < 10:
                    poll_interval = 10
                
                if wait_time % 20 == 0:  # Log every 20 seconds
                    logger.info(f"Bulk job status: {state} (waited {wait_time}s)...")
            
            if wait_time >= max_wait:
                raise TimeoutError(f"Bulk job timed out after {max_wait}s")
            
            # Step 3: Retrieve results as CSV (with locator pagination for large datasets)
            results_url = f"{job_status_url}/results"
            headers_csv = self.headers.copy()
            headers_csv['Accept'] = 'text/csv'
            
            logger.info(f"Downloading results for {record_type}...")
            all_records = []
            locator = None
            batch_count = 0
            
            while True:
                batch_count += 1
                # Add locator to URL if this is not the first batch
                if locator:
                    batch_url = f"{results_url}?locator={locator}"
                    logger.info(f"Fetching batch {batch_count} with locator...")
                else:
                    batch_url = results_url
                
                response = requests.get(batch_url, headers=headers_csv, stream=True)
                response.raise_for_status()
                
                # Parse CSV batch directly into all_records (avoid intermediate list)
                csv_content = response.content.decode('utf-8')
                csv_reader = csv.DictReader(io.StringIO(csv_content))
                batch_start = len(all_records)
                
                for row in csv_reader:
                    # Convert CSV row to match REST API nested structure
                    record = {}
                    for key, value in row.items():
                        # Convert empty strings to None
                        value = None if value == '' else value
                        
                        # Handle nested fields (e.g., "c2g__Transaction__r.c2g__Period__r.Name")
                        if '.' in key:
                            parts = key.split('.')
                            current = record
                            for part in parts[:-1]:
                                current = current.setdefault(part, {})
                            current[parts[-1]] = value
                        else:
                            record[key] = value
                    
                    all_records.append(record)
                
                batch_size = len(all_records) - batch_start
                logger.info(f"Batch {batch_count}: Retrieved {batch_size} records (total: {len(all_records)})")
                
                # Check for more batches via Sforce-Locator header
                locator = response.headers.get('Sforce-Locator')
                if not locator or locator.lower() == 'null':
                    break
            
            logger.info(f"Retrieved {len(all_records)} {record_type} via Bulk API v2 ({batch_count} batches)")
            return all_records
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error in Bulk API query for {record_type}: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error in Bulk API query for {record_type}: {e}")
            raise
    
    def extract_certinia_data(self, year: str, period_from: str, period_to: str,
                            start_date: datetime, end_date: datetime,
                            company_filter: str | None = None, 
                            sections: Set[str] | None = None) -> Dict[str, List]:
        """
        Extract Certinia data for SAF-T reporting
        
        Args:
            year: Year for extraction (e.g., '2024')
            period_from: Starting period number (e.g., '1', '2', etc.)
            period_to: Ending period number (e.g., '12')
            start_date: Period start date (for non-GL queries and balance calculations)
            end_date: Period end date (for non-GL queries and balance calculations)
            company_filter: Optional company name to filter data
            sections: Set of sections to extract. If None, extracts all.
                     Options: 'gl', 'customers', 'suppliers', 'sales_invoices', 'purchase_invoices', 'payments'
            
        Returns:
            Dictionary containing all extracted data
        """
        # Default to all sections if not specified
        if sections is None:
            sections = {'gl', 'customers', 'suppliers', 'sales_invoices', 'purchase_invoices', 'payments'}
        
        data = {}
        objects_config = self.config['certinia']['objects']
        
        # Format dates for SOQL (used for invoices, payments, and balance calculations)
        start_str = start_date.strftime('%Y-%m-%d')
        end_str = end_date.strftime('%Y-%m-%d')
        
        # Build period filter for GL journal queries (period-based, not date-based)
        # Get period names for the range (year + period number, e.g., '2025/001', '2025/002')
        # Valid periods: 000 (opening), 001-012 (monthly), 100 (year-end adjustments)
        period_names = []
        try:
            period_from_num = int(period_from)
            period_to_num = int(period_to)
            
            # Build list of periods in range, ensuring we only include valid periods
            for p in range(period_from_num, period_to_num + 1):
                # Only include valid periods: 000, 001-012, 100
                if p == 0 or (1 <= p <= 12) or p == 100:
                    period_names.append(f"{year}/{p:03d}")
        except ValueError:
            # If not numeric, use as-is (e.g., '000', '001', '100')
            period_names = [f"{year}/{period_from}"]
            if period_from != period_to:
                period_names.append(f"{year}/{period_to}")
        
        logger.info(f"GL Journals: Filtering by periods {period_names}")
        logger.info(f"Other documents: Filtering by dates {start_str} to {end_str}")
        
        # Get company ID if filter is specified
        company_id = None
        if company_filter:
            company_query = f"""
                SELECT Id, Name, FF_Name_cyrillic__c, c2g__Street__c, c2g__City__c, 
                       F_City_Cyrillic__c, c2g__ZipPostCode__c, c2g__Country__c, 
                       c2g__Phone__c, c2g__ContactEmail__c, c2g__Website__c,
                       c2g__VATRegistrationNumber__c, c2g__TaxIdentificationNumber__c,
                       SFocus_Company_Identification_Number__c, c2g__StateProvince__c,
                       F_Address_Cyrillic__c, c2g__BankAccount__r.c2g__IBANNumber__c,
                       Contact__r.FirstName, Contact__r.LastName, Contact__r.Title
                FROM {objects_config['company']}
                WHERE Name = '{company_filter}'
                LIMIT 1
            """
            company_result = self.query_rest(company_query, "companies")
            if company_result:
                company_id = company_result[0]['Id']
                data['company'] = company_result
                logger.info(f"Found company: {company_filter} (ID: {company_id})")
            else:
                logger.warning(f"Company '{company_filter}' not found, proceeding without filter")
        
        # Build company filter clause for queries (validate company_id is valid)
        company_filter_clause = f"AND c2g__OwnerCompany__c = '{company_id}'" if company_id and isinstance(company_id, str) else ""
        
        # Extract Journal Entries (GL entries)
        if 'gl' in sections:
            logger.info("Extracting general ledger journal entries...")
            # Build IN clause for period names
            period_in_clause = "('" + "', '".join(period_names) + "')"
            journal_query = f"""
                SELECT Id, Name, c2g__JournalDate__c, c2g__Type__c, 
                       c2g__JournalStatus__c, c2g__Reference__c, c2g__Period__r.Name,
                       c2g__Period__r.c2g__PeriodNumber__c
                FROM {objects_config['journal_entry']}
                WHERE c2g__Period__r.Name IN {period_in_clause}
                  AND c2g__JournalStatus__c = 'Complete'
                  {company_filter_clause}
            """
            data['journals'] = self.query_rest(journal_query, "journal entries")
            logger.info(f"Found {len(data['journals'])} journals.")
            
            line_query = f"""
                SELECT Id, Name, c2g__Journal__c, c2g__GeneralLedgerAccount__c,
                       c2g__GeneralLedgerAccount__r.Name, c2g__GeneralLedgerAccount__r.c2g__ReportingCode__c,
                       c2g__LineType__c, c2g__Debits__c, c2g__Credits__c, c2g__LineDescription__c
                FROM {objects_config['journal_line']}
                WHERE c2g__Journal__r.c2g__Period__r.Name IN {period_in_clause}
                  {company_filter_clause}
            """
            data['journal_lines'] = self.query_rest(line_query, "journal lines")
        else:
            data['journals'] = []
            data['journal_lines'] = []
        
        # Extract Sales Invoices
        if 'sales_invoices' in sections:
            logger.info("Extracting sales invoices...")
            invoice_company_filter = f"AND fferpcore__Company__r.c2g__msg_link_ffa_id__c = '{company_id}'" if company_id else ""
            sales_invoice_query = f"""
                SELECT Id, Name, fferpcore__DocumentDate__c, fferpcore__DocumentDueDate__c, fferpcore__Account__c,
                       fferpcore__Account__r.Name, fferpcore__Account__r.c2g__CODATaxpayerIdentificationNumber__c,
                       fferpcore__DocumentStatus__c, CurrencyIsoCode
                FROM {objects_config['invoice']}
                WHERE fferpcore__DocumentDate__c >= {start_str}
                  AND fferpcore__DocumentDate__c <= {end_str}
                  AND fferpcore__DocumentStatus__c = 'Complete'
                  {invoice_company_filter}
            """
            data['sales_invoices'] = self.query_rest(sales_invoice_query, "sales invoices")
            
            invoice_line_company_filter = f"AND fferpcore__BillingDocument__r.fferpcore__Company__r.c2g__msg_link_ffa_id__c = '{company_id}'" if company_id else ""
            sales_invoice_line_query = f"""
                SELECT Id, Name, fferpcore__BillingDocument__c, c2g__GeneralLedgerAccount__c,
                       c2g__GeneralLedgerAccount__r.c2g__ReportingCode__c,
                       fferpcore__ProductService__c, fferpcore__ProductService__r.ProductCode, fferpcore__ProductService__r.Name,
                       fferpcore__Quantity__c, fferpcore__UnitPrice__c, fferpcore__NetValue__c,
                       fferpcore__LineDescription__c, fferpcore__TaxCode1__c, fferpcore__TaxCode1__r.Name,
                       fferpcore__TaxValue1__c
                FROM {objects_config['invoice_line']}
                WHERE fferpcore__BillingDocument__r.fferpcore__DocumentDate__c >= {start_str}
                  AND fferpcore__BillingDocument__r.fferpcore__DocumentDate__c <= {end_str}
                  {invoice_line_company_filter}
            """
            data['sales_invoice_lines'] = self.query_rest(sales_invoice_line_query, "sales invoice lines")
        else:
            data['sales_invoices'] = []
            data['sales_invoice_lines'] = []
        
        # Extract Cash Entries (Payments)
        if 'payments' in sections:
            logger.info("Extracting payment transactions...")
            payment_query = f"""
                SELECT Id, Name, c2g__Date__c, c2g__Reference__c, c2g__Period__r.Name,
                       c2g__Account__c, c2g__Account__r.Name,
                       c2g__Account__r.c2g__CODATaxpayerIdentificationNumber__c,
                       CurrencyIsoCode
                FROM {objects_config['cash_entry']}
                WHERE c2g__Date__c >= {start_str}
                  AND c2g__Date__c <= {end_str}
                  {company_filter_clause}
            """
            data['payments'] = self.query_rest(payment_query, "payment entries")
            
            payment_line_company_filter = f"AND c2g__CashEntry__r.c2g__OwnerCompany__c = '{company_id}'" if company_id else ""
            payment_line_query = f"""
                SELECT Id, Name, c2g__CashEntry__c,
                       c2g__BankAccountValue__c, c2g__CashEntryValue__c, c2g__NetValue__c,
                       c2g__LineDescription__c, c2g__LineNumber__c,
                       c2g__Account__c, c2g__Account__r.c2g__CODATaxpayerIdentificationNumber__c,
                       c2g__Account__r.Name
                FROM {objects_config['cash_entry_line']}
                WHERE c2g__CashEntry__r.c2g__Date__c >= {start_str}
                  AND c2g__CashEntry__r.c2g__Date__c <= {end_str}
                  {payment_line_company_filter}
            """
            data['payment_lines'] = self.query_rest(payment_line_query, "payment lines")
        else:
            data['payments'] = []
            data['payment_lines'] = []
        
        # Extract Transaction Line Items for balance calculations - fetch ALL historical data up to period end
        # Include period information for proper opening/closing balance calculation
        logger.info("Extracting transaction lines for balance calculations...")
        company_filter_sql = f"c2g__Transaction__r.c2g__OwnerCompany__c = '{company_id}' AND " if company_id and isinstance(company_id, str) else ""
        
        # Fetch ALL transaction lines through the selected period for accurate balance calculation
        # CRITICAL: We need ALL historical transactions to calculate opening balances correctly
        # Cannot filter by year in SOQL due to field type ambiguity, so fetch all and filter in code
        # The transformer will handle period-based filtering for opening/closing balances
        
        logger.info(f"Transaction lines: Fetching ALL transactions with periods assigned")
        logger.info(f"Note: Balance calculations will filter by period {year}/{int(period_to):03d}")
        logger.info(f"Note: This may take a while for large datasets...")
        
        transaction_line_query = f"""
            SELECT Id, c2g__GeneralLedgerAccount__c, c2g__Account__c, c2g__LineType__c, c2g__HomeValue__c,
                   c2g__HomeCredits__c, c2g__HomeDebits__c,
                   c2g__Transaction__r.c2g__TransactionDate__c, c2g__HomeCurrency__r.Name,
                   c2g__Transaction__r.c2g__Period__r.Name,
                   c2g__Transaction__r.c2g__Period__r.c2g__PeriodNumber__c,
                   c2g__Transaction__r.c2g__Period__r.c2g__YearName__c
            FROM c2g__codaTransactionLineItem__c
            WHERE {company_filter_sql}c2g__Transaction__r.c2g__Period__r.Name != null
                  AND c2g__HomeCurrency__r.Name = 'BGN'
        """
        
        # Use Bulk API v2 for large transaction line queries (600k+ records)
        data['transaction_lines'] = self.query_bulk(transaction_line_query, "transaction line items for balance calculations")
        
        # Extract General Ledger Accounts
        if data['transaction_lines']:
            gl_account_ids = {
                line['c2g__GeneralLedgerAccount__c'] 
                for line in data['transaction_lines'] 
                if line.get('c2g__GeneralLedgerAccount__c')
            }
            
            if gl_account_ids:
                gl_ids_str = "','".join(gl_account_ids)
                gl_query = f"""
                    SELECT Id, Name, F_Bulgarian_GLA_Name__c, c2g__ReportingCode__c, c2g__StandardAccountID__c, c2g__Type__c, 
                           c2g__TrialBalance1__c, c2g__TrialBalance2__c
                    FROM {objects_config['general_ledger']}
                    WHERE Id IN ('{gl_ids_str}')
                """
                data['gl_accounts'] = self.query_rest(gl_query, "GL accounts")
            else:
                data['gl_accounts'] = []
        else:
            gl_query = f"""
                SELECT Id, Name, c2g__ReportingCode__c, c2g__StandardAccountID__c, c2g__Type__c, 
                       c2g__TrialBalance1__c, c2g__TrialBalance2__c
                FROM {objects_config['general_ledger']}
                WHERE c2g__ReportingCode__c != null
            """
            data['gl_accounts'] = self.query_rest(gl_query, "GL accounts")
        
        # Extract Accounts (Customers/Suppliers)
        if 'customers' in sections or 'suppliers' in sections:
            # Filter accounts that have transactions in the selected company
            # Use transaction lines to identify relevant accounts
            if data.get('transaction_lines'):
                account_ids = {
                    line['c2g__Account__c'] 
                    for line in data['transaction_lines'] 
                    if line.get('c2g__Account__c')
                }
                
                if account_ids:
                    # Batch the account IDs to avoid SOQL query length limits
                    account_list = []
                    batch_size = 200  # Safe batch size for IN clause
                    account_ids_list = list(account_ids)
                    
                    for i in range(0, len(account_ids_list), batch_size):
                        batch = account_ids_list[i:i + batch_size]
                        acc_ids_str = "','".join(batch)
                        account_query = f"""
                            SELECT Id, Name, AccountNumber, Type, BillingStreet, 
                                   BillingCity, BillingPostalCode, BillingCountry, Phone,
                                   c2g__CODATaxpayerIdentificationNumber__c, c2g__CODAVATRegistrationNumber__c,
                                   c2g__CODAECCountryCode__c, F_Group__r.Name, Fax, Website, c2g__CODAInvoiceEmail__c, RecordType.Name,
                                   c2g__CODAAccountsReceivableControl__r.c2g__StandardAccountID__c,
                                   c2g__CODAAccountsPayableControl__r.c2g__StandardAccountID__c
                            FROM {objects_config['account']}
                            WHERE Id IN ('{acc_ids_str}')
                              AND (RecordType.Name = 'Standard' OR RecordType.Name = 'Supplier Data Management')
                        """
                        batch_results = self.query_rest(account_query, f"accounts batch {i//batch_size + 1}")
                        account_list.extend(batch_results)
                    
                    data['accounts'] = account_list
                    logger.info(f"Filtered to {len(account_list)} accounts with transactions in selected company")
                else:
                    data['accounts'] = []
            else:
                # Fallback: fetch all accounts if no transaction lines
                account_query = f"""
                    SELECT Id, Name, AccountNumber, Type, BillingStreet, 
                           BillingCity, BillingPostalCode, BillingCountry, Phone,
                           c2g__CODATaxpayerIdentificationNumber__c, c2g__CODAVATRegistrationNumber__c,
                           c2g__CODAECCountryCode__c, F_Group__r.Name, Fax, Website, c2g__CODAInvoiceEmail__c, RecordType.Name,
                           c2g__CODAAccountsReceivableControl__r.c2g__StandardAccountID__c,
                           c2g__CODAAccountsPayableControl__r.c2g__StandardAccountID__c
                    FROM {objects_config['account']}
                    WHERE (RecordType.Name = 'Standard' OR RecordType.Name = 'Supplier Data Management')
                """
                data['accounts'] = self.query_rest(account_query, "accounts")
        else:
            data['accounts'] = []
        
        # Extract Products
        product_query = """
            SELECT Id, ProductCode, Name, Description, Family
            FROM Product2
            WHERE IsActive = true
        """
        data['products'] = self.query_rest(product_query, "products")
        
        # Extract Tax Codes with Rates
        tax_code_query = f"""
            SELECT Id, Name, c2g__Description__c,
                   (SELECT c2g__Rate__c, c2g__StartDate__c 
                    FROM c2g__TaxRates__r 
                    WHERE c2g__StartDate__c <= {end_str}
                    ORDER BY c2g__StartDate__c DESC
                    LIMIT 1)
            FROM c2g__codaTaxCode__c
        """
        data['tax_codes'] = self.query_rest(tax_code_query, "tax codes")
        
        # Extract Purchase Invoices
        if 'purchase_invoices' in sections:
            purchase_invoice_query = f"""
                SELECT Id, Name, c2g__Account__c, c2g__Account__r.c2g__CODATaxpayerIdentificationNumber__c,
                       c2g__InvoiceDate__c, c2g__DueDate__c, c2g__InvoiceStatus__c,
                       c2g__AccountInvoiceNumber__c, c2g__InvoiceDescription__c, CurrencyIsoCode
                FROM {objects_config['payable_invoice']}
                WHERE c2g__InvoiceDate__c >= {start_str}
                  AND c2g__InvoiceDate__c <= {end_str}
                  {company_filter_clause}
                  AND c2g__InvoiceStatus__c = 'Complete'
            """
            data['purchase_invoices'] = self.query_rest(purchase_invoice_query, "purchase invoices")
            
            purchase_line_company_filter = f"AND c2g__PurchaseInvoice__r.c2g__OwnerCompany__c = '{company_id}'" if company_id else ""
            purchase_invoice_line_query = f"""
                SELECT Id, Name, c2g__PurchaseInvoice__c, c2g__GeneralLedgerAccount__c,
                       c2g__GeneralLedgerAccount__r.c2g__ReportingCode__c,
                       F_Product__c, F_Product__r.ProductCode, F_Product__r.Name,
                       F_Quantity__c, c2g__NetValue__c,
                       c2g__LineDescription__c, c2g__InputVATCode__c, c2g__TaxValue1__c
                FROM {objects_config['payable_invoice_line']}
                WHERE c2g__PurchaseInvoice__r.c2g__InvoiceDate__c >= {start_str}
                  AND c2g__PurchaseInvoice__r.c2g__InvoiceDate__c <= {end_str}
                  {purchase_line_company_filter}
                  AND c2g__PurchaseInvoice__r.c2g__InvoiceStatus__c = 'Complete'
            """
            data['purchase_invoice_lines'] = self.query_rest(purchase_invoice_line_query, "purchase invoice lines")
        else:
            data['purchase_invoices'] = []
            data['purchase_invoice_lines'] = []
        
        # Extract Company Information (if not already extracted by filter)
        if 'company' not in data:
            company_query = f"""
                SELECT Id, Name, FF_Name_cyrillic__c, c2g__Street__c, c2g__City__c, 
                       F_City_Cyrillic__c, c2g__ZipPostCode__c, c2g__Country__c, 
                       c2g__Phone__c, c2g__Fax__c, c2g__ContactEmail__c, c2g__Website__c,
                       c2g__VATRegistrationNumber__c, c2g__TaxIdentificationNumber__c,
                       SFocus_Company_Identification_Number__c, c2g__StateProvince__c,
                       F_Address_Cyrillic__c, c2g__BankAccount__r.c2g__IBANNumber__c
                FROM {objects_config['company']}
                LIMIT 1
            """
            data['company'] = self.query_rest(company_query, "companies")
        
        return data
    
    def get_companies(self) -> list[dict]:
        """
        Fetch all accounting companies from Salesforce
        
        Returns:
            List of company dictionaries with Id and Name
        """
        try:
            query = """
                SELECT Id, Name
                FROM c2g__codaCompany__c
                ORDER BY Name ASC
            """
            results = self.query_rest(query, "companies")
            
            companies = [{
                'id': record.get('Id', ''),
                'name': record.get('Name', '')
            } for record in results]
            
            logger.info(f"Fetched {len(companies)} companies from Salesforce")
            return companies
            
        except Exception as e:
            logger.error(f"Error fetching companies from Salesforce: {e}")
            raise
    
    def get_periods_by_year(self, company_id: str | None = None) -> tuple[list[str], dict[str, list[dict]]]:
        """
        Fetch years and periods from Salesforce c2g__codaPeriod__c object
        
        Args:
            company_id: Optional company ID to filter periods by company
        
        Returns:
            Tuple of (years_list, periods_by_year_dict) where:
            - years_list: Sorted list of year names
            - periods_by_year_dict: Dictionary mapping year names to list of period info dicts
        """
        try:
            # Build query with optional company filter
            if company_id:
                query = f"""
                    SELECT Name, c2g__PeriodNumber__c, c2g__YearName__r.Name, 
                           c2g__StartDate__c, c2g__EndDate__c, c2g__OwnerCompany__c
                    FROM c2g__codaPeriod__c 
                    WHERE c2g__OwnerCompany__c = '{company_id}'
                    ORDER BY c2g__YearName__r.Name ASC, c2g__StartDate__c ASC
                """
            else:
                query = """
                    SELECT Name, c2g__PeriodNumber__c, c2g__YearName__r.Name, 
                           c2g__StartDate__c, c2g__EndDate__c, c2g__OwnerCompany__c
                    FROM c2g__codaPeriod__c 
                    ORDER BY c2g__YearName__r.Name ASC, c2g__StartDate__c ASC
                """
            
            results = self.query_rest(query, "periods")
            
            # Organize data by year, using dict to track unique periods
            years_set = set()
            periods_by_year = {}
            
            for record in results:
                if 'c2g__YearName__r' in record and record['c2g__YearName__r']:
                    year_name = record['c2g__YearName__r']['Name']
                    period_num = record.get('c2g__PeriodNumber__c', '')
                    
                    # Extract just the period number (e.g., '001' from '2024/001')
                    if '/' in period_num:
                        period_num = period_num.split('/')[-1]
                    
                    # Only include periods 000, 001-012, and 100
                    if period_num not in ['000'] + [f'{i:03d}' for i in range(1, 13)] + ['100']:
                        continue
                    
                    years_set.add(year_name)
                    
                    if year_name not in periods_by_year:
                        periods_by_year[year_name] = {}
                    
                    # Use period number as key to ensure uniqueness
                    if period_num not in periods_by_year[year_name]:
                        periods_by_year[year_name][period_num] = {
                            'number': period_num,
                            'name': record.get('Name', ''),
                            'start_date': record.get('c2g__StartDate__c', ''),
                            'end_date': record.get('c2g__EndDate__c', ''),
                            'company_id': record.get('c2g__OwnerCompany__c', '')
                        }
            
            # Convert period dicts back to sorted lists
            for year in periods_by_year:
                periods_by_year[year] = sorted(
                    periods_by_year[year].values(),
                    key=lambda x: x['number']
                )
            
            years = sorted(list(years_set))
            logger.info(f"Fetched {len(years)} years and periods from Salesforce")
            
            return years, periods_by_year
            
        except Exception as e:
            logger.error(f"Error fetching periods from Salesforce: {e}")
            raise