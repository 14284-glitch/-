import math

import pandas as pd

from services.dividend_service import (
    build_dividend_history,
    calculate_dividend,
    safe_number,
    simulate_reinvestment,
)


def test_dividend_calculator_supports_odd_lots_and_zero_denominators():
    result = calculate_dividend(250, 4, 0.1, 0, 0, 0.05, True)
    assert result.shares == 250
    assert result.lots == 0.25
    assert result.gross_cash_dividend == 1000
    assert result.stock_dividend_new_shares == 25
    assert result.yield_on_cost == 0
    assert result.current_yield == 0
    assert result.estimated_nhi_premium == 0


def test_supplementary_premium_uses_configured_threshold_and_rate():
    result = calculate_dividend(10_000, 2, 0, 100, 100, 0, True)
    assert result.gross_cash_dividend == 20_000
    assert result.estimated_nhi_premium == 422


def test_non_finite_inputs_never_escape_to_ui_results():
    result = calculate_dividend(float("nan"), float("inf"), -2, None, "bad", -1, True)
    assert all(math.isfinite(value) for value in result.__dict__.values())
    assert safe_number("undefined") == 0


def test_reinvestment_is_deterministic_and_preserves_columns():
    frame = simulate_reinvestment(1000, 100, 5, 0.1, 0.05, 10_000, 5)
    assert len(frame) == 5
    assert frame.iloc[0]["當年度現金股息"] == 5000
    assert frame.iloc[-1]["年末總持股"] > 1000
    assert "預估持股市值" in frame


def test_dividend_history_uses_prior_close_and_observed_fill_date():
    dividends = pd.Series(
        [2.0],
        index=pd.DatetimeIndex(["2025-06-18"], tz="Asia/Taipei"),
    )
    prices = pd.DataFrame({
        "trade_date": ["2025-06-17", "2025-06-18", "2025-06-19", "2025-06-20"],
        "close": [100, 97, 99, 101],
    })
    result = build_dividend_history(dividends, prices)
    assert result.iloc[0]["除息前參考價"] == 100
    assert result.iloc[0]["填息天數"] == 2
    assert result.iloc[0]["是否完成填息"] == "是"
