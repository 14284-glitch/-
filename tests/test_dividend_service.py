import math

import pandas as pd

from services.dividend_service import (
    build_dividend_history,
    calculate_dividend,
    safe_number,
    simulate_reinvestment,
    summarize_cash_payment_frequency,
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


def test_payment_frequency_uses_unique_cash_payment_dates_and_completed_year():
    history = pd.DataFrame({
        "每股現金股利": [3, 3, 3, 3, 3, 3, 0],
        "發放日期": [
            "2025-01-10", "2025-04-10", "2025-07-10", "2025-10-10",
            "2025-10-10", "2026-04-10", "2025-08-01",
        ],
        "除息日期": [
            "2024-12-12", "2025-03-12", "2025-06-12", "2025-09-12",
            "2025-09-12", "2026-03-12", "2025-07-01",
        ],
    })
    result = summarize_cash_payment_frequency(history, as_of="2026-08-11")
    assert result["reference_year"] == 2025
    assert result["frequency_count"] == 4
    assert result["frequency_text"] == "每季"
    assert result["current_announced_count"] == 1
    assert result["current_paid_count"] == 1


def test_stock_only_event_is_not_counted_as_cash_payment():
    history = pd.DataFrame({
        "每股現金股利": [0],
        "發放日期": ["2025-09-01"],
        "除息日期": ["2025-08-01"],
    })
    result = summarize_cash_payment_frequency(history, as_of="2026-08-11")
    assert result["frequency_count"] == 0
    assert result["current_paid_count"] == 0


def test_quarterly_schedule_survives_one_missing_calendar_event():
    history = pd.DataFrame({
        "每股現金股利": [1, 1, 1, 1, 1, 1],
        "發放日期": [
            "2024-11-12", "2025-05-14", "2025-08-08",
            "2025-11-14", "2026-02-11", "2026-05-14",
        ],
        "除息日期": [
            "2024-10-17", "2025-04-23", "2025-07-21",
            "2025-10-23", "2026-01-22", "2026-04-23",
        ],
    })
    result = summarize_cash_payment_frequency(history, as_of="2026-08-11")
    assert result["completed_year_count"] == 3
    assert result["frequency_count"] == 4
    assert result["frequency_text"] == "每季"
