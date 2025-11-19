"""Excel exporter for Certinia data"""
import logging
import pandas as pd
from pathlib import Path
from typing import Dict, List
from datetime import datetime


logger = logging.getLogger(__name__)


class ExcelExporter:
    """Export extracted Certinia data to Excel file with multiple sheets"""
    
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
        Prepare DataFrame from list of records with memory-efficient processing
        
        Args:
            records: List of record dictionaries
            sheet_name: Name of the sheet (for logging)
            
        Returns:
            pandas DataFrame
        """
        if not records:
            logger.warning(f"No data for sheet: {sheet_name}")
            return pd.DataFrame()
        
        # Process in chunks if dataset is large (> 10,000 records)
        chunk_size = 10000
        if len(records) > chunk_size:
            logger.info(f"Processing {len(records)} records in chunks for {sheet_name}...")
            dfs = []
            for i in range(0, len(records), chunk_size):
                chunk = records[i:i + chunk_size]
                flattened = [self._flatten_record(record) for record in chunk]
                dfs.append(pd.DataFrame(flattened))
            df = pd.concat(dfs, ignore_index=True)
        else:
            # Flatten all records
            flattened = [self._flatten_record(record) for record in records]
            df = pd.DataFrame(flattened)
        
        logger.info(f"Prepared {len(df)} rows for sheet: {sheet_name}")
        return df
    
    def _prepare_hierarchical_data(self, records: List[dict], child_key: str, sheet_name: str) -> pd.DataFrame:
        """
        Prepare DataFrame from hierarchical data (parent records with child lists)
        Each child record becomes a row with parent information prefixed
        
        Args:
            records: List of parent record dictionaries
            child_key: Key in parent dict that contains list of child records
            sheet_name: Name of the sheet (for logging)
            
        Returns:
            pandas DataFrame with parent-child data flattened into rows
        """
        if not records:
            logger.warning(f"No data for sheet: {sheet_name}")
            return pd.DataFrame()
        
        rows = []
        
        for parent in records:
            # Extract child records
            children = parent.get(child_key, [])
            
            # Create a copy of parent without the children
            parent_data = {k: v for k, v in parent.items() if k != child_key}
            
            if not children:
                # If no children, still output parent as one row
                flat_parent = self._flatten_record(parent_data)
                flat_parent['_row_type'] = 'PARENT'
                rows.append(flat_parent)
            else:
                # For each child, create a row with parent data
                for idx, child in enumerate(children):
                    flat_child = self._flatten_record(child)
                    flat_parent = self._flatten_record(parent_data)
                    
                    # Combine parent and child data
                    combined = {}
                    
                    # Add row type indicator
                    combined['_row_type'] = 'HEADER' if idx == 0 else 'LINE'
                    
                    # Add parent fields with prefix
                    for key, value in flat_parent.items():
                        combined[f'HEADER_{key}'] = value
                    
                    # Add child fields with indentation prefix
                    for key, value in flat_child.items():
                        combined[f'  LINE_{key}'] = value
                    
                    rows.append(combined)
        
        if not rows:
            return pd.DataFrame()
        
        df = pd.DataFrame(rows)
        
        # Reorder columns: _row_type first, then HEADER_ columns, then LINE_ columns
        cols = df.columns.tolist()
        row_type_cols = ['_row_type'] if '_row_type' in cols else []
        header_cols = sorted(c for c in cols if c.startswith('HEADER_'))
        line_cols = sorted(c for c in cols if c.startswith('  LINE_'))
        used_cols = set(row_type_cols + header_cols + line_cols)
        other_cols = [c for c in cols if c not in used_cols]
        
        df = df[row_type_cols + header_cols + line_cols + other_cols]
        
        logger.info(f"Prepared {len(df)} rows for hierarchical sheet: {sheet_name}")
        return df
    
    def export(self, data: Dict[str, List], output_path: Path, start_date: datetime, end_date: datetime, saft_data: Dict | None = None):
        """
        Export data to Excel file with multiple sheets
        
        Args:
            data: Dictionary containing all extracted data (raw data)
            output_path: Path for the output Excel file
            start_date: Start date of extraction period
            end_date: End date of extraction period
            saft_data: Optional transformed/calculated SAF-T data
        """
        logger.info(f"Exporting data to Excel: {output_path}")
        
        # Create Excel writer
        with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
            # Add summary sheet
            summary_data = {
                'Extraction Date': [datetime.now().strftime('%Y-%m-%d %H:%M:%S')],
                'Period Start': [start_date.strftime('%Y-%m-%d')],
                'Period End': [end_date.strftime('%Y-%m-%d')],
                'Company': [data.get('company', [{}])[0].get('Name', 'N/A') if data.get('company') else 'N/A']
            }
            
            summary_df = pd.DataFrame(summary_data)
            summary_df.to_excel(writer, sheet_name='Summary', index=False)
            logger.info("Added Summary sheet")
            
            # Export transformed SAF-T data if provided
            if saft_data:
                logger.info("Exporting transformed SAF-T data...")
                
                # Export master files (flat structure)
                if 'master_files' in saft_data:
                    master_mappings = {
                        'general_ledger_accounts': 'SAFT - GL Accounts',
                        'customers': 'SAFT - Customers',
                        'suppliers': 'SAFT - Suppliers',
                        'products': 'SAFT - Products',
                        'tax_table': 'SAFT - Tax Codes'
                    }
                    
                    for key, sheet_name in master_mappings.items():
                        if key in saft_data['master_files'] and saft_data['master_files'][key]:
                            records = saft_data['master_files'][key]
                            
                            # Filter out zero-balance accounts for GL, customers, and suppliers
                            if key in ['general_ledger_accounts', 'customers', 'suppliers']:
                                original_count = len(records)
                                records = [
                                    rec for rec in records
                                    if (rec.get('opening_debit_balance', 0.0) + rec.get('opening_credit_balance', 0.0) +
                                        rec.get('closing_debit_balance', 0.0) + rec.get('closing_credit_balance', 0.0)) != 0.0
                                ]
                                if original_count > len(records):
                                    logger.info(f"Filtered {original_count - len(records)} zero-balance records from {sheet_name}")
                            
                            df = self._prepare_dataframe(records, sheet_name)
                            if not df.empty:
                                safe_sheet_name = sheet_name[:31]
                                df.to_excel(writer, sheet_name=safe_sheet_name, index=False)
                                logger.info(f"Added sheet: {safe_sheet_name} ({len(df)} rows)")
                
                # Export source documents with parent-child structure
                if 'source_documents' in saft_data:
                    # Sales Invoices
                    if 'sales_invoices' in saft_data['source_documents']:
                        df = self._prepare_hierarchical_data(
                            saft_data['source_documents']['sales_invoices'],
                            'lines',
                            'SAFT - Sales Invoices'
                        )
                        if not df.empty:
                            df.to_excel(writer, sheet_name='SAFT - Sales Invoices', index=False)
                            logger.info(f"Added sheet: SAFT - Sales Invoices ({len(df)} rows)")
                    
                    # Purchase Invoices
                    if 'purchase_invoices' in saft_data['source_documents']:
                        df = self._prepare_hierarchical_data(
                            saft_data['source_documents']['purchase_invoices'],
                            'lines',
                            'SAFT - Purchase Invoices'
                        )
                        if not df.empty:
                            df.to_excel(writer, sheet_name='SAFT - Purch Invoices', index=False)
                            logger.info(f"Added sheet: SAFT - Purch Invoices ({len(df)} rows)")
                    
                    # Payments
                    if 'payments' in saft_data['source_documents']:
                        df = self._prepare_hierarchical_data(
                            saft_data['source_documents']['payments'],
                            'lines',
                            'SAFT - Payments'
                        )
                        if not df.empty:
                            df.to_excel(writer, sheet_name='SAFT - Payments', index=False)
                            logger.info(f"Added sheet: SAFT - Payments ({len(df)} rows)")
                
                # Export GL entries with transaction-line structure
                if 'general_ledger_entries' in saft_data and saft_data['general_ledger_entries']:
                    df = self._prepare_hierarchical_data(
                        saft_data['general_ledger_entries'],
                        'lines',
                        'SAFT - GL Entries'
                    )
                    if not df.empty:
                        df.to_excel(writer, sheet_name='SAFT - GL Entries', index=False)
                        logger.info(f"Added sheet: SAFT - GL Entries ({len(df)} rows)")
        
        logger.info(f"✓ Excel export complete: {output_path}")
