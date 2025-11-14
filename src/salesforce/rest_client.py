"""Salesforce REST API client"""
import logging
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
            sf_session: Authenticated Salesforce session
            config: Configuration dictionary
        """
        self.sf_session = sf_session
        self.config = config
        
        # Get instance URL - handle both regular auth and session_id auth
        if hasattr(sf_session, 'sf_instance') and sf_session.sf_instance:
            self.instance_url = f"https://{sf_session.sf_instance}"
        else:
            # Fallback to config instance_url for session_id auth
            self.instance_url = config['salesforce'].get('instance_url', 'https://scalefocus.my.salesforce.com')
        
        self.session_id = sf_session.session_id
        self.api_version = config['salesforce']['api_version']
        self.base_url = f"{self.instance_url}/services/data/v{self.api_version}"
        
        self.headers = {
            'Authorization': f'Bearer {self.session_id}',
            'Content-Type': 'application/json'
        }
        
        logger.debug(f"REST API initialized - Instance: {self.instance_url}, API: v{self.api_version}")

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
                url = result.get('nextRecordsUrl')
                if url:
                    url = f"{self.instance_url}{url}"
                    params = None  # params are included in nextRecordsUrl
            
            logger.info(f"Retrieved {len(all_records)} {record_type}")
            return all_records
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error querying {record_type}: {e}")
            raise
    
    def extract_certinia_data(self, start_date: datetime, end_date: datetime, 
                            company_filter: str | None = None, 
                            sections: Set[str] | None = None) -> Dict[str, List]:
        """
        Extract Certinia data for SAF-T reporting
        
        Args:
            start_date: Start date for extraction
            end_date: End date for extraction
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
        
        # Format dates for SOQL
        start_str = start_date.strftime('%Y-%m-%d')
        end_str = end_date.strftime('%Y-%m-%d')
        
        # Get company ID if filter is specified
        company_id = None
        if company_filter:
            company_query = f"""
                SELECT Id, Name, FF_Name_cyrillic__c, c2g__Street__c, c2g__City__c, 
                       F_City_Cyrillic__c, c2g__ZipPostCode__c, c2g__Country__c, 
                       c2g__Phone__c, c2g__Fax__c, c2g__ContactEmail__c, c2g__Website__c,
                       c2g__VATRegistrationNumber__c, c2g__TaxIdentificationNumber__c,
                       SFocus_Company_Identification_Number__c, c2g__StateProvince__c,
                       F_Address_Cyrillic__c, c2g__BankAccount__r.c2g__IBANNumber__c
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
        
        # Build company filter clause for queries
        company_filter_clause = f"AND c2g__OwnerCompany__c = '{company_id}'" if company_id else ""
        
        # Extract Journal Entries (GL entries)
        if 'gl' in sections:
            logger.info("Extracting general ledger journal entries...")
            journal_query = f"""
                SELECT Id, Name, c2g__JournalDate__c, c2g__Type__c, 
                       c2g__JournalStatus__c, c2g__Reference__c, c2g__Period__r.Name
                FROM {objects_config['journal_entry']}
                WHERE c2g__JournalDate__c >= {start_str} 
                  AND c2g__JournalDate__c <= {end_str}
                  AND c2g__JournalStatus__c = 'Complete'
                  {company_filter_clause}
            """
            data['journals'] = self.query_rest(journal_query, "journal entries")
            
            line_query = f"""
                SELECT Id, Name, c2g__Journal__c, c2g__GeneralLedgerAccount__c,
                       c2g__GeneralLedgerAccount__r.Name, c2g__GeneralLedgerAccount__r.c2g__ReportingCode__c,
                       c2g__LineType__c, c2g__Debits__c, c2g__Credits__c, c2g__LineDescription__c
                FROM {objects_config['journal_line']}
                WHERE c2g__Journal__r.c2g__JournalDate__c >= {start_str}
                  AND c2g__Journal__r.c2g__JournalDate__c <= {end_str}
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
        
        # Extract Transaction Line Items for balance calculations - fetch ALL historical data
        # Include period information for proper opening/closing balance calculation
        logger.info("Extracting transaction lines for balance calculations...")
        company_filter_sql = f"c2g__Transaction__r.c2g__OwnerCompany__c = '{company_id}' AND " if company_id else ""
        transaction_line_query = f"""
            SELECT Id, c2g__GeneralLedgerAccount__c, c2g__Account__c, c2g__LineType__c, c2g__HomeValue__c,
                   c2g__HomeCredits__c, c2g__HomeDebits__c,
                   c2g__Transaction__r.c2g__TransactionDate__c, c2g__HomeCurrency__r.Name,
                   c2g__Transaction__r.c2g__Period__r.Name,
                   c2g__Transaction__r.c2g__Period__r.c2g__PeriodNumber__c,
                   c2g__Transaction__r.c2g__Period__r.c2g__YearName__c
            FROM c2g__codaTransactionLineItem__c
            WHERE {company_filter_sql}c2g__Transaction__r.c2g__TransactionDate__c <= {end_str}
                  AND c2g__HomeCurrency__r.Name = 'BGN'
        """
        
        result = self.sf_session.query_all(transaction_line_query)
        transaction_lines = result['records']
        
        # Remove Salesforce metadata attributes
        for record in transaction_lines:
            record.pop('attributes', None)
            if isinstance(record.get('c2g__Transaction__r'), dict):
                record['c2g__Transaction__r'].pop('attributes', None)
        
        data['transaction_lines'] = transaction_lines
        
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
                    SELECT Id, Name, c2g__ReportingCode__c, c2g__Type__c, 
                           c2g__TrialBalance1__c, c2g__TrialBalance2__c
                    FROM {objects_config['general_ledger']}
                    WHERE Id IN ('{gl_ids_str}')
                """
                data['gl_accounts'] = self.query_rest(gl_query, "GL accounts")
            else:
                data['gl_accounts'] = []
        else:
            gl_query = f"""
                SELECT Id, Name, c2g__ReportingCode__c, c2g__Type__c, 
                       c2g__TrialBalance1__c, c2g__TrialBalance2__c
                FROM {objects_config['general_ledger']}
                WHERE c2g__ReportingCode__c != null
            """
            data['gl_accounts'] = self.query_rest(gl_query, "GL accounts")
        
        # Extract Accounts (Customers/Suppliers)
        if 'customers' in sections or 'suppliers' in sections:
            account_query = f"""
                SELECT Id, Name, AccountNumber, Type, BillingStreet, 
                       BillingCity, BillingPostalCode, BillingCountry, Phone,
                       c2g__CODATaxpayerIdentificationNumber__c, Fax, Website,
                       c2g__CODAInvoiceEmail__c, RecordType.Name
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
                    WHERE c2g__StartDate__c <= {end_date.strftime('%Y-%m-%d')}
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