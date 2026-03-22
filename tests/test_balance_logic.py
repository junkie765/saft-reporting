"""Simplified unit tests for GL balance calculation logic"""
import unittest
import sys
from pathlib import Path
from datetime import datetime
from lxml import etree as ET

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from transformers.certinia_transformer import CertiniaTransformer
from saft.saft_generator import SAFTGenerator


class TestBalanceLogic(unittest.TestCase):
    """Test core balance calculation logic"""
    
    def setUp(self):
        """Set up test fixtures"""
        config = {
            'year': '2025',
            'period_from': '005',
            'period_to': '005',
            'saft': {
                'selection_start_date': '2025-05-01',
                'selection_end_date': '2025-05-31'
            }
        }
        self.transformer = CertiniaTransformer(config)
        # Clear cache between tests
        self.transformer._period_info_cache = None
    
    def test_positive_net_balance_is_debit(self):
        """Positive net balance should result in debit side"""
        transaction_lines = [
            {
                'c2g__GeneralLedgerAccount__c': 'GL001',
                'c2g__HomeValue__c': 100.0,
                'c2g__Transaction__r': {
                    'c2g__Period__r': {
                        'Name': '2025/005',
                        'c2g__PeriodNumber__c': 5,
                        'c2g__YearName__c': '2025'
                    }
                }
            }
        ]
        
        gl_account_codes = {'GL001': '100001'}
        gl_balances, _ = self.transformer._calculate_all_balances(transaction_lines, gl_account_codes)
        
        self.assertIn('GL001', gl_balances)
        # Positive balance → debit side
        self.assertGreater(gl_balances['GL001']['closing_debit_balance'], 0)
        self.assertEqual(gl_balances['GL001']['closing_credit_balance'], 0.0)
    
    def test_negative_net_balance_is_credit(self):
        """Negative net balance should result in credit side"""
        transaction_lines = [
            {
                'c2g__GeneralLedgerAccount__c': 'GL001',
                'c2g__HomeValue__c': -100.0,
                'c2g__Transaction__r': {
                    'c2g__Period__r': {
                        'Name': '2025/005',
                        'c2g__PeriodNumber__c': 5,
                        'c2g__YearName__c': '2025'
                    }
                }
            }
        ]
        
        gl_account_codes = {'GL001': '200001'}
        gl_balances, _ = self.transformer._calculate_all_balances(transaction_lines, gl_account_codes)
        
        self.assertIn('GL001', gl_balances)
        # Negative balance → credit side
        self.assertEqual(gl_balances['GL001']['closing_debit_balance'], 0.0)
        self.assertGreater(gl_balances['GL001']['closing_credit_balance'], 0)

    def test_gl_balances_unchanged_when_account_balance_accumulation_is_disabled(self):
        """Skipping account balance accumulation must not change GLA balances."""
        transaction_lines = [
            {
                'c2g__GeneralLedgerAccount__c': 'GL001',
                'c2g__Account__c': 'ACC1',
                'c2g__HomeValue__c': 100.0,
                'c2g__Transaction__r': {
                    'c2g__Period__r': {
                        'Name': '2025/004',
                        'c2g__PeriodNumber__c': 4,
                        'c2g__YearName__c': '2025'
                    }
                }
            },
            {
                'c2g__GeneralLedgerAccount__c': 'GL001',
                'c2g__Account__c': 'ACC1',
                'c2g__HomeValue__c': -25.0,
                'c2g__Transaction__r': {
                    'c2g__Period__r': {
                        'Name': '2025/005',
                        'c2g__PeriodNumber__c': 5,
                        'c2g__YearName__c': '2025'
                    }
                }
            },
            {
                'c2g__GeneralLedgerAccount__c': 'GL002',
                'c2g__Account__c': 'ACC2',
                'c2g__HomeValue__c': -50.0,
                'c2g__Transaction__r': {
                    'c2g__Period__r': {
                        'Name': '2025/005',
                        'c2g__PeriodNumber__c': 5,
                        'c2g__YearName__c': '2025'
                    }
                }
            }
        ]

        gl_account_codes = {'GL001': '100001', 'GL002': '200001'}
        baseline_gl_balances, baseline_account_balances = self.transformer._calculate_all_balances(
            transaction_lines,
            gl_account_codes,
        )
        optimized_gl_balances, optimized_account_balances = self.transformer._calculate_all_balances(
            transaction_lines,
            gl_account_codes,
            include_account_balances=False,
        )

        self.assertEqual(baseline_gl_balances, optimized_gl_balances)
        self.assertTrue(baseline_account_balances)
        self.assertEqual(optimized_account_balances, {})

    def test_contact_person_written_before_telephone(self):
        """Contact must include nested ContactPerson before Telephone."""
        generator = SAFTGenerator({})
        root = ET.Element(f"{{{generator.NAMESPACE}}}Root")

        generator._add_contact(root, {
            'telephone': '123456789',
            'email': 'test@example.com',
            'website': 'https://example.com',
        })

        namespace = {'ns': generator.NAMESPACE}
        contact_elem = root.find('ns:Contact', namespace)
        self.assertIsNotNone(contact_elem)

        children = list(contact_elem)
        self.assertGreaterEqual(len(children), 2)
        self.assertTrue(children[0].tag.endswith('ContactPerson'))
        self.assertTrue(children[1].tag.endswith('Telephone'))

        contact_person = contact_elem.find('ns:ContactPerson', namespace)
        self.assertIsNotNone(contact_person)
        self.assertEqual(contact_person.find('ns:FirstName', namespace).text, 'Unknown')
        self.assertEqual(contact_person.find('ns:LastName', namespace).text, 'Contact')
        self.assertEqual(contact_person.find('ns:OtherTitles', namespace).text, 'Contact')

    def test_gl_entries_use_standard_account_id(self):
        """GL transaction lines should prefer the standard account ID over reporting code."""
        data = {
            'journals': [
                {
                    'Id': 'J1',
                    'Name': 'Actual Journal Name',
                    'c2g__JournalDate__c': '2025-05-15',
                    'c2g__Reference__c': 'Journal Entry',
                }
            ],
            'journal_lines': [
                {
                    'c2g__Journal__c': 'J1',
                    'c2g__Debits__c': 10,
                    'c2g__Credits__c': 0,
                    'c2g__GeneralLedgerAccount__r.c2g__StandardAccountID__c': '5030',
                    'c2g__GeneralLedgerAccount__r.c2g__ReportingCode__c': '5030019',
                    'c2g__LineDescription__c': 'Test line',
                }
            ],
        }

        transformed = self.transformer._transform_gl_entries(data)

        self.assertEqual(transformed[0]['journal_id'], 'Actual Journal Name')
        self.assertEqual(transformed[0]['lines'][0]['account_id'], '5030')

    def test_journal_xml_uses_transformed_journal_name_for_journal_id(self):
        """JournalID should be written from the transformed journal Name field."""
        generator = SAFTGenerator({})
        root = ET.Element(f"{{{generator.NAMESPACE}}}Root")

        generator._add_journal_entry(root, {
            'journal_id': 'Sales Journal',
            'transaction_id': '1',
            'period': 5,
            'period_year': 2025,
            'transaction_date': '2025-05-15',
            'transaction_type': 'Normal',
            'description': 'Journal Entry',
            'system_entry_date': '2025-05-15',
            'gl_posting_date': '2025-05-15',
            'source_id': 'J1',
            'batch_id': '0',
            'customer_id': '0',
            'supplier_id': '0',
            'system_id': 'J1',
            'lines': [
                {
                    'record_id': '1',
                    'account_id': '5030',
                    'taxpayer_account_id': '5030',
                    'debit_amount': 10.0,
                    'credit_amount': 0.0,
                    'description': 'Test line',
                    'value_date': '2025-05-15',
                    'source_document_id': 'J1',
                    'customer_id': '0',
                    'supplier_id': '0',
                    'currency_code': 'BGN',
                    'exchange_rate': '1.0000',
                    'tax_type': '',
                    'tax_code': '',
                    'tax_percentage': 0,
                    'tax_base': 0,
                    'tax_base_description': '',
                    'tax_amount': 0,
                    'tax_exemption_reason': '',
                    'tax_declaration_period': '',
                }
            ],
        })

        namespace = {'ns': generator.NAMESPACE}
        journal_id = root.find('ns:Journal/ns:JournalID', namespace)

        self.assertIsNotNone(journal_id)
        self.assertEqual(journal_id.text, 'Sales Journal')

    def test_gl_transaction_line_writes_description_before_amount_even_when_blank(self):
        """GL TransactionLine must include Description before DebitAmount even for blank descriptions."""
        generator = SAFTGenerator({})
        root = ET.Element(f"{{{generator.NAMESPACE}}}Root")

        generator._add_journal_entry(root, {
            'journal_id': 'Sales Journal',
            'journal_description': 'General ledger',
            'type': 'GLEntry',
            'transaction_id': '1',
            'period': 5,
            'period_year': 2025,
            'transaction_date': '2025-05-15',
            'transaction_type': 'Normal',
            'description': '',
            'system_entry_date': '2025-05-15',
            'gl_posting_date': '2025-05-15',
            'source_id': 'J1',
            'batch_id': '0',
            'customer_id': '0',
            'supplier_id': '0',
            'system_id': 'J1',
            'lines': [
                {
                    'record_id': '1',
                    'account_id': '60205',
                    'taxpayer_account_id': '60205',
                    'debit_amount': 48.0,
                    'credit_amount': 0.0,
                    'description': '',
                    'value_date': '2025-05-15',
                    'source_document_id': 'J1',
                    'customer_id': '0',
                    'supplier_id': '0',
                    'currency_code': 'BGN',
                    'exchange_rate': '1.0000',
                    'tax_type': '',
                    'tax_code': '',
                    'tax_percentage': 0,
                    'tax_base': 0,
                    'tax_base_description': '',
                    'tax_amount': 0,
                    'tax_exemption_reason': '',
                    'tax_declaration_period': '',
                }
            ],
        })

        namespace = {'ns': generator.NAMESPACE}
        line_elem = root.find('ns:Journal/ns:Transaction/ns:TransactionLine', namespace)

        self.assertIsNotNone(line_elem)
        child_names = [child.tag.rsplit('}', 1)[-1] for child in line_elem]
        self.assertIn('Description', child_names)
        self.assertLess(child_names.index('Description'), child_names.index('DebitAmount'))

    def test_purchase_invoice_line_writes_description_before_amount(self):
        """Purchase invoice lines must include Description before InvoiceLineAmount."""
        generator = SAFTGenerator({})
        root = ET.Element(f"{{{generator.NAMESPACE}}}Root")

        generator._add_purchase_invoices(root, [{
            'invoice_no': 'PINV-1',
            'invoice_date': '2025-05-15',
            'period': 5,
            'period_year': 2025,
            'gl_posting_date': '2025-05-15',
            'supplier_id': 'SUP-1',
            'supplier_name': 'Supplier 1',
            'total_debit': 100.0,
            'total_credit': 0.0,
            'lines': [{
                'line_number': '1',
                'account_id': '60205',
                'product_code': 'P1',
                'product_description': 'Product 1',
                'quantity': 1,
                'unit_price': 100,
                'line_amount': 100,
                'debit_credit_indicator': 'D',
                'tax_amount': 20,
                'description': '',
            }],
        }])

        namespace = {'ns': generator.NAMESPACE}
        line_elem = root.find('ns:Invoice/ns:InvoiceLine', namespace)

        self.assertIsNotNone(line_elem)
        child_names = [child.tag.rsplit('}', 1)[-1] for child in line_elem]
        self.assertIn('Description', child_names)
        self.assertLess(child_names.index('Description'), child_names.index('InvoiceLineAmount'))
        self.assertNotIn('DebitAmount', child_names)
        self.assertNotIn('CreditAmount', child_names)

    def test_purchase_invoice_line_falls_back_to_product_code_before_quantity(self):
        """Purchase invoice lines must always emit ProductCode before Quantity."""
        generator = SAFTGenerator({})
        root = ET.Element(f"{{{generator.NAMESPACE}}}Root")

        generator._add_purchase_invoices(root, [{
            'invoice_no': 'PINV-2',
            'account_id': '401',
            'invoice_date': '2025-05-15',
            'period': 5,
            'period_year': 2025,
            'gl_posting_date': '2025-05-15',
            'supplier_id': 'SUP-1',
            'supplier_name': 'Supplier 1',
            'total_debit': 100.0,
            'total_credit': 0.0,
            'lines': [{
                'line_number': '7',
                'account_id': '60205',
                'quantity': 1,
                'unit_price': 100,
                'line_amount': 100,
                'debit_credit_indicator': 'D',
                'description': 'Fallback product code line',
            }],
        }])

        namespace = {'ns': generator.NAMESPACE}
        line_elem = root.find('ns:Invoice/ns:InvoiceLine', namespace)

        self.assertIsNotNone(line_elem)
        child_names = [child.tag.rsplit('}', 1)[-1] for child in line_elem]
        self.assertIn('ProductCode', child_names)
        self.assertLess(child_names.index('ProductCode'), child_names.index('Quantity'))
        self.assertEqual(line_elem.find('ns:ProductCode', namespace).text, '60205')

    def test_purchase_invoice_uses_invoice_document_totals(self):
        """Purchase invoices must emit InvoiceDocumentTotals instead of DocumentTotals."""
        generator = SAFTGenerator({})
        root = ET.Element(f"{{{generator.NAMESPACE}}}Root")

        generator._add_purchase_invoices(root, [{
            'invoice_no': 'PINV-3',
            'account_id': '401',
            'invoice_date': '2025-05-15',
            'period': 5,
            'period_year': 2025,
            'gl_posting_date': '2025-05-15',
            'supplier_id': 'SUP-1',
            'supplier_name': 'Supplier 1',
            'total_debit': 100.0,
            'total_credit': 0.0,
            'lines': [],
        }])

        namespace = {'ns': generator.NAMESPACE}
        invoice_elem = root.find('ns:Invoice', namespace)

        self.assertIsNotNone(invoice_elem)
        self.assertIsNotNone(invoice_elem.find('ns:InvoiceDocumentTotals', namespace))
        self.assertIsNone(invoice_elem.find('ns:DocumentTotals', namespace))

    def test_purchase_invoice_line_always_includes_tax_information(self):
        """Purchase invoice lines must include TaxInformation even when tax amount is zero."""
        generator = SAFTGenerator({})
        root = ET.Element(f"{{{generator.NAMESPACE}}}Root")

        generator._add_purchase_invoices(root, [{
            'invoice_no': 'PINV-4',
            'account_id': '401',
            'invoice_date': '2025-05-15',
            'period': 5,
            'period_year': 2025,
            'gl_posting_date': '2025-05-15',
            'supplier_id': 'SUP-1',
            'supplier_name': 'Supplier 1',
            'total_debit': 100.0,
            'total_credit': 0.0,
            'lines': [{
                'line_number': '1',
                'account_id': '60205',
                'product_code': 'P1',
                'quantity': 1,
                'unit_price': 100,
                'line_amount': 100,
                'debit_credit_indicator': 'D',
                'tax_amount': 0,
                'description': 'Zero tax line',
            }],
        }])

        namespace = {'ns': generator.NAMESPACE}
        line_elem = root.find('ns:Invoice/ns:InvoiceLine', namespace)
        tax_info = line_elem.find('ns:TaxInformation', namespace)

        self.assertIsNotNone(tax_info)
        self.assertEqual(tax_info.find('ns:TaxType', namespace).text, '100010')
        self.assertEqual(tax_info.find('ns:TaxCode', namespace).text, '110010')
        self.assertEqual(tax_info.find('ns:TaxAmount/ns:Amount', namespace).text, '0.00')

    def test_purchase_invoice_writes_supplier_info_before_invoice_date(self):
        """Purchase invoices must write the header fields in schema order."""
        generator = SAFTGenerator({})
        root = ET.Element(f"{{{generator.NAMESPACE}}}Root")

        generator._add_purchase_invoices(root, [{
            'invoice_no': 'PINV-1',
            'account_id': '401',
            'invoice_date': '2025-05-15',
            'period': 5,
            'period_year': 2025,
            'gl_posting_date': '2025-05-15',
            'supplier_id': 'SUP-1',
            'supplier_name': 'Supplier 1',
            'total_debit': 100.0,
            'total_credit': 0.0,
            'lines': [],
        }])

        namespace = {'ns': generator.NAMESPACE}
        invoice_elem = root.find('ns:Invoice', namespace)

        self.assertIsNotNone(invoice_elem)
        child_names = [child.tag.rsplit('}', 1)[-1] for child in invoice_elem]
        self.assertIn('SupplierInfo', child_names)
        self.assertIn('AccountID', child_names)
        self.assertIn('BranchStoreNumber', child_names)
        self.assertIn('Period', child_names)
        self.assertIn('PeriodYear', child_names)
        self.assertIn('InvoiceDate', child_names)
        self.assertIn('SelfBillingIndicator', child_names)
        self.assertIn('TransactionID', child_names)
        self.assertLess(child_names.index('SupplierInfo'), child_names.index('InvoiceDate'))
        self.assertLess(child_names.index('SupplierInfo'), child_names.index('AccountID'))
        self.assertLess(child_names.index('AccountID'), child_names.index('BranchStoreNumber'))
        self.assertLess(child_names.index('BranchStoreNumber'), child_names.index('Period'))
        self.assertLess(child_names.index('Period'), child_names.index('PeriodYear'))
        self.assertLess(child_names.index('PeriodYear'), child_names.index('InvoiceDate'))
        self.assertLess(child_names.index('InvoiceType'), child_names.index('SelfBillingIndicator'))
        self.assertLess(child_names.index('SelfBillingIndicator'), child_names.index('TransactionID'))

        namespace = {'ns': generator.NAMESPACE}
        supplier_info = invoice_elem.find('ns:SupplierInfo', namespace)
        self.assertIsNotNone(supplier_info)
        self.assertIsNotNone(supplier_info.find('ns:Name', namespace))
        self.assertIsNone(supplier_info.find('ns:SupplierName', namespace))
        self.assertIsNotNone(supplier_info.find('ns:BillingAddress', namespace))

    def test_purchase_invoices_use_payable_control_account_for_invoice_account_id(self):
        """Purchase invoice header AccountID should come from the supplier payable control account."""
        data = {
            'purchase_invoices': [{
                'Id': 'PI1',
                'Name': 'PINV-1',
                'c2g__InvoiceDate__c': '2025-05-15',
                'c2g__Account__r.Name': 'Supplier 1',
                'c2g__Account__r.c2g__CODATaxpayerIdentificationNumber__c': 'SUP-1',
                'c2g__Account__r.c2g__CODAAccountsPayableControl__r.c2g__StandardAccountID__c': '401',
                'c2g__Account__r.c2g__CODAAccountsPayableControl__r.c2g__ReportingCode__c': '4010001',
            }],
            'purchase_invoice_lines': [{
                'c2g__PurchaseInvoice__c': 'PI1',
                'c2g__NetValue__c': 100,
                'c2g__TaxValue1__c': 20,
                'F_Quantity__c': 1,
                'c2g__LineDescription__c': 'Line',
                'c2g__GeneralLedgerAccount__r': {
                    'c2g__StandardAccountID__c': '60205',
                    'c2g__ReportingCode__c': '6020501',
                },
                'F_Product__r': {
                    'ProductCode': 'P1',
                    'Name': 'Product 1',
                },
            }],
        }

        transformed = self.transformer._transform_purchase_invoices(data)

        self.assertEqual(transformed[0]['account_id'], '401')
        self.assertEqual(transformed[0]['supplier_name'], 'Supplier 1')

    def test_gl_entries_use_nested_standard_account_id_from_rest_query(self):
        """GL journal lines from REST queries should read the nested standard account ID."""
        data = {
            'journals': [
                {
                    'Id': 'J1',
                    'c2g__JournalDate__c': '2025-05-15',
                    'c2g__Reference__c': 'Journal Entry',
                }
            ],
            'journal_lines': [
                {
                    'c2g__Journal__c': 'J1',
                    'c2g__Debits__c': 10,
                    'c2g__Credits__c': 0,
                    'c2g__GeneralLedgerAccount__r': {
                        'c2g__StandardAccountID__c': '629',
                        'c2g__ReportingCode__c': '629002',
                    },
                    'c2g__LineDescription__c': 'Bank charges on wire transfers',
                }
            ],
        }

        transformed = self.transformer._transform_gl_entries(data)

        self.assertEqual(transformed[0]['lines'][0]['account_id'], '629')

    def test_gl_entries_keep_lines_without_standard_account_id(self):
        """GL transaction lines without a standard account ID should still be kept with fallback account data."""
        data = {
            'journals': [
                {
                    'Id': 'J1',
                    'c2g__JournalDate__c': '2025-05-15',
                    'c2g__Reference__c': 'Journal Entry',
                }
            ],
            'journal_lines': [
                {
                    'Id': 'JL1',
                    'c2g__Journal__c': 'J1',
                    'c2g__Debits__c': 10,
                    'c2g__Credits__c': 0,
                    'c2g__GeneralLedgerAccount__r.c2g__ReportingCode__c': '5030029',
                    'c2g__LineDescription__c': 'Invalid fallback line',
                }
            ],
        }

        transformed = self.transformer._transform_gl_entries(data)

        self.assertEqual(len(transformed), 1)
        self.assertEqual(len(transformed[0]['lines']), 1)
        self.assertEqual(transformed[0]['lines'][0]['account_id'], '5030029')

    def test_payment_lines_use_standard_account_id(self):
        """Payment lines should use the related account control account ID."""
        data = {
            'payments': [
                {
                    'Id': 'PAY1',
                    'Name': 'PAY-1',
                    'c2g__Date__c': '2025-05-15',
                    'c2g__Reference__c': 'Payment',
                    'c2g__Type__c': 'Receipt',
                    'c2g__Account__r': {
                        'Name': 'Customer A',
                        'c2g__CODATaxpayerIdentificationNumber__c': 'BG123',
                    },
                }
            ],
            'payment_lines': [
                {
                    'c2g__CashEntry__c': 'PAY1',
                    'c2g__CashEntryValue__c': 10,
                    'c2g__NetValue__c': 10,
                    'c2g__LineDescription__c': 'Payment line',
                    'c2g__Account__r': {
                        'Name': 'Customer A',
                        'c2g__CODATaxpayerIdentificationNumber__c': 'BG123',
                        'c2g__CODAAccountsReceivableControl__r': {
                            'c2g__StandardAccountID__c': '411',
                            'c2g__ReportingCode__c': '4110001',
                        },
                    },
                }
            ],
        }

        transformed = self.transformer._transform_payments(data)

        self.assertEqual(transformed[0]['lines'][0]['account_id'], '411')

    def test_address_normalizes_country_name_to_iso_code(self):
        """Customer and supplier address countries must be ISO alpha-2 codes."""
        generator = SAFTGenerator({})
        root = ET.Element(f"{{{generator.NAMESPACE}}}Root")

        generator._add_address(root, {
            'street': '1 Test Street',
            'city': 'Budapest',
            'postal_code': '1000',
            'country': 'Hungary',
        })

        namespace = {'ns': generator.NAMESPACE}
        country_elem = root.find('ns:Address/ns:Country', namespace)

        self.assertIsNotNone(country_elem)
        self.assertEqual(country_elem.text, 'HU')

    def test_address_normalizes_additional_country_names_to_iso_code(self):
        """Additional country names from validator output must normalize to ISO alpha-2."""
        generator = SAFTGenerator({})

        expected_codes = {
            'Brazil': 'BR',
            'India': 'IN',
            'Italy': 'IT',
            'Romania': 'RO',
            'Saudi Arabia': 'SA',
            'Singapore': 'SG',
            'Spain': 'ES',
            'Turkey': 'TR',
        }

        for country_name, expected_code in expected_codes.items():
            with self.subTest(country=country_name):
                root = ET.Element(f"{{{generator.NAMESPACE}}}Root")
                generator._add_address(root, {
                    'street': '1 Test Street',
                    'city': 'Test City',
                    'postal_code': '1000',
                    'country': country_name,
                })

                namespace = {'ns': generator.NAMESPACE}
                country_elem = root.find('ns:Address/ns:Country', namespace)

                self.assertIsNotNone(country_elem)
                self.assertEqual(country_elem.text, expected_code)

    def test_address_normalizes_common_country_aliases_to_iso_code(self):
        """Non-ISO aliases should still normalize correctly with the pycountry-based lookup."""
        generator = SAFTGenerator({})

        expected_codes = {
            'UK': 'GB',
            'USA': 'US',
            'Great Britain': 'GB',
        }

        for country_name, expected_code in expected_codes.items():
            with self.subTest(country=country_name):
                root = ET.Element(f"{{{generator.NAMESPACE}}}Root")
                generator._add_address(root, {
                    'street': '1 Test Street',
                    'city': 'Test City',
                    'postal_code': '1000',
                    'country': country_name,
                })

                namespace = {'ns': generator.NAMESPACE}
                country_elem = root.find('ns:Address/ns:Country', namespace)

                self.assertIsNotNone(country_elem)
                self.assertEqual(country_elem.text, expected_code)

    def test_address_normalizes_legacy_country_name_to_iso_code(self):
        """Legacy country names should normalize before the pycountry lookup."""
        generator = SAFTGenerator({})
        root = ET.Element(f"{{{generator.NAMESPACE}}}Root")

        generator._add_address(root, {
            'street': '1 Test Street',
            'city': 'Istanbul',
            'postal_code': '34000',
            'country': 'turkey',
        })

        namespace = {'ns': generator.NAMESPACE}
        country_elem = root.find('ns:Address/ns:Country', namespace)

        self.assertIsNotNone(country_elem)
        self.assertEqual(country_elem.text, 'TR')

    def test_sales_invoice_customer_info_uses_billing_address(self):
        """Sales invoice CustomerInfo must emit BillingAddress instead of Address."""
        generator = SAFTGenerator({})
        root = ET.Element(f"{{{generator.NAMESPACE}}}Root")

        generator._add_sales_invoices(root, [{
            'invoice_no': 'BD-1',
            'customer_id': 'CUST-1',
            'customer_name': 'Customer 1',
            'period': 2,
            'period_year': 2026,
            'invoice_date': '2026-02-03',
            'gl_posting_date': '2026-02-03',
            'system_id': 'INV-1',
            'total_debit': 0,
            'total_credit': 100,
            'lines': [{
                'line_number': '1',
                'account_id': '411',
                'product_code': 'P1',
                'product_description': 'Product',
                'quantity': 1,
                'unit_price': 100,
                'description': 'Line',
                'line_amount': 100,
                'debit_credit_indicator': 'C',
                'tax_amount': 20,
            }],
        }])

        namespace = {'ns': generator.NAMESPACE}
        customer_info = root.find('ns:Invoice/ns:CustomerInfo', namespace)

        self.assertIsNotNone(customer_info)
        self.assertIsNotNone(customer_info.find('ns:BillingAddress', namespace))
        self.assertIsNone(customer_info.find('ns:Address', namespace))

    def test_address_truncates_street_name_to_xsd_limit(self):
        """StreetName must be capped at the 70-character XSD limit."""
        generator = SAFTGenerator({})
        root = ET.Element(f"{{{generator.NAMESPACE}}}Root")
        long_street = "zh.k. Iztok, ul. Lachezar Stanchev No 5, Sopharma Business Towers, floor 12"

        generator._add_address(root, {
            'street_name': long_street,
            'city': 'Sofia',
            'postal_code': '1000',
            'country': 'Bulgaria',
        })

        namespace = {'ns': generator.NAMESPACE}
        street_elem = root.find('ns:Address/ns:StreetName', namespace)

        self.assertIsNotNone(street_elem)
        self.assertEqual(len(street_elem.text), 70)
        self.assertEqual(street_elem.text, long_street[:70])

    def test_customer_company_structure_includes_tax_registration_and_related_party(self):
        """Customer CompanyStructure must include tax registration details and RelatedParty."""
        generator = SAFTGenerator({})
        root = ET.Element(f"{{{generator.NAMESPACE}}}Root")

        generator._add_customers(root, [{
            'customer_id': 'CUST-1',
            'account_id': '411',
            'customer_tax_id': 'BG123456789',
            'company_name': 'Test Customer',
            'billing_address': {
                'street_name': '1 Test Street',
                'city': 'Sofia',
                'postal_code': '1000',
                'country': 'Bulgaria',
            },
            'opening_debit_balance': 10.0,
            'opening_credit_balance': 0.0,
            'closing_debit_balance': 10.0,
            'closing_credit_balance': 0.0,
        }])

        namespace = {'ns': generator.NAMESPACE}
        company_struct = root.find('ns:Customer/ns:CompanyStructure', namespace)

        self.assertIsNotNone(company_struct)
        self.assertEqual(
            company_struct.find('ns:TaxRegistration/ns:TaxRegistrationNumber', namespace).text,
            'BG123456789',
        )
        self.assertEqual(company_struct.find('ns:RelatedParty', namespace).text, 'N')

    def test_tax_table_entry_writes_description_before_tax_code_details(self):
        """TaxTableEntry must emit Description before nested TaxCodeDetails."""
        generator = SAFTGenerator({})
        root = ET.Element(f"{{{generator.NAMESPACE}}}Root")

        generator._add_tax_table(root, [{
            'tax_type': '100010',
            'tax_code': '110010',
            'tax_percentage': 20,
            'description': 'Standard VAT',
        }])

        namespace = {'ns': generator.NAMESPACE}
        tax_entry = root.find('ns:TaxTableEntry', namespace)

        self.assertIsNotNone(tax_entry)
        children = list(tax_entry)
        self.assertEqual(children[0].tag.split('}')[-1], 'TaxType')
        self.assertEqual(children[1].tag.split('}')[-1], 'Description')
        self.assertEqual(children[2].tag.split('}')[-1], 'TaxCodeDetails')

        details = tax_entry.find('ns:TaxCodeDetails', namespace)
        self.assertIsNotNone(details)
        self.assertEqual(details.find('ns:TaxCode', namespace).text, '110010')
        self.assertEqual(details.find('ns:Description', namespace).text, 'Standard VAT')
        self.assertEqual(details.find('ns:TaxPercentage', namespace).text, '20.00')
        self.assertEqual(details.find('ns:BaseRate', namespace).text, '0.20')
        self.assertEqual(details.find('ns:Country', namespace).text, 'BG')
    
    def test_opening_excludes_current_period(self):
        """Opening balance should not include current period"""
        transaction_lines = [
            {
                'c2g__GeneralLedgerAccount__c': 'GL001',
                'c2g__HomeValue__c': 100.0,
                'c2g__Transaction__r': {
                    'c2g__Period__r': {
                        'Name': '2025/004',
                        'c2g__PeriodNumber__c': 4,
                        'c2g__YearName__c': '2025'
                    }
                }
            },
            {
                'c2g__GeneralLedgerAccount__c': 'GL001',
                'c2g__HomeValue__c': 200.0,
                'c2g__Transaction__r': {
                    'c2g__Period__r': {
                        'Name': '2025/005',
                        'c2g__PeriodNumber__c': 5,
                        'c2g__YearName__c': '2025'
                    }
                }
            }
        ]
        
        gl_account_codes = {'GL001': '100001'}
        gl_balances, _ = self.transformer._calculate_all_balances(transaction_lines, gl_account_codes)
        
        # Opening should be 100 (period 4 only)
        self.assertEqual(gl_balances['GL001']['opening_debit_balance'], 100.0)
        # Closing should be 300 (periods 4+5)
        self.assertEqual(gl_balances['GL001']['closing_debit_balance'], 300.0)
    
    def test_closing_includes_through_end_period(self):
        """Closing balance should include all through end period"""
        transaction_lines = [
            {'c2g__GeneralLedgerAccount__c': 'GL001', 'c2g__HomeValue__c': 100.0,
             'c2g__Transaction__r': {'c2g__Period__r': {'Name': '2025/004', 'c2g__PeriodNumber__c': 4, 'c2g__YearName__c': '2025'}}},
            {'c2g__GeneralLedgerAccount__c': 'GL001', 'c2g__HomeValue__c': 200.0,
             'c2g__Transaction__r': {'c2g__Period__r': {'Name': '2025/005', 'c2g__PeriodNumber__c': 5, 'c2g__YearName__c': '2025'}}},
            {'c2g__GeneralLedgerAccount__c': 'GL001', 'c2g__HomeValue__c': 300.0,
             'c2g__Transaction__r': {'c2g__Period__r': {'Name': '2025/006', 'c2g__PeriodNumber__c': 6, 'c2g__YearName__c': '2025'}}}
        ]
        
        gl_account_codes = {'GL001': '100001'}
        gl_balances, _ = self.transformer._calculate_all_balances(transaction_lines, gl_account_codes)
        
        # Closing should NOT include period 6
        self.assertEqual(gl_balances['GL001']['closing_debit_balance'], 300.0)  # Only 4+5
    
    def test_mixed_debit_credit_net_calculation(self):
        """Mixed debits and credits should net correctly"""
        transaction_lines = [
            {'c2g__GeneralLedgerAccount__c': 'GL001', 'c2g__HomeValue__c': 500.0,
             'c2g__Transaction__r': {'c2g__Period__r': {'Name': '2025/005', 'c2g__PeriodNumber__c': 5, 'c2g__YearName__c': '2025'}}},
            {'c2g__GeneralLedgerAccount__c': 'GL001', 'c2g__HomeValue__c': -300.0,
             'c2g__Transaction__r': {'c2g__Period__r': {'Name': '2025/005', 'c2g__PeriodNumber__c': 5, 'c2g__YearName__c': '2025'}}},
            {'c2g__GeneralLedgerAccount__c': 'GL001', 'c2g__HomeValue__c': 100.0,
             'c2g__Transaction__r': {'c2g__Period__r': {'Name': '2025/005', 'c2g__PeriodNumber__c': 5, 'c2g__YearName__c': '2025'}}}
        ]
        
        gl_account_codes = {'GL001': '100001'}
        gl_balances, _ = self.transformer._calculate_all_balances(transaction_lines, gl_account_codes)
        
        # Net: 500 - 300 + 100 = 300 (positive = debit)
        self.assertEqual(gl_balances['GL001']['closing_debit_balance'], 300.0)
        self.assertEqual(gl_balances['GL001']['closing_credit_balance'], 0.0)
    
    def test_zero_balance_accounts_included_in_calculation(self):
        """Zero balance accounts should still be in results"""
        transaction_lines = [
            {'c2g__GeneralLedgerAccount__c': 'GL001', 'c2g__HomeValue__c': 100.0,
             'c2g__Transaction__r': {'c2g__Period__r': {'Name': '2025/003', 'c2g__PeriodNumber__c': 3, 'c2g__YearName__c': '2025'}}},
            {'c2g__GeneralLedgerAccount__c': 'GL001', 'c2g__HomeValue__c': -100.0,
             'c2g__Transaction__r': {'c2g__Period__r': {'Name': '2025/004', 'c2g__PeriodNumber__c': 4, 'c2g__YearName__c': '2025'}}}
        ]
        
        gl_account_codes = {'GL001': '100001'}
        gl_balances, _ = self.transformer._calculate_all_balances(transaction_lines, gl_account_codes)
        
        # Should have entry even with zero balance
        self.assertIn('GL001', gl_balances)
        # All balances should be zero
        opening_sum = gl_balances['GL001']['opening_debit_balance'] + gl_balances['GL001']['opening_credit_balance']
        closing_sum = gl_balances['GL001']['closing_debit_balance'] + gl_balances['GL001']['closing_credit_balance']
        self.assertAlmostEqual(opening_sum, 0.0, places=2)
        self.assertAlmostEqual(closing_sum, 0.0, places=2)
    
    def test_multi_period_range_calculation(self):
        """Multi-period range (Q1) should calculate correctly"""
        transaction_lines = [
            {'c2g__GeneralLedgerAccount__c': 'GL001', 'c2g__HomeValue__c': 1000.0,
             'c2g__Transaction__r': {'c2g__Period__r': {'Name': '2024/012', 'c2g__PeriodNumber__c': 12, 'c2g__YearName__c': '2024'}}},
            {'c2g__GeneralLedgerAccount__c': 'GL001', 'c2g__HomeValue__c': 100.0,
             'c2g__Transaction__r': {'c2g__Period__r': {'Name': '2025/001', 'c2g__PeriodNumber__c': 1, 'c2g__YearName__c': '2025'}}},
            {'c2g__GeneralLedgerAccount__c': 'GL001', 'c2g__HomeValue__c': 200.0,
             'c2g__Transaction__r': {'c2g__Period__r': {'Name': '2025/002', 'c2g__PeriodNumber__c': 2, 'c2g__YearName__c': '2025'}}},
            {'c2g__GeneralLedgerAccount__c': 'GL001', 'c2g__HomeValue__c': 300.0,
             'c2g__Transaction__r': {'c2g__Period__r': {'Name': '2025/003', 'c2g__PeriodNumber__c': 3, 'c2g__YearName__c': '2025'}}},
            {'c2g__GeneralLedgerAccount__c': 'GL001', 'c2g__HomeValue__c': 400.0,
             'c2g__Transaction__r': {'c2g__Period__r': {'Name': '2025/004', 'c2g__PeriodNumber__c': 4, 'c2g__YearName__c': '2025'}}}
        ]
        
        # Change config to Q1 (periods 1-3)
        self.transformer.config['period_from'] = '001'
        self.transformer.config['period_to'] = '003'
        self.transformer.config['saft']['selection_start_date'] = '2025-01-01'
        self.transformer.config['saft']['selection_end_date'] = '2025-03-31'
        self.transformer._period_info_cache = None
        
        gl_account_codes = {'GL001': '100001'}
        gl_balances, _ = self.transformer._calculate_all_balances(transaction_lines, gl_account_codes)
        
        # Opening: Dec 2024 = 1000
        self.assertEqual(gl_balances['GL001']['opening_debit_balance'], 1000.0)
        # Closing: Dec 2024 + Q1 2025 = 1000 + 100 + 200 + 300 = 1600
        self.assertEqual(gl_balances['GL001']['closing_debit_balance'], 1600.0)
    
    def test_multiple_accounts_independent(self):
        """Multiple accounts should calculate independently"""
        transaction_lines = [
            {'c2g__GeneralLedgerAccount__c': 'GL001', 'c2g__HomeValue__c': 1000.0,
             'c2g__Transaction__r': {'c2g__Period__r': {'Name': '2025/004', 'c2g__PeriodNumber__c': 4, 'c2g__YearName__c': '2025'}}},
            {'c2g__GeneralLedgerAccount__c': 'GL002', 'c2g__HomeValue__c': -500.0,
             'c2g__Transaction__r': {'c2g__Period__r': {'Name': '2025/004', 'c2g__PeriodNumber__c': 4, 'c2g__YearName__c': '2025'}}},
            {'c2g__GeneralLedgerAccount__c': 'GL001', 'c2g__HomeValue__c': 200.0,
             'c2g__Transaction__r': {'c2g__Period__r': {'Name': '2025/005', 'c2g__PeriodNumber__c': 5, 'c2g__YearName__c': '2025'}}},
            {'c2g__GeneralLedgerAccount__c': 'GL002', 'c2g__HomeValue__c': -100.0,
             'c2g__Transaction__r': {'c2g__Period__r': {'Name': '2025/005', 'c2g__PeriodNumber__c': 5, 'c2g__YearName__c': '2025'}}}
        ]
        
        gl_account_codes = {'GL001': '100001', 'GL002': '200001'}
        gl_balances, _ = self.transformer._calculate_all_balances(transaction_lines, gl_account_codes)
        
        # GL001: 1000 + 200 = 1200 debit
        self.assertEqual(gl_balances['GL001']['closing_debit_balance'], 1200.0)
        self.assertEqual(gl_balances['GL001']['closing_credit_balance'], 0.0)
        
        # GL002: -500 + -100 = -600 = 600 credit
        self.assertEqual(gl_balances['GL002']['closing_debit_balance'], 0.0)
        self.assertEqual(gl_balances['GL002']['closing_credit_balance'], 600.0)

    def test_header_uses_xsd_date_for_audit_file_created(self):
        """AuditFileDateCreated must be YYYY-MM-DD for the BG SAF-T XSD."""
        self.transformer.config['saft'].update({
            'software_company_name': 'Scale Focus',
            'software_product_name': 'SAFT Reporting',
            'software_product_version': '1.0.0',
            'fiscal_year': '2026',
            'header_comment': 'M',
        })

        header = self.transformer._transform_header({'company': [{}]})

        self.assertRegex(header['audit_file_date_created'], r'^\d{4}-\d{2}-\d{2}$')
        self.assertNotIn('T', header['audit_file_date_created'])

    def test_header_company_omits_name_latin(self):
        """Header Company must go from Name directly to Address in BG SAF-T."""
        generator = SAFTGenerator({})
        root = ET.Element(f"{{{generator.NAMESPACE}}}AuditFile")
        header = {
            'audit_file_version': '1.0',
            'audit_file_country': 'BG',
            'audit_file_date_created': '2026-03-20',
            'software_company_name': 'Scale Focus',
            'software_product_name': 'SAFT Reporting',
            'software_product_version': '1.0.0',
            'company': {
                'registration_number': '123456789',
                'name': 'Тест Компания',
                'name_latin': 'Test Company',
                'street': '1 Test Street',
                'city': 'Sofia',
                'postal_code': '1000',
                'country': 'BG',
                'telephone': '123456789',
                'email': 'test@example.com',
                'website': 'example.com',
                'iban': 'BG00TEST12345678901234',
            },
            'header_comment': 'M',
            'tax_accounting_basis': 'A',
        }

        generator._add_header(root, header, datetime(2026, 3, 1), datetime(2026, 3, 31))

        namespace = {'ns': generator.NAMESPACE}
        company_elem = root.find('ns:Header/ns:Company', namespace)

        self.assertIsNotNone(company_elem)
        self.assertIsNone(company_elem.find('ns:NameLatin', namespace))
        self.assertIsNotNone(company_elem.find('ns:Address', namespace))
    
    def test_rounding_precision_maintained(self):
        """Floating point precision should be maintained"""
        transaction_lines = [
            {'c2g__GeneralLedgerAccount__c': 'GL001', 'c2g__HomeValue__c': 33.33,
             'c2g__Transaction__r': {'c2g__Period__r': {'Name': '2025/004', 'c2g__PeriodNumber__c': 4, 'c2g__YearName__c': '2025'}}},
            {'c2g__GeneralLedgerAccount__c': 'GL001', 'c2g__HomeValue__c': 33.33,
             'c2g__Transaction__r': {'c2g__Period__r': {'Name': '2025/005', 'c2g__PeriodNumber__c': 5, 'c2g__YearName__c': '2025'}}},
            {'c2g__GeneralLedgerAccount__c': 'GL001', 'c2g__HomeValue__c': 33.34,
             'c2g__Transaction__r': {'c2g__Period__r': {'Name': '2025/005', 'c2g__PeriodNumber__c': 5, 'c2g__YearName__c': '2025'}}}
        ]
        
        gl_account_codes = {'GL001': '100001'}
        gl_balances, _ = self.transformer._calculate_all_balances(transaction_lines, gl_account_codes)
        
        # Opening: 33.33
        self.assertAlmostEqual(gl_balances['GL001']['opening_debit_balance'], 33.33, places=2)
        # Closing: 33.33 + 33.33 + 33.34 = 100.00
        self.assertAlmostEqual(gl_balances['GL001']['closing_debit_balance'], 100.0, places=2)
    
    def test_year_boundary_handling(self):
        """Year boundary transitions should be handled correctly"""
        transaction_lines = [
            {'c2g__GeneralLedgerAccount__c': 'GL001', 'c2g__HomeValue__c': 1000.0,
             'c2g__Transaction__r': {'c2g__Period__r': {'Name': '2024/012', 'c2g__PeriodNumber__c': 12, 'c2g__YearName__c': '2024'}}},
            {'c2g__GeneralLedgerAccount__c': 'GL001', 'c2g__HomeValue__c': 100.0,
             'c2g__Transaction__r': {'c2g__Period__r': {'Name': '2025/001', 'c2g__PeriodNumber__c': 1, 'c2g__YearName__c': '2025'}}},
            {'c2g__GeneralLedgerAccount__c': 'GL001', 'c2g__HomeValue__c': 200.0,
             'c2g__Transaction__r': {'c2g__Period__r': {'Name': '2025/002', 'c2g__PeriodNumber__c': 2, 'c2g__YearName__c': '2025'}}}
        ]
        
        # Report for January 2025
        self.transformer.config['period_from'] = '001'
        self.transformer.config['period_to'] = '001'
        self.transformer.config['saft']['selection_start_date'] = '2025-01-01'
        self.transformer.config['saft']['selection_end_date'] = '2025-01-31'
        self.transformer._period_info_cache = None
        
        gl_account_codes = {'GL001': '100001'}
        gl_balances, _ = self.transformer._calculate_all_balances(transaction_lines, gl_account_codes)
        
        # Opening: 2024/012 is before 2025/001 = 1000
        self.assertEqual(gl_balances['GL001']['opening_debit_balance'], 1000.0)
        # Closing: through 2025/001 = 1000 + 100 = 1100
        self.assertEqual(gl_balances['GL001']['closing_debit_balance'], 1100.0)
    
    def test_balance_sign_flip_between_periods(self):
        """Balance can flip from debit to credit between opening and closing"""
        transaction_lines = [
            {'c2g__GeneralLedgerAccount__c': 'GL001', 'c2g__HomeValue__c': 300.0,
             'c2g__Transaction__r': {'c2g__Period__r': {'Name': '2025/004', 'c2g__PeriodNumber__c': 4, 'c2g__YearName__c': '2025'}}},
            {'c2g__GeneralLedgerAccount__c': 'GL001', 'c2g__HomeValue__c': -1000.0,
             'c2g__Transaction__r': {'c2g__Period__r': {'Name': '2025/005', 'c2g__PeriodNumber__c': 5, 'c2g__YearName__c': '2025'}}}
        ]
        
        gl_account_codes = {'GL001': '100001'}
        gl_balances, _ = self.transformer._calculate_all_balances(transaction_lines, gl_account_codes)
        
        # Opening: +300 = 300 debit
        self.assertEqual(gl_balances['GL001']['opening_debit_balance'], 300.0)
        self.assertEqual(gl_balances['GL001']['opening_credit_balance'], 0.0)
        
        # Closing: 300 - 1000 = -700 = 700 credit
        self.assertEqual(gl_balances['GL001']['closing_debit_balance'], 0.0)
        self.assertEqual(gl_balances['GL001']['closing_credit_balance'], 700.0)
    
    def test_large_number_accuracy(self):
        """Large transaction amounts should maintain accuracy"""
        transaction_lines = [
            {'c2g__GeneralLedgerAccount__c': 'GL001', 'c2g__HomeValue__c': 1234567.89,
             'c2g__Transaction__r': {'c2g__Period__r': {'Name': '2025/004', 'c2g__PeriodNumber__c': 4, 'c2g__YearName__c': '2025'}}},
            {'c2g__GeneralLedgerAccount__c': 'GL001', 'c2g__HomeValue__c': 9876543.21,
             'c2g__Transaction__r': {'c2g__Period__r': {'Name': '2025/005', 'c2g__PeriodNumber__c': 5, 'c2g__YearName__c': '2025'}}}
        ]
        
        gl_account_codes = {'GL001': '100001'}
        gl_balances, _ = self.transformer._calculate_all_balances(transaction_lines, gl_account_codes)
        
        # Opening: 1234567.89
        self.assertAlmostEqual(gl_balances['GL001']['opening_debit_balance'], 1234567.89, places=2)
        # Closing: 1234567.89 + 9876543.21 = 11111111.10
        self.assertAlmostEqual(gl_balances['GL001']['closing_debit_balance'], 11111111.10, places=2)
    
    def test_many_small_transactions_accumulate_correctly(self):
        """Many small transactions should accumulate without rounding errors"""
        transaction_lines = []
        # Add 100 transactions of 1.01 each in current period
        for i in range(100):
            transaction_lines.append({
                'c2g__GeneralLedgerAccount__c': 'GL001',
                'c2g__HomeValue__c': 1.01,
                'c2g__Transaction__r': {
                    'c2g__Period__r': {
                        'Name': '2025/005',
                        'c2g__PeriodNumber__c': 5,
                        'c2g__YearName__c': '2025'
                    }
                }
            })
        
        gl_account_codes = {'GL001': '100001'}
        gl_balances, _ = self.transformer._calculate_all_balances(transaction_lines, gl_account_codes)
        
        # Expected: 100 * 1.01 = 101.00
        self.assertAlmostEqual(gl_balances['GL001']['closing_debit_balance'], 101.0, places=2)


if __name__ == '__main__':
    unittest.main()
