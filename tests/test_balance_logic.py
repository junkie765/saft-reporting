"""Simplified unit tests for GL balance calculation logic"""
import unittest
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from transformers.certinia_transformer import CertiniaTransformer


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
