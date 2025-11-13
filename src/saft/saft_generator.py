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
    
    def _add_address(self, parent: ET.Element, address: Dict, address_type: str = "StreetAddress"):
        """Add Address element with standard structure"""
        addr_elem = self._elem(parent, "Address")
        self._elem(addr_elem, "StreetName", address.get('street_name', address.get('street', '')))
        self._elem(addr_elem, "Number", "")
        self._elem(addr_elem, "AdditionalAddressDetail", "")
        self._elem(addr_elem, "Building", "")
        self._elem(addr_elem, "City", address.get('city', ''))
        self._elem(addr_elem, "PostalCode", address.get('postal_code', ''))
        self._elem(addr_elem, "Region", address.get('region', address.get('state_province', '')))
        self._elem(addr_elem, "Country", address.get('country', 'BG'))
        self._elem(addr_elem, "AddressType", address_type)
        return addr_elem
    
    def _add_contact(self, parent: ET.Element, contact: Dict):
        """Add Contact element with standard structure"""
        contact_elem = self._elem(parent, "Contact")
        self._elem(contact_elem, "Telephone", contact.get('telephone', ''))
        self._elem(contact_elem, "Fax", contact.get('fax', ''))
        self._elem(contact_elem, "Email", contact.get('email', ''))
        self._elem(contact_elem, "Website", contact.get('website', ''))
        return contact_elem
    
    def _add_company_name(self, parent: ET.Element, name: str):
        """Add company name in appropriate format (Cyrillic or Latin)"""
        if any(ord(c) > 127 for c in name):
            self._elem(parent, "Name", name)
        else:
            self._elem(parent, "NameLatin", name)
    
    def _add_balance(self, parent: ET.Element, opening_debit: float, opening_credit: float, 
                     closing_debit: float, closing_credit: float):
        """Add balance elements following same-side rule (closing determines side)"""
        if closing_credit > 0:
            self._elem(parent, "OpeningCreditBalance", f"{opening_credit:.2f}")
            self._elem(parent, "ClosingCreditBalance", f"{closing_credit:.2f}")
        else:
            self._elem(parent, "OpeningDebitBalance", f"{opening_debit:.2f}")
            self._elem(parent, "ClosingDebitBalance", f"{closing_debit:.2f}")
    
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
        self._add_master_files(root, saft_data['master_files'], saft_data.get('tax_codes', []))
        
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
        self._add_address(company_elem, company)
        
        # Contact (required - at least one)
        self._add_contact(company_elem, company)
        
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
    
    def _add_master_files(self, root: ET.Element, master_files: Dict, tax_codes: list):
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
        
        # TaxTable (required) - Add tax codes from Salesforce
        tax_table_elem = self._elem(master_elem, "TaxTable")
        self._add_tax_table(tax_table_elem, tax_codes)
        
        # UOMTable (required) - Add minimal unit of measure table
        uom_table_elem = self._elem(master_elem, "UOMTable")
        self._add_uom_table(uom_table_elem)
        
        # Products (required) - Add products from Salesforce
        products_elem = self._elem(master_elem, "Products")
        self._add_products(products_elem, master_files.get('products', []))
    
    def _add_general_ledger_accounts(self, parent: ET.Element, accounts: list):
        """Add GeneralLedgerAccount elements with balances following same-side rule"""
        for account in accounts:
            account_elem = self._elem(parent, "Account")
            self._elem(account_elem, "AccountID", str(account['account_id']))
            self._elem(account_elem, "AccountDescription", account['account_description'])
            self._elem(account_elem, "TaxpayerAccountID", str(account['account_id']))
            self._elem(account_elem, "AccountType", "Bifunctional")
            self._elem(account_elem, "AccountCreationDate", "2020-01-01")
            
            self._add_balance(account_elem,
                            account.get('opening_debit_balance', 0.0),
                            account.get('opening_credit_balance', 0.0),
                            account.get('closing_debit_balance', 0.0),
                            account.get('closing_credit_balance', 0.0))
    
    def _add_customers(self, parent: ET.Element, customers: list):
        """Add Customer elements with CompanyStructure, output only one balance side"""
        for customer in customers:
            customer_elem = self._elem(parent, "Customer")
            company_struct = self._elem(customer_elem, "CompanyStructure")
            self._elem(company_struct, "RegistrationNumber", customer.get('customer_tax_id', ''))
            self._add_company_name(company_struct, customer['company_name'])
            self._add_address(company_struct, customer.get('billing_address', {}))
            self._add_contact(company_struct, customer.get('contact', {}))
            self._elem(customer_elem, "CustomerID", str(customer.get('customer_id', '')))
            self._elem(customer_elem, "AccountID", str(customer.get('account_id', '')))
            self._add_balance(customer_elem,
                            customer.get('opening_debit_balance', 0.0),
                            customer.get('opening_credit_balance', 0.0),
                            customer.get('closing_debit_balance', 0.0),
                            customer.get('closing_credit_balance', 0.0))
    
    def _add_suppliers(self, parent: ET.Element, suppliers: list):
        """Add Supplier elements with CompanyStructure, output only one balance side"""
        for supplier in suppliers:
            supplier_elem = self._elem(parent, "Supplier")
            company_struct = self._elem(supplier_elem, "CompanyStructure")
            self._elem(company_struct, "RegistrationNumber", supplier.get('supplier_tax_id', ''))
            self._add_company_name(company_struct, supplier['company_name'])
            self._add_address(company_struct, supplier.get('billing_address', {}))
            self._add_contact(company_struct, supplier.get('contact', {}))
            self._elem(supplier_elem, "SupplierID", str(supplier.get('supplier_id', '')))
            self._elem(supplier_elem, "AccountID", str(supplier.get('account_id', '')))
            self._add_balance(supplier_elem,
                            supplier.get('opening_debit_balance', 0.0),
                            supplier.get('opening_credit_balance', 0.0),
                            supplier.get('closing_debit_balance', 0.0),
                            supplier.get('closing_credit_balance', 0.0))
    
    def _add_general_ledger_entries(self, root: ET.Element, entries: list):
        """Add GeneralLedgerEntries section"""
        gl_entries_elem = self._elem(root, "GeneralLedgerEntries")
        self._elem(gl_entries_elem, "NumberOfEntries", str(len(entries)))
        
        total_debit = sum(sum(line['debit_amount'] for line in entry['lines']) for entry in entries)
        total_credit = sum(sum(line['credit_amount'] for line in entry['lines']) for entry in entries)
        
        self._elem(gl_entries_elem, "TotalDebit", f"{total_debit:.2f}")
        self._elem(gl_entries_elem, "TotalCredit", f"{total_credit:.2f}")
        
        for entry in entries:
            self._add_journal_entry(gl_entries_elem, entry)
    
    def _add_journal_entry(self, parent: ET.Element, entry: Dict):
        """Add a Journal entry according to Bulgarian SAF-T schema"""
        journal_elem = self._elem(parent, "Journal")
        
        self._elem(journal_elem, "JournalID", "GL")
        self._elem(journal_elem, "Description", entry.get('description', 'General Ledger'))
        self._elem(journal_elem, "Type", "GLEntry")
        
        # Transaction
        trans_elem = self._elem(journal_elem, "Transaction")
        self._elem(trans_elem, "TransactionID", entry['transaction_id'])
        self._elem(trans_elem, "Period", str(entry.get('period', '')))
        self._elem(trans_elem, "PeriodYear", str(entry.get('period_year', '')))
        self._elem(trans_elem, "TransactionDate", entry['transaction_date'])
        self._elem(trans_elem, "SourceID", entry.get('source_id', '0'))
        self._elem(trans_elem, "TransactionType", entry.get('transaction_type', 'Normal'))
        self._elem(trans_elem, "Description", entry.get('description', ''))
        self._elem(trans_elem, "BatchID", entry.get('batch_id', '0'))
        self._elem(trans_elem, "SystemEntryDate", entry['system_entry_date'])
        self._elem(trans_elem, "GLPostingDate", entry['gl_posting_date'])
        self._elem(trans_elem, "CustomerID", entry.get('customer_id', '0'))
        self._elem(trans_elem, "SupplierID", entry.get('supplier_id', '0'))
        self._elem(trans_elem, "SystemID", entry.get('system_id', '0'))
        
        # Transaction Lines
        for line in entry['lines']:
            line_elem = self._elem(trans_elem, "TransactionLine")
            self._elem(line_elem, "RecordID", line['record_id'])
            self._elem(line_elem, "AccountID", str(line['account_id']))
            self._elem(line_elem, "TaxpayerAccountID", str(line.get('taxpayer_account_id', line['account_id'])))
            
            # ValueDate
            if line.get('value_date'):
                self._elem(line_elem, "ValueDate", line['value_date'])
            
            # SourceDocumentID
            if line.get('source_document_id'):
                self._elem(line_elem, "SourceDocumentID", line['source_document_id'])
            
            # CustomerID and SupplierID
            self._elem(line_elem, "CustomerID", line.get('customer_id', '0'))
            self._elem(line_elem, "SupplierID", line.get('supplier_id', '0'))
            
            # Description
            if line.get('description'):
                self._elem(line_elem, "Description", line['description'])
            
            # Per Bulgarian SAF-T schema: MUST have either DebitAmount OR CreditAmount (xs:choice)
            currency = line.get('currency_code', 'BGN')
            exchange_rate = line.get('exchange_rate', '1.0000')
            
            if line['debit_amount'] > 0 or (line['debit_amount'] == 0 and line['credit_amount'] == 0):
                self._add_currency_amount(line_elem, "DebitAmount", line['debit_amount'], currency, exchange_rate)
            elif line['credit_amount'] > 0:
                self._add_currency_amount(line_elem, "CreditAmount", line['credit_amount'], currency, exchange_rate)
            
            # Tax Information
            tax_info = self._elem(line_elem, "TaxInformation")
            self._elem(tax_info, "TaxType", line.get('tax_type', ''))
            self._elem(tax_info, "TaxCode", line.get('tax_code', ''))
            self._elem(tax_info, "TaxPercentage", str(line.get('tax_percentage', 0)))
            self._elem(tax_info, "TaxBase", f"{line.get('tax_base', 0):.2f}")
            self._elem(tax_info, "TaxBaseDescription", line.get('tax_base_description', ''))
            self._add_currency_amount(tax_info, "TaxAmount", line.get('tax_amount', 0), currency, exchange_rate)
            
            self._elem(tax_info, "TaxExemptionReason", line.get('tax_exemption_reason', ''))
            self._elem(tax_info, "TaxDeclarationPeriod", line.get('tax_declaration_period', ''))
    
    def _add_tax_table(self, parent: ET.Element, tax_codes: list):
        """Add TaxTable with tax codes from Salesforce"""
        if not tax_codes:
            tax_entry = self._elem(parent, "TaxTableEntry")
            self._elem(tax_entry, "TaxType", "ДДС")
            self._elem(tax_entry, "TaxCode", "STD")
            self._elem(tax_entry, "TaxPercentage", "20.00")
            self._elem(tax_entry, "Description", "Стандартна ставка на ДДС")
        else:
            for tax_code in tax_codes:
                tax_entry = self._elem(parent, "TaxTableEntry")
                self._elem(tax_entry, "TaxType", tax_code.get('tax_type', 'ДДС'))
                self._elem(tax_entry, "TaxCode", tax_code.get('tax_code', 'STD'))
                self._elem(tax_entry, "TaxPercentage", f"{tax_code.get('tax_percentage', 0):.2f}")
                if tax_code.get('description'):
                    self._elem(tax_entry, "Description", tax_code['description'])
    
    def _add_uom_table(self, parent: ET.Element):
        """Add UOMTable with basic units of measure"""
        uom_entry = self._elem(parent, "UOMTableEntry")
        self._elem(uom_entry, "UnitOfMeasure", "HUR")
        self._elem(uom_entry, "Description", "Часове")
    
    def _add_currency_amount(self, parent: ET.Element, element_name: str, amount: float, currency: str = "BGN", exchange_rate: str = "1.0000"):
        """Add currency amount element with standard structure"""
        amount_elem = self._elem(parent, element_name)
        self._elem(amount_elem, "Amount", f"{amount:.2f}")
        self._elem(amount_elem, "CurrencyCode", currency)
        self._elem(amount_elem, "CurrencyAmount", f"{amount:.2f}")
        if exchange_rate:
            self._elem(amount_elem, "ExchangeRate", exchange_rate)
        return amount_elem
    
    def _add_products(self, parent: ET.Element, products: list):
        """Add Products section from Salesforce Product2 records"""
        for prod in products:
            product = self._elem(parent, "Product")
            self._elem(product, "ProductCode", prod['product_code'])
            self._elem(product, "GoodsServicesID", prod['goods_services_id'])
            
            if prod.get('product_group'):
                self._elem(product, "ProductGroup", prod['product_group'])
            
            self._elem(product, "Description", prod['description'])
            self._elem(product, "ProductCommodityCode", prod['product_commodity_code'])
            self._elem(product, "ProductNumberCode", prod['product_number_code'])
            self._elem(product, "UOMBase", prod['uom_base'])
            self._elem(product, "UOMStandard", prod['uom_standard'])
            self._elem(product, "UOMToUOMBaseConversionFactor", prod['uom_conversion_factor'])
            
            # Tax information
            tax_elem = self._elem(product, "Tax")
            self._elem(tax_elem, "TaxType", prod['tax_type'])
            self._elem(tax_elem, "TaxCode", prod['tax_code'])
    
    def _add_source_documents_monthly(self, root: ET.Element, source_docs: Dict):
        """Add SourceDocumentsMonthly section"""
        source_docs_elem = self._elem(root, "SourceDocumentsMonthly")
        
        sales_invoices = source_docs.get('sales_invoices', [])
        if sales_invoices:
            self._add_sales_invoices(self._elem(source_docs_elem, "SalesInvoices"), sales_invoices)
        
        payments = source_docs.get('payments', [])
        if payments:
            self._add_payments(self._elem(source_docs_elem, "Payments"), payments)
        
        purchase_invoices = source_docs.get('purchase_invoices', [])
        if purchase_invoices:
            self._add_purchase_invoices(self._elem(source_docs_elem, "PurchaseInvoices"), purchase_invoices)
    
    def _add_sales_invoices(self, parent: ET.Element, invoices: list):
        """Add sales invoices to XML"""
        self._elem(parent, "NumberOfEntries", str(len(invoices)))
        self._elem(parent, "TotalDebit", f"{sum(inv.get('total_debit', 0) for inv in invoices):.2f}")
        self._elem(parent, "TotalCredit", f"{sum(inv.get('total_credit', 0) for inv in invoices):.2f}")
        
        for invoice in invoices:
            inv_elem = self._elem(parent, "Invoice")
            self._elem(inv_elem, "InvoiceNo", invoice['invoice_no'])
            
            # CustomerInfo
            customer_elem = self._elem(inv_elem, "CustomerInfo")
            self._elem(customer_elem, "CustomerID", invoice['customer_id'])
            self._elem(customer_elem, "Name", invoice['customer_name'])
            billing_addr = self._elem(customer_elem, "BillingAddress")
            self._elem(billing_addr, "City", "")
            self._elem(billing_addr, "Country", "BG")
            
            self._elem(inv_elem, "AccountID", "411")  # Revenue account
            self._elem(inv_elem, "BranchStoreNumber", "0")
            self._elem(inv_elem, "Period", str(invoice['period']))
            self._elem(inv_elem, "PeriodYear", str(invoice['period_year']))
            self._elem(inv_elem, "InvoiceDate", invoice['invoice_date'])
            self._elem(inv_elem, "InvoiceType", "01")  # Standard invoice
            
            # ShipTo
            ship_to = self._elem(inv_elem, "ShipTo")
            self._elem(ship_to, "DeliveryID", "")
            self._elem(ship_to, "DeliveryDate", invoice['invoice_date'])
            self._elem(ship_to, "WarehouseID", "")
            self._elem(ship_to, "LocationID", "")
            self._elem(ship_to, "UCR", "")
            addr = self._elem(ship_to, "Address")
            self._elem(addr, "City", "")
            self._elem(addr, "Country", "BG")
            
            # ShipFrom
            ship_from = self._elem(inv_elem, "ShipFrom")
            self._elem(ship_from, "DeliveryID", "")
            self._elem(ship_from, "DeliveryDate", invoice['invoice_date'])
            self._elem(ship_from, "WarehouseID", "")
            self._elem(ship_from, "LocationID", "")
            self._elem(ship_from, "UCR", "")
            addr = self._elem(ship_from, "Address")
            self._elem(addr, "City", "")
            self._elem(addr, "Country", "BG")
            
            self._elem(inv_elem, "PaymentTerms", "30")
            self._elem(inv_elem, "SelfBillingIndicator", "N")
            self._elem(inv_elem, "SourceID", "Certinia")
            self._elem(inv_elem, "GLPostingDate", invoice['gl_posting_date'])
            self._elem(inv_elem, "BatchID", "0")
            self._elem(inv_elem, "SystemID", invoice['system_id'])
            self._elem(inv_elem, "TransactionID", invoice['invoice_no'])
            self._elem(inv_elem, "ReceiptNumbers", "")
            
            # Invoice Lines
            for line in invoice['lines']:
                line_elem = self._elem(inv_elem, "InvoiceLine")
                self._elem(line_elem, "LineNumber", line['line_number'])
                self._elem(line_elem, "AccountID", line['account_id'])
                
                analysis = self._elem(line_elem, "Analysis")
                self._elem(analysis, "AnalysisType", "")
                self._elem(analysis, "AnalysisID", "")
                
                self._elem(line_elem, "OrderReferences", "")
                self._elem(line_elem, "ShipTo", "")
                self._elem(line_elem, "ShipFrom", "")
                self._elem(line_elem, "GoodsServicesID", "01")
                self._elem(line_elem, "ProductCode", line['product_code'])
                self._elem(line_elem, "ProductDescription", line['product_description'])
                
                delivery = self._elem(line_elem, "Delivery")
                self._elem(delivery, "DeliveryDate", invoice['invoice_date'])
                
                self._elem(line_elem, "Quantity", f"{line['quantity']:.2f}")
                self._elem(line_elem, "InvoiceUOM", "HUR")
                self._elem(line_elem, "UOMToUOMBaseConversionFactor", "1")
                self._elem(line_elem, "UnitPrice", f"{line['unit_price']:.2f}")
                self._elem(line_elem, "TaxPointDate", invoice['invoice_date'])
                self._elem(line_elem, "References", "")
                self._elem(line_elem, "Description", line['description'])
                
                line_amt = self._elem(line_elem, "InvoiceLineAmount")
                self._elem(line_amt, "Amount", f"{line['line_amount']:.2f}")
                self._elem(line_amt, "CurrencyCode", "BGN")
                self._elem(line_amt, "CurrencyAmount", f"{line['line_amount']:.2f}")
                
                self._elem(line_elem, "DebitCreditIndicator", line['debit_credit_indicator'])
                
                shipping = self._elem(line_elem, "ShippingCostsAmount")
                self._elem(shipping, "Amount", "0.00")
                self._elem(shipping, "CurrencyCode", "BGN")
                self._elem(shipping, "CurrencyAmount", "0.00")
                
                tax_info = self._elem(line_elem, "TaxInformation")
                self._elem(tax_info, "TaxType", "100010")
                self._elem(tax_info, "TaxCode", "110010")
                tax_amt = self._elem(tax_info, "TaxAmount")
                self._elem(tax_amt, "Amount", f"{line['tax_amount']:.2f}")
                self._elem(tax_amt, "CurrencyCode", "BGN")
                self._elem(tax_amt, "CurrencyAmount", f"{line['tax_amount']:.2f}")
    
    def _add_payments(self, parent: ET.Element, payments: list):
        """Add payments to XML"""
        self._elem(parent, "NumberOfEntries", str(len(payments)))
        self._elem(parent, "TotalDebit", f"{sum(pay.get('total_debit', 0) for pay in payments):.2f}")
        self._elem(parent, "TotalCredit", f"{sum(pay.get('total_credit', 0) for pay in payments):.2f}")
        
        for payment in payments:
            pay_elem = self._elem(parent, "Payment")
            self._elem(pay_elem, "PaymentRefNo", payment['payment_ref_no'])
            self._elem(pay_elem, "Period", str(payment['period']))
            self._elem(pay_elem, "PeriodYear", str(payment['period_year']))
            self._elem(pay_elem, "TransactionID", payment['payment_ref_no'])
            self._elem(pay_elem, "TransactionDate", payment['payment_date'])
            self._elem(pay_elem, "PaymentMethod", "03")  # Bank transfer
            self._elem(pay_elem, "Description", payment.get('reference', 'Payment'))
            self._elem(pay_elem, "BatchID", "")
            self._elem(pay_elem, "SystemID", payment['system_id'])
            self._elem(pay_elem, "SourceID", "Certinia")
            
            # Payment Lines
            for line in payment['lines']:
                line_elem = self._elem(pay_elem, "PaymentLine")
                self._elem(line_elem, "LineNumber", line['line_number'])
                self._elem(line_elem, "SourceDocumentID", payment['system_id'])
                self._elem(line_elem, "AccountID", line['account_id'])
                
                analysis = self._elem(line_elem, "Analysis")
                self._elem(analysis, "AnalysisType", "")
                self._elem(analysis, "AnalysisID", "")
                
                self._elem(line_elem, "CustomerID", line.get('customer_id', ''))
                self._elem(line_elem, "SupplierID", "")
                self._elem(line_elem, "TaxPointDate", payment['payment_date'])
                self._elem(line_elem, "Description", line['description'])
                self._elem(line_elem, "DebitCreditIndicator", line['debit_credit_indicator'])
                
                line_amt = self._elem(line_elem, "PaymentLineAmount")
                amount = line['debit_amount'] if line['debit_amount'] > 0 else line['credit_amount']
                self._elem(line_amt, "Amount", f"{amount:.2f}")
                self._elem(line_amt, "CurrencyCode", "BGN")
                self._elem(line_amt, "CurrencyAmount", f"{amount:.2f}")
                
                tax_info = self._elem(line_elem, "TaxInformation")
                self._elem(tax_info, "TaxType", "")
                self._elem(tax_info, "TaxCode", "")
                tax_amt = self._elem(tax_info, "TaxAmount")
                self._elem(tax_amt, "Amount", "0.00")
                self._elem(tax_amt, "CurrencyCode", "BGN")
                self._elem(tax_amt, "CurrencyAmount", "0.00")
    
    def _add_purchase_invoices(self, parent: ET.Element, invoices: list):
        """Add purchase invoices to XML"""
        self._elem(parent, "NumberOfEntries", str(len(invoices)) if invoices else "0")
        self._elem(parent, "TotalDebit", f"{sum(inv.get('total_debit', 0) for inv in invoices):.2f}")
        self._elem(parent, "TotalCredit", f"{sum(inv.get('total_credit', 0) for inv in invoices):.2f}")
        
        if not invoices:
            return
        
        for invoice in invoices:
            invoice_elem = self._elem(parent, "Invoice")
            
            self._elem(invoice_elem, "InvoiceNo", invoice.get('invoice_no', ''))
            self._elem(invoice_elem, "InvoiceDate", invoice.get('invoice_date', ''))
            self._elem(invoice_elem, "InvoiceType", "FT")  # Standard invoice
            self._elem(invoice_elem, "Period", str(invoice.get('period', '')))
            self._elem(invoice_elem, "PeriodYear", str(invoice.get('period_year', '')))
            self._elem(invoice_elem, "GLPostingDate", invoice.get('gl_posting_date', ''))
            
            # Supplier info
            supplier_info = self._elem(invoice_elem, "SupplierInfo")
            self._elem(supplier_info, "SupplierID", invoice.get('supplier_id', ''))
            self._elem(supplier_info, "SupplierName", invoice.get('supplier_name', ''))
            
            # Lines
            for line in invoice.get('lines', []):
                line_elem = self._elem(invoice_elem, "Line")
                
                self._elem(line_elem, "LineNumber", line.get('line_number', ''))
                
                if line.get('account_id'):
                    self._elem(line_elem, "AccountID", line.get('account_id', ''))
                
                if line.get('product_code'):
                    self._elem(line_elem, "ProductCode", line.get('product_code', ''))
                
                if line.get('product_description'):
                    self._elem(line_elem, "ProductDescription", line.get('product_description', ''))
                
                self._elem(line_elem, "Quantity", f"{line.get('quantity', 0):.2f}")
                self._elem(line_elem, "UnitPrice", f"{line.get('unit_price', 0):.2f}")
                
                # Amount with proper debit/credit handling
                line_amount = line.get('line_amount', 0)
                indicator = line.get('debit_credit_indicator', 'D')
                
                if indicator == 'D':
                    debit_elem = self._elem(line_elem, "DebitAmount")
                    self._elem(debit_elem, "Amount", f"{line_amount:.2f}")
                    self._elem(debit_elem, "CurrencyCode", "BGN")
                else:
                    credit_elem = self._elem(line_elem, "CreditAmount")
                    self._elem(credit_elem, "Amount", f"{line_amount:.2f}")
                    self._elem(credit_elem, "CurrencyCode", "BGN")
                
                if line.get('tax_amount', 0) > 0:
                    self._elem(line_elem, "TaxAmount", f"{line.get('tax_amount', 0):.2f}")
                
                if line.get('description'):
                    self._elem(line_elem, "Description", line.get('description', ''))
            
            # Document totals
            doc_totals = self._elem(invoice_elem, "DocumentTotals")
            self._elem(doc_totals, "TaxPayable", f"{sum(l.get('tax_amount', 0) for l in invoice.get('lines', [])):.2f}")
            self._elem(doc_totals, "NetTotal", f"{invoice.get('total_debit', 0):.2f}")
            self._elem(doc_totals, "GrossTotal", f"{invoice.get('total_debit', 0) + sum(l.get('tax_amount', 0) for l in invoice.get('lines', [])):.2f}")
