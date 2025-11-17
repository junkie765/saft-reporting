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


class ProgressWindow:
    """Progress window with log display for report generation"""
    
    def __init__(self, root):
        self.root = root
        self.root.title("SAFT Report Generation - Progress")
        self.root.geometry("800x600")
        self.root.resizable(True, True)
        
        # Main frame
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky="nsew")
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        
        # Log text widget with scrollbar
        log_frame = ttk.Frame(main_frame)
        log_frame.grid(row=0, column=0, sticky="nsew", pady=(0, 10))
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(0, weight=1)
        
        scrollbar = ttk.Scrollbar(log_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.log_text = tk.Text(
            log_frame,
            wrap=tk.WORD,
            yscrollcommand=scrollbar.set,
            font=('Consolas', 9),
            bg='#1e1e1e',
            fg='#d4d4d4',
            insertbackground='white'
        )
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.log_text.yview)
        
        # Progress bar
        self.progress = ttk.Progressbar(main_frame, mode='indeterminate')
        self.progress.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        
        # Status label
        self.status_label = ttk.Label(main_frame, text="Initializing...")
        self.status_label.grid(row=2, column=0, sticky="w")
        
        # Close button (initially disabled)
        self.close_btn = ttk.Button(
            main_frame,
            text="Close",
            command=self.root.destroy,
            state="disabled"
        )
        self.close_btn.grid(row=3, column=0, pady=(10, 0))
        
        self.is_complete = False
        
    def log(self, message, level="INFO"):
        """Add log message to the text widget"""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        color_tags = {
            'INFO': 'info',
            'WARNING': 'warning',
            'ERROR': 'error',
            'SUCCESS': 'success'
        }
        
        # Configure tags if not already done
        if not hasattr(self, '_tags_configured'):
            self.log_text.tag_config('info', foreground='#4ec9b0')
            self.log_text.tag_config('warning', foreground='#dcdcaa')
            self.log_text.tag_config('error', foreground='#f48771')
            self.log_text.tag_config('success', foreground='#b5cea8')
            self._tags_configured = True
        
        formatted_message = f"[{timestamp}] {level}: {message}\n"
        self.log_text.insert(tk.END, formatted_message, color_tags.get(level, 'info'))
        self.log_text.see(tk.END)
        self.root.update()
        
    def update_status(self, status):
        """Update status label"""
        self.status_label.config(text=status)
        self.root.update()
        
    def start_progress(self):
        """Start progress bar animation"""
        self.progress.start(10)
        
    def stop_progress(self):
        """Stop progress bar animation"""
        self.progress.stop()
        
    def complete(self, success=True):
        """Mark operation as complete"""
        self.is_complete = True
        self.stop_progress()
        self.close_btn.config(state="normal")
        if success:
            self.update_status("✓ Report generation completed successfully!")
        else:
            self.update_status("✗ Report generation failed.")


