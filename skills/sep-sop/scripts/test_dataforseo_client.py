#!/usr/bin/env python3
"""Offline contract tests for the direct DataForSEO integration."""
import importlib.util
import json
import pathlib
import unittest
from unittest.mock import patch


HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("dataforseo_client", HERE / "dataforseo_client.py")
dfs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dfs)

spec = importlib.util.spec_from_file_location("mine_round", HERE / "mine_round.py")
mine_round = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mine_round)


class FakeResponse:
    def __init__(self, payload):
        self.payload = json.dumps(payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self.payload


class DataForSEOClientTests(unittest.TestCase):
    def setUp(self):
        self.client = dfs.Client(login="test-login", password="test-password")

    @patch.object(dfs.urllib.request, "urlopen")
    def test_keyword_ideas_posts_live_task_and_tracks_cost(self, urlopen):
        urlopen.return_value = FakeResponse({
            "status_code": 20000,
            "cost": 0.05,
            "tasks": [{"status_code": 20000, "cost": 0.05,
                       "result": [{"items": [{"keyword": "snake game"}]}]}],
        })
        tasks = self.client.keyword_ideas(["snake game"])
        request = urlopen.call_args.args[0]
        self.assertTrue(request.full_url.endswith("/dataforseo_labs/google/keyword_ideas/live"))
        self.assertEqual(self.client.cost_usd, 0.05)
        self.assertEqual(self.client.items(tasks)[0]["keyword"], "snake game")

    @patch.object(dfs.urllib.request, "urlopen")
    def test_provider_task_error_is_not_silently_accepted(self, urlopen):
        urlopen.return_value = FakeResponse({
            "status_code": 20000,
            "tasks": [{"status_code": 40501, "status_message": "Invalid field"}],
        })
        with self.assertRaises(dfs.DataForSEOError):
            self.client.search_volume(["snake game"])

    def test_labs_keyword_row_normalization(self):
        normalized = mine_round.unpack_item({
            "keyword_data": {
                "keyword": "snake game",
                "keyword_info": {"search_volume": 1200, "cpc": 0.4,
                                 "competition": 0.2,
                                 "monthly_searches": [{"year": 2026, "month": 9,
                                                       "search_volume": 1100}]},
                "keyword_properties": {"keyword_difficulty": 17},
                "search_intent_info": {"main_intent": "informational"},
            }
        })
        self.assertEqual(normalized["keyword"], "snake game")
        self.assertEqual(normalized["search_volume"], 1200)
        self.assertEqual(normalized["keyword_difficulty"], 17)
        self.assertEqual(normalized["intent"], "informational")


if __name__ == "__main__":
    unittest.main()
