"""
Main entry point for SAF-T Bulgaria reporting from Certinia Finance Cloud
"""
import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

from src.transformers.certinia_transformer import CertiniaTransformer
from src.saft.saft_generator import SAFTGenerator
from src.utils.logger import setup_logger
from src.utils.excel_exporter import ExcelExporter


def load_config(config_path: str = 'config.json') -> dict:
    """
    Load configuration from JSON file with validation
    
    Args:
        config_path: Path to configuration file (default: config.json)
        
    Returns:
        Configuration dictionary
        
    Raises:
        SystemExit: If configuration file not found or invalid JSON
    """
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        # Validate required config sections
        required_sections = ['salesforce', 'saft', 'certinia', 'output']
        missing_sections = [s for s in required_sections if s not in config]
        if missing_sections:
            logging.error(f"Missing required config sections: {', '.join(missing_sections)}")
            sys.exit(1)
        
        return config
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
    if not start_date or not end_date:
        logging.error("Start date and end date are required")
        sys.exit(1)
    
    try:
        start = datetime.strptime(start_date, '%Y-%m-%d')
        end = datetime.strptime(end_date, '%Y-%m-%d')
        
        if start > end:
            raise ValueError(f"Start date ({start_date}) must be before end date ({end_date})")
        
        # Warn if date range is very large (> 5 years)
        days_diff = (end - start).days
        if days_diff > 1825:  # ~5 years
            logging.warning(f"Large date range detected: {days_diff} days. This may take a while to process.")
        
        return start, end
    except ValueError as e:
        logging.error(f"Invalid date: {e}")
        logging.error(f"Please use YYYY-MM-DD format. Got: start={start_date}, end={end_date}")
        sys.exit(1)


def build_output_filename(config: dict, start_date: datetime, end_date: datetime, extension: str = 'xml', prefix: str = '') -> str:
    """
    Build output filename using consistent pattern
    
    Args:
        config: Configuration dictionary
        start_date: Start date
        end_date: End date
        extension: File extension without dot (default: 'xml')
        prefix: Optional prefix for filename (default: '')
        
    Returns:
        Formatted filename string
    """
    company_id = config['saft']['company_id']
    date_parts = f"{start_date.year}_{start_date.strftime('%m')}_{end_date.year}_{end_date.strftime('%m')}"
    
    if extension == 'xml':
        # Use pattern from config for XML files
        return config['output']['filename_pattern'].format(
            company_id=company_id,
            start_year=start_date.year,
            start_month=start_date.strftime('%m'),
            end_year=end_date.year,
            end_month=end_date.strftime('%m')
        )
    else:
        # Use consistent pattern for other file types
        base_name = f"{prefix}{company_id}_{date_parts}" if prefix else f"{company_id}_{date_parts}"
        return f"{base_name}.{extension}"


class UILogHandler(logging.Handler):
    """Custom logging handler that sends logs to UI window"""
    def __init__(self, ui_app):
        super().__init__()
        self.ui_app = ui_app
        
    def emit(self, record):
        try:
            msg = self.format(record)
            level = record.levelname
            # Remove timestamp from message since UI adds it
            if ' - ' in msg:
                parts = msg.split(' - ', 2)
                if len(parts) >= 3:
                    msg = parts[2]
            self.ui_app.log(msg, level)
        except Exception:
            self.handleError(record)


