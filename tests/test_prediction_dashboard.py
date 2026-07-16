from pathlib import Path

from pages.prediction_dashboard import load_prediction_data
from config.universe import TAIWAN_50_CONSTITUENTS, load_popular_etfs


def test_missing_prediction_file_is_handled(tmp_path: Path):
    frame, error = load_prediction_data(tmp_path / "missing.csv")
    assert frame.empty
    assert "尚未產生" in error


def test_invalid_prediction_date_is_rejected(tmp_path: Path):
    path = tmp_path / "prediction.csv"
    path.write_text("trade_date,probability_up_1d\nnot-a-date,0.7\n", encoding="utf-8")
    frame, error = load_prediction_data(path)
    assert frame.empty
    assert "有效的交易日期" in error


def test_prediction_universes_have_fifty_items():
    assert len(TAIWAN_50_CONSTITUENTS) == 50
    assert len(load_popular_etfs()) == 50
