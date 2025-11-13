"""
Main entry point for SAF-T Bulgaria reporting from Certinia Finance Cloud
"""
import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

from src.salesforce.bulk_client import SalesforceBulkClient
from src.salesforce.auth import SalesforceAuth
from src.transformers.certinia_transformer import CertiniaTransformer
from src.saft.saft_generator import SAFTGenerator
from src.utils.logger import setup_logger
from src.utils.excel_exporter import ExcelExporter


def load_config(config_path: str = 'config.json') -> dict:
    """Load configuration from JSON file"""
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        logging.error(f"Configuration file not found: {config_path}")
        logging.error("Please copy config.example.json to config.json and update with your settings")
        sys.exit(1)
    except json.JSONDecodeError as e:
        logging.error(f"Invalid JSON in configuration file: {e}")
        sys.exit(1)


def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description='Extract Certinia Finance data and generate SAF-T XML for Bulgaria'
    )
    parser.add_argument(
        '--start-date',
        type=str,
        required=True,
        help='Start date for data extraction (YYYY-MM-DD)'
    )
    parser.add_argument(
        '--end-date',
        type=str,
        required=True,
        help='End date for data extraction (YYYY-MM-DD)'
    )
    parser.add_argument(
        '--company',
        type=str,
        default=None,
        help='Company name to filter data (e.g., "Scalefocus AD")'
    )
    parser.add_argument(
        '--config',
        type=str,
        default='config.json',
        help='Path to configuration file (default: config.json)'
    )
    parser.add_argument(
        '--output',
        type=str,
        help='Output file path (overrides config)'
    )
    parser.add_argument(
        '--log-level',
        type=str,
        default='INFO',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        help='Logging level (default: INFO)'
    )
    parser.add_argument(
        '--export-excel',
        action='store_true',
        help='Export extracted data to Excel file with separate sheets for each section'
    )
    
    return parser.parse_args()


def validate_dates(start_date: str, end_date: str) -> tuple:
    """Validate and parse date strings"""
    try:
        start = datetime.strptime(start_date, '%Y-%m-%d')
        end = datetime.strptime(end_date, '%Y-%m-%d')
        
        if start > end:
            raise ValueError("Start date must be before end date")
        
        return start, end
    except ValueError as e:
        logging.error(f"Invalid date format: {e}")
        logging.error("Please use YYYY-MM-DD format")
        sys.exit(1)


def main():
    """Main execution function"""
    # Parse arguments
    args = parse_arguments()
    
    # Setup logging
    setup_logger(args.log_level)
    logger = logging.getLogger(__name__)
    
    logger.info("=" * 80)
    logger.info("SAF-T Bulgaria Export - Certinia Finance Cloud")
    logger.info("=" * 80)
    
    # Load configuration
    logger.info(f"Loading configuration from {args.config}")
    config = load_config(args.config)
    
    # Validate dates
    start_date, end_date = validate_dates(args.start_date, args.end_date)
    logger.info(f"Data extraction period: {start_date.date()} to {end_date.date()}")
    
    try:
        # Step 1: Authenticate with Salesforce
        logger.info("Step 1: Authenticating with Salesforce...")
        auth = SalesforceAuth(config['salesforce'])
        sf_session = auth.authenticate()
        logger.info("✓ Authentication successful")
        
        # Step 2: Initialize Bulk API client
        logger.info("Step 2: Initializing Bulk API 2.0 client...")
        bulk_client = SalesforceBulkClient(sf_session, config)
        logger.info("✓ Bulk API client ready")
        
        # Step 3: Extract data from Certinia
        logger.info("Step 3: Extracting data from Certinia Finance Cloud...")
        if args.company:
            logger.info(f"Filtering data for company: {args.company}")
        certinia_data = bulk_client.extract_certinia_data(start_date, end_date, args.company)
        logger.info(f"✓ Extracted {len(certinia_data.get('journals', []))} transactions")
        
        # Optional: Export raw data to Excel
        if args.export_excel:
            logger.info("Step 3a: Exporting raw data to Excel...")
            excel_exporter = ExcelExporter()
            
            # Determine Excel output path
            output_dir = Path(config['output']['directory'])
            output_dir.mkdir(exist_ok=True)
            
            excel_filename = f"Certinia_Data_{config['saft']['company_id']}_{start_date.year}_{start_date.strftime('%m')}.xlsx"
            excel_path = output_dir / excel_filename
            
            excel_exporter.export(certinia_data, excel_path, start_date, end_date)
            logger.info(f"✓ Excel export complete: {excel_path}")
        
        # Step 4: Transform data
        logger.info("Step 4: Transforming data for SAF-T format...")
        transformer = CertiniaTransformer(config)
        saft_data = transformer.transform(certinia_data)
        logger.info("✓ Data transformation complete")
        
        # Step 5: Generate SAF-T XML
        logger.info("Step 5: Generating SAF-T XML file...")
        generator = SAFTGenerator(config)
        
        # Determine output path
        if args.output:
            output_path = Path(args.output)
        else:
            output_dir = Path(config['output']['directory'])
            output_dir.mkdir(exist_ok=True)
            
            filename = config['output']['filename_pattern'].format(
                company_id=config['saft']['company_id'],
                year=start_date.year,
                month=start_date.strftime('%m')
            )
            output_path = output_dir / filename
        
        generator.generate(saft_data, output_path, start_date, end_date)
        logger.info(f"✓ SAF-T XML generated: {output_path}")
        
        # Summary
        logger.info("=" * 80)
        logger.info("Export completed successfully!")
        logger.info(f"Output file: {output_path.absolute()}")
        logger.info(f"File size: {output_path.stat().st_size / 1024:.2f} KB")
        logger.info("=" * 80)
        
    except Exception as e:
        logger.error(f"Error during export: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
