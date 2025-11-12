"""Salesforce Bulk API 2.0 client for large data extraction"""
import logging
import time
import csv
import io
from datetime import datetime
from typing import Dict, List, Any
import requests


logger = logging.getLogger(__name__)


class SalesforceBulkClient:
    """Client for Salesforce Bulk API 2.0"""
    
    def __init__(self, sf_session, config: dict):
        """
        Initialize Bulk API client
        
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
        
        logger.debug(f"Bulk API initialized - Instance: {self.instance_url}, API: v{self.api_version}")
    
    def create_query_job(self, soql_query: str) -> str:
        """
        Create a bulk query job
        
        Args:
            soql_query: SOQL query string
            
        Returns:
            Job ID
        """
        url = f"{self.base_url}/jobs/query"
        
        payload = {
            'operation': 'query',
            'query': soql_query
        }
        
        response = requests.post(url, json=payload, headers=self.headers)
        
        if response.status_code != 200:
            error_detail = response.text
            logger.error(f"Failed to create bulk job. Status: {response.status_code}, Response: {error_detail}")
        
        response.raise_for_status()
        
        job_info = response.json()
        job_id = job_info['id']
        
        logger.info(f"Created bulk job: {job_id}")
        return job_id
    
    def get_job_status(self, job_id: str) -> Dict[str, Any]:
        """
        Get status of a bulk job
        
        Args:
            job_id: Job ID
            
        Returns:
            Job status information
        """
        url = f"{self.base_url}/jobs/query/{job_id}"
        response = requests.get(url, headers=self.headers)
        response.raise_for_status()
        return response.json()
    
    def wait_for_job_completion(self, job_id: str, polling_interval: int = 5, 
                                 timeout: int = 3600) -> Dict[str, Any]:
        """
        Poll job status until completion
        
        Args:
            job_id: Job ID
            polling_interval: Seconds between status checks
            timeout: Maximum wait time in seconds
            
        Returns:
            Final job status
        """
        start_time = time.time()
        
        while True:
            if time.time() - start_time > timeout:
                raise TimeoutError(f"Job {job_id} did not complete within {timeout} seconds")
            
            job_status = self.get_job_status(job_id)
            state = job_status['state']
            
            logger.debug(f"Job {job_id} state: {state}")
            
            if state == 'JobComplete':
                logger.info(f"Job completed. Processed {job_status['numberRecordsProcessed']} records")
                return job_status
            elif state == 'Failed':
                raise Exception(f"Job failed: {job_status.get('errorMessage', 'Unknown error')}")
            elif state == 'Aborted':
                raise Exception(f"Job was aborted")
            
            time.sleep(polling_interval)
    
    def get_job_results(self, job_id: str) -> List[Dict[str, Any]]:
        """
        Get results from completed job
        
        Args:
            job_id: Job ID
            
        Returns:
            List of records
        """
        url = f"{self.base_url}/jobs/query/{job_id}/results"
        
        # Update headers for CSV response
        csv_headers = self.headers.copy()
        csv_headers['Accept'] = 'text/csv'
        
        response = requests.get(url, headers=csv_headers)
        response.raise_for_status()
        
        # Parse CSV response - explicitly decode as UTF-8 to preserve Cyrillic characters
        response.encoding = 'utf-8'
        csv_data = response.text
        reader = csv.DictReader(io.StringIO(csv_data))
        records = list(reader)
        
        logger.info(f"Retrieved {len(records)} records from job {job_id}")
        return records
    
    def query(self, soql_query: str) -> List[Dict[str, Any]]:
        """
        Execute SOQL query using Bulk API 2.0
        
        Args:
            soql_query: SOQL query string
            
        Returns:
            List of records
        """
        job_id = self.create_query_job(soql_query)
        
        polling_interval = self.config['bulk_api']['polling_interval']
        timeout = self.config['bulk_api']['timeout']
        
        self.wait_for_job_completion(job_id, polling_interval, timeout)
        return self.get_job_results(job_id)
    
    def query_rest(self, soql_query: str) -> List[Dict[str, Any]]:
        """
        Execute SOQL query using REST API (supports subqueries)
        
        Args:
            soql_query: SOQL query string
            
        Returns:
            List of records
        """
        import urllib.parse
        
        url = f"{self.base_url}/query"
        params = {'q': soql_query}
        
        all_records = []
        
        while url:
            response = requests.get(url, params=params if params else None, headers=self.headers)
            response.raise_for_status()
            
            result = response.json()
            all_records.extend(result.get('records', []))
            
            # Handle pagination
            url = result.get('nextRecordsUrl')
            if url:
                url = f"{self.instance_url}{url}"
                params = None  # params are in the nextRecordsUrl
        
        logger.info(f"Retrieved {len(all_records)} records via REST API")
        return all_records
    
    def extract_certinia_data(self, start_date: datetime, end_date: datetime, company_filter: str | None = None) -> Dict[str, List]:
        """
        Extract all necessary Certinia data for SAF-T reporting
        
        Args:
            start_date: Start date for extraction
            end_date: End date for extraction
            company_filter: Optional company name to filter data (e.g., "Scalefocus AD")
            
        Returns:
            Dictionary containing all extracted data
        """
        logger.info("Extracting Certinia Finance Cloud data...")
        
        data = {}
        objects_config = self.config['certinia']['objects']
        
        # Format dates for SOQL
        start_str = start_date.strftime('%Y-%m-%d')
        end_str = end_date.strftime('%Y-%m-%d')
        
        # Get company ID if filter is specified
        company_id = None
        if company_filter:
            logger.info(f"Filtering data for company: {company_filter}")
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
            company_result = self.query(company_query)
            if company_result:
                company_id = company_result[0]['Id']
                data['company'] = company_result
                logger.info(f"Found company: {company_filter} (ID: {company_id})")
            else:
                logger.warning(f"Company '{company_filter}' not found, proceeding without filter")
        
        # Build company filter clause for queries
        company_filter_clause = f"AND c2g__OwnerCompany__c = '{company_id}'" if company_id else ""
        
        # Extract Journal Entries
        logger.info("Extracting Journal Entries...")
        journal_query = f"""
            SELECT Id, Name, c2g__JournalDate__c, c2g__Type__c, 
                   c2g__JournalStatus__c, c2g__Reference__c, c2g__Period__r.Name
            FROM {objects_config['journal_entry']}
            WHERE c2g__JournalDate__c >= {start_str} 
              AND c2g__JournalDate__c <= {end_str}
              AND c2g__JournalStatus__c = 'Posted'
              {company_filter_clause}
        """
        data['journals'] = self.query(journal_query)
        
        # Extract Journal Line Items
        logger.info("Extracting Journal Line Items...")
        line_query = f"""
            SELECT Id, Name, c2g__Journal__c, c2g__GeneralLedgerAccount__c,
                   c2g__GeneralLedgerAccount__r.Name, c2g__GeneralLedgerAccount__r.c2g__ReportingCode__c,
                   c2g__LineType__c, c2g__Value__c, c2g__LineDescription__c
            FROM {objects_config['journal_line']}
            WHERE c2g__Journal__r.c2g__JournalDate__c >= {start_str}
              AND c2g__Journal__r.c2g__JournalDate__c <= {end_str}
              AND c2g__Journal__r.c2g__OwnerCompany__c = '{company_id}'
        """ if company_id else f"""
            SELECT Id, Name, c2g__Journal__c, c2g__GeneralLedgerAccount__c,
                   c2g__GeneralLedgerAccount__r.Name, c2g__GeneralLedgerAccount__r.c2g__ReportingCode__c,
                   c2g__LineType__c, c2g__Value__c, c2g__LineDescription__c
            FROM {objects_config['journal_line']}
            WHERE c2g__Journal__r.c2g__JournalDate__c >= {start_str}
              AND c2g__Journal__r.c2g__JournalDate__c <= {end_str}
        """
        data['journal_lines'] = self.query(line_query)
        
        # Extract Transaction Line Items for balance calculations using REST API
        # NOTE: Bulk API has issues with large datasets - using REST API with pagination instead
        logger.info("Extracting Transaction Line Items for balance calculations via REST API...")
        logger.info(f"Extracting transactions up to {end_str} for company {company_filter}")
        
        # Build query with optional company filter
        company_filter_sql = f"c2g__Transaction__r.c2g__OwnerCompany__c = '{company_id}' AND " if company_id else ""
        transaction_line_query = f"""
            SELECT Id, c2g__GeneralLedgerAccount__c, c2g__Account__c, c2g__LineType__c, c2g__HomeValue__c,
                c2g__HomeCredits__c, c2g__HomeDebits__c,
                c2g__Transaction__r.c2g__TransactionDate__c, c2g__HomeCurrency__r.Name
            FROM c2g__codaTransactionLineItem__c
            WHERE {company_filter_sql}c2g__Transaction__r.c2g__TransactionDate__c <= {end_str}
                AND c2g__HomeCurrency__r.Name = 'BGN'
        """
        
        # Use REST API with query_all for pagination
        transaction_lines = []
        result = self.sf_session.query_all(transaction_line_query)
        transaction_lines = result['records']
        
        logger.info(f"Extracted {len(transaction_lines)} transaction lines via REST API")
        
        # Remove Salesforce metadata attributes
        for record in transaction_lines:
            if 'attributes' in record:
                del record['attributes']
            if 'c2g__Transaction__r' in record and isinstance(record['c2g__Transaction__r'], dict):
                if 'attributes' in record['c2g__Transaction__r']:
                    del record['c2g__Transaction__r']['attributes']
        
        data['transaction_lines'] = transaction_lines
        

        
        # Extract General Ledger Accounts - get all GL accounts used in transaction lines
        logger.info("Extracting General Ledger Accounts...")
        if data['transaction_lines']:
            # Get unique GL account IDs from transaction lines
            gl_account_ids = set()
            for line in data['transaction_lines']:
                if line.get('c2g__GeneralLedgerAccount__c'):
                    gl_account_ids.add(line['c2g__GeneralLedgerAccount__c'])
            
            if gl_account_ids:
                # Query GL accounts that were actually used
                gl_ids_str = "','".join(gl_account_ids)
                gl_query = f"""
                    SELECT Id, Name, c2g__ReportingCode__c, c2g__Type__c, 
                           c2g__TrialBalance1__c, c2g__TrialBalance2__c
                    FROM {objects_config['general_ledger']}
                    WHERE Id IN ('{gl_ids_str}')
                """
                data['gl_accounts'] = self.query(gl_query)
                logger.info(f"Extracted {len(data['gl_accounts'])} GL accounts from {len(gl_account_ids)} unique account IDs in transaction lines")
            else:
                data['gl_accounts'] = []
        else:
            # No transaction lines, get all GL accounts
            gl_query = f"""
                SELECT Id, Name, c2g__ReportingCode__c, c2g__Type__c, 
                       c2g__TrialBalance1__c, c2g__TrialBalance2__c
                FROM {objects_config['general_ledger']}
                WHERE c2g__ReportingCode__c != null
            """
            data['gl_accounts'] = self.query(gl_query)
        
        # Extract Accounts (Customers/Suppliers)
        logger.info("Extracting Accounts...")
        account_query = f"""
            SELECT Id, Name, AccountNumber, Type, BillingStreet, 
                   BillingCity, BillingPostalCode, BillingCountry, Phone,
                   c2g__CODATaxpayerIdentificationNumber__c, Fax, Website,
                   c2g__CODAInvoiceEmail__c
            FROM {objects_config['account']}
            WHERE (Type != 'Prospect' AND Type != 'Scaleup' AND Type != '')
        """
        data['accounts'] = self.query(account_query)
        
        # Extract Tax Codes with Rates via REST API (supports subqueries)
        logger.info("Extracting Tax Codes and Rates via REST API...")
        tax_code_query = f"""
            SELECT Id, Name, c2g__Description__c,
                   (SELECT c2g__Rate__c, c2g__StartDate__c 
                    FROM c2g__TaxRates__r 
                    WHERE c2g__StartDate__c <= {end_date.strftime('%Y-%m-%d')}
                    ORDER BY c2g__StartDate__c DESC
                    LIMIT 1)
            FROM c2g__codaTaxCode__c
        """
        data['tax_codes'] = self.query_rest(tax_code_query)
        
        # Extract Company Information (if not already extracted by filter)
        if 'company' not in data:
            logger.info("Extracting Company Information...")
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
            data['company'] = self.query(company_query)
        
        logger.info("Data extraction complete")
        return data
