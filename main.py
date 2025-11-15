"""
Main entry point for SAF-T Bulgaria reporting from Certinia Finance Cloud
"""
import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

from src.salesforce.rest_client import SalesforceRestClient
from src.salesforce.auth import SalesforceAuth
from src.transformers.certinia_transformer import CertiniaTransformer
from src.saft.saft_generator import SAFTGenerator
from src.utils.logger import setup_logger
from src.utils.excel_exporter import ExcelExporter


def load_config(config_path: str = 'config.json') -> dict:
    """
    Load configuration from JSON file
    
    Args:
        config_path: Path to configuration file (default: config.json)
        
    Returns:
        Configuration dictionary
        
    Raises:
        SystemExit: If configuration file not found or invalid JSON
    """
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
    """
    Validate and parse date strings
    
    Args:
        start_date: Start date in YYYY-MM-DD format
        end_date: End date in YYYY-MM-DD format
        
    Returns:
        Tuple of (start_datetime, end_datetime)
        
    Raises:
        SystemExit: If dates are invalid or in wrong format
    """
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
    import time
    
    # Parse arguments
    args = parse_arguments()
    
    # Setup logging
    setup_logger(args.log_level)
    logger = logging.getLogger(__name__)
    
    # Track overall execution time
    total_start_time = time.time()
    
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
        step_start = time.time()
        auth = SalesforceAuth(config['salesforce'])
        sf_session = auth.authenticate()
        step_duration = time.time() - step_start
        logger.info(f"✓ Authentication successful (took {step_duration:.2f}s)")
        
        # Step 2: Initialize REST API client
        logger.info("Step 2: Initializing REST API client...")
        step_start = time.time()
        rest_client = SalesforceRestClient(sf_session, config)
        step_duration = time.time() - step_start
        logger.info(f"✓ REST API client ready (took {step_duration:.2f}s)")
        
        # Step 3: Extract data from Certinia
        logger.info("Step 3: Extracting data from Certinia...")
        if args.company:
            logger.info(f"  Company filter: {args.company}")
        step_start = time.time()
        certinia_data = rest_client.extract_certinia_data(start_date, end_date, args.company)
        step_duration = time.time() - step_start
        logger.info(f"✓ Data extraction complete (took {step_duration:.2f}s)")
        
        # Step 4: Transform data
        logger.info("Step 4: Transforming data for SAF-T format...")
        step_start = time.time()
        # Update config with command-line dates for transformer
        config['saft']['selection_start_date'] = start_date.strftime('%Y-%m-%d')
        config['saft']['selection_end_date'] = end_date.strftime('%Y-%m-%d')
        transformer = CertiniaTransformer(config)
        saft_data = transformer.transform(certinia_data)
        step_duration = time.time() - step_start
        logger.info(f"✓ Data transformation complete (took {step_duration:.2f}s)")
        
        # Step 5: Generate SAF-T XML
        logger.info("Step 5: Generating SAF-T XML file...")
        step_start = time.time()
        generator = SAFTGenerator(config)
        
        # Determine output path
        if args.output:
            output_path = Path(args.output)
        else:
            output_dir = Path(config['output']['directory'])
            output_dir.mkdir(exist_ok=True)
            
            filename = config['output']['filename_pattern'].format(
                company_id=config['saft']['company_id'],
                start_year=start_date.year,
                start_month=start_date.strftime('%m'),
                end_year=end_date.year,
                end_month=end_date.strftime('%m')
            )
            output_path = output_dir / filename
        
        generator.generate(saft_data, output_path, start_date, end_date)
        step_duration = time.time() - step_start
        logger.info(f"✓ SAF-T XML generated: {output_path} (took {step_duration:.2f}s)")
        
        # Step 6: Export to Excel (if requested)
        if args.export_excel:
            logger.info("Step 6: Exporting data to Excel...")
            step_start = time.time()
            excel_exporter = ExcelExporter()
            
            # Determine Excel output path
            output_dir = Path(config['output']['directory'])
            excel_filename = f"Certinia_Data_{config['saft']['company_id']}_{start_date.year}_{start_date.strftime('%m')}_{end_date.year}_{end_date.strftime('%m')}.xlsx"
            excel_path = output_dir / excel_filename
            
            # Export both raw and transformed data
            excel_exporter.export(certinia_data, excel_path, start_date, end_date, saft_data)
            step_duration = time.time() - step_start
            logger.info(f"✓ Excel file generated: {excel_path} (took {step_duration:.2f}s)")
        
        # Calculate total execution time
        total_duration = time.time() - total_start_time
        
        # Summary
        logger.info("=" * 80)
        logger.info("Export completed successfully!")
        logger.info(f"SAF-T XML file: {output_path.absolute()}")
        logger.info(f"File size: {output_path.stat().st_size / 1024:.2f} KB")
        logger.info(f"Total execution time: {total_duration:.2f}s ({total_duration/60:.2f} minutes)")
        logger.info("=" * 80)
        
    except Exception as e:
        logger.error(f"Error during export: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
