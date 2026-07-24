import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from config.color_config import COLORS, LINE_STYLES
from config.indicator_glossary import INDICATOR_GLOSSARY, bilingual
from features.technical_indicators import add_technical_indicators
from pages.chart_factory import kd_chart, macd_chart, prediction_chart, price_chart, rsi_chart, volume_chart
from pages.glossary import DATE_RANGE_OPTIONS, _figure_y_bounds, _selected_date_bounds
from pages.stock_analysis import _load_price_history


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

    def test_every_chart_has_hover_and_disables_in_chart_zoom(self) -> None:
        for figure in (price_chart(self.frame, "測試"), volume_chart(self.frame), kd_chart(self.frame),
                       macd_chart(self.frame), rsi_chart(self.frame)):
            self.assertEqual(figure.layout.hovermode, "x")
            self.assertIsNotNone(figure.layout.legend)
            self.assertEqual(figure.layout.legend.orientation, "v")
            self.assertGreater(float(figure.layout.legend.x), 1.0)
            self.assertFalse(figure.layout.xaxis.rangeslider.visible)
            self.assertTrue(figure.layout.xaxis.fixedrange)
            self.assertTrue(figure.layout.yaxis.fixedrange)
            self.assertFalse(figure.layout.dragmode)
            self.assertEqual(figure.layout.xaxis.tickformat, "%Y/%m/%d")
            self.assertEqual(figure.layout.xaxis.hoverformat, "%Y/%m/%d")
            self.assertGreaterEqual(len(figure.layout.xaxis.tickformatstops), 4)
            self.assertEqual(figure.layout.xaxis.tickformatstops[2].value, "%Y/%m")
            self.assertEqual(figure.layout.xaxis.tickformatstops[3].value, "%Y")
            self.assertEqual(figure.layout.hoverlabel.bgcolor, COLORS["layout"]["tooltip_background"])
            self.assertEqual(figure.layout.hoverlabel.font.color, COLORS["layout"]["tooltip_text"])
            self.assertTrue(figure.layout.xaxis.showspikes)
            self.assertGreaterEqual(figure.layout.height, 480)

    def test_external_date_dropdown_has_requested_intervals_and_defaults_to_one_day(self) -> None:
        self.assertEqual(list(DATE_RANGE_OPTIONS)[:7], ["1天", "3天", "4天", "5天", "7天", "10天", "15天"])
        dates = pd.Series(pd.date_range("2026-01-01", periods=30))
        start, end = _selected_date_bounds(dates, "1天")
        self.assertEqual((end - start).days, 1)
        self.assertEqual(_selected_date_bounds(dates, "全部日期"), (None, None))

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

    def test_external_legend_layout_gives_chart_most_of_the_width(self) -> None:
        pages_dir = Path(__file__).parents[1] / "pages"
        text = (pages_dir / "glossary.py").read_text(encoding="utf-8")
        self.assertIn("st.columns([84, 16]", text)
        self.assertIn("margin=dict(l=50, r=18", text)
        for filename in ("market_overview.py", "prediction_dashboard.py"):
            text = (pages_dir / filename).read_text(encoding="utf-8")
            self.assertNotIn("st.plotly_chart", text)
            self.assertIn("render_chart_with_legend", text)

    def test_right_side_range_slider_can_derive_chart_bounds(self) -> None:
        figure = price_chart(self.frame, "測試")
        minimum, maximum = _figure_y_bounds(figure)
        self.assertIsNotNone(minimum)
        self.assertIsNotNone(maximum)
        self.assertLess(minimum, maximum)

    def test_chart_range_protection_keeps_highest_and_lowest_points_visible(self) -> None:
        figure = price_chart(self.frame, "測試")
        minimum, maximum = _figure_y_bounds(figure)
        span = maximum - minimum
        padding = max(span * 0.06, abs(maximum) * 0.005, 0.01)
        protected_range = [minimum - padding, maximum + padding]
        self.assertLess(protected_range[0], minimum)
        self.assertGreater(protected_range[1], maximum)

        glossary_source = (Path(__file__).parents[1] / "pages" / "glossary.py").read_text(encoding="utf-8")
        self.assertIn("曲線範圍縮放", glossary_source)
        self.assertIn("protected_range", glossary_source)

    def test_external_controls_include_reset_and_fixed_dropdown(self) -> None:
        glossary_source = (Path(__file__).parents[1] / "pages" / "glossary.py").read_text(encoding="utf-8")
        self.assertIn('"日期篩選"', glossary_source)
        self.assertIn('"↺ 回復原始圖形曲線"', glossary_source)
        self.assertIn("accept_new_options=False", glossary_source)
        self.assertIn("filter_mode=None", glossary_source)
        self.assertIn('title=dict(text=f"{dynamic_title_prefix}｜{selected_period}"', glossary_source)

    def test_market_overview_defaults_to_three_months(self) -> None:
        market_source = (Path(__file__).parents[1] / "pages" / "market_overview.py").read_text(encoding="utf-8")
        self.assertIn('default_period="3個月"', market_source)
        self.assertIn('dynamic_title_prefix="主要市場相對走勢"', market_source)

    def test_all_stock_analysis_charts_default_to_seven_days(self) -> None:
        stock_source = (Path(__file__).parents[1] / "pages" / "stock_analysis.py").read_text(encoding="utf-8")
        self.assertEqual(stock_source.count('default_period="7天"'), 5)

    def test_stock_analysis_accepts_mixed_date_formats(self) -> None:
        path = Path(self._testMethodName + ".csv")
        try:
            frame = sample_prices(2)
            frame["trade_date"] = ["2026-07-23 00:00:00", "2026-07-24"]
            frame.to_csv(path, index=False)
            loaded = _load_price_history(path)
            self.assertTrue(pd.api.types.is_datetime64_any_dtype(loaded["trade_date"]))
            self.assertEqual(len(loaded), 2)
        finally:
            path.unlink(missing_ok=True)

    def test_plotly_config_removes_all_in_chart_zoom_controls(self) -> None:
        from config.color_config import PLOTLY_CONFIG

        self.assertFalse(PLOTLY_CONFIG["scrollZoom"])
        self.assertFalse(PLOTLY_CONFIG["doubleClick"])
        self.assertFalse(PLOTLY_CONFIG["editable"])
        for button in ("zoom2d", "pan2d", "zoomIn2d", "zoomOut2d", "autoScale2d", "resetScale2d"):
            self.assertIn(button, PLOTLY_CONFIG["modeBarButtonsToRemove"])

    def test_mobile_charts_ignore_pinch_and_drag_zoom(self) -> None:
        app_source = (Path(__file__).parents[1] / "app.py").read_text(encoding="utf-8")
        self.assertIn("touch-action: pan-y !important", app_source)


if __name__ == "__main__":
    unittest.main()