class SaftReportingUI:
    """Windows GUI application for SAFT reporting parameter selection"""
    
    def __init__(self, root, config_path=None):
        self.root = root
        self.root.title("SAFT Reporting - Parameter Selection")
        self.root.geometry("900x450")
        self.root.resizable(True, True)
        
        # Load configuration
        if config_path is None:
            config_path = os.path.join(os.path.dirname(__file__), '..', '..', 'config.json')
        
        with open(config_path, 'r') as f:
            self.config = json.load(f)
        
        # Variables to store user selections
        self.company_var = tk.StringVar()
        self.year_var = tk.StringVar()
        self.period_from_var = tk.StringVar()
        self.period_to_var = tk.StringVar()
        self.report_type_var = tk.StringVar(value="Monthly")
        self.export_excel_var = tk.BooleanVar(value=True)
        
        # Fetch data from Salesforce
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
        try:
            rest_client = get_authenticated_client(self.config)
            return rest_client.get_companies()
        except Exception as e:
            logger.error(f"Error fetching companies from Salesforce: {e}")
            error_msg = str(e)
            if "401" in error_msg or "Unauthorized" in error_msg:
                messagebox.showerror(
                    "Authentication Error",
                    "Salesforce session has expired.\n\nPlease update the session_id in config.json with a fresh token.\n\nSee OAUTH_SETUP.md for instructions."
                )
            return []
    
    def _fetch_periods_from_salesforce(self, company_id=None):
        """Fetch years and periods from Salesforce c2g__codaPeriod__c object"""
        try:
            # Get authenticated REST client
            rest_client = get_authenticated_client(self.config)
            
            # Fetch periods organized by year, filtered by company if provided
            return rest_client.get_periods_by_year(company_id)
            
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
        
        # Update year dropdown
        self.year_combo['values'] = self.years
        if self.years:
            current_year = str(datetime.now().year)
            if current_year in self.years:
                self.year_combo.set(current_year)
            else:
                self.year_combo.set(self.years[-1])
        
        # Trigger year change to update periods
        self._on_year_change()
    
    def _on_year_change(self, event=None):
        """Update period dropdowns when year is changed"""
        selected_year = self.year_var.get()
        
        if selected_year in self.periods_by_year:
            self.available_periods = self.periods_by_year[selected_year]
            period_numbers = [p['number'] for p in self.available_periods]
            
            # Update Period From dropdown
            self.period_from_combo['values'] = period_numbers
            if period_numbers:
                self.period_from_combo.set(period_numbers[0])
            
            # Update Period To dropdown
            self.period_to_combo['values'] = period_numbers
            if period_numbers:
                self.period_to_combo.set(period_numbers[-1])
        
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
        
        # Period From field - dropdown with periods from selected year
        ttk.Label(main_frame, text="Period From:").grid(row=2, column=0, sticky=tk.W, pady=5)
        self.period_from_combo = ttk.Combobox(
            main_frame,
            textvariable=self.period_from_var,
            state="readonly",
            width=23
        )
        self.period_from_combo.grid(row=2, column=1, sticky="ew", pady=5)
        
        # Period To field - dropdown with periods from selected year
        ttk.Label(main_frame, text="Period To:").grid(row=3, column=0, sticky=tk.W, pady=5)
        self.period_to_combo = ttk.Combobox(
            main_frame,
            textvariable=self.period_to_var,
            state="readonly",
            width=23
        )
        self.period_to_combo.grid(row=3, column=1, sticky="ew", pady=5)
        
        # Report Type picklist
        ttk.Label(main_frame, text="Report Type:").grid(row=4, column=0, sticky=tk.W, pady=5)
        report_type_combo = ttk.Combobox(
            main_frame,
            textvariable=self.report_type_var,
            values=["Annual", "Monthly"],
            state="readonly",
            width=23
        )
        report_type_combo.grid(row=4, column=1, sticky="ew", pady=5)
        
        # Export to Excel checkbox
        export_excel_check = ttk.Checkbutton(
            main_frame,
            text="Export to Excel",
            variable=self.export_excel_var
        )
        export_excel_check.grid(row=5, column=0, columnspan=2, sticky=tk.W, pady=10)
        
        # Initialize period dropdowns based on default company and year (must be after combo creation)
        self._on_company_change()
        
        # Buttons frame
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=6, column=0, columnspan=2, pady=20)
        
        # Generate button
        generate_btn = ttk.Button(
            button_frame,
            text="Generate Report",
            command=self._generate_report
        )
        generate_btn.grid(row=0, column=0, padx=5)
        
        # Cancel button
        cancel_btn = ttk.Button(
            button_frame,
            text="Close",
            command=self.root.quit
        )
        cancel_btn.grid(row=0, column=1, padx=5)
        
        # Configure grid weights
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
            
        # Validate periods
        period_from = self.period_from_var.get()
        period_to = self.period_to_var.get()
        
        if not period_from:
            messagebox.showerror("Validation Error", "Please select Period From.")
            return False
            
        if not period_to:
            messagebox.showerror("Validation Error", "Please select Period To.")
            return False
        
        # Check that Period From <= Period To
        try:
            from_num = int(period_from)
            to_num = int(period_to)
            
            if from_num > to_num:
                messagebox.showerror("Validation Error", "Period From cannot be greater than Period To.")
                return False
        except ValueError:
            # If periods are not numeric, skip the comparison
            pass
            
        return True
        
    def _generate_report(self):
        """Handle report generation"""
        if self._validate_inputs():
            company = self.company_var.get()
            year = self.year_var.get()
            period_from = self.period_from_var.get()
            period_to = self.period_to_var.get()
            report_type = self.report_type_var.get()
            
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
                    if period['number'] == period_from and not start_date:
                        start_date = period['start_date']
                    if period['number'] == period_to:
                        end_date = period['end_date']
            
            # Display selected parameters
            message = f"Report Parameters:\n\n"
            message += f"Company: {company}\n"
            message += f"Year: {year}\n"
            message += f"Period From: {period_from}\n"
            message += f"Period To: {period_to}\n"
            message += f"Report Type: {report_type}\n"
            if start_date and end_date:
                message += f"Date Range: {start_date} to {end_date}\n"
            message += "\nReady to generate report."
            
            messagebox.showinfo("Report Parameters", message)
            
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


def create_progress_window():
    """Create and return a progress window (DEPRECATED - use integrated UI instead)
    
    Returns:
        ProgressWindow instance
    """
    root = tk.Tk()
    progress_window = ProgressWindow(root)
    progress_window.start_progress()
    return progress_window


if __name__ == "__main__":
    # Run the UI when module is executed directly
    selections = launch_ui()
    if selections:
        print("\nSelected Parameters:")
        for key, value in selections.items():
            print(f"{key}: {value}")
