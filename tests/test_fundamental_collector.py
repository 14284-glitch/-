from datetime import date
from pathlib import Path

import pandas as pd

from collectors.fundamental_collector import collect_latest_fundamentals
from features.point_in_time_integrator import attach_point_in_time_features


class FakeResponse:
    def __init__(self, rows):
        self.rows = rows

    def raise_for_status(self):
        return None

    def json(self):
        return {"status": 200, "data": self.rows}


class FakeSession:
    def get(self, _url, params, timeout):
        dataset = params["dataset"]
        rows = {
            "TaiwanStockMonthRevenue": [
                {
                    "date": f"2025-{month:02d}-01",
                    "stock_id": "2330",
                    "revenue": 100 + month,
                    "create_time": "",
                }
                for month in range(1, 13)
            ] + [{
                "date": "2026-01-01",
                "stock_id": "2330",
                "revenue": 130,
                "create_time": "2026-02-10",
            }],
            "TaiwanStockPER": [{
                "date": "2026-02-10", "stock_id": "2330",
                "PER": 20, "PBR": 5, "dividend_yield": 2.5,
            }],
            "TaiwanStockFinancialStatements": [{
                "date": "2025-12-31", "stock_id": "2330",
                "type": "BasicEarningsPerShare", "value": 12,
            }],
            "TaiwanStockBalanceSheet": [],
            "TaiwanStockCashFlowsStatement": [],
        }[dataset]
        return FakeResponse(rows)


def test_latest_fundamental_snapshot_is_regularly_merged_and_point_in_time(tmp_path: Path):
    output = tmp_path / "processed" / "financial_features.csv"
    result = collect_latest_fundamentals(
        output, "token", ["2330"], session=FakeSession(), today=date(2026, 2, 10)
    )
    saved = pd.read_csv(output)

    assert result["completed"] == ["2330"]
    assert saved.iloc[-1]["pe_ratio"] == 20
    assert saved.iloc[-1]["pb_ratio"] == 5
    assert saved.iloc[-1]["eps"] == 12
    assert saved.iloc[-1]["revenue_yoy"] > 0
    assert saved.iloc[-1]["effective_trade_date"] == "2026-02-11"

    frame = pd.DataFrame({
        "trade_date": pd.to_datetime(["2026-02-10", "2026-02-11", "2026-02-12"]),
        "close": [100, 101, 102],
    })
    joined, stages = attach_point_in_time_features(frame, "2330.TW", output.parent)
    assert joined.iloc[0]["pe_ratio"] == 0
    assert joined.iloc[1]["pe_ratio"] == 20
    assert joined.iloc[2]["pe_ratio"] == 20
    assert stages["第三階段｜基本面估值與產業"] is True
