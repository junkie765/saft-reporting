"""
SAFT Reporting UI Module
Windows application for selecting reporting parameters
"""

import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime
import json
import os
import sys
import logging

# Handle both relative and absolute imports
if __name__ == "__main__" and __package__ is None:
    # Running as script, add parent directory to path
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
    from src.salesforce.auth import get_authenticated_client
else:
    # Running as module
    from ..salesforce.auth import get_authenticated_client

logger = logging.getLogger(__name__)


class SaftReportingUI:
    """Windows GUI application for SAFT reporting parameter selection"""
    
    def __init__(self, root, config_path=None):
        self.root = root
        self.root.title("SAFT Reporting - Parameter Selection")
        self.root.state('zoomed')  # Maximize window
        self.root.resizable(True, True)
        
        # Load configuration
        if config_path is None:
            config_path = os.path.join(os.path.dirname(__file__), '..', '..', 'config.json')
        
        with open(config_path, 'r') as f:
            self.config = json.load(f)
        
        # Variables to store user selections
        self.company_var = tk.StringVar()
        self.year_var = tk.StringVar()
        self.month_var = tk.StringVar()
        self.report_type_var = tk.StringVar(value="Monthly")
        self.export_excel_var = tk.BooleanVar(value=True)
        
        # Authenticate once and cache the REST client
        self.rest_client = None
        try:
            self.rest_client = get_authenticated_client(self.config)
            logger.debug("UI: Authenticated with Salesforce")
        except Exception as e:
            logger.error(f"Error authenticating with Salesforce: {e}")
            error_msg = str(e)
            if "401" in error_msg or "Unauthorized" in error_msg:
                messagebox.showerror(
                    "Authentication Error",
                    "Salesforce session has expired.\n\nPlease update the session_id in config.json with a fresh token.\n\nSee OAUTH_SETUP.md for instructions."
                )
        
        # Fetch data from Salesforce using cached client
        self.companies = self._fetch_companies()
        self.years, self.periods_by_year = self._fetch_periods_from_salesforce()
        self.available_periods = []
        
        self._create_widgets()
        self._center_window()
        
    def _center_window(self):
        """Center the window on the screen"""
        self.root.update_idletasks()
        width = self.root.winfo_width()
        height = self.root.winfo_height()
        x = (self.root.winfo_screenwidth() // 2) - (width // 2)
        y = (self.root.winfo_screenheight() // 2) - (height // 2)
        self.root.geometry(f'{width}x{height}+{x}+{y}')
    
    def _fetch_companies(self):
        """Fetch accounting companies from Salesforce"""
        if not self.rest_client:
            return []
        try:
            return self.rest_client.get_companies()
        except Exception as e:
            logger.error(f"Error fetching companies from Salesforce: {e}")
            return []
    
    def _fetch_periods_from_salesforce(self, company_id=None):
        """Fetch years and periods from Salesforce c2g__codaPeriod__c object"""
        if not self.rest_client:
            # Fallback to current year and 1-12 periods
            current_year = str(datetime.now().year)
            return [current_year], {current_year: [{'number': str(i), 'name': str(i)} for i in range(1, 13)]}
        
        try:
            # Fetch periods organized by year, filtered by company if provided
            return self.rest_client.get_periods_by_year(company_id)
            
        except Exception as e:
            logger.error(f"Error fetching periods from Salesforce: {e}")
            # Only show warning if we have companies (avoid duplicate error messages)
            if self.companies:
                messagebox.showwarning(
                    "Warning", 
                    f"Could not fetch periods from Salesforce: {e}\nUsing default values."
                )
            # Fallback to current year and 1-12 periods
            current_year = str(datetime.now().year)
            return [current_year], {current_year: [{'number': str(i), 'name': str(i)} for i in range(1, 13)]}
    
    def _on_company_change(self, event=None):
        """Update years and periods when company is changed"""
        selected_company = self.company_var.get()
        
        # Find company ID from name
        company_id = None
        for company in self.companies:
            if company['name'] == selected_company:
                company_id = company['id']
                break
        
        # Fetch periods for selected company
        self.years, self.periods_by_year = self._fetch_periods_from_salesforce(company_id)
        
        # Update year dropdown and set default
        self.year_combo['values'] = self.years
        if self.years:
            current_year = str(datetime.now().year)
            self.year_combo.set(current_year if current_year in self.years else self.years[-1])
            self._on_year_change()
    
    def _on_report_type_change(self, event=None):
        """Update month field visibility when report type is changed"""
        report_type = self.report_type_var.get()
        
        if report_type == "Annual":
            # Hide month field for Annual reports (shows full year)
            self.month_label.grid_remove()
            self.month_combo.grid_remove()
        else:
            # Show month field for Monthly reports
            self.month_label.grid()
            self.month_combo.grid()
            # Update with appropriate defaults
            self._on_year_change()
    
    def _on_year_change(self, event=None):
        """Update month dropdown when year is changed"""
        selected_year = self.year_var.get()
        report_type = self.report_type_var.get()
        
        if selected_year in self.periods_by_year:
            self.available_periods = self.periods_by_year[selected_year]
            period_numbers = [p['number'] for p in self.available_periods]
            
            # Update Month dropdown
            self.month_combo['values'] = period_numbers
            
            # Set default month based on report type
            if period_numbers and report_type == "Monthly":
                current_year = str(datetime.now().year)
                current_month = datetime.now().month
                
                if selected_year == current_year:
                    # For monthly reports in current year, default to previous month
                    previous_month = current_month - 1 if current_month > 1 else 12
                    # Format as 3-digit string with leading zeros
                    previous_month_str = f"{previous_month:03d}"
                    
                    # Find the period for previous month
                    if previous_month_str in period_numbers:
                        self.month_combo.set(previous_month_str)
                    else:
                        # Fallback to last available period if previous month not found
                        self.month_combo.set(period_numbers[-1])
                else:
                    # For other years, default to December (last period)
                    self.month_combo.set(period_numbers[-1])
        
    def _create_widgets(self):
        """Create and layout all UI widgets"""
        # Configure root grid
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=0)
        self.root.rowconfigure(1, weight=1)
        
        # Main frame with padding (parameters)
        main_frame = ttk.Frame(self.root, padding="20")
        main_frame.grid(row=0, column=0, sticky="nsew")
        
        # Company field - dropdown with Salesforce companies
        ttk.Label(main_frame, text="Company:").grid(row=0, column=0, sticky=tk.W, pady=5)
        company_names = [c['name'] for c in self.companies]
        company_combo = ttk.Combobox(
            main_frame,
            textvariable=self.company_var,
            values=company_names,
            state="readonly",
            width=23
        )
        company_combo.grid(row=0, column=1, sticky="ew", pady=5)
        company_combo.bind('<<ComboboxSelected>>', self._on_company_change)
        
        # Set default company from config or first in list
        default_company = self.config.get('saft', {}).get('company_name', '')
        if default_company and default_company in company_names:
            company_combo.set(default_company)
        elif company_names:
            company_combo.set(company_names[0])
        
        # Year field - dropdown with Salesforce years
        ttk.Label(main_frame, text="Year:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.year_combo = ttk.Combobox(
            main_frame,
            textvariable=self.year_var,
            values=self.years,
            state="readonly",
            width=23
        )
        self.year_combo.grid(row=1, column=1, sticky="ew", pady=5)
        self.year_combo.bind('<<ComboboxSelected>>', self._on_year_change)
        
        # Set default to current year if available
        current_year = str(datetime.now().year)
        if current_year in self.years:
            self.year_combo.set(current_year)
        elif self.years:
            self.year_combo.set(self.years[-1])  # Set to most recent year
        
        # Month field - dropdown with periods from selected year (only for Monthly reports)
        self.month_label = ttk.Label(main_frame, text="Month:")
        self.month_label.grid(row=2, column=0, sticky=tk.W, pady=5)
        self.month_combo = ttk.Combobox(
            main_frame,
            textvariable=self.month_var,
            state="readonly",
            width=23
        )
        self.month_combo.grid(row=2, column=1, sticky="ew", pady=5)
        
        # Report Type picklist
        ttk.Label(main_frame, text="Report Type:").grid(row=3, column=0, sticky=tk.W, pady=5)
        report_type_combo = ttk.Combobox(
            main_frame,
            textvariable=self.report_type_var,
            values=["Annual", "Monthly"],
            state="readonly",
            width=23
        )
        report_type_combo.grid(row=3, column=1, sticky="ew", pady=5)
        report_type_combo.bind('<<ComboboxSelected>>', self._on_report_type_change)
        
        # Export to Excel checkbox
        export_excel_check = ttk.Checkbutton(
            main_frame,
            text="Export to Excel",
            variable=self.export_excel_var
        )
        export_excel_check.grid(row=4, column=0, columnspan=2, sticky=tk.W, pady=10)
        
        # Initialize period dropdowns based on default company and year (must be after combo creation)
        self._on_company_change()
        
        # Buttons frame
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=5, column=0, columnspan=2, pady=20)
        
        # Generate button
        ttk.Button(button_frame, text="Generate Report", command=self._generate_report).grid(row=0, column=0, padx=5)
        
        # Cancel button
        ttk.Button(button_frame, text="Close", command=self.root.quit).grid(row=0, column=1, padx=5)
        
        # Configure grid weight for stretching
        main_frame.columnconfigure(1, weight=1)
        
        # Log panel frame
        log_frame = ttk.LabelFrame(self.root, text="Progress Log", padding="10")
        log_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        
        # Log text widget with scrollbar
        log_scroll = ttk.Scrollbar(log_frame)
        log_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.log_text = tk.Text(
            log_frame,
            wrap=tk.WORD,
            yscrollcommand=log_scroll.set,
            font=('Consolas', 9),
            bg='#1e1e1e',
            fg='#d4d4d4',
            insertbackground='white',
            height=10
        )
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        log_scroll.config(command=self.log_text.yview)
        
        # Configure text tags for colored output
        self.log_text.tag_config('info', foreground='#4ec9b0')
        self.log_text.tag_config('warning', foreground='#dcdcaa')
        self.log_text.tag_config('error', foreground='#f48771')
        self.log_text.tag_config('success', foreground='#b5cea8')
        
        # Progress bar
        self.progress = ttk.Progressbar(self.root, mode='indeterminate')
        self.progress.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 10))
        
        # Initially hide progress bar
        self.progress.grid_remove()
        
    def _validate_inputs(self):
        """Validate user inputs"""
        # Validate company
        company = self.company_var.get()
        if not company:
            messagebox.showerror("Validation Error", "Please select a company.")
            return False
        
        # Validate year
        year = self.year_var.get()
        if not year:
            messagebox.showerror("Validation Error", "Please select a year.")
            return False
        
        # Validate report type
        report_type = self.report_type_var.get()
        
        # Validate month for Monthly reports
        if report_type == "Monthly":
            month = self.month_var.get()
            if not month:
                messagebox.showerror("Validation Error", "Please select a month.")
                return False
            
        return True
        
    def _generate_report(self):
        """Handle report generation"""
        if self._validate_inputs():
            company = self.company_var.get()
            year = self.year_var.get()
            report_type = self.report_type_var.get()
            
            # Determine period range based on report type
            if report_type == "Annual":
                # For annual reports, use full year (first to last period)
                if year in self.periods_by_year:
                    periods = self.periods_by_year[year]
                    period_from = periods[0]['number'] if periods else '001'
                    period_to = periods[-1]['number'] if periods else '012'
                else:
                    period_from = '001'
                    period_to = '012'
            else:
                # For monthly reports, use selected month for both from and to
                month = self.month_var.get()
                period_from = month
                period_to = month
            
            # Find company ID
            company_id = None
            for comp in self.companies:
                if comp['name'] == company:
                    company_id = comp['id']
                    break
            
            # Get date ranges from periods
            start_date = None
            end_date = None
            
            if year in self.periods_by_year:
                for period in self.periods_by_year[year]:
                    if period['number'] == period_from:
                        start_date = period['start_date']
                    if period['number'] == period_to:
                        end_date = period['end_date']
                    # Break early if we found both dates
                    if start_date and end_date:
                        break
            
            # Store selections for later use
            self.selections = {
                'company': company,
                'company_id': company_id,
                'year': year,
                'period_from': period_from,
                'period_to': period_to,
                'report_type': report_type,
                'start_date': start_date,
                'end_date': end_date,
                'export_excel': self.export_excel_var.get()
            }
            
            # Don't close - let main.py handle the UI
            # Just trigger the event loop to continue
            self.root.quit()
    
    def get_selections(self):
        """Return the user's selections"""
        return getattr(self, 'selections', None)
    
    def get_rest_client(self):
        """Return the cached authenticated REST client"""
        return self.rest_client
    
    def log(self, message, level="INFO"):
        """Add log message to the text widget"""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        color_tags = {
            'INFO': 'info',
            'WARNING': 'warning',
            'ERROR': 'error',
            'SUCCESS': 'success'
        }
        
        formatted_message = f"[{timestamp}] {level}: {message}\n"
        self.log_text.insert(tk.END, formatted_message, color_tags.get(level, 'info'))
        self.log_text.see(tk.END)
        self.root.update()
    
    def start_progress(self):
        """Show and start progress bar"""
        self.progress.grid()
        self.progress.start(10)
        self.root.update()
    
    def stop_progress(self):
        """Stop and hide progress bar"""
        self.progress.stop()
        self.progress.grid_remove()
        self.root.update()


def launch_ui(config_path=None):
    """Launch the SAFT Reporting UI
    
    Args:
        config_path: Optional path to config.json file
        
    Returns:
        Dictionary with user selections or None if cancelled
    """
    root = tk.Tk()
    app = SaftReportingUI(root, config_path)
    root.mainloop()
    return app.get_selections()


def launch_ui_with_instance(config_path=None):
    """Launch the SAFT Reporting UI and return both selections and app instance
    
    Args:
        config_path: Optional path to config.json file
        
    Returns:
        Tuple of (selections dict or None, app instance)
    """
    root = tk.Tk()
    app = SaftReportingUI(root, config_path)
    root.mainloop()
    return app.get_selections(), app


if __name__ == "__main__":
    # Run the UI when module is executed directly
    selections = launch_ui()
    if selections:
        print("\nSelected Parameters:")
        for key, value in selections.items():
            print(f"{key}: {value}")
