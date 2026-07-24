"""Single source of truth for all dashboard chart colors and line styles."""

COLORS = {
    "candlestick": {"up": "#D62728", "down": "#2CA02C", "volume_up": "#F4A6A6", "volume_down": "#A8D5A2"},
    "moving_average": {"ma5": "#F2C80F", "ma10": "#FF8C00", "ma20": "#1F77B4", "ma60": "#9467BD", "ma120": "#006400", "ma240": "#8B4513"},
    "bollinger": {"upper": "#76C7F0", "middle": "#174A7E", "lower": "#76C7F0", "fill": "rgba(31,119,180,0.12)"},
    "kd": {"k": "#0072B2", "d": "#E69F00", "overbought": "rgba(214,39,40,0.10)", "oversold": "rgba(44,160,44,0.10)"},
    "macd": {"dif": "#0072B2", "signal": "#E69F00", "positive": "#D62728", "negative": "#2CA02C", "zero": "#7F7F7F"},
    "rsi": {"line": "#7B2CBF", "overbought": "rgba(214,39,40,0.10)", "oversold": "rgba(44,160,44,0.10)", "midline": "#7F7F7F"},
    "dmi": {"plus_di": "#D62728", "minus_di": "#2CA02C", "adx": "#3C096C", "threshold": "#7F7F7F"},
    "institutional": {"foreign": "#0072B2", "trust": "#E69F00", "dealer": "#9467BD", "net_buy": "#D62728", "net_sell": "#2CA02C"},
    "prediction": {"actual": "#444444", "predicted": "#0096FF", "upper": "#F4A6A6", "lower": "#A8D5A2", "interval": "rgba(0,150,255,0.15)"},
    "backtest": {"strategy": "#0072B2", "benchmark": "#7F7F7F", "cash": "#E69F00", "drawdown": "#D62728", "zero": "#000000"},
    "signal": {"strong_buy": "#8B0000", "bullish": "#FF4500", "neutral": "#808080", "bearish": "#9ACD32", "high_risk": "#006400"},
    "market": {"twii": "#D62728", "sp500": "#0072B2", "nasdaq100": "#E69F00", "sox": "#7B2CBF", "vix": "#006400"},
    "layout": {
        "grid": "rgba(127,127,127,0.18)", "axis": "#6B7280", "background": "rgba(0,0,0,0)",
        "tooltip_background": "#000000", "tooltip_text": "#FFFFFF", "tooltip_border": "#FFFFFF",
        "attention_background": "#FFF4B8", "attention_text": "#123B6D", "attention_border": "#D4A72C",
        "date_cursor": "#123B6D",
    },
}

LINE_STYLES = {
    "moving_average": {"ma5": 2, "ma10": 2, "ma20": 3, "ma60": 3, "ma120": 2, "ma240": 2},
    "bollinger": {"upper": "dash", "middle": "solid", "lower": "dash"},
    "prediction": {"actual": "solid", "predicted": "solid", "upper": "dash", "lower": "dash"},
    "reference": "dash",
    "market": {"twii": "solid", "sp500": "dash", "nasdaq100": "dot", "sox": "dashdot", "vix": "longdash"},
}

PLOTLY_CONFIG = {
    "displaylogo": False,
    "scrollZoom": False,
    "doubleClick": False,
    "editable": False,
    "responsive": True,
    "modeBarButtonsToRemove": [
        "zoom2d", "pan2d", "zoomIn2d", "zoomOut2d",
        "autoScale2d", "resetScale2d", "lasso2d", "select2d",
    ],
    "toImageButtonOptions": {"format": "png", "scale": 2},
}
