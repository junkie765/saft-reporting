"""Excel exporter for Certinia data"""
import logging
import pandas as pd
from pathlib import Path
from typing import Dict, List
from datetime import datetime


logger = logging.getLogger(__name__)


class ExcelExporter:
    """Export extracted Certinia data to Excel file with multiple sheets"""
    
    def __init__(self):
        """Initialize Excel exporter"""
        pass
    
    def _flatten_record(self, record: dict, parent_key: str = '', sep: str = '.') -> dict:
        """
        Flatten nested dictionary structure for DataFrame conversion
        
        Args:
            record: Dictionary with potentially nested structures
            parent_key: Parent key for nested fields
            sep: Separator for nested field names
            
        Returns:
            Flattened dictionary
        """
        items = []
        for k, v in record.items():
            new_key = f"{parent_key}{sep}{k}" if parent_key else k
            
            # Skip Salesforce attributes
            if k == 'attributes':
                continue
                
            if isinstance(v, dict):
                # Recursively flatten nested dicts
                items.extend(self._flatten_record(v, new_key, sep=sep).items())
            else:
                items.append((new_key, v))
        return dict(items)
    
    def _prepare_dataframe(self, records: List[dict], sheet_name: str) -> pd.DataFrame:
        """
        Prepare DataFrame from list of records
        
        Args:
            records: List of record dictionaries
            sheet_name: Name of the sheet (for logging)
            
        Returns:
            pandas DataFrame
        """
        if not records:
            logger.warning(f"No data for sheet: {sheet_name}")
            return pd.DataFrame()
        
        # Flatten all records
        flattened = [self._flatten_record(record) for record in records]
        
        # Create DataFrame
        df = pd.DataFrame(flattened)
        
        logger.info(f"Prepared {len(df)} rows for sheet: {sheet_name}")
        return df
    
    def export(self, data: Dict[str, List], output_path: Path, start_date: datetime, end_date: datetime):
        """
        Export data to Excel file with multiple sheets
        
        Args:
            data: Dictionary containing all extracted data
            output_path: Path for the output Excel file
            start_date: Start date of extraction period
            end_date: End date of extraction period
        """
        logger.info(f"Exporting data to Excel: {output_path}")
        
        # Define sheet mappings (data key -> sheet name)
        sheet_mappings = {
            'company': 'Company Info',
            'journals': 'Journal Entries',
            'journal_lines': 'Journal Lines',
            'sales_invoices': 'Sales Invoices',
            'sales_invoice_lines': 'Sales Invoice Lines',
            'purchase_invoices': 'Purchase Invoices',
            'purchase_invoice_lines': 'Purchase Invoice Lines',
            'payments': 'Cash Entries',
            'payment_lines': 'Cash Entry Lines',
            'transaction_lines': 'Transaction Lines',
            'gl_accounts': 'GL Accounts',
            'accounts': 'Accounts',
            'products': 'Products',
            'tax_codes': 'Tax Codes'
        }
        
        # Create Excel writer
        with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
            # Add summary sheet
            summary_data = {
                'Extraction Date': [datetime.now().strftime('%Y-%m-%d %H:%M:%S')],
                'Period Start': [start_date.strftime('%Y-%m-%d')],
                'Period End': [end_date.strftime('%Y-%m-%d')],
                'Company': [data.get('company', [{}])[0].get('Name', 'N/A') if data.get('company') else 'N/A']
            }
            
            # Add record counts
            for key, sheet_name in sheet_mappings.items():
                if key in data:
                    count = len(data[key]) if isinstance(data[key], list) else 1
                    summary_data[f'{sheet_name} Count'] = [count]
            
            summary_df = pd.DataFrame(summary_data)
            summary_df.to_excel(writer, sheet_name='Summary', index=False)
            logger.info("Added Summary sheet")
            
            # Export each data section to a separate sheet
            for key, sheet_name in sheet_mappings.items():
                if key in data and data[key]:
                    df = self._prepare_dataframe(data[key], sheet_name)
                    
                    if not df.empty:
                        # Truncate sheet name if too long (Excel limit is 31 characters)
                        safe_sheet_name = sheet_name[:31]
                        
                        df.to_excel(writer, sheet_name=safe_sheet_name, index=False)
                        logger.info(f"Added sheet: {safe_sheet_name} ({len(df)} rows)")
        
        logger.info(f"✓ Excel export complete: {output_path}")
