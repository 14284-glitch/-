import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from collectors.etf_popularity_collector import collect_popular_etfs


class EtfPopularityTests(unittest.TestCase):
    def test_official_rows_are_sorted_by_traded_value(self) -> None:
        rows = [[f"00{index:04d}", f"ETF{index}", f"{index:,}"] for index in range(1, 61)]
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"tables": [{
            "title": "test", "fields": ["證券代號", "證券名稱", "成交金額"], "data": rows,
        }]}
        with tempfile.TemporaryDirectory() as directory, patch(
            "collectors.etf_popularity_collector.requests.get", return_value=response
        ):
            target = Path(directory) / "popular.json"
            result = collect_popular_etfs(target, limit=50)
            document = json.loads(target.read_text(encoding="utf-8"))
        self.assertEqual(result["rows"], 50)
        self.assertEqual(document["items"][0]["code"], "000060")
        self.assertEqual(document["items"][-1]["code"], "000011")


if __name__ == "__main__":
    unittest.main()
