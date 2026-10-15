import unittest
from unittest.mock import patch, Mock
from main import hh_search, HHAccessUnavailable


class HHApiRetryTests(unittest.TestCase):
    @patch("main.requests.get")
    def test_public_api_success_without_login(self, get):
        get.return_value = Mock(status_code=200, json=lambda: {"items": [], "pages": 1})
        self.assertEqual(hh_search("frontend", "junior React"), [])
        self.assertEqual(get.call_count, 1)

    @patch("main.time.sleep")
    @patch("main.requests.get")
    def test_retries_rate_limit(self, get, sleep):
        get.side_effect = [
            Mock(status_code=429, headers={"Retry-After": "1"}),
            Mock(status_code=200, json=lambda: {"items": [], "pages": 1}),
        ]
        self.assertEqual(hh_search("frontend", "junior React"), [])
        self.assertEqual(get.call_count, 2)
        sleep.assert_called_once_with(1)

    @patch.dict("main.os.environ", {"HH_STORAGE_STATE_JSON": ""})
    @patch("main.requests.get")
    def test_403_without_session_is_reported(self, get):
        get.return_value = Mock(status_code=403)
        with self.assertRaises(HHAccessUnavailable):
            hh_search("frontend", "junior React")

    @patch("main.time.sleep")
    @patch("main.requests.get")
    def test_repeated_server_error_is_reported(self, get, sleep):
        get.return_value = Mock(status_code=503, headers={})
        with self.assertRaises(HHAccessUnavailable):
            hh_search("frontend", "junior React")
        self.assertEqual(get.call_count, 3)


if __name__ == "__main__":
    unittest.main()
