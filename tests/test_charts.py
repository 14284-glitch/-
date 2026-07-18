import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from config.color_config import COLORS, LINE_STYLES
from config.indicator_glossary import INDICATOR_GLOSSARY, bilingual
from features.technical_indicators import add_technical_indicators
from pages.chart_factory import RANGE_BUTTONS, kd_chart, macd_chart, prediction_chart, price_chart, rsi_chart, volume_chart


def sample_prices(rows: int = 260) -> pd.DataFrame:
    close = pd.Series(100 + np.arange(rows) * 0.25 + np.sin(np.arange(rows) / 5))
    return pd.DataFrame({
        "trade_date": pd.date_range("2025-01-01", periods=rows, freq="D"),
        "open": close - 0.5, "high": close + 1, "low": close - 1,
        "close": close, "volume": np.arange(rows) * 1000 + 100_000,
    })


class ChartDesignTests(unittest.TestCase):
    def setUp(self) -> None:
        self.frame = add_technical_indicators(sample_prices())

    def test_price_chart_uses_taiwan_candle_and_ma_palette(self) -> None:
        figure = price_chart(self.frame, "測試股票")
        candle = figure.data[0]
        self.assertEqual(candle.increasing.line.color, COLORS["candlestick"]["up"])
        self.assertEqual(candle.decreasing.line.color, COLORS["candlestick"]["down"])
        traces = {trace.name: trace for trace in figure.data if trace.name != "觀看提醒"}
        for key in ("ma5", "ma10", "ma20", "ma60", "ma120", "ma240"):
            trace = traces[bilingual(key.upper(), key.upper())]
            self.assertEqual(trace.line.color, COLORS["moving_average"][key])
            self.assertGreaterEqual(trace.line.width, 2)

    def test_every_chart_has_legend_hover_range_selector_and_zoomable_axes(self) -> None:
        for figure in (price_chart(self.frame, "測試"), volume_chart(self.frame), kd_chart(self.frame),
                       macd_chart(self.frame), rsi_chart(self.frame)):
            self.assertEqual(figure.layout.hovermode, "x")
            self.assertIsNotNone(figure.layout.legend)
            self.assertEqual(figure.layout.legend.orientation, "v")
            self.assertGreater(float(figure.layout.legend.x), 1.0)
            self.assertGreater(len(figure.layout.xaxis.rangeselector.buttons), 0)
            self.assertTrue(figure.layout.xaxis.rangeslider.visible)
            self.assertFalse(figure.layout.yaxis.fixedrange)
            self.assertEqual(figure.layout.xaxis.tickformat, "%Y/%m/%d")
            self.assertEqual(figure.layout.xaxis.hoverformat, "%Y/%m/%d")
            self.assertGreaterEqual(len(figure.layout.xaxis.tickformatstops), 4)
            self.assertEqual(figure.layout.xaxis.tickformatstops[2].value, "%Y/%m")
            self.assertEqual(figure.layout.xaxis.tickformatstops[3].value, "%Y")
            self.assertEqual(figure.layout.hoverlabel.bgcolor, COLORS["layout"]["tooltip_background"])
            self.assertEqual(figure.layout.hoverlabel.font.color, COLORS["layout"]["tooltip_text"])
            self.assertTrue(figure.layout.xaxis.showspikes)

    def test_range_selector_has_requested_day_intervals(self) -> None:
        day_buttons = {
            (button["count"], button["label"], button["step"])
            for button in RANGE_BUTTONS if button.get("step") == "day"
        }
        self.assertEqual(day_buttons, {
            (4, "4天", "day"), (5, "5天", "day"), (7, "7天", "day"),
            (10, "10天", "day"), (15, "15天", "day"),
        })

    def test_prediction_chart_distinguishes_all_required_series(self) -> None:
        prediction = pd.DataFrame({
            "trade_date": pd.date_range("2026-01-01", periods=5), "actual_price": range(100, 105),
            "predicted_price": range(101, 106), "prediction_upper": range(105, 110),
            "prediction_lower": range(95, 100),
        })
        figure = prediction_chart(prediction)
        traces = {trace.name: trace for trace in figure.data if trace.name != "觀看提醒"}
        actual = bilingual("ACTUAL_PRICE", "Actual Price")
        predicted = bilingual("PREDICTED_PRICE", "Predicted Price")
        self.assertEqual(set(traces), {actual, predicted, "Prediction Upper｜預測上界", "Prediction Lower｜預測下界"})
        self.assertEqual(traces["Prediction Lower｜預測下界"].fillcolor, COLORS["prediction"]["interval"])
        self.assertNotEqual(traces[actual].line.dash, traces[predicted].line.dash)

    def test_glossary_contains_chinese_name_and_purpose_for_every_term(self) -> None:
        for chinese, purpose in INDICATOR_GLOSSARY.values():
            self.assertTrue(chinese.strip())
            self.assertGreater(len(purpose), 8)

    def test_legend_tooltip_uses_central_black_and_white_palette(self) -> None:
        self.assertEqual(COLORS["layout"]["tooltip_background"], "#000000")
        self.assertEqual(COLORS["layout"]["tooltip_text"], "#FFFFFF")
        self.assertEqual(COLORS["layout"]["attention_background"], "#FFF4B8")
        self.assertEqual(COLORS["layout"]["attention_text"], "#123B6D")

    def test_indicator_calculation_does_not_change_past_when_future_rows_are_added(self) -> None:
        past = sample_prices(100)
        extended = sample_prices(130)
        past_features = add_technical_indicators(past)
        extended_features = add_technical_indicators(extended).iloc[:100]
        for column in ("ma20", "kd_k", "macd", "rsi14", "bollinger_upper"):
            pd.testing.assert_series_equal(past_features[column], extended_features[column], check_names=False)

    def test_dashboard_pages_do_not_embed_hex_colors(self) -> None:
        pages_dir = Path(__file__).parents[1] / "pages"
        for path in pages_dir.glob("*.py"):
            text = path.read_text(encoding="utf-8")
            self.assertNotRegex(text, r"#[0-9A-Fa-f]{6}", msg=f"hard-coded color in {path.name}")

    def test_pages_render_charts_only_through_right_side_legend_layout(self) -> None:
        pages_dir = Path(__file__).parents[1] / "pages"
        for path in pages_dir.glob("*_analysis.py"):
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("st.plotly_chart", text)
            self.assertIn("render_chart_with_legend", text)
        for filename in ("market_overview.py", "prediction_dashboard.py"):
            text = (pages_dir / filename).read_text(encoding="utf-8")
            self.assertNotIn("st.plotly_chart", text)
            self.assertIn("render_chart_with_legend", text)


if __name__ == "__main__":
    unittest.main()