def main():
    """Main execution function"""
    import time
    from src.ui.saft_ui import launch_ui_with_instance
    
    # Parse arguments
    args = parse_arguments()
    
    # Load configuration first (needed for UI)
    config = load_config(args.config)
    
    # Launch UI for parameter selection and get both selections and UI instance
    selections, ui_app = launch_ui_with_instance(args.config)
    
    if not selections:
        sys.exit(0)
    
    # Setup logging once (file handler and UI handler)
    setup_logger(args.log_level, use_console=False)
    logger = logging.getLogger(__name__)
    
    # Add UI handler to root logger
    ui_handler = UILogHandler(ui_app)
    ui_handler.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    ui_handler.setFormatter(formatter)
    logging.getLogger().addHandler(ui_handler)
    
    # Main loop to allow multiple report generations
    while True:
        # Wait for user to click Generate button
        if not ui_app.selections_ready:
            break
        
        # Start progress bar
        ui_app.start_progress()
        
        # Track overall execution time
        total_start_time = time.time()
        
        logger.info("=" * 80)
        logger.info("SAF-T Bulgaria Export - Certinia Finance Cloud")
        logger.info("=" * 80)
        
        # Validate dates (still needed for XML generation)
        start_date, end_date = validate_dates(selections['start_date'], selections['end_date'])
        
        # Format period display based on report type
        period_display = f"{selections['period_from']}-{selections['period_to']}" if selections['report_type'] == "Annual" else selections['period_from']
        
        logger.info(f"UI selections: Company={selections['company']}, Year={selections['year']}, Period={period_display}, Type={selections['report_type']}")
        logger.info(f"Date range (for display): {start_date.date()} to {end_date.date()}")
        logger.info(f"Company filter: {selections['company']}")
        
        try:
            # Step 1: Reuse authenticated REST client from UI (already authenticated)
            logger.info("Step 1: Using cached Salesforce authentication from UI...")
            step_start = time.time()
            rest_client = ui_app.get_rest_client()
            if not rest_client:
                logger.error("No authenticated REST client available from UI")
                raise Exception("Authentication failed - please check your Salesforce credentials")
            step_duration = time.time() - step_start
            logger.info(f"✓ Using cached authentication (took {step_duration:.2f}s)")
            
            # Step 2: Extract data from Certinia
            logger.info("Step 2: Extracting data from Certinia...")
            logger.info(f"Note: GL Journals filtered by PERIOD ({selections['year']} periods {selections['period_from']}-{selections['period_to']})")
            logger.info(f"Note: Other documents filtered by DOCUMENT DATE ({start_date.date()} to {end_date.date()})")
            step_start = time.time()
            certinia_data = rest_client.extract_certinia_data(selections['year'], selections['period_from'], selections['period_to'], start_date, end_date, selections['company'])
            step_duration = time.time() - step_start
            logger.info(f"✓ Data extraction complete (took {step_duration:.2f}s)")
            
            # Step 3: Transform data
            logger.info("Step 3: Transforming data for SAF-T format...")
            step_start = time.time()
            # Update config with command-line dates for transformer
            config['saft']['selection_start_date'] = start_date.strftime('%Y-%m-%d')
            config['saft']['selection_end_date'] = end_date.strftime('%Y-%m-%d')
            # Map report type to header comment: Monthly -> M, Annual -> A
            config['saft']['header_comment'] = 'M' if selections['report_type'] == 'Monthly' else 'A'
            transformer = CertiniaTransformer(config)
            saft_data = transformer.transform(certinia_data)
            step_duration = time.time() - step_start
            logger.info(f"✓ Data transformation complete (took {step_duration:.2f}s)")
            
            # Step 4: Generate SAF-T XML
            logger.info("Step 4: Generating SAF-T XML file...")
            step_start = time.time()
            generator = SAFTGenerator(config)
            
            # Determine output path
            if args.output:
                output_path = Path(args.output)
            else:
                output_dir = Path(config['output']['directory'])
                output_dir.mkdir(exist_ok=True)
                output_path = output_dir / build_output_filename(config, start_date, end_date, 'xml')
            
            generator.generate(saft_data, output_path, start_date, end_date)
            step_duration = time.time() - step_start
            logger.info(f"✓ SAF-T XML generated: {output_path} (took {step_duration:.2f}s)")
            
            # Step 5: Export to Excel (if requested)
            if selections.get('export_excel', False):
                logger.info("Step 5: Exporting data to Excel...")
                step_start = time.time()
                excel_exporter = ExcelExporter()
                output_dir = Path(config['output']['directory'])
                excel_path = output_dir / build_output_filename(config, start_date, end_date, 'xlsx', 'Certinia_Data_')
                
                # Export both raw and transformed data
                excel_exporter.export(certinia_data, excel_path, start_date, end_date, saft_data)
                step_duration = time.time() - step_start
                logger.info(f"✓ Excel file generated: {excel_path} (took {step_duration:.2f}s)")
            
            # Calculate total execution time
            total_duration = time.time() - total_start_time
            minutes = int(total_duration // 60)
            seconds = int(total_duration % 60)
            
            # Summary
            logger.info("=" * 80)
            logger.info("Export completed successfully!", extra={'level': 'SUCCESS'})
            logger.info(f"SAF-T XML file: {output_path.absolute()}")
            logger.info(f"File size: {output_path.stat().st_size / 1024:.2f} KB")
            logger.info(f"Total execution time: {total_duration:.2f}s ({minutes} minutes and {seconds} seconds)")
            logger.info("=" * 80)
            
            # Stop progress, re-enable inputs, and reset flag for next report
            ui_app.stop_progress()
            ui_app._enable_inputs()
            ui_app.selections_ready = False
            ui_app.log("Process completed successfully. You can generate another report or close this window.", "SUCCESS")
            
            # Wait for next report generation
            ui_app.root.mainloop()
            
            # Check if user clicked Generate again or closed window
            if not ui_app.selections_ready:
                break
            
            # Get new selections
            selections = ui_app.get_selections()
            if not selections:
                break
            
        except Exception as e:
            logger.error(f"Error during export: {e}", exc_info=True)
            ui_app.stop_progress()
            ui_app._enable_inputs()
            ui_app.selections_ready = False
            ui_app.log("Process failed. Check the log for details.", "ERROR")
            
            # Wait for next report generation
            ui_app.root.mainloop()
            
            # Check if user clicked Generate again or closed window
            if not ui_app.selections_ready:
                break
            
            # Get new selections for retry
            selections = ui_app.get_selections()
            if not selections:
                break


if __name__ == '__main__':
    main()
