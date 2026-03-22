import io
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from salesforce.rest_client import SalesforceRestClient


class TestSalesforceRestClient(unittest.TestCase):
    def setUp(self):
        self.config = {
            'salesforce': {
                'api_version': '59.0',
                'connect_timeout': 3,
                'read_timeout': 45,
            }
        }
        self.sf_session = SimpleNamespace(sf_instance='example.my.salesforce.com', session_id='token')
        self.client = SalesforceRestClient(self.sf_session, self.config)

    def test_build_nested_record_matches_rest_shape(self):
        row = {
            'Id': '001',
            'Name': 'Sample',
            'c2g__Transaction__r.c2g__Period__r.Name': '2025/005',
            'c2g__Transaction__r.c2g__Period__r.c2g__PeriodNumber__c': '5',
            'EmptyField__c': '',
        }

        record = self.client._build_nested_record(row)

        self.assertEqual(record['Id'], '001')
        self.assertEqual(record['Name'], 'Sample')
        self.assertIsNone(record['EmptyField__c'])
        self.assertEqual(record['c2g__Transaction__r']['c2g__Period__r']['Name'], '2025/005')
        self.assertEqual(record['c2g__Transaction__r']['c2g__Period__r']['c2g__PeriodNumber__c'], '5')

    def test_iter_bulk_records_streams_nested_rows(self):
        class FakeRaw(io.BytesIO):
            pass

        csv_bytes = (
            b'Id,c2g__Transaction__r.c2g__Period__r.Name,EmptyField__c\n'
            b'001,2025/005,\n'
            b'002,2025/006,value\n'
        )
        raw = FakeRaw(csv_bytes)
        raw.decode_content = False
        response = SimpleNamespace(raw=raw)

        records = list(self.client._iter_bulk_records(response))

        self.assertEqual(len(records), 2)
        self.assertEqual(records[0]['Id'], '001')
        self.assertEqual(records[0]['c2g__Transaction__r']['c2g__Period__r']['Name'], '2025/005')
        self.assertIsNone(records[0]['EmptyField__c'])
        self.assertEqual(records[1]['EmptyField__c'], 'value')

    def test_query_rest_uses_shared_session_with_timeout(self):
        first_response = Mock()
        first_response.json.return_value = {
            'records': [{'Id': '001'}],
            'nextRecordsUrl': '/services/data/v59.0/query/01g-next',
        }
        first_response.raise_for_status.return_value = None

        second_response = Mock()
        second_response.json.return_value = {
            'records': [{'Id': '002'}],
        }
        second_response.raise_for_status.return_value = None

        self.client.session.get = Mock(side_effect=[first_response, second_response])

        records = self.client.query_rest('SELECT Id FROM Account', 'accounts')

        self.assertEqual(records, [{'Id': '001'}, {'Id': '002'}])
        self.assertEqual(self.client.session.get.call_count, 2)
        first_call = self.client.session.get.call_args_list[0]
        second_call = self.client.session.get.call_args_list[1]
        self.assertEqual(first_call.kwargs['timeout'], (3, 45))
        self.assertEqual(first_call.kwargs['params'], {'q': 'SELECT Id FROM Account'})
        self.assertEqual(second_call.kwargs['timeout'], (3, 45))
        self.assertIsNone(second_call.kwargs['params'])


if __name__ == '__main__':
    unittest.main()