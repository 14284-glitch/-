import unittest

from config.color_config import COLORS, LINE_STYLES
from config.settings import Settings
from config.universe import POPULAR_ETFS_TOP_50, TAIWAN_50_CONSTITUENTS, TW_SYMBOLS


class ConfigurationTests(unittest.TestCase):
    def test_default_signal_thresholds_are_ordered(self) -> None:
        settings = Settings()
        self.assertLessEqual(settings.signal_high_risk_threshold, settings.signal_bearish_threshold)
        self.assertLessEqual(settings.signal_bearish_threshold, settings.signal_bullish_threshold)
        self.assertLessEqual(settings.signal_bullish_threshold, settings.signal_strong_buy_threshold)

    def test_required_color_palette_is_centralized(self) -> None:
        self.assertEqual(COLORS["candlestick"]["up"], "#D62728")
        self.assertEqual(COLORS["candlestick"]["down"], "#2CA02C")
        self.assertGreaterEqual(LINE_STYLES["moving_average"]["ma20"], 2)
        self.assertGreaterEqual(LINE_STYLES["moving_average"]["ma60"], 2)

    def test_taiwan_50_stocks_and_etf_are_available(self) -> None:
        self.assertEqual(len(TAIWAN_50_CONSTITUENTS), 50)
        self.assertEqual(len(POPULAR_ETFS_TOP_50), 50)
        self.assertTrue(set(TAIWAN_50_CONSTITUENTS).issubset(TW_SYMBOLS))
        self.assertIn("0050.TW", TW_SYMBOLS)


if __name__ == "__main__":
    unittest.main()
