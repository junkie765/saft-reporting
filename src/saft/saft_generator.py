"""Generate SAF-T XML for Bulgaria"""
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any
from lxml import etree as ET


logger = logging.getLogger(__name__)


class SAFTGenerator:
    """Generate SAF-T XML files compliant with Bulgarian requirements"""
    
    # SAF-T Bulgaria namespace - Official Bulgarian schema
    NAMESPACE = "mf:nra:dgti:dxxxx:declaration:v1"
    
    def __init__(self, config: dict):
        """
        Initialize SAF-T generator
        
        Args:
            config: Configuration dictionary
        """
        self.config = config
    
    def _elem(self, parent: ET.Element, name: str, text: str = None) -> ET.Element:
        """
        Create element with namespace prefix
        
        Args:
            parent: Parent element
            name: Element name (without namespace)
            text: Optional text content
            
        Returns:
            Created element
        """
        elem = ET.SubElement(parent, f"{{{self.NAMESPACE}}}{name}")
        if text is not None:
            elem.text = str(text)
        return elem
    
    def generate(self, saft_data: Dict[str, Any], output_path: Path, 
                 start_date: datetime, end_date: datetime):
        """
        Generate SAF-T XML file
        
        Args:
            saft_data: Transformed SAF-T data
            output_path: Output file path
            start_date: Period start date
            end_date: Period end date
        """
        logger.info("Generating SAF-T XML...")
        
        # Create root element with namespace prefix nsSAFT
        nsmap = {'nsSAFT': self.NAMESPACE}
        root = ET.Element(f"{{{self.NAMESPACE}}}AuditFile", nsmap=nsmap)
        
        # Add Header
        self._add_header(root, saft_data['header'], start_date, end_date)
        
        # Add MasterFiles
        self._add_master_files(root, saft_data['master_files'])
        
        # Add GeneralLedgerEntries
        self._add_general_ledger_entries(root, saft_data['general_ledger_entries'])
        
        # Add SourceDocumentsMonthly (required for monthly reports)
        self._add_source_documents_monthly(root, saft_data.get('source_documents', {}))
        
        # Create XML tree and write to file
        tree = ET.ElementTree(root)
        
        # Write with pretty print
        output_path.parent.mkdir(parents=True, exist_ok=True)
        tree.write(
            str(output_path),
            encoding='UTF-8',
            xml_declaration=True,
            pretty_print=True
        )
        
        logger.info(f"SAF-T XML generated successfully: {output_path}")
    
    def _add_header(self, root: ET.Element, header: Dict, start_date: datetime, end_date: datetime):
        """Add Header section according to Bulgarian SAF-T schema"""
        header_elem = self._elem(root, "Header")
        
        # Basic header information
        self._elem(header_elem, "AuditFileVersion", header['audit_file_version'])
        self._elem(header_elem, "AuditFileCountry", header['audit_file_country'])
        self._elem(header_elem, "AuditFileDateCreated", header['audit_file_date_created'])
        self._elem(header_elem, "SoftwareCompanyName", header['software_company_name'])
        self._elem(header_elem, "SoftwareID", header['software_product_name'])
        self._elem(header_elem, "SoftwareVersion", header['software_product_version'])
        
        # Company information with required structure
        company_elem = self._elem(header_elem, "Company")
        company = header['company']
        self._elem(company_elem, "RegistrationNumber", company['registration_number'])
        self._elem(company_elem, "Name", company['name'])
        
        # Address (required - at least one)
        address_elem = self._elem(company_elem, "Address")
        self._elem(address_elem, "StreetName", company.get('street', ''))
        self._elem(address_elem, "Number", "")
        self._elem(address_elem, "AdditionalAddressDetail", "")
        self._elem(address_elem, "Building", "")
        self._elem(address_elem, "City", company.get('city', ''))
        self._elem(address_elem, "PostalCode", company.get('postal_code', ''))
        self._elem(address_elem, "Region", company.get('state_province', ''))
        self._elem(address_elem, "Country", company.get('country', 'BG'))
        self._elem(address_elem, "AddressType", "StreetAddress")
        
        # Contact (required - at least one)
        contact_elem = self._elem(company_elem, "Contact")
        self._elem(contact_elem, "Telephone", company.get('telephone', ''))
        self._elem(contact_elem, "Fax", company.get('fax', ''))
        self._elem(contact_elem, "Email", company.get('email', ''))
        self._elem(contact_elem, "Website", company.get('website', ''))
        
        # TaxRegistration (optional)
        if company.get('tax_registration_number'):
            tax_reg_elem = self._elem(company_elem, "TaxRegistration")
            self._elem(tax_reg_elem, "TaxRegistrationNumber", company['tax_registration_number'])
            self._elem(tax_reg_elem, "TaxType", "100010")
            self._elem(tax_reg_elem, "TaxNumber", company['tax_registration_number'])
        
        # BankAccount (required - at least one)
        bank_elem = self._elem(company_elem, "BankAccount")
        self._elem(bank_elem, "IBANNumber", company.get('iban', ''))
        
        # Ownership (required)
        ownership_elem = self._elem(header_elem, "Ownership")
        # IsPartOfGroup: 1=standalone, 2=parent, 3=subsidiary, 4=branch, 5=other
        self._elem(ownership_elem, "IsPartOfGroup", company.get('is_part_of_group', '1'))
        self._elem(ownership_elem, "UltimateOwnerNameCyrillicBG", company.get('ultimate_owner_name', company['name']))
        self._elem(ownership_elem, "UltimateOwnerUICBG", company['registration_number'])
        
        # DefaultCurrencyCode - must be EUR per schema restriction
        self._elem(header_elem, "DefaultCurrencyCode", "EUR")
        
        # Selection criteria
        selection_elem = self._elem(header_elem, "SelectionCriteria")
        # Use PeriodStart/PeriodEnd instead of SelectionStartDate/SelectionEndDate
        self._elem(selection_elem, "PeriodStart", str(start_date.month))
        self._elem(selection_elem, "PeriodStartYear", str(start_date.year))
        self._elem(selection_elem, "PeriodEnd", str(end_date.month))
        self._elem(selection_elem, "PeriodEndYear", str(end_date.year))
        
        # HeaderComment - indicates type: M=Monthly, A=Annual, D=OnDemand
        self._elem(header_elem, "HeaderComment", header.get('header_comment', 'M'))
        
        # TaxAccountingBasis (required) - A=General commercial, P=Public, BANK, INSURANCE
        self._elem(header_elem, "TaxAccountingBasis", header.get('tax_accounting_basis', 'A'))
        
        # TaxEntity (optional)
        self._elem(header_elem, "TaxEntity", "Company")
        
        logger.debug("Header section added")
    
    def _add_master_files(self, root: ET.Element, master_files: Dict):
        """Add MasterFilesMonthly section according to Bulgarian SAF-T schema"""
        # Use MasterFilesMonthly for monthly reporting
        master_elem = self._elem(root, "MasterFilesMonthly")
        
        # GeneralLedgerAccounts (required)
        gl_accounts_elem = self._elem(master_elem, "GeneralLedgerAccounts")
        self._add_general_ledger_accounts(gl_accounts_elem, master_files['general_ledger_accounts'])
        
        # Customers (required)
        customers_elem = self._elem(master_elem, "Customers")
        self._add_customers(customers_elem, master_files['customers'])
        
        # Suppliers (required)
        suppliers_elem = self._elem(master_elem, "Suppliers")
        self._add_suppliers(suppliers_elem, master_files['suppliers'])
        
        # TaxTable (required) - Add minimal VAT tax table
        tax_table_elem = self._elem(master_elem, "TaxTable")
        self._add_tax_table(tax_table_elem)
        
        # UOMTable (required) - Add minimal unit of measure table
        uom_table_elem = self._elem(master_elem, "UOMTable")
        self._add_uom_table(uom_table_elem)
        
        # Products (required) - Add minimal product entry
        products_elem = self._elem(master_elem, "Products")
        self._add_products(products_elem)
        
        logger.debug("MasterFilesMonthly section added")
    
    def _add_general_ledger_accounts(self, parent: ET.Element, accounts: list):
        """Add GeneralLedgerAccount elements, output only one balance side per account"""
        for account in accounts:
            account_elem = self._elem(parent, "Account")
            self._elem(account_elem, "AccountID", str(account['account_id']))
            self._elem(account_elem, "AccountDescription", account['account_description'])
            self._elem(account_elem, "TaxpayerAccountID", str(account['account_id']))
            self._elem(account_elem, "AccountType", "Bifunctional")
            self._elem(account_elem, "AccountCreationDate", "2020-01-01")

            # Output only one balance side for opening and closing
            # Following Bulgaria.json schema conditions:
            # - OpeningDebitBalance: ValueHome >= 0
            # - OpeningCreditBalance: ValueHomeReversed > 0 (credit > 0)
            # - ClosingDebitBalance: ValueHome >= 0
            # - ClosingCreditBalance: ValueHomeReversed > 0 (credit > 0)
            opening_debit = account.get('opening_debit_balance', 0.0)
            opening_credit = account.get('opening_credit_balance', 0.0)
            closing_debit = account.get('closing_debit_balance', 0.0)
            closing_credit = account.get('closing_credit_balance', 0.0)

            # Determine which side based on closing (same-side rule)
            # When closing is credit, opening must be credit; when closing is debit, opening must be debit
            # When both are zero, default to debit side (follows >= 0 condition)
            if closing_credit > 0:
                # Closing is credit side - both must be credit
                self._elem(account_elem, "OpeningCreditBalance", f"{opening_credit:.2f}")
                self._elem(account_elem, "ClosingCreditBalance", f"{closing_credit:.2f}")
            else:
                # Closing is debit side (including zero) - both must be debit
                self._elem(account_elem, "OpeningDebitBalance", f"{opening_debit:.2f}")
                self._elem(account_elem, "ClosingDebitBalance", f"{closing_debit:.2f}")
        logger.debug(f"Added {len(accounts)} GL accounts")
    
    def _add_customers(self, parent: ET.Element, customers: list):
        """Add Customer elements with CompanyStructure, output only one balance side"""
        for customer in customers:
            customer_elem = self._elem(parent, "Customer")
            company_struct = self._elem(customer_elem, "CompanyStructure")
            self._elem(company_struct, "RegistrationNumber", customer.get('customer_tax_id', ''))
            company_name = customer['company_name']
            if any(ord(c) > 127 for c in company_name):
                self._elem(company_struct, "Name", company_name)
            else:
                self._elem(company_struct, "NameLatin", company_name)
            addr_elem = self._elem(company_struct, "Address")
            addr = customer.get('billing_address', {})
            self._elem(addr_elem, "StreetName", addr.get('street_name', ''))
            self._elem(addr_elem, "Number", "")
            self._elem(addr_elem, "AdditionalAddressDetail", "")
            self._elem(addr_elem, "Building", "")
            self._elem(addr_elem, "City", addr.get('city', ''))
            self._elem(addr_elem, "PostalCode", addr.get('postal_code', ''))
            self._elem(addr_elem, "Region", "")
            self._elem(addr_elem, "Country", addr.get('country', 'BG'))
            self._elem(addr_elem, "AddressType", "StreetAddress")
            contact_elem = self._elem(company_struct, "Contact")
            contact = customer.get('contact', {})
            self._elem(contact_elem, "Telephone", contact.get('telephone', ""))
            self._elem(contact_elem, "Fax", "")
            self._elem(contact_elem, "Email", "")
            self._elem(contact_elem, "Website", "")
            self._elem(customer_elem, "CustomerID", str(customer.get('customer_id', '')))
            self._elem(customer_elem, "AccountID", str(customer.get('account_id', '')))
            opening_debit = customer.get('opening_debit_balance', 0.0)
            opening_credit = customer.get('opening_credit_balance', 0.0)
            closing_debit = customer.get('closing_debit_balance', 0.0)
            closing_credit = customer.get('closing_credit_balance', 0.0)
            if opening_debit >= opening_credit:
                self._elem(customer_elem, "OpeningDebitBalance", f"{opening_debit:.2f}")
            else:
                self._elem(customer_elem, "OpeningCreditBalance", f"{opening_credit:.2f}")
            if closing_debit >= closing_credit:
                self._elem(customer_elem, "ClosingDebitBalance", f"{closing_debit:.2f}")
            else:
                self._elem(customer_elem, "ClosingCreditBalance", f"{closing_credit:.2f}")
        logger.debug(f"Added {len(customers)} customers")
    
    def _add_suppliers(self, parent: ET.Element, suppliers: list):
        """Add Supplier elements with CompanyStructure, output only one balance side"""
        for supplier in suppliers:
            supplier_elem = self._elem(parent, "Supplier")
            company_struct = self._elem(supplier_elem, "CompanyStructure")
            self._elem(company_struct, "RegistrationNumber", supplier.get('supplier_tax_id', ''))
            company_name = supplier['company_name']
            if any(ord(c) > 127 for c in company_name):
                self._elem(company_struct, "Name", company_name)
            else:
                self._elem(company_struct, "NameLatin", company_name)
            addr_elem = self._elem(company_struct, "Address")
            addr = supplier.get('billing_address', {})
            self._elem(addr_elem, "StreetName", addr.get('street_name', ''))
            self._elem(addr_elem, "Number", "")
            self._elem(addr_elem, "AdditionalAddressDetail", "")
            self._elem(addr_elem, "Building", "")
            self._elem(addr_elem, "City", addr.get('city', ''))
            self._elem(addr_elem, "PostalCode", addr.get('postal_code', ''))
            self._elem(addr_elem, "Region", "")
            self._elem(addr_elem, "Country", addr.get('country', 'BG'))
            self._elem(addr_elem, "AddressType", "StreetAddress")
            contact_elem = self._elem(company_struct, "Contact")
            contact = supplier.get('contact', {})
            self._elem(contact_elem, "Telephone", contact.get('telephone', ""))
            self._elem(contact_elem, "Fax", "")
            self._elem(contact_elem, "Email", "")
            self._elem(contact_elem, "Website", "")
            self._elem(supplier_elem, "SupplierID", str(supplier.get('supplier_id', '')))
            self._elem(supplier_elem, "AccountID", str(supplier.get('account_id', '')))
            opening_debit = supplier.get('opening_debit_balance', 0.0)
            opening_credit = supplier.get('opening_credit_balance', 0.0)
            closing_debit = supplier.get('closing_debit_balance', 0.0)
            closing_credit = supplier.get('closing_credit_balance', 0.0)
            if opening_credit >= opening_debit:
                self._elem(supplier_elem, "OpeningCreditBalance", f"{opening_credit:.2f}")
            else:
                self._elem(supplier_elem, "OpeningDebitBalance", f"{opening_debit:.2f}")
            if closing_credit >= closing_debit:
                self._elem(supplier_elem, "ClosingCreditBalance", f"{closing_credit:.2f}")
            else:
                self._elem(supplier_elem, "ClosingDebitBalance", f"{closing_debit:.2f}")
        logger.debug(f"Added {len(suppliers)} suppliers")
    
    def _add_general_ledger_entries(self, root: ET.Element, entries: list):
        """Add GeneralLedgerEntries section"""
        gl_entries_elem = self._elem(root, "GeneralLedgerEntries")
        
        self._elem(gl_entries_elem, "NumberOfEntries", str(len(entries)))
        
        total_debit = sum(
            sum(line['debit_amount'] for line in entry['lines'])
            for entry in entries
        )
        total_credit = sum(
            sum(line['credit_amount'] for line in entry['lines'])
            for entry in entries
        )
        
        self._elem(gl_entries_elem, "TotalDebit", f"{total_debit:.2f}")
        self._elem(gl_entries_elem, "TotalCredit", f"{total_credit:.2f}")
        
        # Add Journal entries
        for entry in entries:
            self._add_journal_entry(gl_entries_elem, entry)
        
        logger.debug(f"Added {len(entries)} GL entries")
    
    def _add_journal_entry(self, parent: ET.Element, entry: Dict):
        """Add a Journal entry"""
        journal_elem = self._elem(parent, "Journal")
        
        self._elem(journal_elem, "JournalID", entry['transaction_id'])
        self._elem(journal_elem, "Description", entry.get('description', ''))
        
        # Transaction
        trans_elem = self._elem(journal_elem, "Transaction")
        self._elem(trans_elem, "TransactionID", entry['transaction_id'])
        self._elem(trans_elem, "Period", str(entry.get('period', '')))
        self._elem(trans_elem, "TransactionDate", entry['transaction_date'])
        self._elem(trans_elem, "TransactionType", entry.get('transaction_type', 'N'))
        self._elem(trans_elem, "Description", entry.get('description', ''))
        self._elem(trans_elem, "SystemEntryDate", entry['system_entry_date'])
        self._elem(trans_elem, "GLPostingDate", entry['gl_posting_date'])
        
        # Lines
        for line in entry['lines']:
            line_elem = self._elem(trans_elem, "Line")
            self._elem(line_elem, "RecordID", line['record_id'])
            self._elem(line_elem, "AccountID", str(line['account_id']))
            
            if line['debit_amount'] > 0:
                debit_elem = self._elem(line_elem, "DebitAmount")
                self._elem(debit_elem, "Amount", f"{line['debit_amount']:.2f}")
            
            if line['credit_amount'] > 0:
                credit_elem = self._elem(line_elem, "CreditAmount")
                self._elem(credit_elem, "Amount", f"{line['credit_amount']:.2f}")
            
            if line.get('description'):
                self._elem(line_elem, "Description", line['description'])
    
    def _add_tax_table(self, parent: ET.Element):
        """Add TaxTable with Bulgarian VAT rates"""
        # Add standard Bulgarian VAT rates
        tax_entry = self._elem(parent, "TaxTableEntry")
        self._elem(tax_entry, "TaxType", "VAT")
        self._elem(tax_entry, "TaxCode", "STD")
        self._elem(tax_entry, "TaxPercentage", "20.00")
        self._elem(tax_entry, "Description", "Standard VAT Rate")
        
        logger.debug("Added tax table")
    
    def _add_uom_table(self, parent: ET.Element):
        """Add UOMTable with basic units of measure"""
        # Add basic unit of measure
        uom_entry = self._elem(parent, "UOMTableEntry")
        self._elem(uom_entry, "UnitOfMeasure", "UNIT")
        self._elem(uom_entry, "Description", "Unit")
        
        logger.debug("Added UOM table")
    
    def _add_products(self, parent: ET.Element):
        """Add minimal Products section"""
        # Add minimal product entry (required by schema)
        product = self._elem(parent, "Product")
        self._elem(product, "ProductCode", "SERVICES")
        self._elem(product, "ProductDescription", "Professional Services")
        self._elem(product, "ProductNumberCode", "SERVICES")
        
        logger.debug("Added products")
    
    def _add_source_documents_monthly(self, root: ET.Element, source_docs: Dict):
        """Add SourceDocumentsMonthly section (required for monthly reports)"""
        # Add minimal SourceDocumentsMonthly structure
        source_docs_elem = self._elem(root, "SourceDocumentsMonthly")
        
        # SalesInvoices (optional but good to include structure)
        # PurchaseInvoices (optional)
        # Payments (optional)
        # For now, add minimal structure
        logger.debug("Added SourceDocumentsMonthly section")
