"""Market overview with normalized, colorblind-friendly cross-market lines."""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from config.color_config import COLORS, LINE_STYLES
from config.settings import PROJECT_ROOT
from pages.chart_factory import add_attention_trace, apply_chart_layout
from pages.glossary import market_legend_items, render_chart_with_legend, render_glossary


SERIES = {
    "台灣加權指數": ("tw/INDEX_TWII.csv", "twii"),
    "S&P 500｜標普500指數": ("us/INDEX_GSPC.csv", "sp500"),
    "Nasdaq 100｜那斯達克100指數": ("us/INDEX_NDX.csv", "nasdaq100"),
    "SOX｜費城半導體指數": ("us/INDEX_SOX.csv", "sox"),
}


def render() -> None:
    st.header("市場總覽")
    figure = go.Figure()
    for label, (relative_path, style_key) in SERIES.items():
        path = PROJECT_ROOT / "data" / "raw" / relative_path
        if not path.exists():
            continue
        frame = pd.read_csv(path)
        date_column = "trade_date" if "trade_date" in frame else "us_trade_date"
        frame[date_column] = pd.to_datetime(frame[date_column])
        frame = frame.tail(252)
        normalized = frame["close"] / frame["close"].iloc[0] * 100
        figure.add_trace(go.Scatter(
            x=frame[date_column], y=normalized, name=label, mode="lines",
            line=dict(color=COLORS["market"][style_key], width=3 if style_key == "twii" else 2,
                      dash=LINE_STYLES["market"][style_key]),
            hovertemplate=f"{label}：%{{y:.2f}}<extra></extra>",
        ))
    if not figure.data:
        st.warning("尚無市場資料，請先執行更新。")
        return
    first_trace = figure.data[0]
    attention_notes = pd.Series("比較臺灣加權指數與美股指數的相對強弱；若走勢明顯分歧，注意隔日連動風險。", index=range(len(first_trace.x)))
    add_attention_trace(figure, pd.Series(first_trace.x), pd.Series(first_trace.y), attention_notes)
    render_chart_with_legend(
        apply_chart_layout(figure, "主要市場近一年相對走勢（起點＝100）", "指數化價格", True),
        market_legend_items(),
        "market_overview",
    )
    render_glossary(("SP500", "NASDAQ100", "SOX"))
